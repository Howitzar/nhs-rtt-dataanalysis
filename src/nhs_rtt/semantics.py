"""Phase 2 — dataset semantics, grain and arithmetic-validation helpers.

Reusable analysis logic for establishing *what a row means* and *when rows and
values may be aggregated* in an NHS RTT monthly provider extract. Read-only with
respect to the raw file; the blank-vs-value distinction is preserved everywhere
(blank loads as pandas ``<NA>``; explicit ``0`` stays ``0``).

Scope guard (Phase 2): this module **describes and validates**. It does not
clean, reshape the week-band columns, impute blanks, build a key, or produce
KPIs. Those are later phases.

Reading arithmetic results
--------------------------
A reconciliation result distinguishes an **arithmetic identity** from a
**semantic conclusion**:

* ``observed_band_sum`` is the sum of the *non-missing* band cells — a stated
  **skip-missing numerical convention**, NOT evidence that a blank band means
  "zero patients". For the June banded parts every row has at least one
  observed band, so this equals filling blanks with 0; that equality is a
  property of June's population, not of what a blank encodes.
* ``policy = "strict"`` rows exclude any row with a missing operand and report
  how many were excluded. ``policy = "missing-as-zero"`` rows apply an explicit
  zero-contribution convention to a missing operand and say so.
* ``verdict`` is only ``HOLDS`` when its subset was fully evaluated with zero
  numeric mismatches. Otherwise it is ``PARTIAL (...)``, ``FAILS`` or ``n/a``.

Key references (NHS England; see ``docs/rtt_semantics.md`` for the full table):

* **S1** Recording and reporting RTT waiting times for consultant-led elective
  care, v5.0, 11 Feb 2025 (PRN01045) — §10.1.1.1–3, §10.1.4, §10.1.5, §10.1.7,
  §10.1.8, Annex B.
* **S5** RTT statistics user guidance — "Reproducibility and derived measures"
  (within-18-weeks formula, ``Commissioner Org Code <> NONC``, denominator),
  "Navigating published files" (NONC submission not mandatory),
  "Unknown clock starts" (completed pathways only).
* **S6** RTT Statistical Press Notice, **June 2026** (published 13 Aug 2026) —
  Table 1 same-month unestimated totals.
"""

from __future__ import annotations

import csv as _csv
import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from nhs_rtt.profile import check_week_bucket_sequence, classify_columns

# --------------------------------------------------------------------------- #
# Column / value constants (observed in rtt_2026_06.csv; documented where noted)
# --------------------------------------------------------------------------- #

TOTAL_COL = "Total"
UNKNOWN_CLOCK_COL = "Patients with unknown clock start date"
TOTAL_ALL_COL = "Total All"
NUMERIC_TAIL_COLS = [TOTAL_COL, UNKNOWN_CLOCK_COL, TOTAL_ALL_COL]

RTT_PART_COL = "RTT Part Type"
TFC_COL = "Treatment Function Code"
TFN_COL = "Treatment Function Name"
PROVIDER_COL = "Provider Org Code"
COMMISSIONER_COL = "Commissioner Org Code"
COMMISSIONER_PARENT_COL = "Commissioner Parent Org Code"
PERIOD_COL = "Period"

#: Treatment Function Code whose name is the literal "Total". NHS validates
#: "the total is a sum over all treatment functions" (S1 Annex B); S1 does not
#: name the literal CSV code ``C_999`` — that association is from the June data.
TOTAL_TFC = "C_999"
TOTAL_TFN = "Total"

#: Parts that carry the 105 weekly bands (S1 §10.1.1.3: bands "added to Parts
#: 1A, 1B, 2 and 2A"). Part_3 carries only a count.
BANDED_PARTS = ("Part_1A", "Part_1B", "Part_2", "Part_2A")
COMPLETED_PARTS = ("Part_1A", "Part_1B")
INCOMPLETE_PARTS = ("Part_2", "Part_2A")
COUNT_ONLY_PARTS = ("Part_3",)

#: Non-English commissioner code (S1 §10.1.8 / §10.1.9.2). Present in the raw
#: return; excluded from England published performance (S5). Submission is
#: **not mandatory** (S5), so observed NONC rows are not a complete record.
NONC_CODE = "NONC"

#: Candidate composite key. ``Period`` is constant within one monthly file but
#: is part of the key across files (and does not distinguish revised releases).
CANDIDATE_KEY = [PERIOD_COL, PROVIDER_COL, COMMISSIONER_COL, RTT_PART_COL, TFC_COL]

#: June 2026 Statistical Press Notice, Table 1 (England, **not** including
#: estimates for the two non-submitting trusts RHQ, RA9), published 13 Aug 2026.
JUNE_2026_SPN_UNESTIMATED = {
    "incomplete_total": 7_147_562,
    "incomplete_within_18wk_pct": 65.8,
    "completed_admitted_total": 318_650,
    "completed_non_admitted_total": 1_307_837,
    "new_rtt_periods_total": 1_930_912,
}

_BAND_RANGE_RE = re.compile(r"^\s*Gt\s+(\d+)\s+To\s+(\d+)\s+Weeks", re.IGNORECASE)
_BAND_OPEN_RE = re.compile(r"^\s*Gt\s+(\d+)\s+Weeks", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Week-band column identification (programmatic — never hard-coded)
# --------------------------------------------------------------------------- #

def week_band_columns(columns: list[str], *, require_clean_sequence: bool = True) -> list[str]:
    """Return the week-band column names, in header order.

    Uses the Phase 1 header classifier. When ``require_clean_sequence`` is set
    (default) a malformed band sequence raises ``ValueError`` so a future file
    cannot silently analyse with a broken band set.
    """
    cols = classify_columns(list(columns))["week_bucket_columns"]
    if require_clean_sequence:
        warns = check_week_bucket_sequence(cols)
        if warns:
            raise ValueError("week-band sequence is not clean: " + "; ".join(warns))
    return cols


def parse_week_band(col: str) -> tuple[int, int | None]:
    """``'Gt 17 To 18 Weeks SUM 1'`` -> ``(17, 18)``; ``'Gt 104 Weeks SUM 1'`` -> ``(104, None)``."""
    m = _BAND_RANGE_RE.match(col)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = _BAND_OPEN_RE.match(col)
    if m:
        return int(m.group(1)), None
    raise ValueError(f"not a week-band column: {col!r}")


def bands_up_to_weeks(columns: list[str], max_weeks: int) -> list[str]:
    """Ranged bands whose upper bound is ``<= max_weeks`` (e.g. 18 -> 'Gt 00 To
    01' … 'Gt 17 To 18'). S1 §10.1.7: a 126-day / 18-week wait sits in the
    17-18 band, so "within 18 weeks" == bands with upper bound ≤ 18.
    """
    out = []
    for c in week_band_columns(columns, require_clean_sequence=False):
        lo, hi = parse_week_band(c)
        if hi is not None and hi <= max_weeks:
            out.append(c)
    return out


def expected_week_band_names() -> list[str]:
    """The canonical **105** NHS RTT week-band column names, in order:
    ``Gt 00 To 01 Weeks SUM 1`` … ``Gt 103 To 104 Weeks SUM 1`` (104 unit
    bands) then the open-ended ``Gt 104 Weeks SUM 1``."""
    names = [f"Gt {lo:02d} To {lo + 1:02d} Weeks SUM 1" for lo in range(104)]
    names.append("Gt 104 Weeks SUM 1")
    return names


def check_expected_band_schema(header: list[str]) -> list[str]:
    """Problems if ``header`` does not carry **exactly** the canonical 105-band
    schema (:func:`expected_week_band_names`), in order.

    Contiguity alone is not enough for the Phase 2 extract contract: this
    rejects zero bands, a single valid-looking band, a missing first (``0-1``)
    or open-ended (``>104``) band, a missing interior band, a duplicate band,
    and any unexpected band-like column. An empty list means the schema is
    complete and correctly ordered.
    """
    problems: list[str] = []
    expected = expected_week_band_names()
    found = classify_columns(list(header))["week_bucket_columns"]
    if found == expected:
        return problems

    dups = sorted(h for h, n in Counter(found).items() if n > 1)
    if dups:
        problems.append(f"duplicate week-band column(s): {dups}")
    if len(found) != len(expected):
        problems.append(f"expected {len(expected)} week-band columns, found {len(found)}")
    missing = [c for c in expected if c not in set(found)]
    if missing:
        problems.append("missing expected week-band column(s): "
                        + ", ".join(missing[:5]) + (" …" if len(missing) > 5 else ""))
    extra = [c for c in found if c not in set(expected)]
    if extra:
        problems.append("unexpected week-band-like column(s): "
                        + ", ".join(extra[:5]) + (" …" if len(extra) > 5 else ""))
    if not problems and found != expected:
        problems.append("week-band columns present but out of the expected order")
    return problems


# --------------------------------------------------------------------------- #
# Extract validation (Phase 2 acceptance checks — not a Phase 3 ingester)
# --------------------------------------------------------------------------- #

def validate_extract(path: str | Path, *, encoding: str = "utf-8-sig",
                     required_key: list[str] | None = None,
                     required_measures: list[str] | None = None,
                     require_full_band_schema: bool = True) -> dict[str, object]:
    """Structural acceptance checks on a raw RTT CSV, run **before** pandas can
    mangle duplicate headers or coerce lexical NA tokens.

    Checks: no duplicate header names; required key + measure columns present;
    a clean band sequence; and (``require_full_band_schema=True``, the Phase 2
    production gate) the **exact canonical 105-band schema**
    (:func:`check_expected_band_schema`). Returns ``{"ok": bool, "problems":
    [...], ...}``; callers decide whether to proceed.
    """
    path = Path(path)
    required_key = required_key or CANDIDATE_KEY
    required_measures = required_measures or NUMERIC_TAIL_COLS
    with path.open("r", newline="", encoding=encoding) as fh:
        raw_header = next(_csv.reader(fh))

    problems: list[str] = []
    dupes = sorted(h for h, c in Counter(raw_header).items() if c > 1)
    if dupes:
        problems.append(f"duplicate header name(s): {dupes}")
    hset = set(raw_header)
    for c in required_key:
        if c not in hset:
            problems.append(f"missing key column: {c!r}")
    for c in required_measures:
        if c not in hset:
            problems.append(f"missing measure column: {c!r}")
    try:
        bands = week_band_columns(raw_header, require_clean_sequence=True)
    except ValueError as exc:
        problems.append(str(exc))
        bands = []
    if require_full_band_schema:
        problems.extend(check_expected_band_schema(raw_header))
    return {
        "path": str(path),
        "n_header_columns": len(raw_header),
        "duplicate_headers": dupes,
        "n_week_bands": len(bands),
        "expected_band_schema_ok": not check_expected_band_schema(raw_header),
        "problems": problems,
        "ok": not problems,
    }


# --------------------------------------------------------------------------- #
# Loading (read-only, blank-preserving, explicit NA policy)
# --------------------------------------------------------------------------- #

def load_rtt_csv(path: str | Path, *, encoding: str = "utf-8-sig",
                 validate: bool = True, require_full_band_schema: bool = True) -> pd.DataFrame:
    """Load an RTT monthly extract with an **explicit** missing-value policy.

    * The only value treated as missing is the empty string (``keep_default_na
      =False, na_values=[""]``): a literal ``NULL`` / ``NA`` / ``NaN`` in a code
      column stays that literal string, not silently ``<NA>``.
    * Numeric columns (105 bands + Total + unknown + Total All) load as nullable
      ``Int64`` so blank (``<NA>``) and explicit ``0`` are always distinct.
    * ``validate=True`` runs :func:`validate_extract` first and raises
      ``ValueError`` on any structural problem (duplicate headers, missing key/
      measure columns, broken band sequence, and — with
      ``require_full_band_schema=True``, the default production gate — anything
      other than the exact canonical 105-band schema) so a malformed future
      file cannot receive a false semantic pass. Unit tests that only exercise
      *other* logic on a miniature synthetic CSV pass
      ``require_full_band_schema=False``.
    * Negative values are rejected (S1 Annex B: no negative/decimal values).

    The raw file is opened read-only and never written.
    """
    path = Path(path)
    if validate:
        report = validate_extract(path, encoding=encoding,
                                  require_full_band_schema=require_full_band_schema)
        if not report["ok"]:
            raise ValueError(f"{path.name}: not a valid RTT extract — "
                             + "; ".join(report["problems"]))

    header = pd.read_csv(path, nrows=0, encoding=encoding).columns.tolist()
    band_cols = week_band_columns(header)
    num_cols = band_cols + NUMERIC_TAIL_COLS
    dtypes: dict[str, str] = {c: "Int64" for c in num_cols if c in header}
    dtypes.update({c: "string" for c in header if c not in num_cols})
    df = pd.read_csv(path, dtype=dtypes, encoding=encoding,
                     keep_default_na=False, na_values=[""])

    present_num = [c for c in num_cols if c in df.columns]
    neg = int(df[present_num].lt(0).to_numpy(dtype="bool", na_value=False).sum())
    if neg:
        raise ValueError(f"{path.name}: {neg} negative value(s) in numeric columns "
                         "— not a valid RTT extract (Annex B forbids negatives)")
    return df


def assert_raw_unchanged(path: str | Path, expected_sha256: str | None = None) -> str:
    """Return the SHA-256 of ``path``; if ``expected_sha256`` is given, assert it
    matches. Used to prove Phase 2 never mutated the raw file."""
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise AssertionError(f"{Path(path).name} SHA-256 changed: {digest} != {expected_sha256}")
    return digest


# --------------------------------------------------------------------------- #
# Arithmetic reconciliation (with explicit coverage + missingness reporting)
# --------------------------------------------------------------------------- #

def observed_band_sum(df: pd.DataFrame, band_cols: list[str]) -> pd.Series:
    """Row-wise sum of the **observed (non-missing)** week-band cells.

    ``<NA>`` only when *every* band cell is missing (Part_3). This is a stated
    skip-missing numerical convention — it is not a claim about what a blank
    band means. See the module docstring.
    """
    return df[band_cols].sum(axis=1, min_count=1)


@dataclass
class ReconResult:
    """One candidate identity tested over a declared subset of rows."""

    part: str
    rule: str
    policy: str            # "strict" | "missing-as-zero"
    subset: str            # human description of which rows this covers
    n_in_subset: int
    n_evaluated: int        # rows with a genuine numeric comparison on both sides
    n_convention_rows: int  # rows where an *authorised* zero-fill was applied
    n_missing_operand: int  # rows in subset with a still-missing required operand
    n_excluded_missing: int  # == n_missing_operand (rows dropped from evaluation)
    n_match: int
    n_mismatch: int
    diff_min: int | None
    diff_max: int | None
    verdict: str

    def as_row(self) -> dict[str, object]:
        return {
            "part": self.part, "rule": self.rule, "policy": self.policy,
            "subset": self.subset,
            "n_in_subset": self.n_in_subset, "n_evaluated": self.n_evaluated,
            "n_convention_rows": self.n_convention_rows,
            "n_missing_operand": self.n_missing_operand,
            "n_excluded_missing": self.n_excluded_missing,
            "n_match": self.n_match, "n_mismatch": self.n_mismatch,
            "mismatch_pct": (round(100.0 * self.n_mismatch / self.n_evaluated, 4)
                             if self.n_evaluated else 0.0),
            "diff_min": self.diff_min, "diff_max": self.diff_max,
            "verdict": self.verdict,
        }


def _reconcile(lhs: pd.Series, rhs: pd.Series, subset: pd.Series, *, part: str,
               rule: str, policy: str, subset_desc: str,
               convention_applied: pd.Series | None = None) -> ReconResult:
    """Compare ``lhs`` vs ``rhs`` over ``subset``.

    ``lhs`` / ``rhs`` already carry **only** the caller's explicitly-authorised
    zero-fill (e.g. a blank unknown-clock contribution under D-016, or
    skip-missing band cells). A subset row is *evaluated* iff **both** ``lhs``
    and ``rhs`` are non-``<NA>`` after that authorised fill — i.e. a genuine
    numeric comparison. Any subset row still carrying a missing required operand
    (e.g. a missing ``Total All`` or ``Total``) is **excluded and counted**,
    for *both* policies; an unqualified ``HOLDS`` needs zero exclusions.
    ``convention_applied`` marks subset rows where an authorised zero-fill was
    used (informational).
    """
    n_subset = int(subset.sum())
    evalmask = subset & lhs.notna() & rhs.notna()
    n_eval = int(evalmask.sum())
    n_excluded = n_subset - n_eval
    n_conv = (int((subset & convention_applied.fillna(False)).sum())
              if convention_applied is not None else 0)

    if n_eval:
        le = lhs[evalmask]
        re_ = rhs[evalmask]
        eq = (le == re_)                          # both non-NA -> no <NA> in eq
        n_match = int(eq.sum())
        n_mismatch = n_eval - n_match
        diff = (le - re_)
        diff_min = int(diff.min())
        diff_max = int(diff.max())
    else:
        n_match = n_mismatch = 0
        diff_min = diff_max = None

    if n_subset == 0:
        verdict = "n/a"
    elif n_mismatch > 0:
        verdict = "FAILS"
    elif n_excluded > 0:
        verdict = f"PARTIAL ({n_excluded} rows excluded: required operand missing)"
    elif n_conv > 0:
        verdict = "HOLDS (missing-as-zero convention)"
    else:
        verdict = "HOLDS"

    return ReconResult(
        part=part, rule=rule, policy=policy, subset=subset_desc,
        n_in_subset=n_subset, n_evaluated=n_eval, n_convention_rows=n_conv,
        n_missing_operand=n_excluded, n_excluded_missing=n_excluded,
        n_match=n_match, n_mismatch=n_mismatch,
        diff_min=diff_min, diff_max=diff_max, verdict=verdict,
    )


def reconciliation_summary(df: pd.DataFrame, band_cols: list[str] | None = None) -> pd.DataFrame:
    """Per ``RTT Part Type``, test the candidate arithmetic identities with
    explicit coverage and missingness reporting.

    Completed parts (1A/1B):
      * ``observed_bandsum == Total``                    strict, all rows
      * ``Total + unknown == Total All``                 strict, **unknown-present** rows only
      * ``Total == Total All``                           strict, **unknown-blank** rows only
      * ``Total + unknown(→0) == Total All``             missing-as-zero, all rows
      * ``observed_bandsum + unknown(→0) == Total All``  missing-as-zero, all rows
    Incomplete parts (2/2A):
      * ``observed_bandsum == Total All``                strict, all rows
    Part_3: diagnostic only — bands + Total + unknown all missing; ``Total All``
    is a standalone count of new clock starts.

    ``expected`` marks the checks that should HOLD for that part.
    """
    if band_cols is None:
        band_cols = week_band_columns(df.columns.tolist())
    bs = observed_band_sum(df, band_cols)          # skip-missing bands (authorised)
    T, U, TA = df[TOTAL_COL], df[UNKNOWN_CLOCK_COL], df[TOTAL_ALL_COL]
    U0 = U.fillna(0)                               # ONLY the unknown-clock zero-fill is authorised (D-016)
    band_any_missing = df[band_cols].isna().any(axis=1)
    rows: list[dict[str, object]] = []

    for part, idx in df.groupby(RTT_PART_COL).groups.items():
        part_mask = pd.Series(df.index.isin(idx), index=df.index)
        checks: list[ReconResult] = []

        if part in COMPLETED_PARTS:
            u_present = part_mask & U.notna()
            u_blank = part_mask & U.isna()
            checks += [
                _reconcile(bs, T, part_mask, part=part,
                           rule="observed_bandsum == Total", policy="strict",
                           subset_desc="all rows in part"),
                _reconcile(T + U, TA, u_present, part=part,
                           rule="Total + unknown == Total All", policy="strict",
                           subset_desc="rows where unknown-clock is populated"),
                _reconcile(T, TA, u_blank, part=part,
                           rule="Total == Total All", policy="strict",
                           subset_desc="rows where unknown-clock is blank"),
                # missing-as-zero: ONLY U is zero-filled. A missing Total (lhs
                # via T) or missing Total All (rhs) still propagates <NA> and is
                # excluded -- never silently zero-filled to a match.
                _reconcile(T + U0, TA, part_mask, part=part,
                           rule="Total + unknown(missing->0) == Total All",
                           policy="missing-as-zero", subset_desc="all rows in part",
                           convention_applied=U.isna()),
                _reconcile(bs + U0, TA, part_mask, part=part,
                           rule="observed_bandsum + unknown(missing->0) == Total All",
                           policy="missing-as-zero", subset_desc="all rows in part",
                           convention_applied=(U.isna() | band_any_missing)),
            ]
        elif part in INCOMPLETE_PARTS:
            checks += [
                _reconcile(bs, TA, part_mask, part=part,
                           rule="observed_bandsum == Total All", policy="strict",
                           subset_desc="all rows in part"),
                _reconcile(T + U, TA, part_mask & T.notna() & U.notna(), part=part,
                           rule="Total + unknown == Total All", policy="strict",
                           subset_desc="rows where Total & unknown populated (none)"),
            ]
        else:  # Part_3
            checks += [
                _reconcile(bs, TA, part_mask, part=part,
                           rule="observed_bandsum == Total All", policy="strict",
                           subset_desc="all rows (bands all blank -> nothing evaluated)"),
            ]

        for res in checks:
            row = res.as_row()
            row["expected"] = res.rule in _expected_rules(part)
            rows.append(row)
    return pd.DataFrame(rows)


def _expected_rules(part: str) -> set[str]:
    if part in COMPLETED_PARTS:
        return {
            "observed_bandsum == Total",
            "Total + unknown == Total All",
            "Total == Total All",
            "Total + unknown(missing->0) == Total All",
            "observed_bandsum + unknown(missing->0) == Total All",
        }
    if part in INCOMPLETE_PARTS:
        return {"observed_bandsum == Total All"}
    return set()


def reconciliation_coverage_by_part(df: pd.DataFrame) -> pd.DataFrame:
    """Prove, per part, that the strict-subset checks together account for
    every row (so no rows are silently dropped from the arithmetic story)."""
    U = df[UNKNOWN_CLOCK_COL]
    rows = []
    for part, sub in df.groupby(RTT_PART_COL):
        n = len(sub)
        if part in COMPLETED_PARTS:
            u_present = int(sub[UNKNOWN_CLOCK_COL].notna().sum())
            u_blank = int(sub[UNKNOWN_CLOCK_COL].isna().sum())
            rows.append({
                "part": part, "n_rows": n,
                "unknown_present_subset": u_present,
                "unknown_blank_subset": u_blank,
                "subsets_sum": u_present + u_blank,
                "covers_all_rows": (u_present + u_blank) == n,
                "note": "strict checks cover both subsets; the two are disjoint and partition the part",
            })
        elif part in INCOMPLETE_PARTS:
            rows.append({
                "part": part, "n_rows": n,
                "unknown_present_subset": 0, "unknown_blank_subset": n,
                "subsets_sum": n, "covers_all_rows": True,
                "note": "one strict check (observed_bandsum == Total All) over all rows",
            })
        else:
            rows.append({
                "part": part, "n_rows": n,
                "unknown_present_subset": 0, "unknown_blank_subset": n,
                "subsets_sum": n, "covers_all_rows": True,
                "note": "no distribution identity applies; Total All is a standalone count",
            })
    return pd.DataFrame(rows)


def reconciliation_mismatch_examples(df: pd.DataFrame, band_cols: list[str] | None = None,
                                     n: int = 10) -> pd.DataFrame:
    """Rows where strict ``observed_bandsum == Total All`` does not hold — i.e.
    completed rows with a positive unknown-clock count (the difference is
    exactly ``-unknown``). Explained differences, not corrupt records."""
    if band_cols is None:
        band_cols = week_band_columns(df.columns.tolist())
    bs = observed_band_sum(df, band_cols)
    T, U, TA = df[TOTAL_COL], df[UNKNOWN_CLOCK_COL], df[TOTAL_ALL_COL]
    bad = df.loc[bs.notna() & TA.notna() & (bs != TA),
                 [PROVIDER_COL, COMMISSIONER_COL, RTT_PART_COL, TFC_COL, TFN_COL,
                  TOTAL_COL, UNKNOWN_CLOCK_COL, TOTAL_ALL_COL]].copy()
    bad.insert(5, "observed_bandsum", bs.loc[bad.index])
    bad["bandsum_minus_totalall"] = bad["observed_bandsum"] - bad[TOTAL_ALL_COL]
    return bad.sort_values([RTT_PART_COL, PROVIDER_COL]).head(n)


# --------------------------------------------------------------------------- #
# Blank vs explicit zero
# --------------------------------------------------------------------------- #

def blank_zero_summary(df: pd.DataFrame, band_cols: list[str] | None = None) -> pd.DataFrame:
    """Per ``RTT Part Type``: blank / zero / positive frequency for the total
    fields, band-cell-level blank/zero/positive, and how many rows mix blank
    and explicit-zero band cells. Describes represented rows only — a missing
    provider/commissioner/specialty combination cannot be diagnosed from
    absence."""
    if band_cols is None:
        band_cols = week_band_columns(df.columns.tolist())
    rows = []
    for part, sub in df.groupby(RTT_PART_COL):
        b = sub[band_cols]
        cell = b.to_numpy(dtype="float64", na_value=float("nan"))
        rows.append({
            "part": part, "n_rows": int(len(sub)),
            "Total_blank": int(sub[TOTAL_COL].isna().sum()),
            "Total_zero": int((sub[TOTAL_COL] == 0).sum()),
            "Total_pos": int((sub[TOTAL_COL] > 0).sum()),
            "unknown_blank": int(sub[UNKNOWN_CLOCK_COL].isna().sum()),
            "unknown_zero": int((sub[UNKNOWN_CLOCK_COL] == 0).sum()),
            "unknown_pos": int((sub[UNKNOWN_CLOCK_COL] > 0).sum()),
            "TotalAll_blank": int(sub[TOTAL_ALL_COL].isna().sum()),
            "TotalAll_pos": int((sub[TOTAL_ALL_COL] > 0).sum()),
            "band_cells": int(cell.size),
            "band_cell_blank": int(pd.isna(b).to_numpy().sum()),
            "band_cell_zero": int((cell == 0).sum()),
            "band_cell_pos": int((cell > 0).sum()),
            "rows_all_bands_blank": int(b.isna().all(axis=1).sum()),
            "rows_mixing_blank_and_zero_bands":
                int((b.isna().any(axis=1) & b.eq(0).fillna(False).any(axis=1)).sum()),
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Candidate key / grain
# --------------------------------------------------------------------------- #

def candidate_key_report(df: pd.DataFrame, key_cols: list[str]) -> dict[str, object]:
    """Uniqueness of ``key_cols`` over ``df``.

    ``is_unique`` is ``None`` (never ``True``) when a requested column is
    absent. ``usable`` requires: all columns present, no missing cell in any key
    column, and uniqueness. Below that the key is diagnostic only.
    """
    missing = [c for c in key_cols if c not in df.columns]
    present = [c for c in key_cols if c in df.columns]
    if missing:
        return {
            "key": key_cols, "present_cols": present, "missing_cols": missing,
            "usable": False, "is_unique": None,
            "reason": f"requested key column(s) absent: {missing}",
            "n_rows": int(len(df)),
        }
    n_key_na = int(df[present].isna().any(axis=1).sum())
    g = df.groupby(present, dropna=False).size()
    dup = g[g > 1]
    is_unique = bool(len(dup) == 0)
    ex = pd.DataFrame()
    if len(dup):
        first = list(dup.index[:5])
        ex = df.merge(pd.DataFrame(first, columns=present), on=present, how="inner")
    return {
        "key": present, "missing_cols": [],
        "n_rows": int(len(df)), "n_unique": int(len(g)),
        "n_duplicate_groups": int(len(dup)),
        "n_excess_rows": int((dup - 1).sum()) if len(dup) else 0,
        "n_key_cells_missing": n_key_na,
        "is_unique": is_unique,
        "usable": bool(is_unique and n_key_na == 0),
        "duplicate_example": ex.head(10),
    }


# --------------------------------------------------------------------------- #
# Aggregate-vs-detail (C_999 and any other roll-up row)
# --------------------------------------------------------------------------- #

def aggregate_vs_detail(df: pd.DataFrame, *, agg_col: str, agg_value: str,
                        group_cols: list[str], value_cols: list[str]) -> dict[str, object]:
    """Compare, per ``group_cols`` group, the aggregate row (``agg_col ==
    agg_value``) against the sum of the detail rows (``agg_col != agg_value``)
    over every ``value_cols`` column, on the **union** of aggregate/detail
    groups.

    Reports: orphan groups (aggregate-only, detail-only); groups with more than
    one aggregate row; detail-rows-per-group spread; and per (common group,
    column) comparison states — numeric/numeric (with mismatch count),
    both-missing, aggregate-zero vs all-missing-detail, other missing.

    Three result flags, in increasing strictness:

    * ``reconciles_numeric`` — **diagnostic only**: no orphan/multi-aggregate
      groups and zero *numeric/numeric* mismatches. It says nothing about
      missingness states, so it can be ``True`` while an unacceptable
      ``cmp_other_missing`` comparison exists (aggregate ``<NA>`` opposite a
      numeric detail sum).
    * ``reconciles_missing_as_zero`` — additionally treats every missing cell as
      ``0`` (a stated convention) and requires zero mismatch under that fill.
    * ``acceptable`` — the **policy-aware overall acceptance** used by Phase 2
      orchestration: no orphan groups, exactly one aggregate row per group,
      zero numeric mismatch, and **no disallowed missingness state**
      (``cmp_other_missing == 0``); ``cmp_both_missing`` and
      ``cmp_agg_zero_vs_all_missing_detail`` are the only tolerated states, each
      evaluated under the documented zero-contribution convention.
    """
    is_agg = df[agg_col] == agg_value
    agg_rows, det_rows = df[is_agg], df[~is_agg]
    agg_cnt = agg_rows.groupby(group_cols, dropna=False).size()
    det_cnt = det_rows.groupby(group_cols, dropna=False).size()
    agg_sum = agg_rows.groupby(group_cols, dropna=False)[value_cols].sum(min_count=1)
    det_sum = det_rows.groupby(group_cols, dropna=False)[value_cols].sum(min_count=1)

    agg_only = agg_cnt.index.difference(det_cnt.index)
    det_only = det_cnt.index.difference(agg_cnt.index)
    common = agg_cnt.index.intersection(det_cnt.index)
    n_multi_agg = int((agg_cnt > 1).sum())

    det_per_common = det_cnt.reindex(common).astype(int)
    a, d = agg_sum.reindex(common), det_sum.reindex(common)

    numeric_both = numeric_mismatch = both_missing = agg_zero_all_missing = other_missing = 0
    mz_mismatch = 0
    for c in value_cols:
        ac, dc = a[c], d[c]
        nb = ac.notna() & dc.notna()
        numeric_both += int(nb.sum())
        numeric_mismatch += int((nb & (ac != dc)).sum())
        bm = ac.isna() & dc.isna()
        both_missing += int(bm.sum())
        az = (ac == 0) & dc.isna()
        agg_zero_all_missing += int(az.fillna(False).sum())
        om = (ac.isna() ^ dc.isna()) & ~az.fillna(False)
        other_missing += int(om.sum())
        mz_mismatch += int((ac.fillna(0) != dc.fillna(0)).sum())

    no_orphans = len(agg_only) == 0 and len(det_only) == 0 and n_multi_agg == 0
    reconciles_numeric = bool(no_orphans and numeric_mismatch == 0)
    reconciles_mz = bool(no_orphans and mz_mismatch == 0)
    acceptable = bool(no_orphans and numeric_mismatch == 0 and other_missing == 0)
    return {
        "agg_col": agg_col, "agg_value": agg_value, "group_cols": group_cols,
        "n_value_cols": len(value_cols),
        "n_agg_groups": int(len(agg_cnt)), "n_detail_groups": int(len(det_cnt)),
        "n_common_groups": int(len(common)),
        "n_agg_only_groups": int(len(agg_only)),
        "n_detail_only_groups": int(len(det_only)),
        "n_groups_multiple_agg_rows": n_multi_agg,
        "detail_rows_per_group_min": int(det_per_common.min()) if len(common) else 0,
        "detail_rows_per_group_max": int(det_per_common.max()) if len(common) else 0,
        "n_groups_one_detail_row": int((det_per_common == 1).sum()),
        "n_groups_at_max_detail_rows":
            int((det_per_common == det_per_common.max()).sum()) if len(common) else 0,
        "cmp_numeric_both": numeric_both,
        "cmp_numeric_mismatch": numeric_mismatch,
        "cmp_both_missing": both_missing,
        "cmp_agg_zero_vs_all_missing_detail": agg_zero_all_missing,
        "cmp_other_missing": other_missing,
        "reconciles_numeric": reconciles_numeric,       # diagnostic: numeric/numeric only
        "reconciles_missing_as_zero": reconciles_mz,     # under a fill-all-missing-with-0 view
        "acceptable": acceptable,                        # policy-aware overall acceptance
    }


def treatment_function_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Each Treatment Function Code, its name, row count, and whether it is the
    treatment-function "Total" roll-up marker (``C_999``)."""
    g = (df.groupby([TFC_COL, TFN_COL], dropna=False)
           .size().rename("n_rows").reset_index())
    g["is_total_rollup_marker"] = g[TFC_COL].eq(TOTAL_TFC)
    return g.sort_values(TFC_COL, ignore_index=True)


# --------------------------------------------------------------------------- #
# Part_2A ⊆ Part_2 count-conformance (S1 Annex B)
# --------------------------------------------------------------------------- #

def part_2a_subset_conformance(df: pd.DataFrame) -> dict[str, object]:
    """Necessary count check for the documented rule that Part_2A (incomplete
    with decision to admit) is a **subset** of Part_2 (incomplete): for matching
    provider / commissioner / treatment function (Period constant in-file),
    ``Part_2A Total All`` must be ``<= Part_2 Total All``.

    Patient-level membership is not testable from this aggregate file; the count
    condition is. Violations are **preserved and flagged** — never capped.
    """
    key = [PROVIDER_COL, COMMISSIONER_COL, TFC_COL]
    p2 = df[df[RTT_PART_COL] == "Part_2"].set_index(key)[TOTAL_ALL_COL]
    p2a = df[df[RTT_PART_COL] == "Part_2A"].set_index(key)[TOTAL_ALL_COL]
    j = pd.DataFrame({"part_2a": p2a})
    j["part_2"] = p2.reindex(p2a.index)
    j["has_matching_part_2"] = j["part_2"].notna()
    matched = j[j["has_matching_part_2"]]
    viol = matched[matched["part_2a"] > matched["part_2"]].reset_index()
    return {
        "rule": "NHS S1 Annex B: Part_2A count <= Part_2 count for matching "
                "provider/commissioner/treatment function/period",
        "n_part_2a_groups": int(len(p2a)),
        "n_with_matching_part_2": int(len(matched)),
        "n_without_matching_part_2": int((~j["has_matching_part_2"]).sum()),
        "n_conformant": int((matched["part_2a"] <= matched["part_2"]).sum()),
        "n_violations": int(len(viol)),
        "violations": viol,
        "disposition": "Preserve source values; flag violations; do not cap "
                       "Part_2A or alter Part_2. Any measure relying on "
                       "Part_2A <= Part_2 must validate this invariant first.",
    }


# --------------------------------------------------------------------------- #
# NONC — structural prevalence separated from pathway counts
# --------------------------------------------------------------------------- #

def nonc_prevalence(df: pd.DataFrame) -> dict[str, object]:
    """Structural prevalence of ``Commissioner Org Code == 'NONC'`` — row/
    provider/coverage counts only, **no pathway total** (that would double-count
    C_999 with its constituents and mix RTT parts)."""
    nonc = df[df[COMMISSIONER_COL] == NONC_CODE]
    return {
        "n_rows": int(len(nonc)),
        "n_providers": int(nonc[PROVIDER_COL].nunique()),
        "n_treatment_functions": int(nonc[TFC_COL].nunique()),
        "rtt_parts": sorted(nonc[RTT_PART_COL].dropna().unique().tolist()),
        "share_of_all_rows_pct": round(100.0 * len(nonc) / len(df), 3),
        "coverage_note": "NONC submission is not mandatory (S5, 'Navigating "
                         "published files'); these rows are not a complete "
                         "record of non-English-commissioned activity.",
    }


def nonc_pathways_by_part(df: pd.DataFrame, *, representation: str = "C_999") -> pd.DataFrame:
    """NONC pathway counts **per RTT Part**, using exactly one treatment-
    function representation (``"C_999"`` = the roll-up row, preferred; or
    ``"detail"`` = sum of the non-C_999 rows). **Do not sum across parts** —
    they are different populations and Part_2A ⊆ Part_2."""
    nonc = df[df[COMMISSIONER_COL] == NONC_CODE]
    if representation == "C_999":
        sel = nonc[nonc[TFC_COL] == TOTAL_TFC]
    elif representation == "detail":
        sel = nonc[nonc[TFC_COL] != TOTAL_TFC]
    else:
        raise ValueError("representation must be 'C_999' or 'detail'")
    t = (sel.groupby(RTT_PART_COL)[TOTAL_ALL_COL].sum()
             .rename("pathways").reset_index())
    t["representation"] = representation
    t["do_not_sum_across_parts"] = True
    return t


def nonc_raw_cell_checksum(df: pd.DataFrame) -> dict[str, object]:
    """The raw ``Total All`` sum over *all* NONC rows — an uninterpreted
    checksum, **not** a pathway population (it adds C_999 to its constituents
    and mixes RTT parts). Kept only for reproducibility of the earlier
    mislabelled figure."""
    nonc = df[df[COMMISSIONER_COL] == NONC_CODE]
    return {
        "raw_total_all_sum_all_nonc_rows": int(nonc[TOTAL_ALL_COL].sum()),
        "warning": "double-counts C_999 with its detail rows and mixes RTT Part "
                   "Types (incompatible/overlapping event bases); not a count of "
                   "pathways or patients.",
    }


def nonc_summary(df: pd.DataFrame) -> dict[str, object]:
    """Combined NONC view: structural prevalence, per-part pathway counts
    (C_999 representation), and the uninterpreted raw checksum — kept strictly
    separate."""
    return {
        "prevalence": nonc_prevalence(df),
        "pathways_by_part_c999": nonc_pathways_by_part(df, representation="C_999"),
        "raw_cell_checksum": nonc_raw_cell_checksum(df),
    }


# --------------------------------------------------------------------------- #
# Published-measure reproduction (same-month benchmark, not a KPI deliverable)
# --------------------------------------------------------------------------- #

def incomplete_within_18wk(df: pd.DataFrame, *, exclude_nonc: bool = True) -> dict[str, object]:
    """Reproduce the published "% incomplete pathways within 18 weeks" per the
    NHS statistics user guidance (S5, "Reproducibility and derived measures"):
    ``RTT Part Type = Part_2``, ``Treatment Function Name = Total``, numerator =
    bands 0-1 … 17-18, denominator = ``Total All``, ``Commissioner Org Code <>
    NONC``.

    Benchmarked against the **same-month** June 2026 SPN Table 1 unestimated
    figure. The published *estimate-inclusive* headline additionally uplifts
    for non-submitting trusts (RHQ, RA9 in June 2026); that uplift is NOT
    computed here — see P2-U1.
    """
    cols = df.columns.tolist()
    b18 = bands_up_to_weeks(cols, 18)
    sel = df[RTT_PART_COL].eq("Part_2") & df[TFN_COL].eq(TOTAL_TFN)
    if exclude_nonc:
        sel &= df[COMMISSIONER_COL].ne(NONC_CODE)
    sub = df[sel]
    within = int(sub[b18].sum().sum())
    denom = int(sub[TOTAL_ALL_COL].sum())
    pct = round(100.0 * within / denom, 3) if denom else None
    out = {
        "filter": "RTT Part Type=Part_2, Treatment Function Name=Total"
                  + (", Commissioner Org Code<>NONC" if exclude_nonc else ""),
        "n_rows": int(len(sub)), "n_bands_used": len(b18),
        "within_18wk": within, "total_all": denom, "pct_within_18wk": pct,
    }
    if exclude_nonc:
        out["benchmark_june_2026_spn_unestimated"] = {
            "total_all": JUNE_2026_SPN_UNESTIMATED["incomplete_total"],
            "pct_within_18wk_1dp": JUNE_2026_SPN_UNESTIMATED["incomplete_within_18wk_pct"],
            "total_all_matches": denom == JUNE_2026_SPN_UNESTIMATED["incomplete_total"],
            "pct_matches_1dp": (pct is not None
                                and round(pct, 1) == JUNE_2026_SPN_UNESTIMATED["incomplete_within_18wk_pct"]),
            "source": "NHS England RTT SPN June 2026, Table 1 (published 13 Aug 2026), "
                      "not including estimates for missing acute trusts.",
        }
    return out


def same_month_totals_check(df: pd.DataFrame) -> pd.DataFrame:
    """Reproduce the June 2026 SPN Table 1 *unestimated* England totals from the
    raw file (Treatment Function Name = Total, exclude NONC): incomplete,
    completed admitted, completed non-admitted, new RTT periods."""
    def _tot(part: str) -> int:
        s = df[(df[RTT_PART_COL] == part) & (df[TFN_COL] == TOTAL_TFN)
               & (df[COMMISSIONER_COL] != NONC_CODE)]
        return int(s[TOTAL_ALL_COL].sum())
    rows = [
        ("incomplete (Part_2)", _tot("Part_2"), JUNE_2026_SPN_UNESTIMATED["incomplete_total"]),
        ("completed admitted (Part_1A)", _tot("Part_1A"),
         JUNE_2026_SPN_UNESTIMATED["completed_admitted_total"]),
        ("completed non-admitted (Part_1B)", _tot("Part_1B"),
         JUNE_2026_SPN_UNESTIMATED["completed_non_admitted_total"]),
        ("new RTT periods (Part_3)", _tot("Part_3"),
         JUNE_2026_SPN_UNESTIMATED["new_rtt_periods_total"]),
    ]
    out = pd.DataFrame(rows, columns=["measure", "raw_file_value", "june_spn_unestimated"])
    out["matches"] = out["raw_file_value"] == out["june_spn_unestimated"]
    return out


# --------------------------------------------------------------------------- #
# Controlled examples (Step 1 — curated real rows for manual inspection)
# --------------------------------------------------------------------------- #

def controlled_examples(df: pd.DataFrame, band_cols: list[str] | None = None) -> pd.DataFrame:
    """A small curated table of real June rows that together show every case an
    analyst must understand:

    * a completed row with a **positive** unknown-clock count;
    * a completed row with a **blank** unknown-clock cell (Total == Total All);
    * a normal incomplete (Part_2) and Part_2A row;
    * the Part_2A > Part_2 data-quality exception;
    * a Part_3 row (band sum is ``<NA>``, deliberately not shown as 0).

    ``observed_bandsum`` uses the skip-missing convention and is ``<NA>`` when
    every band is blank. ``note`` states, per row, which identity/behaviour
    applies.
    """
    if band_cols is None:
        band_cols = week_band_columns(df.columns.tolist())
    bs = observed_band_sum(df, band_cols)
    keep = [PROVIDER_COL, COMMISSIONER_COL, RTT_PART_COL, TFC_COL, TFN_COL,
            TOTAL_COL, UNKNOWN_CLOCK_COL, TOTAL_ALL_COL]
    picks: list[pd.Series] = []
    notes: dict[int, str] = {}

    def _add(row_idx, note):
        picks.append(row_idx)
        notes[row_idx] = note

    completed = df[df[RTT_PART_COL].isin(COMPLETED_PARTS)]
    pos_u = completed[completed[UNKNOWN_CLOCK_COL] > 0].sort_index()
    if len(pos_u):
        _add(pos_u.index[0],
             "completed, unknown>0: Total + unknown = Total All (strict); "
             "observed_bandsum = Total, and = Total All - unknown")
    blank_u = completed[completed[UNKNOWN_CLOCK_COL].isna()].sort_index()
    if len(blank_u):
        _add(blank_u.index[0],
             "completed, unknown blank: Total = Total All (strict). Extending "
             "'Total + unknown = Total All' to this row needs the missing->0 convention")

    # a provider/commissioner that reports both Part_2 and Part_2A, C_999 rows
    inc = df[(df[RTT_PART_COL] == "Part_2") & (df[TFC_COL] == TOTAL_TFC)]
    if len(inc):
        pc = inc.sort_values(TOTAL_ALL_COL, ascending=False).iloc[0]
        prov, comm = pc[PROVIDER_COL], pc[COMMISSIONER_COL]
        for part in ("Part_2", "Part_2A"):
            r = df[(df[PROVIDER_COL] == prov) & (df[COMMISSIONER_COL] == comm)
                   & (df[RTT_PART_COL] == part) & (df[TFC_COL] == TOTAL_TFC)]
            if len(r):
                _add(r.index[0],
                     f"{part} snapshot: Total/unknown not collected; "
                     "observed_bandsum = Total All (strict)")

    conf = part_2a_subset_conformance(df)
    for _, v in conf["violations"].iterrows():
        r = df[(df[PROVIDER_COL] == v[PROVIDER_COL])
               & (df[COMMISSIONER_COL] == v[COMMISSIONER_COL])
               & (df[TFC_COL] == v[TFC_COL])
               & (df[RTT_PART_COL].isin(["Part_2", "Part_2A"]))]
        for idx in r.index:
            part = df.at[idx, RTT_PART_COL]
            _add(idx, f"DATA-QUALITY: {v[PROVIDER_COL]}/{v[COMMISSIONER_COL]}/"
                      f"{v[TFC_COL]} has Part_2A > Part_2 (NHS: 2A subset of 2). "
                      "Preserved and flagged; not capped.")

    p3 = df[(df[RTT_PART_COL] == "Part_3") & (df[TFC_COL] == TOTAL_TFC)].sort_index()
    if len(p3):
        _add(p3.index[0],
             "Part_3 = count of new clock starts. No band distribution collected; "
             "observed_bandsum is <NA> (NOT a computed 0)")

    seen: set[int] = set()
    order = [i for i in picks if not (i in seen or seen.add(i))]
    out = df.loc[order, keep].copy()
    out.insert(5, "observed_bandsum", bs.loc[order])
    out["note"] = [notes[i] for i in order]
    return out.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

@dataclass
class Phase2Outputs:
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    facts: dict[str, object] = field(default_factory=dict)

    def write(self, outdir: str | Path) -> list[Path]:
        import json
        outdir = Path(outdir)
        outdir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for name, tbl in self.tables.items():
            p = outdir / f"{name}.csv"
            tbl.to_csv(p, index=False)
            written.append(p)
        p = outdir / "facts.json"
        p.write_text(json.dumps(self.facts, indent=1, default=str), encoding="utf-8")
        written.append(p)
        return written


def run_phase2_analysis(df: pd.DataFrame, *, source_path: str | Path | None = None) -> Phase2Outputs:
    """Run the full Phase 2 semantic/arithmetic battery and return compact
    results (tables + scalar facts). Writing is the caller's choice."""
    cols = df.columns.tolist()
    band_cols = week_band_columns(cols)
    out = Phase2Outputs()

    out.tables["reconciliation_by_part"] = reconciliation_summary(df, band_cols)
    out.tables["reconciliation_coverage_by_part"] = reconciliation_coverage_by_part(df)
    out.tables["blank_zero_by_part"] = blank_zero_summary(df, band_cols)
    out.tables["treatment_function_rows"] = treatment_function_rows(df)
    out.tables["nonc_pathways_by_part_c999"] = nonc_pathways_by_part(df, representation="C_999")
    out.tables["part2a_subset_violations"] = part_2a_subset_conformance(df)["violations"]
    out.tables["controlled_examples"] = controlled_examples(df, band_cols)
    out.tables["mismatch_positive_unknown"] = reconciliation_mismatch_examples(df, band_cols, n=10)
    out.tables["same_month_totals_check"] = same_month_totals_check(df)

    key = candidate_key_report(df, CANDIDATE_KEY)
    key_wo_period = candidate_key_report(df, [c for c in CANDIDATE_KEY if c != PERIOD_COL])
    c999 = aggregate_vs_detail(
        df, agg_col=TFC_COL, agg_value=TOTAL_TFC,
        group_cols=[PROVIDER_COL, COMMISSIONER_COL, RTT_PART_COL],
        value_cols=band_cols + NUMERIC_TAIL_COLS,
    )
    conf = part_2a_subset_conformance(df)
    conf.pop("violations", None)

    facts: dict[str, object] = {
        "n_rows": int(len(df)),
        "n_week_bands": len(band_cols),
        "candidate_key": key.get("key"),
        "candidate_key_is_unique": key.get("is_unique"),
        "candidate_key_usable": key.get("usable"),
        "candidate_key_n_key_cells_missing": key.get("n_key_cells_missing"),
        "candidate_key_excl_period_is_unique": key_wo_period.get("is_unique"),
        "candidate_key_duplicate_groups": key.get("n_duplicate_groups"),
        "c999_aggregate_vs_detail": c999,
        "c999_acceptable": c999["acceptable"],
        "nonc_prevalence": nonc_prevalence(df),
        "nonc_raw_cell_checksum": nonc_raw_cell_checksum(df),
        "part2a_subset_conformance": conf,
        "incomplete_within_18wk_excl_nonc": incomplete_within_18wk(df, exclude_nonc=True),
        "incomplete_within_18wk_incl_nonc": incomplete_within_18wk(df, exclude_nonc=False),
    }
    if source_path is not None:
        facts["extract_validation"] = validate_extract(source_path)
    out.facts = facts
    return out
