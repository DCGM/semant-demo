"""Redis client for storing task status and progress."""
import redis
from config import config

redis_client = redis.Redis(
    host=config.REDIS_HOST,
    port=config.REDIS_PORT,
    decode_responses=True,
)
