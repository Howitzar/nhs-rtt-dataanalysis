# Phase 3 — Reproducible Multi-Month Ingestion & Provenance

Scope: `data/raw/rtt_2026_04.csv`, `rtt_2026_05.csv`, `rtt_2026_06.csv` (and any
later monthly file). Companion to `docs/rtt_semantics.md` /
`docs/rtt_grain_and_aggregation.md` (Phase 2, frozen) and
`docs/data_provenance.md`. Code: `src/nhs_rtt/ingest.py`,
`src/nhs_rtt/crossmonth.py`. Notebook: `notebooks/03_multi_month_ingestion.ipynb`
(thin orchestration only). Tests: `tests/test_ingest.py`,
`tests/test_crossmonth.py`.

Phase 3 is **ingestion and provenance only**. It turns "one validated month"
into a repeatable, deterministic, provenance-tracked process that discovers,
validates, accepts/rejects and combines monthly extracts **without changing
their source meaning**. No reshaping, cleaning, imputation, modelling, SQL, KPIs
or BI — those are Phase 4+.

---

## 1. Architecture

```
data/raw/manifest.json  (intended source set, tracked)
        │
        ▼
discover_sources(raw_dir)         nhs_rtt.ingest
   exact filename contract, deterministic order, malformed vs unrelated split
        │
        ▼
SourceRegistry.resolve_month()    same-month/same-hash → 1 artifact
   revised-release resolution      same-month/different-hash → 'selected' or FAIL CLOSED
        │
        ▼
accept_month(path, registry)      per-month acceptance gate (§3)
   reuses frozen Phase 2: validate_extract · load_rtt_csv · candidate_key_report
        │
        ▼
crossmonth.mapping_diagnostics / coverage_diagnostics / part2a_subset_diagnostics
   cross-month warnings — never rejection
        │
        ▼
crossmonth.combine_months()       deterministic concat + provenance columns
   asserts row conservation and candidate-key completeness + uniqueness
        │
        ▼
crossmonth.write_combined_parquet()   data/interim/rtt_combined.parquet  (regenerated, untracked)
        + rtt_combined.ingest_manifest.json (observed evidence)
        + roundtrip_check (data-level)
```

Module split: `ingest.py` = discovery, provenance, registry, per-month
acceptance; `crossmonth.py` = cross-month diagnostics, combine, Parquet.
Import direction is one-way (`crossmonth` → `ingest`); `ingest.main()` reaches
`crossmonth` only lazily, so there is no import cycle. Entry point:
`python -m nhs_rtt.ingest` (delegates to `crossmonth.run_phase3`).

No new dependencies (`pandas` + `pyarrow` already declared). Raw files are
opened read-only; Phase 3 never writes, moves, renames or "repairs" a raw file.

---

## 2. Deterministic source discovery

**Filename contract** (`PRODUCTION_FILENAME_RE`): `rtt_YYYY_MM.csv`, anchored,
case-sensitive, month `01`–`12`. `parse_production_filename` → canonical
`"YYYY-MM"`.

`discover_sources(raw_dir)` returns:

| Field | Meaning |
|---|---|
| `production_files` | exact-contract matches, sorted |
| `malformed_candidates` | RTT-*like* names that break the contract (`rtt_2026_4.csv`, `rtt_2026_13.csv`, `RTT_2026_06.CSV`, `rtt_2026_04.csv.bak`, …) — **surfaced explicitly**, never silently ignored |
| `ignored` | genuinely unrelated files (`README.md`, `notes.txt`, …) |
| `months` | `DiscoveredMonth(reporting_month, files, multiple_candidates)`, sorted by `reporting_month` |

Ordering is by `(reporting_month, filename)` and **never** depends on filesystem
order or mtime (`sorted(...)` unconditionally). The filename contract permits
exactly one name per month, so on-disk discovery never yields more than one
candidate per month; the same-month/different-bytes (revision) case is handled
by the registry (§4).

---

## 3. Monthly acceptance gate — `accept_month`

Returns an `AcceptanceReport` with `accepted` (⇔ `blocking == []`), a `blocking`
list, a `warnings` list and observed facts. **Blocking conditions:**

| # | Blocks when | Reuses |
|---|---|---|
| 1 | file missing / unreadable | — |
| 2 | filename not the exact production contract | `parse_production_filename` |
| 3 | the **snapshot digest** disagrees with `discovery_sha256` (the source changed between discovery and the one acceptance read) — P3-A03 | `hashlib.sha256` |
| 4 | a **reserved Phase 3 provenance column name** is present in the source header (`RESERVED_PROVENANCE_COLUMNS`) — P3-A05 | — |
| 5 | `Period` absent / blank / unparseable / **more than one distinct value** / disagrees with the filename month | `parse_period_value` |
| 6 | provenance cannot be established or bound: no registry digest match and no `expected_sha256`; **or the matched registry entry's `reporting_period` / `file` is not the accepted month / filename** (P3-A02); or a supplied `expected_sha256` disagrees with the snapshot digest | `SourceRegistry.entry_for_hash` |
| 7 | not the exact canonical **105-band** schema; missing key/measure columns; duplicate headers | `semantics.validate_extract(require_full_band_schema=True)` |
| 8 | fails to load — negative values, a **non-integer measure cell**, … — the pandas `ValueError`/`TypeError` is normalised into a structured `load:` message (P3-A07) | `semantics.load_rtt_csv` |
| 9 | loaded row count ≠ an **independent CSV-aware** streamed data-row count | `count_data_rows` (uses `csv.reader`, not newline counting) |
| 10 | candidate-key column absent, a **missing or whitespace-only** key cell, or not unique | `semantics.candidate_key_report` + an explicit `str.strip()==""` check |
| 11 | the registry lists more than one release for the month and this file's byte-stream is not the `selected` one | `SourceRegistry.selected_for_month` |

**Immutable snapshot (P3-A03, closure).** `accept_month` reads the mutable
source **in one authoritative snapshot-acquisition read** into a private temp copy. `source_sha256` is the
SHA-256 of that snapshot's bytes, and *every* step — reserved-column check,
`Period`, `validate_extract`, `load_rtt_csv`, `count_data_rows` — runs against
the snapshot. So a temporary change to the original file during the load window
(even one reverted before acceptance finishes) cannot misbind the accepted
bytes: the accepted `frame` and its digest are the snapshot's. The original
file is never written; the snapshot is deleted afterwards and never enters
provenance (`source_file` stays the original basename). A change to the original
*after* the snapshot produces a `warnings` entry, not a block. If
`discovery_sha256` is supplied it is compared against the snapshot digest — a
change *before* the snapshot is a hard reject.

Provenance is also bound to the **canonical reporting month**: a registry digest
authorises a source only for *its own* month — a cross-month hash match is
rejected (P3-A02). On an accepted report `frame` holds the DataFrame derived
from the snapshot; the caller **must** combine from `frame`, never by re-reading
the path.

An invalid file is only *logically* rejected — it is left exactly where and as
it is.

---

## 4. SHA-256 provenance & the source registry

`data/raw/manifest.json` (tracked via a precise `.gitignore` negation;
`data/raw/*` otherwise stays ignored) is the **authoritative intended source
set** — never generated results. One entry per byte-stream:

```json
{ "reporting_period": "2026-06", "file": "rtt_2026_06.csv",
  "sha256": "<64 hex>", "selected": true,
  "revision_note": null, "source_url": null }
```

`SourceRegistry.load` validates: `reporting_period` is `YYYY-MM`; `file` matches
the filename contract and agrees with `reporting_period`; `sha256` is 64-hex;
`(reporting_period, sha256)` is unique; **at most one `selected` per month**;
and whenever a month lists more than one distinct-hash release, **exactly one**
is `selected` (otherwise `load` fails).

### Revised / re-released files — `SourceRegistry.resolve_month`

| Situation | Behaviour |
|---|---|
| same month, **same** SHA-256 across files | one artifact; the identical duplicates are noted, not re-ingested |
| same month, **different** SHA-256 | distinct release candidates; accepted only if **exactly one** observed digest is a `selected` registry entry for that month; otherwise `AmbiguousRevisionError` — **fail closed** |

Never resolved by file order, mtime, filename sort, file size or discovery
order. NHS revision metadata is **not invented** (`revision_note` / `source_url`
are optional and currently `null`; `Period` alone does not distinguish a
revision — see P2-U5).

---

## 5. Period contract

`parse_period_value`: `^RTT-<MonthName>-<YYYY>$` (English month name,
case-insensitive) → canonical `"YYYY-MM"`. The raw `Period` column is **never
overwritten**; the canonical `reporting_month` is a separate derived value and
must equal the filename month. April/May/June 2026 all use exactly this format,
one value per file. Mapping a `Period` to a calendar **month-end date** (and the
flow-vs-stock temporal meaning, already documented in `rtt_semantics.md` §2) is
left to Phase 4/5 — see P2-U5.

---

## 6. Cross-month diagnostics (warnings, never rejection)

`crossmonth.mapping_diagnostics` — for Provider, Commissioner, Treatment
Function, Provider Parent, Commissioner Parent code↔name:

* `code_name_changes` — one code carrying more than one name across the months;
* `name_code_collisions` — one non-blank name carried by several codes
  (`scope` = `within_month` / `cross_month`);
* `membership_changes` — codes appearing / disappearing between consecutive
  months.

`<NA>` name groups are kept explicitly (`dropna=False`). **"Codes identify;
names label"** — a change is surfaced, never auto-resolved.

`coverage_diagnostics` — per month: row count, RTT-part counts, TFC coverage,
missingness prevalence (`Total` / unknown-clock / `Total All` / all-band-blank).

`part2a_subset_diagnostics` — the frozen `semantics.part_2a_subset_conformance`
per month; collates violations + "no matching Part_2" groups (P2-U7, §9).

Any diagnostic grouping over a nullable dimension preserves the NA group
(`dropna=False`).

### Observed for April–June 2026 (development inputs)

| Check | Result |
|---|---|
| 105-band schema / header | identical 121-col header all three months; all pass `validate_extract` |
| `Period` format | `RTT-<MonthName>-<YYYY>`, one value per file, agrees with filename |
| Candidate key | unique + `usable` per month **and** on the 541,363-row combined frame |
| Code↔name maps | **no drift** across the three months |
| RTT parts | all five present each month |
| Treatment functions | 24 codes each month, identical set |
| Membership | minor provider churn (≈1 retired, ≈9 new by June); commissioner `Y63` appears in June — warnings only |
| `Part_2A > Part_2` | April 0 · May **1** (`NT230`/`05V`/`C_100`) · June 2 (`RTG`/`84H`/`C_502` + `C_999`) — **P2-U7**, preserved & flagged |
| Contradiction to a frozen Phase 2 decision | **none** |

---

## 7. Intended-source completeness, row conservation & provenance columns

**Intended-source reconciliation (P3-A01).** The registry is the authoritative
intended set. `run_phase3` computes the months with a `selected` entry and, by
default, **requires every one of them to be present and accepted** before it
publishes — a missing intended month sets `ok=False`, adds a note, and withholds
publication (the previous generation is untouched). An explicit
`require_months=[...]` subset is supported and **recorded** in the result
(`requested_subset`) and its notes; absence of a file is never read as
intentional exclusion.

`combine_months(payloads, require_months=…)`:

* rejects any payload frame that already carries a reserved provenance column
  (`ReservedColumnError`, P3-A05);
* when `require_months` is given, the payload months must equal it exactly
  (`IntendedSourceError`, P3-A01);
* months ascending by `reporting_month`; **source row order preserved** within a
  month;
* asserts `len(combined) == Σ len(payload.df)` (`RowConservationError`);
* asserts the candidate key **complete and unique** on the combined frame —
  directly (all 5 columns present, no missing cell, `duplicated(subset=KEY)==0`)
  **and** via `candidate_key_report(...).usable` (`CombinedKeyError` otherwise);
* transforms **no** measure column; `<NA>` missingness preserved;
* a rejected month is simply absent from `payloads` — it can never partially
  contaminate the output.

Every combined row carries exactly four added columns:

| Column | Meaning |
|---|---|
| `source_file` | basename of the accepted raw CSV |
| `source_sha256` | SHA-256 of that file's exact raw bytes |
| `reporting_month` | canonical `"YYYY-MM"` (filename == `Period`) |
| `source_row_index` | **0-based position of the row among the source file's parsed CSV data records** (what `pandas.read_csv` yields) — *not* a physical line number; quoted embedded newlines do not shift it |

The original `Period` column is retained unchanged. No wall-clock run timestamp
enters row-level identity.

---

## 8. CSV → Parquet boundary — atomic publication

`write_combined_parquet` publishes three files as **one logical generation**
(P3-A04):

1. `rtt_combined.parquet` (pyarrow) — wide structure, nullable `Int64` /
   `string` dtypes, `<NA>` missingness and deterministic row order preserved;
2. `rtt_combined.ingest_manifest.json` — **observed ingestion evidence**
   (per-month filename / SHA-256 / rows, combined row count, key uniqueness). Its
   `deterministic` block is reproducible; its `run` block carries a timestamp
   and a `generation_id`, and is excluded from determinism comparisons via
   `deterministic_manifest_view`;
3. `rtt_combined.generation.json` — the **commit marker**: `generation_id`, the
   SHA-256 of the published Parquet and sidecar, and `combined_rows`.

Protocol: everything is written into a private `.staging-*` directory and the
staged Parquet is roundtrip-validated; then the existing published trio is
copied to `*.prev` **only if it currently verifies** (P3-R02 — a failed retry
never overwrites a good backup with an invalid trio); then the three files are
`os.replace`d into place **marker last**. That final `os.replace` is the atomic
commit point. A staged-validation failure raises `PublicationError`; a failed
`os.replace` propagates its `OSError`.

**Consumer contract — `verify_publication(out_dir)`.** A published pair is
*valid* iff:

* the marker exists, is a well-formed object, and its required fields have the
  right types (`generation_id` / `parquet_sha256` / `sidecar_sha256` non-empty
  strings; `combined_rows` a non-negative int);
* `parquet_sha256` / `sidecar_sha256` equal the SHA-256 of the on-disk Parquet
  and sidecar;
* the sidecar's `run.generation_id` equals the marker's `generation_id`;
* `combined_rows` **reconciles** — marker `combined_rows` == sidecar
  `deterministic.combined_rows` == the actual Parquet row count (from cheap
  Parquet metadata) — P3-R01. The returned `combined_rows` is this reconciled
  value.

**Interruption semantics** (not "every interrupted run leaves an invalid trio"):

* failure **before** the first replace → the previous valid generation is intact
  and still verifies;
* failure **during** the replaces → the final paths are invalid, and
  `verify_publication` says so (a hash or row-count disagreement);
* completion of the **marker-last commit** → the new generation is valid, even
  if the caller subsequently fails;
* **a trio is consumable only when `verify_publication` returns `valid: True`.**

`restore_previous_generation(out_dir)` verifies the `*.prev` trio (in a scratch
dir) **before** restoring, then restores and re-verifies; it reports
`restored: True` only when the restored trio verifies, and distinguishes
*no backup* / *backup invalid* / *restore-copy failed* / *restored & valid*.
`run_phase3` fails (`ok=False`) unless `verify_publication` confirms the
generation it just wrote.

`roundtrip_check` (used on the staged Parquet, and re-exported) asserts
**data-level** equality (shape, columns, values, per-column NA counts) — not
byte-for-byte file hashing. `generation_id` is a per-run label (derived from the
Parquet digest + the deterministic block); it is deliberately **not** in the
`deterministic` block, so data-level determinism across runs is unaffected.

**Determinism:** the same accepted source set + same code/environment →
identical combined rows, order, values and provenance, and an identical
`deterministic` manifest block. Verified by re-running and by a payload-order
shuffle.

### Tracked vs regenerated

| Path | Git |
|---|---|
| `src/nhs_rtt/ingest.py`, `crossmonth.py`, tests, this doc, notebook | tracked |
| `data/raw/manifest.json` | **tracked** (precise `.gitignore` negation) |
| `data/raw/*.csv` | ignored (raw NHS data) |
| `data/interim/rtt_combined.{parquet,ingest_manifest.json,generation.json}` and `*.prev` | **ignored** — regenerated from the accepted raw set + `src/` |

---

## 9. Carried-forward Phase 2 items

| ID | Phase 3 status |
|---|---|
| **P2-U3** cross-month stability of schema / candidate key / code↔name maps; revised-release handling; intended-set completeness; month-specific artifact authorization | **Partially addressed for ingestion — pending independent closure confirmation.** Per-file and combined 105-band + candidate-key checks; `mapping_diagnostics` reports drift; fail-closed revised-release policy; intended-source completeness reconciled (P3-A01); provenance bound to the reporting month (P3-A02); accepted bytes bound to the published rows via an **immutable snapshot** (P3-A03 closure, D-039 — not yet re-audited); reserved provenance names rejected (P3-A05). April/May/June show no schema/key/map drift. Full ingestion closure is claimed only once the snapshot fix and P3-R01/R02 pass an independent closure check. |
| **P2-U5** `Period` literal → temporal alignment; file-revision selection | **Partially addressed for ingestion — pending closure confirmation.** `Period` parses to a canonical `reporting_month`, filename agreement enforced, revised releases resolve (or fail closed), and the selected identity is bound to the published bytes via the immutable snapshot (P3-A02/A03, D-039). Calendar **month-end date** mapping and the flow-vs-stock temporal model stay Phase 4/5. |
| **P2-U7** `Part_2A > Part_2` source exceptions | **Carried, unchanged.** `part2a_subset_diagnostics` runs the frozen conformance check per month; values are **preserved and flagged**, never capped. New instance recorded: May 2026 `NT230`/`05V`/`C_100`. |
| P2-U1, P2-U2, P2-U4, P2-U6 | Untouched — not Phase 3 scope. |

---

## 10. Phase 3 boundary (NOT done here)

No waiting-band long reshaping · no analytical/clean dataset · no imputation ·
no dimensional model · no DuckDB / SQL analytics · no KPI logic · no
provider-type enrichment · no trend/statistical analysis · no Power BI · no ML ·
no Spark. The combined artifact is the raw wide structure **plus four
provenance columns** — nothing else.

---

## 11. Post-audit remediation (P3-A01 – P3-A07)

The independent Codex audit (`docs/phase3_codex_audit.md`, PASS WITH CHANGES)
raised five BLOCKING and two NON-BLOCKING findings. Targeted closure changes
(`docs/phase3_remediation_report.md`, decisions D-038):

| ID | Change |
|---|---|
| **P3-A01** | `run_phase3` reconciles the registry's `selected` months against discovered + accepted sources; a missing intended month → `ok=False`, publication withheld. Explicit `require_months` subset supported and recorded. |
| **P3-A02** | `accept_month` binds the registry digest lookup to the **canonical reporting month** and filename; a digest registered under another month is rejected — fail closed. |
| **P3-A03** | *(first remediation)* `accept_month` returns the loaded `frame` and `run_phase3` combines from it. **Closure (D-039):** the mutable source is read **in one authoritative snapshot-acquisition read** into a private snapshot; SHA-256 and *all* validation/parsing/loading run against that snapshot, so a changed-and-restored source during the load window cannot misbind the accepted bytes. Snapshot never enters provenance; original basename retained; original file untouched. |
| **P3-A04** | Atomic publication: stage → validate → copy previous to `*.prev` → `os.replace` (marker last). `verify_publication` is the consumer's validity gate. **Closure (D-039):** `verify_publication` also validates marker structure/types and **reconciles `combined_rows`** across marker, sidecar `deterministic.combined_rows` and the actual Parquet row metadata (P3-R01); `*.prev` is rotated **only when the current trio verifies valid** and `restore_previous_generation` verifies `.prev` before restoring and reports success only on a verified restore (P3-R02). |
| **P3-A05** | A source header containing any of `source_file` / `source_sha256` / `reporting_month` / `source_row_index` is rejected in `accept_month`; `combine_months` re-asserts defensively. |
| **P3-A06** | `_RTT_LIKE_RE` extended so `rtt_*.csv.bak` / `.csv~` / `.csv.tmp` are surfaced as **malformed candidates**, not ignored. Strict `PRODUCTION_FILENAME_RE` unchanged. |
| **P3-A07** | `SourceRegistry.load` validates entry types (non-object / non-string → `ValueError`); the load handler normalises pandas `ValueError`/`TypeError` into a structured `load:` rejection. |

### Closure audit (`docs/phase3_codex_closure_audit.md`, PASS WITH CHANGES)

P3-A01 / A02 / A05 / A06 / A07 **CLOSED**. P3-A03 and P3-A04 **partially closed**
with residuals — the **immutable-snapshot** byte binding (A03), **P3-R01**
(`verify_publication` returned an unchecked marker row count) and **P3-R02**
(a failed retry could overwrite the valid `.prev` backup). Closure remediation
in `docs/phase3_closure_remediation_report.md` (decision **D-039**):

| ID | Closure change |
|---|---|
| **P3-A03 residual** | `accept_month` now reads the source once into a private snapshot and runs the whole gate against it (`_accept_from_snapshot`). Endpoint re-hashing of the mutable path is gone; a post-snapshot change of the original is a warning only. |
| **P3-R01** | `verify_publication` validates marker structure/types and reconciles `combined_rows` (marker == sidecar `deterministic` == Parquet metadata) before returning it. |
| **P3-R02** | `write_combined_parquet` rotates `*.prev` only when the current trio verifies; `restore_previous_generation` verifies `.prev` first and reports the true outcome. |

After closure: **98 Phase 1/2 tests unchanged; 110 Phase 3 tests**
(`test_ingest` 55 + `test_crossmonth` 17 + `test_phase3_audit_remediation` 38)
pass — **208 total**. Real April–June result unchanged (541,363 rows, same
hashes, same diagnostics, stable `generation_id`, publication verifies).

Snapshot read-count clarification: one authoritative snapshot-acquisition read plus an informational reread used only for warning/reporting; the original source is not literally read only once in total.
