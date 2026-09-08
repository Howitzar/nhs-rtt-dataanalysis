# Independent Phase 1 audit — June 2026

Audit date: 2026-09-07. Verdict: **PASS WITH CHANGES** (conditional acceptance; findings below remain open).

Reviewed `src/nhs_rtt/`, both test files, the discovery notebook including saved outputs, all ten profile artifacts, the four requested project documents, README files, `.gitignore`, `pyproject.toml`, and `requirements.txt`. Used only `C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe` (Python 3.14.3). No external domain sources were consulted. June was the only real CSV read. April/May compatibility was assessed through code inspection and synthetic period values.

## 1. Overall verdict

The June structural profile is reliable: independent counts and mappings agree with the saved artifacts, and a fresh run reproduces all nine CSV outputs byte for byte. The overview matches after excluding generation time and source-path formatting. The implementation stays within structural profiling, but its future-input safeguards and documentation require changes before treating it as a trustworthy general profiling gate.

No production fixes were applied: this is an audit, and the observed June results do not need rebuilding. PASS WITH CHANGES does not mean the outstanding findings are resolved.

## 2. Critical issues

No critical defect affecting the independently verified June figures was found. No raw-data mutation, cleaning, reshaping, SQL/BI construction, or performance-metric calculation was found or performed.

The unsupported domain assertions described below are a blocker to using those assertions as Phase 2 requirements.

## 3. Moderate issues

**M1 — “Exact duplicates” is stronger than the implementation guarantees.** `src/nhs_rtt/profile.py:339` stores only `hash(tuple(row))`. Different rows can have the same hash, producing false duplicates; Python's randomized string hashing also makes such rare errors process-dependent. A forced-collision probe reproduces one false duplicate from two different rows. June independently has zero duplicates using SQLite uniqueness over complete JSON-serialized field arrays, with no row-hash approximation. Recommendation: use full-row equality, potentially through disk-backed storage or collision verification; a stronger digest alone is still not mathematically exact.

**M2 — Duplicate headers silently bind mappings to the last occurrence.** At `profile.py:321`, the header-to-index dictionary overwrites earlier positions. A synthetic `Provider Org Code,Provider Org Code,Provider Org Name` row `A,B,Name` silently maps B to Name. Per-column profiles still contain both columns, so the categorical result hides the ambiguity. Report or reject ambiguous headers before binding roles. June has no duplicate headers.

**M3 — Malformed quoting can pass with zero ragged rows.** `csv.reader` at `profile.py:313` uses default permissive parsing. A file ending in an unterminated quoted cell is accepted as one row with zero ragged rows. Strict parsing should reject or explicitly report such input. June passes an independent `strict=True` parse without decode or CSV errors. Row-width checks alone cannot establish quoting validity.

**M4 — Documentation turns unresolved domain questions into assertions.** `docs/data_dictionary.md:32,56,63` and the notebook's final observations call C_999 a subtotal/non-specialty and prescribe aggregation treatment; the dictionary expands DTA without repository-held authoritative evidence. `docs/assumptions.md` A-07/A-08 assert subtotal/overlap and double-counting behavior despite declaring every item unresolved. The commissioner-code interpretation is also speculative, though marked unconfirmed. Replace these assertions with observed labels and explicitly unresolved questions, or attach authoritative evidence in a separately authorized phase. This audit verifies only `C_999` maps to the literal name `Total` on 40,636 records.

**M5 — Reproducibility claims exceed captured evidence.** README says every run records URLs, checksums, and package versions; the profiler does not. Original source URL, download time, publication date, and source version remain absent. Dependency lower bounds are not pins or a lockfile; requirements and package metadata differ (notably great-expectations). The source checksum is now captured in audit evidence, but it cannot reconstruct missing provenance. The notebook has a generic `python3` kernel and working-directory assumptions, rather than an enforced interpreter. Preserve the exact run environment and align installation instructions/metadata before calling the workflow fully reproducible.

## 4. Minor issues

- `_md_table()` at `profile.py:426` does not escape pipes or newlines. The current anomaly overview is already malformed: `NT447 | NVC04` occupies extra Markdown cells. CSV anomaly output retains the full values correctly.
- Categorical name counts include empty strings, while per-column distinct counts exclude empty/whitespace values. Thus 122 commissioner name values versus 121 nonblank names is consistent implementation behavior but needs explicit labeling.
- Token classification labels numeric-looking identifiers such as `001` as integer and calculates float extrema. It preserves `001` in categorical pairs and raw unique values; no actual leading-zero loss was reproduced. Inferred types must not become an ingestion schema. Float extrema can lose precision for very large integers, and date classification checks shape rather than calendar validity.
- `null_pct` combines empty strings and whitespace-only strings, and short-row missing fields are counted as null without an `empty` type-count increment. Literal NULL/NA-like strings remain strings. These conventions are stated only partly and can make summaries seem inconsistent on other inputs.
- Exact categorical header matching silently omits roles when spelling/case/spacing changes or one partner is absent. Commissioner parent is not a default categorical role, although both columns receive ordinary profiles. Report missing roles rather than presenting absence as completeness.
- Empty anomaly CSVs are zero-byte files without headers. Reusing an output stem after roles disappear can leave stale role CSVs because save_profile does not remove or inventory old artifacts.
- README and data/raw/README still say April 2025; the README recommends a new environment and does not install the src-layout package. The current environment's editable install makes imports work, but those instructions do not recreate it. D-007 incorrectly calls `pytest>=8` a pin.
- The notebook displays the full overview despite its introductory claim that large tables are not dumped inline. Its final observations are manually maintained narrative, not generated assertions. Notebook source and stored results were reviewed; its kernel was not re-executed, since doing so would overwrite existing profiles. The underlying profiling API was run freshly instead.

## 5. Independently verified June figures

Source: `data/raw/rtt_2026_06.csv`, **82,084,725 bytes** (78.28 MiB).

SHA-256: `edc3927e4a0065855ad3b2347e7f82688e687b065406eefb49e2f67a9cd67f02`.

- **182,411 data rows; 121 columns; zero exact duplicate parsed rows.**
- **Zero ragged rows; zero duplicate headers.** All records have 121 fields; 182,412 physical lines including the header.
- **13 identifier/label columns**, positions 0–12: Period; Provider Parent Org Code/Name; Provider Org Code/Name; Commissioner Parent Org Code/Name; Commissioner Org Code/Name; RTT Part Type/Description; Treatment Function Code/Name. Exact header strings are in the JSON evidence.
- **105 wait-bucket headers**, positions 13–117: 104 consecutive interval labels from `Gt 00 To 01 Weeks SUM 1` through `Gt 103 To 104 Weeks SUM 1`, then `Gt 104 Weeks SUM 1`.
- Trailing columns are exactly `Total`, `Patients with unknown clock start date`, `Total All`; none is classified as a wait band.
- Period is exactly `RTT-June-2026` on every record.
- Providers: **537 codes / 536 names**, no blanks; provider parents: **36 codes / 36 names**, no blanks.
- Commissioners: **129 codes / 121 nonblank names**, or **122 distinct raw name values including the empty string**. Commissioner parents: 36 nonblank codes/names each, or 37 values each including empty string. Their blank code/name pairing occurs together.
- RTT parts: **5 codes / 5 descriptions**, bijective within June. Part_1A → Completed Pathways For Admitted Patients (18,803); Part_1B → Completed Pathways For Non-Admitted Patients (32,351); Part_2 → Incomplete Pathways (63,355); Part_2A → Incomplete Pathways with DTA (30,548); Part_3 → New RTT Periods - All Patients (37,354).
- Treatment functions: **24 codes / 24 names**, bijective within June. Every pair and record count matches the saved treatment-function CSV. `C_999` → `Total` occurs **40,636** times. Full independently reconstructed mappings are retained in JSON.
- Commissioner parent code and name: **10,263 empty cells each / 5.6263%**. Commissioner name: **3,348 / 1.8354%**. All other identifier/label columns have zero empty cells.
- `Total`: **131,257 / 71.9567%** empty; unknown-clock column: **148,294 / 81.2966%**; `Total All`: **0 / 0%**.
- Week-column empty percentages range from **27.8766% to 33.0304%**. These are structural missingness percentages, not NHS performance metrics.
- **Zero whitespace-only cells; zero padded nonblank cells** across the full file. No case-insensitive literal NULL, None, NaN, NA or N/A tokens were found. CSV parsing yields empty strings, not typed database nulls; quoted versus unquoted empty fields are not distinguished by this audit.
- Strict UTF-8-SIG decoding/parsing succeeds. The first bytes are `50 65 72` (the start of Period): **no UTF-8 BOM is present**. UTF-8-SIG also correctly removes a BOM in a synthetic probe. Quoted commas and `001` identifiers survive that probe unchanged. June commissioner codes with leading zeros survive in the saved mappings.

Independent reconstruction compares every column's name, row count, empty count, nonblank distinct count and null percentage, plus all saved categorical pair counts. No mismatches were found. A fresh profiler run separately reproduces every saved CSV byte for byte. The independent scan did not reimplement numeric extrema/type inference, which are outside the explicitly requested June facts.

## 6. Wait-band detection

Correct for June, but a candidate finder, not sequence validation. The regex is anchored at the start but not the end, ignores case, tolerates initial whitespace, does not require SUM 1, and accepts arbitrary bounds and arbitrary open-ended weeks. Probes accept `Gt 99 To 02 Weeks unexpected` and `Gt 5 Weeks Total`. It checks neither contiguity, order, uniqueness, adjacent bounds, nor 105-column completeness. Total/unknown matching uses substrings, so `subtotal` is a total candidate and flags can overlap. These are documented candidate semantics; do not silently turn the June schema into a universal NHS schema. A separately named structural sequence check with explicit expectations would close the future-input gap without interpreting interval inclusivity.

## 7. Provider/commissioner mappings

Every provider code has one observed name; the sole shared provider name is **DUCHY HOSPITAL → NT447, NVC04**. Provider parents are bijective. Every commissioner code has one raw name value; the only shared value is empty, associated with **NONC, Y56, Y58, Y59, Y60, Y61, Y62, Y63**. All 121 nonblank commissioner names are unique to one code.

The algorithm reports structural cardinality in both directions without picking a correct identity. It does not normalize case/whitespace, distinguish missingness from named-entity collisions, validate referential relationships between roles, or establish consistency over time. A “1:1” result means only a bijection of the observed raw values; one-to-one blank pairs can pass. The findings neither establish a primary key nor justify joins or aggregation rules.

## 8. Test-suite assessment

The original suite passes: **29 passed in 0.15 seconds** with the specified interpreter. There are 17 test functions; the 13 parameterized token examples contribute 13 collected cases. This is useful basic coverage of shape, empty files, no raw mutation, null counts, output creation, ordinary duplicate counting, missing role binding, simple flags, and shared provider names.

It is not merely tautological, but coverage is narrower than the case count suggests. Fixtures have 17 columns and only three selected buckets, omit commissioner parents, and use manual comma joining rather than csv.writer. They cannot establish the actual 121-column schema or complete bucket sequence. No original tests cover malformed quoting, BOM/non-ASCII, duplicate headers, hash collisions, ragged rows, numeric-looking identifier preservation, code-to-multiple-names, blank mapping semantics, uniqueness capping, CLI behavior, or serialized output fidelity. The test called `test_blank_never_becomes_zero_in_type_mix` inspects a column with no blanks; the earlier null/min test provides the meaningful blank-versus-zero check. Output tests check existence and headings, not correctness of emitted facts.

The suite was not inflated or modified. Reproducible audit probes demonstrate real gaps separately, without locking in defective behavior as passing unit tests. Any future bug fix should include a failing regression for that defect first.

## 9. Scalability/reproducibility

The fresh June profile took **14.377 seconds**. The probe process's measured peak working set was **44,515,328 bytes (~42.5 MiB)**, including the interpreter, synthetic probes, profiler and output comparison. This is a single local run, not a performance guarantee. The independent strict scan with disk-backed exact-row uniqueness took 6.719 seconds; its workload differs, so this is not a like-for-like speed comparison.

Streaming is appropriate for roughly 80 MB monthly files. It avoids materializing 22 million cells as Python objects simultaneously. The reported ~797.8 MiB is a hypothetical string-storage estimate, not profiler RAM use; it omits container/reference overhead and is not a reliable DataFrame estimate.

Memory is not constant: row-hash storage grows with distinct rows, category pair Counters are uncapped, and the 500,000 distinct-value cap applies separately to each column. Much larger/high-cardinality inputs can still exhaust memory. Successive monthly runs should release prior profiles; future growth needs measurements and an exact-duplicate strategy with explicit memory limits.

`DEV_MONTH = "2026-06"` is unused by profile_csv/CLI/notebook and creates **no functional monthly coupling**. Its location in package metadata is unnecessary but harmless. The CLI takes an arbitrary file path and output stem; synthetic April/May periods profile without modification. Actual April/May schema compatibility has not been established, because those datasets were deliberately not read. June remains the sole analytical development dataset.

## 10. Files changed

Added only audit artifacts:

- `docs/phase1_audit.md` — this report.
- `outputs/audit/verify_phase1.py` — independent June scanner.
- `outputs/audit/june_2026_verification.json` — independently reconstructed figures, all column missingness/distinct facts, all categorical pairs and counts, checksum.
- `outputs/audit/probe_profiler.py` — synthetic defect probes and fresh profiling benchmark.
- `outputs/audit/profiler_probes.json` — probe/benchmark results.

No existing source, tests, notebook, configuration, raw files, or profile artifacts were edited. Temporary profiling outputs and the SQLite comparison database were discarded. The repository contains pre-existing untracked files; no commits or staging changes were made.

## 11. Unresolved analytical/domain questions

Meaning of blanks; definitions and arithmetic relationships of Total, Total All and unknown-clock fields; C_999 meaning/aggregation safety; DTA expansion; bucket boundary inclusivity; pathway overlap; primary key; provider organizational type; commissioner/parent hierarchy meanings; period/snapshot semantics; and source provenance remain unresolved. Observed labels and cardinalities do not answer these questions. No authoritative publication notes were present in the reviewed repository to settle them.

## 12. Phase 2 recommendation

**Proceed conditionally after a short Phase 1 closure pass**, not directly into cleaning or aggregation. Resolve the misleading exact-duplicate guarantee, duplicate-header ambiguity and permissive-quoting behavior with focused regressions; correct unsupported domain assertions; align reproducibility claims with recorded evidence. Keep sequence detection explicitly structural and missing-value counting explicitly defined. The June file itself passes the requested structural verification. Analytical rules need separately documented authoritative support before Phase 2 acts on them.

The audit stops here; Phase 2 has not begun.
