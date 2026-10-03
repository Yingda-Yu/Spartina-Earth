"""Resource accounting for the national GEE metadata census (Issue #16).

Every census run logs server interaction and local resource usage so the
"no 3,319 x scenes getInfo" rule is auditable afterwards:

* ``api_calls`` / ``getinfo_calls`` / ``reductions`` - server interactions;
* per-call target, result count, payload bytes, duration, retries, errors;
* wall runtime and process peak RSS sampled after each call;
* sizes of local scene/event caches written during the run.

Pure standard library; GEE code lives in scripts and feeds this ledger.
"""

from __future__ import annotations

import json
import resource
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from spartina.data.national.footprints import utc_now_iso


@dataclass(frozen=True)
class CallRecord:
    sensor: str
    call_kind: str  # reduceColumns.getInfo | geometry_batch.getInfo | ...
    scope: str  # year / period / probe identifier
    n_results: int
    payload_bytes: int
    duration_s: float
    retries: int
    ok: bool
    error: str | None = None


@dataclass
class ResourceLedger:
    run_id: str
    git_commit: str
    started_utc: str = field(default_factory=utc_now_iso)
    calls: list[CallRecord] = field(default_factory=list)
    cache_files: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    _wall_start: float = field(default_factory=time.perf_counter)

    def record_call(
        self,
        *,
        sensor: str,
        call_kind: str,
        scope: str,
        n_results: int,
        payload_bytes: int,
        duration_s: float,
        retries: int = 0,
        ok: bool = True,
        error: str | None = None,
    ) -> None:
        self.calls.append(
            CallRecord(
                sensor=sensor,
                call_kind=call_kind,
                scope=scope,
                n_results=n_results,
                payload_bytes=payload_bytes,
                duration_s=duration_s,
                retries=retries,
                ok=ok,
                error=error,
            )
        )

    def note(self, text: str) -> None:
        self.notes.append(text)

    def record_cache_file(self, path: Path) -> None:
        self.cache_files[str(path)] = path.stat().st_size if path.exists() else 0

    @staticmethod
    def peak_rss_mib() -> float:
        """Peak resident set size in MiB (ru_maxrss, KiB on Linux)."""
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0

    def totals(self) -> dict[str, Any]:
        ok_calls = [c for c in self.calls if c.ok]
        return {
            "api_calls": len(self.calls),
            "failed_calls": sum(1 for c in self.calls if not c.ok),
            "getinfo_calls": sum(1 for c in self.calls if "getInfo" in c.call_kind),
            "reduction_calls": sum(
                1 for c in self.calls if c.call_kind.startswith("reduceColumns")
            ),
            "retries": sum(c.retries for c in self.calls),
            "results_returned": sum(c.n_results for c in ok_calls),
            "payload_bytes": sum(c.payload_bytes for c in ok_calls),
            "wall_s": round(time.perf_counter() - self._wall_start, 3),
            "peak_rss_mib": round(self.peak_rss_mib(), 2),
            "cache_bytes": sum(self.cache_files.values()),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "git_commit": self.git_commit,
            "started_utc": self.started_utc,
            "finished_utc": utc_now_iso(),
            "totals": self.totals(),
            "notes": self.notes,
            "cache_files": self.cache_files,
            "calls": [asdict(c) for c in self.calls],
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
