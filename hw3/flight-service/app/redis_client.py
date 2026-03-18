import redis
from redis.sentinel import Sentinel
import json
import logging
import os
from typing import Optional, Any

logger = logging.getLogger(__name__)

class RedisCache:
    def __init__(self):
        # Получаем адреса sentinel из переменных окружения
        sentinel_hosts = [
            (os.getenv('REDIS_SENTINEL_HOST_1', 'redis-sentinel-1'), 
             int(os.getenv('REDIS_SENTINEL_PORT_1', 26379))),
            (os.getenv('REDIS_SENTINEL_HOST_2', 'redis-sentinel-2'), 
             int(os.getenv('REDIS_SENTINEL_PORT_2', 26380))),
            (os.getenv('REDIS_SENTINEL_HOST_3', 'redis-sentinel-3'), 
             int(os.getenv('REDIS_SENTINEL_PORT_3', 26381))),
        ]
        
        self.password = os.getenv('REDIS_PASSWORD', 'redispass')
        
        try:
            # Подключаемся к Sentinel
            self.sentinel = Sentinel(
                sentinel_hosts,
                password=self.password,
                socket_timeout=0.5
            )
            
            # Получаем мастер для записи
            self.master = self.sentinel.master_for(
                'mymaster',
                password=self.password,
                decode_responses=True
            )
            
            # Получаем реплику для чтения
            self.slave = self.sentinel.slave_for(
                'mymaster',
                password=self.password,
                decode_responses=True
            )
            
            logger.info(f"Connected to Redis Sentinel: {sentinel_hosts}")
            self.default_ttl = 300
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis Sentinel: {e}")
            # Fallback to direct connection (for development)
            self.fallback_client = redis.Redis(
                host=os.getenv('REDIS_HOST', 'redis-master'),
                port=int(os.getenv('REDIS_PORT', 6379)),
                password=self.password,
                decode_responses=True
            )
            self.master = self.fallback_client
            self.slave = self.fallback_client
            self.default_ttl = 300
    
    def get(self, key: str) -> Optional[Any]:
        """Чтение из реплики (или мастера если реплика недоступна)"""
        try:
            value = self.slave.get(key)
            if value:
                logger.info(f"CACHE HIT: {key}")
                return json.loads(value)
            logger.info(f"CACHE MISS: {key}")
            return None
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            try:
                # Пробуем прочитать из мастера
                value = self.master.get(key)
                if value:
                    logger.info(f"CACHE HIT (master): {key}")
                    return json.loads(value)
            except:
                pass
            return None
    
    def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """Запись в мастер"""
        try:
            self.master.setex(key, ttl or self.default_ttl, json.dumps(value, default=str))
            logger.info(f"CACHE SET: {key} (TTL: {ttl or self.default_ttl}s)")
            return True
        except Exception as e:
            logger.error(f"Redis set error: {e}")
            return False
    
    def delete(self, pattern: str) -> None:
        """Инвалидация кеша по паттерну"""
        try:
            keys = self.master.keys(pattern)
            if keys:
                self.master.delete(*keys)
                logger.info(f"CACHE INVALIDATED: {pattern} ({len(keys)} keys)")
        except Exception as e:
            logger.error(f"Redis delete error: {e}")
    
    def invalidate_flight(self, flight_id: int) -> None:
        """Инвалидация кеша рейса"""
        self.delete(f"flight:{flight_id}")
        self.delete("search:*")

redis_cache = RedisCache()