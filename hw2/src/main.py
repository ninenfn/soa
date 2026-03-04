from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional, List
import uuid
import time
import json
import logging
from datetime import datetime
from contextvars import ContextVar

from src.database import get_db, engine
from src import models
from src.security import SecurityService
from src.config import settings

# Импортируем сгенерированные модели и контроллеры
from marketplace_api.models.product_create import ProductCreate
from marketplace_api.models.product_update import ProductUpdate
from marketplace_api.models.product_response import ProductResponse
from marketplace_api.models.products_page import ProductsPage
from marketplace_api.models.error import Error
from marketplace_api.models.order_create import OrderCreate
from marketplace_api.models.order_response import OrderResponse
from marketplace_api.models.user_register import UserRegister
from marketplace_api.models.user_login import UserLogin
from marketplace_api.models.token_response import TokenResponse
from marketplace_api.models.refresh_token import RefreshToken

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Context variable для request_id
request_id_var: ContextVar[str] = ContextVar('request_id', default='')

class JSONLogFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'message': record.getMessage(),
            'request_id': request_id_var.get(),
        }
        if hasattr(record, 'extra'):
            log_record.update(record.extra)
        return json.dumps(log_record)

# Настройка хендлера для JSON логов
handler = logging.StreamHandler()
handler.setFormatter(JSONLogFormatter())
logger.handlers = [handler]

app = FastAPI(title="Marketplace API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware для логирования
@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request_id_var.set(request_id)
    
    start_time = time.time()
    
    # Логирование входящего запроса
    logger.info(
        f"Incoming request",
        extra={
            'method': request.method,
            'endpoint': request.url.path,
            'request_id': request_id
        }
    )
    
    response = await call_next(request)
    
    duration = int((time.time() - start_time) * 1000)
    
    # Добавляем request_id в заголовок ответа
    response.headers["X-Request-Id"] = request_id
    
    # Логирование ответа
    logger.info(
        f"Request completed",
        extra={
            'method': request.method,
            'endpoint': request.url.path,
            'status_code': response.status_code,
            'duration_ms': duration,
            'request_id': request_id
        }
    )
    
    return response

# Обработчик ошибок
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    error_response = Error(
        error_code=exc.detail.get('code', 'INTERNAL_ERROR'),
        message=exc.detail.get('message', str(exc)),
        details=exc.detail.get('details')
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.dict()
    )

# Middleware для проверки JWT
async def get_current_user(request: Request, db: Session = Depends(get_db)):
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={'code': 'TOKEN_INVALID', 'message': 'Invalid token'}
        )
    
    token = auth_header.split(' ')[1]
    try:
        payload = SecurityService.decode_token(token)
        if payload.get('type') != 'access':
            raise ValueError('Invalid token type')
        
        user_id = payload.get('sub')
        if not user_id:
            raise ValueError('Invalid token')
        
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise ValueError('User not found')
        
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={'code': 'TOKEN_EXPIRED' if 'expired' in str(e) else 'TOKEN_INVALID', 'message': str(e)}
        )

# Проверка ролей
def require_role(required_roles: List[models.UserRole]):
    async def role_checker(current_user = Depends(get_current_user)):
        if current_user.role not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={'code': 'ACCESS_DENIED', 'message': 'Insufficient permissions'}
            )
        return current_user
    return role_checker

# Эндпоинты аутентификации
@app.post("/api/v1/auth/register", response_model=TokenResponse, status_code=201)
async def register(user_data: UserRegister, db: Session = Depends(get_db)):
    # Проверка уникальности
    if db.query(models.User).filter(models.User.username == user_data.username).first():
        raise HTTPException(
            status_code=400,
            detail={'code': 'VALIDATION_ERROR', 'message': 'Username already exists'}
        )
    
    if db.query(models.User).filter(models.User.email == user_data.email).first():
        raise HTTPException(
            status_code=400,
            detail={'code': 'VALIDATION_ERROR', 'message': 'Email already exists'}
        )
    
    # Создание пользователя
    user = models.User(
        username=user_data.username,
        email=user_data.email,
        password_hash=SecurityService.get_password_hash(user_data.password),
        role=user_data.role if user_data.role else models.UserRole.USER
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Создание токенов
    access_token = SecurityService.create_access_token({"sub": str(user.id), "role": user.role.value})
    refresh_token = SecurityService.create_refresh_token({"sub": str(user.id)})
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )

@app.post("/api/v1/auth/login", response_model=TokenResponse)
async def login(login_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == login_data.username).first()
    
    if not user or not SecurityService.verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail={'code': 'TOKEN_INVALID', 'message': 'Invalid credentials'}
        )
    
    access_token = SecurityService.create_access_token({"sub": str(user.id), "role": user.role.value})
    refresh_token = SecurityService.create_refresh_token({"sub": str(user.id)})
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )

@app.post("/api/v1/auth/refresh", response_model=TokenResponse)
async def refresh(refresh_data: RefreshToken, db: Session = Depends(get_db)):
    try:
        payload = SecurityService.decode_token(refresh_data.refresh_token)
        if payload.get('type') != 'refresh':
            raise ValueError('Invalid token type')
        
        user_id = payload.get('sub')
        user = db.query(models.User).filter(models.User.id == user_id).first()
        
        if not user:
            raise ValueError('User not found')
        
        access_token = SecurityService.create_access_token({"sub": str(user.id), "role": user.role.value})
        refresh_token = SecurityService.create_refresh_token({"sub": str(user.id)})
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail={'code': 'REFRESH_TOKEN_INVALID', 'message': str(e)}
        )

# Эндпоинты для товаров
@app.get("/api/v1/products", response_model=ProductsPage)
async def get_products(
    page: int = 0,
    size: int = 20,
    status: Optional[str] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    query = db.query(models.Product)
    
    if status:
        query = query.filter(models.Product.status == status)
    if category:
        query = query.filter(models.Product.category == category)
    
    total = query.count()
    products = query.offset(page * size).limit(size).all()
    
    items = [
        ProductResponse(
            id=str(p.id),
            name=p.name,
            description=p.description,
            price=float(p.price),
            stock=p.stock,
            category=p.category,
            status=p.status.value,
            seller_id=str(p.seller_id),
            created_at=p.created_at.isoformat(),
            updated_at=p.updated_at.isoformat() if p.updated_at else None
        )
        for p in products
    ]
    
    return ProductsPage(
        items=items,
        total_elements=total,
        page=page,
        size=size
    )

@app.get("/api/v1/products/{id}", response_model=ProductResponse)
async def get_product(id: str, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    try:
        product_id = uuid.UUID(id)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail={'code': 'PRODUCT_NOT_FOUND', 'message': 'Product not found'}
        )
    
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    
    if not product:
        raise HTTPException(
            status_code=404,
            detail={'code': 'PRODUCT_NOT_FOUND', 'message': f'Product with id {id} not found'}
        )
    
    return ProductResponse(
        id=str(product.id),
        name=product.name,
        description=product.description,
        price=float(product.price),
        stock=product.stock,
        category=product.category,
        status=product.status.value,
        seller_id=str(product.seller_id),
        created_at=product.created_at.isoformat(),
        updated_at=product.updated_at.isoformat() if product.updated_at else None
    )

@app.post("/api/v1/products", response_model=ProductResponse, status_code=201)
async def create_product(
    product_data: ProductCreate,
    db: Session = Depends(get_db),
    current_user = Depends(require_role([models.UserRole.SELLER, models.UserRole.ADMIN]))
):
    product = models.Product(
        name=product_data.name,
        description=product_data.description,
        price=product_data.price,
        stock=product_data.stock,
        category=product_data.category,
        status=models.ProductStatus(product_data.status),
        seller_id=current_user.id if current_user.role == models.UserRole.SELLER else product_data.seller_id
    )
    
    db.add(product)
    db.commit()
    db.refresh(product)
    
    return ProductResponse(
        id=str(product.id),
        name=product.name,
        description=product.description,
        price=float(product.price),
        stock=product.stock,
        category=product.category,
        status=product.status.value,
        seller_id=str(product.seller_id),
        created_at=product.created_at.isoformat() if product.created_at else None,
        updated_at=product.updated_at.isoformat() if product.updated_at else None
    )

@app.put("/api/v1/products/{id}", response_model=ProductResponse)
async def update_product(
    id: str,
    product_data: ProductUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(require_role([models.UserRole.SELLER, models.UserRole.ADMIN]))
):
    try:
        product_id = uuid.UUID(id)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail={'code': 'PRODUCT_NOT_FOUND', 'message': 'Product not found'}
        )
    
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    
    if not product:
        raise HTTPException(
            status_code=404,
            detail={'code': 'PRODUCT_NOT_FOUND', 'message': f'Product with id {id} not found'}
        )
    
    # Проверка прав на редактирование
    if current_user.role == models.UserRole.SELLER and product.seller_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail={'code': 'ACCESS_DENIED', 'message': 'You can only edit your own products'}
        )
    
    # Обновление полей
    if product_data.name is not None:
        product.name = product_data.name
    if product_data.description is not None:
        product.description = product_data.description
    if product_data.price is not None:
        product.price = product_data.price
    if product_data.stock is not None:
        product.stock = product_data.stock
    if product_data.category is not None:
        product.category = product_data.category
    if product_data.status is not None:
        product.status = models.ProductStatus(product_data.status)
    
    db.commit()
    db.refresh(product)
    
    return ProductResponse(
        id=str(product.id),
        name=product.name,
        description=product.description,
        price=float(product.price),
        stock=product.stock,
        category=product.category,
        status=product.status.value,
        seller_id=str(product.seller_id),
        created_at=product.created_at.isoformat(),
        updated_at=product.updated_at.isoformat() if product.updated_at else None
    )

@app.delete("/api/v1/products/{id}", status_code=204)
async def delete_product(
    id: str,
    db: Session = Depends(get_db),
    current_user = Depends(require_role([models.UserRole.SELLER, models.UserRole.ADMIN]))
):
    try:
        product_id = uuid.UUID(id)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail={'code': 'PRODUCT_NOT_FOUND', 'message': 'Product not found'}
        )
    
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    
    if not product:
        raise HTTPException(
            status_code=404,
            detail={'code': 'PRODUCT_NOT_FOUND', 'message': f'Product with id {id} not found'}
        )
    
    # Проверка прав на удаление
    if current_user.role == models.UserRole.SELLER and product.seller_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail={'code': 'ACCESS_DENIED', 'message': 'You can only delete your own products'}
        )
    
    # Мягкое удаление
    product.status = models.ProductStatus.ARCHIVED
    db.commit()

# Эндпоинты для заказов
@app.post("/api/v1/orders", response_model=OrderResponse, status_code=201)
async def create_order(
    order_data: OrderCreate,
    db: Session = Depends(get_db),
    current_user = Depends(require_role([models.UserRole.USER, models.UserRole.ADMIN]))
):
    # 1. Проверка частоты создания
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
    
    # 2. Проверка активных заказов
    active_order = db.query(models.Order).filter(
        models.Order.user_id == current_user.id,
        models.Order.status.in_([models.OrderStatus.CREATED, models.OrderStatus.PAYMENT_PENDING])
    ).first()
    
    if active_order:
        raise HTTPException(
            status_code=409,
            detail={'code': 'ORDER_HAS_ACTIVE', 'message': 'User already has an active order'}
        )
    
    # 3-4. Проверка товаров и остатков
    insufficient_stock = []
    products = []
    
    for item in order_data.items:
        product = db.query(models.Product).filter(models.Product.id == item.product_id).first()
        
        if not product:
            raise HTTPException(
                status_code=404,
                detail={'code': 'PRODUCT_NOT_FOUND', 'message': f'Product {item.product_id} not found'}
            )
        
        if product.status != models.ProductStatus.ACTIVE:
            raise HTTPException(
                status_code=409,
                detail={'code': 'PRODUCT_INACTIVE', 'message': f'Product {item.product_id} is not active'}
            )
        
        if product.stock < item.quantity:
            insufficient_stock.append({
                'product_id': str(item.product_id),
                'requested': item.quantity,
                'available': product.stock
            })
        
        products.append((product, item))
    
    if insufficient_stock:
        raise HTTPException(
            status_code=409,
            detail={
                'code': 'INSUFFICIENT_STOCK',
                'message': 'Insufficient stock for some products',
                'details': {'products': insufficient_stock}
            }
        )
    
    # Начинаем транзакцию
    try:
        # 5. Резервирование остатков и создание заказа
        total_amount = 0
        discount_amount = 0
        promo_code = None
        
        # Рассчет начальной суммы
        for product, item in products:
            total_amount += float(product.price) * item.quantity
        
        # 7. Проверка промокода
        if order_data.promo_code:
            promo_code = db.query(models.PromoCode).filter(
                models.PromoCode.code == order_data.promo_code,
                models.PromoCode.active == True,
                models.PromoCode.current_uses < models.PromoCode.max_uses,
                models.PromoCode.valid_from <= datetime.utcnow(),
                models.PromoCode.valid_until >= datetime.utcnow()
            ).first()
            
            if not promo_code:
                raise HTTPException(
                    status_code=422,
                    detail={'code': 'PROMO_CODE_INVALID', 'message': 'Invalid or expired promo code'}
                )
            
            if total_amount < float(promo_code.min_order_amount):
                raise HTTPException(
                    status_code=422,
                    detail={
                        'code': 'PROMO_CODE_MIN_AMOUNT',
                        'message': f'Minimum order amount for this promo code is {promo_code.min_order_amount}'
                    }
                )
            
            # Рассчет скидки
            if promo_code.discount_type == models.DiscountType.PERCENTAGE:
                discount = total_amount * float(promo_code.discount_value) / 100
                discount = min(discount, total_amount * 0.7)  # Не более 70%
            else:  # FIXED_AMOUNT
                discount = min(float(promo_code.discount_value), total_amount)
            
            discount_amount = discount
            
            # Инкремент использования промокода
            promo_code.current_uses += 1
        
        # Создание заказа
        order = models.Order(
            user_id=current_user.id,
            status=models.OrderStatus.CREATED,
            promo_code_id=promo_code.id if promo_code else None,
            total_amount=total_amount - discount_amount,
            discount_amount=discount_amount
        )
        db.add(order)
        db.flush()
        
        # Создание позиций заказа и резервирование
        for product, item in products:
            order_item = models.OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=item.quantity,
                price_at_order=product.price
            )
            db.add(order_item)
            
            # Резервирование
            product.stock -= item.quantity
        
        # Запись операции
        operation = models.UserOperation(
            user_id=current_user.id,
            operation_type=models.OperationType.CREATE_ORDER
        )
        db.add(operation)
        
        db.commit()
        db.refresh(order)
        
        order_items = db.query(models.OrderItem).filter(models.OrderItem.order_id == order.id).all()
        items_response = []
        for item in order_items:
            items_response.append({
                'product_id': str(item.product_id),
                'quantity': item.quantity,
                'price_at_order': float(item.price_at_order)
            })
                
        return OrderResponse(
            id=str(order.id),
            user_id=str(order.user_id),
            status=order.status.value,
            items=items_response,
            promo_code=order_data.promo_code,
            total_amount=float(order.total_amount),
            discount_amount=float(order.discount_amount),
            created_at=order.created_at.isoformat(),
            updated_at=order.updated_at.isoformat() if order.updated_at else None
        )
        
    except Exception as e:
        db.rollback()
        raise e

@app.get("/api/v1/orders/{id}", response_model=OrderResponse)
async def get_order(
    id: str,
    db: Session = Depends(get_db),
    current_user = Depends(require_role([models.UserRole.USER, models.UserRole.ADMIN]))
):
    try:
        order_id = uuid.UUID(id)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail={'code': 'ORDER_NOT_FOUND', 'message': 'Order not found'}
        )
    
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    
    if not order:
        raise HTTPException(
            status_code=404,
            detail={'code': 'ORDER_NOT_FOUND', 'message': f'Order with id {id} not found'}
        )
    
    # Проверка прав
    if current_user.role == models.UserRole.USER and order.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail={'code': 'ORDER_OWNERSHIP_VIOLATION', 'message': 'Order belongs to another user'}
        )
    
    items_response = []
    for item in order.items:
        items_response.append({
            'product_id': str(item.product_id),
            'quantity': item.quantity,
            'price_at_order': float(item.price_at_order)
        })
    
    promo_code = None
    if order.promo_code_id:
        promo = db.query(models.PromoCode).filter(models.PromoCode.id == order.promo_code_id).first()
        if promo:
            promo_code = promo.code
    
    return OrderResponse(
        id=str(order.id),
        user_id=str(order.user_id),
        status=order.status.value,
        items=items_response,
        promo_code=promo_code,
        total_amount=float(order.total_amount),
        discount_amount=float(order.discount_amount),
        created_at=order.created_at.isoformat(),
        updated_at=order.updated_at.isoformat() if order.updated_at else None
    )

@app.put("/api/v1/orders/{id}", response_model=OrderResponse)
async def update_order(
    id: str,
    order_data: dict,  # В реальном проекте использовать сгенерированную модель
    db: Session = Depends(get_db),
    current_user = Depends(require_role([models.UserRole.USER, models.UserRole.ADMIN]))
):
    try:
        order_id = uuid.UUID(id)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail={'code': 'ORDER_NOT_FOUND', 'message': 'Order not found'}
        )
    
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    
    if not order:
        raise HTTPException(
            status_code=404,
            detail={'code': 'ORDER_NOT_FOUND', 'message': f'Order with id {id} not found'}
        )
    
    # Проверка владельца
    if current_user.role == models.UserRole.USER and order.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail={'code': 'ORDER_OWNERSHIP_VIOLATION', 'message': 'Order belongs to another user'}
        )
    
    # Проверка состояния
    if order.status != models.OrderStatus.CREATED:
        raise HTTPException(
            status_code=409,
            detail={'code': 'INVALID_STATE_TRANSITION', 'message': 'Order can only be updated in CREATED state'}
        )
    
    # Проверка частоты обновления
    last_update = db.query(models.UserOperation).filter(
        models.UserOperation.user_id == current_user.id,
        models.UserOperation.operation_type == models.OperationType.UPDATE_ORDER
    ).order_by(models.UserOperation.created_at.desc()).first()
    
    if last_update:
        cooldown = datetime.utcnow() - last_update.created_at.replace(tzinfo=None)
        if cooldown.total_seconds() < settings.ORDER_UPDATE_COOLDOWN_MINUTES * 60:
            raise HTTPException(
                status_code=429,
                detail={'code': 'ORDER_LIMIT_EXCEEDED', 'message': 'Too many order update attempts'}
            )
    
    # Начинаем транзакцию
    try:
        # Возврат предыдущих остатков
        for item in order.items:
            product = db.query(models.Product).filter(models.Product.id == item.product_id).first()
            if product:
                product.stock += item.quantity
        
        # Удаляем старые позиции
        db.query(models.OrderItem).filter(models.OrderItem.order_id == order.id).delete()
        
        # Проверка новых позиций
        insufficient_stock = []
        products = []
        
        for item in order_data['items']:
            product = db.query(models.Product).filter(models.Product.id == item['product_id']).first()
            
            if not product:
                raise HTTPException(
                    status_code=404,
                    detail={'code': 'PRODUCT_NOT_FOUND', 'message': f'Product {item["product_id"]} not found'}
                )
            
            if product.status != models.ProductStatus.ACTIVE:
                raise HTTPException(
                    status_code=409,
                    detail={'code': 'PRODUCT_INACTIVE', 'message': f'Product {item["product_id"]} is not active'}
                )
            
            if product.stock < item['quantity']:
                insufficient_stock.append({
                    'product_id': str(item['product_id']),
                    'requested': item['quantity'],
                    'available': product.stock
                })
            
            products.append((product, item))
        
        if insufficient_stock:
            raise HTTPException(
                status_code=409,
                detail={
                    'code': 'INSUFFICIENT_STOCK',
                    'message': 'Insufficient stock for some products',
                    'details': {'products': insufficient_stock}
                }
            )
        
        # Пересчет стоимости
        total_amount = 0
        for product, item in products:
            total_amount += float(product.price) * item['quantity']
            product.stock -= item['quantity']
        
        # Пересчет скидки
        discount_amount = 0
        if order.promo_code_id:
            promo_code = db.query(models.PromoCode).filter(models.PromoCode.id == order.promo_code_id).first()
            if promo_code:
                if total_amount >= float(promo_code.min_order_amount):
                    if promo_code.discount_type == models.DiscountType.PERCENTAGE:
                        discount = total_amount * float(promo_code.discount_value) / 100
                        discount = min(discount, total_amount * 0.7)
                    else:
                        discount = min(float(promo_code.discount_value), total_amount)
                    discount_amount = discount
                else:
                    # Скидка больше не применима
                    order.promo_code_id = None
                    promo_code.current_uses -= 1
        
        # Создание новых позиций
        for product, item in products:
            order_item = models.OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=item['quantity'],
                price_at_order=product.price
            )
            db.add(order_item)
        
        # Обновление заказа
        order.total_amount = total_amount - discount_amount
        order.discount_amount = discount_amount
        
        # Запись операции
        operation = models.UserOperation(
            user_id=current_user.id,
            operation_type=models.OperationType.UPDATE_ORDER
        )
        db.add(operation)
        
        db.commit()
        db.refresh(order)
        
        # Формирование ответа
        items_response = []
        for item in order.items:
            items_response.append({
                'product_id': str(item.product_id),
                'quantity': item.quantity,
                'price_at_order': float(item.price_at_order)
            })
        
        promo_code = None
        if order.promo_code_id:
            promo = db.query(models.PromoCode).filter(models.PromoCode.id == order.promo_code_id).first()
            if promo:
                promo_code = promo.code
        
        return OrderResponse(
            id=str(order.id),
            user_id=str(order.user_id),
            status=order.status.value,
            items=items_response,
            promo_code=promo_code,
            total_amount=float(order.total_amount),
            discount_amount=float(order.discount_amount),
            created_at=order.created_at.isoformat(),
            updated_at=order.updated_at.isoformat() if order.updated_at else None
        )
        
    except Exception as e:
        db.rollback()
        raise e

@app.post("/api/v1/orders/{id}/cancel", response_model=OrderResponse)
async def cancel_order(
    id: str,
    db: Session = Depends(get_db),
    current_user = Depends(require_role([models.UserRole.USER, models.UserRole.ADMIN]))
):
    try:
        order_id = uuid.UUID(id)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail={'code': 'ORDER_NOT_FOUND', 'message': 'Order not found'}
        )
    
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    
    if not order:
        raise HTTPException(
            status_code=404,
            detail={'code': 'ORDER_NOT_FOUND', 'message': f'Order with id {id} not found'}
        )
    
    # Проверка владельца
    if current_user.role == models.UserRole.USER and order.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail={'code': 'ORDER_OWNERSHIP_VIOLATION', 'message': 'Order belongs to another user'}
        )
    
    # Проверка состояния
    if order.status not in [models.OrderStatus.CREATED, models.OrderStatus.PAYMENT_PENDING]:
        raise HTTPException(
            status_code=409,
            detail={'code': 'INVALID_STATE_TRANSITION', 'message': f'Order cannot be cancelled from {order.status.value} state'}
        )
    
    # Начинаем транзакцию
    try:
        # Возврат остатков
        # Получаем позиции заказа из БД
        order_items = db.query(models.OrderItem).filter(models.OrderItem.order_id == order.id).all()

        # Возврат остатков
        for item in order_items:
            product = db.query(models.Product).filter(models.Product.id == item.product_id).first()            
            if product:
                product.stock += item.quantity
        
        # Возврат использования промокода
        if order.promo_code_id:
            promo_code = db.query(models.PromoCode).filter(models.PromoCode.id == order.promo_code_id).first()
            if promo_code:
                promo_code.current_uses -= 1
        
        # Изменение статуса
        order.status = models.OrderStatus.CANCELED
        
        db.commit()
        db.refresh(order)
        
        # Формирование ответа
        items_response = []
        for item in order_items:
            items_response.append({
                'product_id': str(item.product_id),
                'quantity': item.quantity,
                'price_at_order': float(item.price_at_order)
            })
        promo_code = None
        if order.promo_code_id:
            promo = db.query(models.PromoCode).filter(models.PromoCode.id == order.promo_code_id).first()
            if promo:
                promo_code = promo.code
        
        return OrderResponse(
            id=str(order.id),
            user_id=str(order.user_id),
            status=order.status.value,
            items=items_response,
            promo_code=promo_code,
            total_amount=float(order.total_amount),
            discount_amount=float(order.discount_amount),
            created_at=order.created_at.isoformat(),
            updated_at=order.updated_at.isoformat() if order.updated_at else None
        )
        
    except Exception as e:
        db.rollback()
        raise e