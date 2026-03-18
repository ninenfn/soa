import grpc
import logging
import os
from typing import Optional, Any
from datetime import datetime, timedelta
from enum import Enum
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception, before_sleep_log, after_log

from app import flight_service_pb2
from app import flight_service_pb2_grpc

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

class CircuitBreaker:
    def __init__(self, failure_threshold=5, timeout=30):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.last_open_time = None
    
    def record_success(self):
        if self.state == CircuitState.HALF_OPEN:
            logger.info("Circuit HALF_OPEN → CLOSED (success)")
            self.state = CircuitState.CLOSED
            self.failure_count = 0
        elif self.state == CircuitState.CLOSED:
            self.failure_count = max(0, self.failure_count - 1)
    
    def record_failure(self):
        self.last_failure_time = datetime.now()
        
        if self.state == CircuitState.HALF_OPEN:
            logger.warning("Circuit HALF_OPEN → OPEN (failed)")
            self.state = CircuitState.OPEN
            self.last_open_time = datetime.now()
        elif self.state == CircuitState.CLOSED:
            self.failure_count += 1
            logger.warning(f"Failures: {self.failure_count}/{self.failure_threshold}")
            
            if self.failure_count >= self.failure_threshold:
                logger.warning("Circuit CLOSED → OPEN")
                self.state = CircuitState.OPEN
                self.last_open_time = datetime.now()
    
    def can_request(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            if self.last_open_time:
                elapsed = (datetime.now() - self.last_open_time).total_seconds()
                if elapsed >= self.timeout:
                    logger.info("Circuit OPEN → HALF_OPEN (timeout)")
                    self.state = CircuitState.HALF_OPEN
                    return True
            return False
        
        return True

class FlightClient:
    def __init__(self, host='flight-service', port=50051):
        self.host = host
        self.port = port
        self.channel = grpc.insecure_channel(f'{self.host}:{self.port}')
        self.stub = flight_service_pb2_grpc.FlightServiceStub(self.channel)
        self.api_key = os.getenv("FLIGHT_SERVICE_API_KEY", "secret-key-123")
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=int(os.getenv("CB_FAILURE_THRESHOLD", 5)),
            timeout=int(os.getenv("CB_TIMEOUT", 30))
        )
    
    def _get_metadata(self):
        return [('x-api-key', self.api_key)]
    
    def _is_retryable_error(self, e):
        return e.code() in [grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED]
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.1, min=0.1, max=0.4),
        retry=retry_if_exception(lambda e: isinstance(e, grpc.RpcError) and 
                                 e.code() in [grpc.StatusCode.UNAVAILABLE, 
                                             grpc.StatusCode.DEADLINE_EXCEEDED])
    )
    def _call_with_retry(self, method, request):
        try:
            return method(request, metadata=self._get_metadata())
        except grpc.RpcError as e:
            logger.error(f"gRPC error in _call_with_retry: {e.code()}")
            raise  # Пробрасываем дальше
        except Exception as e:
            logger.error(f"Unexpected error in _call_with_retry: {type(e).__name__}")
            raise

    def _call(self, method_name, request):
        logger.info(f"Circuit state: {self.circuit_breaker.state.value}, failures: {self.circuit_breaker.failure_count}")
        
        if not self.circuit_breaker.can_request():
            logger.warning(f"Circuit OPEN, blocking request to {method_name}")
            raise Exception("Flight service unavailable (circuit open)")
        
        try:
            method = getattr(self.stub, method_name)
            response = self._call_with_retry(method, request)
            self.circuit_breaker.record_success()
            return response
        except Exception as e:
            logger.error(f"Exception in _call: {type(e).__name__}")
            self.circuit_breaker.record_failure()  # Теперь это сработает для любых исключений
            if isinstance(e, grpc.RpcError):
                if e.code() == grpc.StatusCode.NOT_FOUND:
                    raise Exception(f"Not found: {e.details()}")
                elif e.code() == grpc.StatusCode.RESOURCE_EXHAUSTED:
                    raise Exception(f"No seats available: {e.details()}")
            raise Exception(f"Flight service error: {str(e)}")
    
    def search_flights(self, origin: str, destination: str, date: Optional[datetime] = None):
        request = flight_service_pb2.SearchFlightsRequest(
            origin=origin,
            destination=destination
        )
        if date:
            request.date.FromDatetime(date)
        return self._call('SearchFlights', request)
    
    def get_flight(self, flight_id: int):
        request = flight_service_pb2.GetFlightRequest(id=flight_id)
        return self._call('GetFlight', request)
    
    def reserve_seats(self, flight_id: int, seat_count: int, booking_id: str):
        request = flight_service_pb2.ReserveSeatsRequest(
            flight_id=flight_id,
            seat_count=seat_count,
            booking_id=booking_id
        )
        return self._call('ReserveSeats', request)
    
    def release_reservation(self, booking_id: str):
        request = flight_service_pb2.ReleaseReservationRequest(booking_id=booking_id)
        return self._call('ReleaseReservation', request)



            
flight_client = FlightClient()