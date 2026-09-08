# Assumptions & unresolved questions

The table below is the **Phase 1 record** — items the profiler deliberately did
not assume. Phase 2 (dataset semantics, grain & arithmetic) has since resolved
most of them against NHS England guidance and the June data; see
**"Phase 2 resolutions"** further down, and `docs/rtt_semantics.md` /
`docs/rtt_grain_and_aggregation.md` for the evidence. Original Phase 1 wording
is left intact.

Status legend: 🔴 open · 🟡 partial evidence · ⚪ needs external doc ·
✅ resolved in Phase 2 · ➡️ carried forward

## Deliberately NOT assumed in Phase 1

| # | We did **not** assume | Why it matters | Evidence seen | Status |
|---|-----------------------|----------------|---------------|--------|
| A-01 | Blank in a week-bucket / `Total` / unknown-clock column means **0** | Summing or filling blanks would fabricate volume | Week buckets 28–33 % blank; `Total` 72 % blank; `Total All` 0 % blank | 🔴 |
| A-02 | `Total`, `Total All`, and "unknown clock start" measure the same thing | They may be different denominators; conflating them corrupts every rate | `Total` null 72 % vs `Total All` null 0 %, different distinct counts and maxima | 🟡 |
| A-03 | `Total All` = sum of the 105 week buckets (+ unknown?) | Needed before trusting any recomputed metric | Not tested — arithmetic reconciliation deferred | 🔴 |
| A-04 | Every `Provider Org Code` is an NHS trust | Independent-sector and other provider types change any "trust" analysis | `DUCHY HOSPITAL` present; provider list not yet classified | ⚪ |
| A-05 | `Provider Org Code` ↔ `Provider Org Name` is 1:1 | Joins / grouping by name would double count or merge | 537 codes vs 536 names; `DUCHY HOSPITAL` → `NT447` + `NVC04` | 🟡 |
| A-06 | `Commissioner Org Code` ↔ `Commissioner Org Name` is 1:1 and always populated | Blank names break name-based joins | 3,348 rows blank name; 8 raw name-collision codes (`NONC`, `Y56`,`Y58`–`Y63`) all share the **empty** name — a blank collision, not a named-entity collision | 🟡 |
| A-07 | `C_999` rows can be summed with the other 23 `Treatment Function Code` rows | If `C_999` is a per-provider subtotal, adding it double counts; if it is a distinct population, excluding it under counts. Which one is unknown. | Observed only: `Treatment Function Code` `C_999` carries the literal `Treatment Function Name` `Total` on 40,636 of 182,411 rows. No arithmetic relationship tested. | 🔴 |
| A-08 | Rows can be aggregated (across providers, functions, or part types) without double counting | A safe `groupby().sum()` needs to know which rows are disjoint populations and which are roll-ups | Observed only: 5 `RTT Part Type` values (incl. `Part_3` "New RTT Periods - All Patients"); `Treatment Function Code` includes `C_999`/`Total` and `X02`–`X06` "Other …" groupers. Overlap/roll-up structure not established. | 🔴 |
| A-09 | A primary key is known | Needed for dedupe, joins, and month-over-month tracking | 0 exact duplicate rows, but candidate key (Period + Provider + Commissioner + Part + TFC) not verified unique | 🔴 |
| A-10 | Week-bucket columns should be reshaped to long form now | Premature; bucket semantics (`Gt 00 To 01` = 0–1 wks? inclusive?) unconfirmed | 105 buckets + open-ended `Gt 104 Weeks` | 🔴 |
| A-11 | `Provider Parent Org Code` is the commissioning/geography hierarchy to use | Two parents present (provider parent + commissioner parent); roles differ | Provider Parent = 36 ICBs; Commissioner Parent = 36, 5.6 % blank | ⚪ |
| A-12 | The single `Period` value / `RTT-June-2026` label maps to a specific calendar month-end snapshot | Time-series alignment across files | Only one period per file observed | ⚪ |
| A-13 | `RTT Part Type` values are mutually exclusive and collectively exhaustive of pathways | Rate denominators | 5 values, 1:1 with descriptions; overlap logic unconfirmed | ⚪ |
| A-14 | The abbreviation "DTA" in `Part_2A` ("Incomplete Pathways with DTA") stands for anything in particular | Interpreting `Part_2A` vs `Part_2` | Observed only: the literal description string. No expansion is asserted; a commonly-seen reading ("Decision To Admit") is **not** verified against any repository-held NHS source. | ⚪ |
| A-15 | Independent-sector / blank-parent rows are in scope for headline metrics | NHS England headline figures may exclude some provider types | Commissioner parent blank on 10,263 rows; provider list contains non-trust names (e.g. SpaMedica, Optegra) | ⚪ |
| A-16 | The blank-named commissioner codes (`NONC`, `Y5x`, `Y6x`) are national / specialised-commissioning identifiers | Deciding whether those rows join to a commissioner dimension | Observed only: those codes carry an empty `Commissioner Org Name`. Any interpretation of the `Y`-prefix is a guess, not verified. | ⚪ |
| A-17 | Bucket header text (`Gt 00 To 01 Weeks`) implies specific interval inclusivity (e.g. 0 ≤ w < 1) | Any week-threshold metric (18/52 week) | Observed only: 104 contiguous unit-width ranged headers + one open-ended `Gt 104 Weeks`. Boundary semantics not established. | 🔴 |

## Phase 2 resolutions (2026-09-07; revised after independent audit)

Evidence classes: **DOCS+DATA** = NHS definition + shown in June data;
**DATA** = shown in June data, not found verbatim in guidance;
**DOCUMENTED** = NHS definition, not row-testable here; **INFERRED**;
**UNRESOLVED**.

> Audit corrections applied: A-01 narrowed to an explicit *arithmetic
> convention*; A-02/A-03 corrected for the completed-part unknown-clock blanks
> (6,032 / 11,005 rows) and split into strict subsets + a stated missing-as-zero
> policy; A-07 evidence wording scoped; a new data-quality item **P2-U7**
> (`RTG`/`84H` `Part_2A > Part_2`). See `docs/phase2_remediation_report.md`.

| Phase 1 item | Phase 2 outcome | Class | Evidence |
|---|---|---|---|
| A-01 blank = 0 | 🟡 **Narrowed — arithmetic convention only.** For the **June** banded parts, the sum of *observed* band cells reconciles to the reported totals, and remains exact if missing band contributions are also treated as `0`. This is a **scoped, non-destructive numerical convention**, applied per calculation — **not** semantic equivalence, **not** global imputation, **not** automatically valid for future files. Blank in `Total`/unknown for Parts 2/2A/3, and every Part_3 band = **not-collected** (structural). Raw missingness preserved (`<NA>`). NHS Annex B has total/quality checks, **not** a cell-encoding rule. | DATA (convention) | `rtt_semantics.md` §5; `outputs/phase2/blank_zero_by_part.csv` |
| A-02 `Total` = `Total All` = unknown | ✅ **They differ.** 1A/1B: `Total = observed_bandsum`; `Total All = Total + unknown` (unknown-clock is **blank on 6,032 / 11,005 rows** — on those `Total = Total All`; extending the additive form to them needs the missing-as-zero convention). 2/2A: `Total`/unknown not collected; `Total All = observed_bandsum`. 3: only `Total All` (a count; `observed_bandsum` is `<NA>`). | DOCS+DATA | `reconciliation_by_part.csv`, `reconciliation_coverage_by_part.csv`; `rtt_semantics.md` §4 |
| A-03 `Total All` = Σ bands (+ unknown?) | ✅ **Conditional by part**, with the coverage/policy split above. Every *expected* check `HOLDS` with full subset coverage (strict) or `HOLDS (missing-as-zero convention)` for June. | DOCS+DATA | as A-02 |
| A-04 every provider is an NHS trust | ✅ **No.** Independent-sector providers are in scope (S1 §10.1.1.1) and present (SpaMedica, Optegra, …). Org-type classification needs ODS reference files — carried forward (P2-U4). | DOCS+DATA | `rtt_semantics.md` §7 |
| A-05 provider code ↔ name 1:1 | 🟡➡️ June: 1:1 except `DUCHY HOSPITAL` → `NT447`+`NVC04`. Group/join on **code**. Cross-month stability untested (P2-U3). | DATA | `rtt_grain_and_aggregation.md` §4 |
| A-06 commissioner code ↔ name 1:1 & populated | 🟡➡️ June: name blank on 3,348 rows / 8 codes (`NONC`, `Y56`, `Y58`–`Y63`) — a blank collision. Join on **code**. | DATA | `rtt_grain_and_aggregation.md` §4–5 |
| A-07 `C_999` may be summed with specialties | ✅ **No — double-counts** (rule supported). `C_999` = the sum of the group's *available* non-C_999 rows on every numeric column with **0 numeric mismatches** under the stated zero-contribution convention, over all 40,636 groups (each with exactly one C_999 row, ≥1 detail row; detail rows per group range **1–23**, only 18 groups carry all 23). 928,416 comparisons are both-missing and 588,157 are agg-zero vs all-missing detail — reported separately, not counted as observed equality. | DOCS (rule) + DATA | `rtt_semantics.md` §6; `outputs/phase2/facts.json` |
| A-08 rows may be summed | ✅ **Only with rules.** Aggregation-safety matrix + double-counting risks documented. Never sum across `RTT Part Type` (`Part_2A` ⊆ `Part_2`); exclude `C_999` for specialty sums; never sum snapshot parts across months. | DOCS+DATA | `rtt_grain_and_aggregation.md` §4–5 |
| A-09 primary key unknown | ✅ **Best-supported key found** (not an NHS-guaranteed PK): `Period · Provider Org Code · Commissioner Org Code · RTT Part Type · Treatment Function Code` — unique for all 182,411 June rows. No surrogate key manufactured. | DATA (grain: DOCS) | `rtt_grain_and_aggregation.md` §1–2 |
| A-10 reshape week bands now | ➡️ **Still deferred** (Phase 2 must not reshape). Band structure/inclusivity now documented (§3), so a later phase can melt safely. | — | `rtt_semantics.md` §3 |
| A-11 which parent hierarchy | 🟡 Provider Parent (ICB) and Commissioner Parent are **labels on detail rows**, no aggregate rows. Which to use is an analysis choice, not a data fact. | DATA | `rtt_grain_and_aggregation.md` §3–4 |
| A-12 `Period` → calendar month | ➡️ Single value `RTT-June-2026`; mapping/formatting is a later-phase concern (P2-U5). | UNRESOLVED | — |
| A-13 `RTT Part Type` mutually exclusive & exhaustive | 🟡 1A/1B/2/2A/3 are distinct populations, **but `Part_2A` ⊆ `Part_2`** (S1 Annex B) so not disjoint; not "exhaustive of pathways" in a set sense (different event bases). | DOCUMENTED | `rtt_semantics.md` §2 |
| A-14 "DTA" = Decision To Admit | ✅ Confirmed (S1 §10.1.1.2 / terminology). | DOCS | `rtt_semantics.md` §2 |
| A-15 IS / blank-parent rows in scope for headline metrics | 🟡 IS providers are in the collection; England **performance** excludes non-English commissioners (`NONC`) and adds non-submitter estimates. Exact scope of the published headline (provider-type filters, estimation) is UNRESOLVED (P2-U1). | DOCS (partial) | `rtt_semantics.md` §8–9 |
| A-16 `NONC`/`Y5x`/`Y6x` = specialised/non-English commissioning | ✅ `NONC` = non-English commissioner (S1 §10.1.8/§10.1.9.2). `Y`-code specifics still **INFERRED** (NHS-England-commissioned per S1 §10.1.10). | DOCS+DATA (NONC); INFERRED (Y-codes) | `rtt_semantics.md` §8 |
| A-17 band interval inclusivity | ✅ Bands are by days waited; a 126-day / 18-week wait is in the **17-18** band; "≤ k weeks" = bands with upper bound ≤ k (S1 §10.1.7). NHS gives **5** worked examples (0-1, 1-2, 17-18, 51-52, 104+); intermediate bounds are **derived and labelled as derived** (P2-U6). | DOCUMENTED | `rtt_semantics.md` §3 |

### Carried forward (UNRESOLVED after Phase 2 — see `rtt_semantics.md` §10)

* **P2-U1** exact **estimate-inclusive** England headline. The June 2026
  publication **is** available and its **unestimated** Table 1 totals reproduce
  exactly; the non-submitter uplift (RHQ, RA9) is not implemented. Do not claim
  exact estimate-inclusive reproduction.
* **P2-U2** whether incomplete pathways with an unknown clock start exist / are
  folded into a band. **The earlier "negligible / folded" inference is
  withdrawn** — neither the empty field nor the zero residual proves it.
* **P2-U3** cross-month stability of code↔name maps and the candidate key;
  revised-release handling. Required during multi-month ingestion.
* **P2-U4** provider organisational-type classification (needs ODS `etr` /
  `ephp` / `ephpsite` / `ect` reference files). Do not infer type from names.
* **P2-U5** `Period` literal → calendar-month-end; file-revision handling.
  Part-specific temporal meaning (flow vs month-end stock) **is** documented.
* **P2-U6** full per-band day ranges — **narrowed**: 5 NHS examples + stated
  sequence; intermediate bounds derived (`7n+1 … 7(n+1)` for band `n`–`n+1`).
* **P2-U7** (new) the `RTG` / `84H` `Part_2A > Part_2` count exception — a
  data-quality issue. Raw values preserved and flagged; any measure assuming
  `Part_2A <= Part_2` must validate the invariant per group first.

## Data-availability note

- The brief named **April 2025**; supplied files are **April/May/June 2026**.
- Per corrected instruction, Phase 1 profiles **June 2026 only**
  (`rtt_2026_06.csv`). April/May 2026 files exist but are untouched.
- Provenance is **partially** recorded: `docs/data_provenance.md` now holds the
  size and SHA-256; source URL, download timestamp, NHS publication date, and
  revision status remain **NOT SUPPLIED** (see `docs/decisions.md` D-004, D-011).

## Reproducibility gaps (audit M5 — open)

- The profiler does not record source URL / download time / package versions;
  the README previously implied it did (now corrected).
- `requirements.txt` / `pyproject.toml` use **minimum version bounds, not pins**,
  and there is no lockfile. A hash-pinned lockfile is deferred to a later phase.
- The notebook assumes it is run from `notebooks/` or the repo root and uses a
  generic `python3` kernel rather than an enforced interpreter.

## Scalability note (audit §9 — open)

`profile_csv` holds one exact serialisation per **distinct row** (for a true
whole-row duplicate count) plus uncapped categorical pair counters; the
per-column distinct-value cap (`DEFAULT_MAX_UNIQUE_TRACKED`) is applied
per column. This is comfortable for ~80 MB monthly RTT files (measured peak
working set well under 200 MB) but is **not constant memory**. Much larger or
higher-cardinality inputs need a disk-backed exact-duplicate strategy and
explicit memory limits.

## Recommended next validation step

_Phase 1's recommendation (reconcile band sum vs `Total` / `Total All`) was
carried out in Phase 2 — see `docs/rtt_semantics.md` §4._

**Resolved (same-month benchmark).** The **June 2026** RTT publication (SPN
Table 1, published 13 Aug 2026 — S6) is available, and its *unestimated*
England totals reproduce **exactly** from `rtt_2026_06.csv` with
`Treatment Function Name = Total`, excluding `Commissioner Org Code = NONC`
(`outputs/phase2/same_month_totals_check.csv`):

| Measure | value |
|---|---|
| Incomplete pathways | 7,147,562 |
| Completed admitted | 318,650 |
| Completed non-admitted | 1,307,837 |
| New RTT periods | 1,930,912 |
| % incomplete within 18 weeks | 65.826% → published **65.8%** (1 dp) |

**Still unresolved (P2-U1).** The **estimate-inclusive** national headline
additionally uplifts for the two non-submitting trusts (RHQ, RA9); that uplift
is **not** implemented, and matching at 1 dp is not exact estimate-inclusive
reproduction. (The earlier draft compared against May 2026's 65.6%; that
cross-month comparison is withdrawn — see `docs/decisions.md` D-023.)
