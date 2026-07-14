"""
Generates seed data matching the assessment's minimums:
  - 5,000 employees
  - 5 floors, 10 zones per floor, >=5,500 seats total
  - 10+ projects
  - >=500 available seats, >=100 reserved seats, >=50 pending employees

Run with:  python -m app.seed
"""
import random

from faker import Faker

from .database import SessionLocal, Base, engine
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
ZONES_PER_FLOOR = [f"Z{i}" for i in range(1, 11)]  # 10 zones per floor
SEATS_PER_ZONE = 112  # 5 floors * 10 zones * 112 = 5,600 seats total (clears the 5,500 minimum)

TOTAL_EMPLOYEES = 5000
MIN_AVAILABLE_SEATS = 500
MIN_RESERVED_SEATS = 100
MIN_PENDING_EMPLOYEES = 60


def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def seed():
    reset_db()
    db = SessionLocal()
    try:
        # --- Projects ---
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

        # --- Seats ---
        seats = []
        for floor in FLOORS:
            for zone in ZONES_PER_FLOOR:
                for i in range(1, SEATS_PER_ZONE + 1):
                    bay = f"B{((i - 1) // 10) + 1}"
                    seat_number = f"{zone}-{floor}{str(i).zfill(3)}"
                    seats.append(
                        models.Seat(floor=floor, zone=zone, bay=bay, seat_number=seat_number)
                    )
        db.add_all(seats)
        db.commit()
        for s in seats:
            db.refresh(s)

        total_seats = len(seats)

        # --- Employees (decide pending vs active first, so seat counts can match exactly) ---
        num_pending = MIN_PENDING_EMPLOYEES
        num_active = TOTAL_EMPLOYEES - num_pending

        employees = []
        for i in range(1, TOTAL_EMPLOYEES + 1):
            name = fake.name()
            email = f"{name.lower().replace(' ', '.').replace(chr(39), '')}{i}@ethara.ai"
            is_pending = i <= num_pending
            emp = models.Employee(
                employee_code=f"ETH{str(i).zfill(5)}",
                name=name,
                email=email,
                department=random.choice(DEPARTMENTS),
                role=random.choice(ROLES),
                joining_date=fake.date_between(start_date="-3y", end_date="today"),
                status=models.EmployeeStatus.pending if is_pending else models.EmployeeStatus.active,
                project_id=None if is_pending else random.choice(projects).id,
            )
            employees.append(emp)
        db.add_all(employees)
        db.commit()
        for e in employees:
            db.refresh(e)

        active_employees = [e for e in employees if e.status == models.EmployeeStatus.active]

        # --- Assign seat statuses so counts line up exactly with allocations ---
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
        db.commit()

        # --- Seat allocations: one per active employee, matched 1:1 with occupied seats ---
        allocations = []
        for emp, seat in zip(active_employees, occupied_seats):
            allocations.append(
                models.SeatAllocation(
                    employee_id=emp.id,
                    seat_id=seat.id,
                    project_id=emp.project_id,
                    allocation_status=models.AllocationStatus.active,
                )
            )
        db.add_all(allocations)
        db.commit()

        print(f"Seeded: {len(projects)} projects, {total_seats} seats, {len(employees)} employees, "
              f"{len(allocations)} active allocations.")
        print(f"Seats -> available: {len(available_seats)}, reserved: {len(reserved_seats)}, "
              f"occupied: {len(occupied_seats)}")
        print(f"Employees -> pending: {num_pending}, active: {num_active}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
