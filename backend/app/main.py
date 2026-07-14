import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base
from . import models  # noqa: F401 ensures models are registered before create_all
from .routers import employees, projects, seats, dashboard, ai

# Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Ethara Seat Allocation & Project Mapping System",
    description="Manages seat allocation and project mapping for ~5,000 employees, "
                "with search, a dashboard, and a natural-language AI assistant.",
    version="1.0.0",
)

allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(employees.router)
app.include_router(projects.router)
app.include_router(seats.router)
app.include_router(dashboard.router)
app.include_router(ai.router)


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "service": "ethara-seat-allocation", "docs": "/docs"}
