FROM python:3.10-slim

WORKDIR /app

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY migrate.py .

# Запускаем миграции и потом приложение
CMD python migrate.py && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload