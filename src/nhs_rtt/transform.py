"""Phase 4 — transformation, data quality and the analytical dataset.

Turns the **verified Phase 3 publication** (`data/interim/rtt_combined.parquet`
+ its generation marker + sidecar) into deterministic, analysis-ready datasets
whose grains, derived fields, missingness, quality conditions and lineage are
explicit and tested.

What this module produces
-------------------------
* **analytical-wide** — one row per accepted Phase 3 source row (exact row
  conservation), the full wide NHS structure and *unchanged* source values,
  plus a small set of analytically-justified derived columns and row-level
  data-quality flags.
* **waiting-band-long** — a *dense* long representation: every analytical-wide
  row yields exactly 105 ordered band rows (including rows whose source band
  value is ``<NA>``), so ``len(long) == len(wide) * 105`` and the
  explicit-zero / source-``<NA>`` distinction is preserved.
* **wait-band metadata** — 105 rows derived deterministically from the frozen
  Phase 2 band contract (label, order, week/day boundaries; ``>104`` open).
* **transformation / data-quality report** — machine-readable JSON + a
  human-readable Markdown summary, separating row-level quality conditions from
  dataset-level diagnostics.
* **Phase 4 generation manifest** (`phase4_generation.json`) — the commit
  marker written last, binding the consumed Phase 3 identity and the SHA-256 /
  schema / row count of every Phase 4 output into one coherent generation.
  :func:`verify_phase4_publication` is the consumer's validity gate.

What this module does **not** do (Phase 5+)
-------------------------------------------
No dimensional model, no surrogate-key architecture, no DuckDB / SQL layer, no
calendar dimension, no KPI / threshold logic, no statistical analysis, no BI,
no ML, no Spark. It never re-reads ``data/raw/*.csv`` (Phase 3 is the input
boundary) and never mutates the Phase 3 publication.

Frozen contracts (see ``docs/rtt_semantics.md`` / ``docs/rtt_grain_and_aggregation.md``
/ ``docs/decisions.md``): the 105-band schema, the candidate natural key, "blank
!= zero" (no blanket ``fillna(0)``), C_999 *or* detail (never both), NONC
retained and classified neutrally, ``Part_2A`` ⊆ ``Part_2`` with the P2-U7
preserve-and-flag exceptions, codes identify / names label.
"""

from __future__ import annotations

import copy as _copy
import datetime as _dt
import hashlib as _hashlib
import json
import os as _os
import shutil as _shutil
import tempfile as _tempfile
import time as _time
import tracemalloc as _tracemalloc
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from nhs_rtt import crossmonth as _xm
from nhs_rtt.crossmonth import PROVENANCE_COLS, mapping_diagnostics, verify_publication
from nhs_rtt.semantics import (BANDED_PARTS, CANDIDATE_KEY, COMMISSIONER_COL,
                               NONC_CODE, PERIOD_COL, PROVIDER_COL, RTT_PART_COL,
                               TFC_COL, TOTAL_ALL_COL, TOTAL_COL, TOTAL_TFC,
                               candidate_key_report, expected_week_band_names,
                               parse_week_band, part_2a_subset_conformance,
                               week_band_columns)

__all__ = [
    "PublicationNotVerifiedError",
    "TransformError",
    "RowConservationError",
    "CardinalityError",
    "LineageError",
    "Phase4PublicationError",
    "PHASE3_PUBLICATION_PARQUET",
    "ANALYTICAL_WIDE_PARQUET",
    "WAITING_BAND_LONG_PARQUET",
    "WAIT_BAND_METADATA_PARQUET",
    "TRANSFORM_REPORT_JSON",
    "TRANSFORM_REPORT_MD",
    "PHASE4_MANIFEST",
    "PHASE4_OUTPUT_FILES",
    "REQUIRED_MANIFEST_OUTPUTS",
    "DERIVED_TIME_COLS",
    "DERIVED_CLASSIFICATION_COLS",
    "DQ_FLAG_COLS",
    "RTT_PART_EVENT_BASIS",
    "REPORTING_DATE_DTYPE",
    "VARIABLE_REPORT_FIELDS",
    "load_verified_publication",
    "wait_band_metadata",
    "build_analytical_wide",
    "build_waiting_band_long",
    "write_waiting_band_long",
    "validate_persisted_long",
    "reconcile_long_against_wide",
    "build_transformation_report",
    "render_report_markdown",
    "deterministic_report_view",
    "build_phase4_manifest",
    "compute_phase4_generation_id",
    "verify_phase4_publication",
    "restore_previous_phase4_generation",
    "Phase4Result",
    "run_phase4",
]

# --------------------------------------------------------------------------- #
# Paths / constants
# --------------------------------------------------------------------------- #

#: Phase 3 publication (the Phase 4 input boundary). Never written by Phase 4.
PHASE3_PUBLICATION_PARQUET = "rtt_combined.parquet"
#: Phase 3 sidecar / marker names (== ``crossmonth._SIDECAR_NAME`` /
#: ``crossmonth.GENERATION_MARKER``; Phase 3 is frozen).
_PHASE3_SIDECAR = "rtt_combined.ingest_manifest.json"
_PHASE3_MARKER = _xm.GENERATION_MARKER

ANALYTICAL_WIDE_PARQUET = "rtt_analytical_wide.parquet"
WAITING_BAND_LONG_PARQUET = "rtt_waiting_band_long.parquet"
WAIT_BAND_METADATA_PARQUET = "wait_band_metadata.parquet"
TRANSFORM_REPORT_JSON = "phase4_transformation_report.json"
TRANSFORM_REPORT_MD = "phase4_transformation_report.md"
#: Phase 4 commit marker — written **last** by :func:`run_phase4`; a publication
#: is coherent iff every output's SHA-256 matches this manifest (see
#: :func:`verify_phase4_publication`).
PHASE4_MANIFEST = "phase4_generation.json"

#: The ordered Phase 4 output set. The manifest is committed **last**.
PHASE4_OUTPUT_FILES = [
    ANALYTICAL_WIDE_PARQUET,
    WAIT_BAND_METADATA_PARQUET,
    WAITING_BAND_LONG_PARQUET,
    TRANSFORM_REPORT_JSON,
    TRANSFORM_REPORT_MD,
    PHASE4_MANIFEST,
]

#: Number of ordered waiting-time bands in a production extract (frozen).
N_WAIT_BANDS = 105

#: Enforced serialized resolution of ``reporting_period_start_date`` — an
#: explicit, environment-stable contract (P4-A05). Microsecond precision is
#: ample for a month-start anchor and matches what pandas/pyarrow persist here.
REPORTING_DATE_DTYPE = "datetime64[us]"

#: Derived reporting-time columns added to the analytical-wide dataset. Derived
#: from the canonical Phase 3 ``reporting_month`` — the raw ``Period`` column is
#: retained unchanged alongside them.
DERIVED_TIME_COLS = [
    "reporting_year",
    "reporting_month_num",
    "reporting_month_name",
    "reporting_period_start_date",
]

#: Derived neutral analytical classifications (legitimate semantic categories,
#: NOT data-quality conditions).
DERIVED_CLASSIFICATION_COLS = [
    "is_treatment_function_total",
    "is_nonc_commissioner",
    "rtt_part_event_basis",
    "rtt_part_carries_bands",
    "rtt_part_is_month_end_snapshot",
]

#: Row-level data-quality / condition flags (a small, meaningful set). Every
#: ``dq_`` column is a *factual condition flag* — it records that a row meets a
#: condition, regardless of whether the condition is structurally expected for
#: that RTT Part. The data-quality policy in ``docs/phase4_transformation.md``
#: §9 classifies each: ``dq_all_bands_missing`` (structural for Part_3) and
#: ``dq_total_missing`` (structural for Parts 2/2A/3) are *structurally
#: expected* conditions; ``dq_part2a_gt_part2`` and
#: ``dq_part2a_no_matching_part2`` mark *anomalous* source conditions (P2-U7).
DQ_FLAG_COLS = [
    "dq_all_bands_missing",
    "dq_total_missing",
    "dq_part2a_gt_part2",
    "dq_part2a_no_matching_part2",
]

#: ``RTT Part Type`` -> neutral event-basis classification (S1 §10.1.1.2,
#: frozen contract §5.7 — CONFIRMED DOCS+DATA). 1:1 with ``RTT Part Type``.
RTT_PART_EVENT_BASIS = {
    "Part_1A": "completed_admitted_in_month",
    "Part_1B": "completed_non_admitted_in_month",
    "Part_2": "incomplete_at_month_end",
    "Part_2A": "incomplete_with_dta_at_month_end",
    "Part_3": "new_clock_starts_in_month",
}

_MONTH_END_SNAPSHOT_PARTS = ("Part_2", "Part_2A")

_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December",
]

# Canonical sort key for the analytical-wide dataset: this is exactly the
# deterministic Phase 3 combined order (months ascending; within a month the
# 0-based parsed source-record order).
_WIDE_SORT_COLS = ["reporting_month", "source_row_index"]

#: Report fields that legitimately vary between runs / configurations (P4-A04):
#: wall-clock timestamps and durations, peak allocation, output paths, and the
#: block-size-dependent *physical* Parquet layout metadata. Everything else in
#: the report is deterministic analytical content. Dotted paths are nested keys.
VARIABLE_REPORT_FIELDS = (
    "generated_utc",
    "dense_long_benchmark.build_write_seconds",
    "dense_long_benchmark.peak_tracemalloc_mib",
    "dense_long_benchmark.path",
    "dense_long_benchmark.parquet_bytes",
    "dense_long_benchmark.block_rows",
    "dense_long_benchmark.n_blocks",
    "dense_long_benchmark.row_group_rows",
    "transformation_integrity.persisted_long_validation.seconds",
    "transformation_integrity.persisted_long_validation.path",
    "transformation_integrity.persisted_long_validation.batches",
)


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #

class TransformError(RuntimeError):
    """A Phase 4 transformation invariant failed."""


class PublicationNotVerifiedError(TransformError):
    """The Phase 3 publication input gate did not pass ``verify_publication``."""


class RowConservationError(TransformError):
    """A transformation did not preserve the expected row count."""


class CardinalityError(TransformError):
    """The wide -> long transformation did not produce exactly N x 105 rows."""


class LineageError(TransformError):
    """A derived long row could not be traced back to a Phase 3 parent row, or
    a persisted-output cell disagreed with the verified analytical-wide cell."""


class Phase4PublicationError(TransformError):
    """The staged Phase 4 generation failed validation or an atomic commit
    step, or a published generation failed self-verification."""


# --------------------------------------------------------------------------- #
# Input boundary — an immutable verified snapshot of the Phase 3 publication
# --------------------------------------------------------------------------- #

@dataclass
class VerifiedInput:
    """The verified Phase 3 publication, ready to transform.

    ``df`` / ``parquet_sha256`` / ``generation_id`` all derive from **one
    private immutable snapshot** whose exact bytes passed
    ``crossmonth.verify_publication``. A concurrent replace, or a
    change-and-restore of the live publication during reading, cannot detach
    these values from the verified generation (P4-A01).
    """

    df: pd.DataFrame
    interim_dir: Path
    generation_id: str
    combined_rows: int
    parquet_sha256: str          # SHA-256 of the *verified consumed snapshot* bytes
    verification: dict


def _sha256_path(path: str | Path, *, _chunk: int = 1 << 20) -> str:
    h = _hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(_chunk), b""):
            h.update(block)
    return h.hexdigest()


def load_verified_publication(interim_dir: str | Path = "data/interim") -> VerifiedInput:
    """Load the Phase 3 combined publication **from a private verified snapshot**.

    P4-A01 binding: the publication trio (Parquet + sidecar + generation marker)
    is copied once into a private temp directory; ``crossmonth.verify_publication``
    is run against *that snapshot*; the consumed-input digest is the SHA-256 of
    the snapshot Parquet (identical to the marker's ``parquet_sha256`` that
    ``verify_publication`` just checked); and the DataFrame is parsed only from
    the snapshot. So the returned frame, its recorded digest and the generation
    identity always refer to the same verified bytes even if the live
    ``interim_dir`` is replaced or changed-and-restored during the read.

    Raises :class:`PublicationNotVerifiedError` if the snapshot does not verify
    (missing / invalid marker, hash mismatch, row-count disagreement) or fails
    the frozen Phase 3 contract re-checks. Never writes to ``interim_dir``.
    """
    interim_dir = Path(interim_dir)
    snap = Path(_tempfile.mkdtemp(prefix="nhs_rtt_p4in_"))
    try:
        for name in (PHASE3_PUBLICATION_PARQUET, _PHASE3_SIDECAR, _PHASE3_MARKER):
            src_f = interim_dir / name
            if not src_f.exists():
                raise PublicationNotVerifiedError(
                    f"Phase 3 publication file missing: {src_f}. Regenerate it "
                    "(nhs_rtt.crossmonth.run_phase3) before running Phase 4.")
            _shutil.copy2(src_f, snap / name)

        v = verify_publication(snap)
        if not v.get("valid"):
            raise PublicationNotVerifiedError(
                f"Phase 3 publication in {interim_dir} does not verify: {v.get('reason')!r}. "
                "Regenerate it (nhs_rtt.crossmonth.run_phase3) before running Phase 4.")

        snap_parquet = snap / PHASE3_PUBLICATION_PARQUET
        consumed_sha = _sha256_path(snap_parquet)          # == marker.parquet_sha256
        df = pd.read_parquet(snap_parquet, engine="pyarrow").reset_index(drop=True)

        # frozen Phase 3 contract re-checks (against the verified snapshot)
        if len(df) != v["combined_rows"]:
            raise PublicationNotVerifiedError(
                f"snapshot Parquet row count {len(df)} != verified combined_rows {v['combined_rows']}")
        missing_prov = [c for c in PROVENANCE_COLS if c not in df.columns]
        if missing_prov:
            raise PublicationNotVerifiedError(f"provenance column(s) absent: {missing_prov}")
        krep = candidate_key_report(df, CANDIDATE_KEY)
        if not krep["usable"]:
            raise PublicationNotVerifiedError(
                f"candidate key not usable on the publication: is_unique={krep.get('is_unique')} "
                f"n_key_cells_missing={krep.get('n_key_cells_missing')}")

        return VerifiedInput(
            df=df, interim_dir=interim_dir,
            generation_id=v["generation_id"], combined_rows=v["combined_rows"],
            parquet_sha256=consumed_sha, verification=v,
        )
    finally:
        _shutil.rmtree(snap, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Wait-band metadata (derived from the frozen contract — never a 2nd hand list)
# --------------------------------------------------------------------------- #

def wait_band_metadata() -> pd.DataFrame:
    """The 105 waiting-time bands as an ordered reference table, derived
    deterministically from :func:`nhs_rtt.semantics.expected_week_band_names`
    and :func:`nhs_rtt.semantics.parse_week_band`.

    Columns:

    * ``wait_band_order``       1..105, header order (frozen).
    * ``wait_band_label``       the canonical source column name.
    * ``wait_band_lower_weeks`` lower **week** boundary (0, 1, ..., 104).
    * ``wait_band_upper_weeks`` upper week boundary (1, ..., 104), ``<NA>`` for
      the open-ended ``>104`` band.
    * ``wait_band_lower_days`` / ``wait_band_upper_days`` — **DERIVED** day
      bounds (P2-U6): band ``n``-``n+1`` (n>=1) covers days ``7n+1 .. 7(n+1)``;
      first band 0..7 days; final band >= 729 days (``upper`` is ``<NA>``). NHS
      England gives only 5 worked examples; these are labelled derived.
    * ``is_open_ended``         True only for ``>104 weeks``.
    """
    names = expected_week_band_names()
    rows: list[dict[str, object]] = []
    for i, label in enumerate(names, start=1):
        lo_w, hi_w = parse_week_band(label)
        if lo_w == 0:
            lo_d, hi_d = 0, 7
        else:
            lo_d, hi_d = 7 * lo_w + 1, (7 * (lo_w + 1) if hi_w is not None else None)
        rows.append({
            "wait_band_order": i,
            "wait_band_label": label,
            "wait_band_lower_weeks": lo_w,
            "wait_band_upper_weeks": hi_w,
            "wait_band_lower_days": lo_d,
            "wait_band_upper_days": hi_d,
            "is_open_ended": hi_w is None,
        })
    df = pd.DataFrame(rows)
    return df.astype({
        "wait_band_order": "Int16",
        "wait_band_label": "string",
        "wait_band_lower_weeks": "Int16",
        "wait_band_upper_weeks": "Int16",
        "wait_band_lower_days": "Int32",
        "wait_band_upper_days": "Int32",
        "is_open_ended": "boolean",
    })


# --------------------------------------------------------------------------- #
# Dataset A — analytical-wide (row-preserving)
# --------------------------------------------------------------------------- #

def _reporting_month_parts(month: pd.Series) -> pd.DataFrame:
    """``"YYYY-MM"`` -> year / month number / month name / month-start date.

    ``reporting_period_start_date`` is the first calendar day of the reporting
    month — a mechanical, sortable **monthly anchor** for a chronological axis,
    serialized at an **explicit, enforced** resolution
    (:data:`REPORTING_DATE_DTYPE`, ``datetime64[us]``). It is *not* an event
    timestamp: the flow-vs-stock analytical temporal model and any month-end
    snapshot date remain deferred to Phase 5 (P2-U5).
    """
    s = month.astype("string")
    year = s.str.slice(0, 4).astype("Int16")
    mnum = s.str.slice(5, 7).astype("Int16")
    name = mnum.map(lambda m: _MONTH_NAMES[int(m) - 1] if pd.notna(m) else pd.NA).astype("string")
    start = (pd.to_datetime(s + "-01", format="%Y-%m-%d", errors="coerce")
             .astype(REPORTING_DATE_DTYPE))
    return pd.DataFrame({
        "reporting_year": year,
        "reporting_month_num": mnum.astype("Int8"),
        "reporting_month_name": name,
        "reporting_period_start_date": start,
    }, index=month.index)


def _part2a_row_dq_flags(month_df: pd.DataFrame) -> pd.DataFrame:
    """Per-month row-level P2-U7 flags for ``Part_2A`` rows, using exactly the
    frozen :func:`nhs_rtt.semantics.part_2a_subset_conformance` matching logic
    (match on ``[Provider Org Code, Commissioner Org Code, Treatment Function
    Code]``; ``Period`` is constant within a month; the frozen helper's
    ``has_matching_part_2`` is ``Part_2 Total All`` *not null*).

    Returns two boolean Series aligned to ``month_df.index``:

    * ``dq_part2a_gt_part2`` — a matching Part_2 row exists with a **numeric**
      ``Total All`` and this Part_2A row's ``Total All`` is strictly greater.
      Source values are **preserved**, never capped.
    * ``dq_part2a_no_matching_part2`` — **no matching Part_2 row with a usable
      (non-null) ``Total All`` comparator** is available. This covers *both*
      "no Part_2 row at the key" and "a Part_2 row exists but its ``Total All``
      is ``<NA>``" — matching the frozen conformance helper exactly. See
      ``docs/phase4_transformation.md`` §9 for the four-state breakdown.

    Both are ``False`` for every non-Part_2A row.
    """
    key = [PROVIDER_COL, COMMISSIONER_COL, TFC_COL]
    idx = month_df.index
    gt = pd.Series(False, index=idx)
    nomatch = pd.Series(False, index=idx)

    is_2a = month_df[RTT_PART_COL] == "Part_2A"
    if not bool(is_2a.any()):
        return pd.DataFrame({"dq_part2a_gt_part2": gt,
                             "dq_part2a_no_matching_part2": nomatch})

    p2 = (month_df.loc[month_df[RTT_PART_COL] == "Part_2", key + [TOTAL_ALL_COL]]
          .drop_duplicates(subset=key).set_index(key)[TOTAL_ALL_COL])
    rows_2a = month_df.loc[is_2a, key + [TOTAL_ALL_COL]]
    matched_p2 = p2.reindex(pd.MultiIndex.from_frame(rows_2a[key])).to_numpy()
    own = rows_2a[TOTAL_ALL_COL].to_numpy()

    has_usable_comparator = ~pd.isna(matched_p2)      # frozen helper semantics
    gt_vals = np.zeros(len(rows_2a), dtype=bool)
    both = has_usable_comparator & ~pd.isna(own)
    gt_vals[both] = own[both].astype("int64") > matched_p2[both].astype("int64")

    gt.loc[rows_2a.index] = gt_vals
    nomatch.loc[rows_2a.index] = ~has_usable_comparator
    return pd.DataFrame({"dq_part2a_gt_part2": gt,
                         "dq_part2a_no_matching_part2": nomatch})


def build_analytical_wide(vin: VerifiedInput) -> pd.DataFrame:
    """Dataset A — one analytical-wide row per accepted Phase 3 source row.

    * **Row conservation.** ``len(out) == len(vin.df)`` (541,363 for the current
      publication). No row is filtered, deduplicated or reshaped.
    * **Grain.** ``reporting_month x Provider Org Code x Commissioner Org Code x
      RTT Part Type x Treatment Function Code`` — equivalent to the frozen
      candidate key (``Period`` <-> ``reporting_month`` is 1:1). Asserted unique.
    * **Source values unchanged.** Every one of the 125 Phase 3 columns is
      carried through verbatim (including ``Period`` and the four provenance
      columns). Missingness is preserved — **no ``fillna(0)``**.
    * **Derived columns appended** (``DERIVED_TIME_COLS`` +
      ``DERIVED_CLASSIFICATION_COLS`` + ``DQ_FLAG_COLS``): pure, deterministic
      functions of the source columns.

    Deterministic order: months ascending, then ``source_row_index`` ascending
    (identical to the Phase 3 combined order).
    """
    src = vin.df
    n_in = len(src)

    out = src.sort_values(_WIDE_SORT_COLS, kind="stable").reset_index(drop=True)

    # --- derived reporting-time metadata (raw Period retained) ---
    tparts = _reporting_month_parts(out["reporting_month"])

    # --- neutral analytical classifications (legitimate semantic categories) ---
    is_tf_total = (out[TFC_COL] == TOTAL_TFC)
    is_nonc = (out[COMMISSIONER_COL] == NONC_CODE)
    event_basis = out[RTT_PART_COL].map(RTT_PART_EVENT_BASIS).astype("string")
    carries_bands = out[RTT_PART_COL].isin(BANDED_PARTS)
    is_snapshot = out[RTT_PART_COL].isin(_MONTH_END_SNAPSHOT_PARTS)

    # --- row-level data-quality / condition flags ---
    band_cols = week_band_columns(out.columns.tolist())
    dq_all_bands_missing = out[band_cols].isna().all(axis=1)
    dq_total_missing = out[TOTAL_COL].isna()

    p2a = pd.DataFrame({"dq_part2a_gt_part2": False,
                        "dq_part2a_no_matching_part2": False}, index=out.index)
    for _, mrows in out.groupby("reporting_month", sort=True):
        flags = _part2a_row_dq_flags(mrows)
        p2a.loc[flags.index, flags.columns] = flags

    derived = pd.DataFrame({
        "reporting_year": tparts["reporting_year"],
        "reporting_month_num": tparts["reporting_month_num"],
        "reporting_month_name": tparts["reporting_month_name"],
        "reporting_period_start_date": tparts["reporting_period_start_date"],
        "is_treatment_function_total": is_tf_total.astype("boolean"),
        "is_nonc_commissioner": is_nonc.astype("boolean"),
        "rtt_part_event_basis": event_basis,
        "rtt_part_carries_bands": carries_bands.astype("boolean"),
        "rtt_part_is_month_end_snapshot": is_snapshot.astype("boolean"),
        "dq_all_bands_missing": dq_all_bands_missing.astype("boolean"),
        "dq_total_missing": dq_total_missing.astype("boolean"),
        "dq_part2a_gt_part2": p2a["dq_part2a_gt_part2"].astype("boolean"),
        "dq_part2a_no_matching_part2": p2a["dq_part2a_no_matching_part2"].astype("boolean"),
    }, index=out.index)

    wide = pd.concat([out, derived], axis=1)

    # --- invariants ---
    if len(wide) != n_in:
        raise RowConservationError(f"analytical-wide has {len(wide)} rows, expected {n_in}")
    krep = candidate_key_report(wide, CANDIDATE_KEY)
    if not krep["usable"]:
        raise TransformError(
            f"analytical-wide candidate key not usable: is_unique={krep.get('is_unique')} "
            f"n_duplicate_groups={krep.get('n_duplicate_groups')}")
    # source columns byte-for-byte unchanged (order-independent comparison)
    src_sorted = src.sort_values(_WIDE_SORT_COLS, kind="stable").reset_index(drop=True)
    a = src_sorted.astype(object).where(pd.notna(src_sorted), None)
    b = wide[src.columns].astype(object).where(pd.notna(wide[src.columns]), None)
    if not a.equals(b):
        raise TransformError("analytical-wide changed a source column value")
    if str(wide["reporting_period_start_date"].dtype) != REPORTING_DATE_DTYPE:
        raise TransformError(
            f"reporting_period_start_date dtype {wide['reporting_period_start_date'].dtype} "
            f"!= enforced contract {REPORTING_DATE_DTYPE}")
    return wide


# --------------------------------------------------------------------------- #
# Dataset B — waiting-band long (dense)
# --------------------------------------------------------------------------- #

#: Parent columns carried onto every derived long row. The first six identify
#: the analytical grain; the last three are Phase 3 **source provenance** used
#: for lineage. ``(source_file, source_row_index, wait_band_order)`` identifies
#: the exact source cell each long row represents.
_LONG_ID_COLS = [
    "reporting_month", PERIOD_COL, PROVIDER_COL, COMMISSIONER_COL,
    RTT_PART_COL, TFC_COL, "source_file", "source_sha256", "source_row_index",
]

#: Column order of the waiting-band-long dataset.
LONG_COLUMNS = _LONG_ID_COLS + [
    "wait_band_order", "wait_band_label",
    "wait_band_lower_weeks", "wait_band_upper_weeks",
    "pathway_count",
]


def _long_arrow_schema() -> pa.Schema:
    return pa.schema([
        ("reporting_month", pa.string()),
        (PERIOD_COL, pa.string()),
        (PROVIDER_COL, pa.string()),
        (COMMISSIONER_COL, pa.string()),
        (RTT_PART_COL, pa.string()),
        (TFC_COL, pa.string()),
        ("source_file", pa.string()),
        ("source_sha256", pa.string()),
        ("source_row_index", pa.int64()),
        ("wait_band_order", pa.int16()),
        ("wait_band_label", pa.string()),
        ("wait_band_lower_weeks", pa.int16()),
        ("wait_band_upper_weeks", pa.int16()),   # null on the open >104 band
        ("pathway_count", pa.int64()),           # explicit 0 stays 0; source <NA> stays null
    ])


def _dense_long_chunk(block: pd.DataFrame, band_cols: list[str],
                      meta: pd.DataFrame) -> pa.Table:
    """Vectorised wide -> dense-long for one block of analytical-wide rows.

    Produces exactly ``len(block) * 105`` rows in **parent-major** order (each
    parent's 105 bands together, ascending ``wait_band_order``) via
    ``np.repeat`` / ``np.tile`` — no melt, no post-sort. ``pathway_count`` is
    the source band cell carried through an **integer-preserving** path (nullable
    ``Int64`` -> ``int64`` data + a separate NA mask -> nullable ``Int64``); no
    float round-trip, so there is no ``2**53`` precision ceiling. Explicit ``0``
    stays ``0``; source ``<NA>`` stays null (dense representation).
    """
    n = len(block)
    b = N_WAIT_BANDS
    rep = lambda s: np.repeat(np.asarray(s, dtype=object), b)  # noqa: E731

    vals = block[band_cols]
    data = np.ascontiguousarray(vals.to_numpy(dtype="int64", na_value=0))   # (n,105)
    na_mask = vals.isna().to_numpy()                                        # (n,105) bool
    counts = pd.array(data.reshape(-1), dtype="Int64")                      # C-order == parent-major
    flat_mask = na_mask.reshape(-1)
    if flat_mask.any():
        counts[flat_mask] = pd.NA

    order = np.tile(np.arange(1, b + 1, dtype="int16"), n)
    labels = np.tile(meta["wait_band_label"].to_numpy(dtype=object), n)
    lo_w = np.tile(meta["wait_band_lower_weeks"].to_numpy(dtype="int16"), n)
    hi_w = np.tile(
        meta["wait_band_upper_weeks"].astype("float64").to_numpy(na_value=np.nan), n)

    cols = {
        "reporting_month": rep(block["reporting_month"]),
        PERIOD_COL: rep(block[PERIOD_COL]),
        PROVIDER_COL: rep(block[PROVIDER_COL]),
        COMMISSIONER_COL: rep(block[COMMISSIONER_COL]),
        RTT_PART_COL: rep(block[RTT_PART_COL]),
        TFC_COL: rep(block[TFC_COL]),
        "source_file": rep(block["source_file"]),
        "source_sha256": rep(block["source_sha256"]),
        "source_row_index": np.repeat(
            block["source_row_index"].to_numpy(dtype="int64"), b),
        "wait_band_order": order,
        "wait_band_label": labels,
        "wait_band_lower_weeks": lo_w,
        "wait_band_upper_weeks": pa.array(hi_w, type=pa.int16(), from_pandas=True),
        "pathway_count": pa.array(counts, type=pa.int64(), from_pandas=True),
    }
    return pa.table(cols, schema=_long_arrow_schema())


def build_waiting_band_long(wide: pd.DataFrame, *, meta: pd.DataFrame | None = None,
                            block_rows: int = 40_000) -> pd.DataFrame:
    """Materialise the **dense** waiting-band-long dataset in memory.

    ``len(out) == len(wide) * 105`` exactly. Intended for tests / small inputs;
    for the full publication use :func:`write_waiting_band_long`, which streams
    to Parquet in blocks and does not hold the whole 56.8M-row frame in memory.
    """
    if meta is None:
        meta = wait_band_metadata()
    band_cols = week_band_columns(wide.columns.tolist())
    parts = [
        _dense_long_chunk(wide.iloc[i:i + block_rows], band_cols, meta)
        for i in range(0, len(wide), block_rows)
    ]
    tbl = (pa.concat_tables(parts) if parts
           else _long_arrow_schema().empty_table())
    out = tbl.to_pandas().reset_index(drop=True)
    out["pathway_count"] = out["pathway_count"].astype("Int64")
    out["source_row_index"] = out["source_row_index"].astype("Int64")
    out["wait_band_order"] = out["wait_band_order"].astype("Int16")
    out["wait_band_lower_weeks"] = out["wait_band_lower_weeks"].astype("Int16")
    out["wait_band_upper_weeks"] = out["wait_band_upper_weeks"].astype("Int16")
    _assert_long_cardinality(wide, out)
    return out[LONG_COLUMNS]


@dataclass
class LongWriteResult:
    """Outcome + benchmark of a streamed dense-long Parquet write.

    ``build_write_seconds`` / ``peak_tracemalloc_mib`` / ``path`` /
    ``parquet_bytes`` / ``block_rows`` / ``n_blocks`` / ``row_group_rows`` are
    run/configuration-dependent (see :data:`VARIABLE_REPORT_FIELDS`);
    ``rows`` / ``expected_rows`` / ``zero_count`` / ``na_count`` are
    deterministic analytical content.
    """

    path: str
    rows: int
    expected_rows: int
    columns: list[str]
    parquet_bytes: int
    block_rows: int
    n_blocks: int
    build_write_seconds: float
    peak_tracemalloc_mib: float
    row_group_rows: int
    read_back_rows: int
    zero_count: int
    na_count: int

    def as_dict(self) -> dict[str, object]:
        d = dict(self.__dict__)
        d["cardinality_ok"] = self.rows == self.expected_rows == self.read_back_rows
        return d


def write_waiting_band_long(wide: pd.DataFrame, out_path: str | Path, *,
                            meta: pd.DataFrame | None = None,
                            block_rows: int = 40_000,
                            benchmark: bool = True) -> LongWriteResult:
    """Stream the dense waiting-band-long dataset to a single Parquet file.

    The transform runs in parent-row blocks (default 40,000 wide rows ->
    4,200,000 long rows per block), so peak memory is bounded by one block, not
    the full 56.8M-row result. **This function's own checks are write-side
    (cardinality only).** Authoritative acceptance of the persisted artifact is
    :func:`validate_persisted_long`, which ``run_phase4`` runs mandatorily
    against the file on disk before publication (P4-A02).

    Returns a :class:`LongWriteResult` carrying the dense-long **benchmark**
    evidence (rows, Parquet size, wall time, peak Python allocation, read-back
    check, explicit-zero vs source-``<NA>`` cell counts).
    """
    if meta is None:
        meta = wait_band_metadata()
    band_cols = week_band_columns(wide.columns.tolist())
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    expected = len(wide) * N_WAIT_BANDS

    if benchmark:
        _tracemalloc.start()
    t0 = _time.perf_counter()

    rows = zero_count = na_count = n_blocks = 0
    schema = _long_arrow_schema()
    writer = pq.ParquetWriter(str(out_path), schema, compression="zstd")
    try:
        for i in range(0, len(wide), block_rows):
            tbl = _dense_long_chunk(wide.iloc[i:i + block_rows], band_cols, meta)
            writer.write_table(tbl)
            pc = tbl.column("pathway_count")
            rows += tbl.num_rows
            na_count += pc.null_count
            zero_count += pa.compute.sum(pa.compute.equal(pc, 0)).as_py() or 0
            n_blocks += 1
    finally:
        writer.close()

    elapsed = _time.perf_counter() - t0
    peak_mib = 0.0
    if benchmark:
        peak_mib = _tracemalloc.get_traced_memory()[1] / (1024 * 1024)
        _tracemalloc.stop()

    pf = pq.ParquetFile(str(out_path))
    read_back = int(pf.metadata.num_rows)
    rg_rows = int(pf.metadata.row_group(0).num_rows) if pf.metadata.num_row_groups else 0

    if rows != expected or read_back != expected:
        raise CardinalityError(
            f"dense-long rows written={rows} read_back={read_back} expected={expected}")

    return LongWriteResult(
        path=str(out_path), rows=rows, expected_rows=expected,
        columns=list(LONG_COLUMNS), parquet_bytes=out_path.stat().st_size,
        block_rows=block_rows, n_blocks=n_blocks,
        build_write_seconds=round(elapsed, 3),
        peak_tracemalloc_mib=round(peak_mib, 1),
        row_group_rows=rg_rows, read_back_rows=read_back,
        zero_count=zero_count, na_count=na_count,
    )


def _assert_long_cardinality(wide: pd.DataFrame, long: pd.DataFrame) -> None:
    expected = len(wide) * N_WAIT_BANDS
    if len(long) != expected:
        raise CardinalityError(f"long has {len(long)} rows, expected {expected}")
    per_parent = long.groupby(["source_file", "source_row_index"], sort=False).size()
    if not bool((per_parent == N_WAIT_BANDS).all()):
        raise CardinalityError("not every parent row expands to exactly 105 band rows")
    labels = long["wait_band_label"].drop_duplicates().tolist()
    if sorted(labels) != sorted(expected_week_band_names()):
        raise CardinalityError("unexpected or missing wait_band_label(s) in long form")
    if int(long.duplicated(
            subset=["source_file", "source_row_index", "wait_band_order"]).sum()):
        raise CardinalityError("duplicate (source_file, source_row_index, wait_band_order)")


# --------------------------------------------------------------------------- #
# P4-A02 — authoritative bounded-memory validation of the persisted long Parquet
# --------------------------------------------------------------------------- #

def _schema_signature(schema: pa.Schema) -> list[str]:
    return [f"{f.name}:{f.type}" for f in schema]


def validate_persisted_long(long_path: str | Path, wide: pd.DataFrame,
                            meta: pd.DataFrame | None = None, *,
                            batch_rows: int = 262_144) -> dict[str, object]:
    """Authoritative validation of the **persisted** waiting-band-long Parquet
    (P4-A02). Streams the file on disk in fixed-size batches (bounded memory:
    reference arrays scale with the *wide* row count, which is fixed; the long
    file itself is never materialised) and checks, **positionally** — the writer
    emits parent-major order, so long row ``p`` is parent ``p // 105`` band
    ``(p % 105) + 1`` — every one of:

    exact schema; exact row count (= ``len(wide) * 105``); ``wait_band_order``;
    ``wait_band_label``; lower/upper week bounds (upper null only on the open
    band); all nine parent / provenance identity fields (``reporting_month``,
    ``Period``, provider / commissioner / RTT part / treatment-function codes,
    ``source_file``, ``source_sha256``, ``source_row_index``); ``pathway_count``
    value and its zero / NA state — each against the corresponding verified
    analytical-wide cell.

    A repeated / missing / reordered band, a wrong order / label / bound, a
    swapped value, a zero<->NA change, a wrong identity field, or a
    duplicate / extra observation all break positional alignment or the row-count
    check and raise :class:`LineageError` / :class:`CardinalityError`. Faults
    introduced *after* serialization are caught because the file on disk is what
    is read.

    **Integer-exact (P4-R02).** ``pathway_count`` is compared as ``int64``
    throughout — the wide reference is an integer matrix + a separate NA mask,
    and the persisted Arrow column is read via ``fill_null(0).to_numpy()`` (no
    ``float64`` round-trip), so the full nullable ``Int64`` domain (including
    values ``> 2**53``) is validated exactly.

    Returns a dict of counts (rows, batches, numeric / zero / positive / NA
    cells, wall time). ``seconds`` / ``path`` / ``batches`` are run-dependent.
    """
    if meta is None:
        meta = wait_band_metadata()
    long_path = Path(long_path)
    t0 = _time.perf_counter()

    pf = pq.ParquetFile(str(long_path))
    exp_sig = _schema_signature(_long_arrow_schema())
    got_sig = _schema_signature(pf.schema_arrow)
    if got_sig != exp_sig:
        raise LineageError(f"persisted long schema differs: {got_sig} != {exp_sig}")

    wide_ = wide.reset_index(drop=True)
    n_parents = len(wide_)
    expected_rows = n_parents * N_WAIT_BANDS
    if int(pf.metadata.num_rows) != expected_rows:
        raise CardinalityError(
            f"persisted long has {pf.metadata.num_rows} rows, expected {expected_rows}")

    band_names = expected_week_band_names()
    band_names_arr = np.asarray(band_names, dtype=object)
    id_ref: dict[str, np.ndarray] = {}
    for c in _LONG_ID_COLS:
        if c == "source_row_index":
            id_ref[c] = wide_[c].astype("int64").to_numpy()
        else:
            id_ref[c] = wide_[c].astype("string").to_numpy(dtype=object)
    # integer-exact reference: int64 data (0 where NA) + a separate NA mask
    _band_df = wide_[band_names]
    band_ref = np.ascontiguousarray(_band_df.to_numpy(dtype="int64", na_value=0))  # (N,105)
    band_isna = _band_df.isna().to_numpy()                                        # (N,105) bool
    lower_by_order = np.arange(0, N_WAIT_BANDS, dtype="int64")                     # order 1->0 .. 105->104

    off = n_zero = n_pos = n_na = n_batches = 0
    for batch in pf.iter_batches(batch_size=batch_rows):
        n = batch.num_rows
        pos = off + np.arange(n, dtype="int64")
        parent = pos // N_WAIT_BANDS
        order = (pos % N_WAIT_BANDS) + 1
        if int(parent.max()) >= n_parents:
            raise CardinalityError("persisted long row position exceeds len(wide) * 105")
        col = {f.name: batch.column(i) for i, f in enumerate(batch.schema)}

        if not np.array_equal(
                col["wait_band_order"].to_numpy(zero_copy_only=False).astype("int64"), order):
            raise LineageError(f"wait_band_order not parent-major near long row {off}")
        got_label = col["wait_band_label"].to_numpy(zero_copy_only=False).astype(object)
        if not np.array_equal(got_label, band_names_arr[order - 1]):
            raise LineageError(f"wait_band_label mismatch near long row {off}")

        got_lo = col["wait_band_lower_weeks"]
        if got_lo.null_count:
            raise LineageError("wait_band_lower_weeks contains null (never valid)")
        if not np.array_equal(got_lo.to_numpy(zero_copy_only=False).astype("int64"),
                              lower_by_order[order - 1]):
            raise LineageError("wait_band_lower_weeks mismatch")
        got_hi = col["wait_band_upper_weeks"]
        got_hi_isna = got_hi.is_null().to_numpy(zero_copy_only=False)
        exp_hi_isna = (order == N_WAIT_BANDS)
        if not np.array_equal(got_hi_isna, exp_hi_isna):
            raise LineageError("wait_band_upper_weeks null/non-null pattern disagrees with "
                               "the band contract (only the open >104 band may be null)")
        m_hi = ~exp_hi_isna
        if m_hi.any():
            got_hi_np = got_hi.fill_null(0).to_numpy(zero_copy_only=False).astype("int64")
            if not np.array_equal(got_hi_np[m_hi], order[m_hi]):
                raise LineageError("wait_band_upper_weeks value mismatch")

        for c in _LONG_ID_COLS:
            exp = id_ref[c][parent]
            if c == "source_row_index":
                got = col[c].to_numpy(zero_copy_only=False).astype("int64")
                if not np.array_equal(got, exp.astype("int64")):
                    raise LineageError(f"identity field '{c}' mismatch near long row {off}")
            else:
                got = col[c].to_numpy(zero_copy_only=False).astype(object)
                if not np.array_equal(got, exp):
                    raise LineageError(f"identity field '{c}' mismatch near long row {off}")

        pc = col["pathway_count"]
        exp_isna = band_isna[parent, order - 1]
        if not np.array_equal(pc.is_null().to_numpy(zero_copy_only=False), exp_isna):
            raise LineageError(f"pathway_count NA-state mismatch near long row {off}")
        m_num = ~exp_isna
        if m_num.any():
            got_pc = pc.fill_null(0).to_numpy(zero_copy_only=False).astype("int64")   # exact int64
            exp_pc = band_ref[parent, order - 1]                                      # exact int64
            if not np.array_equal(got_pc[m_num], exp_pc[m_num]):
                raise LineageError(f"pathway_count value mismatch near long row {off}")
            n_zero += int((exp_pc[m_num] == 0).sum())
            n_pos += int((exp_pc[m_num] > 0).sum())
        n_na += int(exp_isna.sum())
        off += n
        n_batches += 1

    if off != expected_rows:
        raise CardinalityError(
            f"persisted long streamed {off} rows, expected {expected_rows}")

    return {
        "path": str(long_path),
        "rows": off,
        "expected_rows": expected_rows,
        "parents": n_parents,
        "bands_per_parent": N_WAIT_BANDS,
        "batches": n_batches,
        "schema_ok": True,
        "numeric_cells": n_zero + n_pos,
        "explicit_zero_cells": n_zero,
        "positive_cells": n_pos,
        "source_na_cells": n_na,
        "value_mismatches": 0,
        "na_state_mismatches": 0,
        "identity_mismatches": 0,
        "seconds": round(_time.perf_counter() - t0, 3),
    }


def reconcile_long_against_wide(wide: pd.DataFrame, long: pd.DataFrame, *,
                                meta: pd.DataFrame | None = None) -> dict[str, object]:
    """**In-memory** cell-level reconciliation of a waiting-band-long *frame*
    against the analytical-wide frame — a heavier secondary diagnostic, not the
    authoritative persisted-artifact gate (that is
    :func:`validate_persisted_long`).

    Hardened per P4-A02: it requires an **exact 1:1** correspondence — exact
    row count (``len(wide) * 105``), no duplicate
    ``(source_file, source_row_index, wait_band_order)``, every long identity
    field (the six analytical dimensions + ``source_sha256`` + label + week
    bounds) equal to the wide parent / metadata — as well as the
    ``pathway_count`` value and zero / NA state.

    Band bounds are compared **explicitly and NA-safe** (P4-R01): expected and
    actual ``wait_band_lower_weeks`` must both be non-null and integer-equal;
    the ``wait_band_upper_weeks`` null mask must match the metadata exactly
    (only the open ``>104`` band is null) and numeric bounds are compared only
    at non-null positions — never via nullable equality + a skip-NA reduction.
    """
    if meta is None:
        meta = wait_band_metadata()
    band_names = expected_week_band_names()
    order_of = {c: i + 1 for i, c in enumerate(band_names)}
    expected_rows = len(wide) * N_WAIT_BANDS

    if len(long) != expected_rows:
        raise CardinalityError(f"long frame has {len(long)} rows, expected {expected_rows}")
    ndup = int(long.duplicated(
        subset=["source_file", "source_row_index", "wait_band_order"]).sum())
    if ndup:
        raise LineageError(f"{ndup} duplicate (source_file, source_row_index, wait_band_order) in long")
    bad_labels = set(long["wait_band_label"].astype("string").dropna().unique()) - set(band_names)
    if bad_labels:
        raise LineageError(f"unexpected wait_band_label(s): {sorted(bad_labels)[:5]}")

    dim_cols = ["reporting_month", PERIOD_COL, PROVIDER_COL, COMMISSIONER_COL,
                RTT_PART_COL, TFC_COL, "source_sha256"]
    wide_ = wide.reset_index(drop=True)
    tall = wide_[["source_file", "source_row_index", *dim_cols, *band_names]].melt(
        id_vars=["source_file", "source_row_index", *dim_cols],
        var_name="wait_band_label", value_name="wide_value")
    tall["wait_band_order"] = tall["wait_band_label"].map(order_of)

    keys = ["source_file", "source_row_index", "wait_band_order"]
    ldf = long.copy()
    for fr in (ldf, tall):
        fr["source_file"] = fr["source_file"].astype("string").astype(object)
        fr["source_row_index"] = fr["source_row_index"].astype("int64")
        fr["wait_band_order"] = fr["wait_band_order"].astype("int64")

    merged = ldf.merge(tall, on=keys, how="outer", indicator=True, suffixes=("", "_w"))
    if len(merged) != expected_rows or not bool((merged["_merge"] == "both").all()):
        raise LineageError(
            f"long/wide cells are not 1:1 (merged {len(merged)}, expected {expected_rows})")

    for c in [*dim_cols, "wait_band_label"]:
        left = merged[c].astype("string").fillna("\x00")
        right = merged[f"{c}_w"].astype("string").fillna("\x00")
        if not bool((left == right).all()):
            raise LineageError(f"long identity field '{c}' disagrees with the wide parent")

    # --- band bounds: explicit, NA-safe (P4-R01) — never a skip-NA reduction ---
    lo_by_order = {int(o): (None if pd.isna(w) else int(w))
                   for o, w in zip(meta["wait_band_order"], meta["wait_band_lower_weeks"])}
    hi_by_order = {int(o): (None if pd.isna(w) else int(w))
                   for o, w in zip(meta["wait_band_order"], meta["wait_band_upper_weeks"])}
    order_np = merged["wait_band_order"].to_numpy()                       # int64
    exp_lo = np.array([lo_by_order.get(int(o)) for o in order_np], dtype=object)
    exp_hi = np.array([hi_by_order.get(int(o)) for o in order_np], dtype=object)
    exp_lo_isna = np.array([v is None for v in exp_lo])
    exp_hi_isna = np.array([v is None for v in exp_hi])
    if exp_lo_isna.any():
        raise LineageError("metadata lower week bound is null — contract violation (all 105 "
                           "bands have a numeric lower bound)")

    got_lo = merged["wait_band_lower_weeks"]
    got_hi = merged["wait_band_upper_weeks"]
    got_lo_isna = got_lo.isna().to_numpy()
    got_hi_isna = got_hi.isna().to_numpy()
    if got_lo_isna.any():
        raise LineageError("wait_band_lower_weeks contains null — never valid")
    if not np.array_equal(got_lo.astype("int64").to_numpy(), exp_lo.astype("int64")):
        raise LineageError("wait_band_lower_weeks disagrees with metadata")
    # upper: null masks must match exactly (only the open >104 band is null)
    if not np.array_equal(got_hi_isna, exp_hi_isna):
        raise LineageError("wait_band_upper_weeks null/non-null pattern disagrees with metadata "
                           "(only the open >104 band may be null)")
    m_hi = ~exp_hi_isna
    if m_hi.any() and not np.array_equal(
            got_hi[m_hi].astype("int64").to_numpy(), exp_hi[m_hi].astype("int64")):
        raise LineageError("wait_band_upper_weeks disagrees with metadata")

    lv, wv = merged["pathway_count"], merged["wide_value"]
    xor_na = int((lv.isna() ^ wv.isna()).sum())
    both_num = lv.notna() & wv.notna()
    mism = int((both_num & (lv.astype("Int64") != wv.astype("Int64"))).sum())
    if xor_na or mism:
        raise LineageError(
            f"pathway_count reconciliation failed: value_mismatch={mism} na_mismatch={xor_na}")
    return {
        "cells": int(len(merged)),
        "both_missing": int((lv.isna() & wv.isna()).sum()),
        "both_numeric": int(both_num.sum()),
        "explicit_zero": int((both_num & (lv.astype("Int64") == 0)).sum()),
        "duplicate_keys": 0,
        "identity_mismatches": 0,
        "value_mismatches": 0,
        "na_state_mismatches": 0,
    }


# --------------------------------------------------------------------------- #
# Transformation / data-quality report
# --------------------------------------------------------------------------- #

def _by_month_part_counts(wide: pd.DataFrame, flag: str) -> dict[str, dict[str, int]]:
    sub = wide.loc[wide[flag].fillna(False)]
    out: dict[str, dict[str, int]] = {}
    for month, m in sub.groupby("reporting_month", sort=True):
        out[str(month)] = {str(k): int(v) for k, v in
                           m[RTT_PART_COL].value_counts().sort_index().items()}
    return out


def _mapping_summary(frames: dict[str, pd.DataFrame]) -> dict[str, object]:
    md = mapping_diagnostics(frames)
    return {
        "code_name_changes": int(len(md["code_name_changes"])),
        "name_code_collisions": md["name_code_collisions"].to_dict("records"),
        "membership_changes": md["membership_changes"][
            ["dimension", "from_month", "to_month", "n_appeared", "n_disappeared"]
        ].to_dict("records"),
        "note": "Codes identify; names label. Churn is diagnostic, never invalid data.",
    }


def build_transformation_report(vin: VerifiedInput, wide: pd.DataFrame,
                                long_result: LongWriteResult,
                                meta: pd.DataFrame, *,
                                persisted_validation: dict | None = None,
                                long_reconciliation: dict | None = None) -> dict[str, object]:
    """Assemble the machine-readable Phase 4 transformation / DQ evidence.

    Row-level quality conditions (attributable to one source-grain record) are
    kept separate from dataset-level diagnostics (global / by-month / by-mapping).
    No substantive waiting-time interpretation is performed here.
    """
    src = vin.df
    band_cols = week_band_columns(src.columns.tolist())
    months = sorted(src["reporting_month"].unique().tolist())
    frames = {m: wide.loc[wide["reporting_month"] == m] for m in months}

    # --- semantic diagnostics reuse the frozen conformance check per month ---
    p2a_by_month = {}
    for m in months:
        conf = part_2a_subset_conformance(frames[m])
        p2a_by_month[m] = {
            "n_part_2a_groups": conf["n_part_2a_groups"],
            "n_without_matching_part_2": conf["n_without_matching_part_2"],
            "n_conformant": conf["n_conformant"],
            "n_violations": conf["n_violations"],
            "violation_keys": [
                f"{r[PROVIDER_COL]}/{r[COMMISSIONER_COL]}/{r[TFC_COL]}"
                f"(2A={int(r['part_2a'])}>2={int(r['part_2'])})"
                for _, r in conf["violations"].iterrows()
            ],
        }

    c999 = {m: {"rows": int((frames[m][TFC_COL] == TOTAL_TFC).sum()),
                "share_pct": round(100.0 * (frames[m][TFC_COL] == TOTAL_TFC).mean(), 3)}
            for m in months}
    nonc = {m: {"rows": int((frames[m][COMMISSIONER_COL] == NONC_CODE).sum()),
                "share_pct": round(100.0 * (frames[m][COMMISSIONER_COL] == NONC_CODE).mean(), 3)}
            for m in months}

    row_level = {
        flag: {
            "total": int(wide[flag].fillna(False).sum()),
            "by_month_and_part": _by_month_part_counts(wide, flag),
        }
        for flag in DQ_FLAG_COLS
    }
    p2u7_rowflag_check = {
        m: {
            "dq_part2a_gt_part2": int(frames[m]["dq_part2a_gt_part2"].fillna(False).sum()),
            "matches_conformance_violations":
                int(frames[m]["dq_part2a_gt_part2"].fillna(False).sum())
                == p2a_by_month[m]["n_violations"],
            "dq_part2a_no_matching_part2": int(
                frames[m]["dq_part2a_no_matching_part2"].fillna(False).sum()),
            "matches_conformance_unmatched":
                int(frames[m]["dq_part2a_no_matching_part2"].fillna(False).sum())
                == p2a_by_month[m]["n_without_matching_part_2"],
        }
        for m in months
    }

    krep = candidate_key_report(wide, CANDIDATE_KEY)
    report = {
        "phase": 4,
        "generated_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "input_integrity": {
            "phase3_publication_verified": bool(vin.verification.get("valid")),
            "phase3_generation_id": vin.generation_id,
            "phase3_consumed_parquet_sha256": vin.parquet_sha256,
            "phase3_input_binding": (
                "consumed from a private immutable snapshot that passed "
                "crossmonth.verify_publication; the digest above is the SHA-256 of "
                "those exact verified bytes (P4-A01). The Phase 3 identity and every "
                "Phase 4 output hash are bound together in " + PHASE4_MANIFEST
                + " (verify_phase4_publication)."),
            "source_months": months,
            "input_rows": int(len(src)),
            "input_columns": int(src.shape[1]),
        },
        "transformation_integrity": {
            "analytical_wide_rows": int(len(wide)),
            "analytical_wide_columns": int(wide.shape[1]),
            "wide_row_conservation_ok": len(wide) == len(src),
            "candidate_key": CANDIDATE_KEY,
            "candidate_key_unique": bool(krep["is_unique"]),
            "candidate_key_usable": bool(krep["usable"]),
            "analytical_wide_sort_contract": _WIDE_SORT_COLS,
            "reporting_period_start_date_dtype": REPORTING_DATE_DTYPE,
            "waiting_band_long_rows": long_result.rows,
            "waiting_band_long_expected_rows": long_result.expected_rows,
            "long_cardinality_ok": long_result.rows == long_result.expected_rows,
            "long_rows_per_parent": N_WAIT_BANDS,
            "long_sort_contract": ["reporting_month", "source_row_index", "wait_band_order"],
            "long_lineage_keys": ["source_file", "source_row_index", "wait_band_order"],
            "persisted_long_validation": persisted_validation,
            "long_cell_reconciliation": long_reconciliation,
        },
        "missingness": {
            "no_blanket_fillna_zero": True,
            "rows_all_bands_missing": int(src[band_cols].isna().all(axis=1).sum()),
            "rows_total_missing": int(src[TOTAL_COL].isna().sum()),
            "rows_total_all_missing": int(src[TOTAL_ALL_COL].isna().sum()),
            "long_pathway_count_source_na": long_result.na_count,
            "long_pathway_count_explicit_zero": long_result.zero_count,
            "wide_reporting_period_start_date_na":
                int(wide["reporting_period_start_date"].isna().sum()),
            "long_wait_band_upper_weeks_na_per_parent": 1,
        },
        "semantic_diagnostics": {
            "part_2a_subset_by_month": p2a_by_month,
            "p2u7_row_flag_cross_check": p2u7_rowflag_check,
            "dq_part2a_no_matching_part2_meaning": (
                "no matching Part_2 row with a usable (non-null) Total All comparator "
                "— covers both 'no Part_2 row at the key' and 'Part_2 row present but "
                "Total All is <NA>'; matches the frozen part_2a_subset_conformance"),
            "c999_coverage_by_month": c999,
            "nonc_coverage_by_month": nonc,
            "aggregation_rules": {
                "c999": "Use C_999 OR non-C_999 treatment-function detail, never both.",
                "nonc": "Retained and classified neutrally; exclude only for England-performance methodology.",
                "rtt_parts": "Not freely additive; different populations / event bases.",
                "part_2a_subset": "Part_2A is a subset of Part_2; never sum Part_2 + Part_2A.",
                "stock_vs_flow": "Part_2 / Part_2A are month-end snapshots; do not sum them across reporting months.",
                "missingness": "blank != zero; not-collected != zero.",
                "organisations": "Group / join on codes; names are labels only.",
            },
        },
        "row_level_quality_conditions": row_level,
        "dataset_level_diagnostics": {
            "mapping": _mapping_summary(frames),
            "wait_band_metadata_rows": int(len(meta)),
            "wait_band_open_ended": meta.loc[meta["is_open_ended"], "wait_band_label"].tolist(),
        },
        "dense_long_benchmark": long_result.as_dict(),
        "outputs": {
            "analytical_wide": ANALYTICAL_WIDE_PARQUET,
            "waiting_band_long": WAITING_BAND_LONG_PARQUET,
            "wait_band_metadata": WAIT_BAND_METADATA_PARQUET,
            "report_json": TRANSFORM_REPORT_JSON,
            "report_md": TRANSFORM_REPORT_MD,
            "manifest": PHASE4_MANIFEST,
        },
        "determinism": {
            "logical": (
                "Across any valid block_rows (including a non-divisible final "
                "block): identical schema, rows, values, NA states, analytical "
                "ordering and lineage."),
            "physical_byte_repeatability": (
                "Byte-identical rtt_analytical_wide.parquet / "
                "wait_band_metadata.parquet / rtt_waiting_band_long.parquet only "
                "under a fixed writer + environment + block_rows. Changing "
                "block_rows changes the long file's Parquet row-group structure "
                "and therefore its hash; the wide and metadata files are "
                "unaffected."),
            "intentionally_variable_report_fields": list(VARIABLE_REPORT_FIELDS),
        },
    }
    return report


def deterministic_report_view(report: dict) -> dict:
    """Return the analytical-content view of the report — dropping every field
    in :data:`VARIABLE_REPORT_FIELDS` (timestamps, wall-clock durations, peak
    allocation, output paths, block-size-dependent physical layout). Two runs of
    ``run_phase4`` against the same verified Phase 3 generation produce an
    identical deterministic view regardless of ``block_rows``."""
    r = _copy.deepcopy(report)
    for dotted in VARIABLE_REPORT_FIELDS:
        node = r
        parts = dotted.split(".")
        for p in parts[:-1]:
            node = node.get(p) if isinstance(node, dict) else None
            if node is None:
                break
        if isinstance(node, dict):
            node.pop(parts[-1], None)
    return r


def render_report_markdown(report: dict) -> str:
    """A concise human-readable rendering of :func:`build_transformation_report`."""
    L: list[str] = []
    a = L.append
    ii = report["input_integrity"]
    ti = report["transformation_integrity"]
    mi = report["missingness"]
    sd = report["semantic_diagnostics"]
    bm = report["dense_long_benchmark"]

    a("# Phase 4 — transformation & data-quality summary")
    a("")
    a(f"_Generated {report['generated_utc']}. Reproducible from the verified "
      f"Phase 3 publication; no substantive waiting-time analysis._")
    a("")
    a("## Input integrity")
    a(f"- Phase 3 publication verified: **{ii['phase3_publication_verified']}** "
      f"(`generation_id` `{ii['phase3_generation_id'][:16]}…`)")
    a(f"- Consumed Phase 3 Parquet SHA-256 (verified snapshot): "
      f"`{ii['phase3_consumed_parquet_sha256'][:16]}…`")
    a(f"- Source months: {', '.join(ii['source_months'])}")
    a(f"- Input rows / columns: **{ii['input_rows']:,}** / {ii['input_columns']}")
    a(f"- Output-set binding: `{PHASE4_MANIFEST}` (verify with "
      f"`verify_phase4_publication`)")
    a("")
    a("## Transformation integrity")
    a(f"- Analytical-wide: **{ti['analytical_wide_rows']:,} rows** × "
      f"{ti['analytical_wide_columns']} cols — row conservation "
      f"**{ti['wide_row_conservation_ok']}**")
    a(f"- Candidate key `{' · '.join(ti['candidate_key'])}` unique: "
      f"**{ti['candidate_key_unique']}**")
    a(f"- `reporting_period_start_date` dtype: `{ti['reporting_period_start_date_dtype']}`")
    a(f"- Waiting-band-long: **{ti['waiting_band_long_rows']:,} rows** "
      f"(expected {ti['waiting_band_long_expected_rows']:,}, "
      f"= wide × {ti['long_rows_per_parent']}) — cardinality "
      f"**{ti['long_cardinality_ok']}**")
    if ti.get("persisted_long_validation"):
        pv = ti["persisted_long_validation"]
        a(f"- Persisted-long validation (authoritative, streamed from disk): "
          f"{pv['rows']:,} rows in {pv['batches']} batches — "
          f"{pv['numeric_cells']:,} numeric cells ({pv['explicit_zero_cells']:,} zero), "
          f"{pv['source_na_cells']:,} source-NA — mismatches "
          f"{pv['value_mismatches']}/{pv['na_state_mismatches']}/{pv['identity_mismatches']}")
    if ti.get("long_cell_reconciliation"):
        r = ti["long_cell_reconciliation"]
        a(f"- In-memory long/wide reconciliation (secondary diagnostic): "
          f"{r['both_numeric']:,} numeric cells, {r['explicit_zero']:,} explicit zeros, "
          f"{r['both_missing']:,} source-NA — mismatches "
          f"{r['value_mismatches']}/{r['na_state_mismatches']}")
    a("")
    a("## Missingness (blank ≠ zero — no blanket fillna(0))")
    a(f"- Rows with every waiting band missing: **{mi['rows_all_bands_missing']:,}**")
    a(f"- Rows with `Total` missing: **{mi['rows_total_missing']:,}**")
    a(f"- Rows with `Total All` missing: **{mi['rows_total_all_missing']:,}**")
    a(f"- Dense-long `pathway_count`: {mi['long_pathway_count_explicit_zero']:,} explicit "
      f"zeros vs {mi['long_pathway_count_source_na']:,} source-NA (kept distinct)")
    a("")
    a("## Semantic diagnostics")
    a("### Part_2A ⊆ Part_2 (P2-U7 — preserved & flagged, never capped)")
    a("| Month | Part_2A groups | no usable Part_2 comparator | conformant | violations | keys |")
    a("|---|---|---|---|---|---|")
    for m, d in sd["part_2a_subset_by_month"].items():
        a(f"| {m} | {d['n_part_2a_groups']} | {d['n_without_matching_part_2']} | "
          f"{d['n_conformant']} | {d['n_violations']} | "
          f"{'; '.join(d['violation_keys']) or '—'} |")
    a("")
    a(f"_`dq_part2a_no_matching_part2` = {sd['dq_part2a_no_matching_part2_meaning']}._")
    a("")
    a("### C_999 / NONC coverage by month")
    a("| Month | C_999 rows (%) | NONC rows (%) |")
    a("|---|---|---|")
    for m in sd["c999_coverage_by_month"]:
        c = sd["c999_coverage_by_month"][m]
        n = sd["nonc_coverage_by_month"][m]
        a(f"| {m} | {c['rows']:,} ({c['share_pct']}%) | {n['rows']:,} ({n['share_pct']}%) |")
    a("")
    a("## Row-level data-quality / condition flags")
    a("| Flag | Rows | Classification |")
    a("|---|---|---|")
    notes = {
        "dq_all_bands_missing": "factual condition flag — structurally expected for Part_3 (bands not collected)",
        "dq_total_missing": "factual condition flag — structurally expected for Parts 2/2A/3 (Total not collected)",
        "dq_part2a_gt_part2": "anomalous source condition (P2-U7) — values preserved, never capped",
        "dq_part2a_no_matching_part2": "anomalous source condition — no usable Part_2 comparator",
    }
    for flag in DQ_FLAG_COLS:
        a(f"| `{flag}` | {report['row_level_quality_conditions'][flag]['total']:,} "
          f"| {notes[flag]} |")
    a("")
    a("## Dense-long benchmark (run-dependent — see determinism section)")
    a(f"- Rows: **{bm['rows']:,}** · Parquet: **{bm['parquet_bytes'] / 1e6:.1f} MB** "
      f"(zstd) · build+write: **{bm['build_write_seconds']} s**")
    a(f"- Blocks: {bm['n_blocks']} × {bm['block_rows']:,} wide rows · row-group rows: "
      f"{bm['row_group_rows']:,} · peak Python alloc: {bm['peak_tracemalloc_mib']} MiB")
    a(f"- Read-back rows: {bm['read_back_rows']:,} · cardinality ok: "
      f"**{bm['cardinality_ok']}**")
    a("")
    a("## Determinism")
    a(f"- **Logical:** {report['determinism']['logical']}")
    a(f"- **Physical byte repeatability:** {report['determinism']['physical_byte_repeatability']}")
    a(f"- **Intentionally variable report fields:** "
      f"{', '.join(report['determinism']['intentionally_variable_report_fields'])}")
    a("")
    a("## Aggregation rules carried forward")
    for k, v in sd["aggregation_rules"].items():
        a(f"- **{k}**: {v}")
    a("")
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# P4-A03 — coherent, atomic Phase 4 publication (staged, manifest last)
# --------------------------------------------------------------------------- #

#: The canonical Phase 4 output set — logical key -> canonical local filename.
#: The manifest may **not** redefine this (P4-R03); ``verify_phase4_publication``
#: requires exactly these keys, at exactly these filenames.
REQUIRED_MANIFEST_OUTPUTS: dict[str, str] = {
    "analytical_wide": ANALYTICAL_WIDE_PARQUET,
    "wait_band_metadata": WAIT_BAND_METADATA_PARQUET,
    "waiting_band_long": WAITING_BAND_LONG_PARQUET,
    "report_json": TRANSFORM_REPORT_JSON,
    "report_md": TRANSFORM_REPORT_MD,
}
_PARQUET_OUTPUT_KEYS = ("analytical_wide", "wait_band_metadata", "waiting_band_long")
_REPORT_OUTPUT_KEYS = ("report_json", "report_md")


def _parquet_meta(path: str | Path) -> dict[str, object]:
    pf = pq.ParquetFile(str(path))
    return {
        "rows": int(pf.metadata.num_rows),
        "columns": int(pf.metadata.num_columns),
        "column_names": [f.name for f in pf.schema_arrow],
        "schema": _schema_signature(pf.schema_arrow),
    }


def compute_phase4_generation_id(*, phase3_generation_id: str,
                                 phase3_consumed_parquet_sha256: str,
                                 analytical_wide_sha256: str,
                                 wait_band_metadata_sha256: str,
                                 analytical_wide_rows: int,
                                 waiting_band_long_rows: int,
                                 bands_per_parent: int = N_WAIT_BANDS) -> str:
    """The **single** definition of the Phase 4 logical generation identity
    (P4-R03). It is the analytical content: the verified Phase 3 input identity +
    the two block-size-independent, byte-deterministic data artifacts
    (analytical-wide, wait-band metadata) + the exact long cardinality — so it is
    stable across runs *and* across ``block_rows``. The long file's physical
    SHA-256 is bound separately in the manifest ``outputs`` but is deliberately
    not part of this identity (its content is fully determined by the wide frame
    + the frozen band contract, which ``validate_persisted_long`` proves).

    Both :func:`build_phase4_manifest` and :func:`verify_phase4_publication`
    call this over independently-validated inputs.
    """
    material = json.dumps(
        {"phase3_generation_id": phase3_generation_id,
         "phase3_consumed_parquet_sha256": phase3_consumed_parquet_sha256,
         "analytical_wide_sha256": analytical_wide_sha256,
         "wait_band_metadata_sha256": wait_band_metadata_sha256,
         "analytical_wide_rows": int(analytical_wide_rows),
         "waiting_band_long_rows": int(waiting_band_long_rows),
         "bands_per_parent": int(bands_per_parent)},
        sort_keys=True)
    return _hashlib.sha256(material.encode("utf-8")).hexdigest()


def build_phase4_manifest(vin: VerifiedInput, staged_dir: str | Path,
                          report: dict) -> dict[str, object]:
    """Build the Phase 4 generation manifest from the **staged** output set. It
    binds the consumed Phase 3 identity and the SHA-256 / schema / byte size /
    row+column count of every Phase 4 output into one generation. Written last by
    :func:`_commit_phase4_generation`; enforced by
    :func:`verify_phase4_publication`."""
    staged_dir = Path(staged_dir)
    outs: dict[str, dict[str, object]] = {}
    for key, fname in REQUIRED_MANIFEST_OUTPUTS.items():
        p = staged_dir / fname
        entry: dict[str, object] = {
            "file": fname, "sha256": _sha256_path(p), "bytes": p.stat().st_size,
        }
        if fname.endswith(".parquet"):
            entry.update(_parquet_meta(p))
        outs[key] = entry

    wide_rows = int(outs["analytical_wide"]["rows"])
    long_rows = int(outs["waiting_band_long"]["rows"])
    meta_rows = int(outs["wait_band_metadata"]["rows"])
    gen_id = compute_phase4_generation_id(
        phase3_generation_id=vin.generation_id,
        phase3_consumed_parquet_sha256=vin.parquet_sha256,
        analytical_wide_sha256=str(outs["analytical_wide"]["sha256"]),
        wait_band_metadata_sha256=str(outs["wait_band_metadata"]["sha256"]),
        analytical_wide_rows=wide_rows,
        waiting_band_long_rows=long_rows)

    return {
        "phase": 4,
        "phase4_generation_id": gen_id,
        "committed_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "phase3_input": {
            "generation_id": vin.generation_id,
            "consumed_parquet_sha256": vin.parquet_sha256,
            "combined_rows": vin.combined_rows,
        },
        "analytical_wide_rows": wide_rows,
        "wait_band_metadata_rows": meta_rows,
        "waiting_band_long_rows": long_rows,
        "bands_per_parent": N_WAIT_BANDS,
        "long_equals_wide_times_bands": long_rows == wide_rows * N_WAIT_BANDS,
        "outputs": outs,
        "consumer_note": (
            "valid iff verify_phase4_publication enforces the full contract: exactly the "
            f"{sorted(REQUIRED_MANIFEST_OUTPUTS)} outputs at their canonical filenames; every "
            "field type/value; bands_per_parent == 105; wait_band_metadata_rows == 105; "
            "waiting_band_long_rows == analytical_wide_rows * 105; combined_rows == "
            "analytical_wide_rows; each Parquet's actual sha256/bytes/rows/columns/schema; "
            "both reports present, hashed and (JSON) parseable and reconciled with this "
            "manifest; and phase4_generation_id recomputed from the identity material"),
    }


def _replace_with_retry(src: str | Path, dst: str | Path, *,
                        attempts: int = 12, base_delay: float = 0.1) -> None:
    """``os.replace`` with a bounded retry on a **transient** ``PermissionError``
    (Windows ``WinError 5``): OneDrive / antivirus / a concurrent reader can
    briefly lock the destination. Every other ``OSError`` — and a
    ``PermissionError`` that never clears — propagates. ``os.replace`` itself is
    still atomic; the retry only waits out a lock before it."""
    for i in range(attempts):
        try:
            _os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            _time.sleep(base_delay * (i + 1))


def _commit_phase4_generation(out_dir: str | Path, staged_dir: str | Path) -> None:
    """Atomically commit the staged Phase 4 output set into ``out_dir``.

    Rotates the current published set to ``*.prev`` **only if it currently
    verifies** (a failed retry never overwrites a good backup), then
    ``os.replace``s each output into place (with a bounded retry on a transient
    Windows lock — :func:`_replace_with_retry`) with :data:`PHASE4_MANIFEST`
    **last** — that final replace is the atomic commit point. A failure before
    the first replace leaves the previous generation intact; a failure during
    the replaces leaves a state that :func:`verify_phase4_publication` reports as
    invalid.
    """
    out_dir, staged_dir = Path(out_dir), Path(staged_dir)
    if verify_phase4_publication(out_dir).get("valid"):
        for f in PHASE4_OUTPUT_FILES:
            cur = out_dir / f
            if cur.exists():
                _shutil.copy2(cur, cur.with_name(cur.name + ".prev"))
    for f in PHASE4_OUTPUT_FILES[:-1]:
        _replace_with_retry(staged_dir / f, out_dir / f)
    _replace_with_retry(staged_dir / PHASE4_MANIFEST, out_dir / PHASE4_MANIFEST)   # marker LAST


def _is_int(x: object) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _pos_int(x: object) -> bool:
    return _is_int(x) and x > 0


def _hex64(x: object) -> bool:
    return isinstance(x, str) and len(x) == 64 and all(c in "0123456789abcdef" for c in x.lower())


class _Invalid(Exception):
    """Internal: a Phase 4 publication validation failure (structured, not a bug)."""


def verify_phase4_publication(out_dir: str | Path) -> dict[str, object]:
    """The consumer's Phase 4 validity gate — it enforces the **complete
    publication contract** (P4-R03), not merely hashes for whatever entries a
    manifest happens to list. A malformed manifest / publication always returns a
    structured ``{"valid": False, "reason": ...}`` — never a ``KeyError``.

    A published generation is **valid** iff:

    * the manifest exists and is a JSON object with `phase == 4`;
    * ``outputs`` has **exactly** the canonical keys
      (:data:`REQUIRED_MANIFEST_OUTPUTS`), each at its **canonical local
      filename** (no missing / extra / duplicate / redirected / traversal
      member), each entry well-formed;
    * every field's type and value is sane: ``phase4_generation_id`` 64-hex;
      ``phase3_input`` = {64-hex-ish ``generation_id`` string, 64-hex
      ``consumed_parquet_sha256``, positive int ``combined_rows``}; positive
      ``analytical_wide_rows`` / ``waiting_band_long_rows``;
      ``wait_band_metadata_rows == 105``; ``bands_per_parent == 105``;
      ``long_equals_wide_times_bands is True``;
      ``waiting_band_long_rows == analytical_wide_rows * 105``;
      ``combined_rows == analytical_wide_rows`` (Phase-3 row conservation);
    * **every physical output claim is re-checked against the file on disk** —
      SHA-256, byte size, and (Parquet) row count, column count, ordered column
      names, serialized schema; the long Parquet must carry the canonical
      :func:`_long_arrow_schema`; both reports exist, hash and (JSON) parse;
    * the JSON report **reconciles** with the manifest — Phase 3
      ``generation_id`` / ``consumed_parquet_sha256`` / input rows and the
      analytical-wide / long row counts;
    * ``phase4_generation_id`` **recomputes** from
      :func:`compute_phase4_generation_id` over the independently re-validated
      identity material (so a forged id, or a forged Phase 3 identity that the
      hashed report contradicts, fails).

    A mixed generation (new wide + old long) fails: the manifest, written last,
    either records the new hashes (old long mismatches) or was not updated (new
    wide mismatches the stale manifest). Interruption states are coherent-old /
    coherent-new / detectably-invalid.
    """
    out_dir = Path(out_dir)
    try:
        return _verify_phase4_publication(out_dir)
    except _Invalid as exc:
        return {"valid": False, "reason": str(exc)}


def _verify_phase4_publication(out_dir: Path) -> dict[str, object]:
    mpath = out_dir / PHASE4_MANIFEST
    if not mpath.exists():
        raise _Invalid("no phase4 manifest")
    try:
        m = json.loads(mpath.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise _Invalid(f"unreadable phase4 manifest: {exc}") from None
    if not isinstance(m, dict):
        raise _Invalid("phase4 manifest is not a JSON object")
    if m.get("phase") != 4:
        raise _Invalid(f"manifest 'phase' is {m.get('phase')!r}, expected 4")

    # --- exact required output set at canonical filenames ------------------- #
    outs = m.get("outputs")
    if not isinstance(outs, dict):
        raise _Invalid("manifest 'outputs' is not an object")
    if set(outs) != set(REQUIRED_MANIFEST_OUTPUTS):
        missing = sorted(set(REQUIRED_MANIFEST_OUTPUTS) - set(outs))
        extra = sorted(set(outs) - set(REQUIRED_MANIFEST_OUTPUTS))
        raise _Invalid(f"manifest outputs keys wrong: missing={missing} extra={extra}")
    seen_files: set[str] = set()
    for key, canonical in REQUIRED_MANIFEST_OUTPUTS.items():
        entry = outs[key]
        if not isinstance(entry, dict):
            raise _Invalid(f"manifest output entry {key!r} is not an object")
        fname = entry.get("file")
        if fname != canonical:                       # rejects redirect / traversal / rename
            raise _Invalid(f"output {key!r} file is {fname!r}, expected the canonical {canonical!r}")
        if fname in seen_files:
            raise _Invalid(f"duplicate output filename {fname!r}")
        seen_files.add(fname)
        if not _hex64(entry.get("sha256")):
            raise _Invalid(f"output {key!r} sha256 is missing / not 64-hex")
        if not _pos_int(entry.get("bytes")):
            raise _Invalid(f"output {key!r} bytes is missing / not a positive int")

    # --- manifest field contract ------------------------------------------- #
    if not _hex64(m.get("phase4_generation_id")):
        raise _Invalid("phase4_generation_id missing / not 64-hex")
    p3 = m.get("phase3_input")
    if not isinstance(p3, dict):
        raise _Invalid("manifest 'phase3_input' is not an object")
    if not isinstance(p3.get("generation_id"), str) or not p3["generation_id"]:
        raise _Invalid("phase3_input.generation_id missing / not a non-empty string")
    if not _hex64(p3.get("consumed_parquet_sha256")):
        raise _Invalid("phase3_input.consumed_parquet_sha256 missing / not 64-hex")
    if not _pos_int(p3.get("combined_rows")):
        raise _Invalid("phase3_input.combined_rows missing / not a positive int")
    wide_rows = m.get("analytical_wide_rows")
    long_rows = m.get("waiting_band_long_rows")
    if not _pos_int(wide_rows):
        raise _Invalid("analytical_wide_rows missing / not a positive int")
    if not _pos_int(long_rows):
        raise _Invalid("waiting_band_long_rows missing / not a positive int")
    if m.get("wait_band_metadata_rows") != N_WAIT_BANDS:
        raise _Invalid(f"wait_band_metadata_rows is {m.get('wait_band_metadata_rows')!r}, "
                       f"expected {N_WAIT_BANDS}")
    if m.get("bands_per_parent") != N_WAIT_BANDS:
        raise _Invalid(f"bands_per_parent is {m.get('bands_per_parent')!r}, expected {N_WAIT_BANDS}")
    if m.get("long_equals_wide_times_bands") is not True:
        raise _Invalid("long_equals_wide_times_bands is not True")
    if long_rows != wide_rows * N_WAIT_BANDS:
        raise _Invalid(f"waiting_band_long_rows ({long_rows}) != analytical_wide_rows "
                       f"({wide_rows}) * {N_WAIT_BANDS}")
    if p3["combined_rows"] != wide_rows:
        raise _Invalid(f"phase3_input.combined_rows ({p3['combined_rows']}) != "
                       f"analytical_wide_rows ({wide_rows}) — row conservation")

    # --- every physical output claim re-checked against disk --------------- #
    on_disk_sha: dict[str, str] = {}
    for key, canonical in REQUIRED_MANIFEST_OUTPUTS.items():
        entry = outs[key]
        f = out_dir / canonical
        if not f.exists():
            raise _Invalid(f"output {canonical!r} is missing on disk")
        actual_sha = _sha256_path(f)
        on_disk_sha[key] = actual_sha
        if actual_sha != entry["sha256"]:
            raise _Invalid(f"{canonical!r} SHA-256 does not match the committed generation "
                           "— the output set is not coherent")
        if f.stat().st_size != entry["bytes"]:
            raise _Invalid(f"{canonical!r} byte size disagrees with the manifest")
        if key in _PARQUET_OUTPUT_KEYS:
            try:
                pm = _parquet_meta(f)
            except Exception as exc:                       # noqa: BLE001 - report, don't crash
                raise _Invalid(f"cannot read {canonical!r} Parquet metadata: {exc}") from None
            for fld in ("rows", "columns", "column_names", "schema"):
                if pm[fld] != entry.get(fld):
                    raise _Invalid(f"{canonical!r} {fld} disagrees with the manifest")
        if key == "wait_band_metadata" and entry.get("rows") != N_WAIT_BANDS:
            raise _Invalid(f"wait_band_metadata Parquet has {entry.get('rows')} rows, "
                           f"expected {N_WAIT_BANDS}")
        if key == "analytical_wide" and entry.get("rows") != wide_rows:
            raise _Invalid("analytical_wide Parquet row count disagrees with the manifest header")
        if key == "waiting_band_long":
            if entry.get("rows") != long_rows:
                raise _Invalid("waiting_band_long Parquet row count disagrees with the manifest header")
            if entry.get("column_names") != list(LONG_COLUMNS) \
                    or entry.get("schema") != _schema_signature(_long_arrow_schema()):
                raise _Invalid("waiting_band_long does not carry the canonical long schema")

    # --- reconcile the hashed JSON report with the manifest --------------- #
    try:
        rep = json.loads((out_dir / TRANSFORM_REPORT_JSON).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise _Invalid(f"phase4_transformation_report.json is not parseable: {exc}") from None
    if not isinstance(rep, dict):
        raise _Invalid("phase4_transformation_report.json is not a JSON object")
    ii = rep.get("input_integrity", {})
    ti = rep.get("transformation_integrity", {})
    if not isinstance(ii, dict) or not isinstance(ti, dict):
        raise _Invalid("report is missing input_integrity / transformation_integrity")
    if ii.get("phase3_generation_id") != p3["generation_id"]:
        raise _Invalid("report phase3_generation_id disagrees with the manifest")
    if ii.get("phase3_consumed_parquet_sha256") != p3["consumed_parquet_sha256"]:
        raise _Invalid("report phase3_consumed_parquet_sha256 disagrees with the manifest")
    if ii.get("input_rows") != wide_rows:
        raise _Invalid("report input_rows disagrees with analytical_wide_rows / combined_rows")
    if ti.get("analytical_wide_rows") != wide_rows:
        raise _Invalid("report analytical_wide_rows disagrees with the manifest")
    if ti.get("waiting_band_long_rows") != long_rows:
        raise _Invalid("report waiting_band_long_rows disagrees with the manifest")

    # --- recompute the logical generation id ----------------------------- #
    recomputed = compute_phase4_generation_id(
        phase3_generation_id=p3["generation_id"],
        phase3_consumed_parquet_sha256=p3["consumed_parquet_sha256"],
        analytical_wide_sha256=on_disk_sha["analytical_wide"],
        wait_band_metadata_sha256=on_disk_sha["wait_band_metadata"],
        analytical_wide_rows=wide_rows,
        waiting_band_long_rows=long_rows)
    if recomputed != m["phase4_generation_id"]:
        raise _Invalid("phase4_generation_id does not match the recomputed logical identity")

    return {
        "valid": True,
        "phase4_generation_id": m["phase4_generation_id"],
        "phase3_generation_id": p3["generation_id"],
        "analytical_wide_rows": wide_rows,
        "waiting_band_long_rows": long_rows,
    }


def restore_previous_phase4_generation(out_dir: str | Path) -> dict[str, object]:
    """Roll the published Phase 4 output set back to the ``*.prev`` copies. The
    backup is **verified before** it is restored (in a scratch dir), then
    restored and re-verified; ``restored`` is ``True`` only on a verified
    restore. Distinguishes: no complete backup / backup invalid / restore-copy
    failed / restored & valid."""
    out_dir = Path(out_dir)
    prevs = [out_dir / (f + ".prev") for f in PHASE4_OUTPUT_FILES]
    if not all(p.exists() for p in prevs):
        return {"restored": False, "reason": "no complete previous generation (.prev) present"}
    scratch = Path(_tempfile.mkdtemp(prefix="nhs_rtt_p4prev_"))
    try:
        for f, p in zip(PHASE4_OUTPUT_FILES, prevs):
            _shutil.copy2(p, scratch / f)
        prev_v = verify_phase4_publication(scratch)
    finally:
        _shutil.rmtree(scratch, ignore_errors=True)
    if not prev_v.get("valid"):
        return {"restored": False,
                "reason": f"the previous generation (.prev) does not verify: {prev_v.get('reason')}",
                "prev_verify": prev_v}
    try:
        for f, p in zip(PHASE4_OUTPUT_FILES, prevs):
            _shutil.copy2(p, out_dir / f)
    except OSError as exc:
        return {"restored": False, "reason": f"restore copy failed: {exc}"}
    final_v = verify_phase4_publication(out_dir)
    return {"restored": bool(final_v.get("valid")), "verify": final_v,
            "reason": None if final_v.get("valid") else "restored files did not verify"}


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

@dataclass
class Phase4Result:
    ok: bool
    input_verification: dict
    generation_id: str
    input_rows: int
    consumed_parquet_sha256: str | None = None
    wide_rows: int | None = None
    wide_columns: int | None = None
    wide_key_unique: bool | None = None
    long_result: LongWriteResult | None = None
    persisted_validation: dict | None = None
    long_reconciliation: dict | None = None
    band_metadata_rows: int | None = None
    report: dict | None = None
    manifest: dict | None = None
    phase4_generation_id: str | None = None
    publication: dict | None = None
    outputs: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def render_text(self) -> str:  # pragma: no cover - presentation only
        L = ["=== Phase 4 — transformation & analytical dataset ===",
             f"input verified   : {self.input_verification.get('valid')}  "
             f"(phase3 generation {self.generation_id[:16]}…)",
             f"consumed sha256  : {(self.consumed_parquet_sha256 or '')[:16]}…",
             f"input rows       : {self.input_rows:,}",
             f"analytical-wide  : {self.wide_rows:,} rows × {self.wide_columns} cols  "
             f"key unique={self.wide_key_unique}"]
        if self.long_result:
            r = self.long_result
            L.append(f"waiting-band-long: {r.rows:,} rows (= wide × {N_WAIT_BANDS}); "
                     f"{r.parquet_bytes / 1e6:.1f} MB; {r.build_write_seconds}s; "
                     f"peak {r.peak_tracemalloc_mib} MiB")
        if self.persisted_validation:
            pv = self.persisted_validation
            L.append(f"persisted-long   : validated {pv['rows']:,} rows in {pv['batches']} "
                     f"batches, 0 mismatches ({pv['seconds']}s)")
        if self.long_reconciliation:
            L.append(f"in-memory recon  : {self.long_reconciliation['both_numeric']:,} numeric, "
                     f"0 mismatches")
        L.append(f"band metadata    : {self.band_metadata_rows} rows")
        if self.phase4_generation_id:
            L.append(f"phase4 generation: {self.phase4_generation_id[:16]}…  "
                     f"publication valid={self.publication and self.publication.get('valid')}")
        for k, v in self.outputs.items():
            L.append(f"  output {k}: {v}")
        for n in self.notes:
            L.append(f"note: {n}")
        L.append(f"OVERALL OK       : {self.ok}")
        return "\n".join(L)


def run_phase4(*, interim_dir: str | Path = "data/interim",
               out_dir: str | Path = "data/processed",
               block_rows: int = 40_000,
               write_long: bool = True,
               reconcile_long: bool = False) -> Phase4Result:
    """End-to-end Phase 4.

    1. **Verified snapshot** — ``load_verified_publication`` binds the input to a
       private immutable snapshot that passed ``crossmonth.verify_publication``
       (P4-A01).
    2. **Transform** — build the analytical-wide dataset and the wait-band
       metadata.
    3. **Stage** — write every output into a private ``.staging-*`` directory
       under ``out_dir`` (nothing in ``out_dir`` is touched yet).
    4. **Validate the persisted long** — ``validate_persisted_long`` streams the
       staged Parquet from disk and checks every derived cell against the
       verified wide / source (P4-A02, mandatory).
    5. **Manifest + atomic commit** — build :data:`PHASE4_MANIFEST` binding the
       Phase 3 identity and every output's SHA-256 / schema / rows; rotate any
       current generation to ``*.prev``; ``os.replace`` the outputs into place
       with the manifest **last** (P4-A03).
    6. **Self-verify** — ``verify_phase4_publication`` must confirm the committed
       generation is coherent.

    On failure before the first replace the previous generation is intact; a
    failure during the replaces leaves a state ``verify_phase4_publication``
    reports as invalid. The Phase 3 publication in ``interim_dir`` is read-only
    and never written. ``reconcile_long=True`` additionally runs the heavier
    in-memory ``reconcile_long_against_wide`` diagnostic.
    """
    interim_dir, out_dir = Path(interim_dir), Path(out_dir)
    if out_dir.resolve() == interim_dir.resolve():
        raise TransformError("Phase 4 out_dir must not be the Phase 3 interim_dir")
    out_dir.mkdir(parents=True, exist_ok=True)

    vin = load_verified_publication(interim_dir)
    res = Phase4Result(ok=True, input_verification=vin.verification,
                       generation_id=vin.generation_id, input_rows=vin.combined_rows,
                       consumed_parquet_sha256=vin.parquet_sha256)

    wide = build_analytical_wide(vin)
    res.wide_rows, res.wide_columns = len(wide), wide.shape[1]
    krep = candidate_key_report(wide, CANDIDATE_KEY)
    res.wide_key_unique = bool(krep["is_unique"] and krep["usable"])
    meta = wait_band_metadata()
    res.band_metadata_rows = len(meta)

    if not write_long:
        # dev-only partial run: wide + metadata, NO staged/coherent publication
        wide.to_parquet(out_dir / ANALYTICAL_WIDE_PARQUET, engine="pyarrow", index=False)
        meta.to_parquet(out_dir / WAIT_BAND_METADATA_PARQUET, engine="pyarrow", index=False)
        res.outputs["analytical_wide"] = str(out_dir / ANALYTICAL_WIDE_PARQUET)
        res.outputs["wait_band_metadata"] = str(out_dir / WAIT_BAND_METADATA_PARQUET)
        res.notes.append(
            "write_long=False: partial dev run — dense-long, persisted validation, "
            "report and the Phase 4 manifest were skipped; this is NOT a coherent, "
            "verifiable Phase 4 publication.")
        return res

    staging = out_dir / f".staging-{_os.getpid()}-{_time.time_ns()}"
    staging.mkdir(parents=True, exist_ok=True)
    try:
        wide.to_parquet(staging / ANALYTICAL_WIDE_PARQUET, engine="pyarrow", index=False)
        meta.to_parquet(staging / WAIT_BAND_METADATA_PARQUET, engine="pyarrow", index=False)
        long_stg = staging / WAITING_BAND_LONG_PARQUET
        res.long_result = write_waiting_band_long(
            wide, long_stg, meta=meta, block_rows=block_rows, benchmark=True)

        # P4-A02 — mandatory authoritative validation of the *persisted* artifact
        res.persisted_validation = validate_persisted_long(long_stg, wide, meta)

        if reconcile_long:
            res.long_reconciliation = reconcile_long_against_wide(
                wide, pd.read_parquet(long_stg, engine="pyarrow"), meta=meta)

        report = build_transformation_report(
            vin, wide, res.long_result, meta,
            persisted_validation=res.persisted_validation,
            long_reconciliation=res.long_reconciliation)
        (staging / TRANSFORM_REPORT_JSON).write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8")
        (staging / TRANSFORM_REPORT_MD).write_text(
            render_report_markdown(report), encoding="utf-8")
        res.report = report

        manifest = build_phase4_manifest(vin, staging, report)
        (staging / PHASE4_MANIFEST).write_text(
            json.dumps(manifest, indent=2), encoding="utf-8")
        res.manifest = manifest
        res.phase4_generation_id = manifest["phase4_generation_id"]

        _commit_phase4_generation(out_dir, staging)
        res.publication = verify_phase4_publication(out_dir)
        if not res.publication.get("valid"):
            res.ok = False
            raise Phase4PublicationError(
                f"published Phase 4 generation failed self-verification: {res.publication}")

        for key, fname in (("analytical_wide", ANALYTICAL_WIDE_PARQUET),
                           ("wait_band_metadata", WAIT_BAND_METADATA_PARQUET),
                           ("waiting_band_long", WAITING_BAND_LONG_PARQUET),
                           ("report_json", TRANSFORM_REPORT_JSON),
                           ("report_md", TRANSFORM_REPORT_MD),
                           ("manifest", PHASE4_MANIFEST)):
            res.outputs[key] = str(out_dir / fname)
        return res
    finally:
        _shutil.rmtree(staging, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI
    import argparse
    p = argparse.ArgumentParser(description="Phase 4 — transformation & analytical dataset")
    p.add_argument("--interim-dir", default="data/interim")
    p.add_argument("--out-dir", default="data/processed")
    p.add_argument("--block-rows", type=int, default=40_000)
    p.add_argument("--no-long", action="store_true",
                   help="dev-only partial run (wide + metadata; no coherent publication)")
    p.add_argument("--reconcile-long", action="store_true",
                   help="also run the heavier in-memory long<->wide reconciliation")
    p.add_argument("--verify", action="store_true",
                   help="just verify the existing Phase 4 publication and exit")
    ns = p.parse_args(argv)
    if ns.verify:
        v = verify_phase4_publication(ns.out_dir)
        print(json.dumps(v, indent=2))
        return 0 if v.get("valid") else 1
    res = run_phase4(interim_dir=ns.interim_dir, out_dir=ns.out_dir,
                     block_rows=ns.block_rows, write_long=not ns.no_long,
                     reconcile_long=ns.reconcile_long)
    print(res.render_text())
    return 0 if res.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
