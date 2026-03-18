from fastapi import FastAPI, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date, datetime
import logging
import uuid

from . import models, schemas
from .database import SessionLocal, engine, get_db
from .flight_client import flight_client

# Создаем таблицы
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Booking Service")
logger = logging.getLogger(__name__)

@app.get("/flights", response_model=List[schemas.Flight])
async def search_flights(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    date: Optional[date] = None
):
    """Поиск рейсов (прокси на Flight Service)"""
    try:
        search_date = datetime.combine(date, datetime.min.time()) if date else None
        response = flight_client.search_flights(origin, destination, search_date)
        
        flights = []
        for f in response.flights:
            flights.append(schemas.Flight(
                id=f.id,
                flight_number=f.flight_number,
                airline=f.airline,
                origin=f.origin,
                destination=f.destination,
                departure_time=f.departure_time.ToDatetime(),
                arrival_time=f.arrival_time.ToDatetime(),
                total_seats=f.total_seats,
                available_seats=f.available_seats,
                price=f.price,
                status=f.status
            ))
        return flights
        
    except Exception as e:
        logger.error(f"Flight search failed: {e}")
        raise HTTPException(status_code=503, detail=str(e))

@app.get("/flights/{flight_id}", response_model=schemas.Flight)
async def get_flight(flight_id: int):
    """Получение рейса по ID (прокси на Flight Service)"""
    try:
        flight = flight_client.get_flight(flight_id)
        return schemas.Flight(
            id=flight.id,
            flight_number=flight.flight_number,
            airline=flight.airline,
            origin=flight.origin,
            destination=flight.destination,
            departure_time=flight.departure_time.ToDatetime(),
            arrival_time=flight.arrival_time.ToDatetime(),
            total_seats=flight.total_seats,
            available_seats=flight.available_seats,
            price=flight.price,
            status=flight.status
        )
    except Exception as e:
        if "Not found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=503, detail=str(e))

@app.post("/bookings", response_model=schemas.Booking, status_code=201)
async def create_booking(booking: schemas.BookingCreate, db: Session = Depends(get_db)):
    """Создание бронирования"""
    # Генерируем ID для идемпотентности
    booking_id = str(uuid.uuid4())
    
    try:
        # 1. Получаем информацию о рейсе
        flight = flight_client.get_flight(booking.flight_id)
        
        # 2. Резервируем места
        reservation = flight_client.reserve_seats(
            booking.flight_id, 
            booking.seat_count,
            booking_id
        )
        
        # 3. Создаем бронирование в БД
        db_booking = models.Booking(
            id=booking_id,
            user_id=booking.user_id,
            flight_id=booking.flight_id,
            passenger_name=booking.passenger_name,
            passenger_email=booking.passenger_email,
            seat_count=booking.seat_count,
            total_price=reservation.total_price,
            status=models.BookingStatus.CONFIRMED,
            created_at=datetime.now()
        )
        
        db.add(db_booking)
        db.commit()
        db.refresh(db_booking)
        
        return db_booking
        
    except Exception as e:
        logger.error(f"Booking creation failed: {e}")
        if "No seats available" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=503, detail=str(e))

@app.get("/bookings/{booking_id}", response_model=schemas.Booking)
async def get_booking(booking_id: str, db: Session = Depends(get_db)):
    """Получение бронирования по ID"""
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking

@app.post("/bookings/{booking_id}/cancel")
async def cancel_booking(booking_id: str, db: Session = Depends(get_db)):
    """Отмена бронирования"""
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    if booking.status != models.BookingStatus.CONFIRMED:
        raise HTTPException(status_code=400, detail="Booking is not confirmed")
    
    try:
        # Освобождаем места в Flight Service
        flight_client.release_reservation(booking_id)
        
        # Обновляем статус
        booking.status = models.BookingStatus.CANCELLED
        db.commit()
        
        return {"status": "cancelled", "booking_id": booking_id}
        
    except Exception as e:
        logger.error(f"Cancellation failed: {e}")
        raise HTTPException(status_code=503, detail=str(e))

@app.get("/bookings", response_model=List[schemas.Booking])
async def list_bookings(user_id: str, db: Session = Depends(get_db)):
    """Список бронирований пользователя"""
    bookings = db.query(models.Booking).filter(
        models.Booking.user_id == user_id
    ).all()
    return bookings