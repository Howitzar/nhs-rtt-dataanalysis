# Phase 2 focused remediation closure audit

Date: 7 September 2026. Dataset: June 2026 only. Final verdict: **PASS WITH CHANGES**.

## A. Executive closure summary

The remediation substantially improves Phase 2, but the repository cannot yet be marked PASS. **Five original findings are CLOSED and five are PARTIALLY CLOSED.** The independently reproduced June figures remain sound; the remaining problems concern contradictory current documentation and validation acceptance, rather than changed June results.

Closed: **P2-A02, P2-A03, P2-A05, P2-A07, P2-A10**.

Partially closed: **P2-A01, P2-A04, P2-A06, P2-A08, P2-A09**. None is wholly OPEN: each has substantive remediation, but incomplete closure evidence.

The remaining work is focused:

1. Correct the active data dictionary's semantic `blank ≡ 0` statement and its assertion of 23 detail rows per group with exact equality on every numeric column.
2. Remove the active assumptions document's withdrawn May comparison and June-publication-unavailable statement.
3. Correct the new missing-as-zero reconciliation path: a missing `Total All` can be counted as a successful numeric comparison, and missing `Total`/entire distributions can be zero-filled without being counted as missing operands.
4. Enforce the agreed complete 105-band schema at the Phase 2 extract-validation boundary. Contiguity alone still accepts no bands, a single 5–6 band, or a missing first/open-ended band.

One newly introduced technical failure mechanism is recorded as **P2-R01 (HIGH)** and linked to P2-A04; it is not a separate unrelated audit topic. K-1 and K-2, **as formulated in the closure brief**, are acceptable policy decisions. Their approval does not certify the remaining implementation/documentation gaps.

This was a closure review of P2-A01–A10 and the declared remediation files, not a new broad audit. No fixes, production-test changes, raw changes, or Phase 3 work were implemented.

## B. Reproducibility results

### Inputs and scope

Reviewed the original `docs/phase2_independent_audit.md`, the attached closure brief, the remediation report, and the current versions of every declared remediation file: `src/nhs_rtt/semantics.py`, `tests/test_semantics.py`, the Phase 2 notebook, both semantics/grain documents, assumptions, decisions, data dictionary, the superseded completion report, and all current Phase 2 outputs. Also inspected both notebook sources and relevant dependency/status information for the requested regression/scope check.

The Downloads remediation report and `docs/phase2_remediation_report.md` are identical: SHA-256 `06da04ed5263882e5e0c6c9ba014d15dd8b4ab2a9cce7b5a2e3a9c0eea624162`. Its resolution labels were treated as claims, not closure evidence. The original completion report has an explicit supersession banner; its historical wording is not treated as active guidance. The contradictory data-dictionary and assumptions passages identified below have no equivalent withdrawal at the affected locations.

There is no immutable pre-remediation commit baseline established by this repository. Review therefore used the declared file list, current source, original audit evidence, targeted searches, and execution. No unstaged changes were reported for Phase 1 source/tests or dependency files relative to the index. This is a limited comparison, not proof of the complete editing history.

### Execution

Every Python execution used `C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe`; no environment or packages were created or installed.

| Check | Independently observed result |
|---|---|
| Full `python -m pytest -q` | **83 passed in 11.66 seconds**, 0 failed, 0 skipped |
| Test count | 47 Phase 1 + 36 Phase 2; Phase 2 classes contain 24 correctness, 2 immutability, 10 June-invariant tests |
| Phase 1 notebook | **0 errors**, 8 original code cells executed; 20.40 seconds |
| Phase 2 notebook | **0 errors**, 11 original code cells executed; 17.18 seconds |
| Phase 1 generated CSV comparison | All **9 CSVs** byte-identical to saved outputs |
| Phase 2 generated comparison | All **10 CSV/JSON files** byte-identical to saved outputs |
| Independent raw calculation | Completed in 3.92 seconds, no project analysis functions used |
| Raw hashes | All three files unchanged before/after the independent check and notebook execution; June matches the required historical hash |

Each notebook ran as an in-memory audit copy, with only its output-directory assignment redirected and one interpreter-identification cell added. Therefore executed code-cell totals including the audit cell are 9 and 12. Original notebook bytes remained unchanged. Phase 1 Markdown/manifest files were regenerated only in audit storage; the byte-comparison claim above is for the nine CSVs, not time-bearing Markdown. Existing project outputs were not overwritten.

The runtime emitted a Windows ZeroMQ selector-fallback warning and a local-kernel TCP-transport warning. Neither caused execution errors; no Windows configuration was changed. Initial new Python invocations encountered sandbox process denial and were rerun through approved escalation. No audit work remained blocked.

### Raw-file evidence

| File | SHA-256 before and after |
|---|---|
| April, hashed only | `0486aca5891a96af4f15e2f4559795138baef08b0ed580602b8c3a7aec6a56e9` |
| May, hashed only | `fee364bc3654cf666f79d3485d26e2ada649a3418988a47aa1784e93294a5707` |
| June | `edc3927e4a0065855ad3b2347e7f82688e687b065406eefb49e2f67a9cd67f02` |

April and May were not parsed or analyzed. Their hashes prove invariance during these closure checks; no earlier independent April/May baseline was found in the reviewed provenance records, so this audit does not independently prove their entire remediation-period history. June's historical expected hash does match.

No Phase 3 implementation was found in the inspected source, tests, notebooks or file inventory: no band reshaping, SQL/BI model, DuckDB or Parquet processing. Existing dependency declarations for potential later work are not new implementation. Phase 1's accepted findings were not reopened.

### Independently reproduced June evidence

The audit scanner uses strict `csv.reader`, explicit nullable integer parsing, counters and a union of C_999/detail groups. It includes Period in independent keys and subset/group comparisons. Missing distributions remain missing rather than becoming observed zero. The scanner verifies 182,411 rows, 121 columns and the exact 105-band header sequence as prerequisites to the requested calculations.

**Completed-path identities:**

| Part | Rows | Blank unknown | Populated unknown | Observed band sum = Total | Strict populated `Total + unknown = Total All` | Strict blank-unknown `Total = Total All` |
|---|---:|---:|---:|---:|---:|---:|
| Part_1A | 18,803 | 6,032 | 12,771 | 18,803 matches | 12,771 matches | 6,032 matches |
| Part_1B | 32,351 | 11,005 | 21,346 | 32,351 matches | 21,346 matches | 11,005 matches |

There are no mismatches in those declared subsets. All banded June rows have at least one observed band; all 37,354 Part_3 distributions are entirely missing. Applying zero contribution to blank unknown values extends the addition identity by convention; it does not establish their semantic meaning.

**NONC C_999 counts, separately by part:** Part_1A **1,224**; Part_1B **4,478**; Part_2 **31,156**; Part_2A **7,734**; Part_3 **6,649**. These are not summed into a unique population. The current outputs keep structural prevalence and the labeled 102,482 raw-cell checksum separate.

**Same-month benchmark:** with `Treatment Function Name = Total`, excluding `NONC`, the independent totals are **7,147,562 incomplete**, **318,650 admitted**, **1,307,837 non-admitted**, and **1,930,912 new periods**. The numerator is **4,704,942**, giving **65.8258298424%**, displayed as 65.826% and rounded to **65.8%** at publication precision. These agree with the previously retrieved and directly inspected June notice, Table 1: four exact counts and the rate at one decimal place. This is not exact reproduction of an estimate-inclusive rate. [June 2026 NHS statistical notice](https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2026/08/Jun26-RTT-statistical-press-notice-PDF-579K-6jPlxd.pdf).

**Subset conformance:** **30,548** Part_2A groups, all matched to Part_2; **30,546 conform**, **2 violate**. For `RTG / 84H / C_502` and `RTG / 84H / C_999`, each has Part_2A **2** and Part_2 **1**. The source values remain intact and the regenerated violation table reports both.

**C_999:** **40,636 groups**, each with exactly one aggregate and at least one detail row; no orphans or duplicate aggregates. Detail counts range **1–23**, with **20,518** one-detail groups and **18** groups containing all 23. All **4,388,688** group-column comparisons are accounted for: **2,872,115 numeric/numeric**, **928,416 both missing**, **588,157 aggregate-zero versus all-missing detail**; **0 numeric mismatches**, no other missingness state in June. The last two states are not observed numeric equalities.

**Key:** **182,411 unique five-column keys**, no duplicate groups and no missing/whitespace-only key rows. June's key is usable. **Nullable parent aggregation:** the correctly filtered Part_2 population contains **489** blank-parent rows contributing **131,509** pathways. Default grouping would retain **7,016,053**; explicit NA-preserving grouping conserves **7,147,562**. These directly confirm the revised grain document's example.

## C. P2-A01–P2-A10 closure table

Original severities are retained; closure status reflects the current repository, not the remediation report's labels.

| ID | Original severity | Closure status | Evidence | Residual risk | Further remediation required |
|---|---|---|---|---|---|
| **P2-A01** | HIGH | **PARTIALLY CLOSED** | D-016 and `rtt_semantics.md` §5 now distinguish arithmetic convention, semantic uncertainty, raw missingness, structural non-collection and future-file applicability. `observed_band_sum` uses `min_count=1`; the Part_3 example is missing. However, `docs/data_dictionary.md:53` still states **“Within a banded row, blank ≡ 0.”** | A material active field reference still authorizes the semantic equivalence that D-016 withdraws. The closure standard explicitly requires consistency throughout material documentation. | **YES** — replace this with the scoped June arithmetic policy and preserved semantic uncertainty. Also correct reconciliation behavior under P2-A04/R01. |
| **P2-A02** | HIGH | **CLOSED** | Independent counts and all strict identities match the table in §B. Current decisions, assumptions, semantics, dictionary and notebook acknowledge 6,032/11,005 blanks and state the separate missing-as-zero convention. No active claim that unknown-clock is never blank for completed parts was found; historical claims are explicitly superseded. | Meaning of blank unknown remains unresolved, correctly separated from arithmetic. Generic missing-operand implementation defects are tracked under A04, not a failure of these June counts. | **NO** |
| **P2-A03** | HIGH | **CLOSED** | Independent per-part NONC counts match. `nonc_prevalence` has no pathway total; the C_999 table says not to sum across parts; the 102,482 value is a clearly warned checksum. NONC remains retained, published-performance exclusions are scoped, optional submission is documented. | Observed NONC activity is incomplete coverage and must not become a claim about all non-English activity. This caveat is now explicit. | **NO** |
| **P2-A04** | HIGH | **PARTIALLY CLOSED** | Strict checks now expose subset/evaluated/excluded/match/mismatch counts and detect deliberately broken numeric values. Orphans and duplicate aggregate rows are reported and block aggregate booleans. Missingness comparison states are distinct. But the new missing-as-zero branch still overcounts evaluated matches and understates missing operands; see **P2-R01**. | A reported expected identity can say unqualified HOLDS despite an undefined comparison. `reconciles_numeric` is also only a diagnostic for numeric/numeric cells: an aggregate missing opposite detail 9 yields True with `cmp_other_missing=1`, while `reconciles_missing_as_zero=False`. It must not be used alone as a full acceptance flag. | **YES** — resolve R01, retain coverage checks, and make acceptance depend on explicit allowed missingness states plus structural coverage, not the numeric diagnostic alone. |
| **P2-A05** | HIGH | **CLOSED** | Independent reproduction gives 30,548/30,546/2 and the exact RTG/84H detail/total exceptions. D-022, semantics, grain guidance, tests, notebook and violation output preserve and flag them; subset-derived calculations are instructed to validate first. | Source-data exceptions remain. The helper is currently scoped to a single-period file; multi-month use requires Period-aware checks during future ingestion. Neither warrants changing source counts. | **NO** for Phase 2; carry P2-U7 safely. |
| **P2-A06** | MEDIUM | **PARTIALLY CLOSED** | The implementation, notebook, D-023 and main semantics document correctly use the same-month unestimated June benchmark. Independent values match. However, `docs/assumptions.md:122–126` still recommends a comparison with May 65.6% and states the June sources were unavailable. | Active next-step guidance contradicts the corrected benchmark and availability record. No estimated-headline implementation is needed to fix this. | **YES** — update the final recommended-next-validation paragraph; distinguish matched unestimated counts/rate precision from deferred estimate-inclusive uplift. |
| **P2-A07** | MEDIUM | **CLOSED** | Grain guidance explicitly uses `dropna=False`, count conservation, one part/one TFC representation, and join-multiplicity checks. Independent 489-row/131,509 loss matches. Claims about detail categories and patient disjointness have been narrowed. | Future joins and monthly flow/stock aggregation still need their stated safeguards. Arithmetic reconciliation is not patient-level proof; current guidance says so. | **NO** |
| **P2-A08** | MEDIUM | **PARTIALLY CLOSED** | Revised function/output, semantics, decisions and notebook report all C_999 group/missingness states accurately, independently reproduced in §B. Yet `docs/data_dictionary.md:87–89` still calls C_999 the **“exact sum of the 23 detail rows on every numeric column”** for every group. | The dictionary still suppresses variable detail coverage and missingness normalization. The safe use-C_999-OR-detail rule itself remains correct. | **YES** — synchronize the dictionary with the verified 1–23 available-row and comparison-state description. |
| **P2-A09** | MEDIUM | **PARTIALLY CLOSED** | Duplicate headers are rejected before mangling; missing required key/measure columns fail; literal NULL and leading-zero identifier 001 survive. Missing requested key returns `is_unique=None`; missing key cell gives `usable=False`. But `validate_extract` and the default loader accept zero bands, a single 5–6 band, missing 0–1, and missing 104+. | The promised expected band-schema gate is still a contiguity check. A truncated extract can be labeled valid. Tests using miniature clean sequences do not establish the production schema contract. | **YES** — enforce the agreed 105-band expected bounds/order/open end at the Phase 2 validation boundary, with focused endpoint/empty/truncated regressions. Keep generic Phase 1 detection separate. |
| **P2-A10** | LOW | **CLOSED** | Curated examples now include positive unknown, blank completed unknown, RTG/84H violations, and Part_3 with missing observed band sum. Key-drop comments are corrected; reported test/class counts agree with collection. | Class membership is not identical to evidence type: `test_controlled_examples_shape` is in the correctness class but uses real June data. Tests remain regression evidence rather than independent proof. Additional A04/A09 regressions are required with those fixes, not for test-count padding. | **NO** as a standalone finding. |

### Focused validator falsification details

Saved inputs and complete results: `outputs/audit/phase2_closure/fixtures/` and `probes.json`.

**Extract gate:** a synthetic fixture with the required key/measure columns and all expected bands loads correctly, preserving commissioner `NULL` and provider `001`. Deleting all 105 bands still returns `ok=True`, `n_week_bands=0` and loads. Keeping only 5–6 does the same with one band. Removing 0–1 or 104+ passes with 104 bands. Removing an interior band is correctly rejected. Duplicate raw Period and missing Period/Total All are correctly rejected. The failure is specifically expected-schema completeness, not duplicate-header or lexical-NA handling.

**Strict reconciliation:** a 0-versus-9 total produces FAILS. Missing Total or an entirely missing distribution produces PARTIAL for the affected strict check. Strict coverage reporting is materially improved.

**Aggregate comparison:** independent synthetic cases confirm numeric mismatch rejection, aggregate-only and detail-only detection, duplicate-aggregate rejection, distinct both-missing and aggregate-zero/all-missing states. A missing aggregate opposite numeric detail is exposed as `cmp_other_missing`; it is not treated as a numeric mismatch because it is not numeric on both sides. Consequently the numeric-only flag can be True with no numeric comparisons. That naming/definition is explicit in the function, but acceptance must inspect the other diagnostics or use a policy-aware acceptance result. June has no `cmp_other_missing` comparisons.

## D. New remediation finding

### P2-R01 — New missing-as-zero reconciliation path can certify undefined comparisons

- **Severity:** HIGH.
- **Evidence:** `src/nhs_rtt/semantics.py:308–318` sets the evaluation mask to the entire subset for `policy="missing-as-zero"`, without ensuring both resulting operands are numeric. The callers at lines 385–393 pass unfilled `Total All` as the right-hand side and count only `U.isna()` as missing. In a two-row completed-path fixture with numeric bands/Total/unknown equal to zero, `Total All=0` on row one and missing on row two, the two convention checks report **n_in_subset=2, n_evaluated=2, n_match=2, n_missing_operand=0, n_excluded_missing=0, verdict=HOLDS**. Only one numerical comparison exists. Nullable `(difference != 0).sum()` ignores the missing comparison, and `n_match=n_evaluated-n_mismatch` credits it as a match. The parallel strict check correctly reports one excluded row, so the result table contradicts itself. When every Total All operand is missing, the same path raises a `TypeError` when converting a missing minimum to float. Missing Total and all-missing bands are also zero-filled at lines 365–366 without being included in the supplied missing-operand mask, permitting unqualified HOLDS on those convention checks.
- **Why it matters:** This is a new implementation of the original A04 failure mode: invalid/unexplained operands can be represented as fully evaluated matches. It defeats the remediation's central coverage guarantee and exceeds K-1, which permits scoped missing-band/unknown contributions, not silent acceptance of missing reported totals. June's present Total All values mean this does not change the reproduced June figures.
- **Required remediation:** Validate all operands after the explicitly authorized convention is applied; missing reported Total All must remain an exclusion/failure, never a match. Do not silently extend the policy to missing Total or an entirely unobserved distribution. Count every relevant missing operand, compute matches from actual numeric equalities, and handle zero evaluated rows without a numeric conversion error. Add focused one-good/one-missing and all-missing-operand regressions; retain the strict checks and their coverage assertions. No imputation of raw values is required.
- **Blocking final Phase 2 PASS?:** **YES**. This is the residual technical reason P2-A04 remains partially closed; it is not counted as an unrelated extra audit scope.

No other separately scoped new HIGH/CRITICAL issue was established. The expected-band-schema failure is an unresolved part of original A09; the dictionary/assumptions contradictions are unresolved original findings.

## E. K-1 recommendation

**APPROVE** the decision exactly as formulated in the closure brief: a scoped numerical zero-contribution convention for independently validated June calculations, with raw missingness preserved and no universal semantic blank=zero claim.

D-016 now states an acceptable policy. This approval does not approve the contradictory dictionary wording or R01's missing-operand handling; both must be corrected before overall PASS. It does not authorize global filling, treating absent rows as zero, or automatic transfer to future files.

## F. K-2 recommendation

**APPROVE** the five-column candidate natural key conditionally on all requested columns present, no missing key cells, uniqueness for each incoming file, and explicit revised-release handling.

June satisfies the key conditions. The revised key helper correctly distinguishes diagnostic uniqueness from usability when columns/cells are missing. The key is neither NHS-guaranteed nor a patient identifier. Revised-release handling is a requirement before multi-file use, not something Phase 2 must implement now. This key-policy approval does not close A09's separate expected-band-schema gap or certify the entire loader as an acceptance gate.

## G. Remaining unresolved items and destination phase

| Item | Closure assessment and destination |
|---|---|
| **P2-U1** estimate-inclusive national uplift | Safe to carry into later methodology/metric work. Implement and reconcile estimate inputs before claiming an exact estimate-inclusive national result. Correct the stale assumptions paragraph now under A06; the uplift itself is not a Phase 2 blocker. |
| **P2-U2** unknown-clock incomplete pathways | Legitimately unresolved. Retain the withdrawn-inference wording. Resolve before any downstream claim or transformation specifically relying on their supposed absence, negligibility or placement into a band; it need not block all unrelated Phase 3 work. |
| **P2-U3** cross-month schema/key/code mappings and revised releases | Required during Phase 3 multi-month ingestion, before accepting additional files or treating mappings as stable. Do not use deferral to excuse the already-promised single-file band-schema gate in A09. |
| **P2-U4** provider organisational classification | Safe to defer to reference-data work. Required before NHS-trust-only or organisation-type analysis. No type inference from names. |
| **P2-U5** Period parsing, temporal alignment and revision handling | Required during later ingestion. Preserve the documented distinction between monthly flows and month-end stock; define revised-file replacement/version selection before combining releases. |
| **P2-U6** full band day ranges | Safely narrowed. Preserve the five documented examples, first/open-ended exceptions and label intermediate bounds as derived. Implement/test those labels when later band metadata is built; no Phase 2 blocker. |
| **P2-U7** RTG/84H subset exception | Safe to carry as flagged source quality. Preserve the values and require conformance checks before subset-derived calculations; do not cap counts or demand publisher correction as a prerequisite to acceptance. |

These uncertainties are appropriately bounded for later work. None requires starting Phase 3 to complete this closure. The outstanding Phase 2 blockers are the findings already identified above.

## H. Final Phase 2 verdict

**PASS WITH CHANGES**

The June calculations, notebook reproducibility, raw immutability and corrected NONC/subset evidence are accepted. Phase 2 cannot yet be frozen as PASS because HIGH findings A01 and A04 remain partially closed, R01 demonstrates an unsafe validation result, and the expected-schema gate remains incomplete. Correct those technical gaps and synchronize the three active documentation passages, then perform a narrow follow-up on the residuals.

Audit additions only: this report and `outputs/audit/phase2_closure/` containing the independent scanner/probes, synthetic fixtures, JSON evidence, workspace-local kernel specification, executed notebook copies and redirected output files. Existing source, tests, notebooks, raw data and project outputs were not modified. **No fixes were implemented. Phase 3 was not begun.**
