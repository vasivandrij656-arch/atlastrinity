"""AtlasTrinity State Manager

Redis-based state persistence for:
- Surviving restarts
- Checkpointing task progress
- Session recovery
"""

import asyncio
import json
import os
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    import redis.asyncio as aioredis
    from redis.asyncio import Redis as AsyncRedis
else:
    try:
        import redis.asyncio as aioredis
        from redis.asyncio import Redis as AsyncRedis
    except ImportError:
        aioredis = None
        AsyncRedis = None

from src.brain.monitoring.logger import logger


class StateManager:
    """Manages orchestrator state persistence using Redis.

    Features:
    - Save/restore task state
    - Checkpointing during execution
    - Session recovery after restart
    """

    redis_client: AsyncRedis | None

    def __init__(self, host: str = "localhost", port: int = 6379, prefix: str = "atlastrinity"):
        from src.brain.config.config_loader import config

        self.prefix = prefix
        self.available = False
        self._publish_ready = False  # Only True after Redis connection is verified
        self._publish_fail_count = 0  # Track consecutive publish failures

        if aioredis is None:
            logger.warning("[STATE] Redis not installed. Running without persistence.")
            return

        # Priority: EnvVar > Config > Default Host/Port
        redis_url = os.getenv("REDIS_URL") or config.get("state.redis_url")

        if redis_url:
            self.redis_client = aioredis.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
            )
            logger.info("[STATE] Redis connected via URL")
        else:
            self.redis_client = aioredis.Redis(
                host=host,
                port=port,
                decode_responses=True,
                socket_connect_timeout=2,
            )
            logger.info(f"[STATE] Redis connected at {host}:{port}")

        # Connection will be tested lazily or in initialize
        self.available = True

    async def initialize(self):
        """Test Redis connection and enable event publishing.

        Called after ensure_redis() confirms Redis is running.
        """
        if not self.available or self.redis_client is None or AsyncRedis is None:
            return
        try:
            await self.redis_client.ping()  # type: ignore [not-async]
            self._publish_ready = True
            logger.info("[STATE] Redis publish channel ready.")
        except Exception as e:
            logger.warning(f"[STATE] Redis ping failed during initialize: {e}")
            self._publish_ready = False

    def _key(self, name: str) -> str:
        return f"{self.prefix}:{name}"

    async def save_session(self, session_id: str, state: dict):
        """Persist session state to Redis"""
        if not self.available or self.redis_client is None:
            return
        try:
            key = self._key(f"session:{session_id}")
            # Ensure state is JSON serializable
            await self.redis_client.set(key, json.dumps(state, default=str))
            # Also update last session pointer
            await self.redis_client.set(self._key("last_session"), session_id)
            logger.info(f"[STATE] Session {session_id} saved")
        except Exception as e:
            logger.error(f"[STATE] Failed to save session: {e}")

    async def restore_session(self, session_id: str) -> dict | None:
        """Retrieve session state from Redis"""
        if not self.available or self.redis_client is None:
            return None
        try:
            key = self._key(f"session:{session_id}")
            data = await self.redis_client.get(key)
            if data:
                return cast("dict[Any, Any] | None", json.loads(data))
            return None
        except Exception as e:
            logger.error(f"[STATE] Failed to restore session: {e}")
            return None

    async def list_sessions(self) -> list[dict]:
        """List all available sessions"""
        if not self.available or self.redis_client is None:
            return []
        try:
            pattern = self._key("session:*")
            keys = await self.redis_client.keys(pattern)
            sessions = []
            for k in keys:
                # Key is byte if decode_responses=False, but we set it True
                s_id = k.split(":")[-1]
                sessions.append({"id": s_id, "key": k})
            return sessions
        except Exception as e:
            logger.error(f"[STATE] Failed to list sessions: {e}")
            return []

    async def delete_session(self, session_id: str):
        """Remove a session from persistence"""
        if not self.available or self.redis_client is None:
            return
        try:
            key = self._key(f"session:{session_id}")
            await self.redis_client.delete(key)
        except Exception as e:
            logger.error(f"[STATE] Failed to delete session: {e}")

    async def clear_session(self, session_id: str):
        """Alias for delete_session for compatibility"""
        await self.delete_session(session_id)

    async def checkpoint(self, session_id: str, step_id: Any, result: Any):
        """Save partial progress during a task"""
        if not self.available or self.redis_client is None:
            return
        try:
            key = self._key(f"checkpoint:{session_id}")
            checkpoint_data = {
                "last_step": step_id,
                "timestamp": datetime.now().isoformat(),
                "result": result,
            }
            await self.redis_client.set(key, json.dumps(checkpoint_data, default=str))
        except Exception as e:
            logger.error(f"[STATE] Checkpoint failed: {e}")

    async def get_last_checkpoint(self, session_id: str) -> dict | None:
        """Get the last successful checkpoint for a session"""
        if not self.available or self.redis_client is None:
            return None
        try:
            key = self._key(f"checkpoint:{session_id}")
            data = await self.redis_client.get(key)  # type: ignore
            if data:
                return cast("dict[Any, Any] | None", json.loads(data))
            return None
        except Exception as e:
            logger.error(f"[STATE] Failed to get checkpoint: {e}")
            return None

    async def set_current_task(self, task_id: str, metadata: dict):
        """Store info about the currently active task"""
        if not self.available or self.redis_client is None:
            return
        try:
            key = self._key("active_task")
            data = {"id": task_id, "metadata": metadata, "started": datetime.now().isoformat()}
            await self.redis_client.set(key, json.dumps(data, default=str))  # type: ignore
        except Exception as e:
            logger.error(f"[STATE] Failed to set active task: {e}")

    async def get_current_task(self) -> dict | None:
        """Get info about the currently active task"""
        if not self.available or self.redis_client is None:
            return None
        try:
            key = self._key("active_task")
            data = await self.redis_client.get(key)  # type: ignore
            if data:
                return cast("dict[Any, Any] | None", json.loads(data))
            return None
        except Exception as e:
            logger.error(f"[STATE] Failed to get active task: {e}")
            return None

    async def clear_active_task(self):
        """Clear the active task flag"""
        if not self.available or self.redis_client is None:
            return
        try:
            await self.redis_client.delete(self._key("active_task"))  # type: ignore
        except Exception as e:
            logger.error(f"[STATE] Failed to clear active task: {e}")

    async def publish_event(self, channel: str, message: dict):
        """Publish a message to a Redis channel (Pub/Sub)"""
        if not self._publish_ready or not self.available or self.redis_client is None:
            # Periodically attempt to recover if Redis gets healthy again
            if self.available and self.redis_client is not None and self._publish_fail_count > 0:
                self._publish_ready = True  # Try again
            else:
                return
        try:
            # Check if event loop is running before awaiting
            try:
                loop = asyncio.get_running_loop()
                if not loop.is_running() or loop.is_closed():
                    return
            except RuntimeError:
                # No running loop, cannot publish async event
                return

            full_channel = self._key(f"events:{channel}")
            await self.redis_client.publish(full_channel, json.dumps(message, default=str))  # type: ignore
            
            if self._publish_fail_count > 0:
                logger.info("[STATE] Redis pub/sub recovered from previous failures.")
            self._publish_fail_count = 0  # Reset on success
            
        except Exception as e:
            # Avoid logging if it's just a loop closure error
            if "Event loop is closed" not in str(e):
                self._publish_fail_count += 1
                if self._publish_fail_count <= 3:  # Allow 3 strikes before giving up logging
                    logger.warning(f"[STATE] Redis publish failed (attempt {self._publish_fail_count}), backing off: {e}")
                
                # Do NOT permanently disable. Just mark as temporarily unhealthy.
                if self._publish_fail_count >= 3:
                    self._publish_ready = False

    async def get_key(self, key: str) -> Any | None:
        """Get a raw key value with prefix"""
        if not self.available or self.redis_client is None:
            return None
        try:
            full_key = self._key(key)
            return await self.redis_client.get(full_key)
        except Exception as e:
            logger.error(f"[STATE] Failed to get key {key}: {e}")
            return None


# Singleton instance
state_manager = StateManager()
