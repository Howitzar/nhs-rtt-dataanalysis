# RTT dataset semantics (Phase 2)

> **Post-remediation (2026-09-07).** Updated after the independent Codex audit
> (`docs/phase2_independent_audit.md`, PASS WITH CHANGES). Key corrections:
> the completed-part unknown-clock column **is** blank on many rows
> (6,032 in Part_1A, 11,005 in Part_1B); "blank band ≡ zero" is stated only as
> a **scoped June arithmetic convention**, not a semantic equivalence; the
> same-month **June 2026** SPN is the benchmark (not a May comparison); and the
> documented `Part_2A` ⊆ `Part_2` rule has **two June count exceptions**
> (`RTG`/`84H`). See `docs/phase2_remediation_report.md`.

Scope: `data/raw/rtt_2026_06.csv` (NHS England RTT provider extract, period
`RTT-June-2026`). This document states what each field **means** and how the
values relate arithmetically, separating four evidence classes:

| Class | Meaning |
|---|---|
| **CONFIRMED — DOCS + DATA** | Explicit NHS England definition **and** demonstrated from the June CSV. |
| **CONFIRMED — DATA** | Strongly demonstrated from June; not found verbatim in authoritative guidance. |
| **DOCUMENTED — not fully testable** | Authoritative definition, but not directly checkable from this aggregate file. |
| **INFERRED** | Reasonable reading, supported only indirectly. |
| **UNRESOLVED** | Insufficient evidence. |

Analysis code: `src/nhs_rtt/semantics.py`. Reproducible run:
`notebooks/02_semantics_grain_validation.ipynb`. Compact result tables:
`outputs/phase2/`. Grain & aggregation safety: `docs/rtt_grain_and_aggregation.md`.

---

## 1. Sources

| # | Title | Version / date | URL | Accessed |
|---|---|---|---|---|
| S1 | Recording and reporting referral to treatment (RTT) waiting times for consultant-led elective care (NHS England, PRN01045) | v5.0, 11 Feb 2025 | https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2025/02/Recording-and-reporting-RTT-waiting-times-guidance-v5.0-Feb25.pdf | 2026-09-07 |
| S3 | Consultant-led Referral to Treatment Waiting Times Rules and Guidance (rules suite; distinct from S1, not a substitute for CSV mechanics) | ongoing | https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/rtt-guidance/ | 2026-09-07 |
| S4 | RTT Waiting Times statistical work area / 2026-27 data | 2026-27 | https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/rtt-data-2026-27/ | 2026-09-07 |
| **S5** | **RTT statistics user guidance** — "Reproducibility and derived measures" (within-18-weeks formula, `Commissioner Org Code <> NONC`, denominator, band selection); "Navigating published files" (NONC submission not mandatory); "Unknown clock starts" (completed pathways only) | ongoing | https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/rtt-statistics-user-guidance/ | 2026-09-07 |
| **S6** | **Statistical Press Notice — RTT waiting times data, June 2026** (Table 1 same-month **unestimated** England totals; page 1 estimate-inclusive headlines; non-submitting trusts RHQ, RA9) | published 13 Aug 2026 | https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2026/08/Jun26-RTT-statistical-press-notice-PDF-579K-6jPlxd.pdf | 2026-09-07 |
| S2 | Statistical Press Notice, May 2026 — genuine May facts only; **cannot** explain a June-vs-May residual (retained for context, not used as June evidence) | published 9 Jul 2026 | https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2026/07/May26-RTT-statistical-press-notice-PDF-574K-3jBgba.pdf | 2026-09-07 |

Claims below cite S1 sections (`§`) and S1 Annex B where relevant. **S1 does
not list the literal CSV code `C_999`** — its association with the treatment-
function "Total" is established from the June data (the literal
`Treatment Function Name = "Total"`).

---

## 2. RTT Part Type

The monthly aggregate return has five parts (S1 §10.1.1.2). Observed 1:1 with
`RTT Part Description`; row counts from June in brackets.

| Code | NHS definition (S1 §10.1.1.2, paraphrased) | June rows | Class |
|---|---|---|---|
| `Part_1A` | Completed pathways – **admitted**: RTT waited times for pathways that completed in the month **with** an inpatient/day-case admission. | 18,803 | CONFIRMED — DOCS + DATA |
| `Part_1B` | Completed pathways – **non-admitted**: pathways that completed in the month for reasons **other than** an admission. | 32,351 | CONFIRMED — DOCS + DATA |
| `Part_2` | **Incomplete** pathways: RTT waiting times so far for patients still waiting to start treatment at month-end; a snapshot on the last day of the period. | 63,355 | CONFIRMED — DOCS + DATA |
| `Part_2A` | Incomplete pathways **with a decision to admit (DTA)**: as Part_2, where a clinical decision to admit to a hospital bed has been made. | 30,548 | CONFIRMED — DOCS + DATA |
| `Part_3` | **New RTT periods**: number of new RTT periods (clock starts) during the month. | 37,354 | CONFIRMED — DOCS + DATA |

* "DTA" = **decision to admit** — S1 §10.1.1.2 / terminology ("Decision to
  admit … clinical decision … to admit the patient for … day case or inpatient
  treatment"). Resolves Phase 1 A-14. **CONFIRMED — DOCS.**
* `Part_2A` is a **subset** of `Part_2` (S1 Annex B: "The number of incomplete
  pathways with a decision to admit is a subset of the total number of
  incomplete pathways" / "Part 2A … should be less than or equal to Part 2").
  → Parts overlap: `Part_2` and `Part_2A` must **not** be summed. **DOCUMENTED**
  (patient-level membership is not testable here — no patient IDs).
  **A necessary count implication *is* testable**, and June has **two
  exceptions**: for provider `RTG` / commissioner `84H` / treatment function
  `C_502` (and the corresponding `C_999` roll-up), `Part_2A` Total All = **2**
  while `Part_2` Total All = **1**. These are a detail row and its total, not
  necessarily two independent source errors. This is a **data-quality
  exception**, not a refutation of the NHS rule; raw values are preserved and
  flagged (`part_2a_subset_conformance`, `outputs/phase2/part2a_subset_violations.csv`).
  Any subset-derived measure (e.g. Part_2 minus Part_2A) must validate
  `Part_2A <= Part_2` before use. Carried forward as **P2-U7**.
* The completed parts (1A/1B) count *pathways that stopped in the month*; the
  incomplete parts (2/2A) count *pathways still open at month-end*; Part_3
  counts *pathways that started in the month*. These are three different
  populations measured on three different event bases (S1 §10.1.1.2, §10.2.1).
  **CONFIRMED — DOCS.**

---

## 3. Waiting-time bands (105 columns)

**CONFIRMED — DOCS + DATA.**

* The columns `Gt 00 To 01 Weeks SUM 1` … `Gt 103 To 104 Weeks SUM 1` (104
  one-week bands) plus `Gt 104 Weeks SUM 1` (open-ended) — 105 in total. S1
  §10.1.7: "Data should be allocated to the following time bands: 0-1 weeks,
  >1-2 weeks, >2-3 weeks, then … through to >103-104 weeks, >104 weeks."
* S1 §10.1.1.3 states the **additional** bands (52-53 weeks up to 104+) were
  added to Parts 1A/1B/2/2A from April 2021; the weekly banding itself predates
  that. Empirically: every June `Part_3` row has **all 105 band cells blank**;
  every `Part_1A/1B/2/2A` row has ≥1 non-blank band. → **bands apply to
  1A/1B/2/2A only; not Part_3.**
* **Reported as mutually-exclusive bands**: NHS guidance allocates each pathway
  to one time band by days waited (S1 §10.1.7). The band sum reconciles exactly
  to `Total` / `Total All` (§4) with no residual, which is **consistent with**
  disjoint bands. Arithmetic consistency alone does not *prove* patient-level
  disjointness (an already-duplicated population can also sum consistently);
  the disjointness rests on the guidance, not on the reconciliation.
* **Interval inclusivity** (resolves Phase 1 A-17), S1 §10.1.7: bands are by
  **days waited** — "0 to 1 weeks includes patients … 0, 1, 2, 3, 4, 5, 6 and
  7 days"; "17 to 18 weeks includes … 120–126 days"; "104+ weeks includes …
  729 days and more". So "waited ≤ *k* weeks" = the bands with upper bound
  ≤ *k*, and **a wait of exactly 18 weeks (126 days) is in the 17-18 band**.
  `nhs_rtt.semantics.bands_up_to_weeks(cols, 18)` returns those 18 columns.
  **DOCUMENTED.**
* Applicability does **not** otherwise differ by part for 1A/1B/2/2A — the same
  105 columns are populated (sparsely) for all four. **CONFIRMED — DATA.**

Do **not** reshape these columns in Phase 2.

---

## 4. `Total`, `Patients with unknown clock start date`, `Total All`

`Total All` is never blank in June (min 1). The `Total` and unknown-clock
columns are **collected only for Parts 1A and 1B** (they are entirely blank for
Parts 2/2A/3 — §5). All values are non-negative integers (S1 Annex B).

**Cell population vs applicability (corrects the earlier "never blank" claim).**
Within the completed parts, the unknown-clock column *is* blank on many rows:

| Part | rows | unknown-clock **populated** | unknown-clock **blank** |
|---|---|---|---|
| `Part_1A` | 18,803 | 12,771 | 6,032 |
| `Part_1B` | 32,351 | 21,346 | 11,005 |

So a row belongs to exactly one of two subsets, and the arithmetic is tested
per subset (`outputs/phase2/reconciliation_by_part.csv`,
`reconciliation_coverage_by_part.csv`).

### 4.1 Unknown clock start date

**CONFIRMED — DOCS + DATA.** S1 §10.1.5: "in the unlikely event that the
provider may not be able to accurately identify the RTT clock start date,
patients can be reported … in the 'unknown clock start' column." S5 ("Unknown
clock starts") confines this to **completed** pathways ("less than 0.05% of
total completed pathways in 2025/26"). Such patients have no start date so
cannot be band-placed; empirically the count is an **additive** term to
`Total All` (§4.2).

### 4.2 Arithmetic model — per part, with explicit coverage and policy

Every identity below is exact-integer. A subset row is **evaluated** only when
*both* operands are non-`<NA>` after applying **only** the explicitly-authorised
zero-fill (a blank unknown-clock contribution under D-016, or skip-missing band
cells). Any row still carrying a missing **required** operand — a missing
`Total All`, a missing `Total`, or an entirely unobserved band distribution —
is **excluded and counted** (`n_missing_operand`), for *both* policies. An
unqualified `HOLDS` requires zero exclusions; otherwise the verdict is
`PARTIAL (…)`, `FAILS` or `n/a`. `missing-as-zero` rows additionally report
`n_convention_rows` (how many rows the authorised zero-fill touched) and are
labelled `HOLDS (missing-as-zero convention)`. Match counts come from an
explicit equality mask, never from `n_evaluated − n_mismatch`, so a missing
comparison cannot be silently credited as a match. See
`outputs/phase2/reconciliation_by_part.csv` — for June every `expected` check
is `HOLDS` / `HOLDS (missing-as-zero convention)` with `n_missing_operand = 0`.

**Part_1A / Part_1B (completed):**

| Check | policy | subset | June result | Class |
|---|---|---|---|---|
| `observed_bandsum == Total` | strict | all rows | HOLDS (18,803 / 32,351) | CONFIRMED — DATA |
| `Total + unknown == Total All` | strict | **unknown-populated** rows | HOLDS (12,771 / 21,346) | CONFIRMED — DATA |
| `Total == Total All` | strict | **unknown-blank** rows | HOLDS (6,032 / 11,005) | CONFIRMED — DATA |
| `Total + unknown(→0) == Total All` | missing-as-zero | all rows | HOLDS; convention applied to the 6,032 / 11,005 blank-unknown rows | CONFIRMED — DATA *under the stated convention* |

The two strict subsets are disjoint and partition the part (coverage table).
`observed_bandsum == Total All` therefore *fails* by exactly `−unknown` on the
71 / 235 rows with a positive unknown-clock count
(`outputs/phase2/mismatch_positive_unknown.csv`).

**Part_2 / Part_2A (incomplete snapshot):**

| Check | policy | subset | June result | Class |
|---|---|---|---|---|
| `observed_bandsum == Total All` | strict | all rows | HOLDS (63,355 / 30,548) | CONFIRMED — DATA |

`Total` and unknown-clock are not collected (100% blank), so no `Total`-based
identity applies.

**Part_3 (new RTT periods):** bands + `Total` + unknown all blank on every row;
`observed_bandsum` is `<NA>` (not `0`), so a strict `observed_bandsum ==
Total All` check evaluates **0** rows and is reported `PARTIAL (37,354
excluded)` — deliberately not "HOLDS". `Total All` is a standalone count of new
clock starts (S1 §10.1.1.2).

`observed_bandsum` is the **sum of the observed (non-missing) band cells** — a
skip-missing numerical convention. Because every banded June row has ≥1
observed band, it equals filling blanks with 0; that equality is a property of
June's population, **not** proof that a blank band encodes "zero patients"
(§5). NHS validates internal part totals (S1 Annex B "Incorrect totals in Part
1A/1B/2/2A/3") — documentary support that the parts *have* internal totals,
though S1 does not spell out the formulae.

Resolves Phase 1 A-02 (the three fields are **not** the same) and A-03 (the
band-sum relationship is **conditional on part**, and for completed parts is
`Σ observed bands + unknown` under the stated missing-as-zero policy).

### 4.3 What each field is

| Field | Meaning | Class |
|---|---|---|
| `Total All` | Pathway (not patient) count for the row: completed pathways (1A/1B), pathways open at month-end (2/2A), or new clock starts (3). The **June 2026** SPN Table 1 unestimated national totals — 7,147,562 incomplete; 318,650 admitted; 1,307,837 non-admitted; 1,930,912 new periods — reproduce exactly as sums of `Total All` by part, `Treatment Function Name = Total`, excluding `NONC` (`outputs/phase2/same_month_totals_check.csv`). | CONFIRMED — DOCS + DATA |
| `Total` (1A/1B only) | `= observed_bandsum` for every completed row; `Total All − Total = unknown`. The label "completed pathways with a known clock start" is a reasonable reading of §10.1.5 but not stated verbatim. | CONFIRMED — DATA (arithmetic); INFERRED (label) |
| unknown-clock (1A/1B only) | Completed pathways with no identifiable clock-start date; additive to `Total All`; not band-able. Blank on 6,032 / 11,005 rows (see 4.2). | CONFIRMED — DOCS + DATA |

---

## 5. Blank vs explicit zero — arithmetic compatibility, not semantic equivalence

**The distinction that matters:** an *arithmetic identity* ("the sum reconciles
if missing contributions are 0") is **not** a *semantic conclusion* ("a blank
means zero patients"). Phase 2 establishes only the former.

| Observation | What it establishes | What it does **not** establish |
|---|---|---|
| `Total`/unknown-clock **100% blank** on Parts 2/2A/3, **0% "all-blank"** on 1A/1B | Those columns are **not collected** for Parts 2/2A/3 (structural non-applicability). | — |
| **All 105 bands blank** on every Part_3 row (37,354/37,354) | Bands not collected for Part_3. | — |
| For the banded rows of 1A/1B/2/2A, the **sum of observed band cells** reconciles to `Total`/`Total All` with **zero residual**, with or without also filling blanks with 0; explicit `0` and blank band cells are freely mixed within a row (≈3,431 rows) | The stated **June arithmetic convention** "treat a missing band contribution as 0" reproduces the reported totals. Conditional on complete, correct totals and disjoint non-negative bands, a zero residual is *consistent with* zero missing contributions. | **Why** a publisher serialised a particular cell as blank rather than `0`; whether a blank could instead be unknown/withheld; whether this convention transfers to another return. S1 Annex B contains total/quality checks, **not** a cell-encoding rule. A provider returning zero after prior activity is a *data-quality trigger* in Annex B, not a diagnosis of non-reporting. |
| Missing **provider/commissioner/specialty combinations** (rows absent entirely) | nothing — absence is not observable as zero or as non-reporting from this file | non-reporting vs genuine zero (needs cross-month data — P2-U3) |

**Scoped decision (D-016, narrowed):** for the **June 2026 banded parts**, a
missing band contribution (and a missing unknown-clock contribution, §4.2) may
be treated **numerically as 0** for the reconciliations in this document. This
is an explicit, non-destructive computational convention on a per-calculation
basis — **not** a semantic rule, **not** global imputation, and **not**
automatically valid for future files. Raw missingness is preserved everywhere
(`load_rtt_csv` keeps blank as `<NA>`); any future transformation needs its own
documented policy, validation coverage, and an applicability mask. Phase 1
A-01 is **narrowed accordingly**, not "resolved".

---

## 6. `C_999` / "Total" treatment function

**Practical aggregation rule: CONFIRMED — DOCS + DATA. Evidence wording is
scoped below to what was actually observed.**

* S1 §10.1.4 lists 18 named treatment functions + `X02`–`X06` "Other …"
  groupers ("All other TREATMENT FUNCTIONS in the … group not reported
  individually") — 23 reported detail codes — and NHS validates that "the total
  is a sum over all treatment functions" (S1 Annex B). S1 does **not** name the
  literal CSV code `C_999`; its association with the "Total" is from the June
  label.
* `aggregate_vs_detail` compares, per `(Provider, Commissioner, RTT Part)`
  group, the `C_999` row against the **sum of the available non-C_999 rows from
  the 23-code set**, over 108 numeric columns, on the **union** of aggregate
  and detail groups (`outputs/phase2/facts.json → c999_aggregate_vs_detail`):
  * **40,636** groups, each with **exactly one** `C_999` row and **at least
    one** non-C_999 row; **0** aggregate-only or detail-only groups; **0**
    groups with a duplicate `C_999` row.
  * Detail rows per group range **1–23** (only **18** groups carry all 23;
    **20,518** groups carry just 1). "23 detail rows per group" is **not**
    generally true.
  * Of the 4,388,688 group-column comparisons: **2,872,115** have a numeric
    value on both sides with **0 mismatches**; **928,416** are blank on both
    sides; **588,157** are `C_999`-zero against an **all-missing** detail sum;
    **0** are "other-missing" (aggregate `<NA>` opposite a numeric detail).
    Under the stated **zero-contribution convention for missing cells** every
    group reconciles; under strict nullable equality the 588,157 are not
    observed numeric equalities.
* `aggregate_vs_detail` returns three flags of increasing strictness:
  `reconciles_numeric` (**diagnostic** — numeric/numeric cells only; can be
  `True` while an unacceptable `cmp_other_missing` state exists);
  `reconciles_missing_as_zero` (fill-all-missing-with-0 view); and
  **`acceptable`** — the policy-aware overall gate used by the Phase 2
  orchestration: no orphan groups, exactly one aggregate row per group, zero
  numeric mismatch, and **`cmp_other_missing == 0`** (only both-missing and
  `C_999`-zero-vs-all-missing-detail are tolerated). June: `acceptable = True`.
* **Practical rule (supported):** for a chosen provider/commissioner/period/part
  use **`C_999` alone**, *or* the reported non-C_999 rows alone —
  **never combine both** (adding one specialty duplicates that specialty's
  contribution; adding the whole detail set doubles the total).

`X02`–`X06` are reported leaf groupers within the 23-code set (they aggregate
lower-level treatment functions per S1 §10.1.4). Treat the 23 non-C_999 codes
as **the reported treatment-function analysis level**, not as proof of
clinically indivisible populations. Arithmetic consistency alone does not
establish patient-level disjointness. Phase 1 A-07 is **resolved** for the
aggregation rule; the disjointness caveat is noted.

---

## 7. Other aggregate / hierarchy structure

| Element | Finding | Class |
|---|---|---|
| `Provider Parent Org Code/Name` | A hierarchy **label** (ICB) carried on each provider-level detail row. No row observed where provider = its own parent; every row is one `Provider Org Code`. Its presence is a label, not an additional grain. | CONFIRMED — DATA |
| `Commissioner Parent Org Code/Name` | Same: a label on detail rows; blank on 10,263 rows (NONC / NHS-England-commissioned). **A `groupby` on this column defaults to `dropna=True` and silently drops those rows** — see `rtt_grain_and_aggregation.md` §4. | CONFIRMED — DATA |
| `Provider Org Code` values | 537 distinct ODS-style codes; **no sentinel string** ("TOTAL"/"ENG") was observed — absence of a sentinel is not proof no roll-up marker could exist. Independent-sector providers **are** in scope (S1 §10.1.1.1) and present (SpaMedica, Optegra). Resolves Phase 1 A-04 (not all providers are NHS trusts). | CONFIRMED — DOCS + DATA |
| Roll-up markers among the reported rows | **No additional treatment-function roll-up marker was identified** among the reported June treatment-function rows beyond `C_999`. This is "none observed", not a universal guarantee; `Part_2A` overlaps `Part_2`, and `X02`–`X06` are internally grouped categories. | CONFIRMED — DATA (as "none observed") |

Treat the 23 non-`C_999` treatment-function codes as **the reported analysis
level**, not as proof of indivisible clinical populations. The commissioner
data files NHS England publishes *do* contain sub-ICB / ICB / region / England
roll-ups (S6 "Further information"); the **provider extract used here does
not** — it is provider-level detail plus the `C_999` treatment-function total.
Any later join to a separate parent/organisation table must validate join
multiplicity (a many-to-one join that fans out will double-count).

---

## 8. `NONC` — non-English commissioner

**CONFIRMED — DOCS + DATA.**

* S1 §10.1.8 / §10.1.9.2: `NONC` is the commissioner code used **in the
  aggregate monthly RTT return** for pathways commissioned by non-English
  (e.g. Welsh, Scottish) commissioners — patients treated in England whose
  commissioner sits outside England. (Record-level WLMDS uses the specific
  code instead.) S1 Annex B lists `NONC` as a valid aggregate-return
  commissioner code.
* **Structural prevalence** (`nonc_prevalence`): **2,993 rows** (1.6% of rows),
  **119 providers**, all 24 treatment functions, all 5 parts. *No pathway total
  is quoted at this level* — summing `Total All` over all NONC rows
  double-counts `C_999` with its constituents and mixes RTT parts.
* **Pathway counts per RTT part**, using the `C_999` representation only
  (`nonc_pathways_by_part`, `outputs/phase2/nonc_pathways_by_part_c999.csv`):
  Part_1A **1,224**; Part_1B **4,478**; Part_2 **31,156**; Part_2A **7,734**;
  Part_3 **6,649**. **These five must not be summed** — different populations,
  and Part_2A ⊆ Part_2.
* The earlier figure **102,482** is reproducible as the raw `Total All` sum
  over all NONC rows but is an **uninterpreted checksum, not a pathway
  population** (`nonc_raw_cell_checksum`). Part_2's earlier "62,312" was
  exactly `2 × 31,156` (C_999 + its detail).
* **Analytical treatment:** keep `NONC` rows in the source/analytical
  representation; **exclude `Commissioner Org Code = NONC`** when reproducing
  England published performance (S5, "Reproducibility and derived measures").
  Excluding NONC changes the June "% within 18 weeks (Part_2 / Total)" from
  65.773% (incl.) to 65.826% (excl.) — a 0.053 pp move (NONC contributes
  16,735 / 31,156).
* **Coverage caveat (S5, "Navigating published files"):** NONC submission is
  **not mandatory** — "the data collection does not provide a complete picture
  of non-English commissioned pathways". So "keep NONC for total activity" is
  qualified: these rows are **not exhaustive** of non-English activity.

The blank-named commissioner codes `Y56`, `Y58`–`Y63` are consistent with
**NHS-England-commissioned** activity (S1 §10.1.10: specialised services,
offender health, armed forces). The `Y`-code meanings are not individually
verified — Phase 1 A-16 stays **INFERRED**.

---

## 9. Reproducing the published "% incomplete within 18 weeks" (same-month benchmark)

**Methodology + unestimated total: CONFIRMED — DOCS + DATA.
Exact estimate-inclusive headline: UNRESOLVED (P2-U1).**

Filter per **S5** ("Reproducibility and derived measures"): "the sum of
incomplete pathways in the 0-1 weeks to 17-18 weeks time bands … divided by the
total number of incomplete pathways", with `RTT Part Type = Part_2`,
`Treatment Function Name = Total`, `Commissioner Org Code <> NONC`, denominator
`Total All`. (S1 §10.1.7 fixes the band boundaries; a 126-day / 18-week wait is
in the 17-18 band.)

**Same-month benchmark — S6, June 2026 SPN Table 1, *not* including estimates
for missing acute trusts** (`outputs/phase2/same_month_totals_check.csv`):

| Measure | raw `rtt_2026_06.csv` | S6 Table 1 (unestimated) | match |
|---|---|---|---|
| Incomplete pathways total | 7,147,562 | 7,147,562 | ✅ |
| % incomplete within 18 weeks | 65.826% → **65.8%** | **65.8%** | ✅ (1 dp) |
| Completed admitted total | 318,650 | 318,650 | ✅ |
| Completed non-admitted total | 1,307,837 | 1,307,837 | ✅ |
| New RTT periods total | 1,930,912 | 1,930,912 | ✅ |

The raw file reproduces the **same-month unestimated** publication exactly.
The published **estimate-inclusive** headline (S6 page 1) additionally uplifts
for the two non-submitting trusts (RHQ, RA9); it also rounds to 65.8%, but
**matching rounding is not exact reproduction**. Implementing the
non-submitter estimate is **not** done here — see P2-U1. (The earlier May-2026
comparison is withdrawn: different months cannot explain a residual.)

---

## 10. Unresolved / carried forward

| ID | Question | Status after remediation |
|---|---|---|
| P2-U1 | Exact **estimate-inclusive** England headline (non-submitter uplift method). | UNRESOLVED. The June 2026 publication (S6) **is** available and its **unestimated** Table 1 totals reproduce exactly (§9). The uplift for RHQ/RA9 (S6 page 1, "RTT Overview Timeseries" method) is **not implemented**; do not claim exact estimate-inclusive reproduction until the estimate inputs are reconciled. |
| P2-U2 | Do incomplete pathways (2/2A) with an unknown clock start exist / get folded into a band? | UNRESOLVED. The separate unknown-clock field is unpopulated for 2/2A and S5 confines it to *completed* pathways. Neither that nor the zero residual proves such incomplete pathways are negligible or folded into a particular band — **the earlier "negligible / folded" inference is withdrawn.** Must be settled before any downstream use. |
| P2-U3 | Cross-month stability of code↔name maps and of the candidate key; handling of revised releases. | UNRESOLVED; **required** during multi-month ingestion. Validate on entry of each month; `Period` does not distinguish a revised file from the original. |
| P2-U4 | Provider organisational-type classification (NHS trust vs independent sector vs interface). | UNRESOLVED until the ODS `etr`/`ephp`/`ephpsite`/`ect` reference files (S1 §10.1.1.1 fn.19) are ingested. Do not infer organisation type from provider names. |
| P2-U5 | `Period` literal → calendar month-end; file-revision handling. | Part-specific temporal meaning **is** documented: 1A/1B/3 are within-month *flows*, 2/2A are month-end *stock*. Parsing the literal period and revision handling can be done during later ingestion; a single undifferentiated "month-end snapshot" reading would be wrong for the flow parts. |
| P2-U6 | Full per-band day ranges. | **Narrowed.** S1 §10.1.7 gives **five** worked examples (0-1, 1-2, 17-18, 51-52, 104+) and states the weekly sequence. Intermediate bounds are **derived, and labelled as derived**: ranged band `n`–`(n+1)` (n ≥ 1) covers days `7n+1 … 7(n+1)`; first band 0–7 days; final band ≥ 729 days. Not a blocker for later band-label work. |
| **P2-U7** | The `RTG` / `84H` `Part_2A > Part_2` count exception (§2). | Carried forward as a **data-quality issue**. Raw values preserved and flagged (`part_2a_subset_conformance`). Any measure relying on `Part_2A <= Part_2` (e.g. Part_2-minus-Part_2A) must validate the invariant per group before calculating. Publisher correction is not a prerequisite for honest acceptance. |
