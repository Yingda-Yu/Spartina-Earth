#!/usr/bin/env python3
"""Cartographic map template enforcing CARTOGRAPHIC_DESIGN_STANDARD.md.

`render_map` refuses to render a publication map missing any mandatory
element (raises MapStandardError). Until admin/coastline context layers
are integrated (planned), only draft_mode=True rendering is allowed.

No data claims: the demo path renders a synthetic grid to validate the
layout machinery only.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

MANDATORY_ELEMENTS = [
    "coastline", "admin_boundaries", "graticule", "scale_bar", "north_arrow",
    "legend", "inset_locator", "data_source", "acquisition_year",
    "native_resolution_statement", "uncertainty_representation", "ocean_background",
]


class MapStandardError(RuntimeError):
    pass


def check_elements(elements: dict, publication: bool) -> None:
    missing = [e for e in MANDATORY_ELEMENTS if not elements.get(e)]
    if missing and publication:
        raise MapStandardError(f"publication map missing mandatory elements: {missing}")


def render_map(
    raster: np.ndarray,
    extent: tuple[float, float, float, float] | None = None,
    *,
    draft_mode: bool = True,
    elements: dict | None = None,
    no_valid_observation_mask: np.ndarray | None = None,
    title: str = "Spartina map (DRAFT — template validation)",
    data_source: str | None = None,
    acquisition_year: str | None = None,
    native_resolution: str | None = None,
    save_path: str | None = None,
):
    """Render a standard-compliant map frame.

    draft_mode=True: renders layout without context layers (for template
    testing only — never for publication).
    draft_mode=False: enforces every mandatory element; raises
    MapStandardError if any are missing.
    """
    publication = not draft_mode
    elements = dict(elements or {})
    elements.setdefault("data_source", bool(data_source))
    elements.setdefault("acquisition_year", bool(acquisition_year))
    elements.setdefault("native_resolution_statement", bool(native_resolution))
    elements.setdefault("graticule", True)
    elements.setdefault("scale_bar", True)
    elements.setdefault("north_arrow", True)
    elements.setdefault("legend", True)
    elements.setdefault("inset_locator", draft_mode is False)
    elements.setdefault("ocean_background", draft_mode is False)
    elements.setdefault("coastline", draft_mode is False)
    elements.setdefault("admin_boundaries", draft_mode is False)
    elements.setdefault("uncertainty_representation", True)
    check_elements(elements, publication)

    fig, ax = plt.subplots(figsize=(8, 8))
    im = ax.imshow(raster, extent=extent, cmap="viridis", interpolation="nearest")

    if no_valid_observation_mask is not None:
        # NO_VALID_OBSERVATION is rendered as distinct neutral hatch —
        # never as zero/absence (Atlas integrity rule).
        overlay = np.ma.masked_where(~no_valid_observation_mask,
                                     np.ones_like(no_valid_observation_mask, dtype=float))
        ax.imshow(overlay, extent=extent, cmap="Greys", alpha=0.55,
                  interpolation="nearest", hatch="///")

    if extent:
        ax.set_xticks(np.linspace(extent[0], extent[2], 5))
        ax.set_yticks(np.linspace(extent[1], extent[3], 5))
        ax.set_xlabel("Easting (m, projected CRS)")
        ax.set_ylabel("Northing (m, projected CRS)")  # graticule stand-in (draft)
    ax.set_title(title)

    # scale bar (draft): 1 km reference line
    if extent:
        x0 = extent[0] + 0.1 * (extent[2] - extent[0])
        y0 = extent[1] + 0.05 * (extent[3] - extent[1])
        ax.plot([x0, x0 + 1000], [y0, y0], "k-", lw=2)
        ax.text(x0 + 500, y0, "1 km", ha="center", va="bottom", fontsize=8)

    # north arrow (draft)
    ax.annotate("N", xy=(0.95, 0.95), xytext=(0.95, 0.85),
                xycoords="axes fraction",
                arrowprops=dict(facecolor="black", width=3, headwidth=10),
                ha="center", fontsize=10)

    ax.legend(handles=[mpatches.Patch(color="purple", label="Spartina (legend stand-in)")],
              loc="lower right", fontsize=8)

    footer = []
    if data_source:
        footer.append(f"Source: {data_source}")
    if acquisition_year:
        footer.append(f"Acquisition: {acquisition_year}")
    if native_resolution:
        footer.append(f"Native resolution: {native_resolution}")
    if footer:
        fig.text(0.01, 0.01, " | ".join(footer), fontsize=7)

    if save_path:
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
    return fig, ax


if __name__ == "__main__":
    rng = np.random.default_rng(0)
    demo = rng.random((64, 64))
    nvo = rng.random((64, 64)) > 0.9
    fig, _ = render_map(demo, extent=(0, 6400, 0, 6400), draft_mode=True,
                        data_source="synthetic template validation",
                        acquisition_year="n/a",
                        native_resolution="64 px synthetic grid")
    fig.savefig("map_template_demo.png", dpi=150)
    print("draft render OK -> map_template_demo.png (template validation only)")

    # publication mode without context layers must be refused:
    try:
        render_map(demo, draft_mode=False)
        print("ERROR: publication render should have been refused")
        raise SystemExit(1)
    except MapStandardError as exc:
        print(f"publication refusal OK: {exc}")
