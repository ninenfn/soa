from sqlalchemy import Column, Integer, String, DateTime, Float, Enum, CheckConstraint, Index, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base
import enum

class FlightStatus(enum.Enum):
    SCHEDULED = "SCHEDULED"
    DEPARTED = "DEPARTED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"

class ReservationStatus(enum.Enum):
    ACTIVE = "ACTIVE"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"

class Flight(Base):
    __tablename__ = "flights"
    
    id = Column(Integer, primary_key=True, index=True)
    flight_number = Column(String, nullable=False)
    airline = Column(String, nullable=False)
    origin = Column(String(3), nullable=False)
    destination = Column(String(3), nullable=False)
    departure_time = Column(DateTime, nullable=False)
    arrival_time = Column(DateTime, nullable=False)
    total_seats = Column(Integer, nullable=False)
    available_seats = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    status = Column(Enum(FlightStatus), default=FlightStatus.SCHEDULED)
    
    __table_args__ = (
        Index('idx_flight_number_departure', flight_number, departure_time, unique=True),
        CheckConstraint('available_seats >= 0', name='check_available_seats_non_negative'),
        CheckConstraint('total_seats > 0', name='check_total_seats_positive'),
        CheckConstraint('price > 0', name='check_price_positive'),
    )
    
    reservations = relationship("SeatReservation", back_populates="flight")

class SeatReservation(Base):
    __tablename__ = "seat_reservations"
    
    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(String, unique=True, nullable=False, index=True)
    flight_id = Column(Integer, ForeignKey('flights.id'), nullable=False)  # ИСПРАВЛЕНО
    seat_count = Column(Integer, nullable=False)
    status = Column(Enum(ReservationStatus), default=ReservationStatus.ACTIVE)
    created_at = Column(DateTime, nullable=False)
    
    flight = relationship("Flight", back_populates="reservations")
    
    __table_args__ = (
        CheckConstraint('seat_count > 0', name='check_seat_count_positive'),
    )