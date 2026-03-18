#!/bin/bash

cd booking-service
python -m grpc_tools.protoc -I ../proto --python_out=app --grpc_python_out=app ../proto/flight_service.proto
cd ..

cd flight-service
python -m grpc_tools.protoc -I ../proto --python_out=app --grpc_python_out=app ../proto/flight_service.proto
cd ..