import grpc
import logging
from concurrent import futures
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
import os
import sys

# Добавляем путь к корневой директории
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import flight_service_pb2
from app import flight_service_pb2_grpc
from app.database import SessionLocal, engine, Base
from app import models
from app.redis_client import redis_cache
from app.auth import APIKeyInterceptor
from google.protobuf import empty_pb2

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FlightServicer(flight_service_pb2_grpc.FlightServiceServicer):
    
    def SearchFlights(self, request, context):
        """Поиск рейсов с кешированием"""
        # Формируем ключ кеша
        cache_key = f"search:{request.origin}:{request.destination}"
        if request.HasField('date'):
            date_str = request.date.ToDatetime().date().isoformat()
            cache_key += f":{date_str}"
        
        # Проверяем кеш
        cached = redis_cache.get(cache_key)
        if cached:
            logger.info(f"CACHE HIT: {cache_key}")
            response = flight_service_pb2.SearchFlightsResponse()
            for flight_data in cached:
                flight = response.flights.add()
                flight.id = flight_data['id']
                flight.flight_number = flight_data['flight_number']
                flight.airline = flight_data['airline']
                flight.origin = flight_data['origin']
                flight.destination = flight_data['destination']
                flight.total_seats = flight_data['total_seats']
                flight.available_seats = flight_data['available_seats']
                flight.price = flight_data['price']
                flight.status = flight_data['status']
                
                from google.protobuf.timestamp_pb2 import Timestamp
                departure_ts = Timestamp()
                departure_ts.FromDatetime(datetime.fromisoformat(flight_data['departure_time']))
                flight.departure_time.CopyFrom(departure_ts)
                
                arrival_ts = Timestamp()
                arrival_ts.FromDatetime(datetime.fromisoformat(flight_data['arrival_time']))
                flight.arrival_time.CopyFrom(arrival_ts)
            return response
        
        logger.info(f"CACHE MISS: {cache_key}")
        
        # Cache miss - ищем в БД
        db: Session = SessionLocal()
        try:
            query = db.query(models.Flight).filter(
                models.Flight.origin == request.origin,
                models.Flight.destination == request.destination,
                models.Flight.status == models.FlightStatus.SCHEDULED
            )
            
            if request.HasField('date'):
                date = request.date.ToDatetime().date()
                query = query.filter(
                    func.date(models.Flight.departure_time) == date
                )
            
            flights = query.all()
            
            # Формируем ответ и кешируем
            response = flight_service_pb2.SearchFlightsResponse()
            flights_data = []
            
            for f in flights:
                flight = response.flights.add()
                flight.id = f.id
                flight.flight_number = f.flight_number
                flight.airline = f.airline
                flight.origin = f.origin
                flight.destination = f.destination
                flight.departure_time.FromDatetime(f.departure_time)
                flight.arrival_time.FromDatetime(f.arrival_time)
                flight.total_seats = f.total_seats
                flight.available_seats = f.available_seats
                flight.price = float(f.price)
                flight.status = flight_service_pb2.FlightStatus.Value(f.status.name)
                
                # Для кеша сохраняем данные
                flights_data.append({
                    'id': f.id,
                    'flight_number': f.flight_number,
                    'airline': f.airline,
                    'origin': f.origin,
                    'destination': f.destination,
                    'departure_time': f.departure_time.isoformat(),
                    'arrival_time': f.arrival_time.isoformat(),
                    'total_seats': f.total_seats,
                    'available_seats': f.available_seats,
                    'price': float(f.price),
                    'status': flight_service_pb2.FlightStatus.Value(f.status.name)
                })
            
            # Сохраняем в кеш
            if flights_data:
                redis_cache.set(cache_key, flights_data, ttl=300)
                logger.info(f"CACHE SET: {cache_key} (TTL: 300s)")
            
            return response
            
        finally:
            db.close()
    
    def GetFlight(self, request, context):
        """Получение рейса по ID с кешированием"""
        cache_key = f"flight:{request.id}"
        
        # Проверяем кеш
        cached = redis_cache.get(cache_key)
        if cached:
            logger.info(f"CACHE HIT: {cache_key}")
            flight = flight_service_pb2.Flight()
            flight.id = cached['id']
            flight.flight_number = cached['flight_number']
            flight.airline = cached['airline']
            flight.origin = cached['origin']
            flight.destination = cached['destination']
            flight.total_seats = cached['total_seats']
            flight.available_seats = cached['available_seats']
            flight.price = cached['price']
            flight.status = cached['status']
            
            from google.protobuf.timestamp_pb2 import Timestamp
            departure_ts = Timestamp()
            departure_ts.FromDatetime(datetime.fromisoformat(cached['departure_time']))
            flight.departure_time.CopyFrom(departure_ts)
            
            arrival_ts = Timestamp()
            arrival_ts.FromDatetime(datetime.fromisoformat(cached['arrival_time']))
            flight.arrival_time.CopyFrom(arrival_ts)
            
            return flight
        
        logger.info(f"CACHE MISS: {cache_key}")
        
        # Cache miss - ищем в БД
        db: Session = SessionLocal()
        try:
            flight = db.query(models.Flight).filter(
                models.Flight.id == request.id
            ).first()
            
            if not flight:
                context.abort(grpc.StatusCode.NOT_FOUND, f"Flight {request.id} not found")
            
            # Формируем ответ
            response = flight_service_pb2.Flight()
            response.id = flight.id
            response.flight_number = flight.flight_number
            response.airline = flight.airline
            response.origin = flight.origin
            response.destination = flight.destination
            response.departure_time.FromDatetime(flight.departure_time)
            response.arrival_time.FromDatetime(flight.arrival_time)
            response.total_seats = flight.total_seats
            response.available_seats = flight.available_seats
            response.price = float(flight.price)
            response.status = flight_service_pb2.FlightStatus.Value(flight.status.name)
            
            # Сохраняем в кеш
            cache_data = {
                'id': flight.id,
                'flight_number': flight.flight_number,
                'airline': flight.airline,
                'origin': flight.origin,
                'destination': flight.destination,
                'departure_time': flight.departure_time.isoformat(),
                'arrival_time': flight.arrival_time.isoformat(),
                'total_seats': flight.total_seats,
                'available_seats': flight.available_seats,
                'price': float(flight.price),
                'status': flight_service_pb2.FlightStatus.Value(flight.status.name)
            }
            redis_cache.set(cache_key, cache_data, ttl=600)
            logger.info(f"CACHE SET: {cache_key} (TTL: 600s)")
            
            return response
            
        finally:
            db.close()
    
    def ReserveSeats(self, request, context):
        """Резервирование мест с транзакцией"""
        db: Session = SessionLocal()
        try:
            # Начинаем транзакцию с блокировкой строки
            flight = db.query(models.Flight).filter(
                models.Flight.id == request.flight_id
            ).with_for_update().first()
            
            if not flight:
                context.abort(grpc.StatusCode.NOT_FOUND, f"Flight {request.flight_id} not found")
            
            # Проверяем статус рейса
            if flight.status != models.FlightStatus.SCHEDULED:
                context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Flight is not available for reservation")
            
            # Проверяем доступность мест
            if flight.available_seats < request.seat_count:
                context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, 
                            f"Not enough seats. Available: {flight.available_seats}, Requested: {request.seat_count}")
            
            # Проверяем идемпотентность - может уже есть резервация?
            existing = db.query(models.SeatReservation).filter(
                models.SeatReservation.booking_id == request.booking_id
            ).first()
            
            if existing:
                # Уже зарезервировано, возвращаем существующую
                logger.info(f"Duplicate reservation request for booking {request.booking_id}, returning existing")
                response = flight_service_pb2.ReserveSeatsResponse()
                response.reservation_id = str(existing.id)
                response.total_price = float(existing.seat_count * flight.price)
                return response
            
            # Атомарно обновляем доступные места
            flight.available_seats -= request.seat_count
            
            # Создаем резервацию
            reservation = models.SeatReservation(
                booking_id=request.booking_id,
                flight_id=request.flight_id,
                seat_count=request.seat_count,
                status=models.ReservationStatus.ACTIVE,
                created_at=datetime.now()
            )
            db.add(reservation)
            
            # Коммитим транзакцию
            db.commit()
            logger.info(f"Reserved {request.seat_count} seats on flight {request.flight_id} for booking {request.booking_id}")
            
            # Инвалидируем кеш
            redis_cache.invalidate_flight(request.flight_id)
            
            response = flight_service_pb2.ReserveSeatsResponse()
            response.reservation_id = str(reservation.id)
            response.total_price = float(request.seat_count * flight.price)
            
            return response
            
        except grpc.RpcError:
            # Пробрасываем gRPC ошибки дальше
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Reservation failed: {e}")
            context.abort(grpc.StatusCode.INTERNAL, str(e))
        finally:
            db.close()
        
    def ReleaseReservation(self, request, context):
        logger.info(f"ReleaseReservation called for booking {request.booking_id}")
        db: Session = SessionLocal()
        try:
            # Находим активную резервацию
            reservation = db.query(models.SeatReservation).filter(
                models.SeatReservation.booking_id == request.booking_id,
                models.SeatReservation.status == models.ReservationStatus.ACTIVE
            ).with_for_update().first()
            
            logger.info(f"Found reservation: {reservation.id if reservation else 'None'}")
            
            if not reservation:
                context.abort(grpc.StatusCode.NOT_FOUND, f"Active reservation for booking {request.booking_id} not found")
            
            # Возвращаем места
            flight = db.query(models.Flight).filter(
                models.Flight.id == reservation.flight_id
            ).with_for_update().first()
            
            if not flight:
                context.abort(grpc.StatusCode.NOT_FOUND, f"Flight {reservation.flight_id} not found")
            
            flight.available_seats += reservation.seat_count
            reservation.status = models.ReservationStatus.RELEASED
            
            db.commit()
            logger.info(f"Released {reservation.seat_count} seats on flight {reservation.flight_id} for booking {request.booking_id}")
            
            redis_cache.invalidate_flight(reservation.flight_id)
            
            return empty_pb2.Empty()
            
        except Exception as e:
            db.rollback()
            logger.error(f"Release failed: {str(e)}")
            logger.exception("Full traceback:")  # Это покажет полную ошибку
            context.abort(grpc.StatusCode.INTERNAL, str(e))
        finally:
            db.close()

def serve():
    """Запуск gRPC сервера"""
    # Создаем таблицы если их нет
    Base.metadata.create_all(bind=engine)
    
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        interceptors=[APIKeyInterceptor()]
    )
    
    flight_service_pb2_grpc.add_FlightServiceServicer_to_server(
        FlightServicer(), server
    )
    
    server.add_insecure_port('[::]:50051')
    logger.info("Flight Service starting on port 50051")
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    serve()