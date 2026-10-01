"""Resumable async export task tracking for the EO Data Factory.

A small JSON-backed task store provides:

* stable task IDs and full attempt/error history,
* bounded retry with explicit states,
* resume of tasks left non-terminal by a crashed process,
* a backend protocol so the GEE batch API is only touched lazily.

The store itself is pure standard library and is unit-tested offline
with a fake backend. Real Earth Engine batch exports run through
:class:`EarthEngineBatchBackend` (``ee`` imported inside methods) and are
exercised solely under the ``gee_integration`` marker.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

STATE_PENDING = "PENDING"
STATE_ENQUEUED = "ENQUEUED"
STATE_RUNNING = "RUNNING"
STATE_COMPLETED = "COMPLETED"
STATE_FAILED = "FAILED"
NON_TERMINAL = frozenset(
    {STATE_PENDING, STATE_ENQUEUED, STATE_RUNNING})
TERMINAL = frozenset({STATE_COMPLETED, STATE_FAILED})

#: GEE batch state -> factory state
_GEE_STATE_MAP: dict[str, str] = {
    "READY": STATE_ENQUEUED,
    "RUNNING": STATE_RUNNING,
    "COMPLETED": STATE_COMPLETED,
    "FAILED": STATE_FAILED,
    "CANCEL_REQUESTED": STATE_RUNNING,
    "CANCELLED": STATE_FAILED,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017


@dataclass
class TaskRecord:
    """One tracked export task and its complete attempt history."""

    task_id: str
    request_id: str
    state: str = STATE_PENDING
    backend_task_id: str | None = None
    attempts: int = 0
    max_attempts: int = 3
    errors: list[dict[str, str]] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)
    enqueue_spec: dict[str, Any] = field(default_factory=dict)
    created_utc: str = field(default_factory=_utc_now)
    updated_utc: str = field(default_factory=_utc_now)
    #: Raw GEE state observed at EVERY poll (repeated states kept), each
    #: entry {"utc", "state"} -- the Issue #6 real-byte protocol requires
    #: a timestamped READY -> RUNNING -> COMPLETED/FAILED history, not
    #: only the final state.
    state_history: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> TaskRecord:
        return cls(**payload)


class TaskError(RuntimeError):
    """Invalid task-store operation."""


class TaskStore:
    """JSON-file-backed, crash-resumable task store."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._records: dict[str, TaskRecord] = {}
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        payload = json.loads(self.path.read_text("utf-8"))
        self._records = {
            tid: TaskRecord.from_dict(rec)
            for tid, rec in payload.get("tasks", {}).items()}

    def save(self) -> None:
        """Atomically persist the store (temp file + replace)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = {"version": 1, "updated_utc": _utc_now(),
                "tasks": {tid: rec.to_dict()
                          for tid, rec in self._records.items()}}
        tmp = self.path.with_suffix(self.path.suffix + ".part")
        tmp.write_text(json.dumps(body, indent=2, sort_keys=True),
                       encoding="utf-8")
        tmp.replace(self.path)

    def create(self, request_id: str, *, max_attempts: int = 3) -> TaskRecord:
        if max_attempts < 1:
            raise TaskError("max_attempts must be >= 1")
        task_id = f"task-{uuid.uuid5(uuid.NAMESPACE_URL, request_id).hex[:16]}"
        if task_id in self._records:
            raise TaskError(f"task for request {request_id!r} already exists")
        record = TaskRecord(task_id=task_id, request_id=request_id,
                            max_attempts=max_attempts)
        self._records[task_id] = record
        self.save()
        return record

    def get(self, task_id: str) -> TaskRecord:
        try:
            return self._records[task_id]
        except KeyError:
            raise TaskError(f"unknown task {task_id!r}") from None

    def get_by_request_id(self, request_id: str) -> TaskRecord | None:
        """Look up a record by its deterministic request id (resume)."""
        for record in self._records.values():
            if record.request_id == request_id:
                return record
        return None

    def list_non_terminal(self) -> list[TaskRecord]:
        """Resume entry point: everything not COMPLETED/FAILED."""
        return [r for r in self._records.values()
                if r.state not in TERMINAL]

    def mark_enqueued(self, task_id: str, backend_task_id: str) -> None:
        rec = self.get(task_id)
        if rec.state == STATE_COMPLETED:
            raise TaskError(f"{task_id} already completed")
        rec.state = STATE_ENQUEUED
        rec.backend_task_id = backend_task_id
        rec.updated_utc = _utc_now()
        self.save()

    def mark_running(self, task_id: str) -> None:
        rec = self.get(task_id)
        rec.state = STATE_RUNNING
        rec.updated_utc = _utc_now()
        self.save()

    def record_poll_state(self, task_id: str, gee_state: str,
                          *, detail: str | None = None) -> None:
        """Append one raw GEE poll observation (never deduped).

        Every status poll is persisted with its own UTC timestamp so the
        store keeps a READY -> RUNNING -> COMPLETED/FAILED history rather
        than only the terminal state (Issue #6 real-byte protocol).
        """
        rec = self.get(task_id)
        entry: dict[str, str] = {"utc": _utc_now(),
                                 "state": str(gee_state)}
        if detail is not None:
            entry["detail"] = detail
        rec.state_history.append(entry)
        rec.updated_utc = entry["utc"]
        self.save()

    def record_attempt_error(self, task_id: str, message: str) -> None:
        """Record an error; retry while attempts remain, else FAILED."""
        rec = self.get(task_id)
        rec.attempts += 1
        rec.errors.append({"attempt": str(rec.attempts),
                           "utc": _utc_now(), "message": message})
        rec.state = (STATE_FAILED if rec.attempts >= rec.max_attempts
                     else STATE_PENDING)
        rec.updated_utc = _utc_now()
        self.save()

    def mark_completed(self, task_id: str,
                       result: dict[str, Any]) -> None:
        rec = self.get(task_id)
        rec.state = STATE_COMPLETED
        rec.result = dict(result)
        rec.updated_utc = _utc_now()
        self.save()

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for rec in self._records.values():
            out[rec.state] = out.get(rec.state, 0) + 1
        return out


@runtime_checkable
class TaskBackend(Protocol):
    """Pluggable execution backend (fake in tests, GEE in production)."""

    def enqueue(self, spec: dict[str, Any]) -> str:
        """Submit an export spec; return the backend-side task identifier."""
        ...

    def poll(self, backend_task_id: str) -> dict[str, Any]:
        """Return ``{"state": <factory state>, "result": ..., "error": ...}``."""
        ...


class TaskRunner:
    """Drives tasks through a backend with retry and resume."""

    def __init__(self, store: TaskStore, backend: TaskBackend) -> None:
        self.store = store
        self.backend = backend

    def submit(self, request_id: str, spec: dict[str, Any],
               *, max_attempts: int = 3) -> TaskRecord:
        """Create + enqueue one task, capturing enqueue errors in-store."""
        record = self.store.create(request_id, max_attempts=max_attempts)
        self._enqueue_with_retry(record, spec)
        return self.store.get(record.task_id)

    def _enqueue_with_retry(
        self, record: TaskRecord, spec: dict[str, Any],
    ) -> None:
        while record.state == STATE_PENDING:
            try:
                backend_id = self.backend.enqueue(spec)
            except Exception as exc:  # captured, never silently swallowed
                self.store.record_attempt_error(
                    record.task_id, f"enqueue: {type(exc).__name__}: {exc}")
                record = self.store.get(record.task_id)
                continue
            record = self.store.get(record.task_id)
            record.enqueue_spec = dict(spec)
            self.store.mark_enqueued(record.task_id, backend_id)
            return

    def poll_once(self, task_id: str) -> TaskRecord:
        rec = self.store.get(task_id)
        if rec.state in TERMINAL or rec.backend_task_id is None:
            return rec
        status = self.backend.poll(rec.backend_task_id)
        state = str(status.get("state", STATE_FAILED))
        if state == STATE_RUNNING:
            self.store.mark_running(task_id)
        elif state == STATE_COMPLETED:
            self.store.mark_completed(
                task_id, dict(status.get("result") or {}))
        elif state == STATE_FAILED:
            self.store.record_attempt_error(
                task_id, str(status.get("error") or "backend reported failure"))
            rec = self.store.get(task_id)
            if rec.state == STATE_PENDING:
                self._enqueue_with_retry(rec, rec.enqueue_spec)
        return self.store.get(task_id)

    def resume(self) -> list[TaskRecord]:
        """Re-drive every non-terminal task left by a previous process."""
        driven: list[TaskRecord] = []
        for rec in self.store.list_non_terminal():
            driven.append(self.poll_once(rec.task_id))
        return driven


class EarthEngineBatchBackend:
    """GEE ``ee.batch.Export`` backend (lazy import; needs real auth).

    The image/export specification is built by the factory pipeline; this
    class only translates it into the GEE batch API and polls task state.
    """

    def __init__(self) -> None:
        self._ee: Any | None = None

    def _ee_module(self) -> Any:
        if self._ee is None:
            try:
                import ee
            except ImportError as exc:  # pragma: no cover - env dependent
                raise RuntimeError(
                    "earthengine-api is not installed (optional 'gee' "
                    "extra); real exports are BLOCKED_BY_AUTH/DEPENDENCY") \
                    from exc
            self._ee = ee
        return self._ee

    def enqueue(self, spec: dict[str, Any]) -> str:
        """Start an ``Export.image.toCloudStorage`` batch task.

        Requires real credentials; never call in unit tests.
        """
        ee = self._ee_module()
        task = ee.batch.Export.image.toCloudStorage(**spec)
        task.start()
        return str(task.id)

    def poll(self, backend_task_id: str) -> dict[str, Any]:
        """Fetch one GEE batch task status and map it to factory states."""
        ee = self._ee_module()
        status = ee.data.getTaskStatus(backend_task_id)[0]
        state = _GEE_STATE_MAP.get(str(status.get("state")), STATE_FAILED)
        return {"state": state, "result": status
                if state == STATE_COMPLETED else {},
                "error": status.get("error_message")}


__all__ = [
    "EarthEngineBatchBackend",
    "NON_TERMINAL",
    "STATE_COMPLETED",
    "STATE_ENQUEUED",
    "STATE_FAILED",
    "STATE_PENDING",
    "STATE_RUNNING",
    "TaskBackend",
    "TaskError",
    "TaskRecord",
    "TaskRunner",
    "TaskStore",
    "TERMINAL",
]
