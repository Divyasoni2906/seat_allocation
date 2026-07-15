"""
Rule-based natural-language query assistant for the seat/project system.

Design choice: a deterministic keyword + regex intent parser, not an LLM
call, because:
  - the query space is small and fully known in advance (5 intent types
    given directly in the brief)
  - answers must be deterministic and always match real DB state
  - zero API cost/latency/key management, and it works offline in a demo

Each intent maps to one of the plain functions in services.py / direct
queries below, so the "advanced" LLM-fallback tier (if ever added) would
only need to normalize free-form phrasing into one of these same intents
and call the same functions -- it would not change any of this logic.
"""
import re
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from . import models
from .services import release_seat, AllocationError

INTENTS = [
    "seat_lookup",
    "seat_occupant_lookup",
    "project_lookup",
    "project_location",
    "availability_check",
    "utilization_check",
    "team_location",
    "allocate_request",
    "release_request",
    "unknown",
]


def _extract_email(text: str) -> Optional[str]:
    match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
    return match.group(0) if match else None


def _extract_floor(text: str) -> Optional[int]:
    match = re.search(r"floor\s*(\d+)", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _extract_zone(text: str) -> Optional[str]:
    match = re.search(r"zone\s*([a-zA-Z0-9]+)", text, re.IGNORECASE)
    return match.group(1).upper() if match else None


def _extract_project(text: str, db: Session) -> Optional[str]:
    projects = db.query(models.Project).all()
    text_lower = text.lower()
    for p in projects:
        if p.name.lower() in text_lower:
            return p.name
    match = re.search(r"project\s+([a-zA-Z]+)", text, re.IGNORECASE)
    return match.group(1) if match else None


def _extract_name(text: str) -> Optional[str]:
    # "Where is employee Amit seated?" / "where is amit sitting?" -- matched
    # case-insensitively so lowercase input (very common when typing into a
    # chat box) still resolves to the right employee.
    match = re.search(
        r"(?:employee|is|for)\s+([A-Za-z]+(?:\s[A-Za-z]+)?)\s+(?:seated|sitting|assigned)",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)
    match = re.search(r"employee\s+([A-Za-z]+(?:\s[A-Za-z]+)?)", text, re.IGNORECASE)
    if match:
        return match.group(1)
    # "Release seat for jamie anderson" / "free jamie's seat" / "vacate the
    # seat for Amit" -- release-style phrasing has no "employee"/"seated"
    # anchor to hook onto, so it needs its own pattern.
    match = re.search(r"(?:release|free|vacate)\b.*?\bfor\s+([A-Za-z]+(?:\s[A-Za-z]+)?)", text, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"([A-Za-z]+(?:\s[A-Za-z]+)?)['’]s\s+seat", text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def _extract_seat_number(text: str) -> Optional[str]:
    # Requires a digit somewhere so it doesn't false-match "seat allocation"/
    # "seat status". Captured as one token first, then checked for a digit
    # in Python -- doing the digit check inline in the regex character class
    # boundary (e.g. [A-Za-z0-9]*\d) fails to extract seat numbers where a
    # dash appears before the first digit, like "ZZ-9999".
    match = re.search(r"seat\s+([A-Za-z0-9][A-Za-z0-9\-]*)", text, re.IGNORECASE)
    if match and any(ch.isdigit() for ch in match.group(1)):
        return match.group(1).upper()
    return None


def parse_intent(query: str, db: Session) -> dict:
    q = query.strip()
    q_lower = q.lower()

    entities = {
        "email": _extract_email(q),
        "name": _extract_name(q),
        "floor": _extract_floor(q),
        "zone": _extract_zone(q),
        "project": _extract_project(q, db),
        "seat_number": _extract_seat_number(q),
    }

    if any(k in q_lower for k in ["release my seat", "release seat", "free my seat", "vacate my seat", "release the seat"]):
        intent = "release_request"
    elif any(k in q_lower for k in ["allocate a seat", "allocate seat", "new employee joining", "assign a seat"]):
        intent = "allocate_request"
    elif any(k in q_lower for k in ["who is sitting near", "near me", "team location", "sitting close"]):
        intent = "team_location"
    elif any(k in q_lower for k in ["how many seats are occupied", "utilization", "occupancy", "how many seats"]):
        intent = "utilization_check"
    elif any(k in q_lower for k in ["available seat", "show all available", "which seats are free", "free seats"]):
        intent = "availability_check"
    elif any(k in q_lower for k in ["which project", "what project", "project am i", "project is"]):
        intent = "project_lookup"
    elif "project" in q_lower and any(
        k in q_lower for k in ["location", "located", "which floor", "which floors", "which zone", "seated across"]
    ):
        intent = "project_location"
    elif entities["seat_number"] and any(
        k in q_lower for k in ["who is seated", "who is sitting", "who sits", "who occupies", "who's in", "who is in"]
    ):
        # Reverse lookup: given a specific seat, who's in it -- checked before
        # the general seat_lookup branch below, since "who is seated on Floor
        # 3, Seat Z3-3003" also contains "seated" and would otherwise be
        # misrouted to seat_lookup, which then wrongly searches for an
        # employee named "Floor" and reports a confusing "not found".
        intent = "seat_occupant_lookup"
    elif any(k in q_lower for k in ["where is", "where am i", "my seat", "seated", "sitting"]):
        intent = "seat_lookup"
    else:
        intent = "unknown"

    return {"intent": intent, "entities": entities}


def _resolve_employee(db: Session, email: Optional[str], name: Optional[str]) -> Optional[models.Employee]:
    if email:
        emp = db.query(models.Employee).filter(models.Employee.email == email).first()
        if emp:
            return emp
    if name:
        emp = db.query(models.Employee).filter(models.Employee.name.ilike(f"%{name}%")).first()
        if emp:
            return emp
    return None


def _current_seat(db: Session, employee: models.Employee) -> Optional[models.Seat]:
    allocation = (
        db.query(models.SeatAllocation)
        .filter(
            models.SeatAllocation.employee_id == employee.id,
            models.SeatAllocation.allocation_status == models.AllocationStatus.active,
        )
        .first()
    )
    if not allocation:
        return None
    return db.query(models.Seat).get(allocation.seat_id)


def _current_seat_desc(db: Session, employee: models.Employee) -> Optional[str]:
    seat = _current_seat(db, employee)
    if not seat:
        return None
    return f"Floor {seat.floor}, Zone {seat.zone}, Bay {seat.bay}, Seat {seat.seat_number}"


def handle_query(db: Session, query: str) -> dict:
    parsed = parse_intent(query, db)
    intent = parsed["intent"]
    entities = parsed["entities"]

    if intent == "seat_lookup":
        employee = _resolve_employee(db, entities["email"], entities["name"])
        if not employee:
            return {"answer": "I couldn't find that employee. Could you share their name or email?", "intent": intent}
        seat_desc = _current_seat_desc(db, employee)
        if not seat_desc:
            return {"answer": f"{employee.name} doesn't have an active seat allocation yet.", "intent": intent}
        project_part = f" {'They are' if entities['name'] else 'You are'} assigned to Project {employee.project.name}." if employee.project else ""
        subject = employee.name if entities["name"] else "You"
        verb = "is" if entities["name"] else "are"
        return {"answer": f"{subject} {verb} seated on {seat_desc}.{project_part}", "intent": intent}

    if intent == "project_lookup":
        employee = _resolve_employee(db, entities["email"], entities["name"])
        if not employee:
            return {"answer": "I couldn't find that employee. Could you share their name or email?", "intent": intent}
        if employee.project:
            return {"answer": f"{employee.name} is assigned to Project {employee.project.name}.", "intent": intent}
        return {"answer": f"{employee.name} is not currently assigned to a project.", "intent": intent}

    if intent == "seat_occupant_lookup":
        seat_number = entities["seat_number"]
        seat = db.query(models.Seat).filter(models.Seat.seat_number.ilike(seat_number)).first()
        if not seat:
            return {"answer": f"I couldn't find a seat numbered {seat_number}.", "intent": intent}
        allocation = (
            db.query(models.SeatAllocation)
            .filter(
                models.SeatAllocation.seat_id == seat.id,
                models.SeatAllocation.allocation_status == models.AllocationStatus.active,
            )
            .first()
        )
        if not allocation:
            return {
                "answer": f"Seat {seat.seat_number} (Floor {seat.floor}, Zone {seat.zone}) is currently {seat.status.value}, no one is seated there.",
                "intent": intent,
            }
        emp = db.query(models.Employee).get(allocation.employee_id)
        project_part = f", assigned to Project {emp.project.name}" if emp and emp.project else ""
        return {
            "answer": f"Seat {seat.seat_number} (Floor {seat.floor}, Zone {seat.zone}) is occupied by {emp.name if emp else 'an unknown employee'}{project_part}.",
            "intent": intent,
        }

    if intent == "project_location":
        if not entities["project"]:
            return {"answer": "Which project would you like the location for?", "intent": intent}
        project = db.query(models.Project).filter(models.Project.name.ilike(f"%{entities['project']}%")).first()
        if not project:
            return {"answer": f"I couldn't find a project named {entities['project']}.", "intent": intent}
        rows = (
            db.query(models.Seat.floor, func.count(models.SeatAllocation.id))
            .join(models.SeatAllocation, models.SeatAllocation.seat_id == models.Seat.id)
            .filter(
                models.SeatAllocation.project_id == project.id,
                models.SeatAllocation.allocation_status == models.AllocationStatus.active,
            )
            .group_by(models.Seat.floor)
            .order_by(models.Seat.floor)
            .all()
        )
        if not rows:
            return {"answer": f"Project {project.name} doesn't currently have anyone seated.", "intent": intent}
        parts = [f"Floor {floor} ({count} people)" for floor, count in rows]
        return {"answer": f"Project {project.name} is seated across: {', '.join(parts)}.", "intent": intent}

    if intent == "availability_check":
        q = db.query(models.Seat).filter(models.Seat.status == models.SeatStatus.available)
        if entities["floor"] is not None:
            q = q.filter(models.Seat.floor == entities["floor"])
        if entities["zone"]:
            q = q.filter(models.Seat.zone == entities["zone"])
        seats = q.limit(20).all()
        count = q.count()
        if not seats:
            return {"answer": "No available seats match that filter right now.", "intent": intent}
        listing = ", ".join(f"{s.seat_number} (Floor {s.floor}, Zone {s.zone})" for s in seats[:10])
        more = f" and {count - 10} more" if count > 10 else ""
        return {"answer": f"There are {count} available seats. Examples: {listing}{more}.", "intent": intent}

    if intent == "utilization_check":
        if entities["project"]:
            project = db.query(models.Project).filter(models.Project.name.ilike(f"%{entities['project']}%")).first()
            if not project:
                return {"answer": f"I couldn't find a project named {entities['project']}.", "intent": intent}
            occupied = (
                db.query(models.SeatAllocation)
                .filter(
                    models.SeatAllocation.project_id == project.id,
                    models.SeatAllocation.allocation_status == models.AllocationStatus.active,
                )
                .count()
            )
            return {"answer": f"Project {project.name} currently has {occupied} occupied seats.", "intent": intent}
        total = db.query(models.Seat).count()
        occupied = db.query(models.Seat).filter(models.Seat.status == models.SeatStatus.occupied).count()
        return {"answer": f"{occupied} of {total} seats are currently occupied ({total - occupied} free).", "intent": intent}

    if intent == "team_location":
        employee = _resolve_employee(db, entities["email"], entities["name"])
        if not employee:
            return {
                "answer": "I couldn't find that employee. Could you share their name or email?",
                "intent": intent,
            }
        seat = _current_seat(db, employee)
        if not seat:
            return {
                "answer": f"{employee.name} doesn't have an active seat allocation yet, so I can't tell who's nearby.",
                "intent": intent,
            }
        nearby_allocations = (
            db.query(models.SeatAllocation)
            .join(models.Seat, models.SeatAllocation.seat_id == models.Seat.id)
            .filter(
                models.Seat.floor == seat.floor,
                models.Seat.zone == seat.zone,
                models.SeatAllocation.allocation_status == models.AllocationStatus.active,
                models.SeatAllocation.employee_id != employee.id,
            )
            .limit(10)
            .all()
        )
        if not nearby_allocations:
            return {
                "answer": f"No one else is currently seated on Floor {seat.floor}, Zone {seat.zone} (where {employee.name} sits).",
                "intent": intent,
            }
        neighbor_ids = [a.employee_id for a in nearby_allocations]
        neighbors = db.query(models.Employee).filter(models.Employee.id.in_(neighbor_ids)).all()
        names = ", ".join(n.name for n in neighbors)
        return {
            "answer": f"Seated near {employee.name} on Floor {seat.floor}, Zone {seat.zone}: {names}.",
            "intent": intent,
        }

    if intent == "allocate_request":
        return {
            "answer": "To allocate a seat for a new joiner, please use the seat allocation form (or POST /seats/allocate) with the employee's ID and project.",
            "intent": intent,
        }

    if intent == "release_request":
        employee = _resolve_employee(db, entities["email"], entities["name"])
        if not employee:
            return {
                "answer": "I need to know who you are to release a seat — please include your name or email.",
                "intent": intent,
            }
        try:
            allocation = release_seat(db, employee_id=employee.id)
        except AllocationError:
            return {"answer": f"{employee.name} doesn't have an active seat allocation to release.", "intent": intent}
        seat = db.query(models.Seat).get(allocation.seat_id)
        seat_desc = f"Floor {seat.floor}, Zone {seat.zone}, Seat {seat.seat_number}" if seat else "their seat"
        return {"answer": f"Done — {seat_desc} has been released and is now available.", "intent": intent}

    return {
        "answer": "I didn't quite understand that. Try asking things like 'Where is employee Amit seated?', "
                  "'Show available seats on Floor 3', or 'How many seats are occupied for Project Talos?'",
        "intent": intent,
    }