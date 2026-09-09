# Phase 4 final narrow independent closure audit

9 September 2026. Auditor: Codex. Scope: **Codex — Phase 4 Final Narrow Closure.md**, the final bounded remediation report, and residual P4-R01/R02/R03 from the two previous independent audits. Implementation claims were verified against code and independent fixture mutations. Previously closed findings received regression preservation only.

## Verdict: PASS

- **P4-R01 — CLOSED**
- **P4-R02 — CLOSED**
- **P4-R03 — CLOSED**
- **P4-A02 — CLOSED** (R01 and R02 closed)
- **P4-A03 — CLOSED** (R03 closed)
- **P4-A01 — remains CLOSED**
- **P4-A04 — remains CLOSED**
- **P4-A05 — remains CLOSED**

All named required closure conditions are met. No new material correctness, semantic, provenance or publication-integrity regression was established. **Phase 4 is ready for the owner's milestone decision.** This audit does not create a commit, tag or push.

## Repository and regression baseline

Branch **main**. HEAD and peeled **phase-3-pass** remain **073778b5ddf2fadf2629471d84ab12964cc0ebc1**. No staged changes or Phase 4 milestone exist. Frozen Phase 1–3 production code, tests and notebooks remain unchanged against the accepted Git baseline.

**323 tests collected in 0.81 seconds. 323 passed in 43.26 seconds, zero failed/skipped.** This is **208 frozen + 115 Phase 4** tests. The complete suite was run once; no production changes during this audit required another execution. Independent adversarial probes are recorded separately.

AST comparison against the preceding audit snapshot identifies only four changed existing functions: `validate_persisted_long`, `reconcile_long_against_wide`, `build_phase4_manifest`, `verify_phase4_publication`. Added helpers implement generation-ID calculation and strict verifier validation. Snapshot consumption, classification/time/DQ transformation, the long writer, deterministic-report view, publication orchestration and recovery functions are unchanged. Notebook 04's code-cell sources also exactly match the preceding snapshot; only its saved execution outputs changed during implementation.

**59 protected pre-existing files** retain their final-audit-start hashes, including raw/interim/processed data, source/tests, notebooks and existing documentation. Earlier audit reports/evidence were preserved. New audit artifacts are isolated under ignored `outputs/audit/phase4_final/`.

## P4-R01 — CLOSED: exact, NA-safe bound comparisons

**Location:** `src/nhs_rtt/transform.py:944`, `reconcile_long_against_wide`; the revised bound block begins at line 1005.

The lower-bound path rejects null expected metadata and any null actual lower bound before exact integer comparison. The upper-bound path compares actual and expected null masks first, permitting NA only where expected for the open band, then compares integers at non-null positions. This removes the nullable-equality/skip-NA reduction that caused the defect.

**Independent results** (`probes.json → R01`): valid data passes; all three legitimate final-band upper NAs remain valid; a missing lower, missing closed-band upper, numeric open-band upper, wrong numeric lower and wrong numeric upper each raise `LineageError`. Both exact prior broad attacks—all lower bounds NA and all upper bounds NA—are rejected. The checks use copied long frames and the real helper; no validator was mocked.

No residual skip-NA equivalent was found in this revised block. The unchanged value/lineage checks retain their prior regression tests.

## P4-R02 — CLOSED: persisted count comparison remains integer-exact

**Location:** `transform.py:793`, `validate_persisted_long`; reference arrays at lines 852–856 and Arrow count comparison at 900–912.

Both sides now use exact int64 arrays with separate null masks. The expected matrix uses `to_numpy(dtype='int64', na_value=0)` only as a storage placeholder, with missingness recorded separately. Actual values come directly from Arrow using `is_null()` and `fill_null(0)` before integer conversion. No pandas/float64 round trip lies on the pathway-count comparison path. Zero placeholders do not overwrite source values or equate source NA with zero.

**Independent results** (`probes.json → R02`): a single persisted batch containing zero, NA, `2**53+1`, `2**53+2`, signed Int64 maximum and minimum validates with exact serialized int64 values and zero value/NA/identity mismatches. The writer's actual Arrow values were checked directly.

The following serialized changes each fail:

- **2**53+1 → 2**53**: exact previous counterexample;
- **2**53+1 → 2**53+2**;
- zero → NA and NA → zero;
- Int64 maximum → maximum minus one;
- Int64 minimum → minimum plus one.

The signed-minimum fixture tests numerical transport/comparison only; a negative number is not endorsed as a legitimate NHS pathway count. Normal real-data counts remain nonnegative and fully reconcile. No new writer change or frozen ingestion change was needed.

## P4-R03 — CLOSED: fixed publication contract enforced

**Locations:** `transform.py:1377` (`REQUIRED_MANIFEST_OUTPUTS`), `:1398` (`compute_phase4_generation_id`), `:1540`/`:1585` (public/internal verifier).

The verifier now requires the exact five output entries at fixed canonical filenames. It checks identity/count/cardinality fields, physical hashes and byte sizes, actual Parquet row/column/name/schema claims, the 105-row band reference, canonical long schema, and agreement between the hashed JSON report and manifest. Missing entries cannot redefine a smaller accepted publication. Internal expected validation failures become structured `valid=False` results.

**All 28 independent mutations were rejected with a structured reason**, with no expected-validation exception (`probes.json → R03`):

1. Removed report JSON entry and file.
2. Removed report Markdown entry and file.
3. Removed band-reference entry and file.
4. Removed wide entry.
5. Removed long entry.
6. Stored generation ID set to WRONG.
7. Phase 3 generation ID set to WRONG.
8. Consumed Phase 3 digest set to WRONG.
9. Incorrect Phase 3 combined row count.
10. False Parquet schema.
11. False column count.
12. False ordered column names.
13. False byte size.
14. False output row count.
15. Incorrect reference row count.
16. Incorrect bands-per-parent.
17. False cardinality assertion.
18. Long rows unequal to wide × 105.
19. JSON report content/hash mismatch.
20. JSON report input identity contradicted the manifest, **with its new hash and byte size correctly recorded** to reach the consistency check.
21. Individually tampered long Parquet.
22. Old wide from a different input generation swapped into the current set.
23. Non-object output entry.
24. Redirected/noncanonical filename.
25. Unexpected output key.
26. Wrong phase identifier.
27. A syntactically valid but incorrect 64-hex Phase 4 ID.
28. A syntactically valid but incorrect consumed-input digest.

The last two establish that rejection is not merely a string-format check. This is a bounded integrity verifier, not a claim of cryptographic authenticity against replacement of every artifact and identity together.

### Independent generation-ID reproduction

The audit reconstructed the documented sorted JSON identity material itself, using the real wide/reference file hashes, Phase 3 identity and row counts, and SHA-256 hashed it **without calling the production compute helper**. It matches every fixture manifest ID.

Four executions with block_rows **1, 1, 2, 4** over three parents retain the same logical ID. Fixed configuration reproduces all Parquet bytes. Different block sizes—including a nondivisible final block—retain strict logical frame equality and deterministic report equality while legitimately changing the physical long hash. Each manifest separately binds its actual long hash. The accepted ID design remains unchanged.

### Representative publication/recovery preservation

The audit deliberately did not repeat the previous exhaustive lifecycle matrix. Representative injected failures establish:

- before the first replacement: coherent old generation remains valid;
- during replacement: mixture is detectably invalid;
- immediately after marker replacement: coherent new generation remains valid;
- valid previous generation restores in each case;
- clean retry succeeds after each case;
- a malformed current manifest does **not** rotate over a valid backup: every `.prev` digest stays unchanged, and restoration still succeeds.

Evidence: `probes.json → recovery`. The verifier hardening therefore preserves the accepted marker-last lifecycle and recovery behavior.

## Real-data verification

The strict Phase 4 verifier passes on the actual publication. Phase 3 also verifies, and its identity remains unchanged:

- Phase 3 generation: **f67b7342a30c4642a78864243142d910b84295dc7876ffb01c231cb8dc52627d**.
- Consumed Phase 3 SHA-256: **e5e1a0a40abf447c581895837126fe85eccd8dacc56a75e80c730c5bed2d188f**.
- Phase 4 logical generation: **c15eecd959e2598e918ffb81f524373ce3de681071cd9f6a2a4f130c77267c86**.

Strict frame equality confirms all 125 Phase 3 columns survive unchanged in **541,363 × 138** analytical-wide output. The remediated mandatory validator checks all **56,843,115** persisted long observations in **217 batches**, **50.624 seconds**, with **zero value, NA-state and identity mismatches**.

Observed counts match without adjustment:

- numeric **39,478,695**;
- explicit zero **35,174,239**;
- positive **4,304,456**;
- source NA **17,364,420**;
- all-band-missing rows **109,474**;
- Total missing **391,233**;
- Total All missing **0**.

An independent month/provider/commissioner/treatment-function lookup, not the frozen conformance helper, confirms April/May/June violations **0 / 1 / 2** and unavailable comparator counts **5 / 3 / 0**, with row flags agreeing exactly. Evidence: `real_validation.json`, `independent_dq.json`.

This narrow closure runs the revised full persisted validator and replays its exact previous counterexamples. It does not unnecessarily repeat the previous audit's separate complete cell-scan implementation.

## Notebook and closed-finding preservation

**Notebook 04 executed once: 12 code cells, zero errors, 280.72 seconds.** Its primary 40,000-row-block reproduction matches all three production Parquet hashes byte-for-byte. Its built-in 25,000-row-block rerun also verifies, retains the same logical generation ID and deterministic report content, and legitimately has a different physical long hash. Nonfatal local kernel/selector warnings did not affect execution.

Notebook code is unchanged from the prior reviewed version and remains thin orchestration/demonstration. No authoritative transformation logic migrated into it. The audit redirects only its main and alternate output locations; the canonical notebook is not overwritten.

P4-A01 remains closed: its immutable verified snapshot loader is AST-unchanged, and the complete regression retains its race tests. P4-A04 remains closed: logical/physical determinism survives independent multi-configuration executions and the normalized report comparison. P4-A05 remains closed: comparator and structural-DQ code is unchanged; real reporting dates remain **datetime64[us]** and the full suite retains the four comparator-state and serialization checks. Current documentation describes exact integer validation, NA-safe bounds, strict manifest checks and the valid post-marker interruption state.

## Material regressions and optional observations

**No new material regression was established. No required findings remain.** Scope stayed within R01/R02/R03 and their regression preservation.

Optional future architecture, additional general hardening and the already deferred Phase 5+ work were not expanded into acceptance conditions. No new optional work is required for this milestone. The current tests and this audit are evidence for the named contracts, not an assertion that arbitrary concurrent multiwriter schedules or OS power loss have been exhaustively simulated.

## Evidence and reproduction

Existing interpreter: `C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe`. Normal sandbox escalation was used where that interpreter required it; no alternate environment, dependency installation or production edits were made.

```powershell
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' -m pytest -q
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' -m pytest --collect-only -q
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase4_final/probes.py
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase4_final/real_validation.py
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase4_final/check_dq.py
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase4_final/execute_notebook.py
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase4_final/integrity.py
```

Corresponding JSON evidence, collection output, executed notebook, redirected publications, fixture mutations, reviewed snapshot, AST comparison and protected before/after hashes are retained under ignored `outputs/audit/phase4_final/`. Fixture construction reuses existing test helpers; the assertions, mutations, generation-ID calculation and independent real DQ matching are audit-authored. Existing original/focused audit evidence remains intact.

## Final Git state and milestone recommendation

```text
 M README.md
 M docs/assumptions.md
 M docs/data_dictionary.md
 M docs/decisions.md
?? docs/audit_handover_phase4.md
?? docs/phase4_codex_audit.md
?? docs/phase4_codex_closure_audit.md
?? docs/phase4_codex_final_closure_audit.md
?? docs/phase4_transformation.md
?? notebooks/04_transformation_analytical_dataset.ipynb
?? src/nhs_rtt/transform.py
?? tests/test_transform.py
```

Only this final report and ignored audit evidence were authored by this audit. **Recommend Phase 4 milestone creation after owner review.** The previous PASS WITH CHANGES reports remain historical records; this final closure supersedes their outstanding-finding status. No commit, tag, push or `phase-4-pass` was created.
