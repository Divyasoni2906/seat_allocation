from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from .. import models, schemas
from ..database import get_db
from .employees import _to_out as employee_to_out

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post("", response_model=schemas.ProjectOut, status_code=201)
def create_project(payload: schemas.ProjectCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Project).filter(models.Project.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Project with this name already exists")
    project = models.Project(**payload.model_dump())
    db.add(project)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate project name")
    db.refresh(project)
    return project


@router.get("", response_model=List[schemas.ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return (
        db.query(models.Project)
        .filter(models.Project.status == models.ProjectStatus.active)
        .order_by(models.Project.name)
        .all()
    )


@router.get("/{project_id}/employees", response_model=List[schemas.EmployeeOut])
def list_project_employees(project_id: int, db: Session = Depends(get_db)):
    project = db.query(models.Project).get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    employees = db.query(models.Employee).filter(models.Employee.project_id == project_id).all()
    return [employee_to_out(db, e) for e in employees]


@router.delete("/{project_id}", status_code=200)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    """
    Projects with no employees and no seat-allocation history referencing
    them are removed outright. Otherwise the project is soft-deleted (its
    `status` flips to `inactive` and it drops out of the active project
    list/dropdowns) instead of being destroyed, since a hard delete would
    either orphan those employees' project_id or cascade-delete real
    allocation history -- exactly the kind of silent data loss the seat
    release logic elsewhere was built to avoid.
    """
    project = db.query(models.Project).get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    employee_count = db.query(models.Employee).filter(models.Employee.project_id == project_id).count()
    allocation_count = db.query(models.SeatAllocation).filter(models.SeatAllocation.project_id == project_id).count()

    if employee_count == 0 and allocation_count == 0:
        name = project.name
        db.delete(project)
        db.commit()
        return {"detail": f"Project {name} permanently deleted."}

    project.status = models.ProjectStatus.inactive
    db.commit()
    return {
        "detail": (
            f"Project {project.name} marked inactive and removed from the active list — "
            f"still referenced by {employee_count} employee(s) and {allocation_count} seat allocation "
            "record(s), so it can't be permanently deleted without losing that history. "
            "Reassign those employees first if you need it gone entirely."
        )
    }