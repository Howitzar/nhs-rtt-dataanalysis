"""Reusable, dependency-free profiler for raw NHS RTT monthly CSV extracts.

The profiler makes a **single streaming pass** over a CSV file and reports
structural facts only. It does **no** cleaning, type coercion, row/column
removal, or interpretation of blank values — those are downstream concerns.

Why standard library only
-------------------------
The profiling stage must run anywhere, including locked-down environments
where compiled wheels (numpy/pandas) cannot be loaded. Everything here uses
``csv`` and ``collections`` so a profile can always be produced. Downstream
stages (``transform``, ``metrics``) are free to depend on pandas.

Scope & caveats (read before trusting a number)
-----------------------------------------------
* ``inferred_dtype`` is a **heuristic hint**, never an ingestion schema. It is
  derived from cell *shape*: ``"001"`` is reported ``integer`` even though it is
  an identifier, numeric extrema are computed with ``float`` (so very large
  integers can lose precision), and ``date`` checks shape, not calendar
  validity. Raw values are preserved verbatim in the unique/categorical output.
* ``null`` / ``null_pct`` mean **empty string or whitespace-only**. Literal
  ``NULL`` / ``NA`` / ``NaN`` text stays a ``string``. Fields missing from a
  short row are counted as null.
* ``column_flags`` and ``week_bucket_columns`` are **candidate** groupings
  matched from header text. They assign no meaning. Structural validity of the
  week-bucket sequence is checked separately by
  :func:`check_week_bucket_sequence` and surfaced as
  ``TableProfile.week_bucket_sequence_warnings``.
* Malformed structure (duplicate headers, broken quoting, ambiguous role
  columns) is reported in ``TableProfile.structural_warnings`` and echoed to
  :mod:`warnings` / the CLI exit code — it is never silently accepted.

Public API
----------
``profile_csv(path, ...)``      -> :class:`TableProfile`
``save_profile(profile, outdir)`` -> list[pathlib.Path]  (writes CSV + Markdown)
``profile_and_save(path, outdir)`` -> (:class:`TableProfile`, list[pathlib.Path])

CLI
---
``python -m nhs_rtt.profile data/raw/rtt_2026_06.csv --outdir outputs/profiles``
Exit code is ``2`` when structural warnings were raised, ``0`` otherwise.
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import math
import re
import sys
import warnings
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# csv fields in these files can be long; lift the default limit defensively.
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

#: Semantic column roles for NHS RTT provider-level extracts. Values are the
#: expected column headers; the profiler degrades gracefully if any are absent
#: (the miss is recorded in ``TableProfile.unbound_roles``).
DEFAULT_CATEGORICAL_ROLES: dict[str, tuple[str, str | None]] = {
    # role name            -> (code column,               name column or None)
    "reporting_period":     ("Period", None),
    "provider":             ("Provider Org Code", "Provider Org Name"),
    "provider_parent":      ("Provider Parent Org Code", "Provider Parent Name"),
    "commissioner":         ("Commissioner Org Code", "Commissioner Org Name"),
    "rtt_part":             ("RTT Part Type", "RTT Part Description"),
    "treatment_function":   ("Treatment Function Code", "Treatment Function Name"),
}

#: Above this many distinct values the profiler stops storing them and just
#: reports ">= cap (capped)". Keeps memory bounded on pathological inputs.
#: NOTE: applied *per column*; the exact-duplicate row set and the categorical
#: pair counters are not capped (see docs/assumptions.md scalability note).
DEFAULT_MAX_UNIQUE_TRACKED = 500_000

#: Candidate matcher for a per-week waiting-time bucket header, e.g.
#: ``Gt 00 To 01 Weeks SUM 1`` or the open-ended ``Gt 104 Weeks SUM 1``.
#: Deliberately permissive (a *finder*, not a validator): start-anchored,
#: case-insensitive, tolerates leading space, does not require the ``SUM n``
#: suffix and does not check bounds. Sequence integrity is
#: :func:`check_week_bucket_sequence`'s job.
_WEEK_BUCKET_RE = re.compile(r"^\s*Gt\s+\d+\s+(?:To\s+\d+\s+)?Weeks\b", re.IGNORECASE)
#: Structured forms used only by the sequence validator.
_BUCKET_RANGE_RE = re.compile(r"^\s*Gt\s+(\d+)\s+To\s+(\d+)\s+Weeks\b", re.IGNORECASE)
_BUCKET_OPEN_RE = re.compile(r"^\s*Gt\s+(\d+)\s+Weeks\b", re.IGNORECASE)
#: "total" / "unknown" as whole words, so ``Subtotal`` is not a total candidate.
_TOTAL_TOKEN_RE = re.compile(r"\btotal\b", re.IGNORECASE)
_UNKNOWN_TOKEN_RE = re.compile(r"\bunknown\b", re.IGNORECASE)


def classify_columns(header: list[str]) -> dict[str, list[str]]:
    """Flag columns by header text only. No semantic interpretation.

    Returns a dict with three lists of column names:

    ``total_columns``      headers containing the whole word "total"
    ``unknown_columns``    headers containing the whole word "unknown"
    ``week_bucket_columns``  headers matching :data:`_WEEK_BUCKET_RE`

    These are *candidates* surfaced for human review, not assertions about
    meaning. A header may appear in more than one list.
    """
    return {
        "total_columns": [h for h in header if _TOTAL_TOKEN_RE.search(h)],
        "unknown_columns": [h for h in header if _UNKNOWN_TOKEN_RE.search(h)],
        "week_bucket_columns": [h for h in header if _WEEK_BUCKET_RE.match(h)],
    }


def check_week_bucket_sequence(bucket_headers: list[str]) -> list[str]:
    """Validate that candidate week-bucket headers form a clean sequence.

    Structural only — says nothing about interval inclusivity or what a week
    band *means*. Returns a list of human-readable warning strings; an empty
    list means the sequence is contiguous, ascending, unit-width, unique, and
    followed by at most one open-ended (``Gt N Weeks``) band whose lower bound
    matches the preceding upper bound.
    """
    warns: list[str] = []
    ranged: list[tuple[int, int, str]] = []
    open_ended: list[tuple[int, str]] = []

    for h in bucket_headers:
        m = _BUCKET_RANGE_RE.match(h)
        if m:
            ranged.append((int(m.group(1)), int(m.group(2)), h))
            continue
        m = _BUCKET_OPEN_RE.match(h)
        if m:
            open_ended.append((int(m.group(1)), h))
            continue
        warns.append(f"bucket header not parseable as a week band: {h!r}")

    seen_lows: set[int] = set()
    for idx, (lo, hi, h) in enumerate(ranged):
        if hi != lo + 1:
            warns.append(f"bucket {h!r} is not one week wide ({lo}->{hi})")
        if lo in seen_lows:
            warns.append(f"duplicate bucket lower bound {lo} ({h!r})")
        seen_lows.add(lo)
        if idx > 0:
            plo, phi, ph = ranged[idx - 1]
            if lo < plo:
                warns.append(f"week buckets not in ascending order: {ph!r} then {h!r}")
            elif lo != phi:
                warns.append(
                    f"gap or overlap between {ph!r} (ends {phi}) and {h!r} (starts {lo})"
                )

    if len(open_ended) > 1:
        warns.append(
            "more than one open-ended week bucket: "
            + ", ".join(repr(h) for _, h in open_ended)
        )
    if open_ended:
        lo, h = open_ended[-1]
        if bucket_headers and bucket_headers[-1] != h:
            warns.append(f"open-ended bucket {h!r} is not the last week column")
        if ranged and lo != ranged[-1][1]:
            warns.append(
                f"open-ended bucket {h!r} starts at {lo} but the last ranged "
                f"bucket ends at {ranged[-1][1]}"
            )
    return warns


_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")
_DATE_RES = (
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    re.compile(r"^\d{2}/\d{2}/\d{4}$"),
    re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?$"),
)
_BOOL_TOKENS = {"true", "false"}

# Rough per-object overhead for a short CPython ``str`` (bytes). Used only for a
# transparent in-memory *estimate*; it is not a measurement.
_STR_OBJECT_OVERHEAD = 49


def classify_token(token: str) -> str:
    """Classify a single raw cell string into a coarse type bucket.

    Returns one of: ``"empty"``, ``"int"``, ``"float"``, ``"bool"``,
    ``"date"``, ``"str"``. Whitespace-only strings count as ``"empty"``.
    This is a shape heuristic, not a schema — see the module docstring.
    """
    if token is None:
        return "empty"
    s = token.strip()
    if s == "":
        return "empty"
    if _INT_RE.match(s):
        return "int"
    if _FLOAT_RE.match(s):
        return "float"
    if s.lower() in _BOOL_TOKENS:
        return "bool"
    for rx in _DATE_RES:
        if rx.match(s):
            return "date"
    return "str"


def _resolve_dtype(type_counts: Counter[str]) -> str:
    """Collapse a Counter of per-cell type buckets into one column dtype label."""
    present = [t for t in type_counts if t != "empty" and type_counts[t]]
    if not present:
        return "empty"
    if present == ["int"]:
        return "integer"
    if set(present) <= {"int", "float"}:
        return "float"
    if present == ["bool"]:
        return "boolean"
    if present == ["date"]:
        return "date"
    if present == ["str"]:
        return "string"
    return "mixed(" + ",".join(sorted(present)) + ")"


# --------------------------------------------------------------------------- #
# Result containers
# --------------------------------------------------------------------------- #


@dataclass
class ColumnProfile:
    """Per-column profiling facts."""

    name: str
    position: int
    n_total: int = 0
    n_null: int = 0
    type_counts: Counter[str] = field(default_factory=Counter)
    _uniques: set[str] = field(default_factory=set, repr=False)
    unique_capped: bool = False
    n_unique_est: int = 0
    numeric_min: float | None = None
    numeric_max: float | None = None
    text_bytes: int = 0  # sum of utf-8 byte lengths of non-empty cells

    @property
    def n_non_null(self) -> int:
        return self.n_total - self.n_null

    @property
    def null_pct(self) -> float:
        return 100.0 * self.n_null / self.n_total if self.n_total else 0.0

    @property
    def inferred_dtype(self) -> str:
        return _resolve_dtype(self.type_counts)

    @property
    def est_memory_bytes(self) -> int:
        """Transparent estimate of in-memory size if held as Python strings."""
        return self.text_bytes + _STR_OBJECT_OVERHEAD * self.n_non_null

    def sample_uniques(self, k: int = 15) -> list[str]:
        return sorted(self._uniques)[:k] if not self.unique_capped else []

    def as_row(self) -> dict[str, object]:
        return {
            "position": self.position,
            "column": self.name,
            "inferred_dtype": self.inferred_dtype,
            "n_total": self.n_total,
            "n_non_null": self.n_non_null,
            "n_null": self.n_null,
            "null_pct": round(self.null_pct, 4),
            "n_unique": (f">={len(self._uniques)} (capped)"
                         if self.unique_capped else self.n_unique_est),
            "numeric_min": self.numeric_min,
            "numeric_max": self.numeric_max,
            "est_memory_bytes": self.est_memory_bytes,
            "type_mix": ";".join(f"{t}={c}" for t, c in self.type_counts.most_common()),
        }


@dataclass
class CategoricalSummary:
    """Distinct (code, name) pairs seen for one semantic role.

    Counts include blank values verbatim: a blank ``name`` is a distinct name
    here, whereas :class:`ColumnProfile` distinct counts exclude blanks. The
    renderer labels the blank explicitly.
    """

    role: str
    code_column: str
    name_column: str | None
    pairs: Counter[tuple[str, str]] = field(default_factory=Counter)

    @property
    def n_distinct_codes(self) -> int:
        return len({c for c, _ in self.pairs})

    @property
    def n_distinct_names(self) -> int:
        return len({n for _, n in self.pairs})

    @property
    def n_distinct_names_nonblank(self) -> int:
        return len({n for _, n in self.pairs if n.strip() != ""})

    @property
    def n_blank_name_variants(self) -> int:
        return len({n for _, n in self.pairs if n.strip() == ""})

    def code_to_names(self) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        for code, name in self.pairs:
            out.setdefault(code, set()).add(name)
        return out

    def name_to_codes(self) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        for code, name in self.pairs:
            out.setdefault(name, set()).add(code)
        return out

    def mapping_anomaly_rows(self) -> list[dict[str, object]]:
        """One row per code/name relationship that is not strictly 1:1.

        Purely structural: reports codes carrying more than one name and
        names carried by more than one code. It does **not** decide which
        (if either) is 'correct', normalise case/whitespace, or distinguish
        a blank collision from a real name collision.
        """
        if self.name_column is None:
            return []
        rows: list[dict[str, object]] = []
        for code, names in sorted(self.code_to_names().items()):
            if len(names) > 1:
                rows.append({
                    "kind": "code_has_multiple_names",
                    "key": code,
                    "n_related": len(names),
                    "related_values": " | ".join(sorted(names)),
                })
        for name, codes in sorted(self.name_to_codes().items()):
            if len(codes) > 1:
                rows.append({
                    "kind": "name_has_multiple_codes",
                    "key": name,
                    "n_related": len(codes),
                    "related_values": " | ".join(sorted(codes)),
                })
        return rows

    def rows(self) -> list[dict[str, object]]:
        out = []
        for (code, name), n in sorted(self.pairs.items()):
            row = {"code": code, "row_count": n}
            if self.name_column is not None:
                row["name"] = name
            out.append(row)
        return out


@dataclass
class TableProfile:
    """Whole-file profiling result."""

    path: str
    file_bytes: int
    n_rows: int
    n_cols: int
    columns: list[ColumnProfile]
    duplicate_row_count: int
    n_ragged_rows: int
    categoricals: dict[str, CategoricalSummary]
    column_flags: dict[str, list[str]]
    encoding: str
    delimiter: str
    generated_utc: str
    # --- structural-safety fields (new; default so construction stays simple) --
    structural_warnings: list[str] = field(default_factory=list)
    duplicate_headers: list[str] = field(default_factory=list)
    unbound_roles: list[str] = field(default_factory=list)
    week_bucket_sequence_warnings: list[str] = field(default_factory=list)
    n_cells_with_embedded_newline: int = 0
    parse_truncated: bool = False

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    @property
    def est_memory_bytes(self) -> int:
        return sum(c.est_memory_bytes for c in self.columns)

    @property
    def is_structurally_clean(self) -> bool:
        return not self.structural_warnings


# --------------------------------------------------------------------------- #
# Core profiling pass
# --------------------------------------------------------------------------- #


def profile_csv(
    path: str | Path,
    *,
    encoding: str = "utf-8-sig",
    delimiter: str = ",",
    categorical_roles: dict[str, tuple[str, str | None]] | None = None,
    max_unique_tracked: int = DEFAULT_MAX_UNIQUE_TRACKED,
) -> TableProfile:
    """Profile a CSV file in a single streaming pass.

    Holds in memory: per-column accumulators, one exact serialisation per
    distinct row (for a true whole-row duplicate count), and the categorical
    pair counters. Structural problems are recorded in
    :attr:`TableProfile.structural_warnings` and echoed via :mod:`warnings`;
    they do not raise (a description is still produced) except when there is
    no header row at all.
    """
    path = Path(path)
    roles = DEFAULT_CATEGORICAL_ROLES if categorical_roles is None else categorical_roles

    structural_warnings: list[str] = []
    parse_truncated = False

    with path.open("r", newline="", encoding=encoding) as fh:
        # strict=True rejects a class of broken quoting (stray quote after a
        # closed quoted field, etc.) that permissive parsing swallows.
        reader = csv.reader(fh, delimiter=delimiter, strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:  # empty file
            raise ValueError(f"{path} contains no header row") from exc
        except csv.Error as exc:
            raise ValueError(f"{path}: unreadable header row ({exc})") from exc

        cols = [ColumnProfile(name=h, position=i) for i, h in enumerate(header)]
        ncols = len(header)

        # Duplicate headers: a plain dict would bind roles to the LAST
        # occurrence and hide the ambiguity. Detect, warn, and refuse to bind
        # any role whose code/name column is ambiguous.
        header_counts = Counter(header)
        duplicate_headers = sorted(h for h, n in header_counts.items() if n > 1)
        if duplicate_headers:
            msg = (f"duplicate header name(s) {duplicate_headers}: column "
                   f"positions are still profiled individually, but any "
                   f"categorical role using them is left unbound")
            structural_warnings.append(msg)
            warnings.warn(msg, stacklevel=2)
        col_index = {h: i for i, h in enumerate(header)}  # first occurrence wins

        # Wire up categorical roles whose columns exist AND are unambiguous.
        cats: dict[str, CategoricalSummary] = {}
        unbound_roles: list[str] = []
        for role, (code_col, name_col) in roles.items():
            needed = [code_col] + ([name_col] if name_col is not None else [])
            missing = [c for c in needed if c not in col_index]
            ambiguous = [c for c in needed if header_counts.get(c, 0) > 1]
            if missing or ambiguous:
                unbound_roles.append(role)
                if ambiguous:
                    structural_warnings.append(
                        f"role {role!r} not bound: ambiguous column(s) {ambiguous}"
                    )
                continue
            cats[role] = CategoricalSummary(role, code_col, name_col)

        seen_rows: set[str] = set()   # one exact serialisation per distinct row
        duplicate_rows = 0
        ragged_rows = 0
        n_rows = 0
        n_cells_with_embedded_newline = 0

        row_iter = iter(reader)
        while True:
            try:
                row = next(row_iter)
            except StopIteration:
                break
            except csv.Error as exc:
                msg = (f"CSV parse error after {n_rows:,} data row(s) "
                       f"({exc}); profiling stopped at that point")
                structural_warnings.append(msg)
                warnings.warn(msg, stacklevel=2)
                parse_truncated = True
                break

            n_rows += 1
            if len(row) != ncols:
                ragged_rows += 1

            # Exact whole-row equality via an injective serialisation. repr()
            # of a list[str] is unambiguous, so different rows never collide
            # and genuine repeats always do.
            key = repr(row)
            if key in seen_rows:
                duplicate_rows += 1
            else:
                seen_rows.add(key)

            for i in range(min(len(row), ncols)):
                if "\n" in row[i] or "\r" in row[i]:
                    n_cells_with_embedded_newline += 1
                _accumulate(cols[i], row[i], max_unique_tracked)
            # columns missing from a short row count as null, consistently in
            # both the null tally and the per-type mix.
            for i in range(len(row), ncols):
                cols[i].n_total += 1
                cols[i].n_null += 1
                cols[i].type_counts["empty"] += 1

            for cat in cats.values():
                ci = col_index[cat.code_column]
                code = row[ci] if ci < len(row) else ""
                if cat.name_column is not None:
                    j = col_index[cat.name_column]
                    name = row[j] if j < len(row) else ""
                else:
                    name = ""
                cat.pairs[(code, name)] += 1

    for c in cols:
        c.n_unique_est = len(c._uniques)

    bucket_seq_warnings = check_week_bucket_sequence(
        classify_columns(header)["week_bucket_columns"]
    )
    if bucket_seq_warnings:
        structural_warnings.append(
            f"week-bucket sequence: {len(bucket_seq_warnings)} issue(s) "
            f"(see week_bucket_sequence_warnings)"
        )
    if n_cells_with_embedded_newline:
        structural_warnings.append(
            f"{n_cells_with_embedded_newline:,} cell(s) contain an embedded "
            f"newline (quoted multi-line fields)"
        )

    return TableProfile(
        path=str(path),
        file_bytes=path.stat().st_size,
        n_rows=n_rows,
        n_cols=ncols,
        columns=cols,
        duplicate_row_count=duplicate_rows,
        n_ragged_rows=ragged_rows,
        categoricals=cats,
        column_flags=classify_columns(header),
        encoding=encoding,
        delimiter=delimiter,
        generated_utc=_dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        structural_warnings=structural_warnings,
        duplicate_headers=duplicate_headers,
        unbound_roles=unbound_roles,
        week_bucket_sequence_warnings=bucket_seq_warnings,
        n_cells_with_embedded_newline=n_cells_with_embedded_newline,
        parse_truncated=parse_truncated,
    )


def _accumulate(col: ColumnProfile, raw: str, max_unique_tracked: int) -> None:
    col.n_total += 1
    kind = classify_token(raw)
    col.type_counts[kind] += 1

    if kind == "empty":
        col.n_null += 1
        return

    col.text_bytes += len(raw.encode("utf-8", "replace"))

    if not col.unique_capped:
        if raw not in col._uniques:
            if len(col._uniques) >= max_unique_tracked:
                col.unique_capped = True
            else:
                col._uniques.add(raw)

    if kind in ("int", "float"):
        try:
            v = float(raw)
        except ValueError:
            return
        if not math.isfinite(v):
            return
        col.numeric_min = v if col.numeric_min is None else min(col.numeric_min, v)
        col.numeric_max = v if col.numeric_max is None else max(col.numeric_max, v)


# --------------------------------------------------------------------------- #
# Output writers
# --------------------------------------------------------------------------- #


def _write_csv(
    rows: list[dict[str, object]],
    dest: Path,
    fieldnames: list[str] | None = None,
) -> None:
    """Write ``rows`` as CSV. When ``rows`` is empty but ``fieldnames`` is
    given, a header-only file is written (never a zero-byte file)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    names = fieldnames or (list(rows[0].keys()) if rows else None)
    if names is None:
        dest.write_text("", encoding="utf-8")
        return
    with dest.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=names)
        w.writeheader()
        w.writerows(rows)


def _md_cell(value: object) -> str:
    """Render a value for a Markdown table cell without breaking the table."""
    return (str(value)
            .replace("\\", "\\\\")
            .replace("|", "\\|")
            .replace("\r", " ")
            .replace("\n", " "))


def _md_table(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "_(none)_\n"
    cols = list(rows[0].keys())
    out = ["| " + " | ".join(_md_cell(c) for c in cols) + " |",
           "| " + " | ".join("---" for _ in cols) + " |"]
    for r in rows:
        out.append("| " + " | ".join(_md_cell(r.get(c, "")) for c in cols) + " |")
    return "\n".join(out) + "\n"


def _human_bytes(n: int) -> str:
    step = 1024.0
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < step:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= step
    return f"{n:.1f} PB"


def save_profile(profile: TableProfile, outdir: str | Path) -> list[Path]:
    """Write the profile to ``outdir`` as one Markdown overview plus CSV tables.

    File stem is derived from the source filename, e.g. ``rtt_2026_06``.
    Also writes ``<stem>__MANIFEST.txt`` inventorying this run's artifacts
    (stale files from a previous run with the same stem are **not** deleted;
    the manifest is the record of what belongs to the current run).
    Returns the list of paths written.
    """
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stem = Path(profile.path).stem
    written: list[Path] = []

    col_rows = [c.as_row() for c in profile.columns]
    p = outdir / f"{stem}__columns.csv"
    _write_csv(col_rows, p, fieldnames=list(col_rows[0].keys()) if col_rows else [
        "position", "column", "inferred_dtype", "n_total", "n_non_null",
        "n_null", "null_pct", "n_unique", "numeric_min", "numeric_max",
        "est_memory_bytes", "type_mix",
    ])
    written.append(p)

    for role, cat in profile.categoricals.items():
        fns = ["code", "row_count"] + (["name"] if cat.name_column else [])
        p = outdir / f"{stem}__{role}.csv"
        _write_csv(cat.rows(), p, fieldnames=fns)
        written.append(p)

    flag_rows = [
        {"flag": flag, "column": col}
        for flag, cols in profile.column_flags.items()
        for col in cols
    ]
    p = outdir / f"{stem}__column_flags.csv"
    _write_csv(flag_rows, p, fieldnames=["flag", "column"])
    written.append(p)

    anomaly_rows = [
        {"role": role, **row}
        for role, cat in profile.categoricals.items()
        for row in cat.mapping_anomaly_rows()
    ]
    p = outdir / f"{stem}__mapping_anomalies.csv"
    _write_csv(anomaly_rows, p,
               fieldnames=["role", "kind", "key", "n_related", "related_values"])
    written.append(p)

    p = outdir / f"{stem}__overview.md"
    p.write_text(_render_overview(profile, col_rows), encoding="utf-8")
    written.append(p)

    p = outdir / f"{stem}__MANIFEST.txt"
    p.write_text(
        "# profile artifacts for "
        f"{Path(profile.path).name}\n"
        f"# source SHA is recorded separately in docs/data_provenance.md\n"
        + "\n".join(sorted(w.name for w in written) + [p.name]) + "\n",
        encoding="utf-8",
    )
    written.append(p)

    return written


def _render_overview(profile: TableProfile, col_rows: list[dict[str, object]]) -> str:
    lines: list[str] = []
    a = lines.append
    a(f"# Data profile — `{Path(profile.path).name}`\n")
    a(f"- Generated (UTC): {profile.generated_utc}")
    a(f"- Source path: `{profile.path}`")
    a(f"- File size on disk: {_human_bytes(profile.file_bytes)} "
      f"({profile.file_bytes:,} bytes)")
    a(f"- Encoding assumed: `{profile.encoding}`  ·  delimiter: `{profile.delimiter}`")
    a(f"- Rows (excl. header): **{profile.n_rows:,}**")
    a(f"- Columns: **{profile.n_cols}**")
    a(f"- Duplicate rows (exact whole-row matches): **{profile.duplicate_row_count:,}**")
    a(f"- Ragged rows (field count != {profile.n_cols}): **{profile.n_ragged_rows:,}**")
    a(f"- Estimated in-memory size as Python strings: "
      f"~{_human_bytes(profile.est_memory_bytes)} "
      f"(_estimate only — no pandas measurement_)")
    if profile.structural_warnings:
        a(f"- **Structural warnings: {len(profile.structural_warnings)}** — see below")
    else:
        a("- Structural warnings: none")
    a("")

    if profile.structural_warnings:
        a("## Structural warnings\n")
        a("The file was **not** silently accepted as well-formed. Resolve or "
          "explain each of these before treating the profile as a gate.\n")
        for w in profile.structural_warnings:
            a(f"- {w}")
        if profile.duplicate_headers:
            a(f"\nDuplicate header names: `{'`, `'.join(profile.duplicate_headers)}`")
        if profile.unbound_roles:
            a(f"\nExpected categorical roles left unbound: "
              f"`{'`, `'.join(profile.unbound_roles)}`")
        if profile.week_bucket_sequence_warnings:
            a("\nWeek-bucket sequence issues:")
            for w in profile.week_bucket_sequence_warnings:
                a(f"- {w}")
        if profile.parse_truncated:
            a("\n**Profiling stopped early on a CSV parse error — counts above "
              "are partial.**")
        a("")
    elif profile.unbound_roles:
        a("## Unbound categorical roles\n")
        a("These expected roles were not profiled as categoricals because "
          "their column(s) are absent:\n")
        a(f"`{'`, `'.join(profile.unbound_roles)}`\n")

    a("## Columns\n")
    a("`null_pct` is the percentage of the column that is empty **or "
      "whitespace-only**; literal `NULL`/`NA` text stays a string. "
      "`inferred_dtype` is a shape hint, not a schema. Blanks are "
      "**counted, not interpreted**.\n")
    a(_md_table(col_rows))

    a("\n## Column flags (header text only)\n")
    a("Candidate groupings surfaced for review. Membership is decided purely "
      "from the header string; **no semantic meaning is assigned** here. A "
      "column may appear under more than one flag. Sequence integrity of the "
      "week buckets is checked separately (see structural warnings, if any).\n")
    for flag, cols in profile.column_flags.items():
        if not cols:
            shown = "_(none)_"
        elif len(cols) <= 12:
            shown = ", ".join(f"`{c}`" for c in cols)
        else:
            shown = (f"`{cols[0]}` … `{cols[-1]}` "
                     f"(full list in `{Path(profile.path).stem}__column_flags.csv`)")
        a(f"- **{flag}** ({len(cols)}): {shown}")
    a("")

    for role, cat in profile.categoricals.items():
        anomalies = cat.mapping_anomaly_rows()
        if cat.name_column:
            name_bit = f", {cat.n_distinct_names_nonblank} distinct name(s)"
            if cat.n_blank_name_variants:
                name_bit += f" (+{cat.n_blank_name_variants} blank/whitespace)"
        else:
            name_bit = ""
        a(f"\n## {role} — {cat.n_distinct_codes} distinct code(s){name_bit}\n")
        a(f"Source columns: `{cat.code_column}`"
          + (f" / `{cat.name_column}`" if cat.name_column else ""))
        if cat.name_column is not None:
            if anomalies:
                a(f"\n**Mapping is not 1:1** — {len(anomalies)} anomaly row(s). "
                  f"A blank-vs-blank pair is reported here too; this does not "
                  f"pick a correct value:\n")
                a(_md_table(anomalies))
            else:
                a("\nCode/name mapping is 1:1 across the raw values in this file.")
        a("")
        rows = cat.rows()
        preview = rows if len(rows) <= 60 else rows[:60]
        a(_md_table(preview))
        if len(rows) > len(preview):
            a(f"\n_… {len(rows) - len(preview)} more not shown; see the CSV._\n")

    return "\n".join(lines) + "\n"


def profile_and_save(
    path: str | Path,
    outdir: str | Path = "outputs/profiles",
    **kwargs: object,
) -> tuple[TableProfile, list[Path]]:
    """Convenience: profile ``path`` and immediately write outputs to ``outdir``."""
    prof = profile_csv(path, **kwargs)  # type: ignore[arg-type]
    written = save_profile(prof, outdir)
    return prof, written


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m nhs_rtt.profile",
        description="Profile a raw NHS RTT monthly CSV (structure only, no cleaning).",
    )
    p.add_argument("csv_path", help="Path to the raw CSV, e.g. data/raw/rtt_2026_06.csv")
    p.add_argument("--outdir", default="outputs/profiles",
                   help="Directory for profile outputs (default: outputs/profiles)")
    p.add_argument("--encoding", default="utf-8-sig")
    p.add_argument("--delimiter", default=",")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    prof, written = profile_and_save(
        args.csv_path,
        outdir=args.outdir,
        encoding=args.encoding,
        delimiter=args.delimiter,
    )
    print(f"Profiled {Path(prof.path).name}: "
          f"{prof.n_rows:,} rows x {prof.n_cols} cols, "
          f"{prof.duplicate_row_count:,} duplicate rows, "
          f"{prof.n_ragged_rows:,} ragged rows")
    for role, cat in prof.categoricals.items():
        n_anom = len(cat.mapping_anomaly_rows())
        print(f"  {role:<20} {cat.n_distinct_codes:>6} distinct codes"
              + (f"  ({n_anom} mapping anomalies)" if n_anom else ""))
    for flag, cols in prof.column_flags.items():
        print(f"  flag {flag:<22} {len(cols):>4} column(s)")
    if prof.unbound_roles:
        print(f"  unbound roles: {', '.join(prof.unbound_roles)}")
    if prof.structural_warnings:
        print(f"\n!! {len(prof.structural_warnings)} STRUCTURAL WARNING(S):")
        for w in prof.structural_warnings:
            print(f"   - {w}")
        for w in prof.week_bucket_sequence_warnings:
            print(f"     week-bucket: {w}")
    print("Wrote:")
    for w in written:
        print(f"  {w}")
    return 2 if prof.structural_warnings else 0


if __name__ == "__main__":
    raise SystemExit(main())
