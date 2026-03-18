import os
from typing import Optional
import grpc
from google.protobuf.message import Message

API_KEY = os.getenv("FLIGHT_SERVICE_API_KEY", "secret-key-123")

class APIKeyInterceptor(grpc.ServerInterceptor):   
    def intercept_service(self, continuation, handler_call_details):
        # Извлекаем метаданные
        metadata = dict(handler_call_details.invocation_metadata)
        api_key = metadata.get("x-api-key")
        
        # Проверяем API key
        if not api_key or api_key != API_KEY:
            return grpc.unary_unary_rpc_method_handler(
                lambda request, context: context.abort(
                    grpc.StatusCode.UNAUTHENTICATED,
                    "Invalid or missing API key"
                )
            )
        
        return continuation(handler_call_details)