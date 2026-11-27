"""Hard test-embargo gate for the M1.5 baseline ladder.

TEST windows are unavailable to training/validation tooling until a
``FINAL_EVAL_LOCK.json`` exists *and* the caller explicitly unlocks the
session. Normal training commands cannot reach TEST even if a split
name is supplied by mistake.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ALLOW_TEST_ENV = "SPARTINA_PILOT0_ALLOW_TEST"


class TestEmbargoError(RuntimeError):
    """Raised when TEST is accessed before the final evaluation lock."""


@dataclass(frozen=True)
class LockInfo:
    path: Path
    payload: dict[str, Any]

    @property
    def checksum(self) -> str:
        return str(self.payload.get("lock_sha256", ""))


def read_lock(path: Path) -> LockInfo | None:
    if not path.exists():
        return None
    return LockInfo(path, json.loads(path.read_text(encoding="utf-8")))


class EmbargoGate:
    """Split access policy used by every dataset/CLI entry point."""

    def __init__(
        self, lock_path: Path | None = None,
        expected_split_fingerprint: str | None = None,
        expected_normalization_checksum: str | None = None,
    ) -> None:
        self.lock_path = lock_path
        self.expected_split_fingerprint = expected_split_fingerprint
        self.expected_normalization_checksum = (
            expected_normalization_checksum)

    def request_split(self, split: str) -> None:
        if split in {"train", "val"}:
            return
        if split != "test":
            raise ValueError(f"unknown split: {split!r}")
        if os.environ.get(ALLOW_TEST_ENV) != "1":
            raise TestEmbargoError(
                "TEST split is embargoed: final evaluation lock has not "
                f"been activated for this process (env {ALLOW_TEST_ENV}=1 "
                "required). Run finalize_lock + final_eval, not training.")
        if self.lock_path is None or not self.lock_path.exists():
            raise TestEmbargoError(
                f"TEST embargoed: lock file {self.lock_path} does not "
                "exist; train/val decisions must be frozen first.")
        lock = read_lock(self.lock_path)
        if lock is None:
            raise TestEmbargoError("TEST embargoed: lock file unreadable")
        payload = lock.payload
        if payload.get("status") != "FROZEN":
            raise TestEmbargoError(
                "TEST embargoed: lock status is not FROZEN")
        sfp = payload.get("split_logical_fingerprint")
        if (self.expected_split_fingerprint is not None
                and sfp != self.expected_split_fingerprint):
            raise TestEmbargoError(
                "TEST embargoed: lock split fingerprint mismatch")
        nfp = payload.get("normalization_sha256")
        if (self.expected_normalization_checksum is not None
                and nfp != self.expected_normalization_checksum):
            raise TestEmbargoError(
                "TEST embargoed: lock normalization checksum mismatch")
