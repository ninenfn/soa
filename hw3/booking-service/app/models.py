from sqlalchemy import Column, Integer, String, DateTime, Float, Enum, CheckConstraint, Index
from .database import Base
import enum
from datetime import datetime

class BookingStatus(enum.Enum):
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"

class Booking(Base):
    __tablename__ = "bookings"
    
    id = Column(String(36), primary_key=True)  # UUID
    user_id = Column(String(100), nullable=False, index=True)
    flight_id = Column(Integer, nullable=False)
    passenger_name = Column(String(200), nullable=False)
    passenger_email = Column(String(200), nullable=False)
    seat_count = Column(Integer, nullable=False)
    total_price = Column(Float, nullable=False)
    status = Column(Enum(BookingStatus), default=BookingStatus.CONFIRMED)
    created_at = Column(DateTime, default=datetime.now)
    
    __table_args__ = (
        CheckConstraint('seat_count > 0', name='check_seat_count_positive'),
        CheckConstraint('total_price > 0', name='check_price_positive'),
        Index('idx_bookings_user_id', 'user_id'),
        Index('idx_bookings_flight_id', 'flight_id'),
        Index('idx_bookings_created_at', 'created_at'),
    )