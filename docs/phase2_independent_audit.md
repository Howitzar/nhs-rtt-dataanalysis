# Independent Phase 2 audit

**Recommendation: PASS WITH CHANGES**

Audit date: 7 September 2026. Scope: dataset semantics, grain and arithmetic validation, using June 2026 only. Phase 1 remains accepted. No implementation remediation or Phase 3 work was performed.

## A. Executive audit summary

The core June arithmetic, candidate-key uniqueness, C_999 numerical reconciliation and within-18-week calculation independently reproduce. The notebook executes, all 71 tests pass, and regenerated Phase 2 outputs match the saved outputs byte for byte. This is a useful analytical foundation, not a failed project.

Phase 2 cannot yet be frozen as PASS. Its interpretation of blanks is stronger than its evidence; the completed-part unknown-clock missingness narrative is factually wrong; NONC counts double-count totals/detail and combine incompatible parts; and the validation helpers can report success after omitting problematic data. There is also a previously undisclosed June count inconsistency with the documented Part_2A subset relationship.

The required work is focused corrections to validation and evidence wording, not rebuilding the pipeline or adding technologies. The tests and layered notebook are appropriate junior analyst portfolio work; the main learning gap is distinguishing an arithmetic identity from a semantic conclusion and implementing that distinction consistently.

## B. Commands/checks performed

All project Python execution used `C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe` (3.14.3). Commands below were run from the repository root in PowerShell:

```powershell
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' -m pytest -q
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase2/independent_check.py
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase2/execute_notebook.py
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase2/adversarial_probes.py
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase2/aggregation_examples.py
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase2/read_sources.py
Get-FileHash data/raw/rtt_2026_06.csv -Algorithm SHA256
git diff --stat
git diff -- notebooks/01_data_discovery.ipynb
git diff --name-only -- src/nhs_rtt/profile.py tests/test_profile.py tests/conftest.py pyproject.toml requirements.txt
git log -4 --oneline
git status --short
```

Results:

- **71 passed in 9.16 seconds**, no failures/skips: 47 Phase 1 and 24 Phase 2. The actual Phase 2 split is **13 code-correctness, 2 immutability, 9 June-invariant tests**, not the completion report's 15/2/7 split.
- June is present: 182,411 rows, 121 columns, the exact 105-band header sequence, non-negative integer values where populated. Independent scan: 7.85 seconds.
- SHA-256 before/after independent scan and notebook: **`edc3927e4a0065855ad3b2347e7f82688e687b065406eefb49e2f67a9cd67f02`**. A final PowerShell hash agrees.
- Notebook: **zero errors**, 10 original code cells plus one audit interpreter-identification cell; 14.13 seconds. The in-memory audit copy redirects only `OUT` into audit storage. A workspace-local kernel specification points explicitly to the approved interpreter. Original notebook and output files were not overwritten. All seven generated CSV/JSON files reproduce byte for byte. Two runtime warnings concerned Windows event-loop fallback and local kernel transport; execution completed normally. No Windows configuration was changed.
- The Phase 1 notebook differs from the staged version only in execution timestamps and the displayed profile generation timestamp. Phase 1 source/tests and dependency files have no unstaged differences. The repository has **no commits**, so the index is a comparison reference, not a proven immutable historical milestone.
- The supplied Downloads report and repository report have identical SHA-256 values. The reviewed notebook source, stored outputs, source modules, tests, requested docs, dependency files, `.gitignore`, and generated tables are consistent with one June analysis. No April/May production ingestion, band reshaping, Parquet, DuckDB, SQL, dimensional model, Power BI, or final KPI layer was found. Local fill/skip-NA arithmetic exists, but no global raw/dataframe blank-to-zero rewrite was found. April/May CSVs were not read by this audit.

The independent scanner uses `csv.reader(strict=True)`, explicit integer conversion, counters and dictionaries; it imports **no project functions**. It retains missing values separately and labels the sums of observed cells. Synthetic probes deliberately call project functions to expose false-positive results. The aggregation-examples check independently loads only necessary raw columns as strings.

Source retrieval: initial web requests returned NHS verification pages; a sandboxed download failed with socket permissions. Approved `Invoke-WebRequest -Uri <source URL> -OutFile outputs/audit/phase2/<filename>` successfully downloaded the sources linked in section J. PDFs were extracted using the approved interpreter with the already-bundled pure-Python pypdf library on its search path; no packages or environments were installed. Poppler rendered guidance page 46, Annex B pages 64–66, and June notice page 7 for visual verification.

## C. Findings ordered by severity

### P2-A01 — Arithmetic equivalence is presented as semantic equivalence

- **Severity:** HIGH
- **Category:** Missing-value semantics / evidence classification
- **Evidence:** `semantics.py:211` uses pandas sums with default `skipna=True` in both branches of `band_sum`; `min_count=1` changes only the all-missing case. All four banded parts have at least one nonblank band per row, so equal results from the two branches are inevitable, independent of what missing values mean. `docs/rtt_semantics.md:156`, D-016 and the report promote this to “no patients in this band.” The cited Annex B contains total/quality checks, not an explicit blank-cell encoding rule. Mixed zero/blank rows number 3,431, but coexistence does not explain the encoding. A previously active provider returning zero is a data-quality trigger in Annex B, not proof of non-reporting.
- **Why it matters:** This could authorize unjustified imputation and conceal unknown/non-reporting values in future data. Retaining `<NA>` in the input does not make skip-NA arithmetic semantically neutral.
- **Required remediation:** Narrow D-016 to an explicitly scoped **June arithmetic convention**: observed-cell sums reconcile to reported totals when missing contributions are zero. Preserve missingness; retain semantic meaning as unresolved unless explicit source evidence is obtained. Remove claims that skip-NA versus fill-zero is independent proof, and that a quality trigger diagnoses non-reporting.
- **Blocking Phase 2 PASS?:** YES

### P2-A02 — Completed-part unknown-clock blanks are incorrectly described

- **Severity:** HIGH
- **Category:** Empirical correctness / arithmetic applicability
- **Evidence:** `docs/rtt_semantics.md:154`, the notebook reading section and completion report §§C/G claim unknown-clock is never blank for 1A/1B. Independent raw counts are **6,032 blanks in Part_1A and 11,005 in Part_1B**. The generated `blank_zero_by_part.csv` already reports these correctly. For example, J2H6H / 06Q / Part_1A / C_130 has Total=5, unknown blank, Total All=5. `Total + unknown` under nullable arithmetic is undefined there. The both-present identities cover only **12,771 and 21,346** rows respectively; extending to all completed rows uses a zero-contribution convention.
- **Why it matters:** The stated 0% versus 100% missingness distinction is false and hides a second use of missing-as-zero, outside the stated band-only decision.
- **Required remediation:** Correct the report, semantics docs, assumptions/decisions and notebook. Separate applicability from cell population; document both-present coverage and the blank-unknown convention explicitly. Add a regression covering the real blank counts and a completed row with blank unknown.
- **Blocking Phase 2 PASS?:** YES

### P2-A03 — NONC “pathways” are double-counted and mixed across parts

- **Severity:** HIGH
- **Category:** Aggregation correctness
- **Evidence:** `semantics.py:476–487` sums Total All over all TFCs and parts. **102,482 is reproducible as a raw-cell sum, not a defensible pathway total.** Every part includes C_999 and its detail constituents. For Part_2 the reported 62,312 is exactly twice **31,156** using C_999 alone. Non-overlapping TFC representation gives per-part NONC counts: 1A **1,224**; 1B **4,478**; 2 **31,156**; 2A **7,734**; 3 **6,649**. Adding those five is still not a unique population. `test_nonc_summary` itself adds a completed and incomplete count; the June regression locks the misleading 102,482 label.
- **Why it matters:** The project violates its own most important double-counting rules in a published result and passing tests.
- **Required remediation:** Report raw row prevalence separately from pathway counts. Calculate counts per RTT part using either C_999 or detail, never both. Remove the cross-part pathway total, or label it strictly as an uninterpreted raw-cell checksum. Correct outputs, docs and tests. Retain NONC; do not delete it as remediation.
- **Blocking Phase 2 PASS?:** YES

### P2-A04 — Reconciliation can pass after losing coverage or hiding structural defects

- **Severity:** HIGH
- **Category:** Validation implementation
- **Evidence:** `aggregate_vs_detail` at `semantics.py:441–447` sums duplicate aggregate rows, inner-joins aggregate/detail groups and fills nulls with zero. Synthetic probes return `reconciles=True` for: one matched group plus an aggregate-only and a detail-only group; two aggregate rows summing to one detail row; and a missing aggregate value opposite explicit zero. `_compare` at line 193 drops missing operands; a synthetic two-row Part_2 input with one entirely missing row reports the expected identity HOLDS over the one remaining row. No excluded-row or group-coverage failure is emitted.
- **Why it matters:** Passing these helpers does not establish the claimed all-row/all-group validation contract. June's coverage happens to be complete, as established independently, but the helpers are unsafe as acceptance checks.
- **Required remediation:** Report expected, evaluated and excluded coverage separately; compare group unions and report orphan groups; require one aggregate row per group; distinguish missing/missing and missing/zero from numerical equality. Make the arithmetic missingness policy explicit. Add focused counterexample regressions and ensure the orchestration rejects unexplained coverage failures.
- **Blocking Phase 2 PASS?:** YES

### P2-A05 — A testable June implication of the subset rule was not checked

- **Severity:** HIGH
- **Category:** Dataset-quality exception / semantic validation
- **Evidence:** NHS guidance Annex B documents Part_2A as a subset of Part_2 and checks its count does not exceed Part_2. Patient membership is not testable here, but a necessary count implication is. All 30,548 Part_2A rows have matching Part_2 keys. **Two exceed Part_2:** RTG / 84H / C_502 and RTG / 84H / C_999, each **2 versus 1**, in RTT-June-2026. These are a detail and corresponding total manifestation, not necessarily two independent source errors. Phase 2 calls the relationship “not row-testable” and does not surface this exception.
- **Why it matters:** A documented population rule and its actual data conformance have been conflated. Unqualified downstream subset-derived subtraction or percentages could be invalid.
- **Required remediation:** Add the necessary numerical check; preserve these exceptions and distinguish the documented rule from June conformance. Record an explicit acceptance/handling decision before Phase 3 uses subset-based calculations. Do not change the raw counts or reverse the documented subset rule to fit the data.
- **Blocking Phase 2 PASS?:** YES, until the exception is surfaced and disposition documented; publisher correction is not a prerequisite for honest acceptance.

### P2-A06 — Cross-month comparison cannot explain the residual

- **Severity:** MEDIUM
- **Category:** Published benchmark / source attribution
- **Evidence:** `docs/rtt_semantics.md:258` treats June raw 65.83% versus May published 65.6% as methodological validation and attributes the gap to non-submitter estimates. Different months prevent that attribution. The June notice, published **13 August 2026**, is available from the cited index. Its table 1, page 7, reports unestimated June totals **7,147,562 incomplete, 318,650 admitted, 1,307,837 non-admitted and 1,930,912 new periods**; all match independent raw aggregation excluding NONC and using C_999. Its rounded unestimated incomplete performance is **65.8%**. The estimate-inclusive June headline is also 65.8% to one decimal; matching rounding does not establish exact estimate-inclusive reproduction.
- **Why it matters:** A plausible percentage is not a validation, and an unexplained difference cannot be assigned a cause. The stated source-unavailability reason is outdated/incorrect at the dated audit/report milestone.
- **Required remediation:** Use the same-month, same-scope table as the benchmark. Cite official statistical user guidance for the precise CSV filters/formula. Keep exact estimate-inclusive replication separate and unresolved until its inputs are actually reconciled. Update P2-U1's availability statement.
- **Blocking Phase 2 PASS?:** YES for the erroneous claims; implementing non-submitter estimation is not required here.

### P2-A07 — Aggregation instructions can lose rows and overstate disjointness

- **Severity:** MEDIUM
- **Category:** Analyst guidance / hierarchy assumptions
- **Evidence:** `docs/rtt_grain_and_aggregation.md:104` says a groupby produces an NA bucket. Pandas defaults to `dropna=True`. On June Part_2/C_999 excluding NONC, grouping nullable commissioner parent by default loses **489 rows / 131,509 pathways**: 7,147,562 becomes **7,016,053**. `dropna=False` preserves the total. Blanket “no other aggregate row type” and “everything else is disjoint detail” claims exceed sentinel inspection; Part_2A overlaps Part_2 and guidance §10.1.4 describes internally grouped specialty categories. Arithmetic equality cannot prove no overlap: an already duplicated underlying population can sum consistently. The bad-join warning blames retaining a parent label, rather than join multiplicity.
- **Why it matters:** A junior analyst following the text literally can silently discard data or assume uniqueness/disjointness that was not established.
- **Required remediation:** Show explicit NA-preserving grouping and count-conservation checks; use unknown parent labels without inventing commissioning meanings. Scope “detail” to the reported TFC level and a selected part/period. Describe absence of observed additional roll-up markers, not a universal guarantee. Explain many-to-one join validation and that monthly flow sums count events, not necessarily distinct people/pathways.
- **Blocking Phase 2 PASS?:** YES

### P2-A08 — C_999 reconciliation wording suppresses missing-value and coverage details

- **Severity:** MEDIUM
- **Category:** Empirical reporting
- **Evidence:** Independent union-of-groups comparison confirms **40,636 groups**, exactly one aggregate and at least one detail row each, with **zero numerical mismatches under zero contribution for missing cells**. But **588,157 cells** compare aggregate zero against an all-missing detail sum. There are 928,416 both-missing comparisons, not measured numeric equalities. Detail rows per group range **1–23**; **20,518 groups have one**, and only **18 groups have all 23**. The completion report describes all 108 columns as exact matches and repeatedly implies 23 rows per group without stating this normalization/sparsity.
- **Why it matters:** Readers can mistake missingness normalization for observed equality and absent rows for observed zero rows.
- **Required remediation:** State “sum of available non-C_999 rows from the 23-code set, with the stated zero-contribution policy.” Report missingness states and group coverage. Preserve the sound rule: do not combine C_999 with its constituents. Adding one specialty duplicates that specialty's contribution; adding the entire detail set doubles the total, not every partial combination.
- **Blocking Phase 2 PASS?:** YES for evidence wording; the C_999 exclusion rule itself is supported.

### P2-A09 — Loader/key helpers are not sufficient future-file acceptance checks

- **Severity:** MEDIUM
- **Category:** Input validation / key contract
- **Evidence:** `load_rtt_csv` at `semantics.py:144–149` uses pandas default NA parsing and header mangling, bypassing Phase 1 duplicate-header detection. A probe silently changes duplicate Provider Org Code headers to `Provider Org Code` and `.1`, and turns literal commissioner `NULL` into missing. Empty band sets and a single 5–6 band pass `week_band_columns`. `candidate_key_report` at line 407 removes absent requested columns and can return `is_unique=True` despite missing Period. June has none of these structural failures; the issue concerns claiming reusable validation. Numeric-looking `001` remains a string, which is correct.
- **Why it matters:** A uniqueness boolean alone can certify the wrong key, while malformed/missing input columns can silently change semantics.
- **Required remediation:** Enforce required key/measure columns and nonmissing key values at the analysis entry point; validate raw headers before pandas mangles them; explicitly define lexical NA tokens; enforce a named expected band-schema contract where completeness is required. These are small checks around the existing loader, not a new ingestion platform. Treat the key report as diagnostic unless all preconditions pass.
- **Blocking Phase 2 PASS?:** YES for the proposed acceptance contract; no need to generalize beyond the agreed extract format.

### P2-A10 — Examples and test descriptions overstate what they demonstrate

- **Severity:** LOW
- **Category:** Test quality / portfolio clarity
- **Evidence:** The controlled example selects R1H/A3A8R and X02/C_999; its completed unknown values are all zero, so it does not illustrate the positive or blank unknown cases. The mismatch file does preserve positive unknown examples for both completed parts. Incomplete examples label `Total(+unknown)=TotalAll` after substituting band sum for missing Total; Part_3 displays a zero band sum although all bands are blank. The candidate-key test comment claims dropping TFC, but the actual reduced key drops commissioner. The report's test group counts are wrong (13/2/9 actual). Its 60–70% June rate assertion is a broad smoke test. The core counterexamples in A01–A09 are not covered by the existing tests.
- **Why it matters:** Passing tests and illustrative rows are being credited with stronger validation than they provide.
- **Required remediation:** Add focused regressions with the substantive fixes; include blank/positive unknown and the discovered subset exception in controlled evidence; label substituted arithmetic honestly; correct the test descriptions. Do not increase test count merely for coverage statistics.
- **Blocking Phase 2 PASS?:** NO as a standalone finding; regressions for A01–A09 are part of their closure.

## D. Independent arithmetic results

Define **S** as the sum of the observed nonblank band cells. This is an explicit skip-missing numerical convention, not proof of missing-value meaning. No observed row was filtered out of the independent scan. All banded rows have at least one observed band; all Total All cells are populated.

- **Part_1A:** 18,803 rows. S=Total on 18,803. S=Total All on 18,732; the remaining **71** have positive unknown and difference exactly negative unknown. Total+unknown=Total All holds on all **12,771 both-present** rows. On the **6,032 blank-unknown** rows, Total=Total All; counting unknown contribution as zero extends the identity to all 18,803.
- **Part_1B:** 32,351 rows. S=Total on 32,351. S=Total All on 32,116; the **235** exceptions have positive unknown and the same exact explanation. Both-present addition holds on **21,346**; **11,005** have blank unknown and Total=Total All.
- **Part_2:** 63,355 rows; S=Total All on **all 63,355**. Total and unknown are blank on every row. No all-blank band distribution.
- **Part_2A:** 30,548 rows; S=Total All on **all 30,548**. Total and unknown are blank on every row. No all-blank band distribution.
- **Part_3:** 37,354 rows; all **107 band/Total/unknown fields** are blank on each, with populated positive Total All. No distribution identity applies. The semantic interpretation as new periods comes from guidance, not from blankness alone.

Positive-unknown counterexample to S=Total All: RAJ/06Q/Part_1A/X02 has S=106, Total=106, unknown=1, Total All=107. A Part_1B example is RK9/14F/C_170: S=33, unknown=2, Total All=35. These are explained differences, not corrupt records.

## E. Blank-versus-zero judgement

**Arithmetic compatibility established; semantic equivalence not established.** Missing band contributions can be set to zero for the stated June reconciliations without changing their results. Conditional on complete, correct totals and disjoint nonnegative categories, the zero residual is consistent with zero missing contributions. It does not establish why the publisher serialized a cell as blank or whether that rule can be applied to another return.

There are **248,640 / 456,808 / 879,377 / 408,933** blank band cells respectively in 1A/1B/2/2A, alongside explicit zeros. Mixed blank/zero rows are **551 / 683 / 1,492 / 705**. No banded row is wholly blank; Part_3's 37,354 distributions are all blank. These facts describe represented rows only: missing provider/commissioner/specialty combinations cannot be diagnosed as non-reporting from absence alone.

D-016 should be narrowed. Completed unknown blanks require their own explicitly scoped arithmetic treatment; they cannot be justified by asserting those blanks do not exist. Annex B cannot supply the missing semantic guarantee.

## F. C_999 judgement

The reported code set is C_100, C_101, C_110, C_120, C_130, C_140, C_150, C_160, C_170, C_300, C_301, C_320, C_330, C_340, C_400, C_410, C_430, C_502, X02, X03, X04, X05, X06, plus C_999. The independent calculation includes all available non-C_999 rows, not a hard-coded assumption that every group has 23 detail records.

Period was included in independent grouping. All **40,636** groups have exactly one C_999 and at least one constituent. None is lost by an inner join in this June file. Across **4,388,688 group-column comparisons**, 2,872,115 have numeric values on both sides, 928,416 are both blank, and 588,157 have aggregate zero versus no observed detail value. Under zero contribution for missing values, every group reconciles; under nullable equality, those 588,157 are not equal observations.

The practical TFC aggregation rule is supported for a chosen provider/commissioner/period/part: **use C_999 alone, or its reported constituents alone**. NHS §10.1.4 supplies reporting-category structure; Annex B supplies the existence of a treatment-function total. S1 does not explicitly name the CSV code C_999, so its association is established from the literal June label and data. Other categories can aggregate lower-level treatment functions without being an extra overlapping roll-up among the reported 23. Arithmetic by itself does not establish patient-level disjointness.

## G. Grain/key judgement

Independent counter-based results for the five-column key, with each component dropped separately:

- Full key: **182,411 unique groups; 0 duplicate groups; 0 excess rows**.
- Drop Period: **182,411; 0; 0** (Period is constant).
- Drop Provider Org Code: **13,502 unique; 12,011 duplicate groups; 168,909 excess rows**.
- Drop Commissioner Org Code: **18,752 unique; 16,377 duplicate groups; 163,659 excess rows**.
- Drop RTT Part Type: **69,836 unique; 48,286 duplicate groups; 112,575 excess rows**.
- Drop Treatment Function Code: **40,636 unique; 40,636 duplicate groups; 141,775 excess rows**.

All 13 identifier/label fields were considered. Provider code determines its observed parent code/name and provider name; commissioner code determines its observed parent code/name and commissioner name, including blanks; part and TFC codes each determine their descriptions. No contrary within-June dependency was found. Reverse name collisions from accepted Phase 1 remain a reason to use codes, not names. Full-key uniqueness alone would make omitted-field invariance trivial; the additional child-to-parent/name checks are stronger evidence.

The proposed grain matches S1 §10.1.1.2 and §10.1.4. It is a supported **candidate natural key for this extract**, not an NHS-guaranteed primary key or a patient/pathway identifier. Period is needed when combining reporting months, but does not distinguish revisions of the same month's file. Missing/revised-source and cross-month handling remains a future acceptance requirement.

## H. Aggregation-safety judgement

The central “one part, one TFC representation” rule is good. Direct examples show why:

- Part_2 excluding NONC, all TFC rows: **14,295,124**. C_999 alone or detail alone: **7,147,562** each. Mixing total/detail doubles the sum.
- Part_2 plus Part_2A using C_999 and excluding NONC: **8,343,076**, versus **7,147,562** for Part_2. This sum combines a documented population and subset; it is not a waiting-list size.
- Default nullable commissioner-parent groupby loses **131,509** Part_2 pathways even after correct NONC/TFC filters. `dropna=False` preserves them.

Provider and commissioner aggregation is supported as collection reporting dimensions for a selected part/period, subject to source quality and scope. Parent columns do not introduce additional observed grain; their presence is not itself duplication. Many-to-many joins, unvalidated organization mappings, ambiguous missing parents and mixed reporting levels still require safeguards. Absence of sentinel strings is not exhaustive proof that every possible hierarchy risk has been eliminated. Snapshot sums across months measure repeated stock observations; flow sums measure events, not necessarily distinct people. The subset count exceptions in A05 must accompany the documented rule.

## I. NONC judgement

Raw prevalence independently matches: **2,993 records; 119 providers; all 24 reported TFCs and all five parts**. The 102,482 raw Total All sum is arithmetically reproducible but analytically mislabeled; corrected per-part counts are in A03.

Within-18-week reproduction, Part_2/C_999:

- Including NONC: **4,721,677 / 7,178,718 = 65.773262%**, 12,936 records.
- Excluding NONC: **4,704,942 / 7,147,562 = 65.825830%**, 12,823 records.
- NONC contribution: **16,735 / 31,156**; exclusion changes the overall rate by **0.052568 percentage points**.
- Over-52 count under the same exclusions: **103,318**, independently reproducing the reported raw calculation.

Retain NONC in the source/analysis representation and filter it for applicable published English figures. Official statistical user guidance directly supports the published-output exclusion and specifies the CSV formula. It also says NONC submission is optional, so these observed counts are not complete non-English activity. “Keep for total activity” therefore needs a coverage qualification. These are pathway counts, not unique patient counts. [NHS statistical user guidance](https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/rtt-statistics-user-guidance/).

## J. NHS-documentation judgement

Sources were checked directly, not through Claude's summaries:

- **S1:** [Recording and reporting RTT guidance v5.0, February 2025](https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2025/02/Recording-and-reporting-RTT-waiting-times-guidance-v5.0-Feb25.pdf). Downloaded 79-page document; version history confirms v5.0. §§10.1.1.1–10.1.1.3 support provider scope, reporting grain, part definitions and extra weekly bands. §10.1.4 supports the category scheme, including exceptions that consolidate lower-level specialties. §10.1.5 supports unknown clock-start reporting but does not define every CSV blank. §10.1.7 supports interval boundaries. §§10.1.8/10.1.9.2 support NONC's meaning. Annex B supports the subset rule and validation checks, not universal semantic blank=zero or proof of source correctness. S1 does not list the literal C_999 CSV code. The report's claim that all 105 bands were added in 2021 should be scoped to the additional bands specified by that section.
- **S2:** [May 2026 statistical press notice](https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2026/07/May26-RTT-statistical-press-notice-PDF-574K-3jBgba.pdf). Its reported 65.6%, 104,734 over-52 count and missing-trust estimation context are genuine May facts. They cannot explain a June-versus-May residual.
- **S3:** The official guidance landing page's indexed content identifies February 2025 recording/reporting guidance and the October 2022 Rules Suite. No material superseding recording/reporting version was identified in this check. The Rules Suite is distinct from the reporting guidance; it is not a substitute citation for CSV mechanics.
- **S4:** [2026–27 publication index](https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/rtt-data-2026-27/) currently links June's notice and timeseries. No April/May production CSV was downloaded or ingested.
- **Additional direct methodology support:** [NHS statistical user guidance](https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/rtt-statistics-user-guidance/) specifies the within-18 CSV filter, denominator and band selection; it confines unknown-clock reporting to completed pathways and clarifies NONC coverage. These are better citations for those statements than the existence of a constitutional standard alone.
- **Same-month benchmark:** [June 2026 statistical press notice](https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2026/08/Jun26-RTT-statistical-press-notice-PDF-579K-6jPlxd.pdf), published 13 August. Page 7's unestimated totals and rounded rate match this audit. Page 1 identifies two non-reporting trusts and reports estimate-inclusive June headlines; exact reconstruction of the uplift was not attempted.

Evidence-class corrections: numerical sums do not prove no overlapping individuals, no unobserved roll-ups, or negligible unknown-clock incompletes. Reported treatment-function categories are the analysis level, not necessarily clinically indivisible specialties. The full source check is more supportive of the basic model than Claude's weak May comparison, but less supportive of its blank semantics and universal disjointness claims.

## K. Test-quality judgement

All 24 Phase 2 tests were reviewed and executed. They have useful separation between synthetic behavior and file-specific observations. Positive points include actual NA-versus-zero loading, negative rejection, a deliberately broken reconciliation, duplicate-key detection, a broken C_999 total, and source-hash verification. No new dependencies or elaborate test architecture is needed.

The June fixtures and assertions call the same helpers they are validating; they are regression evidence, not independent proof. In particular, expected-identity tests inherit `_compare`'s exclusions, C_999 tests inherit inner-join/null normalization, and NONC tests lock an unsafe aggregate. Missing groups, duplicate aggregates, missing totals/keys, incomplete band schemas and literal NA strings are not challenged. The key-drop comment disagrees with the columns actually removed. The both-present unknown row count is not tested, allowing the narrative contradiction to survive. The current 18-week range test can pass a materially wrong percentage.

Immutability checks are meaningful for file bytes. The “detects change” test supplies an intentionally wrong expected hash rather than mutating a file; it verifies mismatch detection, not the historical claim that every past run checked all three raw files. This audit establishes June's current hash and before/after invariance. The Phase 1 tests still pass; their accepted milestone was not reopened.

## L. Assessment of P2-U1 through P2-U6

- **P2-U1 — Exact estimated headline:** Safe to carry into later methodology work, but correct the missing-source and residual-explanation claims **before Phase 3**. Same-month unestimated corroboration is now available. Implement estimates before claiming an exact estimate-inclusive national measure, not merely to pass this audit.
- **P2-U2 — Unknown-clock incompletes:** Safe to carry as genuinely unresolved. The separate CSV field is unpopulated for incomplete parts; neither this fact nor zero residual proves such pathways negligible or folded into a particular band. Remove that inference before downstream use.
- **P2-U3 — Cross-month code/key stability:** Safe to carry; validate on entry of each future month and handle revisions explicitly. Must be addressed during multi-month work, before treating dimensions as temporally stable.
- **P2-U4 — Provider type:** Safe to carry; must be resolved before an NHS-trust-only filter or organization-type analysis. Do not infer exact organization types from names alone.
- **P2-U5 — Period:** Part-specific temporal meanings are already documented: month-end stock versus within-month flows. Parsing the literal period and handling file revisions can be completed during later ingestion. A single undifferentiated month-end snapshot interpretation would be wrong for flow parts.
- **P2-U6 — Day boundaries:** Overstated uncertainty. S1 page 46 supplies **five**, not three, examples: 0–1, 1–2, 17–18, 51–52 and 104+. It also states the weekly sequence. The intermediate integer-day bounds can be derived and labeled as derived: for ranged n–(n+1), n≥1, days 7n+1 through 7(n+1); first band 0–7; final band ≥729. No need to block later band-label work merely because all 105 are not enumerated verbatim.

Additionally, carry the **RTG/84H subset-count exception** as a data-quality item, with explicit restrictions on subset-derived measures. It must be surfaced and given a disposition before Phase 3 acceptance, not silently repaired.

## M. K-1 and K-2 sign-off recommendations

**K-1: APPROVE WITH MODIFICATION.** Approve only an explicitly scoped, non-destructive numerical convention for the independently reconciled June calculations. Do not approve semantic blank=zero, global imputation, or automatic extension to future files. Preserve missingness and report the separate blank-unknown behavior. Any future transformation needs a documented policy, validation coverage and an applicability mask.

**K-2: APPROVE WITH MODIFICATION.** The five natural columns are the best-supported candidate key. Require all columns present, key cells nonmissing, uniqueness over every incoming file, and a defined policy for revised releases. `candidate_key_report()['is_unique']` alone is insufficient. Keep the “candidate/June-supported” wording; do not call it NHS-guaranteed or a unique patient identifier. No surrogate is needed for this phase.

These are independent recommendations, not implementation or analyst approval of a Phase 3 transformation.

## N. Required remediation before Phase 3

1. Correct and synchronize missingness facts, arithmetic applicability, D-016, C_999 comparison wording and controlled examples.
2. Correct NONC pathway aggregation and its test assertions; retain raw prevalence as a separate structural statistic.
3. Make reconciliation expose complete row/group coverage, duplicate aggregates and missingness states; enforce the agreed input/key contract with focused negative regressions.
4. Surface and disposition the Part_2A>Part_2 exception without modifying raw data.
5. Fix NA-parent grouping guidance, scope disjointness/roll-up claims, and explain join multiplicity.
6. Replace the May comparison/residual story with the same-month benchmark and direct methodology citation; update U1/U6. Exact estimated-headline implementation and provider-type references may remain deferred.

Keep the current technology scope. Reusable pandas functions, controlled examples, raw-file checksums and a small targeted suite are sufficient. Freezing incorrect domain conclusions would be a more serious portfolio weakness than honestly documenting their limits.

Audit deliverables added only: this report and `outputs/audit/phase2/` containing independent scripts/results, the separately executed notebook and its output copies, retrieved official source files/text, and source-page renderings. Existing implementation, tests, raw data, notebooks and generated project outputs were not edited by this audit. No remediation was implemented. No Phase 3 work was begun.

## O. Final verdict

**PASS WITH CHANGES.** Numerical foundations substantially reproduce, and the same-month official publication provides stronger corroboration than the original report used. The listed semantic, aggregation and validation corrections are required before freezing Phase 2. Legitimate unresolved source/longitudinal questions may remain explicitly deferred.
