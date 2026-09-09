# Independent Phase 4 audit

9 September 2026. Auditor: Codex. Scope: the user-supplied **Independent Audit — NHS RTT DataAnalytics Phase 4** prompt, current repository, handover and implementation report. The implementation report was treated as claims to falsify, not acceptance evidence. No production fixes or milestone actions were authorized or performed.

## Verdict: PASS WITH CHANGES

The current real-data transformation is correct under complete independent inspection, and the implementation is fundamentally sound. **Five bounded findings below require closure before milestone acceptance.** The input boundary and output acceptance/publication controls do not yet support the advertised verified, reproducible lineage guarantees. This verdict is not permission to create `phase-4-pass`.

### Established results

- Full regression: **237 passed in 16.07 seconds**, no failures or skips. Separate collection: **237 tests in 0.60 seconds**. This is 208 unchanged upstream tests plus 29 Phase 4 tests.
- HEAD and peeled `phase-3-pass` both equal **073778b5ddf2fadf2629471d84ab12964cc0ebc1**. No staged changes; only the pre-existing documentation modifications and new Phase 4 files were present before the audit. No tracked upstream production code, tests or notebooks differ from HEAD.
- Phase 3 verifies before and after audit: **541,363 rows**, generation **f67b7342a30c4642a78864243142d910b84295dc7876ffb01c231cb8dc52627d**. Parquet SHA-256 **e5e1a0a40abf447c581895837126fe85eccd8dacc56a75e80c730c5bed2d188f**. Protected raw/interim/processed files, source, tests and canonical notebooks retain their pre-audit hashes.
- Wide: **541,363 × 138**. Strict pandas frame comparison confirms all 125 input columns, dtypes, values, NA states, order and provenance unchanged. Both the reporting-month analytical grain and source-file/row grain are unique.
- Long: **56,843,115 × 14**, **19,088,167 bytes**, **68 row groups**. Complete positional streaming comparison checked every value/null state, all nine parent/provenance fields, every order/label and week boundary against the original Phase 3 row order and physical source-band header. Exactly 105 ordered observations per parent; no missing, extra or duplicate derived keys. **Zero discrepancies.** This comparison does not call the production reshape or reconciliation helper.
- All **39,478,695 numeric cells** reconcile: **35,174,239 zeros**, **4,304,456 positive counts**; **17,364,420 source-NA cells** remain NA. The full scan took **32.64 seconds**; this includes parent and metadata comparisons, not only measures.
- Notebook 04 audit copy: **11 code cells, zero errors, 114.10 seconds**. Only the output-directory assignment was redirected. Its three regenerated Parquets are byte-identical to the current production artifacts. Canonical notebook unchanged.
- Reproduced dense write: **82.411 seconds**, **566.2 MiB peak tracemalloc**, 14 blocks. The compact artifact and streaming practicality claims are plausible and reproduced. Tracemalloc is not process RSS or proof of absence of OS swapping; no independent OS paging measurement was made. Full materializing 56.8M-row outer-merge reconciliation was unnecessary: the audit used full streaming reconciliation, while the notebook executed its existing May-only reconciliation.

## Required findings

### P4-A01 — High: verified input bytes are not bound to consumed bytes

**Category:** correctness and provenance. **Location:** `src/nhs_rtt/transform.py:206`, `load_verified_publication`; verification at line 218, mutable-path parsing at line 228 and a separate later hash at line 244.

**Evidence:** `outputs/audit/phase4/probes.json`, `verify_read_race` and `restore_race`. After genuine verification of an isolated two-row Phase 3 publication, replacing one count with 999 leaves row count/key/provenance-column checks satisfied and the altered frame is accepted under the old generation. More decisively, changing the on-disk count to 888 only during the real pandas read, then restoring the original bytes, yields an accepted frame containing 888 while the reported hash matches the original and final publication verification is valid. The probes use the real verifier/parser and real fixture files, not fabricated verifier responses or hashes.

**Impact:** simultaneous upstream publication/replacement, or change-and-restore, can detach analytical values from the claimed accepted generation. A second endpoint hash alone cannot close this.

**Minimal remediation:** acquire a private snapshot/buffer, verify the marker/sidecar/content relationship for those exact bytes, and parse only that immutable content. Derive the recorded input digest from that same buffer. Implement this at the Phase 4 consumer without reopening accepted upstream findings or changing frozen Phase 3 behavior.

**Closure tests:** changed-after-verification and changed/restored-during-read probes must either reject or return only the verified snapshot values; frame, hash and generation must agree. Preserve existing invalid-marker/hash/row-count rejection tests.

### P4-A02 — High: normal long acceptance is only cardinality; optional reconciliation is incomplete

**Category:** insufficient validation and lineage correctness. **Location:** `transform.py:583` (`write_waiting_band_long`), especially 613–634; `:662` (`reconcile_long_against_wide`), merge at 680–687; `run_phase4` optional check at 1043–1046.

**Evidence:** `probes.json → normal_bad_band_order`: controlled chunk fault sets every band order to 1, preserving 210 rows; normal `run_phase4` returns **ok=True**. This is fault injection testing the acceptance guard, not evidence that the present normal mapper produces this defect. Separately, the unmodified reconciliation helper accepts **211 observations for 210 expected cells** when a duplicate observation is appended, reporting zero mismatches. It also accepts every band label, provider code and source SHA changed to `WRONG`. The outer merge has no one-to-one validation and only compares count values at source-file/row/order keys. The in-memory builder's stronger cardinality helper is not called by the streaming production path.

**Impact:** total row count does not prove one observation per source cell, correct metadata or faithful lineage. Even selecting optional full reconciliation does not establish its documented contract.

**Minimal remediation:** add a mandatory bounded-memory check against the persisted long output, validating exact schema, parent/order/label/bounds/provenance, values and null states. A positional streaming comparison is practical here; the independent full audit scan took about 33 seconds. Full materializing melt/merge can remain optional. Harden the optional helper with exact expected count, unique keys/one-to-one merge and matching identity fields, or route it through the same complete validator. Do not merely invoke the current incomplete helper on normal runs.

**Closure tests:** reject repeated/missing/reordered bands, swapped cell values, zero↔NA changes, wrong parent/SHA/label/bounds, and extra duplicates. Include faults introduced after serialization so write-side checks alone cannot pass. Valid real data must retain exact conservation and missingness.

### P4-A03 — High: failed reruns can leave a mixed output set with an old success report

**Category:** publication correctness and provenance. **Location:** `transform.py:1032` through `:1061`, direct writes in `run_phase4`; long writer opens final destination at line 609. Associated claim: `docs/phase4_transformation.md:66`.

**Evidence:** `extra.json → failed_rerun`. Publish a fixture with first-band count 3, then publish a valid changed Phase 3 fixture with count 99. Inject a long-write failure during rerun. The final wide now contains **99**, the old long still contains **3**, and the old successful report is byte-for-byte unchanged. No output verifier/commit marker exposes the mixture. Parquet metadata inspection also shows **none of the three Parquets carries phase3_generation_id or phase3_parquet_sha256**. These fields appear in the JSON report only; the Markdown report displays only a generation prefix. Thus “recorded in every Phase 4 output” is false, and the report has no hashes binding its output set.

**Impact:** consumers can read a plausible but incoherent analytical publication after failure. Raw source SHA columns correctly identify raw sources but do not bind the complete Phase 4 output generation.

**Minimal remediation:** stage a complete generation, validate it, and commit a manifest/marker last binding the input identity and hashes/schemas/counts of all outputs. Require consumer verification; preserve a previous valid generation or leave an explicit invalid state on interruption. Equivalent generation-directory publication is acceptable; no specific architecture is mandated. Correct the per-output metadata claim to the implemented, verifiable lineage mechanism.

**Closure tests:** inject failure before/during each replacement and report/marker write, including a retry after failure. A consumer must see the coherent old generation, coherent new generation, or a detectable invalid state, never accept the mixed set. Swapping an old report or a single Parquet must fail verification.

### P4-A04 — Medium: determinism claims exceed executable behavior

**Category:** documentation and reproducibility. **Location:** `docs/phase4_transformation.md:307–311`; `docs/decisions.md` D-040 determinism bullet; `tests/test_transform.py`, `test_end_to_end_is_deterministic`.

**Evidence:** `probes.json → determinism`. Identical input and block_rows=1 repeat byte-identically. Changing to block_rows=2 changes the long hash from `6f2aec177db82b49b3791362bd9c846af1e3e9ad53d05f15f537519d3ba355bd` to `0d422bf1c646c6851a307c59926ee32c36a65de1ce9603439d2b62042adbf903`; row groups change from two to one. Wide/reference remain byte-identical. The existing test uses block_rows=1 for both runs, so it never tests the stronger claim. JSON also varies in benchmark duration/allocation/path and configuration, not only generated_utc.

**Impact:** consumers cannot use raw long-file hashes across block-size changes as an analytical determinism test. This does not establish value/order nondeterminism.

**Minimal remediation:** document byte repeatability only under fixed writer/environment/configuration; define content/schema/order determinism across block sizes separately. Identify all intentionally variable report fields. Canonicalizing row groups is optional unless byte identity across configurations remains a requirement.

**Closure tests:** repeated fixed-configuration hashes; strict logical equality across differing block sizes, including nondivisible final blocks; stable report comparison after explicitly separating runtime/path/configuration metadata.

### P4-A05 — Medium: qualify DQ semantics and correct field-contract inconsistencies

**Category:** semantic documentation. **Location:** `transform.py:324–363`, particularly `has_match` at 356; `docs/phase4_transformation.md:124–125` and `:266`; matching field dictionary entries in `docs/data_dictionary.md`; date type at `docs/phase4_transformation.md:108`.

**Evidence:** `extra.json → null_counterpart_verified`: a verified fixture has a Part_2 row whose Total All is NA and a same-key Part_2A row. The latter receives `dq_part2a_no_matching_part2=True`. Therefore the flag means **no matching non-null Part_2 count**, not necessarily “no Part_2 row.” The frozen conformance helper makes the same distinction; this is not an upstream regression and does not justify changing frozen behavior. All real Total All values are present, so real counts are unaffected. Section 9 additionally says structural categories are “not a dq_ flag,” although structural missing bands/Total are deliberately flagged elsewhere. The declared date dtype is datetime64[ns], but actual output is **datetime64[us]** in the installed pandas environment.

**Impact:** downstream readers could mistake unavailable comparator values for missing parent identities or structural conditions for anomalies, or rely on an inaccurate schema contract.

**Minimal remediation:** explicitly document the inherited non-null-comparator meaning and unavailable-comparison case; distinguish factual DQ conditions from errors consistently. Keep frozen helper semantics intact. Correct the date-resolution contract or explicitly enforce the declared resolution. No values need repairing.

**Closure tests:** missing counterpart identity, present counterpart with NA count, and present numeric counterpart; verify documented outcomes and unchanged source values. Confirm declared date dtype against serialized schema. Review all affected field tables for consistent structural-condition wording.

## Semantic and scope assessment

The five classifications follow frozen `docs/rtt_semantics.md` §2 and §3 and the aggregation guide. Part_2/2A snapshot classifications expose an already documented distinction; the month-start date is clearly a sortable reporting anchor, not an event timestamp. No new resolution of P2-U5 is implied. C_999 and NONC are retained and neutrally classified; names are labels, not organisation-type inference. No cross-part aggregation engine or KPI logic was introduced.

The 105-row reference reuses the authoritative frozen band generator/parser. Independent checks confirm first band 0–7 days, intermediate derived formula 7n+1 through 7(n+1), final lower bound 729 with null upper bound. P2-U6 explicitly permits these as derived metadata based on five worked examples and the stated sequence. Retain the fields and derived qualifications; this is not a new semantic resolution or a premature analytical dimension.

Independent relationship matching used month/provider/commissioner/treatment-function identities without invoking the frozen conformance helper. Violations are April/May/June **0/1/2**; unmatched counts **5/3/0**. Exact keys: May NT230/05V/C_100; June RTG/84H/C_502 and C_999. All retain Total All=2 against Part_2=1. Synthetic cross-month and each dimension mismatch do not falsely match. Duplicate parents are rejected by the public wide path; its internal drop_duplicates is not reached as an accepted duplicate-grain result. Partial missing bands remain NA beside explicit zeros.

All four row-level flag totals agree with the JSON report. All-band missing **109,474**, Total missing **391,233**, Total All missing **0**. C_999 rows by month **40,102 / 39,677 / 40,636**; NONC **2,955 / 2,904 / 2,993**. These are row counts, not pathway totals. Reports separate row conditions from dataset diagnostics; mapping churn remains diagnostic. Mapping diagnostics are delegated to unchanged frozen code, not an independently rebuilt ODS classification. No substantive trend/performance conclusions, dimensional model, SQL/DuckDB, calendar dimension, surrogate keys, BI, ML, Spark or infrastructure scope leakage was found.

P2-U1 estimated national headline, P2-U2 unknown-clock interpretation and P2-U4 ODS organisation classification properly remain unresolved. Calendar month-end modeling and downstream temporal analysis remain Phase 5; KPI thresholds remain Phase 7; P2-U7 stays preserve-and-diagnose. No accepted Phase 3 finding is reopened.

Optional robustness: `_dense_long_chunk` routes Int64 counts through float64, exact only within the stated 2**53 precision range. Present NHS counts are far below that range and reconcile completely; an integer-preserving Arrow path or explicit bound would strengthen future reuse. This is not an additional milestone blocker.

## Reproduction and evidence

Use the existing interpreter `C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe` from the repository root. The interpreter intermittently required normal sandbox escalation; authorized runs succeeded without installing dependencies or switching environments.

```powershell
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' -m pytest -q
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' -m pytest --collect-only -q
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase4/scan.py
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase4/probes.py
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase4/extra.py
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase4/execute_notebook.py
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase4/finish.py
```

Scripts and results reside in ignored `outputs/audit/phase4/`: `real_scan.json`, `probes.json`, `extra.json`, `notebook.json`, `executed_notebook.ipynb`, `reproduction.json`, `test_collection.txt`, protected before/after hashes, isolated fixtures and notebook outputs. Synthetic probes reuse test fixture construction only; adversarial expectations and mutations are audit-authored. The full real-data scan independently indexes the physical source header instead of reusing transform mappings. No additional tests were added to the production suite; standalone audit probes record both passing invariants and accepted counterexamples. Preserve original before-hash evidence when re-running the harness.

Notebook reproduction hashes:

- Wide: `474da0fe30896c3b89c5c28638eff9169b56964e0ef15b909bc4bae19e63d419`.
- Long: `8aafa27d1a81ad8dc031989bd529d9ebb21afd716096664af92412474d4d1321`.
- Band reference: `0d61346371a1297de9adfe177ddc3a21a38ff5fe4b064385fd20ad1591e4c1b6`.

## Final Git state and milestone recommendation

```text
 M README.md
 M docs/assumptions.md
 M docs/data_dictionary.md
 M docs/decisions.md
?? docs/audit_handover_phase4.md
?? docs/phase4_codex_audit.md
?? docs/phase4_transformation.md
?? notebooks/04_transformation_analytical_dataset.ipynb
?? src/nhs_rtt/transform.py
?? tests/test_transform.py
```

Only `docs/phase4_codex_audit.md` and ignored audit evidence were authored by this audit. Existing work was preserved. No commit, tag or push was made. **Do not create the Phase 4 milestone yet.** After P4-A01–A05 are remediated, run focused independent closure, the full regression, isolated notebook reproduction and complete persisted-output reconciliation. A clean closure would support the owner's milestone decision.
