# Phase 3 Final Closure Remediation Report

**Date:** 2026-09-08 · **Engineer:** Claude Code
**Closure audit:** `docs/phase3_codex_closure_audit.md` (Codex, **PASS WITH
CHANGES**) — P3-A01 / A02 / A05 / A06 / A07 **CLOSED**; **P3-A03** and **P3-A04**
partially closed, with residuals: the immutable-byte binding (A03), **P3-R01**
(unchecked marker row count) and **P3-R02** (`.prev` overwritten by a failed
retry).
**Scope:** three narrow fixes + documentation alignment. No redesign, no Phase 4
work, no new dependency, raw data and frozen Phase 1/2 contracts untouched.
Not committed / tagged / pushed; no Phase 3 milestone.

Current authority: `docs/phase3_ingestion.md` (§3, §8, §9, §11), decision
**D-039**. The first remediation report `docs/phase3_remediation_report.md`
carries a SUPERSEDED-IN-PART banner.

---

## Files changed

| File | Change |
|---|---|
| `src/nhs_rtt/ingest.py` | `accept_month` reads the source **in one authoritative snapshot-acquisition read** into a private snapshot (`tempfile.mkdtemp` dir, original basename) and delegates steps 4–11 to a new `_accept_from_snapshot(report, snap, …)` which runs the reserved-column / `Period` / `validate_extract` / `load_rtt_csv` / `count_data_rows` steps against `snap`. `report.sha256 = hashlib.sha256(data).hexdigest()`. The step-12 endpoint re-hash **block** is removed; a post-snapshot change of the *original* path is now a `warnings` entry. `discovery_sha256` is compared to the snapshot digest. `snap` dir removed in `finally`. New imports: `shutil`, `tempfile`. |
| `src/nhs_rtt/crossmonth.py` | `verify_publication` validates marker structure/types and **reconciles `combined_rows`** across marker, sidecar `deterministic.combined_rows` and `pyarrow.parquet` `num_rows` (new `_parquet_num_rows`, `_is_int` helpers; `import pyarrow.parquet as _pq`). `write_combined_parquet` rotates `current → *.prev` **only if `verify_publication` on the current trio is valid**. `restore_previous_generation` verifies the `.prev` trio in a scratch dir before restoring, then re-verifies, and distinguishes *no backup* / *backup invalid* / *restore-copy failed* / *restored & valid*. Docstrings updated (interruption state machine; `PublicationError` vs propagated `OSError`). |
| `tests/test_phase3_audit_remediation.py` | `TestA03_*` reworked to the immutable-snapshot guarantees incl. the exact changed-and-restored counterexample; new `TestR01_VerifierValidatesRowCount` (6) and `TestR02_ValidBackupRotation` (5). File now **38** tests. |
| `docs/phase3_ingestion.md` | §3 (immutable snapshot; drop "re-checked after every read"), §8 (row-count reconciliation, valid-only `.prev` rotation, precise interruption semantics), §9 (P2-U3/P2-U5 → *partially addressed, pending closure confirmation*), §11 closure table. |
| `docs/decisions.md` | new **D-039**. |
| `docs/assumptions.md` | P2-U3 / P2-U5 wording aligned (partially addressed, pending confirmation). |
| `docs/phase3_remediation_report.md` | SUPERSEDED-IN-PART banner. |

No raw NHS CSV, `data/interim/` artifact (`*.parquet`, `*.json`, `*.prev`,
`.staging-*`), cache or executed-notebook copy is staged. `data/raw/manifest.json`
remains the one tracked exception under `data/raw/`.

---

## Residual P3-A03 closure — one immutable snapshot

`accept_month(path, …)`:

1. **acquire snapshot bytes** — `data = path.read_bytes()` is the authoritative read of the mutable
   original;
2. **hash** — `report.sha256 = hashlib.sha256(data).hexdigest()`; if
   `discovery_sha256` is supplied and differs → reject (the source changed
   between discovery and this read);
3. **snapshot** — `data` is written to `…/nhs_rtt_snap_<rand>/<original basename>`;
4. **validate + load** — `_accept_from_snapshot` runs the reserved-column check,
   `Period` parsing, `semantics.validate_extract`, `semantics.load_rtt_csv` and
   `count_data_rows` **all against the snapshot path**; the resulting DataFrame
   is `report.frame`;
5. **cleanup** — the snapshot directory is removed in `finally`.

The bytes hashed (step 2), validated and loaded (step 4) are therefore *the same
bytes*. A temporary change to the original file during the load window — even
one reverted before acceptance returns — cannot affect `report.frame` or
`report.sha256`, because all validation and loading use the snapshot acquired in step 1. The
original file is never written; `report.sha256_after` is an *informational*
re-hash of the original that raises only a warning if it differs; the snapshot
path never enters provenance (`report.filename` / `source_file` stay the
original basename; `report.path` is the original path).

Frozen Phase 2 validators are invoked unchanged — they take a filesystem path,
and the snapshot is a byte-exact private copy with the same basename.

**Codex counterexample now:** `test_changed_and_restored_original_does_not_misbind`
monkeypatches `semantics.load_rtt_csv` to write B=99 to the *original* path,
call the real loader (against the snapshot, still A=7), then restore A. Result:
`accepted=True`, `sha256 == sha256_after == A`, published `Total All == 7`,
original file byte-identical to A at the end. Changed-before-snapshot rejects
via the discovery digest; a rejected report has `frame=None`.

---

## P3-R01 closure — verified publication metadata

`verify_publication(out_dir)` now, in order:

1. marker exists, parses, is an object, and `generation_id` /
   `parquet_sha256` / `sidecar_sha256` are non-empty strings and
   `combined_rows` is a non-negative int (malformed marker → `valid=False`);
2. `parquet_sha256` / `sidecar_sha256` equal the SHA-256 of the on-disk files;
3. sidecar `run.generation_id` equals the marker `generation_id`;
4. **row-count reconciliation** — `marker.combined_rows` ==
   `sidecar.deterministic.combined_rows` == `pyarrow.parquet` `metadata.num_rows`
   (cheap metadata read, no full load). Any disagreement → `valid=False` with a
   `row-count disagreement: marker=… sidecar=… parquet=…` reason.

Only after all four does it return `{"valid": True, "generation_id": …,
"combined_rows": <reconciled>}`. The Codex tamper (`combined_rows` → 999999,
digests untouched) now returns `valid=False`. Tests: valid publication returns
the true count; marker-count tamper, sidecar-count tamper (with the sidecar hash
re-synced), actual-Parquet-row mismatch (2 rows vs marker 1, hash re-synced),
and a missing `combined_rows` field each → `valid=False`. Existing
Parquet/sidecar/generation-ID tamper tests retained.

---

## P3-R02 closure — valid-backup rotation & verified restore

`write_combined_parquet`: the `current → *.prev` copy now happens **only when
`verify_publication(out_dir)` on the current published trio returns valid**. A
first publish (no trio yet) and a failed-retry state (current trio invalid) both
skip the rotation, so a known-valid `.prev` is never overwritten by an invalid
trio.

`restore_previous_generation(out_dir)`:

* no `.prev` trio → `{"restored": False, "reason": "no complete previous …"}`;
* copies `.prev` into a scratch dir and runs `verify_publication` there; if
  invalid → `{"restored": False, "reason": "the previous generation (.prev)
  does not verify: …", "prev_verify": …}` (the live trio is untouched);
* otherwise restores, re-verifies the live trio, and returns
  `{"restored": <bool>, "verify": …}` — `True` only on a verified restore.

**Codex sequence now** (`test_failed_retry_preserves_valid_prev`): publish gen 1
(valid); gen-2 attempt fails after the first `os.replace` → current trio invalid,
`.prev` = valid gen 1; retry fails before the first `os.replace` → rotation
skipped, `.prev` still valid gen 1; `restore_previous_generation` →
`{"restored": True, "verify": {"valid": True, "combined_rows": 2}}`. A corrupted
`.prev` → `{"restored": False, "reason": "… does not verify …"}`.

---

## Publication contract wording (aligned)

`docs/phase3_ingestion.md` §8 now states the actual state machine:

* failure **before** the first replace → the previous valid generation is intact;
* failure **during** the replaces → the final paths are invalid, detected by
  `verify_publication` (hash or row-count disagreement);
* completion of the **marker-last** commit → the new generation is valid even if
  the caller subsequently fails;
* **a trio is consumable only when `verify_publication` returns `valid: True`.**

It no longer claims "every interrupted publication leaves an invalid trio", and
notes that a staged-validation failure raises `PublicationError` while a failed
`os.replace` propagates its `OSError`.

---

## Tests

`"C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe" -m pytest -q` →
**208 passed, 0 failed, 0 skipped** (~13 s).

| Suite | Count | Note |
|---|---|---|
| `tests/test_profile.py` | 47 | unchanged |
| `tests/test_semantics.py` | 51 | unchanged |
| `tests/test_ingest.py` | 55 | unchanged |
| `tests/test_crossmonth.py` | 17 | unchanged |
| `tests/test_phase3_audit_remediation.py` | **38** | +13 vs the first remediation |

Focused new tests: changed-and-restored source bytes; snapshot provenance /
original basename; rejected report clears `frame`; raw source untouched by
acceptance; marker row-count tamper; sidecar row-count mismatch; actual-Parquet
row mismatch; missing marker row-count field; valid generation rotates to
`.prev`; failed retry preserves valid `.prev`; invalid `.prev` not reported
restorable; no-backup case.

---

## Real April–June reproduction (unchanged)

`run_phase3` over `data/raw/rtt_2026_{04,05,06}.csv`:

| | |
|---|---|
| April / May / June rows | 180,781 / 178,171 / 182,411 — loaded == streamed |
| Raw SHA-256 | all three unchanged, equal to the registry / baseline |
| 121 source columns · exact 105-band schema | pass for all three |
| Candidate key | `usable` per month **and** on the combined frame |
| Combined | **541,363 rows × 125 columns**, exact conservation |
| `missing_intended` / `unexpected_months` | `[]` / `[]` |
| Missingness | preserved (`Total` blank 391,233; all-band-blank 109,474; `Total All` blank 0) |
| `C_999` / `NONC` | retained |
| P2-U7 | April 0 · May 1 (`NT230`/`05V`/`C_100`) · June 2 (`RTG`/`84H`) — preserved & flagged |
| Publication | `verify_publication` → `{"valid": true, "combined_rows": 541363}` |

The immutable-snapshot mechanism did not alter source semantics, dtypes, row
ordering or provenance.

## Determinism

Two equivalent runs into separate directories: identical combined rows / order /
values / provenance; identical `deterministic` manifest block; stable
`generation_id` `f67b7342a30c4642a78864243142d910b84295dc7876ffb01c231cb8dc52627d`
(run timestamps differ). Reversed payload order → strictly equal frame. No
cross-version Parquet byte identity required or asserted.

## Notebook execution

`nbconvert --to notebook --execute --inplace notebooks/03_multi_month_ingestion.ipynb`
→ **0 error outputs**, all code cells executed. No notebook changes were needed
(the reusable-API surface is unchanged); it remains a thin orchestration layer.

## Documentation alignment

`phase3_ingestion.md` §3 (immutable snapshot; removed "re-checked after every
read"), §8 (row-count consistency in `verify_publication`; valid-only `.prev`
rotation; corrected interruption semantics), §9 + `assumptions.md`
(P2-U3/P2-U5 → *partially addressed for ingestion, pending independent closure
confirmation*), §11 closure table; `decisions.md` D-039;
`phase3_remediation_report.md` superseded banner. P2-U7 wording unchanged
(preserve / diagnose / do not repair).

---

## Remaining issues

| Item | Class |
|---|---|
| P3-A03 residual (immutable-byte binding) | **Fixed** via one-snapshot design — **awaiting independent closure confirmation** |
| P3-R01 (verified metadata consistency) | **Fixed** (row-count reconciliation) — awaiting confirmation |
| P3-R02 (valid-backup rotation / verified restore) | **Fixed** — awaiting confirmation |
| P3-A01 / A02 / A05 / A06 / A07 | CLOSED by the closure audit; unchanged here |
| `roundtrip_check` ignores dtype differences by design | NON-BLOCKING — staged-publication validation + `deterministic` block + independent audit dtype checks cover it; left unchanged |
| P2-U3 / P2-U5 "full ingestion closure" | Not claimed until the above pass an independent closure check |
| `Period` → month-end date; stock/flow analytical temporal model; Phase 4 transformation, model, SQL/KPIs, BI | DEFERRED TO PHASE 4+ |
| P2-U7 | Carried — preserve & flag; not reopened |
| P2-U1 / P2-U2 / P2-U4 / P2-U6; historical download provenance | DEFERRED — out of scope; fields left `null`, not fabricated |

No BLOCKING items introduced by this remediation.

---

## Final self-assessment

The three residual defects (A03 exact-byte binding, P3-R01, P3-R02) are closed
with targeted changes and dedicated regression tests; documentation is aligned
to the actual guarantees; all 98 Phase 1/2 tests and all 110 Phase 3 tests pass
(**208 total**); the real April–June data-level results, hashes, diagnostics and
generation identity are unchanged; the notebook executes clean; repository
hygiene and the Phase 3/4 boundary are intact; no Git milestone was created.

**READY FOR FINAL CODEX PHASE 3 CLOSURE AUDIT**

Claude does not declare Phase 3 PASS.

Snapshot read-count clarification: one authoritative snapshot-acquisition read plus an informational reread used only for warning/reporting; the original source is not literally read only once in total.
