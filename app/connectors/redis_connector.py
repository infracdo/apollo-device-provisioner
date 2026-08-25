"""
Redis Connector

Redis connection handler using redis-py.
"""
import asyncio
from typing import Any, Dict, Optional

import redis
from redis.exceptions import RedisError

from app.utils.logging import logger
from app.config import settings


class RedisConnector:
    """Redis connection handler"""

    def __init__(
        self,
        host: str,
        port: int = 6379,
        username: str = "",
        password: str = "",
        db: int = 0,
        timeout: int = 30,
        ssl: bool = False,
    ):
        """Initialize Redis connector"""
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.db = db
        self.timeout = timeout
        self.ssl = ssl

        self.client: Optional[redis.Redis] = None
        self.is_connected = False

    async def connect(self) -> bool:
        """Establish Redis connection"""
        try:
            # Use run_in_executor for Python 3.8 compatibility
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._connect_sync)

            self.is_connected = True
            logger.info(
                f"Redis connected to {self.host}:{self.port}/{self.db}"
            )
            return True

        except Exception as e:
            logger.error(
                f"Redis connection failed to "
                f"{self.host}:{self.port}/{self.db} - {str(e)}"
            )
            logger.exception("Full traceback:")
            self.is_connected = False
            return False

    def _connect_sync(self):
        """Synchronous connection method"""
        self.client = redis.Redis(
            host=self.host,
            port=self.port,
            username=self.username or None,
            password=self.password or None,
            db=self.db,
            socket_connect_timeout=self.timeout,
            socket_timeout=self.timeout,
            ssl=self.ssl,
            decode_responses=True,
        )

        # Verify that the connection is actually available.
        self.client.ping()

    async def disconnect(self) -> bool:
        """Close Redis connection"""
        try:
            if self.client:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._disconnect_sync)

            self.client = None
            self.is_connected = False

            logger.info(
                f"Redis disconnected from {self.host}:{self.port}/{self.db}"
            )
            return True

        except Exception as e:
            logger.error(f"Error disconnecting Redis: {str(e)}")
            self.is_connected = False
            return False

    def _disconnect_sync(self):
        """Synchronous disconnect method"""
        if self.client:
            self.client.close()

    async def execute(
        self,
        command: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Execute Redis command.

        Args:
            command: Redis command/method name.
            *args: Positional arguments for the Redis command.
            **kwargs: Keyword arguments for the Redis command.

        Returns:
            Any: Result returned by the Redis command.

        Example:
            await connector.execute("set", "key", "value")
            await connector.execute("get", "key")
            await connector.execute("delete", "key")
        """
        if not self.is_connected or not self.client:
            raise ConnectionError("Not connected to Redis")

        try:
            redis_command = getattr(self.client, command, None)

            if not redis_command or not callable(redis_command):
                raise ValueError(f"Unsupported Redis command: {command}")

            # Run blocking redis-py operation outside the event loop.
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: redis_command(*args, **kwargs),
            )

            return result

        except RedisError as e:
            logger.error(
                f"Redis command '{command}' failed: {str(e)}"
            )
            raise

        except Exception as e:
            logger.error(
                f"Error executing Redis command '{command}': {str(e)}"
            )
            raise

    async def ping(self) -> bool:
        """Check Redis server connectivity"""
        if not self.is_connected or not self.client:
            return False

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self.client.ping,
            )
            return bool(result)

        except RedisError as e:
            logger.error(f"Redis ping failed: {str(e)}")
            self.is_connected = False
            return False

        except Exception as e:
            logger.error(f"Error pinging Redis: {str(e)}")
            return False

    async def get(self, key: str) -> Optional[str]:
        """Get value from Redis"""
        return await self.execute("get", key)

    async def set(
        self,
        key: str,
        value: Any,
        expiration: Optional[int] = None,
    ) -> bool:
        """
        Set value in Redis.

        Args:
            key: Redis key.
            value: Value to store.
            expiration: Optional expiration in seconds.
        """
        if expiration is not None:
            return bool(
                await self.execute(
                    "set",
                    key,
                    value,
                    ex=expiration,
                )
            )

        return bool(
            await self.execute(
                "set",
                key,
                value,
            )
        )

    async def delete(self, *keys: str) -> int:
        """Delete one or more Redis keys"""
        return int(await self.execute("delete", *keys))

    async def exists(self, *keys: str) -> int:
        """Check whether Redis keys exist"""
        return int(await self.execute("exists", *keys))

    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiration on a Redis key"""
        return bool(
            await self.execute(
                "expire",
                key,
                seconds,
            )
        )

    async def hgetall(self, key: str) -> Dict[str, str]:
        """Get all fields and values from a Redis hash."""
        result = await self.execute("hgetall", key)
        return result or {}