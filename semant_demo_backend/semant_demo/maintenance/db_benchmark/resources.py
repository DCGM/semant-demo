"""Nonprivileged resource observations: cgroup v2 of the Weaviate container and host /proc files.

Every reader returns None when its source is missing or unreadable; the reports mark such
metrics as unavailable. Nothing here needs root or changes system state. ``docker inspect``
is used only to find a container's cgroup, and only when a container name is given.
"""
import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CGROUP_ROOT = Path("/sys/fs/cgroup")
ZFS_ARCSTATS = Path("/proc/spl/kstat/zfs/arcstats")


def _read(path: Path) -> str | None:
    try:
        return path.read_text()
    except OSError:
        return None


def _key_values(text: str | None) -> dict[str, int]:
    values = {}
    for line in (text or "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].isdigit():
            values[parts[0].rstrip(":")] = int(parts[1])
    return values


def container_cgroup(container: str) -> tuple[Path | None, str | None]:
    """The cgroup v2 directory of a running Docker container, or (None, reason)."""
    try:
        out = subprocess.run(["docker", "inspect", "-f", "{{.Id}} {{.State.Pid}}", container],
                             capture_output=True, text=True, timeout=10, check=True).stdout.split()
    except (OSError, subprocess.SubprocessError) as e:
        return None, f"docker inspect failed: {type(e).__name__}"
    container_id, pid = out[0], out[1]
    for candidate in (CGROUP_ROOT / "system.slice" / f"docker-{container_id}.scope",
                      CGROUP_ROOT / "docker" / container_id):
        if (candidate / "memory.current").exists():
            return candidate, None
    cgroup = _read(Path(f"/proc/{pid}/cgroup"))
    if cgroup and cgroup.startswith("0::"):
        candidate = CGROUP_ROOT / cgroup.strip()[3:].lstrip("/")
        if (candidate / "memory.current").exists():
            return candidate, None
    return None, "cgroup v2 directory not found or not readable"


def container_config(container: str) -> dict[str, Any] | None:
    """Memory/CPU limits, restart count, start time and image of a container (no environment:
    it may hold credentials)."""
    try:
        out = subprocess.run(["docker", "inspect", container], capture_output=True, text=True,
                             timeout=10, check=True).stdout
        info = json.loads(out)[0]
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None
    host = info.get("HostConfig", {})
    return {
        "image": info.get("Config", {}).get("Image"),
        "started_at": info.get("State", {}).get("StartedAt"),
        "restart_count": info.get("RestartCount"),
        "memory_limit_bytes": host.get("Memory") or None,
        "memory_swap_limit_bytes": host.get("MemorySwap") or None,
        "nano_cpus": host.get("NanoCpus") or None,
        "cpuset": host.get("CpusetCpus") or None,
        "mounts": [{"destination": m.get("Destination"), "type": m.get("Type")} for m in info.get("Mounts", [])],
    }


def cgroup_snapshot(cgroup: Path | None) -> dict[str, Any] | None:
    if cgroup is None:
        return None
    memory_stat = _key_values(_read(cgroup / "memory.stat"))
    cpu_stat = _key_values(_read(cgroup / "cpu.stat"))
    current = _read(cgroup / "memory.current")
    if current is None:
        return None
    io = {"rbytes": 0, "wbytes": 0, "rios": 0, "wios": 0}
    for line in (_read(cgroup / "io.stat") or "").splitlines():
        for item in line.split()[1:]:
            key, _, value = item.partition("=")
            if key in io and value.isdigit():
                io[key] += int(value)
    peak = _read(cgroup / "memory.peak")
    limit = _read(cgroup / "memory.max")
    events = _key_values(_read(cgroup / "memory.events"))
    return {
        "memory_current": int(current),
        "memory_peak": int(peak) if peak and peak.strip().isdigit() else None,
        "memory_max": int(limit) if limit and limit.strip().isdigit() else None,
        "anon": memory_stat.get("anon"),
        "file": memory_stat.get("file"),
        "file_mapped": memory_stat.get("file_mapped"),
        "cpu_usage_usec": cpu_stat.get("usage_usec"),
        "oom_events": events.get("oom"),
        "oom_kill_events": events.get("oom_kill"),
        "io": io,
    }


def _arcstats() -> dict[str, int]:
    """ZFS ARC counters ('name type value' lines); empty without ZFS."""
    values = {}
    for line in (_read(ZFS_ARCSTATS) or "").splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2].isdigit():
            values[parts[0]] = int(parts[2])
    return values


def _pressure(kind: str) -> dict[str, float] | None:
    text = _read(Path(f"/proc/pressure/{kind}"))
    if text is None:
        return None
    result = {}
    for line in text.splitlines():
        scope, *items = line.split()
        for item in items:
            key, _, value = item.partition("=")
            if key == "avg10":
                result[scope] = float(value)
    return result


def host_snapshot() -> dict[str, Any]:
    meminfo = {k: v * 1024 for k, v in _key_values(_read(Path("/proc/meminfo"))).items()}
    arc = _arcstats()
    return {
        "mem_total": meminfo.get("MemTotal"),
        "mem_available": meminfo.get("MemAvailable"),
        "cached": meminfo.get("Cached"),
        "anon_pages": meminfo.get("AnonPages"),
        "swap_total": meminfo.get("SwapTotal"),
        "swap_free": meminfo.get("SwapFree"),
        "zfs_arc_size": arc.get("size"),
        "zfs_arc_max": arc.get("c_max"),
        "pressure_memory_avg10": _pressure("memory"),
        "pressure_io_avg10": _pressure("io"),
        "pressure_cpu_avg10": _pressure("cpu"),
        "loadavg": [float(x) for x in (_read(Path("/proc/loadavg")) or "0 0 0").split()[:3]],
        "cpu_count": os.cpu_count(),
    }


def disk_usage(path: str) -> dict[str, int] | None:
    try:
        stat = os.statvfs(path)
    except OSError:
        return None
    return {"total": stat.f_blocks * stat.f_frsize, "free": stat.f_bavail * stat.f_frsize}


@dataclass
class Window:
    """Aggregates of the samples taken while one benchmark point ran."""
    samples: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any] | None:
        cg = [s["cgroup"] for s in self.samples if s.get("cgroup")]
        hosts = [s["host"] for s in self.samples]
        if not self.samples:
            return None
        elapsed = self.samples[-1]["t"] - self.samples[0]["t"]
        result: dict[str, Any] = {"samples": len(self.samples)}
        if len(cg) >= 2 and elapsed > 0:
            first, last = cg[0], cg[-1]
            if first["cpu_usage_usec"] is not None:
                result["cpu_cores_avg"] = round((last["cpu_usage_usec"] - first["cpu_usage_usec"]) / 1e6 / elapsed, 2)
            result["memory_current_max"] = max(s["memory_current"] for s in cg)
            result["anon_max"] = max(s["anon"] or 0 for s in cg)
            result["file_cache_min"] = min(s["file"] or 0 for s in cg)
            result["io_read_bytes"] = last["io"]["rbytes"] - first["io"]["rbytes"]
            result["io_read_ops"] = last["io"]["rios"] - first["io"]["rios"]
            result["io_write_bytes"] = last["io"]["wbytes"] - first["io"]["wbytes"]
            result["oom_kill_events"] = (last["oom_kill_events"] or 0) - (first["oom_kill_events"] or 0)
        avail = [h["mem_available"] for h in hosts if h.get("mem_available") is not None]
        if avail:
            result["host_mem_available_min"] = min(avail)
        for kind in ("memory", "io"):
            values = [(h.get(f"pressure_{kind}_avg10") or {}).get("some") for h in hosts]
            values = [v for v in values if v is not None]
            if values:
                result[f"host_pressure_{kind}_some_avg10_max"] = max(values)
        return result


class ResourceSampler:
    """Samples the cgroup and host files every ``interval`` seconds in a background thread.

    ``window()`` starts a new aggregation window and returns the previous one's summary.
    """

    def __init__(self, cgroup: Path | None, interval: float = 1.0):
        self.cgroup = cgroup
        self.interval = interval
        self._window = Window()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def _sample(self) -> dict[str, Any]:
        return {"t": time.monotonic(), "cgroup": cgroup_snapshot(self.cgroup), "host": host_snapshot()}

    def _loop(self) -> None:
        while not self._stop.is_set():
            sample = self._sample()
            with self._lock:
                self._window.samples.append(sample)
            self._stop.wait(self.interval)

    def start(self) -> "ResourceSampler":
        self._thread.start()
        return self

    def window(self) -> dict[str, Any] | None:
        sample = self._sample()
        with self._lock:
            self._window.samples.append(sample)
            summary = self._window.summary()
            self._window = Window(samples=[sample])
        return summary

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)
