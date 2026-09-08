# Independent Phase 3 audit

8 September 2026. Reviewer: Codex. Scope: the supplied **Codex — Independent Phase 3 Audit Prompt.md**, sections A–R, and the current working tree. Implementation claims were tested against executable behaviour and independent source calculations.

## Verdict

**PASS WITH CHANGES**

Five BLOCKING findings remain. The existing April–June output reproduces correctly, but Phase 3 does not yet establish all required acceptance and publication guarantees. This is not a Phase 3 PASS.

## Executive summary

The full suite passes: **170 passed in 12.11 seconds**, zero failures or skips. Collection independently confirms 47 Phase 1, 51 Phase 2, 55 ingestion and 17 cross-month cases. All three notebooks execute without errors using the required existing interpreter.

Independent reproduction confirms **180,781 April + 178,171 May + 182,411 June = 541,363 rows**, with 121 source columns plus four provenance columns. Every source column was compared against independently parsed CSV values, including missingness and dtypes. The existing production Parquet, two audit workflow runs, reversed payload order and a separate reversed-discovery fixture agree at the data level. Raw hashes match the supplied identities.

The failures concern guarantees beyond these stable inputs:

- **P3-A01:** a missing intended month can silently disappear from a successful publication.
- **P3-A02:** a digest registered for a different reporting month can authorize ingestion.
- **P3-A03:** changing a file after acceptance can publish new values under its old approved digest.
- **P3-A04:** failed sidecar publication can leave new Parquet paired with old ingestion evidence.
- **P3-A05:** an accepted source column named like a provenance column is silently overwritten.

Two NON-BLOCKING issues concern backup-file classification and inconsistent structured rejection. None of these findings establishes corruption of the current April–June saved output. No accepted Phase 1/2 finding is reopened, and no production fixes were made.

## Audit environment and commands

- Workspace: `C:\Users\abdul\OneDrive\Desktop\P_Projects\NHS-RTT-Waiting-Times`.
- Python: `C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe`.
- Shell: PowerShell. No environment creation, package installation or Windows configuration changes.
- The attached completion report and repository copy are byte-identical: SHA-256 `593df81280b4cc1c087518bfd40537244919b7f4a209abd68a45b267655e97e1`.
- Local source evidence sufficed; no new NHS-domain interpretation or external data acquisition was required.

Commands, from the repository root:

```powershell
git rev-parse HEAD main 'phase-2-pass^{commit}'
git status --short --untracked-files=all
git diff --stat 8f32147
git diff --cached --stat
git tag --list
Get-FileHash data/raw/*.csv
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' -m pytest -q
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' -m pytest --collect-only -q
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase3/reproduce.py
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase3/probes.py
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase3/followup_probes.py
& 'C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe' outputs/audit/phase3/execute_notebooks.py
```

Some process launches returned Windows “Access is denied” under the sandbox. Approved escalated execution of the same interpreter succeeded. Jupyter emitted selector-fallback and local TCP transport warnings; these were non-fatal. Canonical notebooks were not edited: audit copies changed only their output-directory assignment and added an interpreter-identification cell. Production outputs were read for comparison, not overwritten.

Reproducible evidence is retained locally under `outputs/audit/phase3/`, already covered by the existing Git ignore policy:

- `real_reproduction.json`, `acceptance.json`, `real_run.txt`, `diagnostic_*.csv` and `real_run1/`, `real_run2/`.
- `probes.py` / `probes.json`: 54 named independent scenarios, constructed without repository test fixtures or its expected-band generator.
- `followup_probes.py` / `followup_probes.json`: successful publication followed by a missing intended file, reversed discovery, injected row-count disagreement, missing Period and header-only input.
- `execute_notebooks.py`, `notebooks.json`, executed copies, redirected outputs and a workspace-local kernel specification.
- `test_collection.txt`, `phase3_tracked.diff`, `git_status_before_report.txt`.

The failure probes modify only synthetic audit fixtures or temporarily patch call boundaries within their own Python process. They neither alter production source files nor simulate changes to real NHS CSVs. Probe results include expected exceptions and deliberately observed violations; they are an audit record, not a claim that every scenario passed.

## Git/baseline verification

`HEAD`, `main` and the **peeled commit** of annotated tag `phase-2-pass` all resolve to `8f321473d286766d23ea4a3172b8f5b4d8e0e018`. The tag object's own hash differs, as expected for an annotated tag. The history contains the Phase 2 baseline commit; the only listed tag is `phase-2-pass`. No Phase 3 commit or tag exists.

There are no staged changes. The five tracked modifications are `.gitignore`, `README.md`, `docs/assumptions.md`, `docs/data_provenance.md` and `docs/decisions.md`. The diff matches the described Phase 3 documentation/ignore changes.

Phase 3 additions are `src/nhs_rtt/ingest.py`, `src/nhs_rtt/crossmonth.py`, their two test files, `notebooks/03_multi_month_ingestion.ipynb`, `data/raw/manifest.json`, `docs/phase3_ingestion.md` and `docs/phase3_completion_report.md`. The audit handover was also already untracked. These were untracked at inspection, rather than already tracked as some prose states. The registry is **eligible to be tracked** through the precise ignore exception; `git ls-files data/raw/manifest.json` returns no entry until staging/commit. This is consistent with the intentionally uncommitted milestone and is not an acceptance blocker.

Diffing the baseline confirms no changes to Phase 1/2 source, tests or notebooks, or the checked dependency declarations. The audit adds only this report and ignored audit evidence. No staging, commit, tag, push or milestone action was performed.

## Test results

**170 passed in 12.11 seconds; zero failed or skipped.** Separate collection produced 170 cases in 0.56 seconds, with the reported per-file counts.

The new tests exercise real acceptance/load paths and useful synthetic invalid inputs. However, their schema fixtures use the production expected-band generator, and the existing rejection test starts without an earlier published artifact. The suite omits missing intended months, cross-month registry/digest disagreement, the acceptance-to-load change window, reserved provenance names and interrupted two-file publication. Passing these tests therefore did not establish those guarantees. Independent audit fixtures construct all 105 band names directly and challenge those missing boundaries.

Notebook execution:

- **01:** 8 original code cells, 9 including audit identification; zero errors; **18.03 seconds**. All nine CSV outputs byte-identical to saved outputs.
- **02:** 11 original code cells, 12 including audit identification; zero errors; **14.02 seconds**. All ten CSV/JSON outputs byte-identical to saved outputs.
- **03:** 10 original code cells, 11 including audit identification; zero errors; **92.36 seconds**. Parquet equals the saved artifact with strict DataFrame/dtype comparison; deterministic sidecar content equals the saved sidecar.

Notebook 03 contains setup, orchestration, displays and narrative. Reusable ingestion and diagnostic logic resides in `src/`. It does not constitute an independent correctness test by itself; the separate raw reproduction supplies that evidence.

## Independent April–June reproduction

Observed raw hashes equal both the supplied expected hashes and registry entries:

- **April — `rtt_2026_04.csv`:** `0486aca5891a96af4f15e2f4559795138baef08b0ed580602b8c3a7aec6a56e9`. **180,781** CSV data records and loaded rows. Sole raw Period `RTT-April-2026`; canonical `2026-04`. Exact ordered 105-band contract passes; all five key columns complete, non-whitespace and unique; accepted, no acceptance warnings.
- **May — `rtt_2026_05.csv`:** `fee364bc3654cf666f79d3485d26e2ada649a3418988a47aa1784e93294a5707`. **178,171** records and loaded rows. Sole raw Period `RTT-May-2026`; canonical `2026-05`. Same schema/key results; accepted, no acceptance warnings.
- **June — `rtt_2026_06.csv`:** `edc3927e4a0065855ad3b2347e7f82688e687b065406eefb49e2f67a9cd67f02`. **182,411** records and loaded rows. Sole raw Period `RTT-June-2026`; canonical `2026-06`. Same schema/key results; accepted, no acceptance warnings.

All three headers have the same 121 names in the same order. An independent lexical `pandas.read_csv` load used explicit empty-string missingness, string columns and separately specified nullable-integer measure conversion. Every resulting source value was compared with the implementation payload and its corresponding Parquet block. CSV record counts were independently streamed with `csv.reader`.

Combined output includes `2026-04`, `2026-05`, `2026-06` in that order: **541,363 rows and 125 columns**, conserving every accepted source row. The original five-column key remains complete and unique; provenance columns do not substitute for it. Every row has the correct source basename/hash/month, and `source_row_index` is exactly `0..n-1` per source. Full ordered source-block equality establishes traceability for all rows, beyond a few spot checks. Original Period remains unchanged. Nullable `Int64` and string dtypes survive strict Parquet comparison.

Missingness and retained categories, April / May / June respectively:

- Entirely missing band distributions: **36,525 / 35,595 / 37,354** rows; preserved as missing.
- Blank Total prevalence: **72.308% / 72.546% / 71.957%**.
- Blank unknown-clock prevalence: **81.606% / 81.729% / 81.297%**.
- Blank Total All: **0%** in all three sources.
- `C_999` rows retained: **40,102 / 39,677 / 40,636**.
- `NONC` commissioner rows retained: **2,955 / 2,904 / 2,993**. These are row counts, not pathway-population totals.

Each month contains the same 24 treatment-function codes and all five RTT parts. Provider counts are **529 / 532 / 537**; commissioner counts **128 / 128 / 129**. Independent code/name pair comparisons, including missing parents/names, find no name drift across the five dimensions. The only nonblank name-to-multiple-code collision is **DUCHY HOSPITAL → NT447, NVC04**, present within each month.

Provider membership changes are precise rather than approximate: April→May adds `A9T5Y`, `D1V5N`, `P1N3Z`, `S5D8W` and loses `F2C9F`; May→June adds `AW7`, `D3R0C`, `N3I9D`, `O1B1P`, `U1I3L` and loses none. Commissioner `Y63` appears in June. Treatment-function and parent-code memberships do not change. Missing parent groups remain represented. These diagnostics are warnings and are not silently resolved.

An independent one-to-one left join of Part_2A against Part_2 on Period/provider/commissioner/TFC reproduces:

- April: **0 violations; 5 unmatched Part_2A groups**.
- May: **1 violation; 3 unmatched groups**. `NT230 / 05V / C_100`: **2 > 1**.
- June: **2 violations; 0 unmatched groups**. `RTG / 84H / C_502` and `RTG / 84H / C_999`: **2 > 1** each.

The May unmatched count is additional detail to the completion report, not a contradiction. All source values remain in the combined artifact. The June detail/total manifestations are not interpreted as two independent patient errors. No cross-part population sum or source correction was performed.

Two real workflow runs, reversed real payload order, the existing production artifact, Notebook 03 and a reversed-discovery synthetic run reproduce equivalent data/order/dtypes and deterministic manifest content. The real verification took **196.04 seconds**. Byte equality across Parquet versions was not required. Protected-file before/after hashes in the reproduction and notebook records confirm real raw files, canonical notebooks and saved interim artifacts remained unchanged.

## Contract-by-contract findings

- **A — Git/hygiene:** baseline and intended uncommitted state verified; see repository section.
- **B — Tests:** reported counts/results reproduced; important gaps independently exercised.
- **C — Discovery:** valid names sort deterministically; malformed month/case variants are surfaced; backup suffix misclassification is P3-A06. Registry completeness is P3-A01.
- **D — Manifest/provenance/revisions:** malformed structure, bad digest, filename/manifest-period mismatch, duplicates, nonboolean selection and zero/multiple selections for multiple releases fail. Same-hash candidates deduplicate; distinct hashes require explicit selection; absent selected release rejects end-to-end. Cross-month identity binding and input stability fail under P3-A02/P3-A03.
- **E — Period:** raw values and filename agree on real inputs. Missing, blank, whitespace-only, lexical `NA`, malformed and conflicting periods reject. English month-name case variations and surrounding whitespace are accepted while retaining raw text. Different raw spellings within one file reject as multiple values. The `RTT-` prefix itself is case-sensitive; supported case insensitivity concerns month names.
- **F — Acceptance:** ordinary blocking conditions prevent payload publication. Some malformed inputs escape as exceptions rather than structured reports (P3-A07). Accepted bytes are not bound to the later payload load (P3-A03).
- **G — Exact bands:** Phase 3 calls frozen validators with `require_full_band_schema=True`. Missing first/interior/final, duplicate, extra, reordered bands and missing key/measure columns reject. This is not an exact 121-column whole-header contract: additional non-band columns may pass. Reserved names need a Phase 3 guard (P3-A05), without changing the accepted Phase 2 band contract.
- **H — Key:** all five components required, blank and whitespace-only cells rejected, duplicate keys rejected. The actual combined frame independently passes the same key. Combining duplicate payload keys raises `CombinedKeyError`.
- **I — Semantics:** stable-source values, missingness, literal `NULL`/`NA`, leading zeros, `C_999`, `NONC`, all five parts and subset exceptions are retained. No global zero-fill was introduced. The reserved-name overwrite is a separate input-extension defect.
- **J/K — Conservation and provenance:** correct for the real and quoted-newline fixtures; an injected count disagreement blocks acceptance. Indices are parsed-record positions, not physical lines. P3-A01 is missing intended-source coverage, not failure of arithmetic over the accepted subset. P3-A03 breaks hash-to-payload binding.
- **L/M — Diagnostics:** real mappings/coverage and subset findings independently agree; synthetic cases exercise rename/missing-name, membership and within-/cross-month collisions across all five dimensions.
- **N/O — Determinism/Parquet:** stable accepted inputs reproduce; strict audit comparisons include dtypes. The built-in `roundtrip_check` meaningfully checks values and missingness but explicitly ignores dtype differences; the stronger dtype claim was verified separately on these inputs.
- **P — Failure/publication:** ordinary rejected reruns return `ok=False`, CLI logic returns nonzero, and text says no combined dataset was produced. Earlier outputs remain byte-identical with their earlier timestamp. Retaining that last successful pair is not, by itself, a blocker given that explicit run result. Interrupted publication can instead create a mismatched pair (P3-A04), and missing intended inputs can yield a false success (P3-A01).
- **Q — Notebooks:** all three execute and reproduce outputs in isolated copies.
- **R — Documentation:** stable real-data claims largely match. The intended-source, file-identity and source-preservation guarantees need correction with P3-A01–A05; backup classification is overstated. P2-U3 cannot yet be called fully addressed. “Tracked” currently means intended for tracking, as explained above.

## Adversarial tests performed

Independent fixtures cover exact band/header rejection, missing Period/key/measure columns, empty input rows, blank and whitespace keys, duplicate keys, negative/fractional counts, source hash mismatch/no provenance, raw Period variants and filename disagreement, quoted embedded newline/comma fields, malformed discovery names, reversed ordering, invalid registry shape/digest/selection, revision selection/deduplication, selected digest absent, unexpected unregistered month, missing intended month, hash registered under the wrong month, stale prior outputs, interrupted sidecar write, source replacement after acceptance, reserved provenance columns, all-missing distributions, literal NA strings, nullable dtypes and combined duplicate-key rejection.

Fault injection is limited and explicit: one test forces the independent row counter to disagree; another raises `OSError` at the sidecar write; another changes a **synthetic** CSV immediately after the real acceptance call returns. The implementation is otherwise exercised unmodified through its actual workflow. Full inputs/results and exception types are in the evidence files named above.

## Repository hygiene

All three raw CSVs and both generated interim artifacts are ignored. `manifest.json` is the narrow intended exception under `data/raw/`. Existing ignore rules cover caches, environments, egg-info, notebook checkpoints and audit execution evidence. No generated raw/interim/cache artifacts are staged or appear among the candidate untracked Phase 3 files. The canonical Phase 3 notebook contains saved outputs; it is the intended notebook, not an extra audit execution copy.

The worktree remains intentionally dirty with the implementer's changes. “Clean” here means those changes were preserved and audit scratch/output files were confined to the already ignored evidence directory, with this explicitly requested report as the sole new audit document. The audit did not attempt to clean, stage or discard user work.

## Phase-boundary assessment

No material Phase 4+ leakage found. No long-form band reshape, final analytical cleaning/imputation, dimensional model, DuckDB/SQL KPI layer, provider-type inference/enrichment, trends/statistics, BI, ML or Spark implementation was introduced. Descriptive coverage and source-quality diagnostics belong to the authorized ingestion audit. Raw `C_999` and detail are retained together as source rows, without analytically summing both. Parts are not combined into a pathway population. Future-phase mentions are explicitly deferred.

## Findings

### P3-A01 — Missing intended sources do not prevent successful publication

**Severity: BLOCKING.** Evidence: `followup_probes.json`, `missing_after_success`; `probes.json`, `missing_intended_month`. `crossmonth.py:470` loads the registry, but the workflow iterates only discovered months and `crossmonth.py:517` compares payload count only with discovered-month count.

Concrete reproduction: publish valid synthetic May and June with both entries selected in the registry (**ok=True, 2 rows**). Rename only the synthetic May file to `.csv.bak`, retaining the same registry. The next run returns **ok=True, 1 row, notes=[]**, replacing the publication with June only. A separate fixture with a completely absent registered May also succeeds without warnings.

**Affected invariant:** the authoritative intended source set must be reconciled with available/accepted inputs; a missing required source must not silently redefine a successful current publication. Row conservation over the reduced accepted subset does not detect this.

**Required remediation:** compare required registry months/selected releases with observed accepted sources before publication. Report missing intended sources and fail the default full-set run. If deliberate subset runs are supported, require an explicit requested subset and record it in evidence. Add successful-run→missing-source regression coverage. Update D-033 and acceptance/completion documentation to match the enforced policy.

### P3-A02 — Registry provenance is not bound to the accepted reporting month

**Severity: BLOCKING.** Evidence: `probes.json`, `hash_registered_for_wrong_month`; `ingest.py:496–509`, with the later selection check at `ingest.py:587`.

A valid June CSV digest is placed in a machine-valid registry entry whose filename/period are **May**. With only the June CSV present, the end-to-end run returns **ok=True**, accepts June and publishes it. The global digest lookup finds the May entry and emits only a filename warning; nothing requires `reg_entry.reporting_period` to equal the accepted month. June has no authoritative registry entry at all.

**Affected invariant:** registry reporting period, observed filename/internal Period and accepted byte identity must agree. Shape validation of the manifest alone does not establish this binding. This is independently a defect in `accept_month`, even if P3-A01 later prevents this particular end-to-end arrangement.

**Required remediation:** bind provenance lookup to the canonical reporting month and digest, and reject a registry-period disagreement. Keep explicit expected-hash support under its documented policy, but do not describe a cross-month hash-only match as registry authorization. Test this conflict through both acceptance and orchestration. Correct the documented warning-only filename behaviour where the filename implies a different month.

### P3-A03 — Acceptance and publication can use different source bytes

**Severity: BLOCKING.** Evidence: `probes.json`, `changed_after_acceptance`; `crossmonth.py:485`, `:496`, `:502–507`. The workflow computes a discovery digest, validates through a separate read, then reloads the path to construct the payload. It retains the discovery digest for provenance and does not bind that final load to the accepted bytes.

The probe lets the real `accept_month` succeed on a synthetic record with **Total All=7**, then changes only that fixture to **99** before the workflow reloads it. The workflow returns **ok=True** and publishes **99** with the original approved digest `abfcde17626765d4d0d5f6caecb46a9635c3dc1e017562d71cbd2b07cdbe95e0`; the changed file's digest is `23c4e9ab789facf4140daef1704d4ec9bb1b3952e7d5540347e69addea7ef240`. The new bytes were never authorized by the registry. The roundtrip still passes because it compares against the already misidentified payload.

**Affected invariant:** each published row's hash must identify the exact bytes from which its values were accepted and loaded. Keeping raw inputs read-only inside this program does not prevent replacement by a download/revision process.

**Required remediation:** use one stable source snapshot/byte stream for hashing, validation and payload construction, and reuse the accepted loaded frame instead of reopening the mutable source path. At minimum detect and reject changes across all current read boundaries and ensure discovery/acceptance/payload digests agree; do not treat a check performed before a later unguarded reload as sufficient. Add a controlled replacement test. No raw repair is needed.

### P3-A04 — Interrupted publication can leave inconsistent Parquet and evidence

**Severity: BLOCKING.** Evidence: `probes.json`, `interrupted_publication`; `crossmonth.py:327` overwrites the final Parquet before `crossmonth.py:362` writes the final sidecar, and roundtrip checking happens afterwards.

The probe first publishes one valid row. It then registers a valid two-row source and raises an ordinary `OSError` at the sidecar write to simulate a publication failure. The on-disk pair contains **2 Parquet rows but a sidecar asserting 1 row**, with the old sidecar unchanged. There is no shared generation binding or invalidation protecting readers of those conventional final paths. The exception signals failure to the caller, but does not make the mismatched persisted pair safe to consume.

**Affected invariant:** a published artifact and its provenance evidence must describe the same successful generation, including after failed/interrupted writes.

**Required remediation:** stage and validate a complete generation before exposing it, and use a single committed generation reference or an explicit validity/hash mechanism that readers enforce. Preserve the previous complete generation on failure, or mark the final pair unusable. Two independent final-path replacements without a pairing/validity rule still leave an interruption window. Test both publication failure and ordinary rejected reruns. Retaining an explicitly identified last successful generation is acceptable; deletion is not inherently required.

### P3-A05 — Incoming provenance-named columns are silently overwritten

**Severity: BLOCKING.** Evidence: `probes.json`, `reserved_provenance_column`; `crossmonth.py:267–270` assigns the four provenance fields without checking collisions. Frozen Phase 2 validation permits additional non-band columns.

The probe supplies a registered, otherwise valid CSV with **122 source columns**, including `source_file='original source value'`. Acceptance and the full workflow return **ok=True**. Publication has **125 columns**, rather than source columns plus four, and `source_file` now contains the CSV basename. The original source cell is lost silently. The same assignment pattern applies to the other reserved provenance names.

**Affected invariant:** Phase 3 preserves every accepted source column/value and adds exactly four provenance columns. This is a Phase 3 boundary issue, not a reason to broaden the accepted Phase 2 schema contract.

**Required remediation:** reject any input containing reserved provenance-column names before acceptance/publication, with a defensive collision check in combination. Do not silently rename or overwrite raw fields. Test all four names and the unchanged valid-source path; document the narrow restriction.

### P3-A06 — Backup suffix files are classified as unrelated

**Severity: NON-BLOCKING.** Evidence: `probes.json`, `discovery`, and `followup_probes.json`; `ingest.py:70`, `:392`. The loose matcher ends in `\.csv$`, so `rtt_2026_04.csv.bak` and the missing-May follow-up file land in **ignored**, not `malformed_candidates`, despite the function documentation, methodology and completion report naming this exact example as surfaced.

**Affected invariant:** malformed RTT-like files should be explicitly distinguished from unrelated clutter. Such a file is not itself ingested, so this classification issue alone does not corrupt accepted rows. The silent missing intended month is separately P3-A01.

**Remediation:** extend the loose detection to documented backup/suffix forms and test discovery classification, not only filename-parser rejection. Keep the strict production filename matcher unchanged.

### P3-A07 — Some invalid inputs bypass the structured rejection report

**Severity: NON-BLOCKING.** Evidence: `probes.json`, `decimal` and `manifest_null_entry`; `ingest.py` registry entry validation and the load exception handler around `:551`.

A numeric cell `Total All=1.5` raises a pandas **TypeError** (`cannot safely cast non-equivalent object to int64`), escaping `accept_month`, which catches only `ValueError` at loading. A null item in the manifest sources list similarly raises TypeError before a targeted validation message. These cases do **not** become accepted payloads or successful publications.

**Affected invariant:** the documented structured acceptance/rejection interface and actionable failure diagnostics, rather than data acceptance correctness.

**Remediation:** validate registry item types and normalize expected parse/load failures into explicit rejection/error messages. Catch specific known input errors without swallowing programming defects. Add fractional-count and null-entry coverage; do not alter the frozen numeric meaning or impute values.

## P2-U3 / P2-U5 / P2-U7 status

- **P2-U3 — PARTIALLY ADDRESSED; not closed.** Per-file exact bands, key checks and actual cross-month mapping diagnostics work. The registry/completeness, stable identity and reserved-source-column gaps prevent unconditional source-ingestion closure (P3-A01–A03/A05). Documentation should not describe the entire obligation as addressed until corrected.
- **P2-U5 — PARTIALLY ADDRESSED FOR INGESTION.** Period parsing and filename agreement pass. Explicit revision-selection fixtures work, but binding the selected identity to the actual published bytes remains blocked by P3-A02/A03. Calendar month-end and stock/flow analytical temporal modelling remain explicitly deferred; no need to implement them during this audit.
- **P2-U7 — PRESERVED AND DIAGNOSED.** The April/May/June violations and unmatched counts were independently verified. Source values are unchanged. The new May instance is covered by the existing preserve-and-flag policy and does not reopen Phase 2. Any future subset-derived analysis must still validate the invariant.

P2-U1/U2/U4/U6 remain out of this audit's remediation scope. Missing original download/publication/revision metadata was not fabricated; completing that historical provenance is not newly imposed as a Phase 3 blocker here.

## Final Phase 3 PASS checklist

- [x] Accepted Phase 1/2 code preserved; all regressions pass.
- [x] Phase 3 test counts and passing results reproduced.
- [x] April/May/June use the shared workflow; raw hashes match.
- [x] Exact 105-band contract and Period/filename agreement enforced.
- [x] Actual per-month and combined five-column keys complete and unique.
- [x] Explicit distinct-release selection/deduplication scenarios behave deterministically.
- [ ] Intended-source completeness and month-specific registry authorization: **P3-A01/A02**.
- [ ] Accepted source bytes remain bound to published row hashes: **P3-A03**.
- [x] Real source values, missingness, conservation and provenance reproduced.
- [ ] Source preservation for reserved-column inputs: **P3-A05**.
- [x] Real mapping, membership, coverage and subset diagnostics reproduced.
- [x] Stable-input repeated/shuffled combination and strict Parquet reproduction pass.
- [ ] Failed/interrupted publication cannot leave inconsistent evidence: **P3-A04**.
- [x] All three notebooks execute without errors and reproduce saved outputs.
- [ ] P2-U3/U5 fully addressed for ingestion and documentation aligned: blocked above.
- [x] P2-U7 preserved and diagnosed; no unsupported Phase 2 reopening.
- [x] Repository hygiene and Phase 3/4 boundary maintained; no Git milestone created.

## Recommendation

Return the five blocking findings to the implementation engineer for targeted changes. Require focused closure checks for intended-source coverage, month/digest binding, stable accepted input, publication generation integrity and provenance-name collisions, plus a regression run and stable real-data reproduction. Correct the two non-blocking discrepancies while touching those boundaries if practical. There is no justification for redesigning the project or repeating the broad Phase 1/2 audits.

Do not create the Phase 3 acceptance milestone until independent closure confirms these blockers are resolved. The original implementation was audited as supplied; no material finding was silently repaired.

**PASS WITH CHANGES**
