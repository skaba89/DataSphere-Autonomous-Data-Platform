"""
In-process Prometheus-compatible metrics for DataSphere API.
No external library required — generates text format manually.
"""
from __future__ import annotations
import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class _Histogram:
    """Simple histogram with fixed buckets."""
    buckets: list[float] = field(default_factory=lambda: [0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0])
    _counts: list[int] = field(default_factory=list)
    _sum: float = 0.0
    _total: int = 0

    def __post_init__(self):
        self._counts = [0] * len(self.buckets)

    def observe(self, value: float):
        self._sum += value
        self._total += 1
        for i, b in enumerate(self.buckets):
            if value <= b:
                self._counts[i] += 1


class MetricsCollector:
    """Thread-safe in-process metrics collector."""

    def __init__(self):
        self._lock = threading.Lock()
        self._start_time = time.time()

        # Counters: {label_tuple: count}
        self._http_requests_total: dict[tuple, int] = defaultdict(int)
        self._http_errors_total: dict[tuple, int] = defaultdict(int)
        self._jobs_created_total: dict[tuple, int] = defaultdict(int)
        self._jobs_completed_total: dict[tuple, int] = defaultdict(int)
        self._jobs_failed_total: dict[tuple, int] = defaultdict(int)
        self._generation_errors_total: dict[tuple, int] = defaultdict(int)

        # Histograms: {label_tuple: _Histogram}
        self._http_duration_seconds: dict[tuple, _Histogram] = defaultdict(_Histogram)
        self._generation_duration_seconds: dict[tuple, _Histogram] = defaultdict(_Histogram)

    def record_http_request(self, method: str, path: str, status: int, duration_s: float):
        key = (method, path, str(status))
        with self._lock:
            self._http_requests_total[key] += 1
            if status >= 400:
                self._http_errors_total[(method, path)] += 1
            self._http_duration_seconds[key].observe(duration_s)

    def record_job_created(self, mode: str = "explicit"):
        with self._lock:
            self._jobs_created_total[(mode,)] += 1

    def record_job_completed(self, mode: str = "explicit", duration_s: float = 0.0):
        with self._lock:
            self._jobs_completed_total[(mode,)] += 1
            self._generation_duration_seconds[(mode,)].observe(duration_s)

    def record_job_failed(self, mode: str = "explicit"):
        with self._lock:
            self._jobs_failed_total[(mode,)] += 1
            self._generation_errors_total[(mode,)] += 1

    def render(self) -> str:
        """Render metrics in Prometheus text format."""
        lines = []
        now = time.time()
        uptime = now - self._start_time

        with self._lock:
            # Process info
            lines += [
                "# HELP datasphere_up API uptime indicator",
                "# TYPE datasphere_up gauge",
                "datasphere_up 1",
                "# HELP datasphere_uptime_seconds Seconds since startup",
                "# TYPE datasphere_uptime_seconds gauge",
                f"datasphere_uptime_seconds {uptime:.2f}",
                "",
                # HTTP requests
                "# HELP datasphere_http_requests_total Total HTTP requests",
                "# TYPE datasphere_http_requests_total counter",
            ]
            for (method, path, status), count in self._http_requests_total.items():
                lines.append(f'datasphere_http_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}')

            lines += [
                "",
                "# HELP datasphere_http_request_duration_seconds HTTP request latency",
                "# TYPE datasphere_http_request_duration_seconds histogram",
            ]
            for (method, path, status), hist in self._http_duration_seconds.items():
                for i, b in enumerate(hist.buckets):
                    lines.append(f'datasphere_http_request_duration_seconds_bucket{{method="{method}",path="{path}",le="{b}"}} {hist._counts[i]}')
                lines.append(f'datasphere_http_request_duration_seconds_bucket{{method="{method}",path="{path}",le="+Inf"}} {hist._total}')
                lines.append(f'datasphere_http_request_duration_seconds_sum{{method="{method}",path="{path}"}} {hist._sum:.4f}')
                lines.append(f'datasphere_http_request_duration_seconds_count{{method="{method}",path="{path}"}} {hist._total}')

            lines += [
                "",
                "# HELP datasphere_jobs_created_total Total jobs created",
                "# TYPE datasphere_jobs_created_total counter",
            ]
            for (mode,), count in self._jobs_created_total.items():
                lines.append(f'datasphere_jobs_created_total{{mode="{mode}"}} {count}')

            lines += [
                "",
                "# HELP datasphere_jobs_completed_total Successfully completed jobs",
                "# TYPE datasphere_jobs_completed_total counter",
            ]
            for (mode,), count in self._jobs_completed_total.items():
                lines.append(f'datasphere_jobs_completed_total{{mode="{mode}"}} {count}')

            lines += [
                "",
                "# HELP datasphere_jobs_failed_total Failed jobs",
                "# TYPE datasphere_jobs_failed_total counter",
            ]
            for (mode,), count in self._jobs_failed_total.items():
                lines.append(f'datasphere_jobs_failed_total{{mode="{mode}"}} {count}')

            lines += [
                "",
                "# HELP datasphere_generation_duration_seconds Generation job duration",
                "# TYPE datasphere_generation_duration_seconds histogram",
            ]
            for (mode,), hist in self._generation_duration_seconds.items():
                for i, b in enumerate(hist.buckets):
                    lines.append(f'datasphere_generation_duration_seconds_bucket{{mode="{mode}",le="{b}"}} {hist._counts[i]}')
                lines.append(f'datasphere_generation_duration_seconds_bucket{{mode="{mode}",le="+Inf"}} {hist._total}')
                lines.append(f'datasphere_generation_duration_seconds_sum{{mode="{mode}"}} {hist._sum:.4f}')
                lines.append(f'datasphere_generation_duration_seconds_count{{mode="{mode}"}} {hist._total}')

        return "\n".join(lines) + "\n"


# Module-level singleton
metrics = MetricsCollector()
