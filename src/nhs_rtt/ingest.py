"""Phase 3 — reproducible multi-month source discovery, provenance and
per-month acceptance for NHS RTT monthly extracts.

This module turns "one validated June file" into a repeatable process. It

* **discovers** production monthly files by an exact filename contract
  (``rtt_YYYY_MM.csv``) and refuses everything else;
* computes **SHA-256** over the exact raw bytes (streamed, read-only);
* parses the internal ``Period`` and cross-checks it against the filename;
* checks each file against the **frozen Phase 1/2 contracts** — it reuses
  :func:`nhs_rtt.semantics.validate_extract` (the exact 105-band schema gate),
  :func:`nhs_rtt.semantics.load_rtt_csv` and
  :func:`nhs_rtt.semantics.candidate_key_report`; it does **not** re-define them;
* resolves revised / re-released files through an explicit registry
  (``data/raw/manifest.json``), failing **closed** when the authoritative
  version is ambiguous;
* returns a structured accept / reject report.

It never edits, moves, renames or "repairs" a raw file. Cross-month diagnostics,
the deterministic combine and the Parquet publication live in
:mod:`nhs_rtt.crossmonth`.
"""

from __future__ import annotations

import csv as _csv
import hashlib
import json
import re
import shutil as _shutil
import sys as _sys
import tempfile as _tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

# CSV fields in these files can be long; lift the default limit defensively
# (mirrors nhs_rtt.profile).
_csv.field_size_limit(min(_sys.maxsize, 2**31 - 1))

from nhs_rtt import semantics as _sem
from nhs_rtt.semantics import CANDIDATE_KEY, PERIOD_COL

__all__ = [
    "PRODUCTION_FILENAME_RE", "PERIOD_VALUE_RE", "RESERVED_PROVENANCE_COLUMNS",
    "SourceError", "AmbiguousRevisionError",
    "parse_production_filename", "parse_period_value",
    "sha256_file", "count_data_rows", "distinct_period_values",
    "SourceEntry", "SourceRegistry", "RevisionResolution",
    "DiscoveredMonth", "DiscoveryResult", "discover_sources",
    "AcceptanceReport", "accept_month",
    "main",
]

#: Column names Phase 3 attaches as provenance (see
#: :data:`nhs_rtt.crossmonth.PROVENANCE_COLS`). A source CSV must not already
#: contain any of these — its value would otherwise be silently overwritten at
#: combination (P3-A05). ``accept_month`` rejects such a source before
#: publication and ``combine_months`` asserts the same defensively.
RESERVED_PROVENANCE_COLUMNS = (
    "source_file", "source_sha256", "reporting_month", "source_row_index")

# --------------------------------------------------------------------------- #
# Filename + Period contracts
# --------------------------------------------------------------------------- #

#: Exact intended production filename, e.g. ``rtt_2026_04.csv``. Anchored and
#: case-sensitive — ``RTT_2026_04.CSV``, ``rtt_2026_4.csv``,
#: ``rtt_2026_04.csv.bak`` do **not** match.
PRODUCTION_FILENAME_RE = re.compile(r"^rtt_(\d{4})_(\d{2})\.csv$")

#: ``Period`` cell contract, e.g. ``RTT-April-2026``.
PERIOD_VALUE_RE = re.compile(r"^RTT-([A-Za-z]+)-(\d{4})$")

#: Loose "looks like somebody's RTT monthly file" matcher. Used **only** to
#: separate a *malformed production candidate* (surfaced explicitly) from
#: unrelated clutter (ignored quietly). Deliberately permissive — it is not an
#: acceptance check. Also catches backup / temp suffixes on an RTT-like csv
#: name (``rtt_2026_04.csv.bak``, ``…​.csv~``, ``…​.csv.tmp``) so they are
#: surfaced, not silently ignored (P3-A06). The strict production matcher
#: :data:`PRODUCTION_FILENAME_RE` is unchanged.
_RTT_LIKE_RE = re.compile(r"(?i)^rtt[ _.\-].*\.csv([.~][A-Za-z0-9_.~-]*)?$")

_MONTH_NUMBER = {name: n for n, name in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}


class SourceError(Exception):
    """Base class for Phase 3 source-acceptance errors."""


class AmbiguousRevisionError(SourceError):
    """Two files claim one reporting month with different SHA-256 and the
    registry does not single out exactly one ``selected`` release. Fail closed —
    never resolved by file order, mtime, name sort or size."""


def parse_production_filename(name: str) -> str:
    """``'rtt_2026_04.csv'`` -> ``'2026-04'``.

    Raises ``ValueError`` for any name that is not the exact production pattern
    or whose month is not ``01``-``12``.
    """
    m = PRODUCTION_FILENAME_RE.match(name)
    if not m:
        raise ValueError(
            f"not a production RTT filename: {name!r} (expected 'rtt_YYYY_MM.csv')")
    year, month = m.group(1), m.group(2)
    if not 1 <= int(month) <= 12:
        raise ValueError(f"{name!r}: month {month!r} is out of range 01-12")
    return f"{year}-{month}"


def parse_period_value(value: str | None) -> str:
    """``'RTT-April-2026'`` -> ``'2026-04'``. Raises ``ValueError`` otherwise.

    One documented policy: ``RTT-<MonthName>-<YYYY>``, month name in English,
    case-insensitive. The raw ``Period`` column is never rewritten — callers
    keep it and derive a separate canonical ``reporting_month``.
    """
    if value is None or value.strip() == "":
        raise ValueError("Period value is missing / blank")
    m = PERIOD_VALUE_RE.match(value.strip())
    if not m:
        raise ValueError(
            f"unparseable Period value: {value!r} (expected 'RTT-<MonthName>-<YYYY>')")
    name, year = m.group(1).lower(), m.group(2)
    if name not in _MONTH_NUMBER:
        raise ValueError(f"unknown month name in Period value: {value!r}")
    return f"{year}-{_MONTH_NUMBER[name]:02d}"


# --------------------------------------------------------------------------- #
# Raw-byte helpers (read-only)
# --------------------------------------------------------------------------- #

def sha256_file(path: str | Path, *, _chunk: int = 1 << 20) -> str:
    """SHA-256 hex digest of the **exact raw bytes** of ``path`` (streamed).

    The file is opened read-only; Phase 3 never writes a raw file.
    """
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(_chunk), b""):
            h.update(block)
    return h.hexdigest()


def count_data_rows(path: str | Path, *, encoding: str = "utf-8-sig") -> int:
    """Number of CSV data records (header excluded), from an **independent**
    streaming parse — the cross-check for row conservation against the loaded
    frame. Handles quoted embedded newlines the same way ``pandas`` does."""
    with Path(path).open("r", newline="", encoding=encoding) as fh:
        reader = _csv.reader(fh)
        try:
            next(reader)
        except StopIteration:
            return 0
        return sum(1 for _ in reader)


def distinct_period_values(path: str | Path, *, encoding: str = "utf-8-sig") -> list[str]:
    """Distinct raw values of the ``Period`` column, first-seen order. Empty
    list if the column is absent. Streamed — no pandas."""
    with Path(path).open("r", newline="", encoding=encoding) as fh:
        reader = _csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            return []
        if PERIOD_COL not in header:
            return []
        idx = header.index(PERIOD_COL)
        seen: dict[str, None] = {}
        for row in reader:
            seen.setdefault(row[idx] if idx < len(row) else "", None)
        return list(seen)


# --------------------------------------------------------------------------- #
# Source registry — the authoritative *intended* source set
# --------------------------------------------------------------------------- #

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class SourceEntry:
    """One intended source file. ``reporting_period`` is ``"YYYY-MM"``;
    ``file`` is a basename; ``selected`` marks the authoritative release for its
    month when several exist."""

    reporting_period: str
    file: str
    sha256: str
    selected: bool
    revision_note: str | None = None
    source_url: str | None = None


@dataclass
class RevisionResolution:
    """Outcome of resolving which file is authoritative for one reporting
    month."""

    reporting_month: str
    chosen_file: str
    chosen_sha256: str
    duplicate_files: list[str] = field(default_factory=list)   # same bytes, ignored
    candidate_files: list[str] = field(default_factory=list)   # all files for the month
    note: str | None = None


@dataclass
class SourceRegistry:
    """Parsed ``data/raw/manifest.json``. Holds only the *intended* source set —
    never generated validation results."""

    entries: list[SourceEntry]
    path: str | None = None

    # -- construction ----------------------------------------------------
    @classmethod
    def load(cls, path: str | Path) -> "SourceRegistry":
        path = Path(path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or "sources" not in raw or not isinstance(raw["sources"], list):
            raise ValueError(f"{path.name}: expected an object with a 'sources' list")
        entries: list[SourceEntry] = []
        seen: set[tuple[str, str]] = set()
        for i, item in enumerate(raw["sources"]):
            if not isinstance(item, dict):
                raise ValueError(
                    f"{path.name}: sources[{i}] must be a JSON object, got "
                    f"{type(item).__name__}")
            for req in ("reporting_period", "file", "sha256", "selected"):
                if req not in item:
                    raise ValueError(f"{path.name}: sources[{i}] missing {req!r}")
            for strfield in ("reporting_period", "file", "sha256"):
                if not isinstance(item[strfield], str):
                    raise ValueError(
                        f"{path.name}: sources[{i}].{strfield} must be a string")
            for opt in ("revision_note", "source_url"):
                if item.get(opt) is not None and not isinstance(item.get(opt), str):
                    raise ValueError(
                        f"{path.name}: sources[{i}].{opt} must be a string or null")
            rp, fn, sha = item["reporting_period"], item["file"], str(item["sha256"]).lower()
            if not re.match(r"^\d{4}-\d{2}$", str(rp)):
                raise ValueError(f"{path.name}: sources[{i}].reporting_period {rp!r} not 'YYYY-MM'")
            if not PRODUCTION_FILENAME_RE.match(str(fn)):
                raise ValueError(f"{path.name}: sources[{i}].file {fn!r} not 'rtt_YYYY_MM.csv'")
            if not _HEX64_RE.match(sha):
                raise ValueError(f"{path.name}: sources[{i}].sha256 is not a 64-char hex digest")
            if not isinstance(item["selected"], bool):
                raise ValueError(f"{path.name}: sources[{i}].selected must be true/false")
            if parse_production_filename(str(fn)) != str(rp):
                raise ValueError(
                    f"{path.name}: sources[{i}] file {fn!r} disagrees with "
                    f"reporting_period {rp!r}")
            # A month may legitimately list several *releases* (same filename,
            # different bytes over time); each exact byte-stream is listed once.
            if (str(rp), sha) in seen:
                raise ValueError(
                    f"{path.name}: duplicate (reporting_period, sha256) for {rp}")
            seen.add((str(rp), sha))
            entries.append(SourceEntry(
                reporting_period=str(rp), file=str(fn), sha256=sha,
                selected=bool(item["selected"]),
                revision_note=item.get("revision_note"),
                source_url=item.get("source_url"),
            ))

        # Each reporting period must have an unambiguous authoritative source:
        # at most one 'selected: true' per month, and whenever a month carries
        # more than one distinct-hash release exactly one must be selected.
        months = {e.reporting_period for e in entries}
        for m in sorted(months):
            month_entries = [e for e in entries if e.reporting_period == m]
            selected = [e for e in month_entries if e.selected]
            if len(selected) > 1:
                raise ValueError(
                    f"{path.name}: reporting period {m} has {len(selected)} "
                    f"'selected: true' entries ({[e.file for e in selected]}); "
                    "exactly one authoritative release is required")
            distinct_hashes = {e.sha256 for e in month_entries}
            if len(distinct_hashes) > 1 and len(selected) != 1:
                raise ValueError(
                    f"{path.name}: reporting period {m} lists "
                    f"{len(distinct_hashes)} different-hash releases but "
                    f"{len(selected)} are 'selected' (need exactly 1)")
        return cls(entries=entries, path=str(path))

    # -- lookups -------------------------------------------------------
    def for_month(self, reporting_month: str) -> list[SourceEntry]:
        return [e for e in self.entries if e.reporting_period == reporting_month]

    def entry_for_hash(self, sha256: str) -> SourceEntry | None:
        """Exact byte-identity lookup — the primary provenance check."""
        sha = sha256.lower()
        for e in self.entries:
            if e.sha256 == sha:
                return e
        return None

    def entry_for_file(self, filename: str) -> SourceEntry | None:
        """First entry naming ``filename`` (a month may list several
        releases under the same name — prefer :meth:`entry_for_hash`)."""
        for e in self.entries:
            if e.file == filename:
                return e
        return None

    def selected_for_month(self, reporting_month: str) -> list[SourceEntry]:
        return [e for e in self.for_month(reporting_month) if e.selected]

    # -- revision resolution ----------------------------------------
    def resolve_month(self, reporting_month: str,
                      observed: list[tuple[str, str]]) -> RevisionResolution:
        """Pick the authoritative ``(file, sha256)`` for ``reporting_month``.

        ``observed`` is ``[(filename, sha256), ...]`` for every discovered file
        that maps to this month.

        * same month + **same** SHA-256 across files -> one artifact; the extra
          identical files are noted as ``duplicate_files`` and not re-ingested;
        * same month + **different** SHA-256 -> distinct release candidates:
          accept only if **exactly one** observed digest has a registry entry
          with ``selected: true``; otherwise :class:`AmbiguousRevisionError`.

        Never uses file order, mtime, name sort, size or discovery order.
        """
        if not observed:
            raise ValueError(f"{reporting_month}: no observed files to resolve")
        by_hash: dict[str, list[str]] = {}
        for fn, sha in observed:
            by_hash.setdefault(sha.lower(), []).append(fn)
        cand_files = sorted(fn for fn, _ in observed)

        if len(by_hash) == 1:
            sha = next(iter(by_hash))
            files = sorted(by_hash[sha])
            note = (None if len(files) == 1
                    else f"{len(files)} files with identical bytes; treated as one artifact")
            return RevisionResolution(
                reporting_month=reporting_month, chosen_file=files[0],
                chosen_sha256=sha, duplicate_files=files[1:],
                candidate_files=cand_files, note=note)

        # genuinely different releases for one month
        sel = self.selected_for_month(reporting_month)
        sel_hashes = {e.sha256 for e in sel}
        match = [sha for sha in by_hash if sha in sel_hashes]
        if len(match) != 1:
            raise AmbiguousRevisionError(
                f"{reporting_month}: {len(by_hash)} different releases "
                f"{cand_files} and the registry marks "
                f"{len(match)} of them 'selected' (need exactly 1). "
                "Set 'selected': true on the authoritative release in the manifest.")
        sha = match[0]
        chosen = sorted(by_hash[sha])[0]
        return RevisionResolution(
            reporting_month=reporting_month, chosen_file=chosen, chosen_sha256=sha,
            duplicate_files=[], candidate_files=cand_files,
            note=f"selected release resolved from registry among {sorted(by_hash)}")


# --------------------------------------------------------------------------- #
# Deterministic discovery
# --------------------------------------------------------------------------- #

@dataclass
class DiscoveredMonth:
    reporting_month: str
    files: list[str]                 # basenames, sorted
    multiple_candidates: bool


@dataclass
class DiscoveryResult:
    raw_dir: str
    months: list[DiscoveredMonth]         # sorted by reporting_month
    production_files: list[str]           # every exact-match basename, sorted
    malformed_candidates: list[str]       # RTT-like but not the exact contract
    ignored: list[str]                    # unrelated files, sorted

    def month(self, reporting_month: str) -> DiscoveredMonth | None:
        for m in self.months:
            if m.reporting_month == reporting_month:
                return m
        return None


def discover_sources(raw_dir: str | Path) -> DiscoveryResult:
    """Find production monthly RTT files in ``raw_dir`` deterministically.

    Only names matching :data:`PRODUCTION_FILENAME_RE` **with a valid month**
    enter ingestion. A name that *looks* like an RTT monthly file but breaks the
    contract (wrong case, ``rtt_2026_4.csv``, ``rtt_2026_13.csv``,
    ``rtt_2026_04.csv.bak`` …) is put in ``malformed_candidates`` and surfaced
    explicitly — it is never silently ignored. Genuinely unrelated files go to
    ``ignored``. Output ordering is by ``(reporting_month, filename)`` and never
    depends on filesystem order or mtime. A reporting month with more than one
    candidate file is flagged for revision resolution.
    """
    raw_dir = Path(raw_dir)
    names = sorted(p.name for p in raw_dir.iterdir() if p.is_file())
    production: list[str] = []
    malformed: list[str] = []
    ignored: list[str] = []
    by_month: dict[str, list[str]] = {}
    for name in names:
        try:
            month = parse_production_filename(name)
        except ValueError:
            (malformed if _RTT_LIKE_RE.match(name) else ignored).append(name)
            continue
        production.append(name)
        by_month.setdefault(month, []).append(name)
    months = [
        DiscoveredMonth(reporting_month=m, files=sorted(fs),
                        multiple_candidates=len(fs) > 1)
        for m, fs in sorted(by_month.items())
    ]
    return DiscoveryResult(raw_dir=str(raw_dir), months=months,
                           production_files=sorted(production),
                           malformed_candidates=sorted(malformed),
                           ignored=sorted(ignored))


# --------------------------------------------------------------------------- #
# Per-month acceptance gate
# --------------------------------------------------------------------------- #

@dataclass
class AcceptanceReport:
    """Structured accept / reject outcome for one candidate monthly file.

    ``blocking`` is empty iff the file is ``accepted``. The raw file is never
    modified regardless of outcome.
    """

    path: str
    filename: str
    accepted: bool = False
    blocking: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    reporting_month_from_filename: str | None = None
    period_values: list[str] = field(default_factory=list)
    reporting_month_from_period: str | None = None
    reporting_month: str | None = None            # canonical, only when agreed
    sha256: str | None = None                     # digest of the one immutable snapshot (P3-A03)
    sha256_after: str | None = None               # informational re-hash of the ORIGINAL path
    expected_sha256: str | None = None
    provenance_source: str | None = None          # 'registry' | 'expected_sha256' | None
    schema_ok: bool | None = None
    n_week_bands: int | None = None
    n_data_rows: int | None = None
    n_loaded_rows: int | None = None
    candidate_key_usable: bool | None = None
    candidate_key_note: str | None = None
    reserved_provenance_columns_present: list[str] = field(default_factory=list)
    #: The loaded frame, bound to the accepted bytes (``sha256``). Present only
    #: on an accepted report; consumed by the combine step so publication never
    #: re-reads a mutable source path (P3-A03). Excluded from :meth:`as_dict`.
    frame: "pd.DataFrame | None" = field(default=None, repr=False)

    def as_dict(self) -> dict[str, object]:
        return {k: v for k, v in self.__dict__.items() if k != "frame"}


def _block(report: AcceptanceReport, msg: str) -> None:
    report.blocking.append(msg)


def accept_month(path: str | Path, *, registry: SourceRegistry | None = None,
                 expected_sha256: str | None = None,
                 discovery_sha256: str | None = None,
                 encoding: str = "utf-8-sig") -> AcceptanceReport:
    """Run the full monthly acceptance gate on one raw CSV.

    Blocking conditions (each recorded; the file is still only *logically*
    rejected — never moved or repaired):

    1. file missing / unreadable;
    2. filename not the exact production pattern;
    3. the snapshot digest disagrees with ``discovery_sha256`` (the source
       changed between discovery and the one acceptance read) — P3-A03;
    4. a **reserved Phase 3 provenance column name** is present in the source
       header (:data:`RESERVED_PROVENANCE_COLUMNS`) — P3-A05;
    5. ``Period`` absent / blank / unparseable / more than one distinct value /
       disagreeing with the filename month;
    6. provenance cannot be established or bound: no registry digest match and no
       ``expected_sha256``; **or the matched registry entry authorises a
       different reporting month / filename than the accepted one** (P3-A02); or
       a supplied ``expected_sha256`` disagrees with the snapshot digest;
    7. fails :func:`nhs_rtt.semantics.validate_extract` (missing key/measure
       columns, duplicate headers, anything but the exact canonical 105-band
       schema);
    8. fails to load (negative values, a non-integer measure cell, …) — the
       load error is normalised into a structured message (P3-A07);
    9. loaded row count != an independent CSV-aware streamed data-row count;
    10. candidate key: a column absent, a missing or whitespace-only key cell,
        or not unique;
    11. the file is not the ``selected`` release for its month when the registry
        lists more than one.

    A change to the **original** path *after* the snapshot is taken produces a
    warning, not a block — the accepted frame is bound to the snapshot.

    On an accepted report, ``frame`` holds the DataFrame derived from the same
    **immutable snapshot** whose digest is ``sha256``; the caller must combine
    from that frame, never by re-reading ``path``.

    P3-A03 (closure): the mutable source has one authoritative snapshot-acquisition
    read plus an informational reread used only for warning/reporting.
    The SHA-256 and *all* validation / parsing / loading run against
    that snapshot, so a temporary change to the original file during the load
    window cannot misbind the accepted bytes. The original file is never
    written; the snapshot never enters provenance (basename stays the original).
    """
    path = Path(path)
    report = AcceptanceReport(path=str(path), filename=path.name)

    # 1. authoritative snapshot-acquisition read ---------------------
    if not path.is_file():
        _block(report, "file does not exist or is not a regular file")
        return report
    try:
        data = path.read_bytes()
    except OSError as exc:
        _block(report, f"file is unreadable: {exc}")
        return report

    # 2. filename contract -----------------------------------------
    try:
        report.reporting_month_from_filename = parse_production_filename(path.name)
    except ValueError as exc:
        _block(report, f"filename: {exc}")

    # 3. digest OF THE SNAPSHOT BYTES; guard the discovery -> snapshot window
    report.sha256 = hashlib.sha256(data).hexdigest()
    if discovery_sha256 is not None and report.sha256 != discovery_sha256.lower():
        _block(report, "source bytes changed between discovery and the acceptance "
                       f"snapshot: {discovery_sha256} -> {report.sha256}")

    # Everything below runs against `snap` — a private copy of exactly `data`.
    snap_dir = Path(_tempfile.mkdtemp(prefix="nhs_rtt_snap_"))
    snap = snap_dir / path.name
    try:
        snap.write_bytes(data)
        _accept_from_snapshot(report, snap, encoding=encoding,
                              registry=registry, expected_sha256=expected_sha256)
    finally:
        _shutil.rmtree(snap_dir, ignore_errors=True)

    # Informational only: has the ORIGINAL path changed since the snapshot? The
    # accepted frame is bound to the snapshot regardless — this is not a block.
    try:
        report.sha256_after = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        report.sha256_after = None
    if report.sha256_after is not None and report.sha256_after != report.sha256:
        report.warnings.append(
            "the original source path changed after the acceptance snapshot; the "
            "accepted frame and its digest are bound to the snapshot, not the new bytes")

    report.accepted = not report.blocking
    if not report.accepted:
        report.frame = None                         # a rejected report never feeds a payload
    return report


def _accept_from_snapshot(report: AcceptanceReport, snap: Path, *, encoding: str,
                          registry: SourceRegistry | None,
                          expected_sha256: str | None) -> None:
    """Steps 4–11 of :func:`accept_month`, run entirely against the immutable
    ``snap`` copy. ``report.sha256`` is already the digest of ``snap``'s bytes;
    ``report.filename`` is the original basename (used for provenance)."""
    filename = report.filename

    # 4. reserved provenance-column collision (P3-A05)
    try:
        with snap.open("r", newline="", encoding=encoding) as fh:
            header = next(_csv.reader(fh))
    except (OSError, StopIteration, _csv.Error):
        header = []
    reserved_present = [c for c in RESERVED_PROVENANCE_COLUMNS if c in header]
    if reserved_present:
        report.reserved_provenance_columns_present = reserved_present
        _block(report, "reserved Phase 3 provenance column name(s) in the source "
                       f"header: {reserved_present} - reject (Phase 3 would "
                       "otherwise overwrite a source value)")

    # 5. Period contract + canonical reporting month
    report.period_values = distinct_period_values(snap, encoding=encoding)
    if not report.period_values:
        _block(report, f"{PERIOD_COL!r} column is absent or the file has no data rows")
    elif len(report.period_values) > 1:
        _block(report, f"multiple distinct {PERIOD_COL} values: {report.period_values}")
    else:
        try:
            report.reporting_month_from_period = parse_period_value(report.period_values[0])
        except ValueError as exc:
            _block(report, f"Period: {exc}")
        if (report.reporting_month_from_period is not None
                and report.reporting_month_from_filename is not None
                and report.reporting_month_from_period != report.reporting_month_from_filename):
            _block(report, "filename / Period disagree: filename says "
                           f"{report.reporting_month_from_filename}, Period says "
                           f"{report.reporting_month_from_period}")
    if (report.reporting_month_from_period is not None
            and (report.reporting_month_from_filename is None
                 or report.reporting_month_from_period == report.reporting_month_from_filename)):
        report.reporting_month = report.reporting_month_from_period

    # 6. provenance, bound to the canonical reporting month (P3-A02)
    canonical = report.reporting_month
    if expected_sha256 is not None:
        report.expected_sha256 = expected_sha256.lower()
        report.provenance_source = "expected_sha256"
        if report.sha256 != report.expected_sha256:
            _block(report, f"SHA-256 mismatch: observed {report.sha256} != "
                           f"expected {report.expected_sha256}")
    elif registry is not None:
        reg_entry = registry.entry_for_hash(report.sha256)
        if reg_entry is None:
            _block(report, "cannot establish provenance: this file's SHA-256 is not "
                           "in the registry and no expected_sha256 was supplied")
        elif canonical is None:
            _block(report, "cannot bind provenance: the canonical reporting month "
                           "could not be established (see Period / filename)")
        elif reg_entry.reporting_period != canonical:
            _block(report, "provenance: the registry entry for this digest authorises "
                           f"reporting month {reg_entry.reporting_period}, not the "
                           f"accepted month {canonical} - fail closed")
        elif reg_entry.file != filename:
            _block(report, "provenance: the registry names this digest's file "
                           f"{reg_entry.file!r}, but it is on disk as {filename!r}")
        else:
            report.expected_sha256 = reg_entry.sha256
            report.provenance_source = "registry"
    else:
        _block(report, "cannot establish provenance: this file's SHA-256 is not in "
                       "the registry and no expected_sha256 was supplied")

    # 7. frozen structural gate
    schema_bad = False
    try:
        vext = _sem.validate_extract(snap, encoding=encoding, require_full_band_schema=True)
        report.schema_ok = bool(vext["ok"])
        report.n_week_bands = vext.get("n_week_bands")
        if not vext["ok"]:
            schema_bad = True
            for prob in vext["problems"]:
                _block(report, f"schema: {prob}")
    except (OSError, ValueError) as exc:
        schema_bad = True
        _block(report, f"schema: {exc}")

    # 8-10. load (from the snapshot) / conservation / candidate key
    if not schema_bad:
        try:
            df = _sem.load_rtt_csv(snap, encoding=encoding, require_full_band_schema=True)
        except (ValueError, TypeError) as exc:      # normalise input-conversion errors (P3-A07)
            _block(report, f"load: {type(exc).__name__}: {exc}")
            df = None
        if df is not None:
            report.n_loaded_rows = int(len(df))
            report.n_data_rows = count_data_rows(snap, encoding=encoding)
            if report.n_loaded_rows != report.n_data_rows:
                _block(report, "row conservation: loaded "
                               f"{report.n_loaded_rows} != streamed {report.n_data_rows}")

            missing_key_cols = [c for c in CANDIDATE_KEY if c not in df.columns]
            if missing_key_cols:
                _block(report, f"candidate key: column(s) absent {missing_key_cols}")
            else:
                ws_cols = [
                    c for c in CANDIDATE_KEY
                    if (df[c].astype("string").str.strip() == "").fillna(False).any()
                ]
                if ws_cols:
                    _block(report, f"candidate key: whitespace-only key cell(s) in {ws_cols}")
                krep = _sem.candidate_key_report(df, CANDIDATE_KEY)
                report.candidate_key_usable = bool(krep["usable"])
                if not krep["usable"]:
                    report.candidate_key_note = (
                        f"is_unique={krep.get('is_unique')} "
                        f"n_key_cells_missing={krep.get('n_key_cells_missing')} "
                        f"n_duplicate_groups={krep.get('n_duplicate_groups')}")
                    _block(report, f"candidate key not usable ({report.candidate_key_note})")
            report.frame = df                        # derived from the snapshot == report.sha256

    # 11. revision selection (fail closed)
    if (registry is not None and report.reporting_month is not None
            and len(registry.for_month(report.reporting_month)) > 1):
        sel_hashes = {e.sha256 for e in registry.selected_for_month(report.reporting_month)}
        if report.sha256 not in sel_hashes:
            _block(report, f"revision: {filename!r} (sha {report.sha256[:12]}) is not "
                           f"the selected release for {report.reporting_month} - fail closed")


# --------------------------------------------------------------------------- #
# CLI entry point (delegates the combine/publish to nhs_rtt.crossmonth)
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    import argparse

    from nhs_rtt import crossmonth

    p = argparse.ArgumentParser(
        prog="python -m nhs_rtt.ingest",
        description="Phase 3 — discover, validate, provenance-track and combine "
                    "monthly NHS RTT extracts (no cleaning / reshaping).")
    p.add_argument("--raw-dir", default="data/raw")
    p.add_argument("--registry", default="data/raw/manifest.json")
    p.add_argument("--out-dir", default="data/interim")
    p.add_argument("--no-parquet", action="store_true",
                   help="run discovery + acceptance + diagnostics only")
    args = p.parse_args(argv)

    result = crossmonth.run_phase3(
        raw_dir=args.raw_dir, registry_path=args.registry,
        out_dir=args.out_dir, write_parquet=not args.no_parquet)
    print(result.render_text())
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
