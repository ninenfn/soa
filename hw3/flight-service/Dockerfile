FROM python:3.10-slim

WORKDIR /app

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip uninstall protobuf grpcio grpcio-tools -y && pip install protobuf==3.20.3 grpcio==1.48.2 grpcio-tools==1.48.2

# Копируем код
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY migrate.py .

# Запускаем миграции и потом сервер
CMD python migrate.py && python -m app.server