# Handover: independent Phase 4 audit

Prepared 2026-09-09 at the user's request to continue in a new chat. This is a context handover, not a Phase 4 audit verdict. Phase 4 has not been independently audited in this chat.

## Start here in the new chat

The user wants an independent audit of Phase 4 in the NHS RTT project. Read this handover, inspect current repository instructions/state, and read the user's Phase 4 audit prompt and completion report when supplied. Treat implementation reports as claims to verify. Ask for any missing acceptance brief needed to settle scope; useful read-only inspection can proceed meanwhile.

Preserve existing work. Audit independently rather than implementing fixes by default. Produce a repository Markdown audit report (suggested `docs/phase4_codex_audit.md`, unless the new prompt specifies another path), with reproducible evidence, precise findings, closure conditions and a clear verdict. Do not commit, tag, push, change production behaviour, overwrite canonical notebooks, or alter raw data as part of the audit unless separately authorized. Previous authorization to seal Phase 3 was fulfilled and does not authorize sealing Phase 4.

## Workspace and execution

- Repository: `C:\Users\abdul\OneDrive\Desktop\P_Projects\NHS-RTT-Waiting-Times`
- Shell: PowerShell.
- Existing project Python: `C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe`.
- Regression command: `& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' -m pytest -q`.
- The existing interpreter previously needed normal sandbox escalation to launch. Use the normal approval mechanism when necessary; do not switch interpreters or install dependencies merely to bypass it.
- Keep independent scripts, fixture publications, logs and executed notebook copies under ignored `outputs/audit/phase4/`. Redirect audit reproduction outputs there, preserving production `data/interim/` and `data/processed/` artifacts.
- Prior audits found no applicable AGENTS.md; recheck in the new session. No subagents were authorized in this session.

## Sealed Phase 3 baseline

- Branch: `main`.
- Full Phase 3 commit: `073778b5ddf2fadf2629471d84ab12964cc0ebc1`.
- Short hash: `073778b`.
- Subject: `phase3: add reproducible multi-month ingestion and provenance`.
- Annotated tag: `phase-3-pass`.
- Tag object: `0eafe84899cb492482f8c51770740a1abfabc9e1`.
- Remote: `origin`, `https://github.com/Howitzar/nhs-rtt-dataanalysis.git`.
- Commit and tag were successfully pushed atomically; local HEAD, origin/main, remote main and peeled tag matched. Working tree was clean at sealing.
- Phase 2 baseline and tag `phase-2-pass`: `8f321473d286766d23ea4a3172b8f5b4d8e0e018`.
- Final pre-commit regression: **208 passed in 14.44 seconds**. Both Phase 3 module ASTs were unchanged after removing docstrings when compared with the accepted audit snapshot.
- Two advisory corrections were included: authoritative snapshot acquisition versus informational reread, and precise publication interruption states. No executable behaviour changed.
- Twenty intended Phase 3 files were committed, including `data/raw/manifest.json` and the final audit. Raw CSVs, generated publications, caches and audit execution artifacts were excluded.

Historical audit reports describe Git state at their audit time, before sealing. Their statements that Phase 3 had no commit/tag are historical, superseded by the milestone above.

## Current worktree observed on 2026-09-09

HEAD still equals the Phase 3 commit. Before creating this handover, status showed:

```text
 M README.md
 M docs/assumptions.md
 M docs/data_dictionary.md
 M docs/decisions.md
?? docs/phase4_transformation.md
?? notebooks/04_transformation_analytical_dataset.ipynb
?? src/nhs_rtt/transform.py
?? tests/test_transform.py
```

These are existing Phase 4 changes, not changes made by the handover author. Preserve them. This handover is an additional uncommitted document. Recheck status because another worker may continue changing files.

Only the Phase 4 methodology introduction and module header were inspected for this handover. They claim a verified Phase 3 input, row-preserving analytical-wide output (541,363 × 138), dense waiting-band long output (56,843,115 × 14), a 105-row band reference and transformation reports. These are **unaudited claims**, not established results. No Phase 4 tests or reproduction were run here. A dedicated Phase 4 audit prompt/completion report has not yet been supplied in this chat.

## Essential reading

Paths below are relative to the repository root above.

1. New user-supplied Phase 4 audit prompt and completion report, when available.
2. `docs/phase4_transformation.md`, `src/nhs_rtt/transform.py`, `tests/test_transform.py`, Notebook 04 and all pending documentation diffs.
3. `docs/phase3_codex_final_closure_audit.md` — authoritative Phase 3 acceptance: **PASS**.
4. `docs/phase3_ingestion.md`, `src/nhs_rtt/ingest.py`, `src/nhs_rtt/crossmonth.py` — sealed input contracts.
5. `docs/rtt_semantics.md`, `docs/rtt_grain_and_aggregation.md`, `docs/data_dictionary.md`, `docs/assumptions.md`, `docs/decisions.md`, `docs/data_provenance.md`.
6. Earlier audit history, if needed: `docs/phase3_codex_audit.md`, `docs/phase3_codex_closure_audit.md`, `docs/phase3_closure_remediation_report.md`.

Use `git show phase-3-pass:<path>` when distinguishing accepted documentation from current Phase 4 edits.

## Phase 3 acceptance evidence to retain

The original and first closure audits returned PASS WITH CHANGES. Final closure independently closed residual P3-A03, P3-R01 and P3-R02, completing P3-A04. P3-A01/A02/A05/A06/A07 stayed closed. Do not reopen them without concrete regression evidence.

- Immutable byte binding: the authoritative source buffer is hashed and copied to a private snapshot. Every validator/parser/loader reads that snapshot. Accepted frame and hash therefore describe the same bytes even if the original changes and is restored during loading. The later original reread is informational only. Original filename remains in provenance; snapshot paths do not.
- Publication validity: marker types/required fields, Parquet and sidecar hashes, generation identity and marker/sidecar/actual Parquet row counts must agree.
- Publication states: before replacement the old generation can remain valid; during replacement a mixed state is detectably invalid; after marker-last commit the new generation is valid. Consumers must enforce verification.
- Backup rotation uses only a verified current generation. Failed retries preserve the valid `.prev`; restoration verifies backup before touching current and verifies restored current before reporting success.
- Final independent suite: 208 passed (98 frozen Phase 1/2; 55 ingestion; 17 crossmonth; 38 remediation).
- Repeated full reproductions and shuffled input ordering matched; Notebook 03 executed with zero errors, strict output equality and canonical notebook unchanged.
- Evidence: `outputs/audit/phase3_final/`, especially `probes.py`, `probes.json`, `reproduce.py`, `real_reproduction.json`, `execute_notebook.py`, `notebook.json`, protected hash files and `snapshot/`. Earlier evidence folders are `phase3/` and `phase3_closure/`. Keep them intact.

## Real-data reference facts

- April 2026: **180,781** rows; SHA-256 `0486aca5891a96af4f15e2f4559795138baef08b0ed580602b8c3a7aec6a56e9`.
- May 2026: **178,171** rows; SHA-256 `fee364bc3654cf666f79d3485d26e2ada649a3418988a47aa1784e93294a5707`.
- June 2026: **182,411** rows; SHA-256 `edc3927e4a0065855ad3b2347e7f82688e687b065406eefb49e2f67a9cd67f02`.
- Combined: **541,363 rows × 125 columns**, comprising 121 source columns and four provenance columns; exactly 105 waiting-band source columns.
- Canonical reporting months: `2026-04`, `2026-05`, `2026-06`; retain original source Period literals.
- Verified deterministic Phase 3 generation: `f67b7342a30c4642a78864243142d910b84295dc7876ffb01c231cb8dc52627d`.
- All-band-missing rows: April 36,525; May 35,595; June 37,354; total **109,474**.
- Blank `Total`: April 130,720; May 129,256; June 131,257; total **391,233**. Missing `Total All`: zero.
- `C_999` row counts: 40,102 / 39,677 / 40,636. `NONC` row counts: 2,955 / 2,904 / 2,993. These are row counts, not pathway totals.
- P2-U7 violations: April 0; May 1 (`NT230` / `05V` / `C_100`, Part_2A 2 > Part_2 1); June 2 (`RTG` / `84H` / `C_502` and `C_999`, 2 > 1). Unmatched Part_2A keys: April 5, May 3, June 0. Preserve and flag, never cap or repair.

## Semantic obligations and deferred questions

- Preserve source missingness, explicit zeros, original values, nullable types and provenance. Missing is not semantically zero. Any arithmetic zero-contribution convention is scoped, non-destructive and separately documented.
- Parts 2/2A/3 have structural non-collection distinctions; Part_3 bands must not become invented observed zeros.
- Never sum `C_999` with specialty detail; never sum across RTT parts indiscriminately; Part_2A overlaps Part_2; monthly snapshots are not additive flows.
- Use organisation codes as identifiers; names are labels. Do not infer organisational type from names or silently discard NONC/unknown codes.
- P2-U3/U5 **Phase 3 ingestion obligations were confirmed addressed** by the final audit. Some implementation docs still say pending closure; that wording is stale. Downstream time modelling is separate.
- P2-U1 estimate-inclusive national headline remains unresolved; unestimated June matching does not establish estimated headline reproduction.
- P2-U2 incomplete-pathway unknown-clock question remains unresolved; consult exact assumptions wording.
- P2-U4 organisation classification requires appropriate ODS reference evidence.
- P2-U5 calendar month-end/event-basis interpretation is distinct from a sortable month-start anchor. Current Phase 4 claims leave month-end and temporal modelling to Phase 5; verify labels and scope.
- P2-U6 intermediate band day bounds are derived, not all directly published. Five NHS examples exist; retain derived labels, check first/open-ended boundaries, and do not introduce KPI threshold flags beyond authorized scope.
- P2-U7 remains preserve-and-diagnose.
- Historical source URLs, download times, publication/revision metadata were not supplied; do not fabricate them. Dependency pinning and some scalability questions remain deferred.

## Suggested audit approach, subject to the new brief

1. Capture current state/hashes and baseline diff. Confirm frozen Phase 1–3 code/contracts have not changed unexpectedly.
2. Inspect implementation and tests independently. Run the full regression suite with the existing interpreter; the old 208 count is a baseline, not the expected total after Phase 4 tests are added.
3. Challenge the verified-input boundary, including corruption, stale metadata and read/change windows. Check that actual consumed bytes are bound to verification rather than trusting a prior check alone.
4. Test source row/value/missingness/provenance conservation, derived-field semantics, exact dense-long cardinality and reversible correspondence, all 105 bands and key uniqueness at each declared grain.
5. Exercise synthetic negative and edge cases independently of production helper assumptions; distinguish implementation test coverage from independent counterexamples.
6. Reproduce real outputs to isolated audit paths. Dense-long claims involve **56.8 million rows**: inspect streaming, disk/memory requirements and benchmark evidence before full execution; avoid materializing the entire long dataset just to compare it. Use complete streaming checks where practical and state any sampling limits accurately.
7. Verify deterministic content/order separately from timestamps and environment-sensitive file bytes. Review publication/failure behaviour and quality-report reconciliation.
8. Execute an audit copy of Notebook 04 with output redirection, capture errors/results, and prove raw/interim/canonical files remain unchanged.
9. Report findings with exact file/line references, reproducible triggers, impacts and required closure evidence. Keep implementation claims, observed facts, derived interpretations and untested limitations distinct.

No Phase 4 verdict is implied by this handover. The next chat should continue from the existing uncommitted implementation and the sealed Phase 3 baseline.
