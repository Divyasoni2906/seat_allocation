"""
Core seat allocation business logic, kept separate from route handlers so it
can be unit tested directly and reused by both the REST API and the AI
assistant layer.

Business rules enforced here (per the assessment brief):
  1. One employee can have only one ACTIVE seat allocation at a time.
  2. One seat can have only one ACTIVE allocation at a time.
  3. Released seats become available again.
  4. Reserved / maintenance seats cannot be allocated directly.
  5. New joiners are prioritized for seats near their project team
     (same floor+zone as other active members of the same project);
     if none is free, fall back to any available seat and flag it.
  6. Duplicate employee email is rejected at the DB layer (unique constraint).
  7. Duplicate seat number on the same floor/zone is rejected at the DB layer.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import and_

from . import models


class AllocationError(Exception):
    """Raised for business-rule violations in seat allocation."""


def get_active_allocation_for_employee(db: Session, employee_id: int) -> Optional[models.SeatAllocation]:
    return (
        db.query(models.SeatAllocation)
        .filter(
            models.SeatAllocation.employee_id == employee_id,
            models.SeatAllocation.allocation_status == models.AllocationStatus.active,
        )
        .first()
    )


def get_active_allocation_for_seat(db: Session, seat_id: int) -> Optional[models.SeatAllocation]:
    return (
        db.query(models.SeatAllocation)
        .filter(
            models.SeatAllocation.seat_id == seat_id,
            models.SeatAllocation.allocation_status == models.AllocationStatus.active,
        )
        .first()
    )


def find_seat_near_project(db: Session, project_id: Optional[int]):
    """
    Look for an available seat on the same floor+zone as other active
    members of the same project. Returns (seat, is_alternate_zone).
    """
    if project_id is not None:
        teammate_seat_ids = (
            db.query(models.SeatAllocation.seat_id)
            .filter(
                models.SeatAllocation.project_id == project_id,
                models.SeatAllocation.allocation_status == models.AllocationStatus.active,
            )
            .subquery()
        )
        teammate_seats = (
            db.query(models.Seat)
            .filter(models.Seat.id.in_(teammate_seat_ids))
            .all()
        )
        zones_used = {(s.floor, s.zone) for s in teammate_seats}

        for floor, zone in zones_used:
            candidate = (
                db.query(models.Seat)
                .filter(
                    models.Seat.floor == floor,
                    models.Seat.zone == zone,
                    models.Seat.status == models.SeatStatus.available,
                )
                .order_by(models.Seat.seat_number)
                .first()
            )
            if candidate:
                return candidate, False

    # Fall back: any available seat, anywhere.
    fallback = (
        db.query(models.Seat)
        .filter(models.Seat.status == models.SeatStatus.available)
        .order_by(models.Seat.floor, models.Seat.zone, models.Seat.seat_number)
        .first()
    )
    if fallback:
        return fallback, True

    return None, False


def allocate_seat(
    db: Session,
    employee_id: int,
    project_id: Optional[int] = None,
    seat_id: Optional[int] = None,
) -> models.SeatAllocation:
    employee = db.query(models.Employee).get(employee_id)
    if not employee:
        raise AllocationError(f"Employee {employee_id} not found")

    # Rule 1: one active allocation per employee
    existing = get_active_allocation_for_employee(db, employee_id)
    if existing:
        raise AllocationError(
            f"Employee {employee.name} already has an active seat allocation (seat_id={existing.seat_id})"
        )

    effective_project_id = project_id if project_id is not None else employee.project_id
    alternate_zone = False

    # Rule: every employee must be mapped to a project before they get a seat.
    # Without this, seats were being handed to pending/unassigned employees
    # with no project link at all, which breaks project-wise utilization
    # and the "one employee -> one active project" rule from the brief.
    if effective_project_id is None:
        raise AllocationError(
            f"Employee {employee.name} has no project assigned yet — "
            "assign a project before allocating a seat"
        )

    if seat_id is not None:
        # Specific seat requested
        seat = db.query(models.Seat).get(seat_id)
        if not seat:
            raise AllocationError(f"Seat {seat_id} not found")
        if seat.status != models.SeatStatus.available:
            raise AllocationError(f"Seat {seat.seat_number} is not available (status={seat.status})")
    else:
        seat, alternate_zone = find_seat_near_project(db, effective_project_id)
        if not seat:
            raise AllocationError("No available seats at this time")

    # Rule 2: one active allocation per seat (re-check right before commit)
    if get_active_allocation_for_seat(db, seat.id):
        raise AllocationError(f"Seat {seat.seat_number} was just taken by someone else, please retry")

    allocation = models.SeatAllocation(
        employee_id=employee_id,
        seat_id=seat.id,
        project_id=effective_project_id,
        allocation_status=models.AllocationStatus.active,
        allocation_date=datetime.utcnow(),
        alternate_zone=alternate_zone,
    )
    seat.status = models.SeatStatus.occupied
    employee.status = models.EmployeeStatus.active
    if effective_project_id is not None:
        employee.project_id = effective_project_id

    db.add(allocation)
    db.commit()
    db.refresh(allocation)
    return allocation

def update_seat_status(
    db: Session,
    seat_id: int,
    new_status: models.SeatStatus,
) -> models.Seat:
    """
    Change a seat's status directly (e.g. Reserved -> Available, Available ->
    Maintenance). This is how Reserved/Maintenance seats become allocatable
    again (business rule 4) -- without this, they'd be stuck in that state
    forever since nothing else in the system ever flips a seat's status back.
    """
    seat = db.query(models.Seat).get(seat_id)
    if not seat:
        raise AllocationError(f"Seat {seat_id} not found")

    if new_status == models.SeatStatus.occupied:
        raise AllocationError("Cannot set status to 'occupied' directly -- use allocate_seat() instead")

    if seat.status == models.SeatStatus.occupied:
        raise AllocationError(
            f"Seat {seat.seat_number} is currently occupied -- release it before changing its status"
        )

    seat.status = new_status
    db.commit()
    db.refresh(seat)
    return seat

def release_seat(
    db: Session,
    employee_id: Optional[int] = None,
    seat_id: Optional[int] = None,
) -> models.SeatAllocation:
    if employee_id is None and seat_id is None:
        raise AllocationError("Provide employee_id or seat_id to release a seat")

    query = db.query(models.SeatAllocation).filter(
        models.SeatAllocation.allocation_status == models.AllocationStatus.active
    )
    if employee_id is not None:
        query = query.filter(models.SeatAllocation.employee_id == employee_id)
    if seat_id is not None:
        query = query.filter(models.SeatAllocation.seat_id == seat_id)

    allocation = query.first()
    if not allocation:
        raise AllocationError("No active allocation found to release (it may already be released)")

    allocation.allocation_status = models.AllocationStatus.released
    allocation.released_date = datetime.utcnow()

    seat = db.query(models.Seat).get(allocation.seat_id)
    if seat:
        seat.status = models.SeatStatus.available

    db.commit()
    db.refresh(allocation)
    return allocation