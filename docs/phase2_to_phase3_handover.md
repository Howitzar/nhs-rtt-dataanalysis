# NHS RTT Data Analytics — Phase 2 → Phase 3 Handover

**Purpose of this document.** It is the primary orientation for the next Claude
Code conversation. It describes the **current accepted project state** — not a
chronological history — so the next instance can continue correctly without the
prior chat. Where older discussion conflicts with the final repository / audits,
**the latest independently accepted state wins** and is what appears below.

**Immediate next action after reading this:** repository hygiene inspection and
creation of the accepted Phase 2 Git milestone (§15). **Do not begin Phase 3.**

---

## 1. Project objective & collaboration model

**What it is.** A reproducible, auditable analytical pipeline for NHS England
Consultant-led **Referral-to-Treatment (RTT) waiting-times** data — from raw
monthly CSV publications through to a validated analytical dataset, a SQL
analytics layer, KPIs, and a Power BI dashboard with a written analytical story.

**Why.** A junior Data Analyst / data-focused **portfolio** project. Its value
is that every analytical decision is **defensible and explainable by the project
owner in an interview** — the reasoning matters more than the tooling.

**Governing principles (keep these):**

* *Analytically defensible, not a technology showcase.* Add a technology only
  when the data and the phase genuinely require it. **Spark is not justified** at
  this scale (~80 MB/month); do not add it. Do not add breadth for its own sake.
* Pipeline order: **Meaning → ingestion → transformation → model → analysis →
  KPIs → presentation.**
* Division of labour: **Code inspects the full data; AI reasons over code,
  summaries, anomalies, tests, and representative examples.** Never dump large
  slices of the 182k-row file into context.
* Every conclusion is labelled by evidence class (see §5).

**Working model.**

| Role | Who | Responsibility |
|---|---|---|
| Project owner | the user | analyst, decision-maker, learner; approves material decisions and all Git actions |
| Implementation engineer | Claude Code | builds reusable `src/` modules, notebooks, tests, docs; proposes, doesn't decide material ambiguity |
| Independent reviewer | Codex | audits each phase against the brief and the data; issues PASS / PASS WITH CHANGES / FAIL |
| Methodology partner | ChatGPT | planning and review support |

---

## 2. Accepted roadmap

| # | Phase | Status |
|---|---|---|
| 1 | Data Discovery & Structural Profiling | **COMPLETE / FROZEN / independently accepted** |
| 2 | Dataset Semantics, Grain & Arithmetic Validation | **COMPLETE / FROZEN / final independent Codex PASS** |
| 3 | **Reproducible Multi-Month Ingestion & Provenance** | **NEXT — not started.** Plan explicitly after the Git milestone. |
| 4 | Transformation, Data Quality & Analytical Dataset | not started |
| 5 | Dimensional Modelling & SQL Analytics Layer | not started |
| 6 | Exploratory Analysis & Statistical Investigation | not started |
| 7 | KPI & Business-Logic Layer | not started |
| 8 | Power BI Semantic Model & Dashboard | not started |
| 9 | Analytical Story, Validation & Portfolio Publication | not started |

**Gates:** semantics before scale · transformation before modelling · analysis
before dashboard · validation before claims.

**Anticipated architecture (direction, not early permission):**
`CSV → Pandas validation → Parquet → DuckDB/SQL → Power BI`. Introducing
Parquet, DuckDB/SQL or BI **before** their phase is out of scope. Parquet
becomes appropriate in Phase 3/4 when the ingestion design calls for it.

---

## 3. PHASE 1 STATUS: COMPLETE / FROZEN / INDEPENDENTLY ACCEPTED

Independent audit: `docs/phase1_audit.md` (Codex, PASS WITH CHANGES → remediated
→ accepted). Reusable code: `src/nhs_rtt/profile.py`. Notebook:
`notebooks/01_data_discovery.ipynb`. Outputs: `outputs/profiles/rtt_2026_06__*`
(gitignored, regenerable). Data dictionary: `docs/data_dictionary.md`.

**Accepted Phase 1 structural facts (June 2026 development file):**

| Item | Value |
|---|---|
| File | `data/raw/rtt_2026_06.csv`, 82,084,725 bytes, period `RTT-June-2026` |
| Shape | **182,411 data rows × 121 columns** |
| Column groups | cols 0–12 = **13 identifier/label** columns; cols 13–117 = **105 week-band** columns (`Gt 00 To 01 Weeks SUM 1` … `Gt 103 To 104 Weeks SUM 1`, then open-ended `Gt 104 Weeks SUM 1`); col 118 `Total`; col 119 `Patients with unknown clock start date`; col 120 `Total All` |
| Identifier/label columns | `Period`; `Provider Parent Org Code`/`Name`; `Provider Org Code`/`Name`; `Commissioner Parent Org Code`/`Name`; `Commissioner Org Code`/`Name`; `RTT Part Type`/`Description`; `Treatment Function Code`/`Name` |
| Encoding | UTF-8, **no BOM**; parses cleanly under strict `utf-8-sig` |
| Exact duplicate rows | **0** (true whole-row equality, not a hash approximation) |
| Ragged rows | 0 |
| RTT Part Types | `Part_1A` (18,803 rows), `Part_1B` (32,351), `Part_2` (63,355), `Part_2A` (30,548), `Part_3` (37,354); each 1:1 with its `RTT Part Description` |
| Providers | 537 `Provider Org Code` / **536** `Provider Org Name` — one shared name: **`DUCHY HOSPITAL` → `NT447` + `NVC04`** |
| Provider Parent | 36 codes / 36 names |
| Commissioner | 129 `Commissioner Org Code`; 121 non-blank names; name blank on 3,348 rows across 8 codes (`NONC`, `Y56`, `Y58`–`Y63`) |
| Commissioner Parent | 36 codes / 36 names; **blank on 10,263 rows** (the NONC / NHS-England-commissioned rows) |
| Treatment Function | **24** codes = 23 "detail" (`C_100`…`C_502` + `X02`–`X06` "Other …") + **`C_999`** whose name is the literal `Total` |
| Missingness (headline) | `Total All` never blank; `Total` blank ~72 %; unknown-clock blank ~81 %; week-band columns blank ~28–33 % each |
| `C_999` discovery | Phase 1 saw `C_999`/`Total` on 40,636 rows and **flagged it as a possible pre-aggregate**, deliberately not treating it as a specialty |
| Raw-data immutability | raw files are never edited, resaved, filtered or imputed; verified by SHA-256 before/after every run |

**Phase 1 deliberately did NOT assume** (A-01…A-17 in `docs/assumptions.md`):
blank = 0 · `Total = Total All` · `Total All = band sum` · unknown-clock has a
fixed arithmetic role · every provider is an NHS trust · code↔name maps are
universally 1:1 · `C_999` may be mixed with detail · rows may be summed across
RTT Parts · a primary key is NHS-guaranteed · week bands are ready to reshape.
**Phase 2 resolved or narrowed most of these — §5 below is now the current
truth; the raw Phase 1 A-xx list is historical context, not current guidance**
(`docs/assumptions.md` "Phase 2 resolutions" table maps each A-xx → outcome).

---

## 4. PHASE 2 STATUS: COMPLETE / FROZEN / FINAL INDEPENDENT CODEX PASS

**Audit trail (see the named docs for detail; do not re-derive):**

| Step | Artifact | Verdict |
|---|---|---|
| 1. Initial implementation | `src/nhs_rtt/semantics.py`, `notebooks/02_…`, `docs/rtt_semantics.md`, `docs/rtt_grain_and_aggregation.md`, `docs/phase2_completion_report.md` | — |
| 2. First independent audit | `docs/phase2_independent_audit.md` (findings P2-A01…P2-A10) | PASS WITH CHANGES |
| 3. Targeted remediation | `docs/phase2_remediation_report.md` | — |
| 4. Focused closure audit | `docs/phase2_closure_audit.md` (5 CLOSED; 5 PARTIALLY CLOSED; new HIGH **P2-R01**) | PASS WITH CHANGES |
| 5. Final residual remediation | `docs/phase2_closure_remediation_report.md` | — |
| 6. **Final focused Codex closure check** | **`docs/phase2_final_closure_check.md`** | **PASS** |

`docs/phase2_completion_report.md` carries a "SUPERSEDED IN PART" banner — treat
`rtt_semantics.md`, `rtt_grain_and_aggregation.md`, `assumptions.md`,
`decisions.md` and `phase2_final_closure_check.md` as the current authority.

**Final reproducibility evidence (from `phase2_final_closure_check.md`, 7 Sep 2026):**

| Check | Result |
|---|---|
| `pytest -q` | **98 passed**, 0 failed, 0 skipped |
| Split | 47 Phase 1 (`tests/test_profile.py`) + 51 Phase 2 (`tests/test_semantics.py`); Phase 2 = 39 code-correctness cases + 2 immutability + 10 June-invariant |
| `notebooks/01_data_discovery.ipynb` | 0 errors |
| `notebooks/02_semantics_grain_validation.ipynb` | 0 errors |
| Phase 1 outputs | all 9 CSVs byte-identical to saved |
| Phase 2 outputs | all 10 CSV/JSON files byte-identical to saved |
| Raw hashes | all three unchanged; June matches the required value |
| Phase 3 | none begun |
| New blocking defect | none |

---

## 5. Final accepted Phase 2 semantic model

Evidence classes used throughout the docs: **CONFIRMED — DOCS+DATA** (NHS
definition + shown in June) · **CONFIRMED — DATA** (shown in June, not verbatim
in guidance) · **DOCUMENTED** (NHS definition, not row-testable here) ·
**INFERRED** · **UNRESOLVED** · plus the Phase-2 term **ARITHMETIC CONVENTION**
(reconciles under a stated zero-fill; not a semantic claim).

NHS sources: **S1** = "Recording and reporting RTT waiting times for
consultant-led elective care", v5.0, 11 Feb 2025 (PRN01045). **S5** = "RTT
statistics user guidance". **S6** = RTT Statistical Press Notice, **June 2026**
(published 13 Aug 2026). Full citation table in `docs/rtt_semantics.md` §1.

### 5.1 RTT Part Types (S1 §10.1.1.2) — CONFIRMED — DOCS+DATA

| Code | Meaning | Event basis |
|---|---|---|
| `Part_1A` | Completed pathways – **admitted** (RTT clock stopped in-month with an inpatient/day-case admission) | in-month *flow* |
| `Part_1B` | Completed pathways – **non-admitted** (clock stopped in-month for any other reason) | in-month *flow* |
| `Part_2` | **Incomplete** pathways — patients still waiting at month-end (a **month-end snapshot / stock**) | month-end *stock* |
| `Part_2A` | Incomplete pathways **with a decision to admit (DTA)** — a **subset of `Part_2`** | month-end *stock*, ⊆ `Part_2` |
| `Part_3` | **New RTT periods** — count of clock starts during the month | in-month *flow* |

"DTA" = decision to admit (S1). The five parts are **different populations on
different event bases** — never a single "all pathways" set.

### 5.2 Arithmetic model — per part, with coverage & policy

Reference table: `outputs/phase2/reconciliation_by_part.csv` (+ `…coverage_by_part.csv`).
Every identity is exact-integer. A row is **evaluated** only when *both*
operands are non-`<NA>` **after applying only the explicitly-authorised
zero-fill** (see §6 K-1). Any row still carrying a missing **required** operand
(`Total All`, `Total`, or an all-blank band distribution) is **excluded and
counted** (`n_missing_operand`), for both policies — an unqualified `HOLDS`
requires zero exclusions.

**`observed_band_sum`** = the sum of the *observed* (non-missing) band cells;
it is `<NA>` **iff every band cell is missing** (i.e. Part_3). It is a
skip-missing numerical convention, **not** a claim that a blank band is a zero.

| Part | Strict identities that HOLD in June (0 mismatches, full coverage) | Class |
|---|---|---|
| `Part_1A` / `Part_1B` | `observed_band_sum == Total` (all rows); **`Total + unknown == Total All`** on **unknown-clock-populated** rows (1A: 12,771 / 1B: 21,346); **`Total == Total All`** on **unknown-clock-blank** rows (1A: **6,032** / 1B: **11,005**). The two subsets are disjoint and partition the part. | CONFIRMED — DATA |
| `Part_1A` / `Part_1B` (+ convention) | `Total + unknown(missing→0) == Total All` over **all** rows — HOLDS **under the stated missing-as-zero convention**, applied to the blank-unknown rows. | ARITHMETIC CONVENTION |
| `Part_2` / `Part_2A` | `observed_band_sum == Total All` (all rows; 63,355 / 30,548). `Total` and unknown-clock are **not collected** (100 % blank). | CONFIRMED — DATA |
| `Part_3` | **None.** Bands + `Total` + unknown-clock all blank on every row; `observed_band_sum` is `<NA>`. A strict band identity evaluates **0** rows → reported `PARTIAL (37,354 excluded)`, deliberately not `HOLDS`. `Total All` is a **standalone count** of new clock starts. | CONFIRMED — DOCS+DATA |

Consequence: strict `observed_band_sum == Total All` for 1A/1B fails by exactly
`−unknown` on the **71 (1A) / 235 (1B)** rows with a positive unknown-clock
count (`outputs/phase2/mismatch_positive_unknown.csv`).

### 5.3 Field meanings

| Field | Meaning | Class |
|---|---|---|
| `Total All` | Pathway (**not patient**) count for the row: completed pathways (1A/1B), pathways open at month-end (2/2A), or new clock starts (3). National sums reproduce S6 exactly — §11. | CONFIRMED — DOCS+DATA |
| `Total` (1A/1B only) | `= observed_band_sum` for every completed row; `Total All − Total = unknown`. Label "completed pathways with a known clock start" is a reasonable reading of S1 §10.1.5, not verbatim. | CONFIRMED — DATA (arithmetic); INFERRED (label) |
| `Patients with unknown clock start date` (1A/1B only) | Completed pathways whose RTT clock-start date could not be identified, so they cannot be band-placed; an **additive** term to `Total All`. S5 confines this field to *completed* pathways. **Blank on 6,032 (1A) / 11,005 (1B) rows** — it is *not* "never blank". | CONFIRMED — DOCS+DATA |

### 5.4 Week bands — CONFIRMED — DOCS+DATA (structure); DOCUMENTED (day boundaries)

105 mutually-exclusive weekly wait bands **by days waited** (S1 §10.1.7): band
"0-1 weeks" = 0–7 days; "17-18 weeks" includes 126 days (so a wait of exactly 18
weeks is in the 17-18 band); "104+ weeks" = ≥729 days. "Within *k* weeks" = the
bands with upper bound ≤ *k*. Applies to Parts 1A/1B/2/2A only; **not Part_3**.
Arithmetic consistency is *consistent with* disjoint bands but does not *prove*
patient-level disjointness.

### 5.5 The distinction that must be preserved everywhere

> **Arithmetic compatibility established; semantic equivalence not established.**

* *Observed equality* — the numbers genuinely match on both sides.
* *Numerical zero-contribution convention* — a stated, scoped choice to treat a
  **specifically authorised** missing contribution as `0` for a validated
  calculation. Applied per calculation. **Not** imputation.
* *Semantic meaning* — why a publisher serialised a cell as blank vs `0`, or
  whether a blank could be "unknown/withheld". **Unresolved.** S1 Annex B has
  total/quality checks, not a cell-encoding rule.

**Structurally uncollected fields stay uncollected.** `Total`/unknown-clock for
Parts 2/2A/3, and every band for Part_3, are **not-collected** (100 % blank) —
this is structural non-applicability, distinct from a missing value within a
populated distribution. Raw missingness is preserved in the loaded frame
(`load_rtt_csv` keeps blank as `<NA>`; `keep_default_na=False, na_values=[""]`
so a literal `NULL` in a code column stays a string).

---

## 6. K-1 and K-2 (final approved, with modification)

### K-1 — scoped numerical zero-contribution convention — APPROVED (with modification)

A scoped, **non-destructive** numerical zero-contribution convention **may** be
used, **only** for independently validated calculations, and **only** for
**explicitly authorised** missing contributions:

* a validated missing **waiting-band** contribution (via `observed_band_sum`'s
  skip-missing behaviour);
* a validated **blank unknown-clock** contribution (D-016).

It does **NOT** mean: blank universally = zero · fill raw missing values ·
automatic application to future files · treating a **missing required reported
operand** (`Total All`, `Total`, an entire unobserved distribution) as zero.

**Post-P2-R01 reconciliation safeguards (decision D-028, in `_reconcile`):**

1. a row is evaluated only when **both** operands are non-`<NA>` after only the
   authorised fill; otherwise it is excluded and counted (`n_missing_operand`,
   verdict `PARTIAL`), never a match;
2. `Total` and `Total All` are **never** pre-filled;
3. match counts come from an **explicit equality mask**, never
   `n_evaluated − n_mismatch`;
4. zero-evaluated / all-missing operands return `None` extrema without a
   numeric-conversion error;
5. `n_convention_rows` records where an authorised fill was actually used;
6. `aggregate_vs_detail` exposes **`acceptable`** (policy-aware: no orphan
   groups, exactly one aggregate row per group, zero numeric mismatch, and
   `cmp_other_missing == 0`). `reconciles_numeric` is a **diagnostic only**
   (numeric/numeric cells) and must not be used alone as acceptance.

### K-2 — candidate natural key — APPROVED (with modification)

```
[ Period, Provider Org Code, Commissioner Org Code, RTT Part Type, Treatment Function Code ]
```

Unique for **all 182,411** June rows (also unique without the constant
`Period`). Dropping `Treatment Function Code` **or** `Commissioner Org Code`
breaks uniqueness. Parent codes are functionally determined and redundant.

**Conditions before relying on it for any incoming file:** all five columns
present; **no missing key cell**; uniqueness re-checked **per file**; a defined
**revision / re-release policy** (`Period` does *not* distinguish a revised file
from the original).

It **is** a candidate natural key supported by the observed extract. It is
**NOT** an NHS-guaranteed primary key and **NOT** a patient/pathway identifier.
No surrogate key was introduced. `candidate_key_report(...)` returns
`is_unique=None` (never silently `True`) when a column is absent and `usable`
stays `False` until every precondition passes.

---

## 7. Exact 105-band schema contract (Phase 2 production validation boundary)

`nhs_rtt.semantics.validate_extract(path, require_full_band_schema=True)` and
`load_rtt_csv(..., require_full_band_schema=True)` are the **default production
gate** (decision D-029). Before pandas can mangle the header they require:

* **exactly 105** week-band columns;
* first band `Gt 00 To 01 Weeks SUM 1`;
* the ordered weekly sequence `0-1 … 103-104`;
* open-ended final band `Gt 104 Weeks SUM 1`;
* **no missing interior band**, **no duplicate band**, **no unexpected
  additional band-like column**, correct order;
* plus: no duplicate header names; required key + measure columns present.

Malformed / truncated schemas (zero bands, a single band, missing first band,
missing open-ended band, missing interior band, duplicate, extra, reordered)
are **rejected** with `ValueError`. The canonical names are
`semantics.expected_week_band_names()`.

This strict acceptance gate is **separate** from generic Phase 1 band
*discovery* (`nhs_rtt.profile.classify_columns` /
`check_week_bucket_sequence`). Miniature synthetic unit tests deliberately
bypass it with `require_full_band_schema=False`; they are not production
extracts. **Phase 3 ingestion must respect this contract for every month.**

---

## 8. `C_999` treatment-function aggregation (final verified)

Reference: `docs/rtt_semantics.md` §6; `outputs/phase2/facts.json →
c999_aggregate_vs_detail`; `outputs/phase2/treatment_function_rows.csv`.

* **23** possible reported non-`C_999` treatment-function codes in June (18
  named `C_1xx`…`C_502` + `X02`–`X06` "Other …" groupers). `X02`–`X06` are
  themselves internally grouped categories (S1 §10.1.4), not further decomposed.
* Grouping `[Provider Org Code, Commissioner Org Code, RTT Part Type]`:
  **40,636** groups, each with **exactly one** `C_999` row and **≥1** non-`C_999`
  row; **0** aggregate-only or detail-only groups; **0** duplicate-aggregate
  groups.
* **Detail rows per group range 1–23.** Only **18** groups carry all 23;
  **20,518** carry just one. **Do not describe every group as having 23 detail
  rows.**
* Of 4,388,688 group×column comparisons: **2,872,115** numeric on both sides
  with **0 mismatches**; **928,416** both-missing; **588,157** `C_999`-zero vs
  an all-missing detail sum; **0** "other-missing". Under the stated
  zero-contribution convention every group reconciles; the last two states are
  **not** observed numeric equalities.
* Arithmetic reconciliation of a total against its parts **does not prove
  patient-level disjointness** — an already-duplicated population can also sum
  consistently. The 23 codes are the **reported analysis level**, not proof of
  indivisible clinical populations.

**Analytical rule (SUPPORTED — carry into all later phases):**

> For a selected period / provider / commissioner / RTT part, use **`C_999`
> alone**, *or* the available reported non-`C_999` representation — **never
> both.** Adding one specialty to `C_999` duplicates that specialty; adding the
> whole detail set doubles the total.

---

## 9. `NONC`

Reference: `docs/rtt_semantics.md` §8; `outputs/phase2/nonc_pathways_by_part_c999.csv`.

* **Meaning (S1 §10.1.8 / §10.1.9.2):** `Commissioner Org Code = NONC` is used
  **in the aggregate monthly return** for pathways commissioned by
  **non-English** (e.g. Welsh, Scottish) commissioners — patients treated in
  England whose commissioner sits outside England. (Record-level WLMDS uses the
  specific code.)
* **Present in the raw extract.** Structural prevalence (June): **2,993 rows**
  (1.6 %), **119 providers**, all 24 treatment functions, all 5 parts.
* **Per-part pathway counts (C_999 representation)** — 1A **1,224** · 1B
  **4,478** · 2 **31,156** · 2A **7,734** · 3 **6,649**. **These five must not
  be summed** into a unique patient/pathway population (different populations;
  `Part_2A ⊆ Part_2`).
* `102,482` (raw `Total All` sum over *all* NONC rows) is an **uninterpreted
  checksum** only (`nonc_raw_cell_checksum`) — it double-counts `C_999` with its
  constituents and mixes parts.
* **Treatment:** retain NONC rows in raw and analytical data. **Exclude
  `Commissioner Org Code = NONC`** only where the published England-performance
  methodology requires it (S5). **Coverage caveat:** NONC submission is **not
  mandatory** (S5) — observed NONC rows are **not exhaustive** of non-English
  activity.
* **Verified impact on the June "% incomplete within 18 weeks" (Part_2, TFC
  Name = `Total`):** excl NONC **65.826 %** (4,704,942 / 7,147,562); incl NONC
  **65.773 %** (4,721,677 / 7,178,718) — a 0.053 pp move (NONC contributes
  16,735 / 31,156).

---

## 10. `Part_2A ⊆ Part_2` — subset rule and June source-data exception

Reference: `docs/rtt_semantics.md` §2; `docs/rtt_grain_and_aggregation.md` §6;
`outputs/phase2/part2a_subset_violations.csv`; decision **D-022**;
`nhs_rtt.semantics.part_2a_subset_conformance`.

* **Rule (DOCUMENTED, S1 Annex B):** `Part_2A` count ≤ `Part_2` count for
  matching provider / commissioner / treatment function (patient-level
  membership is not testable from this aggregate file; the count implication
  is).
* **June conformance:** 30,548 `Part_2A` groups, all with a matching `Part_2`
  key; **30,546 conform**; **2 violate** —

  | Provider | Commissioner | Treatment Function | `Part_2A` `Total All` | `Part_2` `Total All` |
  |---|---|---|---|---|
  | `RTG` | `84H` | `C_502` (Gynaecology) | 2 | 1 |
  | `RTG` | `84H` | `C_999` (Total) | 2 | 1 |

  (a detail row and its total — likely one underlying issue). A **source
  data-quality exception**, not a refutation of the NHS rule.
* **Accepted handling (D-022):** preserve source values; **flag** the
  violations; **do not cap `Part_2A` or alter `Part_2`**; any measure that
  assumes `Part_2A ≤ Part_2` (e.g. `Part_2 − Part_2A`, DTA share) must validate
  the invariant per group **before** calculating.
* **Carried forward as data-quality issue P2-U7** (§13).

---

## 11. Same-month NHS benchmark (June 2026, unestimated)

Reference: `docs/rtt_semantics.md` §9; `outputs/phase2/same_month_totals_check.csv`;
`nhs_rtt.semantics.JUNE_2026_SPN_UNESTIMATED`; decision **D-023**.

Filters (S5, "Reproducibility and derived measures"): `RTT Part Type = Part_2`,
`Treatment Function Name = Total`, numerator = bands 0-1 … 17-18, denominator
`Total All`, `Commissioner Org Code <> NONC`.

**S6 Table 1 (June 2026, "not including estimates for missing acute trusts"),
reproduced EXACTLY from the raw file:**

| Measure | Raw `rtt_2026_06.csv` | S6 unestimated |
|---|---|---|
| Incomplete pathways total | 7,147,562 | 7,147,562 |
| % incomplete within 18 weeks | 65.826 % → **65.8 %** (1 dp) | **65.8 %** |
| Completed admitted total | 318,650 | 318,650 |
| Completed non-admitted total | 1,307,837 | 1,307,837 |
| New RTT periods total | 1,930,912 | 1,930,912 |

This is a **methodology + unestimated-total** confirmation. It is **NOT** the
estimate-inclusive national headline — S6 page 1 additionally uplifts for the
two June non-submitting trusts (RHQ, RA9); that uplift is **not implemented**
(P2-U1). Matching at 1 dp is not exact estimate-inclusive reproduction.
**Do not restore the withdrawn May-2026 (65.6 %) comparison** — different months
cannot explain a residual; it survives only as explicitly-withdrawn history in
`decisions.md` D-023.

---

## 12. Aggregation-safety rules (operational — carry into every later phase)

Full matrix: `docs/rtt_grain_and_aggregation.md` §4 (+ §4a count-conservation
check, §5 ranked risks). Condensed:

* **Never mix `C_999` and its detail representation** in one sum (§8).
* **Do not sum `Part_2` + `Part_2A`** as independent populations
  (`Part_2A ⊆ Part_2`); mind the `RTG`/`84H` exception (§10).
* **Do not sum across `RTT Part Type`** without a metric-specific reason — the
  parts are different populations on different event bases.
* **Month-end stock vs monthly flow:** `Part_2`/`Part_2A` are month-end
  snapshots — an open pathway recurs in every monthly snapshot; only *flow*
  parts (`Part_1A`/`Part_1B`/`Part_3`) may be summed across `Period`, and even
  then they count **events, not necessarily distinct people/pathways**.
* **Preserve nullable grouping dimensions with `dropna=False`.** Verified: on
  June `Part_2` / `Treatment Function Name = Total` / excl-NONC, a default
  pandas `groupby("Commissioner Parent Org Code")` (`dropna=True`) **silently
  drops 489 rows / 131,509 pathways** (7,147,562 → 7,016,053). Always
  `dropna=False` (or a documented "unknown parent" label — **never invent a
  commissioning meaning**) and assert measure-total conservation.
* **Verify row/count conservation** through every transformation.
* **Codes are identifiers; names are labels.** Group/join on **codes**
  (`DUCHY HOSPITAL` → 2 provider codes; 8 commissioner codes share a blank
  name) unless a mapping has been explicitly validated.
* **Do not infer provider organisation type from the provider name** (NHS trust
  vs independent sector vs interface — needs reference data, P2-U4).
* **Validate join cardinality / multiplicity.** A many-to-one join to a
  separate parent/organisation table that fans out will double-count; a parent
  *label already on the detail row* is not itself duplication.
* **Preserve raw source values and flag data-quality exceptions** — never
  silently "clean" anomalous NHS values.

---

## 13. Remaining unresolved items (legitimately open after final PASS)

| ID | Description | Why unresolved | Blocks Phase 3? | Destination / condition |
|---|---|---|---|---|
| **P2-U1** | Exact **estimate-inclusive** England headline (non-submitting-trust uplift for RHQ, RA9). | The June publication *is* available and its **unestimated** Table 1 reproduces exactly; the uplift method (RTT Overview Timeseries) is not implemented, and 1-dp rounding is not exact reproduction. | **No.** | Later KPI / metric-validation phase (7/9). Implement & reconcile the estimate inputs **before** claiming an exact estimate-inclusive national measure. |
| **P2-U2** | Do incomplete pathways (2/2A) with an unknown clock start exist / get folded into a band? | The separate unknown-clock field is unpopulated for 2/2A and S5 confines it to *completed* pathways; neither that nor a zero residual proves such pathways negligible or placed in a band. The earlier "negligible / folded" inference is **withdrawn**. | **No** for unrelated work. | Resolve **before** any downstream claim/transformation that relies on their absence/placement. |
| **P2-U3** | Cross-month stability of schema / candidate key / code↔name maps; revised-release handling. | Only June was analytically parsed. `Period` does not distinguish a revised file from the original. | **YES — core Phase 3 responsibility.** | Phase 3: validate the §7 schema contract and re-check the §6 K-2 key **per incoming file**; define a revised/re-released-file policy before combining months. Do not use this deferral to excuse the already-promised single-file band-schema gate. |
| **P2-U4** | Provider organisational-type classification (NHS trust / independent sector / interface). | Needs the ODS `etr` / `ephp` / `ephpsite` / `ect` reference files (S1 §10.1.1.1 fn.19); not ingested. | **No.** | Reference-data work (Phase 3 provenance or Phase 4). Required before any "NHS-trust-only" or org-type analysis. **No type inference from names.** |
| **P2-U5** | `Period` literal → calendar month-end mapping; temporal alignment; file-revision selection. | Single `Period` value in the dev file. The flow-vs-stock distinction **is** documented; parsing and revision handling are not built. | **YES — Phase 3 responsibility.** | Phase 3 ingestion: parse the period, preserve the flow/stock distinction, define revised-file replacement/version selection before combining releases. |
| **P2-U6** | Full per-band day-range metadata. | S1 §10.1.7 gives **5** worked examples (0-1, 1-2, 17-18, 51-52, 104+) and states the weekly sequence; intermediate bounds are **derived** (band `n`–`n+1`, n ≥ 1: days `7n+1 … 7(n+1)`; first band 0–7; final ≥ 729). | **No.** | Implement & label as *derived* when band-label metadata is built (Phase 4/5). Not a blocker. |
| **P2-U7** | `RTG` / `84H` `Part_2A > Part_2` source data-quality exception (§10). | Genuine source-data inconsistency; publisher correction is **not** a prerequisite for acceptance. | **No.** | Carry as a flagged data-quality issue. Any subset-derived measure must run the conformance check first (`part_2a_subset_conformance`). Preserve values; do not cap. |

**Do not present any of these as resolved.**

---

## 14. Environment & reproducibility

| Item | Value |
|---|---|
| Python interpreter (approved, use this) | `C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe` |
| Python | 3.14.3 |
| Key packages | pandas 3.0.5 · numpy 2.5.3 · pyarrow 25.0.1 · pytest 9.1.1 · jupyterlab 4.6.3 · nbconvert 7.17.1 · openpyxl 3.1.5 |
| Package install | `nhs_rtt` installed **editable** into that venv (`pip install -e .`); `src/nhs_rtt.egg-info/` present (gitignored) |
| Dependency files | `requirements.txt` / `pyproject.toml` — **minimum bounds, not pins**; no lockfile (a hash-pinned lockfile is a later-phase item) |
| Run tests | `"C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe" -m pytest -q` → **98 passed** |
| Run a notebook | `"…python.exe" -m jupyter nbconvert --to notebook --execute --inplace notebooks/<nb>.ipynb` |
| Regenerate Phase 2 outputs | run `notebooks/02_semantics_grain_validation.ipynb`, or `nhs_rtt.semantics.run_phase2_analysis(df, source_path=RAW).write("outputs/phase2")` |
| Scratchpad for throwaway scripts | the session scratchpad dir (never write temp files into the project) |

**Raw files** (`data/raw/`, contents git-ignored; folder + `README.md` kept):

| File | Period | Bytes | SHA-256 |
|---|---|---|---|
| `rtt_2026_04.csv` | April 2026 | 81,624,872 | `0486aca5891a96af4f15e2f4559795138baef08b0ed580602b8c3a7aec6a56e9` |
| `rtt_2026_05.csv` | May 2026 | 80,032,366 | `fee364bc3654cf666f79d3485d26e2ada649a3418988a47aa1784e93294a5707` |
| `rtt_2026_06.csv` | June 2026 | 82,084,725 | `edc3927e4a0065855ad3b2347e7f82688e687b065406eefb49e2f67a9cd67f02` |

* **June was the analytical development / validation file for Phases 1–2.**
* **April and May were NOT analytically parsed** during Phase 2 (or its
  closures) — used only for immutability / hash checks. `src/nhs_rtt/__init__.py`
  has `DEV_MONTH = "2026-06"` (informational only; not read by code).
* **Phase 3 is where controlled multi-month ingestion begins.** Provenance for
  the raw files (source URL, download timestamp, NHS publication date, revision
  status) is **NOT SUPPLIED** — `docs/data_provenance.md` records only size +
  SHA-256; capturing the rest is Phase 3 work.

**Repository paths:**

| Area | Path(s) |
|---|---|
| Reusable source | `src/nhs_rtt/profile.py` (Phase 1 profiler + `classify_columns`, `check_week_bucket_sequence`), `src/nhs_rtt/semantics.py` (Phase 2 — see the API list below), `src/nhs_rtt/__init__.py` |
| Tests | `tests/test_profile.py` (47), `tests/test_semantics.py` (51), `tests/conftest.py` |
| Notebooks | `notebooks/01_data_discovery.ipynb`, `notebooks/02_semantics_grain_validation.ipynb` |
| Docs (current authority) | `docs/rtt_semantics.md`, `docs/rtt_grain_and_aggregation.md`, `docs/assumptions.md`, `docs/decisions.md` (D-000 … D-030), `docs/data_dictionary.md`, `docs/data_provenance.md`, `docs/project_charter.md` |
| Docs (audit trail) | `docs/phase1_audit.md`; `docs/phase2_independent_audit.md`, `docs/phase2_remediation_report.md`, `docs/phase2_closure_audit.md`, `docs/phase2_closure_remediation_report.md`, **`docs/phase2_final_closure_check.md`** (PASS); `docs/phase2_completion_report.md` (SUPERSEDED banner) |
| Raw data | `data/raw/rtt_2026_{04,05,06}.csv` + `data/raw/README.md` |
| Phase 1 generated outputs | `outputs/profiles/rtt_2026_06__*` (gitignored, regenerable) |
| Phase 2 generated outputs | `outputs/phase2/*.csv`, `outputs/phase2/facts.json` (gitignored, regenerable) |
| Codex audit evidence | `outputs/audit/**` (Phase 1) and `outputs/audit/phase2*/**` (Phase 2, closure, final) — **NOT currently gitignored; untracked**. Contains PDFs, PNGs, executed notebook copies, independent scripts + JSON. |
| Memory (Claude) | `.claude/projects/…/memory/` — `dev-dataset-june-2026.md`, `phase1-status.md`, `phase2-status.md`, `MEMORY.md` |

**`nhs_rtt.semantics` public API (Phase 2):** `load_rtt_csv`,
`validate_extract`, `expected_week_band_names`, `check_expected_band_schema`,
`week_band_columns`, `bands_up_to_weeks`, `parse_week_band`,
`observed_band_sum`, `reconciliation_summary`,
`reconciliation_coverage_by_part`, `reconciliation_mismatch_examples`,
`blank_zero_summary`, `candidate_key_report` (+ `CANDIDATE_KEY`),
`aggregate_vs_detail`, `treatment_function_rows`, `part_2a_subset_conformance`,
`nonc_prevalence`, `nonc_pathways_by_part`, `nonc_raw_cell_checksum`,
`nonc_summary`, `incomplete_within_18wk`, `same_month_totals_check`
(+ `JUNE_2026_SPN_UNESTIMATED`), `controlled_examples`, `run_phase2_analysis`
(+ `Phase2Outputs`), `assert_raw_unchanged`.

---

## 15. Git / repository state — FIRST ACTION for the next conversation

**Current state (inspect and confirm — do not assume):**

* Branch `master`, **zero commits**, **no remotes**. There is **no immutable
  historical milestone / commit baseline** — the earlier audits flagged this as
  a limitation (they could only compare against the working index).
* ~20 files are staged in the index; ~118 untracked (most of which is the
  `outputs/audit/**` Codex evidence tree, plus the Phase 2 docs / source /
  tests / notebook added after the last `git add`).
* `.gitignore` **does** exclude: `__pycache__/`, `*.egg-info/`, `.venv/`,
  `.pytest_cache/`, `.ipynb_checkpoints/`, `data/raw/*` (**raw NHS CSVs are
  safely excluded** — keep it that way), `outputs/profiles/*`,
  `outputs/phase2/*`, `outputs/figures/*`, `outputs/tables/*`; it **keeps**
  `!data/**/README.md`, `!data/**/.gitkeep`, `!outputs/**/.gitkeep`.
* `.gitignore` does **NOT** currently cover `outputs/audit/**` — an open
  decision for the milestone (track as evidence vs ignore as regenerable-ish).

**The immediate next action after this handover** is a **repository hygiene
inspection and creation of the accepted Phase 2 Git milestone, BEFORE Phase 3
begins.** Do **not** perform any Git commit / tag / push while producing this
handover or before user approval.

The next conversation must inspect: `git status`, history, branch, remotes,
tracked / untracked / ignored files, `.gitignore`, that raw NHS CSVs are
excluded, temp / cache / notebook-execution artefacts, generated outputs, audit
evidence, and documentation. It should then **propose** (for user approval):

* files to stage / exclude and any `.gitignore` changes (in particular:
  `outputs/audit/**`, `src/nhs_rtt.egg-info/`, executed-notebook churn);
* a commit message and an annotated tag;
* a push plan (there is no remote yet — decide whether to add one).

**Suggested naming (subject to inspection — use a better convention if the repo
suggests one):** commit `phase2: validate RTT semantics, grain and arithmetic`;
annotated tag `phase-2-pass`. A companion `phase-1-*` milestone/commit may also
be warranted since Phase 1 was never committed either.

**Obtain explicit user approval before any commit / tag / push.**

---

## 16. Phase 3 — describe only; DO NOT implement or design here

**Phase 3 = Reproducible Multi-Month Ingestion & Provenance.**

Its purpose is to turn "one validated month" into "a controlled, reproducible,
provenance-tracked pipeline over many months". Based only on the accepted
roadmap and the unresolved Phase 2 items, Phase 3 will *eventually* need to
address (not decided here):

* controlled ingestion of April, May, June and later months through the **§7
  105-band schema contract** and the **§6 K-2 key check, per file**;
* provenance capture per file: source URL, download timestamp, NHS publication
  date, SHA-256, **revision status** (P2-U3 / P2-U5 / `docs/data_provenance.md`);
* `Period` parsing and temporal alignment, preserving the **flow vs month-end
  stock** distinction;
* a **revised / re-released file policy** (which version wins; how a correction
  is represented);
* cross-month stability checks for schema, candidate key, and code↔name maps
  (P2-U3);
* deterministic processing and a manifest of what was ingested;
* **Parquet output only when the Phase 3 design actually calls for it** — not by
  default, not for portfolio breadth.

**Do not** design or implement Phase 3, and **do not** pre-decide any unresolved
implementation detail, in this handover. The order is: **Git milestone (§15) →
explicit Phase 3 planning → Phase 3 implementation.**

---

## 17. Freeze rules for the new conversation

### Frozen

Phase 1 and Phase 2 are **complete and independently accepted**.

* Do **not** reopen them because you would have implemented something
  differently.
* Do **not** refactor accepted code for style.
* Do **not** change an accepted analytical conclusion without **new material
  evidence**.
* Do **not** silently "clean" anomalous NHS source values (e.g. the `RTG`/`84H`
  `Part_2A > Part_2` rows) — preserve and flag.
* Do **not** turn the scoped K-1 zero-contribution convention into universal
  imputation, or fill raw missing values in the loaded frame.

### Reopening is allowed only if

* Phase 3 exposes a genuine **cross-month contradiction**;
* a **reproducibility test fails**;
* **new authoritative NHS documentation** materially changes an interpretation;
* a **concrete correctness defect** is discovered.

If reopening becomes necessary: (1) name the exact accepted decision affected;
(2) provide the evidence; (3) explain downstream consequences; (4) propose the
**smallest** corrective action; (5) get user approval **before** any broad
remediation.

---

## 18. Known inconsistency the next conversation should be aware of

* **Codex audit evidence (`outputs/audit/**`) is untracked and not
  `.gitignore`d.** It includes downloaded NHS PDFs/PNGs and executed
  notebook copies. The Phase 2 Git milestone must make a deliberate decision
  about it (track as evidence, or ignore) rather than sweeping it in by
  accident with `git add -A`.
* **No commits exist yet**, so every "byte-identical to saved outputs" audit
  claim was made against the working tree, not against committed history. The
  §15 milestone is what finally gives Phase 3 a real baseline to diff against.
* `docs/phase2_completion_report.md` and the first three Phase 2 audit/report
  docs contain **superseded** figures (e.g. "unknown-clock never blank for
  1A/1B", "exact sum of 23 rows on every column", the May-vs-June comparison,
  "102,482 NONC pathways"). They are retained as historical audit evidence and
  the completion report carries a "SUPERSEDED IN PART" banner. **Use
  `rtt_semantics.md`, `rtt_grain_and_aggregation.md`, `assumptions.md`,
  `decisions.md` and `phase2_final_closure_check.md` as the current authority.**
