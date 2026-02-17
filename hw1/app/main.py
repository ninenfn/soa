from fastapi import FastAPI
from app.routers import health, users
from app.database import engine, Base
import asyncio

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

app = FastAPI(
    title="User Service",
    description="Сервис управления пользователями маркетплейса",
    version="1.0.0"
)

app.include_router(health.router)
app.include_router(users.router)

@app.on_event("startup")
async def startup():
    await init_db()
    print("Database initialized")

@app.on_event("shutdown")
async def shutdown():
    await engine.dispose()
    print("Database connection closed")

@app.get("/")
async def root():
    return {
        "service": "user-service",
        "message": "User Service API with SQLite",
        "docs": "/docs",
        "database": "SQLite"
    }