import enum
from datetime import datetime, date

from sqlalchemy import (
    Column, Integer, String, Date, DateTime, Enum, ForeignKey,
    UniqueConstraint, Index, Boolean
)
from sqlalchemy.orm import relationship

from .database import Base


class EmployeeStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"
    pending = "pending"


class ProjectStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"


class SeatStatus(str, enum.Enum):
    available = "available"
    occupied = "occupied"
    reserved = "reserved"
    maintenance = "maintenance"


class AllocationStatus(str, enum.Enum):
    active = "active"
    released = "released"


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    employee_code = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    department = Column(String, index=True)
    role = Column(String)
    joining_date = Column(Date, default=date.today)
    status = Column(Enum(EmployeeStatus), default=EmployeeStatus.pending, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="employees")
    allocations = relationship("SeatAllocation", back_populates="employee")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String, nullable=True)
    manager_name = Column(String, nullable=True)
    status = Column(Enum(ProjectStatus), default=ProjectStatus.active)
    created_at = Column(DateTime, default=datetime.utcnow)

    employees = relationship("Employee", back_populates="project")


class Seat(Base):
    __tablename__ = "seats"
    __table_args__ = (
        UniqueConstraint("floor", "zone", "seat_number", name="uq_seat_floor_zone_number"),
        Index("ix_seat_status", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    floor = Column(Integer, nullable=False)
    zone = Column(String, nullable=False)
    bay = Column(String, nullable=True)
    seat_number = Column(String, nullable=False)
    status = Column(Enum(SeatStatus), default=SeatStatus.available, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    allocations = relationship("SeatAllocation", back_populates="seat")


class SeatAllocation(Base):
    __tablename__ = "seat_allocations"
    __table_args__ = (
        Index("ix_allocation_status", "allocation_status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    seat_id = Column(Integer, ForeignKey("seats.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    allocation_status = Column(Enum(AllocationStatus), default=AllocationStatus.active, index=True)
    allocation_date = Column(DateTime, default=datetime.utcnow)
    released_date = Column(DateTime, nullable=True)
    alternate_zone = Column(Boolean, default=False)

    employee = relationship("Employee", back_populates="allocations")
    seat = relationship("Seat", back_populates="allocations")
    project = relationship("Project")
