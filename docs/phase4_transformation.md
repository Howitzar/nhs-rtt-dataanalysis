# Phase 4 — Transformation, Data Quality & Analytical Dataset

Scope: turns the **verified Phase 3 publication** (`data/interim/rtt_combined.parquet`
+ generation marker + sidecar) into deterministic, analysis-ready datasets.
Companion to `docs/rtt_semantics.md` / `docs/rtt_grain_and_aggregation.md`
(Phase 2, frozen) and `docs/phase3_ingestion.md` (Phase 3, frozen). Code:
`src/nhs_rtt/transform.py`. Notebook: `notebooks/04_transformation_analytical_dataset.ipynb`
(thin orchestration only). Tests: `tests/test_transform.py`.

Phase 4 is a **semantic transformation and analytical-readiness** phase, not
conventional data cleaning. It never re-reads `data/raw/*.csv` and never mutates
the Phase 3 publication. It does **not** perform substantive NHS waiting-time
analysis, KPI logic, dimensional modelling or a SQL layer — those are Phases
5–9.

---

## 1. Architecture

```
data/interim/rtt_combined.parquet (+ .generation.json + .ingest_manifest.json)   [Phase 3, read-only]
        │   verify_publication()  ── explicit input gate (marker + hashes + row reconciliation)
        ▼
load_verified_publication(interim_dir)        nhs_rtt.transform
   541,363 rows × 125 cols, 4 provenance cols, candidate key re-checked
        │
        ├──▶ build_analytical_wide(vin)         Dataset A — row-preserving analytical wide
        │        541,363 → 541,363 rows × 138 cols  (125 source + 13 derived)
        │
        ├──▶ wait_band_metadata()               105-row reference table (derived from the frozen band contract)
        │
        ├──▶ write_waiting_band_long(wide, …)   Dataset B — dense waiting-band long (streamed to Parquet)
        │        541,363 × 105 = 56,843,115 rows × 14 cols
        │
        ├──▶ build_transformation_report(…)     machine-readable JSON + human-readable Markdown
        │
        ▼  stage every output → validate_persisted_long (mandatory) → manifest → atomic commit
data/processed/   rtt_analytical_wide.parquet
                  rtt_waiting_band_long.parquet
                  wait_band_metadata.parquet
                  phase4_transformation_report.json
                  phase4_transformation_report.md
                  phase4_generation.json          ← commit marker, written LAST (§10)
                  *.prev                          ← last known-valid generation (rollback)
```

`data/processed/*` is **git-ignored and regenerable** (`python -m nhs_rtt.transform`,
or `nhs_rtt.transform.run_phase4()`; `python -m nhs_rtt.transform --verify` checks
the published set). Nothing in `data/interim/` is written.

No new dependencies: `pandas` + `numpy` + `pyarrow` are already declared. No
DuckDB / SQL, no dimensional model, no surrogate-key architecture, no calendar
dimension, no KPI logic, no BI, no ML, no Spark.

---

## 2. Input boundary — `load_verified_publication` (immutable verified snapshot)

Phase 4 consumes a **private immutable snapshot** whose exact bytes are the
bytes that were verified (P4-A01):

1. the publication trio — `rtt_combined.parquet` + `rtt_combined.ingest_manifest.json`
   + `rtt_combined.generation.json` — is copied once into a private temp
   directory;
2. `crossmonth.verify_publication` runs against **that snapshot** (marker
   well-formed and typed; `parquet_sha256` / `sidecar_sha256` match the snapshot
   files; sidecar `run.generation_id` equals the marker; `combined_rows`
   reconciles across marker / sidecar / Parquet metadata). On failure Phase 4
   raises `PublicationNotVerifiedError` and stops;
3. the recorded consumed-input digest is the SHA-256 of the **snapshot** Parquet
   — identical to the marker's `parquet_sha256` that step 2 just checked;
4. the DataFrame is parsed **only from the snapshot**.

So the returned frame, its recorded digest and the generation identity always
refer to the same verified bytes even if the live `interim_dir` is replaced, or
changed-and-restored, during the read. A second endpoint hash of the mutable
path is *not* used and would not be sufficient.

After the gate, three frozen-contract re-checks (cheap): snapshot Parquet row
count equals the verified `combined_rows`; the four provenance columns are
present; `semantics.candidate_key_report(df, CANDIDATE_KEY)["usable"]` is `True`.

The consumed Phase 3 identity (`phase3_generation_id`,
`phase3_consumed_parquet_sha256`) is recorded in the JSON report **and** in the
Phase 4 generation manifest (`phase4_generation.json`), which additionally binds
the SHA-256 / schema / row count of every Phase 4 output (§10). It is **not**
embedded in the individual Parquet files.

---

## 3. Grains

| Grain | Definition | Rows (current publication) | Key |
|---|---|---|---|
| **Phase 3 / source grain** | one provider × commissioner × treatment function × RTT Part Type, within one reporting `Period` | 541,363 | `[Period, Provider Org Code, Commissioner Org Code, RTT Part Type, Treatment Function Code]` (frozen candidate natural key — **not** a patient/pathway id, **not** an NHS-guaranteed PK) |
| **analytical-wide grain** | *equivalent* to the source grain (`Period` ↔ `reporting_month` is 1:1); one accepted Phase 3 source row → exactly one analytical-wide row | 541,363 | same candidate key; asserted unique + usable |
| **waiting-band-long grain** | analytical-wide grain × `wait_band` | 56,843,115 (= 541,363 × 105) | `[reporting_month, Provider Org Code, Commissioner Org Code, RTT Part Type, Treatment Function Code, wait_band_order]`, equivalently `[source_file, source_row_index, wait_band_order]` |

The source grain is **not uniform in meaning across RTT Parts** (S1 §10.1.1.2):
1A/1B are completed-in-month *flows*, 2/2A are month-end *stock/snapshots*, 3 is
new-clock-starts *flow*. Phase 4 exposes this (`rtt_part_event_basis`,
`rtt_part_is_month_end_snapshot`) but introduces **no** universal `safe_to_sum`
semantics.

---

## 4. Dataset A — analytical-wide (`rtt_analytical_wide.parquet`)

**Row-preserving.** `len(out) == len(in)` (541,363). No row is filtered,
deduplicated or reshaped. Deterministic order: `reporting_month` ascending, then
`source_row_index` ascending (identical to the Phase 3 combined order).

**Source columns unchanged.** All 125 Phase 3 columns (121 source + 4
provenance) are carried through verbatim, including the raw `Period` column and
the band cells. Missingness is preserved — **no `fillna(0)`** anywhere
(§6).

**13 derived columns appended** — pure, deterministic functions of the source
columns:

### 4.1 Derived reporting-time metadata (from `reporting_month`)

| Field | Source | Derivation | Type | Nullable | Rationale / warnings |
|---|---|---|---|---|---|
| `reporting_year` | `reporting_month` | `int(YYYY)` | `Int16` | no | chronological axis |
| `reporting_month_num` | `reporting_month` | `int(MM)` | `Int8` | no | 1–12 |
| `reporting_month_name` | `reporting_month` | English month name | `string` | no | display |
| `reporting_period_start_date` | `reporting_month` | first calendar day of the month (`YYYY-MM-01`), cast to an **explicit enforced resolution** | `datetime64[us]` — serialized as Arrow `timestamp[us]` (P4-A05); `build_analytical_wide` asserts the dtype | no | **A sortable monthly anchor, not an event timestamp.** The raw `Period` column is retained unchanged. The month-**end** snapshot date and the flow-vs-stock analytical temporal model remain deferred to Phase 5 (P2-U5). |

*Not built:* a full calendar dimension (Phase 5); a month-end date; any
threshold/KPI time flag.

### 4.2 Derived neutral classifications (legitimate semantic categories, not DQ conditions)

| Field | Source | Derivation | Type | Rationale / warnings |
|---|---|---|---|---|
| `is_treatment_function_total` | `Treatment Function Code` | `== "C_999"` | `boolean` | Makes the C_999 roll-up explicit. **Aggregation rule: use C_999 *or* non-C_999 detail, never both.** Neither level is removed. |
| `is_nonc_commissioner` | `Commissioner Org Code` | `== "NONC"` | `boolean` | NONC = non-English commissioner (S1 §10.1.8). **Retained; not a DQ failure.** Exclude only where the published England-performance methodology requires it (S5); NONC submission is not mandatory. |
| `rtt_part_event_basis` | `RTT Part Type` | fixed 1:1 map (S1 §10.1.1.2) | `string` | `completed_admitted_in_month` / `completed_non_admitted_in_month` / `incomplete_at_month_end` / `incomplete_with_dta_at_month_end` / `new_clock_starts_in_month`. Different populations on different event bases — **not freely additive**. |
| `rtt_part_carries_bands` | `RTT Part Type` | `in (Part_1A, Part_1B, Part_2, Part_2A)` | `boolean` | Part_3 has no waiting-band distribution. |
| `rtt_part_is_month_end_snapshot` | `RTT Part Type` | `in (Part_2, Part_2A)` | `boolean` | Stock/snapshot parts — **do not sum across reporting months**. `Part_2A ⊆ Part_2`; never `Part_2 + Part_2A`. |

### 4.3 Derived row-level data-quality / condition flags (a small, meaningful set)

Every `dq_` column is a **factual condition flag** — it records that a row meets
a condition, *regardless of whether the condition is structurally expected for
that RTT Part*. The four-category data-quality policy in §9 says which are
**structurally expected** and which are **anomalous**; a factual condition flag
existing for a structurally-expected condition is not a contradiction.

| Field | Source | Derivation | Type | Category (see §9) |
|---|---|---|---|---|
| `dq_all_bands_missing` | 105 band cells | every band cell is `<NA>` | `boolean` | factual condition flag — **structurally expected** for Part_3 (bands not collected); a genuine anomaly only for a banded part. Current publication: 109,474 rows (all Part_3). |
| `dq_total_missing` | `Total` | `Total` is `<NA>` | `boolean` | factual condition flag — **structurally expected** for Parts 2/2A/3 (`Total` not collected there). Current publication: 391,233 rows. |
| `dq_part2a_gt_part2` | `RTT Part Type`, `Total All` | a matching `Part_2` row with a **numeric** `Total All` exists at the same `[reporting_month, Provider, Commissioner, Treatment Function Code]` and this `Part_2A` row's `Total All` is strictly greater | `boolean` | **anomalous source condition (P2-U7).** Values are **preserved**, never capped. `False` for every non-`Part_2A` row. Current: April 0 · May 1 · June 2. |
| `dq_part2a_no_matching_part2` | `RTT Part Type`, key, `Part_2 Total All` | **no matching `Part_2` row with a usable (non-null) `Total All` comparator** — covers *both* "no `Part_2` row at the key" *and* "a `Part_2` row exists but its `Total All` is `<NA>`" | `boolean` | **anomalous source condition** — a `Part_2A` group whose subset invariant cannot be numerically checked. `False` for every non-`Part_2A` row. Current: April 5 · May 3 · June 0. |

The two `dq_part2a_*` flags reproduce **exactly** the frozen
`semantics.part_2a_subset_conformance` per-month `n_violations` /
`n_without_matching_part_2` (its `has_matching_part_2` is "`Part_2 Total All`
not null"). The frozen helper is **not** changed to make the flag name more
literal; the definition above makes the semantics unambiguous. C_999, NONC and
Part_2A **classifications** (§4.2) are legitimate semantic categories, kept
separate from these condition flags.

---

## 5. Dataset B — waiting-band long (`rtt_waiting_band_long.parquet`)

A **dense** long representation of the 105 waiting-band values. Every
analytical-wide row produces exactly 105 ordered band rows, *including* rows
whose source band value is `<NA>` — so the invariant

```
len(long) == len(analytical_wide) × 105          (56,843,115 for the current publication)
```

holds and the explicit-zero / source-`<NA>` distinction is preserved. Order:
parent order (`reporting_month`, `source_row_index`), then `wait_band_order`
1 → 105.

| Column | Source | Type | Nullable | Notes |
|---|---|---|---|---|
| `reporting_month` | provenance | `string` | no | canonical `YYYY-MM` |
| `Period` | source | `string` | no | raw, unchanged |
| `Provider Org Code` | source | `string` | no | codes identify; names not carried into long form |
| `Commissioner Org Code` | source | `string` | no | |
| `RTT Part Type` | source | `string` | no | |
| `Treatment Function Code` | source | `string` | no | |
| `source_file` | provenance | `string` | no | Phase 3 **source provenance** |
| `source_sha256` | provenance | `string` | no | Phase 3 source provenance (not discarded) |
| `source_row_index` | provenance | `Int64` | no | 0-based parsed source record — **parent lineage** |
| `wait_band_order` | derived | `Int16` | no | 1–105, deterministic band order |
| `wait_band_label` | derived | `string` | no | the canonical source band-column name |
| `wait_band_lower_weeks` | derived | `Int16` | no | lower **week** boundary (0…104) |
| `wait_band_upper_weeks` | derived | `Int16` | **yes** | upper week boundary; **`<NA>` for the open-ended `>104` band** (no invented finite maximum) |
| `pathway_count` | source band cell | `Int64` | **yes** | explicit source `0` → `0`; source `<NA>` → `<NA>` (dense). **A derived band observation carrying a reported count — not an individual patient/pathway record.** A value of 27 is one observation reporting 27. |

Lineage: `(source_file, source_row_index, wait_band_label)` — equivalently
`(source_file, source_row_index, wait_band_order)` — identifies the exact source
cell each long row represents. No fake raw-source row identity is created for
derived rows. **Source provenance** (`source_file` / `source_sha256` /
`source_row_index`) is kept distinct from **transformation lineage**
(`wait_band_order` / `wait_band_label`).

### 5.1 Persisted-output validation (authoritative — P4-A02)

`run_phase4` **mandatorily** runs `transform.validate_persisted_long(long_path,
wide, meta)` against the **staged Parquet on disk** before the publication is
committed. It streams the file in fixed-size batches (bounded memory: the
reference arrays scale with the *wide* row count, which is fixed; the long file
is never materialised) and checks **positionally** — the writer emits
parent-major order, so persisted long row `p` is parent `p // 105` band
`(p % 105) + 1` — every one of:

* the exact Arrow schema and exact row count (`= len(wide) × 105`);
* `wait_band_order`, `wait_band_label`, `wait_band_lower_weeks`,
  `wait_band_upper_weeks` (null only on the open band);
* all nine parent / provenance identity fields (`reporting_month`, `Period`,
  the four dimension codes, `source_file`, `source_sha256`, `source_row_index`)
  against the verified analytical-wide parent;
* `pathway_count` value **and** its explicit-`0` / source-`<NA>` state against
  the wide band cell — compared as **exact `int64` throughout** (P4-R02): the
  wide reference is an integer matrix + a separate NA mask, and the persisted
  Arrow column is read via `fill_null(0).to_numpy()`, with **no `float64`
  round-trip**, so the full nullable `Int64` domain (including values `> 2**53`)
  is validated exactly.

A repeated / missing / reordered band, a wrong order / label / bound, a swapped
value, a zero↔NA change, a wrong identity field, or a duplicate / extra
observation each breaks positional alignment or the row-count check and raises
`LineageError` / `CardinalityError` — **including faults introduced after
serialization**, because the file on disk is what is read. On the current
publication: 56,843,115 rows in 217 batches, **0 value / NA-state / identity
mismatches**, ~40–46 s.

`transform.reconcile_long_against_wide(wide, long_frame)` is a **heavier
in-memory secondary diagnostic** (a melt + one-to-one outer merge, run on a
frame — the full 56.8M-row form is optional, `run_phase4(reconcile_long=True)`
or a per-month slice in the notebook). Hardened per P4-A02 / P4-R01: exact
`len == len(wide) × 105`, no duplicate
`(source_file, source_row_index, wait_band_order)`, every identity field (six
dimensions + `source_sha256` + label) equal to the parent, and **explicit,
NA-safe band-bound checks** — expected and actual `wait_band_lower_weeks` must
both be non-null and integer-equal; the `wait_band_upper_weeks` null mask must
match the metadata exactly (only the open `>104` band is null) and numeric
bounds are compared only at non-null positions — never via nullable equality +
a skip-NA reduction.

---

## 6. Missingness contract (hard Phase 4 requirement)

* **No blanket `fillna(0)`** anywhere in the analytical data.
* `explicit zero != missing/NA` is maintained end to end:
  * analytical-wide: source cells are carried through untouched;
  * dense-long: an explicit source `0` becomes a `pathway_count == 0`
    observation; a source `<NA>` stays `<NA>`.
* Structurally-not-collected fields stay `<NA>` (`Total` / unknown-clock for
  Parts 2/2A/3; every band for Part_3). Distinct from a missing value inside a
  populated distribution.
* `Total All` is never blank in the current publication (0 rows).
* Any calculation that needs `<NA>` to contribute `0` must do so **locally and
  explicitly**, without overwriting the analytical value (as Phase 2 does for
  its reconciliations under the scoped D-016 convention). Phase 4 adds no such
  calculation.

Tests (`tests/test_transform.py`) prove the zero-vs-`<NA>` distinction survives
both transformations.

---

## 7. Dense-long benchmark (§8 of the Phase 4 brief)

`541,363 × 105 = 56,843,115` possible source-row × waiting-band observations.
The dense representation was **implemented and benchmarked** on the development
machine (AMD Ryzen AI 5 340, 24 GB RAM; Python 3.14, pandas 3.0.5, pyarrow
25.0.1). The transform runs in parent-row blocks (default 40,000 wide rows →
4,200,000 long rows per block) streamed to one Parquet file via
`pyarrow.parquet.ParquetWriter`, so peak memory is bounded by one block.

| Metric | Result |
|---|---|
| Long rows | 56,843,115 (= wide × 105, asserted; read-back confirms) |
| Parquet size | ~19 MB (zstd; dictionary encoding collapses the repeated dimension strings) |
| Build + write time | ~45–60 s (integer-preserving path) |
| Mandatory persisted-long validation (`validate_persisted_long`, streamed from disk) | ~33–44 s, 217 batches, 0 mismatches |
| Peak Python allocation (`tracemalloc`, build) | ~0.55 GiB |
| Blocks / row-group size | 14 blocks × 40,000 wide rows; pyarrow row groups ≈ 1,048,576 rows |
| Read / query practicality | full read-back and the positional 56.8M-cell validation complete comfortably in memory; column projection / predicate push-down on `reporting_month`, `wait_band_order`, `Treatment Function Code` are cheap |
| Memory pressure / disk behaviour | none observed — no swapping, no pathological write pattern (the atomic commit retries a transient Windows `PermissionError` on `os.replace`) |

**Conclusion: dense long is practical at this scale and is retained.** No sparse
alternative is introduced. Should a future dataset make dense long materially
impractical, the brief's procedure applies: preserve the semantic requirement,
report the benchmark evidence, propose a sparse alternative, state precisely
what an absent sparse row would mean and how the reconciliation/lineage
invariants would change, and stop for methodological approval before making a
sparse representation authoritative.

---

## 8. Wait-band metadata (`wait_band_metadata.parquet`)

105 rows, derived deterministically from `semantics.expected_week_band_names()`
and `semantics.parse_week_band()` — **not** a second hand-maintained list.

| Column | Meaning |
|---|---|
| `wait_band_order` | 1–105, header order (frozen) |
| `wait_band_label` | canonical source column name |
| `wait_band_lower_weeks` / `wait_band_upper_weeks` | week boundaries; `upper` is `<NA>` for `>104` (`is_open_ended`) |
| `wait_band_lower_days` / `wait_band_upper_days` | **DERIVED** day bounds (P2-U6), labelled derived: first band `0–7` days; band `n`–`n+1` (n≥1) → days `7n+1 … 7(n+1)`; final band `≥ 729` (`upper` `<NA>`). NHS England publishes only 5 worked examples. |
| `is_open_ended` | `True` only for `Gt 104 Weeks SUM 1` |

**No** business/KPI classification (`over_18_weeks`, etc.) is added — threshold
logic is Phase 7. "Within *k* weeks" selection remains
`semantics.bands_up_to_weeks`.

---

## 9. Data-quality policy — four distinct categories (P4-A05)

Phase 4 keeps these separate and never implies that all unusual values are
errors. Note the first two categories are **not mutually exclusive**: a
*factual condition flag* can flag a *structurally expected* condition — that is
by design, not a contradiction.

| Category | What it is | Examples | Treatment |
|---|---|---|---|
| **Factual DQ / condition flag** | a `dq_` column recording that a row meets a stated condition, whatever its cause | `dq_all_bands_missing`, `dq_total_missing`, `dq_part2a_gt_part2`, `dq_part2a_no_matching_part2` | computed and emitted for **every** row that meets the condition; source values never changed |
| **Structurally expected condition** | a factual condition that is *expected* for certain RTT Parts and is **not** an anomaly | `dq_all_bands_missing` for **Part_3** (bands not collected); `dq_total_missing` for **Parts 2/2A/3** (`Total` not collected); also blank `Total` / unknown-clock, blank band cell in a not-collected distribution | flagged (above) and documented as structural; **not** treated as an error or repaired |
| **Anomalous source condition** | a factual condition that *is* a source data-quality issue | `dq_part2a_gt_part2` (numeric `Part_2A > Part_2`); `dq_part2a_no_matching_part2` (no usable `Part_2` comparator) — the four Part_2A states are: (1) no matching `Part_2` identity, (2) matching `Part_2` identity but `Total All` is `<NA>`, (3) matching numeric comparator (conformant), (4) numeric `Part_2A > Part_2`. States (1) and (2) set `dq_part2a_no_matching_part2`; state (4) sets `dq_part2a_gt_part2` | **preserved and flagged**, never repaired, capped, coerced or discarded (P2-U7, D-022) |
| **Legitimate semantic classification** | an `is_*` / `rtt_part_*` column describing a valid source category — **not** a DQ judgement at all | `is_treatment_function_total` (C_999), `is_nonc_commissioner` (NONC), `rtt_part_event_basis`, `rtt_part_carries_bands`, `rtt_part_is_month_end_snapshot` | analytical convenience; kept separate from the `dq_` columns |

Mapping instability / churn across months (new/retired provider codes,
`Y63` appearing in June, name↔code collisions such as `DUCHY HOSPITAL`) is
**diagnostic information**, surfaced via `crossmonth.mapping_diagnostics`, not
invalid data.

---

## 10. Phase 4 publication lifecycle — coherent, atomic, self-verifying (P4-A03)

`run_phase4` publishes the six-file output set as **one logical generation**:

1. **Verified snapshot** — `load_verified_publication` (§2) binds the input to a
   private immutable snapshot.
2. **Transform** — build analytical-wide + wait-band metadata (in memory).
3. **Stage** — write every output (`rtt_analytical_wide.parquet`,
   `wait_band_metadata.parquet`, `rtt_waiting_band_long.parquet`,
   `phase4_transformation_report.json`, `phase4_transformation_report.md`) into a
   private `.staging-*` directory under `out_dir`. Nothing in `out_dir` is
   touched yet.
4. **Validate the persisted long** — `validate_persisted_long` streams the
   staged Parquet from disk (§5.1); a failure here aborts before any commit.
5. **Manifest** — `build_phase4_manifest` records: `phase: 4`; the consumed
   Phase 3 identity (`generation_id`, `consumed_parquet_sha256`,
   `combined_rows`); **exactly the five canonical outputs**
   (`REQUIRED_MANIFEST_OUTPUTS` — the manifest may *not* redefine what a Phase 4
   publication is) each with `file` (canonical filename) / `sha256` / `bytes`
   (and for Parquet, `rows` / `columns` / `column_names` / `schema`);
   `analytical_wide_rows` / `wait_band_metadata_rows` (105) /
   `waiting_band_long_rows` / `bands_per_parent` (105) /
   `long_equals_wide_times_bands`. The `phase4_generation_id` comes from the
   **single shared** `compute_phase4_generation_id` over (Phase 3 input identity
   + the two byte-deterministic data artifacts + the exact long cardinality) —
   so it is **stable across runs and across `block_rows`** (the long file's
   physical SHA-256 is bound separately in `outputs`, not in the identity).
6. **Atomic commit** — rotate any current generation to `*.prev` (only if it
   currently verifies under the full contract), then `os.replace` each output
   into place with `phase4_generation.json` **last**. That final replace is the
   commit point.
7. **Self-verify** — `verify_phase4_publication(out_dir)` must return
   `{"valid": True}` or `run_phase4` raises `Phase4PublicationError`.

**Consumer gate — `verify_phase4_publication(out_dir)` (enforces the full
contract — P4-R03).** A malformed manifest / publication always returns a
structured `{"valid": False, "reason": …}` — **never** a `KeyError`. A published
generation is *valid* iff:

* the manifest is a JSON object with `phase == 4`;
* `outputs` has **exactly** the canonical keys, each at its **canonical local
  filename** — a missing / extra / duplicate / redirected / traversal member
  fails; the manifest cannot redefine the required output set;
* every field's type and value is sane — `phase4_generation_id` 64-hex;
  `phase3_input` = {non-empty `generation_id`, 64-hex `consumed_parquet_sha256`,
  positive `combined_rows`}; positive `analytical_wide_rows` /
  `waiting_band_long_rows`; `wait_band_metadata_rows == 105`;
  `bands_per_parent == 105`; `long_equals_wide_times_bands is True`;
  `waiting_band_long_rows == analytical_wide_rows × 105`;
  `combined_rows == analytical_wide_rows` (Phase 3 row conservation);
* **every physical claim is re-checked against the file on disk** — SHA-256,
  byte size, and (Parquet) row count / column count / ordered column names /
  serialized schema; the long Parquet must carry the canonical
  `_long_arrow_schema`; both reports exist and hash, and the JSON report
  parses;
* the JSON report **reconciles** with the manifest (Phase 3
  `generation_id` / `consumed_parquet_sha256` / input rows, and the
  analytical-wide / long row counts);
* `phase4_generation_id` **recomputes** from `compute_phase4_generation_id`
  over the independently re-validated identity material — so a forged id, or a
  forged Phase 3 identity that the hashed report contradicts, fails.

So an old wide / long / metadata / report swapped in, a tampered Parquet, a
false schema / count / byte / identity claim, or a mixed set all fail.

**Interruption semantics.** A failure *before the first replace* leaves the
previous generation intact and still verifying. A failure *during the replaces*
leaves a state `verify_phase4_publication` reports as **invalid**;
`restore_previous_phase4_generation` verifies the `*.prev` set in a scratch dir
and restores it, or a clean re-run stages and commits afresh. **After the
manifest commit point** a subsequent fault may leave the **coherent new
generation valid** — that is a permitted, accepted state, not an invalid one. A
mixed generation is **never** silently accepted, and a malformed current
manifest is **not** eligible for `*.prev` rotation.

Generated Parquets (and the manifest, report, `*.prev`) stay git-ignored under
`data/processed/`.

---

## 11. Transformation / data-quality report

`build_transformation_report` produces a machine-readable dict (written as
`phase4_transformation_report.json`); `render_report_markdown` renders
`phase4_transformation_report.md`. **Row-level quality conditions** (attributable
to one source-grain record — the four `dq_` flag counts, by month and RTT Part)
are kept separate from **dataset-level diagnostics**:

* **Input integrity** — Phase 3 verification result, `generation_id`, source
  months, input rows/columns.
* **Transformation integrity** — wide row conservation, candidate-key
  uniqueness, `reporting_period_start_date` dtype, long cardinality (= wide ×
  105), sort contracts, lineage keys, the **authoritative persisted-long
  validation** result, and the optional in-memory reconciliation.
* **Missingness** — rows all-bands-missing, `Total` missing, `Total All`
  missing, dense-long explicit-zero vs source-`<NA>` counts, derived-field
  missingness.
* **Semantic diagnostics** — `Part_2A` violations / unmatched groups per month
  (with a cross-check against the row-level flags), C_999 coverage, NONC
  coverage, and the aggregation rules carried forward.
* **Mapping diagnostics** — `crossmonth.mapping_diagnostics` (code↔name
  instability, name collisions, membership changes).
* **Dense-long benchmark** — rows, Parquet bytes, build/write time, peak
  allocation, read-back check.

No substantive waiting-time interpretation is performed in the report.

---

## 12. Determinism — logical vs physical (P4-A04)

**Logical determinism (holds across *any* valid `block_rows`, including a
non-divisible final block).** Same Arrow schema, same rows, same values, same
NA states, same analytical ordering, same lineage. Explicit contracts:

* **row order** — analytical-wide: `[reporting_month, source_row_index]`
  ascending; long: `[reporting_month, source_row_index, wait_band_order]`.
* **band order** — `wait_band_order` 1–105 = `expected_week_band_names()` order.
* **derived fields** — pure functions of source columns; `pathway_count`
  through an integer-preserving path (no float `2**53` ceiling).
* **output schemas** — fixed (`transform.LONG_COLUMNS`, the derived-column
  lists, the Arrow schema for the long writer).
* **`phase4_generation_id`** — derived from analytical content, so identical
  across runs and across `block_rows`.
* `deterministic_report_view(report)` drops the variable fields (below) and is
  identical across runs / block sizes.

**Physical byte repeatability (fixed configuration only).** Two `run_phase4`
executions with the **same writer + environment + `block_rows`** produce
byte-identical `rtt_analytical_wide.parquet`, `wait_band_metadata.parquet` and
`rtt_waiting_band_long.parquet`. `rtt_analytical_wide.parquet` and
`wait_band_metadata.parquet` are additionally byte-identical **across**
`block_rows` (they do not depend on it). Changing `block_rows` changes the
**long** file's Parquet row-group structure and therefore its file hash — the
logical content is unchanged. Do not use the raw long-file hash as a
cross-configuration determinism test; use `validate_persisted_long` or a
`pandas` frame comparison.

**Intentionally variable report / result fields** (`VARIABLE_REPORT_FIELDS`):
`generated_utc`; `dense_long_benchmark.{build_write_seconds, peak_tracemalloc_mib,
path, parquet_bytes, block_rows, n_blocks, row_group_rows}`;
`transformation_integrity.persisted_long_validation.{seconds, path, batches}`.
The manifest additionally carries a `committed_utc`. Everything else in the
report / manifest is deterministic analytical content.

Nothing depends on filesystem enumeration order or unstable grouping order.

---

## 13. Regression & audit

* Frozen Phase 1–3 source (`profile.py`, `semantics.py`, `ingest.py`,
  `crossmonth.py`), their tests and notebooks 01–03 are **unmodified**.
* Full suite after the closure-audit residual fixes: **323 passed** (208 frozen
  + 115 in `tests/test_transform.py`).
* Independent Phase 4 audits: `docs/phase4_codex_audit.md` (PASS WITH CHANGES —
  P4-A01…A05, remediated per `docs/decisions.md` **D-041**) →
  `docs/phase4_codex_closure_audit.md` (PASS WITH CHANGES — A01/A04/A05 CLOSED;
  residuals P4-R01/R02/R03, remediated per **D-042**). Codex evidence under
  `outputs/audit/phase4/` and `outputs/audit/phase4_closure/` is preserved
  unchanged.
* `phase-4-pass` is **not** created here. A final narrow independent closure
  check follows; the milestone/tag is the project owner's, after acceptance.

---

## 14. Phase 4 boundary (NOT done here)

No dimensional / star schema, no surrogate-key architecture, no calendar /
organisation / treatment-function / wait-band dimension tables, no DuckDB / SQL
analytical layer or views (Phase 5). No exploratory analysis, provider
performance or trend conclusions, statistical testing (Phase 6). No KPI /
business rules, 18-week performance measures, threshold classifications, the
estimate-inclusive uplift (Phase 7). No Power BI model or dashboard (Phase 8).
No analytical story / portfolio packaging (Phase 9). No ML, no Spark.

Phase 4 output is recognisably derived from the Phase 3 source structure —
cleaned only where "cleaning" means *reshaped, classified and quality-flagged
with provenance intact* — and nothing further.
