# Phase 3 independent closure audit

8 September 2026. Reviewer: Codex. Scope: the supplied **Codex — Phase 3 Closure Audit.md**, the attached remediation report, and the current repository. No production fixes or Git milestone actions were authorized or performed.

## Verdict

**PASS WITH CHANGES**

**P3-A01, P3-A02, P3-A05, P3-A06 and P3-A07: CLOSED.**

**P3-A03 and P3-A04: PARTIALLY CLOSED.** Remaining byte-binding and publication-verification defects prevent final Phase 3 PASS. The current April–June output remains correct and reproducible.

## Executive summary

The remediation is substantially effective. Missing selected months now withhold publication, wrong-month registry authorization rejects, accepted frames are reused, reserved source-column names reject, backup suffixes are surfaced, and fractional counts/null manifest entries produce actionable errors. The complete suite independently returns **195 passed in 15.36 seconds**, zero failed or skipped.

Two real workflow runs preserve **541,363 rows and 125 columns** and reproduce the prior audit and current saved Parquet with strict value, ordering, missingness and dtype comparisons. Both runs and Notebook 03 produce the same generation ID. Notebook 03 executes without errors. Phase 1/2 remain unchanged and accepted.

The remaining material failures are independently demonstrated:

1. **P3-A03 residual — BLOCKING:** a synthetic source changes from A=7 to B=99 for the actual load, then returns to A before the final hash. The workflow accepts and publishes 99 under A's digest. Retaining the frame closes the later reload window, but endpoint hashes do not establish that all reads used one immutable byte stream.
2. **P3-R01, under P3-A04 — BLOCKING:** changing only the marker's `combined_rows` to 999999 makes `verify_publication` return `valid=True, combined_rows=999999` for a one-row Parquet and one-row sidecar. Returned verification evidence is not fully validated.
3. **P3-R02 — NON-BLOCKING:** after one interrupted publication, a second failed attempt overwrites the good `.prev` backup with the already-invalid current trio. Restoration then returns `restored=True` but nested `verify.valid=False`. Invalidity remains detectable, but the promised recovery material is lost.

This is a focused closure check, not a repeat of the original broad audit. No current real-source corruption, Phase 4 leakage or Phase 1/2 regression was established.

## Environment and commands

- Workspace: `C:\Users\abdul\OneDrive\Desktop\P_Projects\NHS-RTT-Waiting-Times`.
- Existing interpreter: `C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe`; pandas **3.0.5**.
- PowerShell; no environment creation, dependency installation or Windows changes.
- The attached and repository remediation reports are byte-identical: SHA-256 **`69c0b97b6fc5198e2966edaa1d232a805d65f979228926462962c2c439c74e36`**.

Commands from the repository root:

```powershell
git rev-parse HEAD 'phase-2-pass^{commit}'
git status --short
git diff --stat 8f32147
git diff --cached --stat
git tag --list
Get-FileHash data/raw/*.csv
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' -m pytest -q
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' -m pytest --collect-only -q
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase3_closure/probes.py
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase3_closure/reproduce.py
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase3_closure/execute_notebook.py
```

Sandbox process creation sometimes returned “Access is denied”; approved execution with the same interpreter succeeded. Notebook selector-fallback/local-kernel transport warnings were non-fatal. No configuration workaround was used.

Evidence is isolated in the already ignored **`outputs/audit/phase3_closure/`**:

- `probes.py` and `probes.json`: **24 named scenarios**, including multiple subchecks. Fixtures construct the 105-band schema independently rather than importing the test suite's band generator.
- `fixtures/run-*/`: independently constructed CSVs, registries and publication trios. Each invocation uses a fresh directory so deliberate failures cannot contaminate reruns.
- `reproduce.py`, `real_reproduction.json`, `real_run1.txt`, `real_run2.txt`, and the two generated audit publications.
- `execute_notebook.py`, `notebook.json`, the executed Notebook 03 copy, `notebook_output/` and its local kernel specification.
- `test_collection.txt`, `git_status_before_report.txt`, `protected_before.json`, `protected_after.json`.
- `snapshot/`: copies of the reviewed Phase 3 modules, relevant tests/docs/notebook and intended registry, retained for an exact subsequent closure baseline.

All fault injection operates on audit fixtures or temporary process-local call boundaries. It does not edit production modules or real NHS raw files. For publication interruption tests, both generations are derived from actually accepted synthetic sources and bound frames. Expected counterexamples are recorded as observations, not incorrectly counted as passing correctness tests.

## Regression results

**195 passed in 15.36 seconds; zero failed or skipped.** Independent collection found 195 cases in 0.77 seconds:

- Phase 1: **47**.
- Phase 2: **51**.
- Existing ingestion: **55**.
- Existing cross-month: **17**.
- New remediation: **25**.

The new tests meaningfully cover the original examples, but they do not establish the full stronger guarantees. The mid-acceptance test mocks two different hash results; it does not load changed bytes that are subsequently restored before the final hash. Publication tests cover one replacement interruption and Parquet tampering, but omit unchecked marker row counts and failed-retry backup preservation. The independent closure cases exercise those boundaries with real fixture writes.

The raw CSVs, frozen Phase 1/2 source/tests/notebooks and checked dependency declarations match the accepted Phase 2 baseline. Notebook 01/02 were not re-executed: their production files/dependencies are unchanged and all their regression tests pass, as permitted by the closure brief.

## P3-A01 closure

**CLOSED.** Evidence: `probes.json → A01`; implementation: `crossmonth.py` intended/required/accepted reconciliation and `combine_months(require_months=...)`.

The default required set is now the registry's selected months. The independent sequence publishes valid May and June (**2 rows**), renames the synthetic May source to `.csv.bak` without changing the registry, then reruns:

- `ok=False`.
- `missing_intended=['2026-05']`.
- No returned publication or reduced combined dataset.
- The prior Parquet, sidecar and marker remain byte-identical; verification still returns the earlier valid **2-row** generation.

An additional selected April entry that was never physically present also appears in `missing_intended` and prevents publication. An unexpected production-looking July source is identified in `unexpected_months=['2026-07']` and cannot join a successful full publication.

An explicit `require_months=['2026-06']` succeeds with one row despite the absent selected May source. The returned evidence records `requested_subset`, required/intended/accepted sets and an explicit-subset note. This is caller intent, not inferred filesystem exclusion. The sidecar records the included month; it does **not** persist the full requested/intended-set context. Consumers needing that context should retain the result/notes; this is consistent with the documented result-level recording and is not elevated to a new blocker here.

Required-month equality is also defensively enforced at combination. Ordinary missing/rejected runs preserve the previous valid generation without labelling it as the failed run's output.

## P3-A02 closure

**CLOSED.** Evidence: `probes.json → A02`.

Valid June bytes registered only under a May filename/reporting-period entry now fail both direct `accept_month` and end-to-end orchestration. Direct rejection includes:

> `provenance: the registry entry for this digest authorises reporting month 2026-05, not the accepted month 2026-06 - fail closed`

The rejected report has `frame=None`; orchestration returns `ok=False` and no publication. Registry-based authorization checks canonical month and basename, in addition to matching SHA-256. The canonical month must still agree with internal Period and production filename.

The explicit `expected_sha256` mechanism remains a separate authorization path. Correct expected-hash-only acceptance works, while an internal June Period in a May filename rejects even with the correct explicit hash. If both a registry and explicit expected hash are supplied, the explicit expected hash takes precedence and `provenance_source='expected_sha256'`; it does not purport to be registry authorization. The normal workflow supplies the registry and discovery digest, not this alternative expected-hash override. Its deliberate precedence is therefore distinguished from the original accidental global-digest authorization defect.

## P3-A03 closure

**PARTIALLY CLOSED — BLOCKING residual.** Evidence: `probes.json → A03_after_acceptance`, `A03_between_discovery_acceptance`, `A03_during_read_persistent`, `A03_during_read_restore`.

The following changes work:

- **Scenario A:** accept A=7, then change the underlying fixture to B=99 after successful acceptance. Orchestration publishes **7 with A's digest**, from the retained accepted frame. The old post-acceptance reload defect is closed.
- **Scenario B:** change the fixture after discovery hashing but before acceptance. The run rejects with a discovery/acceptance digest mismatch and `frame=None`.
- **Scenario C, persistent change:** change the file during the actual loading boundary and leave B on disk. The final rehash detects the change; rejection clears the frame.

**Scenario C, changed-and-restored bytes, still fails:**

1. Start with a registered synthetic CSV containing A=7.
2. Let acceptance perform its initial hash and structural reads against A.
3. At the actual loader boundary, write B=99 to that same synthetic path, then invoke the real `semantics.load_rtt_csv` on B.
4. Restore A's exact original bytes before returning from the loader.
5. Let the remaining real acceptance checks, final hash and workflow publication run unmodified.

Observed result:

```text
accepted=True; workflow ok=True
sha256 == sha256_after == registered A digest
published Total All=99
published source_sha256=A digest
verify_publication.valid=True
```

A's digest is **`abfcde17626765d4d0d5f6caecb46a9635c3dc1e017562d71cbd2b07cdbe95e0`**. The file is back to the registered A bytes, but its accepted/published frame holds B. The probe does not mock hashes, fabricate a DataFrame or alter production code; it changes only the synthetic source around a real load. A temporary replacement followed by a rollback demonstrates why equal endpoint hashes do not prove that the intervening reads consumed those bytes.

**Affected invariant:** the provenance digest must identify the bytes that generated the accepted values, not merely the bytes present before and after loading.

**Code:** `ingest.py:621` loads from the mutable path, `:650` retains that frame, and `:663` hashes the path again. There is no single immutable snapshot shared by hashing, Period/schema checks and loading.

**Required targeted remediation:** hash and validate/load the same stable byte snapshot or stable private source copy, then retain that accepted frame. A before/after hash of a separately reopened path is insufficient. Keep the frozen Phase 2 semantics; they can be invoked against the stable snapshot through a suitable interface or same-basename private copy. Add this real changed-and-restored input case and retain the three successful boundary tests. Clear the frame on all rejected outcomes.

The claimed universal accepted-byte binding and full P2-U3/P2-U5 ingestion closure remain premature until this is resolved.

## P3-A04 closure

**PARTIALLY CLOSED.** The ordinary mixed-generation replacement defect is now detected, but **P3-R01 is BLOCKING** and **P3-R02 is NON-BLOCKING**. Details are in “New findings” below.

Evidence: `probes.json → A04_*`. All interruption tests use valid one-row generation 1 and valid two-row generation 2.

- **Staged roundtrip failure:** raises `PublicationError`; the original valid one-row generation remains coherent.
- **Before final Parquet replacement:** injected `OSError`; verification remains **valid**, and independent hashes/counts show the entire previous one-row generation is intact.
- **After Parquet replacement, before sidecar replacement:** verification is **invalid**; Parquet has two rows while sidecar and marker have one. Direct restoration of the saved prior trio returns the valid original generation.
- **After sidecar replacement, before marker replacement:** verification is **invalid**; Parquet and sidecar have two rows, but the marker still describes the old generation. Direct restoration succeeds.
- **Marker replacement fails before taking effect:** covered at the third replacement boundary above. An atomic rename has no meaningful half-written-file state to simulate.
- **Marker replacement completes, then caller is interrupted:** injected error immediately after the third real replacement; verification is **valid**, and all three artifacts independently agree on generation 2 and two rows. This is acceptable: a completed commit can survive a later caller failure.

These tests also confirm that it is too broad to say **every** interrupted run leaves an invalid trio: failure before replacement leaves the old valid trio, and failure after the commit point leaves the new valid trio. What matters is whether a trio reported valid is coherent.

Independent tampering with Parquet bytes, sidecar bytes, marker generation ID, marker Parquet digest and marker sidecar digest correctly invalidates verification. Critical hashes are actually computed. Ordinary ingestion rejection after a valid publication leaves that earlier generation unchanged and verifiable.

However, `verify_publication` trusts and returns the marker row count without checking it, and backup rotation tests only file existence rather than validity. Those remaining gaps prevent unconditional closure of the claimed publication-generation contract. No additional infrastructure is required to fix them; targeted validation and backup preservation are sufficient.

## P3-A05 closure

**CLOSED.** Evidence: four independent `A05_*` records in `probes.json`.

Each reserved name was added separately to an otherwise valid 121-column source: `source_file`, `source_sha256`, `reporting_month`, `source_row_index`. Each 122-column source now rejects before publication with an explicit reserved-name reason and `frame=None`; no original value is renamed or overwritten.

For each name, separately passing a loaded colliding frame to `combine_months` raises `ReservedColumnError`. The frozen Phase 2 105-band implementation remains unchanged. Ordinary real inputs retain all 121 source columns and publish exactly 125 columns.

## P3-A06 closure

**CLOSED.** Evidence: `probes.json → A06`.

`rtt_2026_04.csv.bak`, `rtt_2026_04.csv~` and `rtt_2026_04.csv.tmp` are all classified as malformed candidates. None enters `production_files`. Unrelated `notes.txt` and `summary.csv` remain ignored. The strict production matcher is unchanged; the loose classifier does not grant ingestion eligibility.

The missing-May sequence also verifies this behaviour in the real orchestration path rather than only through a filename parser test.

## P3-A07 closure

**CLOSED.** Evidence: `probes.json → A07`.

A fractional `1.5` count now yields `accepted=False`, `frame=None` and the structured reason:

```text
load: TypeError: cannot safely cast non-equivalent object to int64
```

No incidental pandas exception escapes that acceptance call; no rounding or imputation occurs. `{"sources":[null]}` raises an explicit `ValueError`:

```text
manifest.json: sources[0] must be a JSON object, got NoneType
```

Registry item/type checks occur before indexing; the existing new regression additionally verifies non-string required fields. The load handler is limited to `(ValueError, TypeError)` around loading, rather than a workflow-wide blanket `except Exception` or a success fallback. This closes the scoped input-error issues without changing numeric semantics.

## Real April–June reproduction

Evidence: `real_reproduction.json`, `real_run1.txt`, `real_run2.txt`, the two audit publications, and protected-file hashes. The focused reproduction completed in **254.88 seconds**.

Independent observed hashes remain equal to the supplied baseline and registry:

- **April:** `0486aca5891a96af4f15e2f4559795138baef08b0ed580602b8c3a7aec6a56e9`; **180,781** CSV data records/loaded rows; Period `RTT-April-2026`; canonical `2026-04`.
- **May:** `fee364bc3654cf666f79d3485d26e2ada649a3418988a47aa1784e93294a5707`; **178,171** records/rows; Period `RTT-May-2026`; canonical `2026-05`.
- **June:** `edc3927e4a0065855ad3b2347e7f82688e687b065406eefb49e2f67a9cd67f02`; **182,411** records/rows; Period `RTT-June-2026`; canonical `2026-06`.

All three have **121 source columns**, the exact independently constructed **105-band ordered schema**, usable five-column keys, matching discovery/initial/final hashes, and accepted frames. No intended month is missing; no unexpected month is present. The required, intended and accepted sets are all April–June.

Combined output is **541,363 rows × 125 columns**, with the original five-column candidate key complete and unique. Raw CSVs were independently parsed as strings with explicit empty-string missingness, followed by independently specified nullable-integer conversion. Every source column was compared against the accepted frame and its ordered Parquet block. Each block has correct basename/hash and continuous `source_row_index=0..n-1`. This establishes actual source preservation, beyond trusting acceptance assertions.

Strict comparisons confirm values, column/row order, missingness and dtypes match both the original audit's saved Parquet and the current production Parquet. Original Period, leading-zero strings, `C_999`, `NONC` and all source parts remain present.

April / May / June preservation counts:

- Blank Total: **130,720 / 129,256 / 131,257**, total **391,233**.
- Entirely missing waiting-band distributions: **36,525 / 35,595 / 37,354**, total **109,474**.
- Blank Total All: **0 / 0 / 0**.
- `C_999` rows: **40,102 / 39,677 / 40,636**.
- `NONC` commissioner rows: **2,955 / 2,904 / 2,993**. These are row counts, not cross-part pathway totals.

Independent one-to-one Part_2A/Part_2 joins reproduce:

- April: **0 violations**, **5 unmatched** Part_2A groups.
- May: **1 violation**, **3 unmatched** groups; `NT230 / 05V / C_100`, **2 > 1**.
- June: **2 violations**, **0 unmatched** groups; `RTG / 84H / C_502` and `RTG / 84H / C_999`, **2 > 1** each.

Those values are preserved rather than capped. P2-U7 remains carried under the accepted policy; no Phase 2 decision is reopened.

## Publication integrity and determinism

Both real workflow runs self-verify and independently have matching artifact hashes, marker/sidecar/Parquet row counts, and recomputed generation IDs. The audit recalculates the ID from the actual Parquet digest and serialized deterministic block, rather than only comparing the two stored ID strings.

The stable ID across both runs and Notebook 03 is:

**`f67b7342a30c4642a78864243142d910b84295dc7876ffb01c231cb8dc52627d`**.

Equivalent reruns retain identical data, order, provenance and deterministic sidecar content. Reversed real payload order produces a strictly equal combined frame. Intended/required/accepted month evidence agrees between runs. Run timestamps differ, demonstrating that volatile metadata does not alter the stable generation ID in this environment. Byte identity across arbitrary Parquet library versions is not required or asserted.

For these legitimate inputs, the generated publication is coherent. That fact does not close the independent verifier-tampering and source-read counterexamples. A file-integrity marker establishes consistency of the files it actually checks; it cannot retrospectively prove a misbound accepted source hash.

## Notebook/documentation verification

Notebook 03 executes as an audit copy using the existing interpreter: **10 original code cells**, **11 including the audit identification cell**, **zero errors**, **105.22 seconds**. Its output equals the saved production Parquet with strict dtype/value comparison, its deterministic manifest agrees, and its generation verifies with the same ID above. The canonical notebook's bytes are unchanged.

Only the output-directory assignment was redirected in the audit copy. The notebook remains setup/orchestration/display/narrative; reusable acceptance and publication code resides in `src/`. No need arose to re-execute Notebook 01/02.

The original completion report now begins with a clear **SUPERSEDED IN PART** banner and points to the remediation report/current methodology. A future reader is directed away from its original acceptance/publication claims. D-038 and the new documentation cover the intended remediation scope.

Remaining documentation corrections should accompany the residual fixes:

- `phase3_ingestion.md` says the digest is rechecked “after every read”; actual acceptance hashes at the beginning and after all reads. Neither wording establishes an immutable snapshot, and the counterexample shows why the claimed binding remains incomplete.
- `phase3_ingestion.md`, D-038 and the remediation report overgeneralize interrupted publication states. The precise contract should permit either a coherent previous/new generation or an explicitly invalid state, depending on the commit point.
- The guaranteed previous-generation recovery wording does not hold after a failed retry (P3-R02).
- `verify_publication` needs to validate the row count it reports as part of a valid generation (P3-R01).
- P2-U3/P2-U5 must remain **partially addressed for ingestion** while A03's exact-byte binding remains unresolved. P2-U7 is preserved and correctly described.

The explicit subset context is documented as recorded in the returned result/notes, which is what the code does. The generated sidecar contains accepted publication months, not the full requested/intended-set context. The report's claim that interruption produces `PublicationError` is narrower than actual behaviour: injected replacement failures propagate `OSError`; both signal failure, and no false successful return was observed in those cases.

## Repository hygiene and phase boundary

`HEAD` and the peeled `phase-2-pass` tag remain **`8f321473d286766d23ea4a3172b8f5b4d8e0e018`**. The only tag is `phase-2-pass`; no Phase 3 commit/milestone exists, and the index has no staged changes.

Against Phase 2, tracked modifications remain `.gitignore`, README and the documented assumptions/provenance/decisions files. The uncommitted Phase 3 additions remain identifiable; the remediation adds its report and the 25-case test file and updates the Phase 3 implementation/notebook/docs. Inspection shows changes concentrated on the seven audited boundaries, especially the required publication rewrite. No unrelated Phase 4 implementation or broad semantic refactor was found.

There was no immutable source snapshot/commit of the original untracked Phase 3 modules. Comparison with the previous audit therefore uses its preserved report, code evidence and executable scenarios, not a falsely claimed exact Git diff of those untracked versions. An exact snapshot of the current reviewed Phase 3 state is retained under the closure evidence directory for the next review. Frozen Phase 1/2 comparisons are exact against the committed baseline.

Real CSVs, canonical notebooks, production source/tests/docs and existing interim files captured in `protected_before.json` are byte-identical in `protected_after.json`. The audit adds this report and ignored evidence only. Raw/interim artifacts, markers, `.prev` files and audit copies remain ignored. `data/raw/manifest.json` remains the narrow intended tracking exception, but is currently **untracked**, consistent with the intentionally uncommitted milestone; “tracked” in prose describes its intended status.

No analytical reshape, cleaning/imputation, dimensional modelling, DuckDB/SQL analytical layer, KPIs, provider enrichment, trends/statistics, BI, ML or Spark was introduced. No source anomaly was repaired. No raw file, production source, canonical notebook, Git index or Git milestone was changed by the auditor.

## New findings, if any

### P3-R01 — Verified publication returns an unchecked marker row count

**Severity: BLOCKING. Related original finding: P3-A04, PARTIALLY CLOSED.**

**Executable evidence:** `probes.py`, `tamper('rows')`; saved result `probes.json → A04_tamper_rows`. Begin with a valid one-row publication. Change only `combined_rows` in `rtt_combined.generation.json` from 1 to **999999**, leaving both artifact digests and generation ID untouched. The actual Parquet and sidecar still describe one row. The verifier returns:

```json
{"valid": true, "generation_id": "265cd804d4bf0efa18eea12a7d5692b1904f8cdde8b515079001e9f8ab5efc30", "combined_rows": 999999}
```

**Affected invariant:** a valid publication verdict and the metadata returned with it must describe one consistent generation. The returned record directly certifies false row-count evidence even though the data file itself has not changed.

**Cause:** `crossmonth.py:491–522` checks file digests and ID equality, then returns `m.get('combined_rows')` without comparing it with the sidecar's deterministic count or actual Parquet metadata. The generation ID is derived from Parquet/deterministic evidence, but verification does not reconcile this returned marker field against those sources.

**Required targeted remediation:** validate marker structure and row-count consistency against the checksum-verified sidecar and actual Parquet row metadata, then return the verified value. Reject this single-field corruption. Retain the existing digest/ID tamper tests and add marker-count mismatch coverage; do not introduce a new storage platform or relax the consumer validity contract.

### P3-R02 — Failed retry overwrites the last valid rollback generation

**Severity: NON-BLOCKING. Related original finding: P3-A04.**

**Executable evidence:** `probes.json → A04_retry_failure_rollback`.

1. Publish valid one-row generation 1.
2. Attempt generation 2 and fail before the second replace. Current files are mixed and verification is invalid; `.prev` still holds valid generation 1.
3. Retry publication and fail before its first replace. Before that failure, the writer copies the already-invalid current trio over `.prev` merely because all three files exist.
4. Restore `.prev`: the function returns **`restored=True`**, but **`verify.valid=False`**, because the saved Parquet has two rows while the saved old sidecar/marker have one.

**Cause:** `crossmonth.py:473–475` treats file existence as evidence of a complete valid previous generation. `restore_previous_generation` at `:525–537` copies the files and reports that copying occurred without making successful validity part of its `restored` flag.

**Affected invariant:** the advertised `.prev` recovery material should preserve the last valid generation across failed attempts.

**Remediation:** verify the current trio before rotating it into `.prev`; retain a known-valid previous backup when current files are invalid. Validate backup contents before restoration and distinguish successful restoration from merely copying an invalid trio. Add this repeated-failure sequence.

This remains non-blocking because the nested verifier correctly reports invalidity and source-based regeneration remains possible. It does not create a false valid publication by itself. The recovery guarantee and documentation nevertheless need correction.

No other new blocking finding is asserted. The changed-and-restored input counterexample is a residual of **P3-A03**, not a reopening of Phase 2 or a separately counted new finding.

## Final Phase 3 PASS checklist

- [x] Frozen Phase 1/2 code/contracts preserved and all 98 regressions pass.
- [x] All 97 Phase 3 cases pass; 195 total independently collected/executed.
- [x] **P3-A01 CLOSED:** missing intended inputs withhold publication; explicit subset and unexpected inputs checked.
- [x] **P3-A02 CLOSED:** registry authorization binds month/filename/digest; explicit expected-hash authority is distinct.
- [ ] **P3-A03 PARTIALLY CLOSED:** retained frame and ordinary change guards work; changed-and-restored read still misbinds bytes.
- [ ] **P3-A04 PARTIALLY CLOSED:** replacement interruption detection works; unchecked verified row count remains blocking (P3-R01).
- [x] **P3-A05 CLOSED:** all four source-column collisions reject, including defensive combination.
- [x] **P3-A06 CLOSED:** backup/temp/suffix classification fixed without widening production eligibility.
- [x] **P3-A07 CLOSED:** fractional counts and null manifest entries fail actionably.
- [x] Real April/May/June rows, schema/key, values/missingness, Period, `C_999`, `NONC` and P2-U7 reproduced.
- [x] Equivalent real reruns and payload shuffle agree; stable generation ID independently recomputed.
- [x] Notebook 03 executes cleanly and remains thin orchestration.
- [ ] Documentation can claim final trustworthy byte/publication binding and P2-U3/U5 closure: residuals above.
- [x] Repository hygiene/Phase 3 boundary preserved; no milestone action performed.

## Recommendation

Apply focused fixes for the **A03 exact-byte snapshot residual** and **P3-R01 verified metadata consistency**, and correct **P3-R02 backup rotation/recovery** while working on publication. Align the documentation with the actual guarantees. Then rerun these counterexamples, the complete regression suite and the focused legitimate-input reproduction. There is no reason to repeat broad Phase 1/2 audits or redesign the pipeline.

Phase 3 is **not yet ready for the project owner to create its acceptance milestone/tag**. Five original findings are closed, but material provenance and verification defects remain. No production fixes were made during this audit.

**PASS WITH CHANGES**
