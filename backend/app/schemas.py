from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, ConfigDict

from .models import EmployeeStatus, ProjectStatus, SeatStatus, AllocationStatus


# ---------- Project ----------
class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    manager_name: Optional[str] = None
    status: ProjectStatus = ProjectStatus.active


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: Optional[str] = None
    manager_name: Optional[str] = None
    status: ProjectStatus
    created_at: datetime


# ---------- Employee ----------
class EmployeeCreate(BaseModel):
    employee_code: str
    name: str
    email: EmailStr
    department: Optional[str] = None
    role: Optional[str] = None
    joining_date: Optional[date] = None
    status: EmployeeStatus = EmployeeStatus.pending
    project_id: Optional[int] = None


class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    department: Optional[str] = None
    role: Optional[str] = None
    status: Optional[EmployeeStatus] = None
    project_id: Optional[int] = None


class EmployeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_code: str
    name: str
    email: str
    department: Optional[str] = None
    role: Optional[str] = None
    joining_date: Optional[date] = None
    status: EmployeeStatus
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    current_seat: Optional[str] = None


# ---------- Seat ----------
class SeatCreate(BaseModel):
    floor: int
    zone: str
    bay: Optional[str] = None
    seat_number: str
    status: SeatStatus = SeatStatus.available

class SeatStatusUpdate(BaseModel):
    status: SeatStatus
    reason: Optional[str] = None

class SeatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    floor: int
    zone: str
    bay: Optional[str] = None
    seat_number: str
    status: SeatStatus
    occupied_by: Optional[str] = None
    occupied_by_project: Optional[str] = None
    allocation_date: Optional[datetime] = None


# ---------- Allocation ----------
class AllocateRequest(BaseModel):
    employee_id: int
    project_id: Optional[int] = None
    seat_id: Optional[int] = None
    preferred_floor: Optional[int] = None
    preferred_zone: Optional[str] = None


class ReleaseRequest(BaseModel):
    employee_id: Optional[int] = None
    seat_id: Optional[int] = None


class AllocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_id: int
    seat_id: int
    project_id: Optional[int] = None
    allocation_status: AllocationStatus
    allocation_date: datetime
    released_date: Optional[datetime] = None
    alternate_zone: bool = False
    seat: Optional[SeatOut] = None


# ---------- Dashboard ----------
class DashboardSummary(BaseModel):
    total_employees: int
    total_seats: int
    occupied_seats: int
    available_seats: int
    reserved_seats: int
    maintenance_seats: int
    new_joiners_pending: int


class ProjectUtilization(BaseModel):
    project_id: int
    project_name: str
    employee_count: int
    seats_occupied: int


class FloorUtilization(BaseModel):
    floor: int
    total_seats: int
    occupied: int
    available: int
    reserved: int
    maintenance: int


# ---------- AI Assistant ----------
class AIQueryRequest(BaseModel):
    query: str


class AIQueryResponse(BaseModel):
    answer: str
    intent: Optional[str] = None


class CSVUploadResult(BaseModel):
    created: int
    skipped: int
    errors: List[str] = []
    warnings: List[str] = []
