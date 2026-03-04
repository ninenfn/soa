# Marketplace API

## 1. OpenAPI спецификация CRUD
**Файл:** `openapi/openapi.yaml`

**Эндпоинты:**
- `POST /products` - создание товара
- `GET /products/{id}` - получение товара по ID
- `GET /products` - список товаров с пагинацией и фильтрацией
- `PUT /products/{id}` - обновление товара
- `DELETE /products/{id}` - мягкое удаление (статус ARCHIVED)

**Пагинация и фильтрация:**
```yaml
parameters:
  - name: page
    in: query
    schema: type: integer default: 0
  - name: size
    in: query
    schema: type: integer default: 20
  - name: status
    in: query
    schema: $ref: '#/components/schemas/ProductStatus'
  - name: category
    in: query
    schema: type: string
```
## 2. Описание схем данных
**ProductCreate:**

```yaml
type: object
required: [name, price, stock, category, status]
properties:
  name: { type: string, minLength: 1, maxLength: 255 }
  description: { type: string, maxLength: 4000, nullable: true }
  price: { type: number, format: decimal, minimum: 0.01 }
  stock: { type: integer, minimum: 0 }
  category: { type: string, minLength: 1, maxLength: 100 }
  status: { $ref: '#/components/schemas/ProductStatus' }
```
**ProductUpdate:**
```yaml
type: object
properties:
  name: { type: string, minLength: 1, maxLength: 255, nullable: true }
  description: { type: string, maxLength: 4000, nullable: true }
  price: { type: number, format: decimal, minimum: 0.01, nullable: true }
  stock: { type: integer, minimum: 0, nullable: true }
  category: { type: string, minLength: 1, maxLength: 100, nullable: true }
  status: { $ref: '#/components/schemas/ProductStatus', nullable: true }
```

**ProductResponse:**
```yaml
type: object
required: [id, name, price, stock, category, status, created_at, seller_id]
properties:
  id: { type: string, format: uuid }
  name: { type: string }
  description: { type: string, nullable: true }
  price: { type: number, format: decimal }
  stock: { type: integer }
  category: { type: string }
  status: { $ref: '#/components/schemas/ProductStatus' }
  seller_id: { type: string, format: uuid }
  created_at: { type: string, format: date-time }
  updated_at: { type: string, format: date-time, nullable: true }
```

**ProductStatus:**
```yaml
type: string
enum: [ACTIVE, INACTIVE, ARCHIVED]
```

## 3. Кодогенерация
**Команда генерации:**

```bash
docker run --rm -v ${PWD}:/local openapitools/openapi-generator-cli generate \
  -i /local/openapi/openapi.yaml \
  -g python-fastapi \
  -o /local/generated \
  --additional-properties=packageName=marketplace_api
```

**Использование в коде:**

```python
from marketplace_api.models.product_create import ProductCreate
from marketplace_api.models.product_update import ProductUpdate
from marketplace_api.models.product_response import ProductResponse
from marketplace_api.models.products_page import ProductsPage
from marketplace_api.models.error import Error
```

## 4. PostgreSQL + базовый CRUD
**Миграции Flyway: src/migrations/V1__initial_schema.sql**

```sql
-- Таблица products
CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(12, 2) NOT NULL CHECK (price > 0),
    stock INTEGER NOT NULL CHECK (stock >= 0),
    category VARCHAR(100) NOT NULL,
    status product_status NOT NULL,
    seller_id UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Индекс на поле status
CREATE INDEX idx_products_status ON products(status);

-- Триггер для updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_products_updated_at 
    BEFORE UPDATE ON products 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();
```

**Мягкое удаление:**

```python
@app.delete("/api/v1/products/{id}", status_code=204)
async def delete_product(id: str, db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(models.Product.id == id).first()
    product.status = models.ProductStatus.ARCHIVED
    db.commit()
```

## 5. Контрактная обработка ошибок
**Схема ошибки:**

```yaml
Error:
  type: object
  required: [error_code, message]
  properties:
    error_code:
      type: string
      enum:
        - PRODUCT_NOT_FOUND
        - PRODUCT_INACTIVE
        - ORDER_NOT_FOUND
        - ORDER_LIMIT_EXCEEDED
        - ORDER_HAS_ACTIVE
        - INVALID_STATE_TRANSITION
        - INSUFFICIENT_STOCK
        - PROMO_CODE_INVALID
        - PROMO_CODE_MIN_AMOUNT
        - ORDER_OWNERSHIP_VIOLATION
        - VALIDATION_ERROR
        - ACCESS_DENIED
        - TOKEN_EXPIRED
        - TOKEN_INVALID
        - REFRESH_TOKEN_INVALID
    message: { type: string }
    details: { type: object, nullable: true }
```

**Пример ответа:**

```json
{
  "error_code": "ORDER_LIMIT_EXCEEDED",
  "message": "Too many order creation attempts",
  "details": null
}
```

## 6. Контрактная валидация входных данных
**Ограничения в OpenAPI:**

```yaml
name: { minLength: 1, maxLength: 255 }
description: { maxLength: 4000 }
price: { minimum: 0.01, exclusiveMinimum: true }
stock: { minimum: 0 }
category: { minLength: 1, maxLength: 100 }
items: { minItems: 1, maxItems: 50 }
quantity: { minimum: 1, maximum: 999 }
promo_code: { pattern: '^[A-Z0-9_]{4,20}$' }
```

**Пример валидации:**

```json
{
  "detail": [{
    "type": "greater_than",
    "loc": ["body", "price"],
    "msg": "Input should be greater than 0.01",
    "input": -100
  }]
}
```

## 7. Сложная бизнес-логика для заказов
**Модель состояний заказа:**

```python
class OrderStatus(enum.Enum):
    CREATED = "CREATED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAID = "PAID"
    SHIPPED = "SHIPPED"
    COMPLETED = "COMPLETED"
    CANCELED = "CANCELED"
```

**Проверка частоты создания:**

```python
last_order = db.query(models.UserOperation).filter(
    models.UserOperation.user_id == current_user.id,
    models.UserOperation.operation_type == models.OperationType.CREATE_ORDER
).order_by(models.UserOperation.created_at.desc()).first()

if last_order:
    cooldown = datetime.utcnow() - last_order.created_at.replace(tzinfo=None)
    if cooldown.total_seconds() < settings.ORDER_CREATE_COOLDOWN_MINUTES * 60:
        raise HTTPException(
            status_code=429,
            detail={'code': 'ORDER_LIMIT_EXCEEDED', 'message': 'Too many order creation attempts'}
        )
```   

**Проверка активных заказов:**

```python
active_order = db.query(models.Order).filter(
    models.Order.user_id == current_user.id,
    models.Order.status.in_([models.OrderStatus.CREATED, models.OrderStatus.PAYMENT_PENDING])
).first()

if active_order:
    raise HTTPException(
        status_code=409,
        detail={'code': 'ORDER_HAS_ACTIVE', 'message': 'User already has an active order'}
    )
```

**Проверка остатков:**

```python
insufficient_stock = []
for item in order_data.items:
    product = db.query(models.Product).filter(models.Product.id == item.product_id).first()
    if product.stock < item.quantity:
        insufficient_stock.append({
            'product_id': str(item.product_id),
            'requested': item.quantity,
            'available': product.stock
        })

if insufficient_stock:
    raise HTTPException(
        status_code=409,
        detail={
            'code': 'INSUFFICIENT_STOCK',
            'message': 'Insufficient stock for some products',
            'details': {'products': insufficient_stock}
        }
    )
```    
**Резервирование в транзакции:**

```python
try:
    for product, item in products:
        product.stock -= item.quantity
    db.commit()
except Exception:
    db.rollback()
    raise
```   

**Снапшот цен:**

```python
order_item = models.OrderItem(
    order_id=order.id,
    product_id=product.id,
    quantity=item.quantity,
    price_at_order=product.price  # фиксация цены на момент заказа
)
```

**Отмена заказа:**

```python
@app.post("/api/v1/orders/{id}/cancel")
async def cancel_order(id: str, db: Session = Depends(get_db)):
    order = db.query(models.Order).filter(models.Order.id == id).first()
    
    if order.status not in [models.OrderStatus.CREATED, models.OrderStatus.PAYMENT_PENDING]:
        raise HTTPException(
            status_code=409,
            detail={'code': 'INVALID_STATE_TRANSITION', 'message': f'Order cannot be cancelled from {order.status.value} state'}
        )
    
    # Возврат остатков
    order_items = db.query(models.OrderItem).filter(models.OrderItem.order_id == order.id).all()
    for item in order_items:
        product = db.query(models.Product).filter(models.Product.id == item.product_id).first()
        product.stock += item.quantity
    
    order.status = models.OrderStatus.CANCELED
    db.commit()
```

## 8. Логирование API
**Middleware для логирования:**

```python
@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start_time = time.time()
    
    response = await call_next(request)
    
    log_entry = {
        'timestamp': datetime.utcnow().isoformat(),
        'method': request.method,
        'endpoint': request.url.path,
        'status_code': response.status_code,
        'duration_ms': int((time.time() - start_time) * 1000),
        'request_id': request_id,
        'user_id': getattr(request.state, 'user_id', None)
    }
    
    logger.info(json.dumps(log_entry))
    response.headers["X-Request-Id"] = request_id
    return response
```

**Пример лога:**

```json
{
  "timestamp": "2026-02-25T13:28:49.456346",
  "method": "POST",
  "endpoint": "/api/v1/products",
  "status_code": 201,
  "duration_ms": 245,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "8dad933d-8ac0-4f12-85af-e02eca09ba4c"
}
```

## 9. Авторизация доступа к API
**JWT токены:**

```python
class SecurityService:
    @staticmethod
    def create_access_token(data: dict) -> str:
        expire = datetime.utcnow() + timedelta(minutes=30)
        data.update({"exp": expire, "type": "access"})
        return jwt.encode(data, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    
    @staticmethod
    def create_refresh_token(data: dict) -> str:
        expire = datetime.utcnow() + timedelta(days=7)
        data.update({"exp": expire, "type": "refresh"})
        return jwt.encode(data, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
```

**Эндпоинты аутентификации:**

```python
POST /api/v1/auth/register
POST /api/v1/auth/login      # возвращает access_token и refresh_token
POST /api/v1/auth/refresh    # обновление access_token
```

**Проверка токена:**

```python
async def get_current_user(request: Request, db: Session = Depends(get_db)):
    auth_header = request.headers.get('Authorization')
    token = auth_header.split(' ')[1]
    payload = SecurityService.decode_token(token)
    user = db.query(models.User).filter(models.User.id == payload.get('sub')).first()
    return user
```

## 10. Ролевая модель доступа
**Роли:**

```python
class UserRole(enum.Enum):
    USER = "USER"
    SELLER = "SELLER"
    ADMIN = "ADMIN"
```
**Проверка ролей:**

```python
def require_role(required_roles: List[models.UserRole]):
    async def role_checker(current_user = Depends(get_current_user)):
        if current_user.role not in required_roles:
            raise HTTPException(
                status_code=403,
                detail={'code': 'ACCESS_DENIED', 'message': 'Insufficient permissions'}
            )
        return current_user
    return role_checker
```
**Матрица доступа:**

```python
# Просмотр товаров - все
@app.get("/api/v1/products")
async def get_products(current_user = Depends(get_current_user)):

# Создание товара - только SELLER и ADMIN
@app.post("/api/v1/products")
async def create_product(current_user = Depends(require_role([models.UserRole.SELLER, models.UserRole.ADMIN]))):

# Обновление товара - SELLER (только свои) и ADMIN
@app.put("/api/v1/products/{id}")
async def update_product(current_user = Depends(require_role([models.UserRole.SELLER, models.UserRole.ADMIN]))):
    if current_user.role == models.UserRole.SELLER and product.seller_id != current_user.id:
        raise HTTPException(status_code=403, detail={'code': 'ACCESS_DENIED'})

# Создание заказа - USER и ADMIN
@app.post("/api/v1/orders")
async def create_order(current_user = Depends(require_role([models.UserRole.USER, models.UserRole.ADMIN]))):

# Создание промокода - SELLER и ADMIN
@app.post("/api/v1/promo-codes")
async def create_promo_code(current_user = Depends(require_role([models.UserRole.SELLER, models.UserRole.ADMIN]))):
```

# Примеры для защиты

## 1. Проверка CRUD для товаров

```powershell
# Создание товара (SELLER)
$product = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/products" -Method Post -Headers @{
    "Authorization" = "Bearer $SELLER_TOKEN"
    "Content-Type" = "application/json"
} -Body (@{
    name="Nbook"
    price=999.99
    stock=10
    category="Elec"
    status="ACTIVE"
} | ConvertTo-Json)
$PRODUCT_ID = $product.id

# Получение по ID
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/products/$PRODUCT_ID" -Method Get -Headers @{
    "Authorization" = "Bearer $SELLER_TOKEN"
}

# Список с пагинацией
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/products?page=0&size=10" -Method Get -Headers @{
    "Authorization" = "Bearer $SELLER_TOKEN"
}

# Обновление
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/products/$PRODUCT_ID" -Method Put -Headers @{
    "Authorization" = "Bearer $SELLER_TOKEN"
    "Content-Type" = "application/json"
} -Body (@{ price=899.99; stock=15 } | ConvertTo-Json)

# Мягкое удаление
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/products/$PRODUCT_ID" -Method Delete -Headers @{
    "Authorization" = "Bearer $SELLER_TOKEN"
}
```


## 2. Проверка пагинации и фильтрации
```powershell
# Пагинация
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/products?page=0&size=2" -Method Get -Headers @{
    "Authorization" = "Bearer $USER_TOKEN"
}

# Фильтр по статусу
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/products?status=ACTIVE" -Method Get -Headers @{
    "Authorization" = "Bearer $USER_TOKEN"
}

# Фильтр по категории
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/products?category=Электроника" -Method Get -Headers @{
    "Authorization" = "Bearer $USER_TOKEN"
}
```

## 3. Проверка обработки ошибок

```powershell
# PRODUCT_NOT_FOUND (404)
try {
    Invoke-RestMethod -Uri "http://localhost:8000/api/v1/products/00000000-0000-0000-0000-000000000000" -Method Get -Headers @{
        "Authorization" = "Bearer $USER_TOKEN"
    }
} catch { $_.Exception.Response.StatusCode }

# ORDER_LIMIT_EXCEEDED (429)
# ORDER_HAS_ACTIVE (409)
# INSUFFICIENT_STOCK (409)
# VALIDATION_ERROR (400) - отрицательная цена
try {
    Invoke-RestMethod -Uri "http://localhost:8000/api/v1/products" -Method Post -Headers @{
        "Authorization" = "Bearer $SELLER_TOKEN"
        "Content-Type" = "application/json"
    } -Body (@{ name="Test"; price=-100; stock=10; category="Test"; status="ACTIVE" } | ConvertTo-Json)
} catch { $_.Exception.Response.StatusCode }

```

## 4. Проверка бизнес-логики заказов
```powershell

# Чтобы не ждать 5 минут(ограничение по ссозданию закаоков)
docker-compose exec db psql -U postgres -d marketplace -c "DELETE FROM user_operations WHERE user_id = (SELECT id FROM users WHERE username = 'user');"


# Создание заказа
$order = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/orders" -Method Post -Headers @{
    "Authorization" = "Bearer $USER_TOKEN"
    "Content-Type" = "application/json"
} -Body (@{
    items = @(@{ product_id = "$PRODUCT_ID"; quantity = 2 })
} | ConvertTo-Json -Depth 3)
$ORDER_ID = $order.id

# Проверка ORDER_HAS_ACTIVE (повторное создание 429 ошибка)
try {
    Invoke-RestMethod -Uri "http://localhost:8000/api/v1/orders" -Method Post -Headers @{
        "Authorization" = "Bearer $USER_TOKEN"
        "Content-Type" = "application/json"
    } -Body (@{ items = @(@{ product_id = "$PRODUCT_ID"; quantity = 1 }) } | ConvertTo-Json -Depth 3)
} catch { $_.Exception.Response.StatusCode }

# Отмена заказа
$canceled = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/orders/$ORDER_ID/cancel" -Method Post -Headers @{
    "Authorization" = "Bearer $USER_TOKEN"
}
$canceled.status  # Должен быть CANCELED
```


## 5. Проверка валидации
```powershell
# quantity > 999 (422)
try {
    Invoke-RestMethod -Uri "http://localhost:8000/api/v1/orders" -Method Post -Headers @{
        "Authorization" = "Bearer $USER_TOKEN"
        "Content-Type" = "application/json"
    } -Body (@{ items = @(@{ product_id = "$PRODUCT_ID"; quantity = 1000 }) } | ConvertTo-Json -Depth 3)
} catch { $_.Exception.Response.StatusCode }
```

## 6. Проверка авторизации и ролей
```powershell
# USER пытается создать товар (403)
try {
    Invoke-RestMethod -Uri "http://localhost:8000/api/v1/products" -Method Post -Headers @{
        "Authorization" = "Bearer $USER_TOKEN"
        "Content-Type" = "application/json"
    } -Body (@{ name="Hack"; price=100; stock=1; category="Test"; status="ACTIVE" } | ConvertTo-Json)
} catch { $_.Exception.Response.StatusCode }

# Невалидный токен (401)
try {
    Invoke-RestMethod -Uri "http://localhost:8000/api/v1/products" -Method Get -Headers @{
        "Authorization" = "Bearer invalid.token.here"
    }
} catch { $_.Exception.Response.StatusCode }

```

## 7. Проверка базы данных

```powershell
# Содержимое таблиц
docker-compose exec db psql -U postgres -d marketplace -c "SELECT * FROM products;"
docker-compose exec db psql -U postgres -d marketplace -c "SELECT * FROM orders;"
docker-compose exec db psql -U postgres -d marketplace -c "SELECT * FROM order_items;"
docker-compose exec db psql -U postgres -d marketplace -c "SELECT * FROM user_operations;"

# Проверка индекса
docker-compose exec db psql -U postgres -d marketplace -c "\di"


PS C:\Users\Chikapushka\Desktop\marketplace> docker-compose exec db psql -U postgres -d marketplace -c "\di"
                         List of relations
 Schema |         Name         | Type  |  Owner   |      Table
--------+----------------------+-------+----------+-----------------
 public | idx_products_status  | index | postgres | products
 public | order_items_pkey     | index | postgres | order_items
 public | orders_pkey          | index | postgres | orders
 public | products_pkey        | index | postgres | products
 public | promo_codes_code_key | index | postgres | promo_codes
 public | promo_codes_pkey     | index | postgres | promo_codes
 public | user_operations_pkey | index | postgres | user_operations
 public | users_email_key      | index | postgres | users
 public | users_pkey           | index | postgres | users
 public | users_username_key   | index | postgres | users
(10 rows)
```

## 8. Проверка логов
```powershell
# посмотреть все логи
docker-compose logs app

# найти логи с request_id
docker-compose logs app | findstr "request_id"
```

# Запуск

## 1. Очистка перед запуском
```powershell
# Остановить контейнеры и удалить volumes
docker-compose down -v

Или лучше если не кеш мешает
# Остановить контейнеры и удалить volumes
docker-compose down -v
# Удалить все неиспользуемые контейнеры, сети, образы
docker system prune -a -f
# Удалить volumes принудительно
docker volume prune -f
```

## 2. Генерация кода из OpenAPI
```powershell
# Создать папку generated если её нет
New-Item -ItemType Directory -Force -Path generated

# Сгенерировать код
docker run --rm -v ${PWD}:/local openapitools/openapi-generator-cli generate `
  -i /local/openapi/openapi.yaml `
  -g python-fastapi `
  -o /local/generated `
  --additional-properties=packageName=marketplace_api
```

## 3. Создание init.py файлов
```powershell
# Создать структуру пакетов Python
New-Item -ItemType File -Force -Path generated\__init__.py
New-Item -ItemType File -Force -Path generated\src\__init__.py
New-Item -ItemType File -Force -Path generated\src\marketplace_api\__init__.py
New-Item -ItemType File -Force -Path generated\src\marketplace_api\models\__init__.py
```

## 4. Запуск приложения
```powershell
# Собрать и запустить контейнеры
docker-compose build --no-cache
# Запустить контейнеры
docker-compose up -d
```

## 5. Проверка работы
```powershell
# Открыть документацию в браузере
Start-Process "http://localhost:8000/docs"
```

## 6. Структура проекта

```text
marketplace/
├── docker-compose.yml          #  ostgreSQL + приложение
├── Dockerfile                   # Сборка образа Python с зависимостями
├── requirements.txt              # Список зависимостей Python (fastapi, sqlalchemy, bcrypt, и т.д.)
├── openapi/
│   └── openapi.yaml              # OpenAPI спецификация API (все endpoints, схемы, валидация)
├── src/
│   ├── main.py                    # Основной файл приложения: все endpoints и бизнес-логика
│   ├── models.py                   # SQLAlchemy модели таблиц БД
│   ├── database.py                  # Подключение к PostgreSQL, сессии
│   ├── security.py                   # JWT токены, хеширование паролей (bcrypt)
│   ├── config.py                      # Настройки из переменных окружения
│   └── migrations/
│       └── V1__initial_schema.sql      # Flyway миграция: создание таблиц, индексов, триггеров
└── generated/                           # Сгенерированный код из OpenAPI
    ├── __init__.py                       # Делает папку Python-пакетом
    └── src/
        └── marketplace_api/
            └── models/                    # Pydantic модели
```        

**Требования**
- Порт 8000 свободен
- Порт 5432 свободен