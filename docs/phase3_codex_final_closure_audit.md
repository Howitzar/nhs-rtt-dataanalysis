# Final independent Phase 3 closure audit

8 September 2026. Reviewer: Codex. Scope: the supplied **Codex — Final Phase 3 Closure Audit.md**, the final remediation report, and the current repository. This is a focused closure of residual P3-A03, P3-R01 and P3-R02, with regression verification.

## Verdict

**PASS**

**Residual P3-A03: CLOSED. P3-R01: CLOSED. P3-R02: CLOSED.** P3-A04 is consequently closed. Previously closed P3-A01, P3-A02, P3-A05, P3-A06 and P3-A07 remain closed. No new blocking defect was established in this final check.

## Executive summary

The three remaining counterexamples now behave correctly. All acceptance validation/loading uses the same private snapshot bytes that supply the accepted digest. Marker, sidecar and actual Parquet row counts must agree. Failed publication retries preserve the valid rollback generation, and restoration reports success only after verification.

The complete suite independently returns **208 passed in 14.26 seconds**, zero failed or skipped. Two legitimate April–June workflow runs reproduce **541,363 rows × 125 columns**, with strict equality of values, order, missingness, dtypes and provenance against the prior audit and saved production output. Both runs and Notebook 03 reproduce the reported generation ID. Notebook 03 executes without errors.

One documentation precision note remains advisory: the original source has one authoritative snapshot-acquisition read and a second informational reread for warnings. The latter supplies no accepted values and is not a mutable-source validation fallback. This distinction was independently traced, not assumed from the report's “exactly once” wording.

No production fixes, raw-data edits, commits, tags, pushes or milestone actions were performed.

## Environment and commands

- Workspace: `C:\Users\abdul\OneDrive\Desktop\P_Projects\NHS-RTT-Waiting-Times`.
- Interpreter: `C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe`; pandas **3.0.5**.
- PowerShell; no new environment, dependency installation or Windows configuration changes.
- Attached and repository final remediation reports are byte-identical: SHA-256 **`b17d9b173afec222e4cc48adc9607b4f1a07e2bb4fd49b053a36fac15bc31af6`**.

Commands, from the repository root:

```powershell
git rev-parse HEAD 'phase-2-pass^{commit}'
git diff --cached --stat
git tag --list
Get-FileHash data/raw/*.csv
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' -m pytest -q
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' -m pytest --collect-only -q
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase3_final/probes.py
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase3_final/reproduce.py
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase3_final/execute_notebook.py
```

One audit execution approval was interrupted by an automatic-review usage limit. Following the user's instruction to continue, the same execution request succeeded through the normal approval mechanism. No workaround or interpreter change was used. Notebook selector-fallback/local TCP warnings were non-fatal.

Evidence is retained under the already ignored **`outputs/audit/phase3_final/`**:

- `probes.py`, `probes.json`: **24 named independent scenarios**, with fresh synthetic fixture directories and asserted expected outcomes.
- `reproduce.py`, `real_reproduction.json`, `real_run1.txt`, `real_run2.txt` and both audit publication trios.
- `execute_notebook.py`, `notebook.json`, the executed notebook copy, redirected notebook output and a local kernel specification.
- `test_collection.txt`, `notebook_source_comparison.json`, `protected_before.json`, `protected_after.json`, `git_status_before_report.txt`.
- `ingest.diff`, `crossmonth.diff`: exact comparisons against the prior closure's saved source snapshot.
- `snapshot/`: copies of the final reviewed implementation, relevant documentation/test file/notebook and registry for future traceability.

Fault injection changed only synthetic original-source paths or audit publication files. It did not modify private snapshot contents, fabricate loader results, mock SHA-256 values or edit production source. Real-data reproduction reused the prior independent audit harness with a new output directory; earlier audit evidence was preserved.

## Regression results

**208 passed in 14.26 seconds; zero failed or skipped.** Separate collection confirms **208 cases in 0.53 seconds**:

- Phase 1: **47**.
- Phase 2: **51**.
- Ingestion: **55**.
- Cross-month: **17**.
- Audit remediation: **38**.

The existing ingestion and cross-month test files are unchanged against the prior closure snapshot. The remediation test file adds the focused final cases and revises the previous endpoint-hash expectations to snapshot behaviour. Independent final probes do not import repository test fixtures or the production expected-band generator.

Phase 1/2 production source, tests and notebooks, and checked dependency declarations, remain unchanged against `8f32147`. Their 98 tests pass. Notebook 01/02 were not re-executed because the final changes do not alter their dependencies or execution paths, as permitted by the brief.

Previously closed findings remain closed: the complete regression suite retains intended-source completeness, month-bound authorization, reserved-name rejection, suffix classification and structured invalid-input coverage. Inspection of the exact remediation diff found no weakening of those paths.

## P3-A03 closure

**CLOSED.** Evidence: `probes.json → A03_changed_restored`, `A03_changed_after_snapshot`, `A03_changed_before_snapshot`, `A03_reject`; source: `ingest.py:531`, `_accept_from_snapshot` at `:575`, and snapshot validation/loading/counting at `:651`, `:665`, `:671`.

The authoritative sequence is now:

1. Acquire the original source as a byte buffer.
2. Compute `report.sha256` from that buffer and compare with the discovery digest when supplied.
3. Write the same bytes to a private temporary file with the original basename.
4. Run reserved-column, Period, frozen schema/loader, row-count and key validation using that snapshot.
5. Retain the resulting frame; clean the snapshot directory in `finally`; clear `frame` on a rejected report.

Independent tracing recorded the actual paths received by `distinct_period_values`, `validate_extract`, `load_rtt_csv` and `count_data_rows`. Every such path was the private snapshot, including nested validation inside the real loader. No validator or loader reopened the original mutable path after snapshot acquisition.

**Exact former counterexample:** initial synthetic A has Total All=7 and the registered/discovery digest **`abfcde17626765d4d0d5f6caecb46a9635c3dc1e017562d71cbd2b07cdbe95e0`**. At the real loader boundary the probe writes B=99 to the original source, invokes the real loader on its supplied snapshot path, and restores A before acceptance returns. Observed and asserted:

- Acceptance succeeds with frame value **7**, not 99.
- The published Parquet contains **7** and A's digest.
- `source_file` remains `rtt_2026_06.csv`; report path is the original path.
- No snapshot/temp path appears in any row-level provenance field.
- The original synthetic source is byte-identical to A at completion.
- The private snapshot file and directory no longer exist after acceptance.
- Publication verifies successfully.

**Change before acquisition:** changing the original after discovery hashing but before snapshot acquisition rejects with a discovery/snapshot mismatch and `frame=None`.

**Change after acquisition:** leaving B on the original path after the snapshot is created still accepts/publishes A=7 with A's digest; a warning records that the original changed. There is no fallback load from B.

**Rejection:** a controlled loader `ValueError` produces a rejected report with `frame=None`; snapshot cleanup still occurs. The changed-before-acquisition rejection likewise clears the frame and cleans the private snapshot.

**Read-count precision:** tracing counted **two** reads of the original path. `ingest.py:531` acquires the authoritative buffer; `:561` performs a later informational reread for `sha256_after`/warnings. The latter is not used to generate, validate or authorize the accepted frame. Therefore the literal report claim that the original is read exactly once in total is inaccurate, but the required exact-byte binding is now demonstrated. Before/after hashing is not being relied on to establish it.

## P3-R01 closure

**CLOSED.** Evidence: `probes.json → R01_*`; implementation: `verify_publication` and `_parquet_num_rows` in `crossmonth.py`.

The original single-field attack now returns:

```text
valid=False
row-count disagreement: marker=999999 sidecar=1 parquet=1
```

Only the marker count was changed; the valid one-row Parquet and sidecar were untouched. Independent further cases confirm rejection of:

- Missing marker `combined_rows`.
- String, fractional, negative, null and boolean marker counts.
- Non-object marker JSON and missing required generation/digest fields.
- Sidecar count=2 with its marker-recorded digest updated to the actual edited sidecar hash.
- Sidecar string/null/negative/boolean counts, with its digest updated.
- A valid two-row Parquet replacing the one-row Parquet, with the marker Parquet digest updated, while marker/sidecar counts remain one.
- Marker and checksum-verified sidecar both claiming two rows while the actual Parquet still has one.

The mismatches are rejected for the expected count/structure reasons, rather than merely failing an unrelated stale checksum. A normal publication verifies and returns the actual row count.

Code inspection confirms required marker returned-identity fields are checked as nonempty strings and marker count as a nonnegative integer excluding booleans. Both artifact SHA-256 values are recomputed. Sidecar generation ID is compared with the marker; marker/sidecar counts are reconciled with actual `ParquetFile.metadata.num_rows`. The successful return uses that reconciled actual count rather than blindly returning marker metadata.

This closes the false-valid metadata result. Existing digest checks remain in place; this focused review does not claim cryptographic authentication against an actor deliberately rewriting an entire artifact set and all its checksums.

## P3-R02 closure

**CLOSED.** Evidence: `probes.json → R02`; rotation guard at `crossmonth.py:484`, verified restoration at `:584–605`.

The exact prior failed-retry sequence was reproduced:

1. Publish valid one-row generation 1.
2. Attempt valid two-row generation 2 and fail before the second final replacement, after Parquet replacement. Current paths are invalid.
3. Copy `.prev` into an independent audit directory and verify it as valid generation 1; record all backup byte hashes.
4. Retry generation 2 and fail before its first final replacement.
5. Verify that every `.prev` file is byte-identical to the recorded valid backup; independently verify the copied `.prev` trio again as generation 1.
6. Restore: `restored=True`, `verify.valid=True`, original generation ID and one row.

The valid backup ID before and after the failed retry is **`265cd804d4bf0efa18eea12a7d5692b1904f8cdde8b515079001e9f8ab5efc30`**.

Additional cases pass:

- **Most recent valid rotation:** after a later two-row generation succeeds, a subsequent publication rotates that newer valid generation into `.prev`, rather than keeping an older backup indefinitely.
- **Corrupt `.prev`:** restoration returns `restored=False` with a verification reason. The live trio remains byte-identical to its pre-attempt state.
- **No `.prev`:** restoration returns a clear `restored=False`, “no complete previous generation” result.

The writer now rotates current files only when they verify, preserving a known-valid backup across the tested failed retries. Restoration verifies a scratch copy before touching live paths and re-verifies the restored publication before reporting success. No false-valid recovery state was observed.

Together with the prior closure's successful interruption/hash-verification cases, closure of R01 and R02 completes **P3-A04**.

## Real April–June reproduction

Evidence: `real_reproduction.json`, `real_run1.txt`, `real_run2.txt` and both audit publication trios. Two real runs and independent comparison completed in **176.18 seconds**.

All observed hashes match both the frozen identities and registry:

- **April:** `0486aca5891a96af4f15e2f4559795138baef08b0ed580602b8c3a7aec6a56e9`; **180,781** CSV records/loaded rows; raw Period `RTT-April-2026`, canonical `2026-04`.
- **May:** `fee364bc3654cf666f79d3485d26e2ada649a3418988a47aa1784e93294a5707`; **178,171** records/rows; raw Period `RTT-May-2026`, canonical `2026-05`.
- **June:** `edc3927e4a0065855ad3b2347e7f82688e687b065406eefb49e2f67a9cd67f02`; **182,411** records/rows; raw Period `RTT-June-2026`, canonical `2026-06`.

All sources have 121 columns and the exact independently constructed ordered 105-band contract. The original five-column candidate key is complete and unique per source and combined. Every source is accepted; intended, required and accepted months are April–June; missing/unexpected sets are empty.

Combined output is **541,363 rows × 125 columns**, preserving all 121 source columns plus four provenance fields. Independent lexical CSV parsing with explicit blank handling and nullable-integer conversion equals each accepted frame and corresponding ordered Parquet block. Basename/digest and continuous `source_row_index=0..n-1` agree with every source block. Original Period remains unchanged.

Strict DataFrame comparisons include values, row/column order, missingness and dtypes. Results equal the original audit's Parquet and current production output. There is no global blank-to-zero conversion, lost `C_999`/`NONC` category or analytical summation of parts.

April / May / June retained counts:

- Entirely missing bands: **36,525 / 35,595 / 37,354**; combined **109,474**.
- Blank Total: **130,720 / 129,256 / 131,257**; combined **391,233**.
- Blank Total All: **0** for each source.
- `C_999` rows: **40,102 / 39,677 / 40,636**.
- `NONC` commissioner rows: **2,955 / 2,904 / 2,993**. These are source-row counts, not cross-part pathway totals.

Independent Part_2A/Part_2 joins reproduce **0 / 1 / 2 violations** and **5 / 3 / 0 unmatched** Part_2A groups. May remains `NT230 / 05V / C_100`, **2 > 1**; June remains `RTG / 84H / C_502` and `RTG / 84H / C_999`, **2 > 1** each. The source values remain untouched. P2-U7 is preserved and diagnosed; Phase 2 is not reopened.

## Determinism and publication verification

Both real runs, and the notebook's separate run, reproduce generation ID:

**`f67b7342a30c4642a78864243142d910b84295dc7876ffb01c231cb8dc52627d`**.

Repeated runs have equivalent rows, order, values, missingness, dtypes, provenance and deterministic sidecar content. Reversed payload order produces a strictly equal frame. Run timestamps differ; the generation ID remains stable in this environment.

The audit independently recomputed the generation ID from the actual Parquet digest and deterministic block, checked both recorded artifact digests against actual files, and reconciled marker/sidecar/actual counts. Every legitimate publication verifies as valid with **541,363 rows**. Cross-version Parquet byte identity was not required or asserted.

The consumer contract remains essential: use a published trio only when `verify_publication` reports valid. Earlier interruption tests already establish old-valid, mixed-invalid and new-valid states around the marker-last commit; the final changes retain those checks and add count consistency and safe backup rotation.

## Notebook/documentation verification

Notebook 03 executes in an audit copy using the existing interpreter: **10 original code cells**, **11 including audit identification**, **zero errors**, **84.53 seconds**. The output equals production Parquet under strict dtype/value comparison, its deterministic manifest agrees, and publication verifies with the generation ID above.

Only the audit copy's output-directory assignment was redirected; its canonical bytes remain unchanged by this audit. Notebook code cells are identical to the prior closure's saved notebook code. It remains thin orchestration and display; no snapshot, acceptance or publication business logic was moved into cells.

The final methodology, D-039, assumptions and reports describe snapshot-derived binding, count reconciliation, valid-only backup rotation and verified restore. The first remediation report now has a clear **SUPERSEDED IN PART** banner linking to the final remediation. The original submission report's earlier supersession banner remains available.

The methodology correctly permits previous-valid state before replacement, detectable mixed-invalid paths during interruption, and new-valid state after marker-last commit, including a later caller failure. Consumption is conditioned on verification. Endpoint hashes alone are no longer presented as the source-binding mechanism.

**Advisory precision:** “reads exactly once” should mean **one authoritative acquisition plus an informational reread**, as demonstrated above. A residual `verify_publication` docstring also still overgeneralizes that any interruption leaves disagreement, although the governing methodology and writer documentation now state the correct state machine. These are wording inconsistencies, not remaining false-valid behaviour; this report records the exact observed semantics. No production/documentation fixes were made by the auditor.

The assumptions/methodology currently mark P2-U3 and P2-U5 as pending independent confirmation. This audit supplies that confirmation: **their Phase 3 ingestion obligations are addressed**, including per-source contract checks, intended completeness, month-bound revision identity and exact accepted-byte binding. Calendar month-end dates and the stock/flow analytical temporal model remain deferred. P2-U7 remains preserve-and-diagnose. P2-U1/U2/U4/U6 and historical download metadata are not silently declared resolved.

## Repository hygiene and phase boundary

`HEAD` and the peeled `phase-2-pass` tag still resolve to **`8f321473d286766d23ea4a3172b8f5b4d8e0e018`**. The only tag is `phase-2-pass`; no Phase 3 milestone exists. The Git index has no staged changes.

Exact diffs against the prior closure's saved Phase 3 modules show targeted changes: snapshot acquisition/delegation in ingestion; count/type verification and valid backup/restore logic in publication. Existing ingestion/cross-month tests are unchanged; the remediation tests and relevant docs changed as reported. The checked frozen Phase 1/2 files and dependency declarations are unchanged against the committed baseline.

Raw CSVs, canonical notebooks, production source/tests/docs and existing interim artifacts captured by the reproduction's protected-file hashes remained byte-identical before/after execution. Audit writes consist of this requested report and ignored evidence. No production output was overwritten by the audit.

Raw files, interim publications/markers/`.prev` files and audit copies remain ignored. `data/raw/manifest.json` remains the narrow intended tracking exception and is currently untracked, consistent with the intentionally uncommitted milestone. The existing worktree changes are preserved.

No Phase 4 analytical reshape, cleaning/imputation, modelling, SQL/KPI layer, provider enrichment, BI, ML or Spark implementation appeared. No source exception was repaired or capped. No commit, tag, push or milestone action was taken.

## New findings, if any

**No new BLOCKING or NON-BLOCKING correctness finding established in this focused audit.** The read-count and residual interruption-docstring wording notes above are **ADVISORY**. Neither invalidates exact snapshot binding, publication consistency or verified restoration demonstrated by the executable cases.

This PASS covers the authorized Phase 3 scope and tested guarantees; it is not a claim that every future input, concurrent writer pattern or downstream analytical interpretation has been audited.

## Final Phase 3 PASS checklist

- [x] Residual **P3-A03 CLOSED**: exact changed-and-restored counterexample preserves A and its digest; all validators/loaders use the cleaned private snapshot.
- [x] **P3-R01 CLOSED**: marker/sidecar/actual row counts and required marker types are checked; false-valid row metadata rejects.
- [x] **P3-R02 CLOSED**: failed retry preserves independently verified `.prev`; invalid/missing backups cannot claim restoration success.
- [x] **P3-A04 CLOSED** following closure of its remaining verification/recovery issues.
- [x] P3-A01/A02/A05/A06/A07 remain closed; no concrete regression found.
- [x] All **208 tests** pass, including all 98 frozen Phase 1/2 regressions.
- [x] Real April–June **541,363 × 125** output preserves source semantics, key, missingness, provenance and P2-U7.
- [x] Repeated/shuffled output and deterministic manifests agree; reported generation ID independently reproduced.
- [x] Notebook 03 executes without errors and remains thin orchestration.
- [x] Material documentation guarantees match implementation; minor wording caveats explicitly recorded.
- [x] P2-U3/P2-U5 ingestion obligations addressed; deferred analytical obligations remain deferred.
- [x] Raw data and Phase 1/2 contracts unchanged; repository hygiene and phase boundary maintained.
- [x] No new blocker; no Git milestone created by the auditor.

## Recommendation

Accept Phase 3 as complete for **Reproducible Multi-Month Ingestion & Provenance**. Carry P2-U7 and the explicitly deferred analytical/historical-provenance obligations into later phases without treating this ingestion PASS as their resolution. The advisory wording corrections can be included in routine documentation housekeeping.

**Phase 3 is ready for the project owner to create the Phase 3 Git milestone/tag.**

The auditor has not created that milestone or made production fixes.

**PASS**
