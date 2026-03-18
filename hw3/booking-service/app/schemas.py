from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional, List

class Flight(BaseModel):
    """Схема рейса из Flight Service"""
    id: int
    flight_number: str
    airline: str
    origin: str
    destination: str
    departure_time: datetime
    arrival_time: datetime
    total_seats: int
    available_seats: int
    price: float
    status: int  # 0=SCHEDULED, 1=DEPARTED, 2=CANCELLED, 3=COMPLETED
    
    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=100)
    flight_id: int = Field(..., gt=0)
    passenger_name: str = Field(..., min_length=1, max_length=200)
    passenger_email: EmailStr
    seat_count: int = Field(..., gt=0, le=10)  # Максимум 10 мест за раз

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: str
    total_price: float
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class BookingCancel(BaseModel):
    booking_id: str
    status: str