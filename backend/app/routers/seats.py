import csv
import io
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from .. import models, schemas
from ..database import get_db
from ..services import allocate_seat, release_seat, update_seat_status, get_active_allocation_for_seat, AllocationError

router = APIRouter(prefix="/seats", tags=["Seats"])


def _seat_to_out(db: Session, seat: models.Seat) -> schemas.SeatOut:
    occupied_by = None
    occupied_by_project = None
    allocation_date = None
    allocation = get_active_allocation_for_seat(db, seat.id)
    if allocation:
        emp = db.query(models.Employee).get(allocation.employee_id)
        occupied_by = emp.name if emp else None
        if allocation.project_id:
            project = db.query(models.Project).get(allocation.project_id)
            occupied_by_project = project.name if project else None
        allocation_date = allocation.allocation_date
    return schemas.SeatOut(
        id=seat.id, floor=seat.floor, zone=seat.zone, bay=seat.bay,
        seat_number=seat.seat_number, status=seat.status, occupied_by=occupied_by,
        occupied_by_project=occupied_by_project, allocation_date=allocation_date,
    )


@router.post("", response_model=schemas.SeatOut, status_code=201)
def create_seat(payload: schemas.SeatCreate, db: Session = Depends(get_db)):
    dup = (
        db.query(models.Seat)
        .filter(
            models.Seat.floor == payload.floor,
            models.Seat.zone == payload.zone,
            models.Seat.seat_number == payload.seat_number,
        )
        .first()
    )
    if dup:
        raise HTTPException(status_code=409, detail="A seat with this floor/zone/seat_number already exists")
    seat = models.Seat(**payload.model_dump())
    db.add(seat)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate seat number on this floor/zone")
    db.refresh(seat)
    return _seat_to_out(db, seat)


@router.post("/upload-csv", response_model=schemas.CSVUploadResult)
def upload_seats_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Bulk-create seats from a CSV. Expected headers (case-insensitive):
      floor, zone, seat_number  (required)
      bay, status  (optional; status defaults to 'available')
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

    required = {"floor", "zone", "seat_number"}
    missing_headers = required - set(reader.fieldnames)
    if missing_headers:
        raise HTTPException(
            status_code=400,
            detail=f"CSV is missing required column(s): {', '.join(sorted(missing_headers))}. "
            "Expected headers: floor, zone, bay, seat_number, status",
        )

    existing_keys = {
        (s.floor, s.zone, s.seat_number) for s in db.query(models.Seat.floor, models.Seat.zone, models.Seat.seat_number)
    }
    valid_statuses = {s.value for s in models.SeatStatus}

    to_add: List[models.Seat] = []
    errors: List[str] = []
    warnings: List[str] = []

    for i, row in enumerate(reader, start=2):
        raw_floor = (row.get("floor") or "").strip()
        zone = (row.get("zone") or "").strip().upper()
        seat_number = (row.get("seat_number") or "").strip()

        if not raw_floor or not zone or not seat_number:
            errors.append(f"Row {i}: missing floor, zone, or seat_number — skipped")
            continue
        try:
            floor = int(raw_floor)
        except ValueError:
            errors.append(f"Row {i}: floor '{raw_floor}' is not a number — skipped")
            continue

        key = (floor, zone, seat_number)
        if key in existing_keys:
            errors.append(f"Row {i}: seat {seat_number} on Floor {floor} Zone {zone} already exists — skipped")
            continue

        status_raw = (row.get("status") or "available").strip().lower()
        if status_raw not in valid_statuses:
            warnings.append(f"Row {i}: unknown status '{status_raw}', defaulted to 'available'")
            status_raw = "available"

        to_add.append(
            models.Seat(
                floor=floor,
                zone=zone,
                bay=(row.get("bay") or "").strip() or None,
                seat_number=seat_number,
                status=status_raw,
            )
        )
        existing_keys.add(key)

    for seat in to_add:
        db.add(seat)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Upload failed on a duplicate value — please retry")

    return schemas.CSVUploadResult(created=len(to_add), skipped=len(errors), errors=errors[:50], warnings=warnings[:50])


@router.get("", response_model=List[schemas.SeatOut])
def list_seats(
    floor: Optional[int] = None,
    zone: Optional[str] = None,
    status: Optional[models.SeatStatus] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(models.Seat)
    if floor is not None:
        q = q.filter(models.Seat.floor == floor)
    if zone:
        q = q.filter(models.Seat.zone == zone)
    if status:
        q = q.filter(models.Seat.status == status)
    seats = q.order_by(models.Seat.floor, models.Seat.zone, models.Seat.seat_number).offset(offset).limit(limit).all()
    return [_seat_to_out(db, s) for s in seats]


@router.get("/available", response_model=List[schemas.SeatOut])
def list_available_seats(
    floor: Optional[int] = None,
    zone: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    q = db.query(models.Seat).filter(models.Seat.status == models.SeatStatus.available)
    if floor is not None:
        q = q.filter(models.Seat.floor == floor)
    if zone:
        q = q.filter(models.Seat.zone == zone)
    seats = q.order_by(models.Seat.floor, models.Seat.zone, models.Seat.seat_number).limit(limit).all()
    return [_seat_to_out(db, s) for s in seats]
@router.patch("/{seat_id}/status", response_model=schemas.SeatOut)
def update_status(seat_id: int, payload: schemas.SeatStatusUpdate, db: Session = Depends(get_db)):
    try:
        seat = update_seat_status(db, seat_id=seat_id, new_status=payload.status)
    except AllocationError as e:
        detail = str(e)
        code = 404 if "not found" in detail else 409 if "occupied" in detail else 400
        raise HTTPException(status_code=code, detail=detail)
    return _seat_to_out(db, seat)


@router.post("/allocate", response_model=schemas.AllocationOut)
def allocate(payload: schemas.AllocateRequest, db: Session = Depends(get_db)):
    try:
        allocation = allocate_seat(
            db,
            employee_id=payload.employee_id,
            project_id=payload.project_id,
            seat_id=payload.seat_id,
            preferred_floor=payload.preferred_floor,
            preferred_zone=payload.preferred_zone,
        )
    except AllocationError as e:
        raise HTTPException(status_code=409, detail=str(e))

@router.post("/release", response_model=schemas.AllocationOut)
def release(payload: schemas.ReleaseRequest, db: Session = Depends(get_db)):
    try:
        allocation = release_seat(db, employee_id=payload.employee_id, seat_id=payload.seat_id)
    except AllocationError as e:
        raise HTTPException(status_code=409, detail=str(e))
    out = schemas.AllocationOut.model_validate(allocation)
    seat = db.query(models.Seat).get(allocation.seat_id)
    if seat:
        out.seat = _seat_to_out(db, seat)
    return out
