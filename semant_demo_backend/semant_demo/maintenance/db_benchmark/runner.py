"""Closed-loop load at a fixed concurrency, paced by a global start-rate limit, with a cap on
requests and seconds per point. Latencies are client-side wall time of one request."""
import asyncio
import math
import time
from dataclasses import dataclass, field

from semant_demo.maintenance.db_benchmark.workload import Request, short_hash


def percentile(sorted_values: list[float], q: float) -> float | None:
    """Nearest-rank percentile of already sorted values."""
    if not sorted_values:
        return None
    return sorted_values[max(0, math.ceil(q * len(sorted_values)) - 1)]


@dataclass
class PointResult:
    concurrency: int
    requests: int = 0
    ok: int = 0
    errors: dict[str, int] = field(default_factory=dict)
    timeouts: int = 0
    wall_seconds: float = 0.0
    latencies: list[float] = field(default_factory=list)
    stopped_by: str = "requests"
    results: dict[int, list[str]] = field(default_factory=dict)
    """Hashed result ids of the first execution of each input index (for overlap checks)."""
    hits: int = 0
    """Requests that returned at least one id (self_recall: chunks found by their own vector)."""

    def summary(self) -> dict:
        lat = sorted(self.latencies)
        ms = lambda v: round(v * 1000, 1) if v is not None else None  # noqa: E731
        return {
            "concurrency": self.concurrency, "requests": self.requests, "ok": self.ok,
            "errors": self.errors, "error_count": sum(self.errors.values()), "timeouts": self.timeouts,
            "wall_seconds": round(self.wall_seconds, 2), "stopped_by": self.stopped_by,
            "throughput_rps": round(self.ok / self.wall_seconds, 2) if self.wall_seconds else None,
            "latency_ms": {"min": ms(lat[0] if lat else None), "p50": ms(percentile(lat, 0.5)),
                           "p95": ms(percentile(lat, 0.95)),
                           "p99": ms(percentile(lat, 0.99)) if len(lat) >= 100 else None,
                           "max": ms(lat[-1] if lat else None),
                           "mean": ms(sum(lat) / len(lat) if lat else None)},
            "hit_requests": self.hits,
        }


class Pacer:
    """Spaces request starts at least ``1 / max_qps`` seconds apart across all workers."""

    def __init__(self, max_qps: float):
        if not max_qps > 0:
            raise ValueError("max_qps must be positive")
        self.interval = 1.0 / max_qps
        self.next = time.monotonic()
        self.lock = asyncio.Lock()

    async def wait(self, deadline: float) -> bool:
        """Waits for the next start slot; False (without waiting) when that slot is at or past ``deadline``."""
        async with self.lock:
            now = time.monotonic()
            slot = max(now, self.next)
            if slot >= deadline:
                return False
            self.next = slot + self.interval
        if slot > now:
            await asyncio.sleep(slot - now)
        return True


async def run_point(request: Request, concurrency: int, requests: int, max_seconds: float, timeout: float,
                    max_qps: float, start_index: int = 0, keep_results: bool = False) -> PointResult:
    if concurrency < 1 or requests < 1 or not (max_seconds > 0 and timeout > 0):
        raise ValueError("concurrency, requests, max_seconds and timeout must be positive")
    result = PointResult(concurrency=concurrency)
    pacer = Pacer(max_qps)
    issued = 0
    start = time.monotonic()
    deadline = start + max_seconds

    async def worker() -> None:
        nonlocal issued
        while True:
            if issued >= requests:
                return
            index = start_index + issued
            issued += 1
            # No request starts at or after the deadline, also when the pacer delayed this one.
            if time.monotonic() >= deadline or not await pacer.wait(deadline):
                result.stopped_by = "time"
                return
            t0 = time.perf_counter()
            try:
                ids = await asyncio.wait_for(request(index), timeout)
            except asyncio.TimeoutError:
                result.timeouts += 1
                result.errors["timeout"] = result.errors.get("timeout", 0) + 1
                continue
            except Exception as e:  # recorded, never raised: one failure must not stop the run
                name = type(e).__name__
                result.errors[name] = result.errors.get(name, 0) + 1
                continue
            finally:
                result.requests += 1
            result.latencies.append(time.perf_counter() - t0)
            result.ok += 1
            result.hits += bool(ids)
            if keep_results and index not in result.results:
                result.results[index] = [short_hash(i) for i in ids]

    await asyncio.gather(*(worker() for _ in range(concurrency)))
    result.wall_seconds = time.monotonic() - start
    return result
