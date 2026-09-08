# Phase 3 Targeted Audit Remediation Report

> **SUPERSEDED IN PART (2026-09-08).** The closure audit of *this* remediation
> (`docs/phase3_codex_closure_audit.md`, PASS WITH CHANGES) closed P3-A01 / A02
> / A05 / A06 / A07 but left **P3-A03** and **P3-A04** partially closed
> (residual immutable-byte binding; new findings **P3-R01**, **P3-R02**). The
> closure remediation is in **`docs/phase3_closure_remediation_report.md`**
> (decision **D-039**); `docs/phase3_ingestion.md` §3/§8/§9/§11 is current
> authority. The A03/A04 sections below describe the *first* fix and are
> strengthened there.

**Date:** 2026-09-08 · **Engineer:** Claude Code
**Audit:** `docs/phase3_codex_audit.md` (Codex, **PASS WITH CHANGES**) —
five BLOCKING (P3-A01…A05), two NON-BLOCKING (P3-A06/A07).
**Scope:** smallest robust closure changes only. No redesign, no Phase 4 work,
no change to raw data or the frozen Phase 1/2 contracts. Not committed / tagged /
pushed; no Phase 3 milestone.

Current authority for Phase 3: `docs/phase3_ingestion.md` (§7–§11), decision
D-038. The original submission report `docs/phase3_completion_report.md` carries
a SUPERSEDED-IN-PART banner.

---

## Files changed

| File | Change |
|---|---|
| `src/nhs_rtt/ingest.py` | `RESERVED_PROVENANCE_COLUMNS`; loose `_RTT_LIKE_RE` extended for backup/temp suffixes (A06); `SourceRegistry.load` entry-type validation (A07); `accept_month` reworked — reserved-column reject (A05), month-bound provenance (A02), `discovery_sha256` + post-read re-hash binding (A03), `frame` returned bound to the digest, `(ValueError, TypeError)` load handler (A07); `AcceptanceReport` gains `sha256_after` / `reserved_provenance_columns_present` / `frame` (excluded from `as_dict`). |
| `src/nhs_rtt/crossmonth.py` | `ReservedColumnError` / `IntendedSourceError` / `PublicationError`; `combine_months` gains a reserved-column guard + `require_months`; `write_combined_parquet` rewritten as a **staged → validate → atomic-commit** protocol with a `rtt_combined.generation.json` marker; new `verify_publication` / `restore_previous_generation`; `run_phase3` reconciles the intended source set, uses the bound `frame`, passes `discovery_sha256`, self-verifies the publication, `require_months` param; `Phase3Result` gains `intended_months` / `required_months` / `requested_subset` / `accepted_months` / `missing_intended` / `unexpected_months` / `publication`. |
| `tests/test_phase3_audit_remediation.py` | **new** — 25 closure tests reproducing the audit's A01–A07 scenarios. |
| `tests/test_crossmonth.py` | one assertion string updated to the new "intended-source completeness" note (behaviour unchanged). |
| `notebooks/03_multi_month_ingestion.ipynb` | display-only: shows intended/required/missing/unexpected months, `generation_id`, `verify_publication`; §8 remediation-guarantee notes. Still a thin orchestration layer; executes clean. |
| `docs/phase3_ingestion.md` | §3 blocking table, §4/§7/§8 rewrites, §9 status, new §11 remediation table. |
| `docs/phase3_completion_report.md` | SUPERSEDED-IN-PART banner. |
| `docs/decisions.md` | new **D-038**. |
| `docs/assumptions.md` | P2-U3 / P2-U5 wording aligned to the post-audit closure. |

No raw NHS CSV, `data/interim/` artifact, cache, or executed-notebook copy is
staged. `data/raw/manifest.json` remains the one tracked exception under
`data/raw/`.

---

## Finding-by-finding closure

### P3-A01 — Intended-source completeness

**Change.** `run_phase3` computes `intended_months` = registry entries with
`selected: true`. By default `required_months == intended_months`; a missing
required month sets `ok=False`, records `missing_intended`, adds a note and
**withholds publication** (the previous generation is left intact). An explicit
`require_months=[...]` subset is honoured and recorded in `requested_subset` +
notes. `combine_months(require_months=…)` asserts the payload months equal the
required set exactly (`IntendedSourceError`). A discovered month absent from the
registry is `unexpected_months` → `ok=False`.

**Tests.** `TestA01_*` — full run succeeds; rename one intended source to
`.csv.bak` and rerun → `ok=False`, `missing_intended == ['2026-05']`,
`parquet is None`, and `verify_publication` still returns the earlier 4-row
generation (not silently reduced to June); a registered month never present →
fail; explicit subset recorded.

**Audit reproduction now.** "publish May+June, rename May, rerun" → the audit's
`ok=True, 1 row` becomes **`ok=False`, no republish**; the earlier publication
is unchanged.

### P3-A02 — Registry authorization bound to reporting month

**Change.** `accept_month` establishes the canonical `reporting_month` (Period ==
filename) first, then, for a registry digest match, requires
`reg_entry.reporting_period == canonical` **and** `reg_entry.file == filename`;
otherwise it blocks — fail closed. The prior filename-mismatch *warning* is now a
*block*. The `expected_sha256` path is unchanged and documented as a distinct
explicit mechanism.

**Tests.** `TestA02_*` — a June CSV whose digest is registered under a May
entry: direct `accept_month` blocks ("authorises reporting month 2026-05");
end-to-end `run_phase3` → `ok=False`, June not accepted, `parquet is None`.

### P3-A03 — Accepted bytes bound to published rows

**Change.** The source is hashed once up front (`report.sha256`); compared to
`discovery_sha256` (discovery→acceptance window); re-hashed after all reads
(`report.sha256_after`) and blocked on change (acceptance-internal window).
`accept_month` stores the loaded frame in `report.frame` (bound to
`report.sha256`; cleared on rejection). `run_phase3` builds the payload from
`report.frame` — the mutable path is **never reopened**.

**Tests.** `TestA03_*` — accept value A=7, change file to B=99, confirm
`rep.frame` and the combined output still hold 7; discovery→acceptance change
blocks via `discovery_sha256`; a monkeypatched mid-acceptance digest change
blocks and nulls `frame`; `run_phase3` payload `df is` the accepted `frame`.

### P3-A04 — Publication generation integrity

**Design.** Parquet + evidence sidecar + a `rtt_combined.generation.json`
marker are one logical generation. `write_combined_parquet`:

1. writes the Parquet and sidecar into a private `.staging-<pid>-<ns>/` dir;
2. roundtrip-validates the staged Parquet (`PublicationError` on failure);
3. computes `generation_id = sha256(parquet_digest | deterministic_block)`;
   writes the staged marker recording `generation_id`, `parquet_sha256`,
   `sidecar_sha256`, `combined_rows`;
4. copies any existing complete published trio to `*.prev`;
5. `os.replace`s the three files into place — **marker last**. That final
   `os.replace` is the atomic commit point.

**Consumer verification.** `verify_publication(out_dir)` → *valid* iff the
marker exists and its `parquet_sha256` / `sidecar_sha256` equal the SHA-256 of
the on-disk files **and** the sidecar's `run.generation_id` equals the marker's
`generation_id`. Any half-applied replace leaves a hash disagreement, so the
pair reads **invalid** — never as a spurious valid publication.
`restore_previous_generation(out_dir)` copies the `*.prev` trio back.
`run_phase3` sets `ok=False` unless it self-verifies the generation it wrote.

**Tests.** `TestA04_*` — successful publication self-verifies and the sidecar
`generation_id` matches the marker; a monkeypatched `OSError` on the 2nd
`os.replace` (after Parquet, before sidecar) → `PublicationError`,
`verify_publication` invalid ("SHA-256 mismatch"), then
`restore_previous_generation` returns to gen 1 and re-verifies; a rejected rerun
after a success leaves gen 1 valid; a tampered Parquet is detected as invalid.

### P3-A05 — Reserved provenance-column collision

**Change.** `RESERVED_PROVENANCE_COLUMNS = (source_file, source_sha256,
reporting_month, source_row_index)` in `ingest.py` (kept in sync with
`crossmonth.PROVENANCE_COLS` by an `assert`). `accept_month` reads the source
header and blocks if any reserved name is present. `combine_months` re-asserts
per payload (`ReservedColumnError`). The frozen Phase 2 105-band contract is
untouched.

**Tests.** `TestA05_*` — parametrised over all four names: a 122-column source
containing `source_file='original source value'` is **rejected** (not silently
overwritten); `combine_months` defensive collision raises; an ordinary
121-column source is unaffected and publishes 125 columns with `source_file` ==
the basename.

### P3-A06 — Backup / suffix classification (NON-BLOCKING)

**Change.** `_RTT_LIKE_RE` → `(?i)^rtt[ _.\-].*\.csv([.~][A-Za-z0-9_.~-]*)?$`, so
`rtt_2026_04.csv.bak`, `…​.csv~`, `…​.csv.tmp` land in `malformed_candidates`.
`PRODUCTION_FILENAME_RE` is unchanged, so such files remain non-ingestible.

**Tests.** `TestA06_*` — the three suffix forms are malformed candidates,
`notes.txt` stays ignored, production is `['rtt_2026_06.csv']`;
`parse_production_filename('rtt_2026_04.csv.bak')` still raises.

### P3-A07 — Structured invalid-input rejection (NON-BLOCKING)

**Change.** `SourceRegistry.load` rejects a non-object entry
(`isinstance(item, dict)`) and non-string `reporting_period` / `file` / `sha256`
(and non-string `revision_note` / `source_url`) with `ValueError`, before any
indexing. `accept_month`'s load handler catches `(ValueError, TypeError)` and
emits a structured `load: <Type>: <msg>` block — the pandas
"cannot safely cast non-equivalent object to int64" from a `1.5` measure cell no
longer escapes. Numeric semantics unchanged; no imputation/rounding.

**Tests.** `TestA07_*` — `Total All = 1.5` → `accepted=False` with a `load:`
block, no exception; `{"sources": [null]}` → `ValueError` ("must be a JSON
object"); a numeric `reporting_period` → `ValueError` ("must be a string").

---

## Full regression result

`"C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe" -m pytest -q` →
**195 passed, 0 failed, 0 skipped** (~12 s).

| Suite | Count | Note |
|---|---|---|
| `tests/test_profile.py` | 47 | unchanged, pass |
| `tests/test_semantics.py` | 51 | unchanged, pass |
| `tests/test_ingest.py` | 55 | pass (previously valid Phase 3 tests retained) |
| `tests/test_crossmonth.py` | 17 | pass (one assertion string updated) |
| `tests/test_phase3_audit_remediation.py` | **25** | new — A01–A07 closure |

---

## Real April–June reproduction (unchanged results, stronger guarantees)

`run_phase3` over `data/raw/rtt_2026_{04,05,06}.csv`:

| | |
|---|---|
| April / May / June rows | 180,781 / 178,171 / 182,411 — loaded == streamed |
| Raw SHA-256 | all three unchanged and equal to the registry / expected values |
| 105-band schema | passes for all three; header identical (121 columns) |
| Candidate key | `usable` per month **and** on the combined frame |
| Combined | **541,363 rows**, 125 columns, exact row conservation |
| `intended_months` / `missing_intended` / `unexpected_months` | `[2026-04, 2026-05, 2026-06]` / `[]` / `[]` |
| Roundtrip | `{"ok": true, "problems": []}` |
| Publication | `verify_publication` → `{"valid": true, ...}`; stable `generation_id` across re-runs |
| Missingness | preserved (e.g. `Total` blank 391,233 / 541,363; all-band-blank 109,474; `Total All` blank 0) |
| `C_999` / `NONC` | retained (row counts per the audit) |
| P2-U7 | April 0 · May 1 (`NT230`/`05V`/`C_100`) · June 2 (`RTG`/`84H`) — preserved & flagged; **not reopened** |
| Determinism | identical data / order / provenance across re-runs and payload-order shuffle |

---

## Notebook 03 execution

`nbconvert --to notebook --execute --inplace notebooks/03_multi_month_ingestion.ipynb`
→ **0 error outputs**, all code cells executed. Cell changes are display-only
(intended/required/missing months, `generation_id`, `verify_publication`,
remediation-guarantee notes); reusable logic stays in `src/`.

---

## Publication-integrity design (A04) — how a consumer verifies a pair

`rtt_combined.generation.json` is written **last**, by a single atomic
`os.replace`, and records `generation_id` plus the SHA-256 of the published
Parquet and sidecar. A consumer treats the pair as usable **iff**
`verify_publication(out_dir)` returns `{"valid": true}` — i.e. those two hashes
match the on-disk files and the sidecar's `run.generation_id` equals the
marker's `generation_id`. If publication is interrupted at any point, at least
one of those equalities fails, so the pair is reported invalid rather than
consumed; `restore_previous_generation` rolls back to the `*.prev` trio kept
from the last success.

---

## Documentation updates

`docs/phase3_ingestion.md` (§3 blocking table, §4/§7/§8 rewrites, §9 status, new
§11), `docs/decisions.md` (D-038), `docs/assumptions.md` (P2-U3 / P2-U5),
`docs/phase3_completion_report.md` (superseded banner), this report.
Manifest is documented as the **intended source set**; completeness
reconciliation, month-specific authorization, accepted-byte binding, publication
generation integrity, reserved provenance names, malformed RTT-like
classification and structured rejection are all described.

---

## Remaining issues

| Item | Class |
|---|---|
| P3-A01 … P3-A07 | **CLOSED** (changes + focused tests above; audit reproductions now behave correctly) |
| `roundtrip_check` ignores dtype differences by design | NON-BLOCKING — the audit verified the stronger dtype claim separately; staged-publication validation and the sidecar `deterministic` block already lock structure. Left unchanged to avoid churn. |
| `Period` → calendar month-end **date**; stock/flow analytical temporal model | DEFERRED TO PHASE 4+ |
| P2-U7 (`Part_2A > Part_2`) | Carried — preserve & flag; not reopened |
| P2-U1 / P2-U2 / P2-U4 / P2-U6; historical download/publication provenance | DEFERRED — out of Phase 3 scope; provenance fields left `null`, not fabricated |
| Phase 4 transformation, dimensional model, SQL/KPIs, BI | DEFERRED TO PHASE 4+ — not started |

No BLOCKING items.

---

## Final self-assessment

All five BLOCKING findings and both NON-BLOCKING findings are closed with
targeted changes and dedicated regression tests; all 98 Phase 1/2 tests and all
97 Phase 3 tests pass; the real April–June data-level results are unchanged
while the guarantees around them are enforced; notebooks execute clean;
repository hygiene and the Phase 3/4 boundary are intact; no Git milestone was
created.

**READY FOR CODEX PHASE 3 CLOSURE AUDIT**

Claude does not declare Phase 3 PASS.
