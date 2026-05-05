"""
PAYMENT MODULE - main.py
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.payments import router as payments_router
from database.db import init_db
from database.models import Base
from database.db import engine

app = FastAPI(
    title="Payment Module API",
    description="Handles payments for the food delivery system",
    version="1.0.0"
)

# Allow other modules (order module, rider module) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace * with specific URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create DB tables on startup
@app.on_event("startup")
def startup():
    init_db()

# Register payment routes
app.include_router(payments_router, prefix="/payments", tags=["Payments"])

@app.get("/")
def root():
    return {
        "message": "Payment Module is running!",
        "docs": "/docs",       # Auto-generated API docs
        "redoc": "/redoc"
    }
