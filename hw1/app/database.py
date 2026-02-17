from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
import os

os.makedirs("data", exist_ok=True)

DATABASE_URL = "sqlite+aiosqlite:///data/users.db"

engine = create_async_engine(
    DATABASE_URL,
    echo=True, 
    future=True
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()