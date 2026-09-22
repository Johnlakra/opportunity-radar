import redis
from .config import settings

r = redis.from_url(settings.redis_url, decode_responses=True)
