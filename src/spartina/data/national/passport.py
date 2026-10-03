"""SOURCE_PASSPORT.json records for external datasets (Issue #14 section 22).

Every external dataset downloaded under ``work/external/`` carries a
passport beside its bytes (source URL, DOI, download UTC, license, file
list with sizes and SHA256, citation).  This module validates passport
structure only; it never fabricates provenance.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

SHA256_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
PASSPORT_FILENAME: Final[str] = "SOURCE_PASSPORT.json"


@dataclass(frozen=True)
class PassportFile:
    """One byte-identifiable component of an external archive."""

    name: str
    size_bytes: int
    sha256: str

    def validate(self) -> None:
        if not self.name:
            raise ValueError("passport file requires a name")
        if self.size_bytes < 0:
            raise ValueError(f"negative size for {self.name}")
        if not SHA256_RE.fullmatch(self.sha256):
            raise ValueError(f"bad sha256 for {self.name}: {self.sha256!r}")


@dataclass(frozen=True)
class SourcePassport:
    """Provenance record accompanying one external download."""

    dataset_id: str
    source_url: str
    download_utc: str
    license: str
    files: tuple[PassportFile, ...]
    citation: str
    doi: str = ""
    publisher: str = ""
    archive_name: str = ""
    archive_size_bytes: int = -1
    archive_sha256: str = ""
    verified_by: str = ""
    notes: str = ""
    extra: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.source_url.startswith(("http://", "https://")):
            raise ValueError("source_url must be an http(s) URL")
        _require_utc(self.download_utc)
        if not self.files:
            raise ValueError("passport needs at least one file")
        for component in self.files:
            component.validate()
        if self.archive_sha256 and not SHA256_RE.fullmatch(self.archive_sha256):
            raise ValueError("bad archive_sha256")
        if not self.citation:
            raise ValueError("passport needs a citation")

    def total_size_bytes(self) -> int:
        return sum(f.size_bytes for f in self.files)


def _require_utc(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"bad ISO timestamp: {value!r}") from exc
    if parsed.tzinfo != UTC:
        raise ValueError(f"timestamp must be UTC: {value!r}")


def utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string (passport convention)."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def load_passport(path: Path | str) -> SourcePassport:
    """Read and validate a SOURCE_PASSPORT.json."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    files = tuple(PassportFile(**f) for f in data.pop("files", []))
    passport = SourcePassport(files=files, **data)
    passport.validate()
    return passport
