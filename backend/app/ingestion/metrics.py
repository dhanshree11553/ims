import asyncio
import logging
import time

logger = logging.getLogger(__name__)

_accepted_window: list[float] = []
_processed_window: list[float] = []
_lock = asyncio.Lock()


async def record_accepted():
    async with _lock:
        _accepted_window.append(time.monotonic())


async def record_processed():
    async with _lock:
        _processed_window.append(time.monotonic())


async def metrics_loop(interval_sec: int = 5):
    while True:
        await asyncio.sleep(interval_sec)
        now = time.monotonic()
        cutoff = now - interval_sec
        async with _lock:
            global _accepted_window, _processed_window
            _accepted_window = [t for t in _accepted_window if t >= cutoff]
            _processed_window = [t for t in _processed_window if t >= cutoff]
            a = len(_accepted_window)
            p = len(_processed_window)
        logger.info(
            "IMS throughput (last %ss): accepted=%.1f signals/s processed=%.1f signals/s",
            interval_sec,
            a / interval_sec,
            p / interval_sec,
        )
