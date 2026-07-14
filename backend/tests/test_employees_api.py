"""
API-level tests (via FastAPI's TestClient) for the endpoints touched by the
release-seat bug fix:

  1. DELETE /employees/{id} now releases any active seat allocation before
     marking the employee inactive, instead of leaving the seat stuck as
     'occupied' forever with no matching active allocation.
  2. POST /seats/release now returns the released seat's details (floor,
     zone, seat_number, status) in the response body, matching what
     POST /seats/allocate already returns.

Run with:  pytest -v  (from the backend/ directory)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def seeded(client):
    project = client.post("/projects", json={"name": "Talos"}).json()
    emp = client.post(
        "/employees",
        json={"employee_code": "E1", "name": "Amit", "email": "amit@ethara.ai", "project_id": project["id"]},
    ).json()
    seat = client.post("/seats", json={"floor": 2, "zone": "B", "bay": "4", "seat_number": "B4-23"}).json()
    return {"project": project, "emp": emp, "seat": seat}


def test_release_response_includes_seat_details(client, seeded):
    client.post("/seats/allocate", json={"employee_id": seeded["emp"]["id"], "project_id": seeded["project"]["id"]})

    resp = client.post("/seats/release", json={"employee_id": seeded["emp"]["id"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["allocation_status"] == "released"
    assert body["seat"] is not None
    assert body["seat"]["seat_number"] == seeded["seat"]["seat_number"]
    assert body["seat"]["status"] == "available"


def test_deactivating_employee_releases_their_seat(client, seeded):
    client.post("/seats/allocate", json={"employee_id": seeded["emp"]["id"], "project_id": seeded["project"]["id"]})

    resp = client.delete(f"/employees/{seeded['emp']['id']}")
    assert resp.status_code == 200
    assert "released" in resp.json()["detail"]

    seat_resp = client.get("/seats", params={"floor": 2, "zone": "B"}).json()
    seat = next(s for s in seat_resp if s["seat_number"] == seeded["seat"]["seat_number"])
    assert seat["status"] == "available"
    assert seat["occupied_by"] is None

    emp_resp = client.get(f"/employees/{seeded['emp']['id']}").json()
    assert emp_resp["status"] == "inactive"
    assert emp_resp["current_seat"] is None


def test_deactivating_unseated_employee_still_succeeds(client, seeded):
    # emp2 was never allocated a seat -- deactivation must not error out.
    emp2 = client.post(
        "/employees",
        json={"employee_code": "E2", "name": "Riya", "email": "riya@ethara.ai"},
    ).json()
    resp = client.delete(f"/employees/{emp2['id']}")
    assert resp.status_code == 200
    assert "released" not in resp.json()["detail"]
