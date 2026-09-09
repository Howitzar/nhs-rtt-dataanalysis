# Phase 4 focused independent closure audit

9 September 2026. Auditor: Codex. Scope: the user-supplied **Codex — Phase 4 Focused Closure Audit.md**, the remediation report, the original five findings, and the actual repository. Remediation assertions were treated as claims requiring independent evidence. No production code was modified.

## Overall verdict: PASS WITH CHANGES

- **P4-A01 — CLOSED**
- **P4-A02 — NOT CLOSED**
- **P4-A03 — NOT CLOSED**
- **P4-A04 — CLOSED**
- **P4-A05 — CLOSED**

The remediation substantially improves Phase 4. The current real artifacts remain correct, and the staged publication/recovery architecture handles the exercised ordinary failures. Remaining blockers are localized: incomplete manifest validation, nullable-bound comparisons in the secondary reconciler, and integer precision in the newly authoritative persisted validator. No architectural redesign is required. **Do not create the Phase 4 milestone yet.**

## Repository, regression and preservation

Branch **main**; HEAD and peeled `phase-3-pass` both **073778b5ddf2fadf2629471d84ab12964cc0ebc1**. The milestone has not moved. No Phase 4 commit/tag/push was made. The baseline diff contains the existing Phase 4 additions and documentation modifications; frozen Phase 1–3 production code, tests and notebooks remain unchanged. The remediation changed `transform.py`, `test_transform.py`, Notebook 04 and related documentation/reports; the three real Parquet hashes remain identical to the original audit. No unrelated implementation scope was found.

**279 tests collected in 0.56 seconds; 279 passed in 26.58 seconds; zero failed/skipped.** This is 208 frozen plus 71 Phase 4 cases. Existing tests cover useful snapshot/read races, serialized corruption, basic publication replacement failures, deterministic configurations and comparator states. They do not cover the residual counterexamples below. Independent probes are separate standalone audit scripts, not additions to the repository test suite.

**58 protected files** retain their closure-start SHA-256 values, including raw/interim/processed files, source, tests, canonical notebooks and existing documentation. Earlier audit evidence was preserved. A snapshot of the reviewed Phase 4 source/test/notebook/documentation is saved in the new evidence directory.

## P4-A01 — CLOSED: immutable verified input consumption

**Implementation:** `src/nhs_rtt/transform.py:284–341`, `load_verified_publication`. The function copies the three publication members into a private temporary directory, verifies the completed snapshot with unchanged Phase 3 verification, hashes its Parquet and parses that snapshot only. Cleanup occurs in `finally`.

**Independent evidence:** `focused.json → A01` and `focused.py`.

- Replacing the complete live trio before copying yields the coherent new generation and its count 99.
- Replacing the live trio between the first and subsequent member copies creates a mixed snapshot that fails the real SHA check. A private directory alone would not suffice; the completed-snapshot verification is what rejects the mixture.
- Replacing live files after snapshot completion but before verification, after verification, during the real pandas read, or during the read followed by restoration yields only the original verified snapshot count 3 and its original digest/generation.
- Individually mixing each trio member from another generation is rejected. Each missing member is rejected.
- All observed private snapshot directories were removed.

The probes changed live fixture publications, never the private snapshot, and used the real verifier/parser and hashes. The returned frame is now bound to the same verified bytes as its recorded identity. No frozen Phase 3 changes are necessary.

## P4-A02 — NOT CLOSED: two bounded validation defects remain

The main remediation is effective: `run_phase4` mandatorily calls `validate_persisted_long` on staged serialized output before commit. Its positional reference is justified by the explicit parent-major writer/order contract and the unique source-row grain. The independent real scan confirms that contract. The validator obtains canonical labels independently of the reshape and compares all nine parent fields. It does not require materializing the long dataset.

**Passing independent corruption checks:** 25 serialized mutations were rejected, covering duplicate/missing/extra observations, reordered/repeated bands, wrong order/label, wrong or null lower/upper bounds, numeric upper bound on the open band, swapped values, zero→NA, NA→zero, each of the nine identity fields, and a count type changed to float64. An additional fault introduced after the real writer serialized the file was rejected by normal `run_phase4` before commit; the previous generation remained valid. Evidence: `focused.json → A02`, `final_probes.json`.

### P4-R01 — Medium: secondary reconciliation accepts missing band bounds

**Exact location:** `transform.py:985–994`, `reconcile_long_against_wide` lower/upper-bound comparisons.

**Reproduction:** start with a valid 315-row long frame and replace every `wait_band_lower_weeks` with nullable NA. The unmodified helper returns success, including `identity_mismatches: 0`. Repeat with all `wait_band_upper_weeks` set to NA: it again succeeds, although 312 closed-band upper bounds should be numeric. See `focused.json → reconcile.lower_null / upper_null`.

**Cause/impact:** nullable equality produces NA; pandas `.all()` skips NA by default. An unavailable bound therefore does not become a failed comparison. The helper is correctly labeled secondary now, but still falsely claims exact bounds/identity checking. This affects its in-memory diagnostic, not the mandatory persisted validator, which rejected these null-bound mutations.

**Minimal remediation:** explicitly compare expected/actual null masks, require non-null lower bounds, and compare numeric values only at valid positions. Alternatively ensure unknown comparisons become false after separately permitting only the expected open-band null. Do not rely on skip-NA reductions.

**Closure test:** correct open-ended upper NA passes; missing lower, missing closed-band upper and numeric open-band upper each fail. Retain successful duplicate, label and identity rejection tests.

### P4-R02 — Medium: new persisted validator rounds unequal Int64 values to equality

**Exact location:** `transform.py:843–844` creates a float64 reference matrix; `:889–899` converts serialized counts to float64 before comparison, inside `validate_persisted_long`.

**Reproduction:** set a source/wide count to **9,007,199,254,740,993 (2**53 + 1)**. The remediated writer correctly serializes that exact Int64 value. Change only the persisted count to **9,007,199,254,740,992 (2**53)**, retaining the int64 schema and null mask. The mandatory validator accepts it with `value_mismatches: 0`. Evidence: `focused.json → integer_writer` and `A02.rounded_large_integer`.

**Cause/impact:** both distinct integers round to the same float64 value. This is a newly introduced validation defect in the remediation's authoritative gate, not a defect in the new integer-preserving writer. Present NHS values are far below this range and independently reconcile completely. Nevertheless, the gate does not prove the full nullable Int64 contract it now claims.

**Minimal remediation:** use an integer reference matrix plus a separate null mask, and read Arrow count arrays with integer-preserving conversion. The actual batch conversion must also avoid pandas' nullable-int-to-float default. Compare exact integers only at non-null positions.

**Closure test:** validate unchanged 2**53+1 beside zeros and NA; reject its ±1 mutations on disk. Include values near signed int64 limits and batches containing both large integers and nulls. Retain all existing real-data counts and mutation tests.

**New-regression classification:** P4-R02 is separately identified as a defect in newly added validation code. The optional `_dense_long_chunk` change itself passes: it preserves the tested large integer, zeros, positives and NA, with Arrow int64 output. P4-R01 is a remaining hole in the hardened secondary helper. Neither indicates corruption of the current real output.

## P4-A03 — NOT CLOSED: manifest consumer gate does not enforce its full contract

### What the remediation successfully closes

Private staging, mandatory long validation, marker-last replacement, verified-current backup rotation and verified restoration are present. Independent tests exercise:

- 12 before/after failures around all six output/manifest replacements, including immediately before and immediately after marker replacement;
- 8 staging/generation/report/validation/manifest/precommit failures, plus wide and reference serialization failures;
- failure at each of the 6 backup-rotation copies and each of the 6 restoration destination copies;
- retry/recovery after those failures;
- all old/new output-member swaps, individual byte tampering and missing outputs under an intact manifest;
- missing, corrupt and unrelated extra `.prev` components.

Observed states were coherent old, coherent new or detectably invalid. Restoration/retry succeeded for complete valid backups. Missing/corrupt backups were refused; an unrelated extra backup file was harmless. An old reference file with identical bytes is correctly accepted—different publication dates do not make identical content a mixture. After the manifest commit point, a fault can leave the coherent new generation valid; documentation should describe this permitted state instead of implying every interruption is invalid.

Evidence: `publication.json`, `publication.py`, `final_probes.json`. These are deterministic file-operation fault injections on isolated fixtures, not simulated power loss or an exhaustive concurrent multiwriter test. They support the staged architecture; they do not excuse the consumer-gate defects below.

### P4-R03 — High: missing manifest members and false identity/schema metadata are accepted

**Exact location:** `transform.py:1453–1524`, `verify_phase4_publication`; particularly the unrestricted output-entry loop at 1489, limited actual-metadata comparison at 1507, unchecked identity returns at 1521–1522. Identity construction is at `build_phase4_manifest:1375–1384`.

**Independent reproductions** in `publication.json → manifest`:

1. Remove `report_json` and `report_md` entries from an otherwise valid manifest, then delete both report files: **valid=True**.
2. Remove the `wait_band_metadata` entry and delete its Parquet: **valid=True**.
3. Replace `phase4_generation_id` with `WRONG`: **valid=True**, returning that string.
4. Replace the Phase 3 generation and consumed hash with `WRONG` and combined_rows with 999: **valid=True**, even though the bound report retains the real identity/count.
5. Set a Parquet entry's schema to `['WRONG']`, columns to 999 and bytes to 1: **valid=True**.
6. Set reference row count to 999, bands_per_parent to 1 and the cardinality assertion to false: **valid=True**.
7. Remove the wide entry: the gate raises **KeyError**, rather than returning its documented invalid result.

These tests change the manifest only, except for deleting the deliberately omitted files. They do not replace the output hashes or fabricate a complete alternative publication.

**Impact:** the verifier checks whichever members happen to be listed, rather than the complete required publication. It trusts a generation ID it never recomputes and input identity it never reconciles with the hashed report. Recorded schema/byte/count claims are only partly checked. A malformed manifest can therefore mark an incomplete publication valid or misattribute its source generation. Backup eligibility/restoration inherit this weak verifier.

**Minimal remediation:**

- Require the exact mandatory output keys and canonical local filenames; reject missing/duplicate/redirected members and malformed entries with structured invalid results.
- Validate all required manifest field types and values, including phase, positive/nonnegative counts as appropriate, fixed 105-band contract and 105-row reference contract. Reconcile Phase 3 combined_rows with wide rows.
- Verify actual size, row count, column count, ordered names and schema for every Parquet as claimed; check reports are present, hashed and parseable where used for consistency.
- Recompute `phase4_generation_id` from the defined identity material and reconcile the manifest's Phase 3 identity with the hashed JSON report and its input rows. Validate relevant report/output counts rather than merely trusting repeated labels.
- Keep snapshot-based Phase 3 consumption and marker-last publication unchanged; this is a bounded verifier hardening task, not a request for cryptographic authentication or a redesign.

**Closure tests:** every mutation above must return `valid=False` without exceptions; intact generations, valid backup restore, fixed-config repeats and differing-block-size generations must still pass. Re-run the meaningful interrupted-commit/retry cases after hardening so invalid current manifests cannot qualify for backup rotation.

**Generation-ID design judgment:** stability across block_rows is appropriate within the documented writer/environment contract. The ID uses Phase 3 identity, wide/reference hashes and cardinality; the validated long is functionally determined by wide and the band contract. Its physical hash remains separately bound in the manifest. Independent fixed/different-block runs confirm this design. The defect is failure to validate the declared ID/manifest, not omission of the physical long hash from the logical ID. This is integrity checking, not protection against someone deliberately replacing every artifact and recomputing a wholly new manifest.

## P4-A04 — CLOSED: determinism contract corrected

Synthetic block_rows **1, 1, 2, 4** over three parents include a nondivisible final block. Fixed repetition reproduces all Parquet bytes. Different block sizes retain strict frame equality—schema, dtypes, values, NA, row order and lineage—while long-file hashes differ. Wide/reference bytes and logical generation ID stay stable. The normalized report view is equal across those runs. A changed analytical DQ total remains visible in that view; it is not filtered out.

Notebook 04 independently reruns the real data at **40,000 and 25,000** block sizes. Wide/reference hashes match across both, the long hashes legitimately differ, the logical generation stays **c15eecd959e2598e918ffb81f524373ce3de681071cd9f6a2a4f130c77267c86**, and deterministic report views match. The 40,000-block reproduction matches all three production Parquets byte-for-byte.

`VARIABLE_REPORT_FIELDS` removes timestamps, runtime/allocation/path and block-layout diagnostics, retaining analytical counts and validation outcomes. Current methodology and D-041 describe the revised distinction. D-040 still contains the historical pre-remediation wording; D-041 explicitly records its correction. Marking that old bullet superseded would improve navigation but is not a new blocker. The manifest itself also contains physical output hashes, sizes, schemas and report hashes that can vary; its logical generation ID must not be confused with byte determinism of the whole manifest.

## P4-A05 — CLOSED: comparator semantics, structural flags and date resolution

Four independently published synthetic comparator states produce the intended results:

- absent Part_2 identity: unmatched true, greater-than false;
- existing Part_2 with NA Total All: unmatched true, greater-than false;
- numeric conformant comparator: both false;
- numeric violation: unmatched false, greater-than true.

Strict source-frame comparison passes in each case: no missing comparator is imputed, and no violation is capped. Methodology, dictionary, helper docstring and report wording now identify the missing **usable non-null comparator**, including both absence and NA-value cases. Frozen semantics are unchanged.

The revised non-mutually-exclusive categories distinguish factual flags, structurally expected conditions, anomalous conditions and legitimate classifications; structural flags no longer contradict a blanket “never dq” rule. Reporting date is explicitly **datetime64[us]** in memory and **timestamp[us]** in Parquet in all four fixtures and real data, matching the documentation and report dtype contract. Month-start remains an axis anchor, not an event timestamp. No deferred temporal/ODS/KPI issue was silently resolved.

## Real-data and notebook closure evidence

**Phase 3 valid and unchanged:** generation **f67b7342a30c4642a78864243142d910b84295dc7876ffb01c231cb8dc52627d**; consumed Parquet SHA-256 **e5e1a0a40abf447c581895837126fe85eccd8dacc56a75e80c730c5bed2d188f**.

**Phase 4 current publication verifier returns valid**, logical generation **c15eecd959e2598e918ffb81f524373ce3de681071cd9f6a2a4f130c77267c86**. This is supplemented by independent content evidence; it is not treated as proof that the verifier handles malformed manifests.

- Wide **541,363 × 138**; all input columns strictly equal the verified Phase 3 frame.
- Long **56,843,115 × 14**, 68 row groups, **19,088,167 bytes**.
- Mandatory persisted validator: **217 batches**, **41.445 seconds**, zero value/NA/identity mismatches.
- Separate original-audit positional scan: all **56,843,115 cells** and all nine identities, orders, labels and week bounds checked independently, **38.57 seconds**, zero discrepancies. This scan uses original source header positions and integer arrays, not the production validator's float mapping.
- Numeric **39,478,695**: zero **35,174,239**, positive **4,304,456**; NA **17,364,420**.
- All-band-missing rows **109,474**; Total missing **391,233**; Total All missing **0**.
- April/May/June P2-U7 violations **0 / 1 / 2**; unmatched **5 / 3 / 0**. Independent matching also confirms unchanged C_999/NONC counts.
- Notebook 04: **12 code cells, zero errors, 240.35 seconds**, including its second real transformation and May in-memory reconciliation. Only the primary and alternate output destinations were redirected to this audit directory. It remains orchestration/demonstration over production functions. Canonical notebook unchanged. Nonfatal local kernel/selector warnings did not affect execution.

## Evidence and reproducibility

All new execution artifacts are under ignored **outputs/audit/phase4_closure/**. Production code, existing publications and previous audit evidence were not edited. Existing project interpreter was used with normal sandbox escalation where required; no dependencies or alternate environment were installed.

```powershell
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' -m pytest -q
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' -m pytest --collect-only -q
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase4_closure/focused.py
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase4_closure/publication.py
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase4_closure/scan.py
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase4_closure/real_validation.py
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase4_closure/execute_notebook.py
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase4_closure/final_probes.py
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase4_closure/integrity.py
```

Each script has corresponding JSON results, plus `test_collection.txt`, executed notebook, both reproduced publications, fixture directories, reviewed-file snapshot and before/after protected hashes. `focused.py` uses existing test helpers for fixture construction only; mutations and expected outcomes are audit-authored. The independent real scan reuses the previous auditor's scan logic with a new evidence destination. `publication.py` exercises 58 named lifecycle/mixing/manifest scenarios, with additional serialization and post-write probes in `final_probes.py`. Re-running fixture scripts changes ignored evidence; preserve the recorded before-hash files when retaining an audit snapshot.

## Final Git state and recommendation

```text
 M README.md
 M docs/assumptions.md
 M docs/data_dictionary.md
 M docs/decisions.md
?? docs/audit_handover_phase4.md
?? docs/phase4_codex_audit.md
?? docs/phase4_codex_closure_audit.md
?? docs/phase4_transformation.md
?? notebooks/04_transformation_analytical_dataset.ipynb
?? src/nhs_rtt/transform.py
?? tests/test_transform.py
```

This audit adds only this report and ignored execution evidence. **Milestone creation is not recommended yet.** Close P4-R01/R02 under A02 and P4-R03 under A03, then perform focused independent rechecks plus full regression and a real persisted-output/notebook verification. A01/A04/A05 need regression preservation rather than reopening. No commit, tag, push or `phase-4-pass` creation was performed.
