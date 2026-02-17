from fastapi import APIRouter, Depends
from datetime import datetime
from app.schemas import HealthResponse
from app.database import engine
import sqlalchemy

router = APIRouter(tags=["health"])

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check с проверкой БД"""
    db_status = "connected"
    
    try:
        async with engine.connect() as conn:
            await conn.execute(sqlalchemy.text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    return HealthResponse(
        status="OK",
        service="user-service",
        timestamp=datetime.utcnow().isoformat(),
        database=db_status
    )

@router.get("/health/ready")
async def readiness_check():
    """Проверка готовности"""
    return {"status": "READY", "service": "user-service"}

@router.get("/health/live")
async def liveness_check():
    """Проверка живости"""
    return {"status": "ALIVE", "service": "user-service"}