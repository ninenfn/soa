-- Тестовые бронирования
INSERT INTO bookings (id, user_id, flight_id, passenger_name, passenger_email, seat_count, total_price, status, created_at) VALUES
    ('550e8400-e29b-41d4-a716-446655440000', 'user123', 1, 'Иван Петров', 'ivan@email.com', 2, 15001.00, 'CONFIRMED', NOW() - INTERVAL '2 days'),
    ('550e8400-e29b-41d4-a716-446655440001', 'user123', 3, 'Мария Сидорова', 'maria@email.com', 1, 4500.00, 'CONFIRMED', NOW() - INTERVAL '1 day'),
    ('550e8400-e29b-41d4-a716-446655440002', 'user456', 2, 'Петр Иванов', 'petr@email.com', 3, 23400.00, 'CONFIRMED', NOW()),
    ('550e8400-e29b-41d4-a716-446655440003', 'user456', 4, 'Анна Смирнова', 'anna@email.com', 2, 25000.00, 'CANCELLED', NOW() - INTERVAL '12 hours'),
    ('550e8400-e29b-41d4-a716-446655440004', 'user789', 5, 'Сергей Козлов', 'sergey@email.com', 1, 13500.00, 'CONFIRMED', NOW() - INTERVAL '3 days');