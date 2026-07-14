import csv
import io
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from .. import models, schemas
from ..database import get_db
from ..services import get_active_allocation_for_employee, release_seat, AllocationError

router = APIRouter(prefix="/employees", tags=["Employees"])


def _to_out(db: Session, emp: models.Employee) -> schemas.EmployeeOut:
    allocation = get_active_allocation_for_employee(db, emp.id)
    seat_desc = None
    if allocation:
        seat = db.query(models.Seat).get(allocation.seat_id)
        if seat:
            seat_desc = f"Floor {seat.floor}, Zone {seat.zone}, Seat {seat.seat_number}"
    return schemas.EmployeeOut(
        id=emp.id,
        employee_code=emp.employee_code,
        name=emp.name,
        email=emp.email,
        department=emp.department,
        role=emp.role,
        joining_date=emp.joining_date,
        status=emp.status,
        project_id=emp.project_id,
        project_name=emp.project.name if emp.project else None,
        current_seat=seat_desc,
    )


@router.post("", response_model=schemas.EmployeeOut, status_code=201)
def create_employee(payload: schemas.EmployeeCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Employee).filter(models.Employee.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Employee with this email already exists")
    existing_code = db.query(models.Employee).filter(models.Employee.employee_code == payload.employee_code).first()
    if existing_code:
        raise HTTPException(status_code=409, detail="Employee code already exists")

    emp = models.Employee(**payload.model_dump())
    db.add(emp)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate employee email or code")
    db.refresh(emp)
    return _to_out(db, emp)


@router.post("/upload-csv", response_model=schemas.CSVUploadResult)
def upload_employees_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Bulk-create employees from a CSV. Expected headers (case-insensitive):
      employee_code, name, email  (required)
      department, role, joining_date (YYYY-MM-DD), project_name  (optional)

    Every row is validated independently -- one bad row is reported and
    skipped rather than failing the whole upload. New employees always
    start as 'pending' (matching the single-employee create form): status
    only flips to 'active' once an actual seat is allocated, so the
    dashboard's "new joiners pending allocation" count stays meaningful
    even if a project was included in the CSV.
    """
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")

    raw = file.file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Could not decode file — please save it as UTF-8 CSV")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV file appears to be empty")
    reader.fieldnames = [(h or "").strip().lower() for h in reader.fieldnames]

    required = {"employee_code", "name", "email"}
    missing_headers = required - set(reader.fieldnames)
    if missing_headers:
        raise HTTPException(
            status_code=400,
            detail=f"CSV is missing required column(s): {', '.join(sorted(missing_headers))}. "
            "Expected headers: employee_code, name, email, department, role, joining_date, project_name",
        )

    projects_by_name = {p.name.strip().lower(): p.id for p in db.query(models.Project).all()}
    existing_emails = {e.lower() for (e,) in db.query(models.Employee.email).all()}
    existing_codes = {c for (c,) in db.query(models.Employee.employee_code).all()}

    to_add: List[models.Employee] = []
    errors: List[str] = []
    warnings: List[str] = []

    for i, row in enumerate(reader, start=2):  # row 1 is the header
        code = (row.get("employee_code") or "").strip()
        name = (row.get("name") or "").strip()
        email = (row.get("email") or "").strip()

        if not code or not name or not email:
            errors.append(f"Row {i}: missing employee_code, name, or email — skipped")
            continue
        if email.lower() in existing_emails:
            errors.append(f"Row {i}: email '{email}' already exists — skipped")
            continue
        if code in existing_codes:
            errors.append(f"Row {i}: employee_code '{code}' already exists — skipped")
            continue

        joining_date = None
        raw_date = (row.get("joining_date") or "").strip()
        if raw_date:
            try:
                joining_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
            except ValueError:
                warnings.append(f"Row {i}: could not parse joining_date '{raw_date}' (use YYYY-MM-DD) — left blank")

        project_id = None
        raw_project = (row.get("project_name") or row.get("project") or "").strip()
        if raw_project:
            project_id = projects_by_name.get(raw_project.lower())
            if project_id is None:
                warnings.append(f"Row {i}: project '{raw_project}' not found — left unassigned (pending)")

        to_add.append(
            models.Employee(
                employee_code=code,
                name=name,
                email=email,
                department=(row.get("department") or "").strip() or None,
                role=(row.get("role") or "").strip() or None,
                joining_date=joining_date,
                project_id=project_id,
                status=models.EmployeeStatus.pending,
            )
        )
        existing_emails.add(email.lower())
        existing_codes.add(code)

    for emp in to_add:
        db.add(emp)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Upload failed on a duplicate value — please retry")

    return schemas.CSVUploadResult(created=len(to_add), skipped=len(errors), errors=errors[:50], warnings=warnings[:50])


@router.delete("/{employee_id}/permanent", status_code=200)
def delete_employee_permanent(employee_id: int, db: Session = Depends(get_db)):
    """
    Hard-delete for cleaning up an accidental duplicate or test employee.
    Blocked if the employee has any seat allocation history at all (active
    or already released) so a real employee's audit trail can never be
    silently destroyed this way -- deactivate_employee (soft delete) is
    the correct path for anyone who's actually used the system.
    """
    emp = db.query(models.Employee).get(employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    allocation_count = db.query(models.SeatAllocation).filter(models.SeatAllocation.employee_id == employee_id).count()
    if allocation_count > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{emp.name} has {allocation_count} seat allocation record(s) in their history — "
                "permanent delete is blocked to protect that history. Use Deactivate instead."
            ),
        )

    name = emp.name
    db.delete(emp)
    db.commit()
    return {"detail": f"Employee {name} permanently deleted."}


@router.get("", response_model=List[schemas.EmployeeOut])
def list_employees(
    search: Optional[str] = Query(None, description="Match name, email, or employee_code"),
    department: Optional[str] = None,
    status: Optional[models.EmployeeStatus] = None,
    project_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(models.Employee)
    if search:
        like = f"%{search}%"
        q = q.filter(
            (models.Employee.name.ilike(like))
            | (models.Employee.email.ilike(like))
            | (models.Employee.employee_code.ilike(like))
        )
    if department:
        q = q.filter(models.Employee.department == department)
    if status:
        q = q.filter(models.Employee.status == status)
    if project_id:
        q = q.filter(models.Employee.project_id == project_id)

    employees = q.order_by(models.Employee.id).offset(offset).limit(limit).all()
    return [_to_out(db, e) for e in employees]


@router.get("/{employee_id}", response_model=schemas.EmployeeOut)
def get_employee(employee_id: int, db: Session = Depends(get_db)):
    emp = db.query(models.Employee).get(employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return _to_out(db, emp)


@router.put("/{employee_id}", response_model=schemas.EmployeeOut)
def update_employee(employee_id: int, payload: schemas.EmployeeUpdate, db: Session = Depends(get_db)):
    emp = db.query(models.Employee).get(employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    data = payload.model_dump(exclude_unset=True)
    if "email" in data and data["email"] != emp.email:
        clash = db.query(models.Employee).filter(models.Employee.email == data["email"]).first()
        if clash:
            raise HTTPException(status_code=409, detail="Another employee already uses this email")

    for field, value in data.items():
        setattr(emp, field, value)

    db.commit()
    db.refresh(emp)
    return _to_out(db, emp)


@router.delete("/{employee_id}", status_code=200)
def deactivate_employee(employee_id: int, db: Session = Depends(get_db)):
    emp = db.query(models.Employee).get(employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    seat_released = False
    try:
        release_seat(db, employee_id=employee_id)
        seat_released = True
    except AllocationError:
        # No active allocation for this employee — nothing to release, that's fine.
        pass

    emp.status = models.EmployeeStatus.inactive
    db.commit()
    detail = f"Employee {emp.name} marked inactive"
    if seat_released:
        detail += " and their seat was released"
    return {"detail": detail}