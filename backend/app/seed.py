"""
Generates seed data matching the assessment's minimums:
  - 5,000 employees
  - 5 floors, 10 zones per floor, >=5,500 seats total
  - 10+ projects
  - >=500 available seats, >=100 reserved seats, >=50 pending employees

Run with:  python -m app.seed
"""
import os
import random

from faker import Faker

from .database import SessionLocal, Base, engine, DATABASE_URL
from . import models

fake = Faker()
random.seed(42)
Faker.seed(42)

PROJECT_NAMES = [
    "Indigo", "Indreed", "Mydreed", "Preed", "Serfy",
    "Oreed", "bedegreed", "Opreed", "Serry", "Kaary", "Mered",
]

DEPARTMENTS = ["Engineering", "HR", "Finance", "Operations", "Sales", "Product", "Design", "QA"]
ROLES = ["Associate", "Senior Associate", "Team Lead", "Manager", "Analyst", "Engineer", "Consultant"]

FLOORS = [1, 2, 3, 4, 5]
ZONES_PER_FLOOR = [f"Z{i}" for i in range(1, 11)]
SEATS_PER_ZONE = 112

TOTAL_EMPLOYEES = 5000
MIN_AVAILABLE_SEATS = 500
MIN_RESERVED_SEATS = 100
MIN_PENDING_EMPLOYEES = 60


def reset_db():
    if not DATABASE_URL.startswith("sqlite") and os.getenv("CONFIRM_SEED_RESET") != "yes":
        raise RuntimeError(
            "Refusing to reset a non-SQLite database without confirmation. "
            "Set CONFIRM_SEED_RESET=yes and run again if you're sure. "
            "Make sure `alembic upgrade head` has already been run against it first."
        )
    print("Step 1: connecting + resetting existing data...", flush=True)
    db = SessionLocal()
    db.expire_on_commit = False
    try:
        db.query(models.SeatAllocation).delete()
        db.query(models.Employee).delete()
        db.query(models.Seat).delete()
        db.query(models.Project).delete()
        db.commit()
    finally:
        db.close()
    print("Step 1 done.", flush=True)


def seed():
    reset_db()
    db = SessionLocal()
    db.expire_on_commit = False
    try:
        print("Step 2: inserting projects...", flush=True)
        projects = []
        for name in PROJECT_NAMES:
            p = models.Project(
                name=name,
                description=f"{name} project",
                manager_name=fake.name(),
                status=models.ProjectStatus.active,
            )
            db.add(p)
            projects.append(p)
        db.commit()
        for p in projects:
            db.refresh(p)
        print("Step 2 done.", flush=True)

        print("Step 3: building + inserting seats...", flush=True)
        seats = []
        for floor in FLOORS:
            for zone in ZONES_PER_FLOOR:
                for i in range(1, SEATS_PER_ZONE + 1):
                    bay = f"B{((i - 1) // 10) + 1}"
                    seat_number = f"{zone}-{floor}{str(i).zfill(3)}"
                    seats.append(
                        models.Seat(floor=floor, zone=zone, bay=bay, seat_number=seat_number)
                    )
        db.bulk_save_objects(seats, return_defaults=False)
        db.commit()
        print("Step 3 done.", flush=True)

        print("Step 4: fetching seat ids...", flush=True)
        seat_ids = [row[0] for row in db.query(models.Seat.id).order_by(models.Seat.id).all()]
        for local_seat, db_id in zip(seats, seat_ids):
            local_seat.id = db_id
        print("Step 4 done.", flush=True)

        total_seats = len(seats)

        print("Step 5: building + inserting employees...", flush=True)
        num_pending = MIN_PENDING_EMPLOYEES
        num_active = TOTAL_EMPLOYEES - num_pending

        employees = []
        employee_project_ids = []
        for i in range(1, TOTAL_EMPLOYEES + 1):
            name = fake.name()
            email = f"{name.lower().replace(' ', '.').replace(chr(39), '')}{i}@ethara.ai"
            is_pending = i <= num_pending
            project_id = None if is_pending else random.choice(projects).id
            emp = models.Employee(
                employee_code=f"ETH{str(i).zfill(5)}",
                name=name,
                email=email,
                department=random.choice(DEPARTMENTS),
                role=random.choice(ROLES),
                joining_date=fake.date_between(start_date="-3y", end_date="today"),
                status=models.EmployeeStatus.pending if is_pending else models.EmployeeStatus.active,
                project_id=project_id,
            )
            employees.append(emp)
            employee_project_ids.append(project_id)
        db.bulk_save_objects(employees, return_defaults=False)
        db.commit()
        print("Step 5 done.", flush=True)

        print("Step 6: fetching employee ids...", flush=True)
        emp_ids = [row[0] for row in db.query(models.Employee.id).order_by(models.Employee.id).all()]
        for local_emp, db_id, proj_id in zip(employees, emp_ids, employee_project_ids):
            local_emp.id = db_id
            local_emp.project_id = proj_id
            local_emp.status = (
                models.EmployeeStatus.pending if proj_id is None else models.EmployeeStatus.active
            )
        print("Step 6 done.", flush=True)

        active_employees = [e for e in employees if e.status == models.EmployeeStatus.active]

        random.shuffle(seats)
        num_occupied = len(active_employees)
        remaining_after_occupied = total_seats - num_occupied
        num_reserved = max(MIN_RESERVED_SEATS, 0)
        num_available = remaining_after_occupied - num_reserved
        if num_available < MIN_AVAILABLE_SEATS:
            raise RuntimeError("Seed parameters don't leave enough seats available - adjust SEATS_PER_ZONE")

        occupied_seats = seats[:num_occupied]
        reserved_seats = seats[num_occupied:num_occupied + num_reserved]
        available_seats = seats[num_occupied + num_reserved:]

        for s in occupied_seats:
            s.status = models.SeatStatus.occupied
        for s in reserved_seats:
            s.status = models.SeatStatus.reserved
        for s in available_seats:
            s.status = models.SeatStatus.available

        print("Step 7: updating seat statuses...", flush=True)
        occupied_ids = [s.id for s in occupied_seats]
        reserved_ids = [s.id for s in reserved_seats]
        available_ids = [s.id for s in available_seats]

        # Three single UPDATE...WHERE id IN (...) statements instead of one
        # UPDATE per row - bulk_update_mappings() was issuing ~5,600
        # individual round trips here, which is what was actually "stuck".
        db.query(models.Seat).filter(models.Seat.id.in_(occupied_ids)).update(
            {models.Seat.status: models.SeatStatus.occupied}, synchronize_session=False
        )
        db.query(models.Seat).filter(models.Seat.id.in_(reserved_ids)).update(
            {models.Seat.status: models.SeatStatus.reserved}, synchronize_session=False
        )
        db.query(models.Seat).filter(models.Seat.id.in_(available_ids)).update(
            {models.Seat.status: models.SeatStatus.available}, synchronize_session=False
        )
        db.commit()
        print("Step 7 done.", flush=True)

        print("Step 8: inserting seat allocations...", flush=True)
        allocations = [
            models.SeatAllocation(
                employee_id=emp.id,
                seat_id=seat.id,
                project_id=emp.project_id,
                allocation_status=models.AllocationStatus.active,
            )
            for emp, seat in zip(active_employees, occupied_seats)
        ]
        db.bulk_save_objects(allocations)
        db.commit()
        print("Step 8 done.", flush=True)

        print(f"Seeded: {len(projects)} projects, {total_seats} seats, {len(employees)} employees, "
              f"{len(allocations)} active allocations.")
        print(f"Seats -> available: {len(available_seats)}, reserved: {len(reserved_seats)}, "
              f"occupied: {len(occupied_seats)}")
        print(f"Employees -> pending: {num_pending}, active: {num_active}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()