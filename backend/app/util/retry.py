import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")
logger = logging.getLogger(__name__)


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = 4,
    base_delay_sec: float = 0.15,
    operation: str = "db_write",
) -> T:
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            return await fn()
        except Exception as e:
            last_exc = e
            if i == attempts - 1:
                logger.exception("%s failed after %s attempts", operation, attempts)
                raise
            delay = base_delay_sec * (2**i)
            logger.warning("%s attempt %s failed: %s; retry in %ss", operation, i + 1, e, delay)
            await asyncio.sleep(delay)
    raise RuntimeError(last_exc)  # pragma: no cover
