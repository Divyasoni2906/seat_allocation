from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary", response_model=schemas.DashboardSummary)
def summary(db: Session = Depends(get_db)):
    total_employees = db.query(models.Employee).count()
    total_seats = db.query(models.Seat).count()
    occupied = db.query(models.Seat).filter(models.Seat.status == models.SeatStatus.occupied).count()
    available = db.query(models.Seat).filter(models.Seat.status == models.SeatStatus.available).count()
    reserved = db.query(models.Seat).filter(models.Seat.status == models.SeatStatus.reserved).count()
    maintenance = db.query(models.Seat).filter(models.Seat.status == models.SeatStatus.maintenance).count()
    pending = db.query(models.Employee).filter(models.Employee.status == models.EmployeeStatus.pending).count()

    return schemas.DashboardSummary(
        total_employees=total_employees,
        total_seats=total_seats,
        occupied_seats=occupied,
        available_seats=available,
        reserved_seats=reserved,
        maintenance_seats=maintenance,
        new_joiners_pending=pending,
    )


@router.get("/project-utilization", response_model=List[schemas.ProjectUtilization])
def project_utilization(db: Session = Depends(get_db)):
    projects = db.query(models.Project).all()
    result = []
    for p in projects:
        employee_count = db.query(models.Employee).filter(models.Employee.project_id == p.id).count()
        seats_occupied = (
            db.query(models.SeatAllocation)
            .filter(
                models.SeatAllocation.project_id == p.id,
                models.SeatAllocation.allocation_status == models.AllocationStatus.active,
            )
            .count()
        )
        result.append(
            schemas.ProjectUtilization(
                project_id=p.id, project_name=p.name,
                employee_count=employee_count, seats_occupied=seats_occupied,
            )
        )
    return result


@router.get("/floor-utilization", response_model=List[schemas.FloorUtilization])
def floor_utilization(db: Session = Depends(get_db)):
    floors = [row[0] for row in db.query(models.Seat.floor).distinct().order_by(models.Seat.floor).all()]
    result = []
    for floor in floors:
        base_q = db.query(models.Seat).filter(models.Seat.floor == floor)
        total = base_q.count()
        occupied = base_q.filter(models.Seat.status == models.SeatStatus.occupied).count()
        available = base_q.filter(models.Seat.status == models.SeatStatus.available).count()
        reserved = base_q.filter(models.Seat.status == models.SeatStatus.reserved).count()
        maintenance = base_q.filter(models.Seat.status == models.SeatStatus.maintenance).count()
        result.append(
            schemas.FloorUtilization(
                floor=floor, total_seats=total, occupied=occupied,
                available=available, reserved=reserved, maintenance=maintenance,
            )
        )
    return result
