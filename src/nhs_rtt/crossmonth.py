"""Phase 3 — cross-month diagnostics, deterministic combination and the
CSV -> Parquet publication boundary for NHS RTT monthly extracts.

Depends on :mod:`nhs_rtt.ingest` (discovery / provenance / per-month
acceptance) and :mod:`nhs_rtt.semantics` (the frozen Phase 1/2 contracts). The
import direction is one-way: ``crossmonth`` imports ``ingest``; ``ingest`` only
reaches back into ``crossmonth`` lazily inside its CLI ``main()``.

What this module does **not** do (Phase 4+): no waiting-band reshaping, no
cleaning or imputation, no dimensional model, no KPIs. The combined frame keeps
the wide NHS source structure and raw values; it only gains four provenance
columns.
"""

from __future__ import annotations

import datetime as _dt
import hashlib as _hashlib
import json
import os as _os
import shutil as _shutil
import tempfile as _tempfile
import time as _time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pyarrow.parquet as _pq

from nhs_rtt import ingest as _ing
from nhs_rtt import semantics as _sem
from nhs_rtt.ingest import (RESERVED_PROVENANCE_COLUMNS, AcceptanceReport,
                            DiscoveryResult, SourceRegistry, accept_month,
                            discover_sources, sha256_file)
from nhs_rtt.semantics import (CANDIDATE_KEY, COMMISSIONER_COL,
                               COMMISSIONER_PARENT_COL, PROVIDER_COL,
                               RTT_PART_COL, TFC_COL, load_rtt_csv,
                               part_2a_subset_conformance, week_band_columns)

__all__ = [
    "PROVENANCE_COLS", "MonthPayload", "GENERATION_MARKER",
    "RowConservationError", "CombinedKeyError", "ReservedColumnError",
    "IntendedSourceError", "PublicationError",
    "mapping_diagnostics", "coverage_diagnostics", "part2a_subset_diagnostics",
    "combine_months", "write_combined_parquet", "deterministic_manifest_view",
    "roundtrip_check", "verify_publication", "restore_previous_generation",
    "Phase3Result", "run_phase3",
]

#: The only columns Phase 3 adds. Everything else is the raw NHS structure.
#:
#: * ``source_file``       basename of the accepted raw CSV
#: * ``source_sha256``     SHA-256 of that file's exact raw bytes
#: * ``reporting_month``   canonical ``"YYYY-MM"`` (agreed filename == Period)
#: * ``source_row_index``  **0-based position of the row among the source
#:   file's parsed CSV data records** (what ``pandas.read_csv`` yields) — *not*
#:   a physical line number; quoted embedded newlines do not shift it.
PROVENANCE_COLS = ["source_file", "source_sha256", "reporting_month", "source_row_index"]
assert set(PROVENANCE_COLS) == set(RESERVED_PROVENANCE_COLUMNS), \
    "PROVENANCE_COLS and ingest.RESERVED_PROVENANCE_COLUMNS must agree"

#: Commit marker written last by :func:`write_combined_parquet`; a publication
#: is valid iff this file exists and its recorded hashes match the on-disk
#: Parquet and sidecar (see :func:`verify_publication`).
GENERATION_MARKER = "rtt_combined.generation.json"
_SIDECAR_NAME = "rtt_combined.ingest_manifest.json"

_NAME_COL = {
    PROVIDER_COL: "Provider Org Name",
    COMMISSIONER_COL: "Commissioner Org Name",
    TFC_COL: "Treatment Function Name",
    "Provider Parent Org Code": "Provider Parent Name",
    COMMISSIONER_PARENT_COL: "Commissioner Parent Name",
}
_DIM_LABEL = {
    PROVIDER_COL: "provider",
    COMMISSIONER_COL: "commissioner",
    TFC_COL: "treatment_function",
    "Provider Parent Org Code": "provider_parent",
    COMMISSIONER_PARENT_COL: "commissioner_parent",
}


class RowConservationError(AssertionError):
    """A combine step did not preserve exact row counts."""


class CombinedKeyError(AssertionError):
    """The candidate key is incomplete or not unique on the combined frame."""


class ReservedColumnError(ValueError):
    """A source frame already carries a reserved Phase 3 provenance column
    (P3-A05) — publishing would overwrite a source value."""


class IntendedSourceError(AssertionError):
    """The combined payloads do not match the required intended source set
    (P3-A01)."""


class PublicationError(RuntimeError):
    """The staged publication failed validation or an atomic commit step."""


@dataclass
class MonthPayload:
    """One accepted month ready to be combined."""

    reporting_month: str        # "YYYY-MM"
    source_file: str            # basename
    source_sha256: str
    df: pd.DataFrame            # exactly as loaded by nhs_rtt.semantics.load_rtt_csv


# --------------------------------------------------------------------------- #
# Cross-month diagnostics (warnings, never rejection)
# --------------------------------------------------------------------------- #

def _pairs_by_month(frames: dict[str, pd.DataFrame], code_col: str,
                    name_col: str) -> dict[str, set[tuple[object, object]]]:
    out: dict[str, set[tuple[object, object]]] = {}
    for month, df in frames.items():
        if code_col not in df.columns or name_col not in df.columns:
            continue
        sub = df[[code_col, name_col]].astype(object).where(pd.notna(df[[code_col, name_col]]), None)
        out[month] = set(map(tuple, sub.drop_duplicates().to_numpy().tolist()))
    return out


def mapping_diagnostics(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Cross-month code<->name and membership diagnostics for the five
    code/name dimensions. **Everything here is a warning, never a rejection.**
    "Codes identify; names label" — changes are surfaced, never auto-resolved.
    ``<NA>`` names are kept explicitly (not dropped).

    Returns three consolidated frames (each carries a ``dimension`` column):

    * ``code_name_changes``      one code carrying more than one name across the
      months provided (with the per-month names);
    * ``name_code_collisions``   one non-blank name carried by more than one
      code (``scope`` = ``within_month`` / ``cross_month``);
    * ``membership_changes``     codes that appear / disappear between
      consecutive months.
    """
    months_sorted = sorted(frames)
    code_name_rows: list[dict[str, object]] = []
    collision_rows: list[dict[str, object]] = []
    membership_rows: list[dict[str, object]] = []

    for code_col, name_col in _NAME_COL.items():
        dim = _DIM_LABEL[code_col]
        pbm = _pairs_by_month(frames, code_col, name_col)
        if not pbm:
            continue

        # code -> {month -> {names}}
        code_names: dict[object, dict[str, set[object]]] = {}
        name_codes_all: dict[object, set[object]] = {}
        name_codes_by_month: dict[str, dict[object, set[object]]] = {m: {} for m in pbm}
        codes_by_month: dict[str, set[object]] = {}
        for month, pairs in pbm.items():
            codes_by_month[month] = set()
            for code, name in pairs:
                code_names.setdefault(code, {}).setdefault(month, set()).add(name)
                codes_by_month[month].add(code)
                if name is not None and str(name).strip() != "":
                    name_codes_all.setdefault(name, set()).add(code)
                    name_codes_by_month[month].setdefault(name, set()).add(code)

        for code, per_month in sorted(code_names.items(), key=lambda kv: str(kv[0])):
            all_names = {n for s in per_month.values() for n in s}
            if len(all_names) > 1:
                code_name_rows.append({
                    "dimension": dim, "code": code,
                    "months_present": ",".join(sorted(per_month)),
                    "n_distinct_names": len(all_names),
                    "names_by_month": " | ".join(
                        f"{m}:{'/'.join(sorted('' if x is None else str(x) for x in per_month[m]))}"
                        for m in sorted(per_month)),
                })

        for name, codes in sorted(name_codes_all.items(), key=lambda kv: str(kv[0])):
            if len(codes) > 1:
                within = any(len(name_codes_by_month[m].get(name, set())) > 1 for m in pbm)
                collision_rows.append({
                    "dimension": dim, "name": name,
                    "n_distinct_codes": len(codes),
                    "codes": ",".join(sorted(str(c) for c in codes)),
                    "scope": "within_month" if within else "cross_month",
                })

        for a, b in zip(months_sorted, months_sorted[1:]):
            if a not in codes_by_month or b not in codes_by_month:
                continue
            appeared = sorted(str(c) for c in codes_by_month[b] - codes_by_month[a])
            disappeared = sorted(str(c) for c in codes_by_month[a] - codes_by_month[b])
            if appeared or disappeared:
                membership_rows.append({
                    "dimension": dim, "from_month": a, "to_month": b,
                    "n_appeared": len(appeared), "n_disappeared": len(disappeared),
                    "appeared": ",".join(appeared[:20]) + (" ..." if len(appeared) > 20 else ""),
                    "disappeared": ",".join(disappeared[:20]) + (" ..." if len(disappeared) > 20 else ""),
                })

    return {
        "code_name_changes": pd.DataFrame(
            code_name_rows,
            columns=["dimension", "code", "months_present", "n_distinct_names",
                     "names_by_month"]),
        "name_code_collisions": pd.DataFrame(
            collision_rows,
            columns=["dimension", "name", "n_distinct_codes", "codes", "scope"]),
        "membership_changes": pd.DataFrame(
            membership_rows,
            columns=["dimension", "from_month", "to_month", "n_appeared",
                     "n_disappeared", "appeared", "disappeared"]),
    }


def coverage_diagnostics(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Per month: row count, RTT-part counts, treatment-function coverage and
    missingness prevalence for the tail measures / all-band-blank rows.
    Diagnostic only — nothing here rejects a file."""
    rows: list[dict[str, object]] = []
    for month in sorted(frames):
        df = frames[month]
        bands = week_band_columns(df.columns.tolist())
        part_counts = df[RTT_PART_COL].value_counts().to_dict()
        rows.append({
            "reporting_month": month,
            "n_rows": int(len(df)),
            "n_treatment_function_codes": int(df[TFC_COL].nunique()),
            "n_providers": int(df[PROVIDER_COL].nunique()),
            "n_commissioners": int(df[COMMISSIONER_COL].nunique()),
            **{f"rows_{p}": int(part_counts.get(p, 0))
               for p in ("Part_1A", "Part_1B", "Part_2", "Part_2A", "Part_3")},
            "pct_Total_blank": round(df["Total"].isna().mean() * 100, 3),
            "pct_unknown_clock_blank": round(
                df["Patients with unknown clock start date"].isna().mean() * 100, 3),
            "pct_TotalAll_blank": round(df["Total All"].isna().mean() * 100, 3),
            "pct_rows_all_bands_blank": round(
                df[bands].isna().all(axis=1).mean() * 100, 3),
        })
    return pd.DataFrame(rows)


def part2a_subset_diagnostics(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Run the frozen :func:`nhs_rtt.semantics.part_2a_subset_conformance` per
    month and collate the counts + any violations. Carries **P2-U7**: values are
    preserved and flagged, never capped."""
    rows: list[dict[str, object]] = []
    for month in sorted(frames):
        conf = part_2a_subset_conformance(frames[month])
        viol = conf["violations"]
        rows.append({
            "reporting_month": month,
            "n_part_2a_groups": conf["n_part_2a_groups"],
            "n_without_matching_part_2": conf["n_without_matching_part_2"],
            "n_conformant": conf["n_conformant"],
            "n_violations": conf["n_violations"],
            "violation_keys": "; ".join(
                f"{r[PROVIDER_COL]}/{r[COMMISSIONER_COL]}/{r[TFC_COL]}"
                f"(2A={r['part_2a']}>2={r['part_2']})"
                for _, r in viol.iterrows()) if len(viol) else "",
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Deterministic combination
# --------------------------------------------------------------------------- #

def combine_months(payloads: list[MonthPayload], *,
                   require_months: list[str] | None = None) -> pd.DataFrame:
    """Concatenate accepted months into one wide frame in deterministic order.

    * months ascending by ``reporting_month``; within a month, the source row
      order is preserved;
    * each row gains :data:`PROVENANCE_COLS` (``source_row_index`` is the 0-based
      parsed data-row position within its file);
    * **no source frame may already carry a reserved provenance column**
      (:class:`ReservedColumnError`, P3-A05);
    * when ``require_months`` is given, the payload months must equal it exactly
      (:class:`IntendedSourceError`, P3-A01);
    * **row conservation** is asserted: ``len(combined) == sum(len(payload.df))``;
    * the candidate key is asserted **complete and unique** on the combined
      frame — directly (all columns present, no missing cell, no duplicate) and
      via :func:`nhs_rtt.semantics.candidate_key_report`;
    * no measure column is transformed; ``<NA>`` missingness is preserved.

    A rejected month must simply be absent from ``payloads`` — it can never
    partially contaminate the output.
    """
    if not payloads:
        raise ValueError("combine_months: no accepted months")
    ordered = sorted(payloads, key=lambda p: p.reporting_month)

    for p in ordered:
        clash = [c for c in RESERVED_PROVENANCE_COLUMNS if c in p.df.columns]
        if clash:
            raise ReservedColumnError(
                f"{p.source_file}: source frame already contains reserved Phase 3 "
                f"provenance column(s) {clash}")

    if require_months is not None:
        got = sorted({p.reporting_month for p in ordered})
        want = sorted(set(require_months))
        if got != want:
            raise IntendedSourceError(
                f"combine payload months {got} != required intended months {want}")

    parts: list[pd.DataFrame] = []
    for p in ordered:
        part = p.df.reset_index(drop=True).copy()
        n = len(part)
        part["source_file"] = pd.array([p.source_file] * n, dtype="string")
        part["source_sha256"] = pd.array([p.source_sha256] * n, dtype="string")
        part["reporting_month"] = pd.array([p.reporting_month] * n, dtype="string")
        part["source_row_index"] = pd.array(range(n), dtype="Int64")
        parts.append(part)

    combined = pd.concat(parts, ignore_index=True)

    expected_total = sum(len(p.df) for p in ordered)
    if len(combined) != expected_total:
        raise RowConservationError(
            f"combined {len(combined)} rows != sum of source rows {expected_total}")

    missing = [c for c in CANDIDATE_KEY if c not in combined.columns]
    if missing:
        raise CombinedKeyError(f"candidate key column(s) absent after combine: {missing}")
    n_key_na = int(combined[CANDIDATE_KEY].isna().any(axis=1).sum())
    if n_key_na:
        raise CombinedKeyError(f"{n_key_na} combined row(s) have a missing candidate-key cell")
    n_dup = int(combined.duplicated(subset=CANDIDATE_KEY).sum())
    if n_dup:
        raise CombinedKeyError(f"{n_dup} duplicate candidate-key row(s) after combine")
    krep = _sem.candidate_key_report(combined, CANDIDATE_KEY)
    if not krep["usable"]:
        raise CombinedKeyError(
            f"candidate_key_report says not usable: is_unique={krep.get('is_unique')} "
            f"n_key_cells_missing={krep.get('n_key_cells_missing')} "
            f"n_duplicate_groups={krep.get('n_duplicate_groups')}")

    return combined


# --------------------------------------------------------------------------- #
# CSV -> Parquet publication boundary
# --------------------------------------------------------------------------- #

def deterministic_manifest_view(manifest: dict | str | Path) -> dict:
    """Return only the reproducible part of an ingest manifest (drops the
    ``run`` block, which carries a wall-clock timestamp). Use this in
    determinism comparisons."""
    if isinstance(manifest, (str, Path)):
        manifest = json.loads(Path(manifest).read_text(encoding="utf-8"))
    return {k: v for k, v in manifest.items() if k != "run"}


def _sha256_path(p: str | Path, *, _chunk: int = 1 << 20) -> str:
    h = _hashlib.sha256()
    with Path(p).open("rb") as fh:
        for block in iter(lambda: fh.read(_chunk), b""):
            h.update(block)
    return h.hexdigest()


def _deterministic_block(combined: pd.DataFrame,
                         payloads: list[MonthPayload] | None) -> dict[str, object]:
    krep = _sem.candidate_key_report(combined, CANDIDATE_KEY)
    months_meta = []
    for p in sorted(payloads or [], key=lambda x: x.reporting_month):
        months_meta.append({
            "reporting_month": p.reporting_month, "source_file": p.source_file,
            "source_sha256": p.source_sha256, "rows": int(len(p.df)),
        })
    return {
        "combined_rows": int(len(combined)),
        "column_count": int(combined.shape[1]),
        "provenance_columns": PROVENANCE_COLS,
        "candidate_key": CANDIDATE_KEY,
        "candidate_key_unique": bool(krep["is_unique"]),
        "candidate_key_usable": bool(krep["usable"]),
        "months": months_meta,
        "rows_by_month": combined["reporting_month"].value_counts().sort_index().to_dict(),
    }


def write_combined_parquet(combined: pd.DataFrame, out_dir: str | Path, *,
                           filename: str = "rtt_combined.parquet",
                           payloads: list[MonthPayload] | None = None,
                           write_sidecar: bool = True) -> dict[str, object]:
    """Atomically publish ``combined`` as a single logical generation (P3-A04).

    Protocol:

    1. write the Parquet and (unless ``write_sidecar=False``) the evidence
       sidecar into a private staging directory under ``out_dir``;
    2. validate the staged Parquet with :func:`roundtrip_check`;
    3. compute a ``generation_id`` from the staged Parquet digest + the
       deterministic evidence block, and write a **generation marker** recording
       ``generation_id``, the SHA-256 of *both* staged files, and
       ``combined_rows``;
    4. copy the existing published trio to ``*.prev`` **only if it currently
       verifies** (P3-R02) — a failed retry never overwrites a good backup;
    5. ``os.replace`` the three files into place — **marker last**. That final
       ``os.replace`` is the atomic commit point.

    A consumer trusts the pair iff :func:`verify_publication` returns
    ``{"valid": True}``. Interruption semantics: a failure *before* the first
    replace leaves the previous valid generation intact; a failure *during* the
    replaces leaves the final paths invalid (detected by
    :func:`verify_publication`); completion of the marker-last commit leaves the
    new generation valid even if the caller later fails. A staged-validation
    failure raises :class:`PublicationError`; a failed ``os.replace`` propagates
    its ``OSError``.

    The Parquet preserves the wide structure, nullable dtypes, ``<NA>``
    missingness and the deterministic row order from :func:`combine_months`.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    final_parquet = out_dir / filename
    final_sidecar = out_dir / _SIDECAR_NAME
    final_marker = out_dir / GENERATION_MARKER

    staging = out_dir / f".staging-{_os.getpid()}-{_time.time_ns()}"
    staging.mkdir(parents=True, exist_ok=True)
    try:
        stg_parquet = staging / filename
        combined.to_parquet(stg_parquet, engine="pyarrow", index=False)
        rt = roundtrip_check(stg_parquet, combined)
        if not rt["ok"]:
            raise PublicationError(f"staged Parquet failed roundtrip: {rt['problems']}")

        parquet_sha = _sha256_path(stg_parquet)
        det = _deterministic_block(combined, payloads)
        gen_id = _hashlib.sha256(
            (parquet_sha + "|" + json.dumps(det, sort_keys=True, default=str)).encode("utf-8")
        ).hexdigest()

        result: dict[str, object] = {
            "parquet_path": str(final_parquet), "rows": int(len(combined)),
            "columns": int(combined.shape[1]), "generation_id": gen_id,
            "roundtrip": rt,
        }
        stg_sidecar = stg_marker = None
        if write_sidecar:
            manifest = {
                "artifact": filename,
                "deterministic": det,
                "run": {
                    "generated_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                    "generation_id": gen_id,
                    "tool": "nhs_rtt.crossmonth.write_combined_parquet",
                    "note": "observed ingestion evidence; the intended source set is data/raw/manifest.json",
                },
            }
            stg_sidecar = staging / _SIDECAR_NAME
            stg_sidecar.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
            sidecar_sha = _sha256_path(stg_sidecar)
            marker = {
                "generation_id": gen_id,
                "parquet": filename, "parquet_sha256": parquet_sha,
                "sidecar": _SIDECAR_NAME, "sidecar_sha256": sidecar_sha,
                "combined_rows": int(len(combined)),
                "committed_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                "consumer_note": "valid iff these hashes match the on-disk files, "
                                 "the sidecar run.generation_id equals generation_id, "
                                 "and combined_rows == sidecar deterministic.combined_rows "
                                 "== the Parquet row count (see verify_publication)",
            }
            stg_marker = staging / GENERATION_MARKER
            stg_marker.write_text(json.dumps(marker, indent=2), encoding="utf-8")
            result["manifest"] = manifest
            result["sidecar_path"] = str(final_sidecar)
            result["generation_path"] = str(final_marker)

        # preserve the previous **known-valid** generation as *.prev (P3-R02):
        # only rotate when the current published trio actually verifies, so a
        # failed retry cannot overwrite a good backup with an invalid trio.
        if write_sidecar and verify_publication(out_dir, filename).get("valid"):
            for f in (final_parquet, final_sidecar, final_marker):
                _shutil.copy2(f, f.with_name(f.name + ".prev"))

        # atomic commit: marker LAST
        _os.replace(stg_parquet, final_parquet)
        if write_sidecar:
            _os.replace(stg_sidecar, final_sidecar)
            _os.replace(stg_marker, final_marker)
            result["publication"] = verify_publication(out_dir)
            if not result["publication"]["valid"]:
                raise PublicationError(
                    f"published generation failed self-verification: {result['publication']}")
        return result
    finally:
        _shutil.rmtree(staging, ignore_errors=True)


def _parquet_num_rows(path: str | Path) -> int:
    """Cheap row count from Parquet file metadata (no full read)."""
    return int(_pq.ParquetFile(str(path)).metadata.num_rows)


def _is_int(x: object) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def verify_publication(out_dir: str | Path,
                       filename: str = "rtt_combined.parquet") -> dict[str, object]:
    """A published pair is **valid** iff, for the generation marker:

    * it exists, is well-formed and its required fields have the right types;
    * `parquet_sha256` / `sidecar_sha256` equal the SHA-256 of the on-disk
      Parquet and sidecar (P3-A04);
    * the sidecar's `run.generation_id` equals the marker's `generation_id`;
    * `combined_rows` **is reconciled** against the sidecar's
      `deterministic.combined_rows` and the actual Parquet row metadata — any
      disagreement is invalid (P3-R01).

    Every field returned in a `valid: True` result describes one consistent
    generation. Interruption before replacement can leave the previous valid
    generation; interruption during replacement can leave a detectable invalid
    mixed state. Completion of the marker-last commit leaves the new valid
    generation. Consumers use a publication only when this function returns
    valid.
    """
    out_dir = Path(out_dir)
    parquet = out_dir / filename
    sidecar = out_dir / _SIDECAR_NAME
    marker = out_dir / GENERATION_MARKER
    if not marker.exists():
        return {"valid": False, "reason": "no generation marker"}
    try:
        m = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"valid": False, "reason": f"unreadable generation marker: {exc}"}
    if not isinstance(m, dict):
        return {"valid": False, "reason": "generation marker is not a JSON object"}
    for k in ("generation_id", "parquet_sha256", "sidecar_sha256"):
        if not isinstance(m.get(k), str) or not m[k]:
            return {"valid": False, "reason": f"marker field {k!r} missing or not a string"}
    if not _is_int(m.get("combined_rows")) or m["combined_rows"] < 0:
        return {"valid": False, "reason": "marker field 'combined_rows' missing or not a non-negative int"}

    for f, key in ((parquet, "parquet_sha256"), (sidecar, "sidecar_sha256")):
        if not f.exists():
            return {"valid": False, "reason": f"{f.name} is missing"}
        if _sha256_path(f) != m[key]:
            return {"valid": False,
                    "reason": f"{f.name} does not match the committed generation "
                              "(SHA-256 mismatch) — the pair is not one valid generation"}
    try:
        sc = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"valid": False, "reason": f"unreadable sidecar: {exc}"}
    if sc.get("run", {}).get("generation_id") != m["generation_id"]:
        return {"valid": False, "reason": "sidecar generation_id disagrees with the marker"}

    sidecar_rows = sc.get("deterministic", {}).get("combined_rows")
    if not _is_int(sidecar_rows):
        return {"valid": False, "reason": "sidecar deterministic.combined_rows missing or not an int"}
    try:
        parquet_rows = _parquet_num_rows(parquet)
    except Exception as exc:                                   # noqa: BLE001 - report, don't crash
        return {"valid": False, "reason": f"cannot read Parquet row metadata: {exc}"}
    if not (m["combined_rows"] == sidecar_rows == parquet_rows):
        return {"valid": False,
                "reason": f"row-count disagreement: marker={m['combined_rows']} "
                          f"sidecar={sidecar_rows} parquet={parquet_rows}"}

    return {"valid": True, "generation_id": m["generation_id"], "combined_rows": parquet_rows}


def restore_previous_generation(out_dir: str | Path,
                                filename: str = "rtt_combined.parquet") -> dict[str, object]:
    """Roll the published trio back to the ``*.prev`` copies. The backup is
    **verified before** it is restored, and success is reported only if the
    restored trio itself verifies (P3-R02). Outcomes are distinguished:
    no backup / backup invalid / restore-copy failed / restored & valid."""
    out_dir = Path(out_dir)
    trio = [out_dir / filename, out_dir / _SIDECAR_NAME, out_dir / GENERATION_MARKER]
    prevs = [f.with_name(f.name + ".prev") for f in trio]
    if not all(p.exists() for p in prevs):
        return {"restored": False, "reason": "no complete previous generation (.prev) present"}

    # verify the backup in a scratch dir before touching the live trio
    scratch = Path(_tempfile.mkdtemp(prefix="nhs_rtt_prevcheck_"))
    try:
        for f, p in zip(trio, prevs):
            _shutil.copy2(p, scratch / f.name)
        prev_v = verify_publication(scratch, filename)
    finally:
        _shutil.rmtree(scratch, ignore_errors=True)
    if not prev_v.get("valid"):
        return {"restored": False,
                "reason": f"the previous generation (.prev) does not verify: {prev_v.get('reason')}",
                "prev_verify": prev_v}

    try:
        for f, p in zip(trio, prevs):
            _shutil.copy2(p, f)
    except OSError as exc:
        return {"restored": False, "reason": f"restore copy failed: {exc}"}
    final_v = verify_publication(out_dir, filename)
    return {"restored": bool(final_v.get("valid")), "verify": final_v,
            "reason": None if final_v.get("valid") else "restored files did not verify"}


def roundtrip_check(parquet_path: str | Path, combined: pd.DataFrame) -> dict[str, object]:
    """Reload the Parquet and assert **data-level** equality with ``combined``
    (shape, columns, values and missingness) — not byte-for-byte file hashing."""
    back = pd.read_parquet(parquet_path, engine="pyarrow")
    problems: list[str] = []
    if back.shape != combined.shape:
        problems.append(f"shape {back.shape} != {combined.shape}")
    if list(back.columns) != list(combined.columns):
        problems.append("column order/name differs")
    if not problems:
        na_back, na_orig = back.isna().sum(), combined.isna().sum()
        if not na_back.equals(na_orig):
            problems.append("missingness (per-column NA counts) differs")
        try:
            pd.testing.assert_frame_equal(
                back.astype(object).where(pd.notna(back), None),
                combined.reset_index(drop=True).astype(object).where(pd.notna(combined), None),
                check_dtype=False)
        except AssertionError as exc:
            problems.append(f"values differ: {str(exc).splitlines()[0]}")
    return {"ok": not problems, "problems": problems}


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

@dataclass
class Phase3Result:
    ok: bool
    discovery: DiscoveryResult
    resolutions: dict[str, object] = field(default_factory=dict)       # month -> RevisionResolution | error str
    acceptance: dict[str, AcceptanceReport] = field(default_factory=dict)   # month -> report (chosen file)
    payloads: list[MonthPayload] = field(default_factory=list)
    intended_months: list[str] = field(default_factory=list)          # months with a selected registry entry
    required_months: list[str] = field(default_factory=list)          # what this run must fully accept
    requested_subset: list[str] | None = None                         # explicit subset, if any
    accepted_months: list[str] = field(default_factory=list)
    missing_intended: list[str] = field(default_factory=list)         # required but not accepted (P3-A01)
    unexpected_months: list[str] = field(default_factory=list)        # discovered but unregistered
    combined_rows: int | None = None
    combined_key_unique: bool | None = None
    parquet: dict[str, object] | None = None
    roundtrip: dict[str, object] | None = None
    publication: dict[str, object] | None = None
    diagnostics: dict[str, object] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def render_text(self) -> str:  # pragma: no cover - presentation only
        L: list[str] = []
        a = L.append
        a("=== Phase 3 - multi-month ingestion ===")
        a(f"raw dir            : {self.discovery.raw_dir}")
        a(f"production files   : {self.discovery.production_files}")
        if self.discovery.malformed_candidates:
            a(f"MALFORMED (surfaced, not ingested): {self.discovery.malformed_candidates}")
        if self.discovery.ignored:
            a(f"ignored (unrelated): {self.discovery.ignored}")
        a(f"intended (selected): {self.intended_months}")
        a(f"required this run  : {self.required_months}"
          + ("  [explicit subset]" if self.requested_subset is not None else ""))
        if self.missing_intended:
            a(f"MISSING intended   : {self.missing_intended}")
        if self.unexpected_months:
            a(f"UNREGISTERED months: {self.unexpected_months}")
        a("")
        a("--- per month ---")
        for m in sorted(self.acceptance):
            r = self.acceptance[m]
            a(f"[{m}] {r.filename}")
            a(f"    sha256 observed : {r.sha256}")
            a(f"    sha256 expected : {r.expected_sha256} ({r.provenance_source})")
            a(f"    rows (loaded)   : {r.n_loaded_rows}   streamed: {r.n_data_rows}")
            a(f"    Period value    : {r.period_values}  -> canonical {r.reporting_month}")
            a(f"    105-band schema : {'OK' if r.schema_ok else 'FAIL'}  (bands={r.n_week_bands})")
            a(f"    candidate key   : {'usable' if r.candidate_key_usable else 'NOT usable'}")
            a(f"    ACCEPTED        : {r.accepted}")
            for b in r.blocking:
                a(f"      BLOCK: {b}")
            for w in r.warnings:
                a(f"      warn : {w}")
        for m, res in self.resolutions.items():
            if isinstance(res, str):
                a(f"[{m}] REVISION UNRESOLVED: {res}")
        a("")
        a("--- combined ---")
        a(f"included months   : {[p.reporting_month for p in sorted(self.payloads, key=lambda x: x.reporting_month)]}")
        a(f"combined rows     : {self.combined_rows}  "
          f"(sum of sources: {sum(len(p.df) for p in self.payloads)})")
        a(f"candidate key uniq: {self.combined_key_unique}")
        if self.parquet:
            a(f"parquet           : {self.parquet.get('parquet_path')}")
            a(f"generation_id     : {self.parquet.get('generation_id')}")
            a(f"roundtrip         : {self.roundtrip}")
            a(f"publication valid : {self.publication}")
        for k, v in self.diagnostics.items():
            if isinstance(v, pd.DataFrame):
                a(f"diagnostic '{k}': {len(v)} row(s)")
        a("")
        a(f"OVERALL OK        : {self.ok}")
        for n in self.notes:
            a(f"note: {n}")
        return "\n".join(L)


def run_phase3(*, raw_dir: str | Path = "data/raw",
               registry_path: str | Path = "data/raw/manifest.json",
               out_dir: str | Path = "data/interim",
               write_parquet: bool = True,
               require_months: list[str] | None = None) -> Phase3Result:
    """End-to-end Phase 3: discover -> reconcile against the intended source set
    -> per-month acceptance (with revision resolution) -> cross-month
    diagnostics -> deterministic combine -> atomic Parquet publication. Never
    commits, never writes a raw file.

    The registry (``data/raw/manifest.json``) is the **authoritative intended
    source set**. By default every reporting month with a ``selected`` entry
    must be present and accepted before a publication succeeds (P3-A01); pass
    ``require_months`` to run an explicit, recorded subset instead.

    ``ok`` is ``True`` only when the required intended set is fully accepted,
    every discovered month is accepted, no unregistered month is present, and
    the combine + roundtrip + publication self-verification all pass.
    """
    raw_dir = Path(raw_dir)
    registry = SourceRegistry.load(registry_path)
    disc = discover_sources(raw_dir)
    result = Phase3Result(ok=True, discovery=disc)

    registered_months = {e.reporting_period for e in registry.entries}
    result.intended_months = sorted({e.reporting_period for e in registry.entries if e.selected})
    if require_months is not None:
        result.requested_subset = sorted(set(require_months))
        result.required_months = list(result.requested_subset)
        result.notes.append(f"explicit requested subset: {result.required_months}")
    else:
        result.required_months = list(result.intended_months)

    if disc.malformed_candidates:
        result.notes.append(
            "malformed RTT-like filenames present and NOT ingested: "
            f"{disc.malformed_candidates}")

    result.unexpected_months = sorted(
        {dm.reporting_month for dm in disc.months} - registered_months)
    if result.unexpected_months:
        result.ok = False
        result.notes.append(
            f"discovered reporting month(s) not in the registry: {result.unexpected_months}")

    if not disc.months:
        result.ok = False
        result.notes.append("no production monthly files discovered")

    frames: dict[str, pd.DataFrame] = {}
    for dm in disc.months:
        observed = [(f, sha256_file(raw_dir / f)) for f in dm.files]
        try:
            resolution = registry.resolve_month(dm.reporting_month, observed)
        except _ing.AmbiguousRevisionError as exc:
            result.resolutions[dm.reporting_month] = str(exc)
            result.ok = False
            continue
        result.resolutions[dm.reporting_month] = resolution
        if resolution.note:
            result.notes.append(f"{dm.reporting_month}: {resolution.note}")

        rep = accept_month(raw_dir / resolution.chosen_file, registry=registry,
                           discovery_sha256=resolution.chosen_sha256)
        result.acceptance[dm.reporting_month] = rep
        if not rep.accepted:
            result.ok = False
            continue
        if rep.frame is None:                        # defensive (P3-A03)
            result.ok = False
            result.notes.append(f"{dm.reporting_month}: accepted report carries no bound frame")
            continue

        frames[dm.reporting_month] = rep.frame       # bound to rep.sha256; no re-read
        result.payloads.append(MonthPayload(
            reporting_month=dm.reporting_month,
            source_file=resolution.chosen_file,
            source_sha256=rep.sha256,
            df=rep.frame))

    # diagnostics on whatever was accepted
    if frames:
        result.diagnostics["mapping"] = mapping_diagnostics(frames)
        result.diagnostics["coverage"] = coverage_diagnostics(frames)
        result.diagnostics["part2a_subset"] = part2a_subset_diagnostics(frames)

    # reconcile intended vs accepted (P3-A01)
    required = set(result.required_months)
    result.accepted_months = sorted({p.reporting_month for p in result.payloads})
    result.missing_intended = sorted(required - set(result.accepted_months))
    if result.missing_intended:
        result.ok = False
        result.notes.append(
            f"intended source(s) missing or not accepted: {result.missing_intended} "
            "- publication withheld (a full-set run requires every selected intended month)")

    all_discovered_accepted = (
        len(result.acceptance) == len(disc.months)
        and bool(disc.months)
        and all(r.accepted for r in result.acceptance.values()))
    complete = (not result.missing_intended and not result.unexpected_months
                and all_discovered_accepted and required.issubset(result.accepted_months))

    combine_payloads = [p for p in result.payloads if p.reporting_month in required]
    if combine_payloads and complete:
        combined = combine_months(combine_payloads, require_months=sorted(required))
        result.combined_rows = int(len(combined))
        krep = _sem.candidate_key_report(combined, CANDIDATE_KEY)
        result.combined_key_unique = bool(krep["is_unique"] and krep["usable"])
        if write_parquet:
            result.parquet = write_combined_parquet(
                combined, out_dir, payloads=combine_payloads)
            result.roundtrip = result.parquet.get("roundtrip")
            result.publication = result.parquet.get("publication")
            if not (result.roundtrip or {}).get("ok") or not (result.publication or {}).get("valid"):
                result.ok = False
    else:
        result.ok = False
        result.notes.append(
            "combined dataset NOT produced - intended-source completeness / "
            "acceptance not satisfied")

    return result
