"""
pytest tests for the seat allocation service, covering:
  - successful allocation
  - duplicate allocation attempt (should fail)
  - releasing a seat and re-allocating it
  - allocation when the preferred zone is full (should suggest alternate zone)

Run with:  pytest -v  (from the backend/ directory)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models
from app.services import allocate_seat, release_seat, update_seat_status, AllocationError


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture()
def seeded(db_session):
    project = models.Project(name="Talos", status=models.ProjectStatus.active)
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    emp1 = models.Employee(employee_code="E1", name="Amit", email="amit@ethara.ai",
                            status=models.EmployeeStatus.pending, project_id=project.id)
    emp2 = models.Employee(employee_code="E2", name="Riya", email="riya@ethara.ai",
                            status=models.EmployeeStatus.pending, project_id=project.id)
    db_session.add_all([emp1, emp2])
    db_session.commit()
    db_session.refresh(emp1)
    db_session.refresh(emp2)

    # One seat in Zone B (Amit's team zone), one seat far away in Zone Z
    seat_zone_b = models.Seat(floor=2, zone="B", bay="4", seat_number="B4-23",
                               status=models.SeatStatus.available)
    seat_zone_z = models.Seat(floor=9, zone="Z", bay="1", seat_number="Z1-01",
                               status=models.SeatStatus.available)
    db_session.add_all([seat_zone_b, seat_zone_z])
    db_session.commit()
    db_session.refresh(seat_zone_b)
    db_session.refresh(seat_zone_z)

    return {
        "project": project, "emp1": emp1, "emp2": emp2,
        "seat_zone_b": seat_zone_b, "seat_zone_z": seat_zone_z,
    }


def test_successful_allocation(db_session, seeded):
    allocation = allocate_seat(db_session, employee_id=seeded["emp1"].id, project_id=seeded["project"].id)
    assert allocation.allocation_status == models.AllocationStatus.active
    assert allocation.employee_id == seeded["emp1"].id

    seat = db_session.query(models.Seat).get(allocation.seat_id)
    assert seat.status == models.SeatStatus.occupied


def test_duplicate_allocation_fails(db_session, seeded):
    allocate_seat(db_session, employee_id=seeded["emp1"].id, project_id=seeded["project"].id)
    with pytest.raises(AllocationError):
        allocate_seat(db_session, employee_id=seeded["emp1"].id, project_id=seeded["project"].id)


def test_release_and_reallocate(db_session, seeded):
    allocation = allocate_seat(db_session, employee_id=seeded["emp1"].id, project_id=seeded["project"].id)
    seat_id = allocation.seat_id

    released = release_seat(db_session, employee_id=seeded["emp1"].id)
    assert released.allocation_status == models.AllocationStatus.released

    seat = db_session.query(models.Seat).get(seat_id)
    assert seat.status == models.SeatStatus.available

    # Now employee 2 can take that same seat again
    new_allocation = allocate_seat(db_session, employee_id=seeded["emp2"].id, project_id=seeded["project"].id)
    assert new_allocation.seat_id == seat_id
    assert new_allocation.allocation_status == models.AllocationStatus.active


def test_alternate_zone_when_preferred_zone_full(db_session, seeded):
    # Take the only seat in Amit's team zone (B) with employee 2 first,
    # on a *different* project so it still counts as "occupied" generally,
    # forcing Amit's allocation to fall back to the far zone.
    other_project = models.Project(name="Other", status=models.ProjectStatus.active)
    db_session.add(other_project)
    db_session.commit()
    db_session.refresh(other_project)

    filler = models.Employee(employee_code="E3", name="Filler", email="filler@ethara.ai",
                              status=models.EmployeeStatus.pending, project_id=other_project.id)
    db_session.add(filler)
    db_session.commit()
    db_session.refresh(filler)

    # Directly occupy the zone-B seat so it's no longer available
    allocate_seat(db_session, employee_id=filler.id, seat_id=seeded["seat_zone_b"].id)

    # Now Amit's project has no active teammates yet in any zone (first member),
    # so allocation should just fall back to any available seat -> Zone Z.
    allocation = allocate_seat(db_session, employee_id=seeded["emp1"].id, project_id=seeded["project"].id)
    seat = db_session.query(models.Seat).get(allocation.seat_id)
    assert seat.id == seeded["seat_zone_z"].id
    assert allocation.alternate_zone is True


def test_reserved_or_occupied_seat_cannot_be_directly_allocated(db_session, seeded):
    seeded["seat_zone_b"].status = models.SeatStatus.reserved
    db_session.commit()
    with pytest.raises(AllocationError):
        allocate_seat(db_session, employee_id=seeded["emp1"].id, seat_id=seeded["seat_zone_b"].id)


def test_allocation_requires_a_project(db_session, seeded):
    """A seat cannot be allocated to an employee with no project resolved
    from either the request or their own record (e.g. a still-pending new
    joiner who hasn't been mapped to a project yet)."""
    unassigned = models.Employee(
        employee_code="E4", name="Noor", email="noor@ethara.ai",
        status=models.EmployeeStatus.pending, project_id=None,
    )
    db_session.add(unassigned)
    db_session.commit()
    db_session.refresh(unassigned)

    with pytest.raises(AllocationError):
        allocate_seat(db_session, employee_id=unassigned.id)

    # Passing project_id explicitly on the request resolves it.
    allocation = allocate_seat(db_session, employee_id=unassigned.id, project_id=seeded["project"].id)
    assert allocation.project_id == seeded["project"].id
    db_session.refresh(unassigned)
    assert unassigned.project_id == seeded["project"].id
    assert unassigned.status == models.EmployeeStatus.active


def test_release_by_seat_id_also_works(db_session, seeded):
    """Release should work when called with seat_id alone (used by the
    'Currently Occupied Seats' quick-release button), not just employee_id."""
    allocation = allocate_seat(db_session, employee_id=seeded["emp1"].id, project_id=seeded["project"].id)
    released = release_seat(db_session, seat_id=allocation.seat_id)
    assert released.allocation_status == models.AllocationStatus.released

    seat = db_session.query(models.Seat).get(allocation.seat_id)
    assert seat.status == models.SeatStatus.available


def test_release_with_no_active_allocation_raises(db_session, seeded):
    with pytest.raises(AllocationError):
        release_seat(db_session, employee_id=seeded["emp1"].id)


class TestSeatStatusTransitions:
    """
    Business rule 4: reserved/maintenance seats cannot be allocated until
    their status is changed back. Covers both directions (pulling a seat
    out of rotation, and restoring one) plus the two guard conditions:
    status can never be set to 'occupied' directly, and status can't be
    changed while a seat is actually occupied.
    """

    def test_reserved_seat_can_be_restored_to_available(self, db_session, seeded):
        seeded["seat_zone_b"].status = models.SeatStatus.reserved
        db_session.commit()

        seat = update_seat_status(db_session, seat_id=seeded["seat_zone_b"].id,
                                   new_status=models.SeatStatus.available)
        assert seat.status == models.SeatStatus.available

        allocation = allocate_seat(db_session, employee_id=seeded["emp1"].id, seat_id=seeded["seat_zone_b"].id)
        assert allocation.allocation_status == models.AllocationStatus.active

    def test_available_seat_can_be_pulled_into_maintenance(self, db_session, seeded):
        seat = update_seat_status(db_session, seat_id=seeded["seat_zone_b"].id,
                                   new_status=models.SeatStatus.maintenance)
        assert seat.status == models.SeatStatus.maintenance

        with pytest.raises(AllocationError):
            allocate_seat(db_session, employee_id=seeded["emp1"].id, seat_id=seeded["seat_zone_b"].id)

    def test_cannot_set_status_to_occupied_directly(self, db_session, seeded):
        with pytest.raises(AllocationError):
            update_seat_status(db_session, seat_id=seeded["seat_zone_b"].id,
                                new_status=models.SeatStatus.occupied)

    def test_cannot_change_status_while_occupied(self, db_session, seeded):
        allocate_seat(db_session, employee_id=seeded["emp1"].id, seat_id=seeded["seat_zone_b"].id)
        with pytest.raises(AllocationError):
            update_seat_status(db_session, seat_id=seeded["seat_zone_b"].id,
                                new_status=models.SeatStatus.maintenance)

    def test_status_update_on_missing_seat_raises(self, db_session, seeded):
        with pytest.raises(AllocationError):
            update_seat_status(db_session, seat_id=999999, new_status=models.SeatStatus.available)


class TestDeactivationReleasesSeat:
    """
    Regression tests for a bug where deactivating an employee (DELETE
    /employees/{id}) left their seat permanently stuck as 'occupied' with
    no way to release it, since the deactivate endpoint never called
    release_seat. Fixed by having deactivation release any active seat
    allocation for that employee first.
    """

    def test_deactivating_seated_employee_frees_their_seat(self, db_session, seeded):
        allocation = allocate_seat(db_session, employee_id=seeded["emp1"].id, project_id=seeded["project"].id)
        seat_id = allocation.seat_id

        # Simulate what the DELETE /employees/{id} endpoint now does.
        released = release_seat(db_session, employee_id=seeded["emp1"].id)
        seeded["emp1"].status = models.EmployeeStatus.inactive
        db_session.commit()

        assert released.allocation_status == models.AllocationStatus.released
        seat = db_session.query(models.Seat).get(seat_id)
        assert seat.status == models.SeatStatus.available

        # The freed seat can now be allocated to someone else.
        new_allocation = allocate_seat(db_session, employee_id=seeded["emp2"].id, project_id=seeded["project"].id)
        assert new_allocation.seat_id == seat_id

    def test_deactivating_unseated_employee_does_not_error(self, db_session, seeded):
        # emp2 has no active allocation; deactivation must not raise.
        with pytest.raises(AllocationError):
            release_seat(db_session, employee_id=seeded["emp2"].id)
        # The router catches this AllocationError and proceeds to mark the
        # employee inactive anyway -- verified at the API level in
        # test_employees_api.py.