# Decisions log

Running log of design choices. Newest first. Each entry: context → decision →
consequence.

---

## D-039 — Phase 3 closure remediation (immutable snapshot; verified publication metadata)
**2026-09-08.** The first-remediation closure audit
(`docs/phase3_codex_closure_audit.md`, PASS WITH CHANGES) confirmed P3-A01 / A02
/ A05 / A06 / A07 CLOSED and left P3-A03 / A04 partially closed. Decision: three
narrow fixes only — no redesign, no Phase 4, no new dependency, raw data and
frozen Phase 1/2 contracts untouched. Report:
`docs/phase3_closure_remediation_report.md`.

* **P3-A03 residual (BLOCKING).** Endpoint hashes of a mutable path did not
  prove the intervening reads used one byte stream (Codex changed-and-restored
  counterexample). `accept_month` now reads the source **in one authoritative snapshot-acquisition read** into a
  private snapshot (`tempfile` dir, original basename); `_accept_from_snapshot`
  runs the reserved-column / `Period` / `validate_extract` / `load_rtt_csv` /
  `count_data_rows` steps against that snapshot, and `report.frame` is derived
  from it. `report.sha256` is `hashlib.sha256(data).hexdigest()`. The step-12
  endpoint re-hash block is removed; a post-snapshot change of the *original*
  path is a `warnings` entry, not a block. `discovery_sha256` is compared to the
  snapshot digest (change before the snapshot → reject). Original file never
  written; snapshot deleted in `finally`; never enters provenance.
* **P3-R01 (BLOCKING, under P3-A04).** `verify_publication` returned
  `marker["combined_rows"]` unchecked (tamper to 999999 → `valid=True`). It now
  validates marker structure/types and **reconciles** `combined_rows` across the
  marker, the checksum-verified sidecar `deterministic.combined_rows`, and the
  actual Parquet row metadata (`pyarrow.parquet` `num_rows`); any disagreement →
  `valid=False`. The returned count is the reconciled value.
* **P3-R02 (NON-BLOCKING, under P3-A04).** A failed retry could copy the
  invalid current trio over a valid `.prev`. `write_combined_parquet` now
  rotates `current → *.prev` **only when `verify_publication` on the current
  trio is valid**. `restore_previous_generation` verifies the `.prev` trio in a
  scratch dir before restoring, then re-verifies, and returns `restored=True`
  only on a verified restore — distinguishing *no backup* / *backup invalid* /
  *restore-copy failed* / *restored & valid*.

Docs corrected: `phase3_ingestion.md` §3 (immutable snapshot; drop "re-checked
after every read"), §8 (row-count reconciliation, valid-only `.prev` rotation,
precise interruption state machine — not "every interruption leaves an invalid
trio"), §9 (P2-U3/P2-U5 → *partially addressed, pending closure confirmation*),
§11. Regression: 98 Phase 1/2 unchanged + 110 Phase 3 (55 + 17 + **38** in
`test_phase3_audit_remediation.py`) = **208 pass**. Real April–June result
unchanged (541,363 rows; hashes, diagnostics, stable `generation_id`, P2-U7
instances identical). No commit/tag/milestone.

## D-038 — Phase 3 remediation after independent audit (PASS WITH CHANGES)
**2026-09-08.** Codex independently audited Phase 3 (`docs/phase3_codex_audit.md`)
and returned PASS WITH CHANGES: five BLOCKING (P3-A01…A05) + two NON-BLOCKING
(P3-A06/A07). Decision: smallest robust closure changes only — no redesign, no
Phase 4 work, raw data and frozen Phase 1/2 contracts untouched. Report:
`docs/phase3_remediation_report.md`.

* **P3-A01** `run_phase3` reconciles the registry's `selected` months against
  discovered + accepted sources; a missing intended month → `ok=False`,
  publication withheld (previous generation untouched). `require_months=[...]`
  supports an explicit, recorded subset. New `IntendedSourceError`; new
  `Phase3Result` fields `intended_months` / `required_months` /
  `requested_subset` / `missing_intended` / `unexpected_months`.
* **P3-A02** `accept_month` binds the registry digest lookup to the canonical
  reporting month (and filename); a digest registered under a different month is
  rejected — fail closed. The old filename-mismatch *warning* is now a *block*.
* **P3-A03** the source is hashed once up front, re-hashed after all reads and
  compared to the discovery digest (`discovery_sha256` arg); `accept_month`
  returns the loaded `frame` bound to that digest and `run_phase3` combines from
  `frame` — the mutable path is never reopened for the payload.
* **P3-A04** atomic publication protocol in `write_combined_parquet`: write to a
  private `.staging-*` dir, roundtrip-validate the staged Parquet, copy any
  existing complete trio to `*.prev`, then `os.replace` Parquet → sidecar →
  **generation marker (last)**. New `rtt_combined.generation.json` records
  `generation_id` + the SHA-256 of both files. `verify_publication(out_dir)` is
  the consumer's validity gate; `restore_previous_generation(out_dir)` rolls
  back; `run_phase3` fails unless it self-verifies. New `PublicationError`.
* **P3-A05** `RESERVED_PROVENANCE_COLUMNS` (`source_file`, `source_sha256`,
  `reporting_month`, `source_row_index`): a source header containing any of them
  is rejected in `accept_month`; `combine_months` re-asserts
  (`ReservedColumnError`). The frozen Phase 2 105-band contract is unchanged.
* **P3-A06** `_RTT_LIKE_RE` extended to catch `rtt_*.csv.bak` / `.csv~` /
  `.csv.tmp` as malformed candidates (surfaced, not ingested); strict
  `PRODUCTION_FILENAME_RE` unchanged.
* **P3-A07** `SourceRegistry.load` validates each entry is an object with
  string fields (non-object / non-string → `ValueError`, not `TypeError`); the
  load handler catches `(ValueError, TypeError)` and emits a structured `load:`
  rejection for a fractional/other non-integer measure cell.

Regression: 98 Phase 1/2 tests unchanged; Phase 3 tests 55 + 17 + **25 new**
closure cases (`tests/test_phase3_audit_remediation.py`). Real April–June result
unchanged (541,363 rows; hashes, diagnostics, P2-U7 instances identical).

## D-037 — Cross-month diagnostics are warnings; combine is deterministic and conservation-checked
**2026-09-08 (Phase 3).** Context: April/May/June must be validated against the
June-derived contracts without weakening them. Decision: `nhs_rtt.crossmonth`
produces **warning-only** cross-month diagnostics — code↔name changes,
name↔code collisions, code appeared/disappeared, coverage & missingness
prevalence, and the frozen `part_2a_subset_conformance` per month — none of
which reject a file. `combine_months` orders months ascending, preserves source
row order, and **asserts** `len(combined) == Σ source rows`
(`RowConservationError`) and candidate-key completeness + uniqueness both
directly (`duplicated(subset=key)==0`, no missing key cell) **and** via
`candidate_key_report(...).usable` (`CombinedKeyError`). Consequence: April
(0), May (**1**, `NT230`/`05V`/`C_100`) and June (2, `RTG`/`84H`) `Part_2A >
Part_2` exceptions are surfaced and carried as **P2-U7**, not treated as
contradictions; no frozen Phase 2 decision is reopened.

## D-036 — CSV → Parquet boundary at `data/interim/`; regenerated, not tracked
**2026-09-08 (Phase 3).** Decision: the accepted multi-month set is published as
one combined `data/interim/rtt_combined.parquet` (pyarrow) — wide NHS structure,
nullable dtypes and `<NA>` missingness preserved, deterministic row order — with
a sidecar `rtt_combined.ingest_manifest.json` of **observed** ingestion evidence
(kept separate from the intended-source registry). Both are **git-ignored**
(regenerable from the raw set + `src/`). `roundtrip_check` asserts data-level
(not byte-level) equality; the sidecar's volatile `run` block is excluded from
determinism checks by `deterministic_manifest_view`. No partitioned data-lake
layout at this scale.

## D-035 — Four provenance columns; `source_row_index` is a parsed-record position
**2026-09-08 (Phase 3).** Decision: every combined row gains exactly
`source_file`, `source_sha256`, `reporting_month` (canonical `YYYY-MM`) and
`source_row_index`. `source_row_index` is explicitly the **0-based position of
the row among its source file's parsed CSV data records** (what
`pandas.read_csv` yields), **not** a physical CSV line number — quoted embedded
newlines do not shift it. Row conservation uses **CSV-aware** record counting
(`csv.reader`), never raw newline counting. No wall-clock timestamp enters
row-level identity. The original `Period` column is retained unchanged.

## D-034 — Revised/re-released files: explicit selection or fail closed
**2026-09-08 (Phase 3, P2-U5).** Context: `Period` does not distinguish a
revised release of a month from the original. Decision:
`SourceRegistry.resolve_month` treats *same month + same SHA-256* as one
artifact (no double-ingest) and *same month + different SHA-256* as distinct
release candidates that are accepted **only if exactly one** observed digest is
a `selected: true` registry entry for that month — otherwise
`AmbiguousRevisionError` (**fail closed**). Never resolved by file order, mtime,
filename sort, size or discovery order. NHS revision metadata is **not
invented**. `SourceRegistry.load` enforces ≤1 `selected` per month and exactly
one when a month lists multiple distinct-hash releases.

## D-033 — `data/raw/manifest.json`: tracked registry of the intended source set
**2026-09-08 (Phase 3, P2-U3).** Decision: a JSON registry at
`data/raw/manifest.json` — one entry per byte-stream: `reporting_period`,
`file`, `sha256`, `selected`, optional `revision_note` / `source_url`. It is the
**authoritative intended source set** and is tracked via a precise `.gitignore`
negation (`!data/raw/manifest.json`); `data/raw/*` (the raw CSVs) stays ignored.
**Generated validation results are not stored here** — observed evidence lives
in `data/interim/rtt_combined.ingest_manifest.json`. Provenance still missing
(source URL, download timestamp, NHS publication date) is left `null`, not
fabricated (D-004/D-011 stand).

## D-032 — Per-month acceptance gate reuses the frozen Phase 1/2 contracts
**2026-09-08 (Phase 3).** Decision: `nhs_rtt.ingest.accept_month` is the single
monthly gate. It **reuses** `semantics.validate_extract` (exact 105-band
schema), `semantics.load_rtt_csv` (blank-preserving, negatives rejected) and
`semantics.candidate_key_report` — it does not re-define them — and adds:
filename-contract check, SHA-256 provenance (byte-stream must be in the
registry, or an explicit `expected_sha256`), a single-and-parseable `Period`
that agrees with the filename, an independent CSV-aware row-conservation
cross-check, and an explicit whitespace-only key-cell check. A rejected file is
only *logically* rejected — never moved, renamed or "repaired". Consequence: all
98 Phase 1/2 tests still pass; 72 new Phase 3 tests added.

## D-031 — Phase 3 split into `ingest.py` + `crossmonth.py`
**2026-09-08 (Phase 3).** Decision: reusable Phase 3 logic is two modules —
`src/nhs_rtt/ingest.py` (deterministic discovery, SHA-256, registry/provenance,
`Period` validation, per-month acceptance) and `src/nhs_rtt/crossmonth.py`
(cross-month diagnostics, deterministic combine, Parquet publication). Import
direction is one-way (`crossmonth` → `ingest`); `ingest.main()` reaches
`crossmonth` only lazily, so there is no cycle. `python -m nhs_rtt.ingest`
delegates to `crossmonth.run_phase3`. `notebooks/03_multi_month_ingestion.ipynb`
is a thin orchestration/narrative layer; `docs/phase3_ingestion.md` is the
dedicated architecture doc. No new dependencies.

## D-030 — Phase 2 closure remediation (narrow patch for the residual blockers)
**2026-09-07.** The remediation was re-audited (`docs/phase2_closure_audit.md`,
PASS WITH CHANGES): 5 findings CLOSED (P2-A02/A03/A05/A07/A10), 5 PARTIALLY
CLOSED (P2-A01/A04/A06/A08/A09) plus a new HIGH **P2-R01**. Decision: a minimal
auditable patch for the residuals only (D-028, D-029 below; data-dictionary
`blank ≡ 0` line and `C_999` "exact sum of 23 rows" line replaced;
`assumptions.md` "next validation step" updated to the same-month June
benchmark). No Phase 3, no new technologies, raw data unchanged. Reproduced
June figures are unchanged. Report: `docs/phase2_closure_remediation_report.md`.

## D-029 — Extract gate enforces the exact canonical 105-band schema
**2026-09-07 (P2-A09 residual).** `validate_extract` previously only checked
band-sequence *contiguity*, which still accepted zero bands, a single band, a
missing first (`0-1`) or open-ended (`>104`) band, and other truncated-but-
contiguous sets. Decision: add `check_expected_band_schema` / the canonical
`expected_week_band_names()` (exactly 105, correctly ordered, first `Gt 00 To
01`, open end `Gt 104 Weeks`, no missing interior, no duplicate, no unexpected
band-like column) and enforce it at `validate_extract` /
`load_rtt_csv(require_full_band_schema=True, default)`. Miniature synthetic unit
tests that exercise other logic pass `require_full_band_schema=False`; new
endpoint / empty / truncated / duplicate / extra regressions plus a positive
105-band test cover the gate. Generic Phase 1 band discovery is untouched.

## D-028 — missing-as-zero reconciliation must not certify undefined comparisons
**2026-09-07 (P2-R01, HIGH).** The `missing-as-zero` path set the evaluation
mask to the whole subset and only counted `unknown-clock` blanks as missing, so
a row with a missing **`Total All`** (or missing `Total`, or an entirely
unobserved band distribution) was counted as `n_evaluated`, credited as a
match via `n_match = n_evaluated − n_mismatch`, and could reach an unqualified
`HOLDS`. Decision: `_reconcile` now (a) applies **only** the explicitly
authorised zero-fill (blank unknown-clock per D-016; skip-missing band cells),
(b) evaluates a row **only when both operands are non-`<NA>` afterwards** —
otherwise it is excluded and counted in `n_missing_operand` / verdict
`PARTIAL`, for *both* policies, (c) derives `n_match` from an explicit equality
mask, and (d) handles zero evaluated rows / all-missing operands without a
numeric-conversion error. New field `n_convention_rows` records where the
authorised fill was used. Missing `Total All` / `Total` are **never**
zero-filled to a match. June figures unchanged (`n_missing_operand = 0` on
every expected check). `aggregate_vs_detail` gains an `acceptable` policy-aware
flag (no orphans, one aggregate row per group, zero numeric mismatch,
`cmp_other_missing == 0`); `reconciles_numeric` is retained but labelled a
diagnostic.

## D-027 — Phase 2 remediation after independent audit (PASS WITH CHANGES)
**2026-09-07.** Codex independently audited Phase 2
(`docs/phase2_independent_audit.md`) and returned PASS WITH CHANGES with
findings **P2-A01…P2-A10**. Decision: remediate the substantive findings
(D-022…D-026 below plus wording/coverage fixes), preserving the reproduced June
numbers (arithmetic, candidate key, C_999 numeric reconciliation, 18-week
figure — all independently re-confirmed byte-for-byte). No Phase 3 work. Full
mapping in `docs/phase2_remediation_report.md`.

## D-026 — Reconciliation & aggregate checks must report coverage, not just a verdict
**2026-09-07 (P2-A04 / P2-A08).** `reconciliation_summary` now reports, per
check: `n_in_subset` / `n_evaluated` / `n_missing_operand` / `n_excluded_missing`
/ `n_mismatch`, and `policy` (`strict` vs `missing-as-zero`). An unqualified
`HOLDS` requires the subset to be **fully evaluated** with zero mismatches;
otherwise `PARTIAL (...)` / `FAILS` / `n/a`. `aggregate_vs_detail` compares the
**union** of aggregate/detail groups, reports orphan groups, groups with >1
aggregate row, detail-rows-per-group spread, and classifies every
group×column comparison (numeric/numeric, both-missing, agg-zero-vs-all-missing,
other) — `reconciles_numeric` is `True` only with no orphans, no duplicate
aggregates and zero numeric mismatches. Consequence: June still passes, now
with explicit coverage; malformed inputs cannot get a silent pass.

## D-025 — `candidate_key_report` and `validate_extract` are acceptance gates
**2026-09-07 (P2-A09, K-2).** `candidate_key_report` returns `is_unique = None`
(never silently `True`) when a requested key column is absent, and `usable`
requires **all columns present + no missing key cell + uniqueness**.
`load_rtt_csv` now runs `validate_extract` first (raw-header duplicate-name
check *before* pandas mangling; required key/measure columns; clean ordered
band sequence) and reads with `keep_default_na=False, na_values=[""]` so a
literal `NULL` in a code column stays the string, not `<NA>`. These are Phase 2
acceptance checks for the agreed extract format — **not** a Phase 3 ingester.

## D-024 — NONC: structural prevalence separated from pathway counts
**2026-09-07 (P2-A03).** The earlier `nonc_summary` summed `Total All` over all
NONC rows (**102,482**) — this double-counts `C_999` with its constituents and
mixes RTT parts. Decision: `nonc_prevalence` reports rows/providers/coverage
only (no pathway total); `nonc_pathways_by_part` reports counts **per RTT part
using one treatment-function representation** (`C_999`: 1,224 / 4,478 / 31,156
/ 7,734 / 6,649) which **must not be summed across parts**; the 102,482 figure
survives only as `nonc_raw_cell_checksum` explicitly labelled uninterpreted.
NONC rows are retained (D-020 stands); the coverage caveat "NONC submission is
optional, so NONC rows are not exhaustive of non-English activity" (S5) is
added.

## D-023 — Same-month June benchmark; May comparison withdrawn
**2026-09-07 (P2-A06).** The Phase-2 report compared June raw 65.83% to the
**May 2026** published 65.6% and attributed the gap to non-submitter estimates
— different months cannot support that. Decision: benchmark against the
**June 2026 SPN Table 1 unestimated** figures (S6, published 13 Aug 2026),
which the raw file reproduces exactly (7,147,562 incomplete; 318,650 admitted;
1,307,837 non-admitted; 1,930,912 new periods; 65.8% within 18 weeks —
`same_month_totals_check`). Cite S5 (user guidance) for the exact CSV filters.
Exact **estimate-inclusive** reproduction stays UNRESOLVED (P2-U1).

## D-022 — `Part_2A > Part_2` count exception: preserve & flag, never cap
**2026-09-07 (P2-A05).** NHS S1 Annex B documents `Part_2A` ⊆ `Part_2`. June
has **two count exceptions** — `RTG` / `84H` / `C_502` and the corresponding
`C_999`, each `Part_2A = 2` vs `Part_2 = 1`. Decision: `part_2a_subset_conformance`
adds a necessary count check; violations are **preserved and flagged**
(`outputs/phase2/part2a_subset_violations.csv`), the raw data is not altered
and `Part_2A` is not capped. Any downstream measure that assumes
`Part_2A <= Part_2` must validate the invariant per group first. Carried
forward as `rtt_semantics.md` P2-U7.

## D-021 — Phase 2 outputs are gitignored; summaries live in docs/
**2026-09-07.** `outputs/phase2/*` (compact reconciliation / blank-zero /
NONC / controlled-example CSVs + `facts.json`) are regenerable from
`nhs_rtt.semantics` + `notebooks/02_semantics_grain_validation.ipynb`, so they
are gitignored like `outputs/profiles/*`. The durable Phase 2 record is
`docs/rtt_semantics.md` and `docs/rtt_grain_and_aggregation.md`, which embed
the key result tables.

## D-020 — NONC rows retained; excluded only for England-performance measures
**2026-09-07 (superseded in part by D-024).** `Commissioner Org Code = NONC` =
non-English commissioner (S1 §10.1.8 / §10.1.9.2); 2,993 June rows. Decision:
keep these rows in the analytical dataset; exclude `NONC` when reproducing NHS
England published performance (S5). Not deleted from anything. The pathway-count
wording is corrected by **D-024** (per-part, one TFC representation; 102,482 was
a double-counted checksum). Evidence: `docs/rtt_semantics.md` §8.

## D-019 — `C_999` treated as a pre-aggregated total, never summed with specialties
**2026-09-07 (evidence wording revised — see D-026).** `Treatment Function Code
= C_999` ("Total") equals the sum of the group's *available* non-C_999 rows on
every numeric column with **0 numeric mismatches** under a stated
zero-contribution convention for missing cells, over all 40,636
`(provider, commissioner, part)` groups (each with exactly one C_999 row and
≥1 detail row; detail rows per group range 1–23). Decision unchanged: for
specialty-level aggregation filter `Treatment Function Code != "C_999"`; for a
cross-specialty total use `C_999` directly — never both. Resolves Phase 1 A-07
(rule). Evidence: `docs/rtt_semantics.md` §6.

## D-018 — Candidate key is the natural composite; no surrogate key
**2026-09-07.** Best-supported key:
`Period · Provider Org Code · Commissioner Org Code · RTT Part Type ·
Treatment Function Code` — unique for all 182,411 June rows and matching the
documented collection grain (S1 §10.1.1.2). Decision: use these natural columns
as the key; do **not** manufacture a surrogate/hash key (it would mask a future
collision). Uniqueness is asserted per file, not assumed. Resolves Phase 1
A-09. Evidence: `docs/rtt_grain_and_aggregation.md` §1–2.

## D-017 — Arithmetic model adopted (conditional by RTT Part Type; revised D-026)
**2026-09-07.** Established for every applicable June row, with explicit
coverage: Parts 1A/1B — `observed_bandsum = Total` (strict, all rows);
`Total + unknown = Total All` (strict, on the **unknown-populated** rows —
12,771 / 21,346); `Total = Total All` (strict, on the **unknown-blank** rows —
6,032 / 11,005); and `Total + unknown(missing→0) = Total All` over all rows
under the stated missing-as-zero convention. Parts 2/2A — `observed_bandsum =
Total All` (strict, all rows); `Total`/unknown not collected. Part_3 — only
`Total All` (a count; `observed_bandsum` is `<NA>`, not 0). Resolves Phase 1
A-02/A-03. Evidence: `docs/rtt_semantics.md` §4;
`outputs/phase2/reconciliation_by_part.csv`,
`reconciliation_coverage_by_part.csv`.

## D-016 — Scoped June zero-contribution convention (narrowed after audit P2-A01)
**2026-09-07, revised.** **Original wording overstated the evidence** by calling
a blank band "arithmetically identical to 0 — no patients in this band" and
citing skip-NA-vs-fill-0 agreement as independent proof. `observed_band_sum`
uses `skipna` in all cases and `min_count=1` only affects the all-missing case;
since every June banded row has ≥1 observed band, the two are trivially equal.
**Narrowed decision:** for the **June 2026 banded parts**, a missing band (or
missing unknown-clock) contribution may be treated **numerically as 0**, on a
per-calculation basis, for the reconciliations in `rtt_semantics.md`. This is
an explicit, non-destructive computational convention — **not** semantic
equivalence, **not** global imputation, **not** automatically valid for future
files. Raw missingness is preserved (`load_rtt_csv` keeps `<NA>`); the earlier
"blank ≡ 0" and "quality trigger diagnoses non-reporting" claims are removed.
Phase 1 A-01 is **narrowed**, not resolved. Evidence: `docs/rtt_semantics.md`
§5; `outputs/phase2/blank_zero_by_part.csv`.

## D-015 — Phase 2 approach: reusable `semantics` module + blank-preserving load
**2026-09-07.** Phase 2 analysis logic lives in `src/nhs_rtt/semantics.py`
(week-band identification reuses `nhs_rtt.profile`; reconciliation,
candidate-key, blank/zero, aggregate-vs-detail, NONC, 18-week reproduction);
`notebooks/02_semantics_grain_validation.ipynb` orchestrates and narrates.
`load_rtt_csv` reads numeric columns as nullable `Int64` so blank (`<NA>`) and
explicit `0` are always distinguishable, and rejects negative values (S1 Annex
B). No new dependencies (pandas already declared). Raw immutability is asserted
by SHA-256 before and after every run.

## D-014 — Independent audit: PASS WITH CHANGES → Phase 1 closure pass
**2026-09-07.** Context: Codex independently audited Phase 1
(`docs/phase1_audit.md`), verified the June structural results as reliable and
byte-for-byte reproducible, and returned **PASS WITH CHANGES**. Decision:
address only the engineering / documentation findings that improve
future-input safety, reproducibility, or docs (D-008…D-013 below); classify
the rest `document only` or `defer to Phase 2` in the audit response. No
Phase 2 work. Consequence: the 9 validated June CSV artifacts are unchanged
(re-verified byte-identical); `rtt_2026_06__overview.md` changed only in
wording + the new "Structural warnings: none" line + Markdown pipe-escaping;
one additive artifact (`rtt_2026_06__MANIFEST.txt`).

## D-013 — Week-bucket sequence is validated separately from detection
**2026-09-07 (audit §6).** Context: `classify_columns` is a permissive header
*finder*; it does not check that the buckets form a real sequence. Decision:
keep the finder permissive and add `check_week_bucket_sequence()`, a
structural validator (contiguity, ascending order, unit width, uniqueness, a
single aligned open-ended band). Findings surface in
`TableProfile.week_bucket_sequence_warnings` and the overview's "Structural
warnings" section. It asserts nothing about interval inclusivity. Consequence:
June passes with zero warnings (104 unit ranged buckets + `Gt 104 Weeks`).

## D-012 — Malformed structure is reported, never silently accepted
**2026-09-07 (audit M1/M2/M3).** Decisions:
- **Exact duplicates (M1):** replaced `hash(tuple(row))` with an injective
  per-row serialisation (`repr(row)`) so different rows can never collide and
  the count is truly exact. Memory cost (~one string per distinct row) is
  acceptable at ~80 MB monthly scale; a disk-backed strategy for much larger
  inputs is deferred (see `docs/assumptions.md` scalability note). June: still
  0 duplicates.
- **Duplicate headers (M2):** detected; the ambiguous role is left *unbound*
  (recorded in `TableProfile.unbound_roles`) and a `warnings.warn` + structural
  warning is raised instead of silently binding to the last column.
- **Broken quoting (M3):** `csv.reader(strict=True)`; a `csv.Error` is caught,
  recorded as a structural warning, `parse_truncated` is set, and the partial
  profile is still returned.
- The CLI now exits `2` when any structural warning was raised, `0` otherwise.
Consequence: June is structurally clean (exit 0, "Structural warnings: none").

## D-011 — Reproducibility claims aligned with captured evidence
**2026-09-07 (audit M5).** Decision: added `docs/data_provenance.md` recording
the June file's size + SHA-256 (`edc3927…f02`) and marking source URL,
download time, NHS publication date and revision status as **NOT SUPPLIED**.
Corrected the README's over-broad "every run records URLs, checksums and
package versions" claim. Removed `great-expectations` from `requirements.txt`
(unused in Phase 1, absent from `pyproject.toml`, heavy). A hash-pinned
lockfile is deferred to a later phase.

## D-010 — Overview Markdown is escaped; blank name counts are labelled
**2026-09-07 (audit minor).** Decision: `_md_table` now escapes `|`, `\` and
newlines so anomaly rows like `NT447 | NVC04` render in one cell. Categorical
"distinct name(s)" is reported non-blank with `(+N blank/whitespace)` shown
separately, matching the per-column convention (which excludes blanks).
Empty output CSVs are written header-only, never zero-byte. `save_profile`
writes `<stem>__MANIFEST.txt` inventorying the run (it does not delete stale
artifacts from a previous run with the same stem).

## D-009 — Unsupported domain assertions downgraded to observed labels
**2026-09-07 (audit M4).** Decision: `docs/data_dictionary.md`,
`docs/assumptions.md` (A-06/A-07/A-08/A-14/A-16) and the notebook no longer
call `C_999` a "subtotal", prescribe aggregation treatment, or expand "DTA".
They now state only what was observed (literal names, row counts, cardinality)
and mark the interpretation as unresolved. Nothing here required NHS-domain
knowledge to fix — it was removing claims the repository could not support.

## D-008 — `DEV_MONTH` confirmed inert; kept as documentation only
**2026-09-07 (audit §9).** The audit confirmed `DEV_MONTH` is unused by
`profile_csv`, the CLI and the notebook, so it creates no functional coupling
to June. Decision: keep it in `src/nhs_rtt/__init__.py` as an informational
constant with a comment stating it is not read by code; do not thread it
through the profiler. The CLI already takes an arbitrary path + output stem.

## D-007 — Environment & install
**2026-09-07.** Decision: use the pre-approved interpreter
`C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe` (Python 3.14, pandas 3.0.5,
numpy 2.5.3, pyarrow 25.0.1). Added `pytest` (9.1.1) to it and ran
`pip install -e . --no-deps` so `import nhs_rtt` and `python -m nhs_rtt.profile`
work without `PYTHONPATH` juggling. `requirements.txt` / `pyproject.toml`
declare `pytest>=8` as a **minimum bound** (not a pin/lock). No new virtual
environment was created.

## D-006 — Cross-month profiling deferred
**2026-09-07.** Context: April & May 2026 files are present. Decision: Phase 1
profiles **June 2026 only**, per corrected instruction; the other files are
left untouched. Consequence: schema-consistency checks across months are a
later-phase task; `nhs_rtt.profile` already supports it via the CLI.

## D-005 — Tests use synthetic fixtures only
**2026-09-07.** Context: real files are ~78 MB and immutable. Decision: all
tests build tiny in-memory CSVs (`tests/conftest.py`) that imitate the RTT
shape; no test reads `data/raw/`. Consequence: fast, hermetic tests; the real
file is exercised only by running the profiler CLI / notebook.

## D-004 — Raw-file provenance not yet captured
**2026-09-07.** Context: `data/raw/README.md` asks for source URL, timestamp,
SHA-256 and publication date per file; these were not supplied with the files.
Decision: record the gap as an open item rather than invent values.
Consequence: tracked in `docs/assumptions.md`; size + SHA-256 now captured in
`docs/data_provenance.md` (D-011); URL / timestamp / publication date /
revision status remain outstanding.

## D-003 — Profiler flags columns by header text only
**2026-09-07.** Context: brief requires identifying `Total` / `Unknown` /
week-bucket columns without interpreting them. Decision: `classify_columns()`
groups columns purely by substring / regex on the header
(`total_columns`, `unknown_columns`, `week_bucket_columns`) and the output
states plainly that no meaning is assigned. Consequence: reviewers get a
starting map; semantic classification stays a later, documented step.

## D-002 — Code/name mapping consistency is reported, not resolved
**2026-09-07.** Context: brief warns against assuming provider name ↔ code is
1:1. Decision: `CategoricalSummary.mapping_anomaly_rows()` reports every
code-with-many-names and name-with-many-codes to
`*__mapping_anomalies.csv`; it does not pick a "correct" value or dedupe.
Consequence: `DUCHY HOSPITAL` (2 codes) and blank commissioner names (8 codes)
are surfaced for human decision.

## D-001 — Development dataset: June 2026
**2026-09-07.** Context: the brief named "April 2025" as the development month,
but the supplied raw files are April, May and June 2026; the instruction was
then corrected to "only … June 2026". Decision: Phase 1 uses
`data/raw/rtt_2026_06.csv` as the sole development dataset; `DEV_MONTH` in
`src/nhs_rtt/__init__.py` is `"2026-06"`. Consequence: all Phase 1 outputs and
docs refer to June 2026; the discrepancy with the original brief is recorded
here and in `docs/assumptions.md`.

## D-000 — Profiler is standard-library only
**Pre-existing (prior session), retained.** Context: profiling must run even
where compiled wheels are unavailable. Decision: `nhs_rtt.profile` uses only
`csv` / `collections` and makes a single streaming pass; memory usage is a
transparent **estimate**, not a pandas measurement. Consequence: a profile can
always be produced; a precise in-memory figure needs a later pandas-based
utility if required.

Snapshot read-count clarification: one authoritative snapshot-acquisition read plus an informational reread used only for warning/reporting; the original source is not literally read only once in total.
