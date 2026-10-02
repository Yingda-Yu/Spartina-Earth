"""Label rights matrix (M2.1a2, Issue #12, sections 26-29).

Splits the M2.1a conflated "usable for training distribution" flag into
eight independent fields. Every decision value is one of YES / NO /
UNKNOWN; UNKNOWN means "the license text does not address this use" and
is never silently upgraded to YES or NO. In particular:

* non-redistribution is NOT auto-interpreted as "no internal research";
* local file presence is NOT a license;
* model-weight release is a separate question from data redistribution.

Records are static, evidence-backed constants. The driver writes the
manifest; no network access happens inside this module.
"""

from __future__ import annotations

from typing import Any, Final

from spartina.data.gee.selection import canonical_fingerprint

YES: Final[str] = "YES"
NO: Final[str] = "NO"
UNKNOWN: Final[str] = "UNKNOWN"
RIGHTS_VALUES: Final[tuple[str, str, str]] = (YES, NO, UNKNOWN)

AUDITED: Final[str] = "AUDITED_TEXT_SUPPORTED"
NO_LICENSE: Final[str] = "NO_LICENSE_TEXT_LOCATED_ALL_UNKNOWN"
RIGHTS_STATUS: Final[tuple[str, str]] = (AUDITED, NO_LICENSE)

LABEL_RIGHTS_COLUMNS: Final[tuple[str, ...]] = (
    "asset_id",
    "label_tier",
    "scientific_analysis_allowed",
    "internal_training_allowed",
    "validation_use_allowed",
    "public_redistribution_allowed",
    "derived_model_release_status",
    "citation_required",
    "permission_evidence",
    "license_source",
    "license_observed_date",
    "rights_status",
    "rights_row_fingerprint",
    "notes",
)

_GEODATA_EVIDENCE: Final[str] = (
    "geodata.cn product page (DOI 10.12041/geodata.65372070926827.ver1.db), "
    "fetched 2026-10-02: 'scientific data limited to scientific research use'; "
    "reproduction/copying/dissemination forbidden without written platform "
    "permission; mandatory source citation + acknowledgement; no clause "
    "addresses machine-learning training or model-weight release"
)
_GEODATA_SOURCE: Final[str] = (
    "https://www.geodata.cn/data/datadetails.html?dataguid=65372070926827 ; "
    "https://doi.org/10.12041/geodata.65372070926827.ver1.db"
)

_USGS_EVIDENCE: Final[str] = (
    "USGS EROS Data Citation page, fetched 2026-10-02: most USGS/NASA EROS "
    "data incl. Landsat 'reside in the public domain and may be used, "
    "transferred, or reproduced without copyright restriction'; source "
    "credit is requested ('...courtesy of the U.S. Geological Survey')"
)
_USGS_SOURCE: Final[str] = (
    "https://www.usgs.gov/centers/eros/data-citation"
)

_COPERNICUS_EVIDENCE: Final[str] = (
    "EU Legal notice on use of Copernicus Sentinel Data (Reg (EU) No "
    "377/2014; Commission Delegated Reg (EU) No 1159/2013, Art. 7-8), "
    "text fetched 2026-10-02: free, full and open access; reproduction, "
    "distribution, communication, adaptation/modification/combination "
    "granted for any lawful use; mandatory notice 'Contains modified "
    "Copernicus Sentinel data [Year]'; no express clause on model weights"
)
_COPERNICUS_SOURCE: Final[str] = (
    "https://sentinels.copernicus.eu/documents/247904/690755/"
    "Sentinel_Data_Legal_Notice"
)

#: Unknown-production composite: upstream license is open but the local
#: derivative chain cannot be verified, so redistribution stays UNKNOWN.
_PROVENANCE_CAVEAT: Final[str] = (
    "upstream raw-data license is permissive, but local composite "
    "production provenance (dates, processing, inputs) is UNKNOWN; "
    "UNKNOWN is retained for redistribution/model release, not inferred"
)


def _r(
    asset_id: str,
    tier: str,
    *,
    analysis: str,
    training: str,
    validation: str,
    redistribution: str,
    model_release: str,
    citation: str,
    evidence: str,
    source: str,
    observed: str,
    status: str,
    notes: str,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "asset_id": asset_id,
        "label_tier": tier,
        "scientific_analysis_allowed": analysis,
        "internal_training_allowed": training,
        "validation_use_allowed": validation,
        "public_redistribution_allowed": redistribution,
        "derived_model_release_status": model_release,
        "citation_required": citation,
        "permission_evidence": evidence,
        "license_source": source,
        "license_observed_date": observed,
        "rights_status": status,
        "rights_row_fingerprint": "",
        "notes": notes,
    }
    row["rights_row_fingerprint"] = canonical_fingerprint(
        {k: v for k, v in row.items() if k != "rights_row_fingerprint"}
    )
    return row


def label_rights_records() -> list[dict[str, Any]]:
    """Static, evidence-text-bound rights decision for every legacy asset."""
    rows: list[dict[str, Any]] = [
        _r(
            "L1-china2015-raster30m", "SILVER",
            analysis=YES,
            training=UNKNOWN,
            validation=YES,
            redistribution=NO,
            model_release=UNKNOWN,
            citation=YES,
            evidence=_GEODATA_EVIDENCE,
            source=_GEODATA_SOURCE,
            observed="2026-10-02",
            status=AUDITED,
            notes=(
                "scientific research explicitly allowed; redistribution "
                "explicitly prohibited absent written permission; training "
                "and model weights are simply not addressed -> UNKNOWN, "
                "never inferred; dataset acquired through platform order "
                "flow (purpose statement), record of grant UNKNOWN"
            ),
        ),
        _r(
            "L2-cmssm2020-polygons", "WEAK",
            analysis=UNKNOWN,
            training=UNKNOWN,
            validation=UNKNOWN,
            redistribution=UNKNOWN,
            model_release=UNKNOWN,
            citation=UNKNOWN,
            evidence=(
                "no license/terms text located for CM-SSM; ownership "
                "UNVERIFIED; local file existence confers no rights"
            ),
            source="UNKNOWN",
            observed="2026-10-02",
            status=NO_LICENSE,
            notes=(
                "all rights UNKNOWN pending owner/license identification; "
                "descriptive geometric audit already performed does not "
                "establish a use right"
            ),
        ),
        _r(
            "L3-hangzhou-mask-2015", "WEAK",
            analysis=UNKNOWN,
            training=UNKNOWN,
            validation=UNKNOWN,
            redistribution=UNKNOWN,
            model_release=UNKNOWN,
            citation=UNKNOWN,
            evidence=(
                "no license/terms text located; file name source "
                "institution unresolved; production provenance UNKNOWN"
            ),
            source="UNKNOWN",
            observed="2026-10-02",
            status=NO_LICENSE,
            notes="all rights UNKNOWN; diagnostic-only at M2.1a",
        ),
        _r(
            "L4-cmsa-polygons-2019", "WEAK",
            analysis=UNKNOWN,
            training=UNKNOWN,
            validation=UNKNOWN,
            redistribution=UNKNOWN,
            model_release=UNKNOWN,
            citation=UNKNOWN,
            evidence="no license/terms text located; CMSA origin unresolved",
            source="UNKNOWN",
            observed="2026-10-02",
            status=NO_LICENSE,
            notes="all rights UNKNOWN pending source identification",
        ),
        _r(
            "L5-cmsa-polygons-2020", "WEAK",
            analysis=UNKNOWN,
            training=UNKNOWN,
            validation=UNKNOWN,
            redistribution=UNKNOWN,
            model_release=UNKNOWN,
            citation=UNKNOWN,
            evidence="no license/terms text located; CMSA origin unresolved",
            source="UNKNOWN",
            observed="2026-10-02",
            status=NO_LICENSE,
            notes="all rights UNKNOWN pending source identification",
        ),
        _r(
            "L6-cmsa-polygons-2021", "WEAK",
            analysis=UNKNOWN,
            training=UNKNOWN,
            validation=UNKNOWN,
            redistribution=UNKNOWN,
            model_release=UNKNOWN,
            citation=UNKNOWN,
            evidence="no license/terms text located; CMSA origin unresolved",
            source="UNKNOWN",
            observed="2026-10-02",
            status=NO_LICENSE,
            notes="all rights UNKNOWN pending source identification",
        ),
        _r(
            "U1-hzb-l8allbands-2015", "UNLABELED",
            analysis=YES, training=YES, validation=YES,
            redistribution=UNKNOWN, model_release=UNKNOWN,
            citation=YES,
            evidence=_USGS_EVIDENCE,
            source=_USGS_SOURCE,
            observed="2026-10-02",
            status=AUDITED,
            notes=_PROVENANCE_CAVEAT,
        ),
        _r(
            "U2-hzb-ndvi-2015", "UNLABELED",
            analysis=YES, training=YES, validation=YES,
            redistribution=UNKNOWN, model_release=UNKNOWN,
            citation=YES,
            evidence=_USGS_EVIDENCE,
            source=_USGS_SOURCE,
            observed="2026-10-02",
            status=AUDITED,
            notes=_PROVENANCE_CAVEAT,
        ),
        _r(
            "U3-hzb-sai-2015", "UNLABELED",
            analysis=YES, training=YES, validation=YES,
            redistribution=UNKNOWN, model_release=UNKNOWN,
            citation=YES,
            evidence=_USGS_EVIDENCE,
            source=_USGS_SOURCE,
            observed="2026-10-02",
            status=AUDITED,
            notes=_PROVENANCE_CAVEAT,
        ),
        _r(
            "U4-hzb-s1vv-2015", "UNLABELED",
            analysis=YES, training=YES, validation=YES,
            redistribution=UNKNOWN, model_release=UNKNOWN,
            citation=YES,
            evidence=_COPERNICUS_EVIDENCE,
            source=_COPERNICUS_SOURCE,
            observed="2026-10-02",
            status=AUDITED,
            notes=_PROVENANCE_CAVEAT,
        ),
        _r(
            "U5-hzb-s1vh-2015", "UNLABELED",
            analysis=YES, training=YES, validation=YES,
            redistribution=UNKNOWN, model_release=UNKNOWN,
            citation=YES,
            evidence=_COPERNICUS_EVIDENCE,
            source=_COPERNICUS_SOURCE,
            observed="2026-10-02",
            status=AUDITED,
            notes=_PROVENANCE_CAVEAT,
        ),
        _r(
            "U6-zj-featurestack-A", "UNLABELED",
            analysis=UNKNOWN,
            training=UNKNOWN,
            validation=UNKNOWN,
            redistribution=UNKNOWN,
            model_release=UNKNOWN,
            citation=UNKNOWN,
            evidence=(
                "11-band feature stack; band provenance and inputs not "
                "resolved; no license text located"
            ),
            source="UNKNOWN",
            observed="2026-10-02",
            status=NO_LICENSE,
            notes="file name 'Spartina' is not a label and not a license",
        ),
        _r(
            "U7-zj-featurestack-B", "UNLABELED",
            analysis=UNKNOWN,
            training=UNKNOWN,
            validation=UNKNOWN,
            redistribution=UNKNOWN,
            model_release=UNKNOWN,
            citation=UNKNOWN,
            evidence=(
                "11-band feature stack; band provenance and inputs not "
                "resolved; no license text located"
            ),
            source="UNKNOWN",
            observed="2026-10-02",
            status=NO_LICENSE,
            notes="file name 'Spartina' is not a label and not a license",
        ),
    ]
    for yr in range(2019, 2026):
        rows.append(_r(
            f"U8-yqb-s2-composite-{yr}", "UNLABELED",
            analysis=YES, training=YES, validation=YES,
            redistribution=UNKNOWN, model_release=UNKNOWN,
            citation=YES,
            evidence=_COPERNICUS_EVIDENCE,
            source=_COPERNICUS_SOURCE,
            observed="2026-10-02",
            status=AUDITED,
            notes=_PROVENANCE_CAVEAT,
        ))
    rows.sort(key=lambda r: r["asset_id"])
    return rows


def rights_registry_fingerprint(rows: list[dict[str, Any]]) -> str:
    return canonical_fingerprint([
        {k: v for k, v in row.items() if k != "rights_row_fingerprint"}
        for row in sorted(rows, key=lambda r: r["asset_id"])
    ])
