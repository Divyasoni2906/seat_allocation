"""
Tests for the rule-based AI assistant (app/ai_assistant.py).

Covers two fixes:
  1. Case sensitivity bug: _extract_name previously required the employee's
     name to start with a capital letter, so a lowercase query like
     "where is amit seated" failed to extract a name at all and the
     assistant reported the employee as not found even though they exist.
  2. New release_request intent: "release my seat" / "release seat for
     <name>" now actually releases the active allocation instead of only
     being understood as a plain seat lookup.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app import models
from app.ai_assistant import parse_intent, handle_query
from app.services import allocate_seat


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def seeded(db_session):
    project = models.Project(name="Talos")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    emp = models.Employee(
        employee_code="E1", name="Amit", email="amit@ethara.ai",
        status=models.EmployeeStatus.pending, project_id=project.id,
    )
    seat = models.Seat(floor=2, zone="B", bay="4", seat_number="B4-23")
    db_session.add_all([emp, seat])
    db_session.commit()
    db_session.refresh(emp)
    db_session.refresh(seat)
    return {"project": project, "emp": emp, "seat": seat}


def test_name_extraction_is_case_insensitive(db_session):
    parsed_lower = parse_intent("where is amit seated?", db_session)
    parsed_upper = parse_intent("Where is Amit seated?", db_session)
    assert parsed_lower["entities"]["name"] == "amit"
    assert parsed_upper["entities"]["name"] == "Amit"


def test_seat_lookup_resolves_regardless_of_query_case(db_session, seeded):
    allocate_seat(db_session, employee_id=seeded["emp"].id, project_id=seeded["project"].id)

    lower_result = handle_query(db_session, "where is employee amit seated?")
    upper_result = handle_query(db_session, "Where is employee Amit seated?")

    assert "B4-23" in lower_result["answer"]
    assert "B4-23" in upper_result["answer"]
    assert lower_result["intent"] == "seat_lookup"


def test_release_request_releases_the_seat(db_session, seeded):
    allocate_seat(db_session, employee_id=seeded["emp"].id, project_id=seeded["project"].id)

    result = handle_query(db_session, "release seat for amit")
    assert result["intent"] == "release_request"
    assert "released" in result["answer"].lower()

    seat = db_session.query(models.Seat).get(seeded["seat"].id)
    assert seat.status == models.SeatStatus.available


def test_release_request_extracts_two_word_names():
    """Regression test for a bug where 'Release seat for jamie anderson'
    extracted no name at all, since _extract_name only recognized
    'employee X' / 'X seated' phrasing, not the 'release ... for X'
    phrasing release requests actually use."""
    from app.ai_assistant import _extract_name

    assert _extract_name("Release seat for jamie anderson") == "jamie anderson"
    assert _extract_name("release seat for Amit") == "Amit"
    assert _extract_name("free jamie anderson's seat") == "jamie anderson"


def test_release_request_resolves_two_word_names_end_to_end(db_session, seeded):
    jamie = models.Employee(
        employee_code="E2", name="Jamie Anderson", email="jamie@ethara.ai",
        status=models.EmployeeStatus.pending, project_id=seeded["project"].id,
    )
    seat2 = models.Seat(floor=3, zone="C", bay="1", seat_number="C1-01")
    db_session.add_all([jamie, seat2])
    db_session.commit()
    db_session.refresh(jamie)
    allocation = allocate_seat(db_session, employee_id=jamie.id, project_id=seeded["project"].id)
    allocated_seat_id = allocation.seat_id

    result = handle_query(db_session, "Release seat for jamie anderson")
    assert result["intent"] == "release_request"
    assert "released" in result["answer"].lower()

    freed_seat = db_session.query(models.Seat).get(allocated_seat_id)
    assert freed_seat.status == models.SeatStatus.available


def test_release_request_with_no_active_seat_is_reported_gracefully(db_session, seeded):
    result = handle_query(db_session, "release seat for amit")
    assert result["intent"] == "release_request"
    assert "doesn't have an active seat" in result["answer"]


def test_release_request_without_identifying_info_asks_for_it(db_session):
    result = handle_query(db_session, "release my seat")
    assert result["intent"] == "release_request"
    assert "email" in result["answer"].lower() or "name" in result["answer"].lower()

def test_team_location_uses_physical_seat_proximity(db_session, seeded):
    """
    "Who is sitting near me?" should mean physical proximity (same
    floor+zone as the asker's active seat), not "who's on my project" --
    two employees on different projects but the same zone should show up
    as neighbors, and a same-project teammate seated elsewhere should not.
    """
    allocation = allocate_seat(db_session, employee_id=seeded["emp"].id, seat_id=seeded["seat"].id)
    asker_floor, asker_zone = seeded["seat"].floor, seeded["seat"].zone

    other_project = models.Project(name="Other")
    db_session.add(other_project)
    db_session.commit()
    db_session.refresh(other_project)

    neighbor_seat = models.Seat(floor=asker_floor, zone=asker_zone, bay="4", seat_number="B4-24")
    neighbor = models.Employee(
        employee_code="E2", name="Neighbor Nearby", email="neighbor@ethara.ai",
        status=models.EmployeeStatus.pending, project_id=other_project.id,
    )
    far_seat = models.Seat(floor=9, zone="Z", bay="1", seat_number="Z1-01")
    far_teammate = models.Employee(
        employee_code="E3", name="Far Teammate", email="far@ethara.ai",
        status=models.EmployeeStatus.pending, project_id=seeded["project"].id,
    )
    db_session.add_all([neighbor_seat, neighbor, far_seat, far_teammate])
    db_session.commit()
    db_session.refresh(neighbor)
    db_session.refresh(far_teammate)

    allocate_seat(db_session, employee_id=neighbor.id, seat_id=neighbor_seat.id)
    allocate_seat(db_session, employee_id=far_teammate.id, seat_id=far_seat.id)

    result = handle_query(db_session, "Who is sitting near me? amit@ethara.ai")
    assert result["intent"] == "team_location"
    assert "Neighbor Nearby" in result["answer"]
    assert "Far Teammate" not in result["answer"]


def test_team_location_with_no_active_seat_is_reported_gracefully(db_session, seeded):
    result = handle_query(db_session, "Who is sitting near me? amit@ethara.ai")
    assert result["intent"] == "team_location"
    assert "doesn't have an active seat" in result["answer"]


def test_team_location_unresolvable_employee_asks_for_identifying_info(db_session):
    result = handle_query(db_session, "Who is sitting near me? nobody@ethara.ai")
    assert result["intent"] == "team_location"
    assert "couldn't find" in result["answer"].lower()