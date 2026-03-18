-- Таблица рейсов
CREATE TABLE IF NOT EXISTS flights (
    id SERIAL PRIMARY KEY,
    flight_number VARCHAR(20) NOT NULL,
    airline VARCHAR(100) NOT NULL,
    origin CHAR(3) NOT NULL,
    destination CHAR(3) NOT NULL,
    departure_time TIMESTAMP NOT NULL,
    arrival_time TIMESTAMP NOT NULL,
    total_seats INTEGER NOT NULL CHECK (total_seats > 0),
    available_seats INTEGER NOT NULL CHECK (available_seats >= 0),
    price DECIMAL(10,2) NOT NULL CHECK (price > 0),
    status flight_status NOT NULL DEFAULT 'SCHEDULED',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Индекс для уникальности
CREATE UNIQUE INDEX IF NOT EXISTS idx_flight_date_unique ON flights (flight_number, date(departure_time));

-- Таблица резерваций
CREATE TABLE IF NOT EXISTS seat_reservations (
    id SERIAL PRIMARY KEY,
    booking_id VARCHAR(36) UNIQUE NOT NULL,
    flight_id INTEGER NOT NULL REFERENCES flights(id),
    seat_count INTEGER NOT NULL CHECK (seat_count > 0),
    status reservation_status NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Индексы
CREATE INDEX IF NOT EXISTS idx_flights_route ON flights(origin, destination, departure_time);
CREATE INDEX IF NOT EXISTS idx_flights_status ON flights(status);
CREATE INDEX IF NOT EXISTS idx_reservations_booking ON seat_reservations(booking_id);
CREATE INDEX IF NOT EXISTS idx_reservations_flight ON seat_reservations(flight_id);

-- Тестовые данные
-- Тестовые данные с проверкой на существование
INSERT INTO flights (flight_number, airline, origin, destination, departure_time, arrival_time, total_seats, available_seats, price, status)
SELECT 'SU1234', 'Aeroflot', 'SVO', 'LED', NOW() + INTERVAL '1 day', NOW() + INTERVAL '1 day 1 hour', 150, 150, 7500.50, 'SCHEDULED'
WHERE NOT EXISTS (SELECT 1 FROM flights WHERE flight_number = 'SU1234' AND date(departure_time) = date(NOW() + INTERVAL '1 day'));

INSERT INTO flights (flight_number, airline, origin, destination, departure_time, arrival_time, total_seats, available_seats, price, status)
SELECT 'SU5678', 'Aeroflot', 'LED', 'SVO', NOW() + INTERVAL '2 days', NOW() + INTERVAL '2 days 1 hour', 150, 150, 7800.00, 'SCHEDULED'
WHERE NOT EXISTS (SELECT 1 FROM flights WHERE flight_number = 'SU5678' AND date(departure_time) = date(NOW() + INTERVAL '2 days'));

INSERT INTO flights (flight_number, airline, origin, destination, departure_time, arrival_time, total_seats, available_seats, price, status)
SELECT 'DP999', 'Pobeda', 'VKO', 'LED', NOW() + INTERVAL '1 day 3 hours', NOW() + INTERVAL '1 day 4 hours', 180, 180, 4500.00, 'SCHEDULED'
WHERE NOT EXISTS (SELECT 1 FROM flights WHERE flight_number = 'DP999' AND date(departure_time) = date(NOW() + INTERVAL '1 day 3 hours'));