# Data dictionary — NHS RTT monthly provider extract

Scope: the single CSV `data/raw/rtt_2026_06.csv` (NHS England RTT, June 2026).
This dictionary records **observed structure** from Phase 1 profiling.
**Field meanings, the arithmetic model, the row grain and aggregation safety
were established in Phase 2 — see `docs/rtt_semantics.md` and
`docs/rtt_grain_and_aggregation.md`** (with NHS England citations and evidence
classes). Items previously marked _TBC_ are now resolved there.

- Source: NHS England RTT waiting times, statistical work area
  <https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/>
- File on disk: 82,084,725 bytes (~78.3 MB)
- Rows (excl. header): 182,411
- Columns: 121
- Encoding assumed: `utf-8-sig`; delimiter `,`
- Exact duplicate rows: 0 · ragged rows: 0
- Machine-readable profile: `outputs/profiles/rtt_2026_06__*.csv` / `__overview.md`
- Provenance / SHA-256: `docs/data_provenance.md`

### Counting conventions used by the profiler

- **`null` / `null_pct`** = the cell is an empty string **or whitespace only**.
  Literal `NULL` / `NA` / `NaN` / `None` text is **not** null — it stays a
  `string`. Fields missing from a short (ragged) row are counted as null.
- **`inferred_dtype`** is a shape heuristic, **not a schema**. `001` is reported
  `integer`; numeric `min`/`max` are computed as `float` (large integers can
  lose precision); `date` matches shape, not calendar validity. Raw values are
  preserved verbatim in the categorical / unique-value output.
- **Per-column `n_unique`** excludes blanks. **Categorical `distinct name(s)`**
  in the overview is reported non-blank, with any blank variant labelled
  separately (`+N blank/whitespace`).
- **`week_bucket_columns`** etc. are header-text **candidates**. The contiguity
  / ordering / width of the week-bucket sequence is validated separately and
  reported under "Structural warnings" (none for this file).

## Column groups

| # | Column | Observed type | Null % | Distinct | Notes (observed only) |
|---|--------|---------------|--------|----------|-----------------------|
| 0 | `Period` | string | 0.00 | 1 | Single value `RTT-June-2026`. |
| 1 | `Provider Parent Org Code` | string | 0.00 | 36 | Maps 1:1 to Provider Parent Name in this file. Values look like ICB codes. |
| 2 | `Provider Parent Name` | string | 0.00 | 36 | All contain "INTEGRATED CARE BOARD". |
| 3 | `Provider Org Code` | string | 0.00 | 537 | Candidate identifier component. |
| 4 | `Provider Org Name` | string | 0.00 | 536 | 1 fewer than codes — see mapping anomaly below. |
| 5 | `Commissioner Parent Org Code` | string | 5.63 | 36 | Blank on 10,263 rows. |
| 6 | `Commissioner Parent Name` | string | 5.63 | 36 | Blank on the same rows. |
| 7 | `Commissioner Org Code` | string | 0.00 | 129 | Never blank. |
| 8 | `Commissioner Org Name` | string | 1.84 | 121 non-blank | Blank on 3,348 rows; 8 codes carry an empty name (see anomalies). |
| 9 | `RTT Part Type` | string | 0.00 | 5 | `Part_1A`, `Part_1B`, `Part_2`, `Part_2A`, `Part_3`. |
| 10 | `RTT Part Description` | string | 0.00 | 5 | 1:1 with RTT Part Type in this file (see mapping table). |
| 11 | `Treatment Function Code` | string | 0.00 | 24 | One code is `C_999`; its name is the literal string `Total`. Meaning / roll-up status not established — see `docs/assumptions.md` A-07. |
| 12 | `Treatment Function Name` | string | 0.00 | 24 | 1:1 with Treatment Function Code in this file. |
| 13–117 | `Gt NN To NN Weeks SUM 1` (104 one-week bands) + `Gt 104 Weeks SUM 1` (open-ended) | integer | 27.9–33.0 | varies | Mutually-exclusive weekly wait bands, by **days waited** (0-1 wk = 0–7 days; 17-18 wk incl. 126 days; 104+ = ≥729 days). Populated for Parts 1A/1B/2/2A only; **all blank for Part_3**. A blank band cell **remains missing** (`<NA>`) in the loaded/raw representation. For the independently validated June reconciliation calculations only, a missing band *contribution* may be taken as `0` under a **scoped numerical zero-contribution convention** — this is arithmetic compatibility, **not** proof of semantic equivalence, and is not automatically transferable to another file. See `rtt_semantics.md` §5 and `decisions.md` D-016. |
| 118 | `Total` | integer | 71.96 | 1,283 | Collected for **Parts 1A/1B only** (blank for 2/2A/3 = not-collected). Equals the sum of observed band cells for every completed row. `rtt_semantics.md` §4. |
| 119 | `Patients with unknown clock start date` | integer | 81.30 | 30 | Parts 1A/1B only; **blank on 6,032 Part_1A + 11,005 Part_1B rows** (not "never blank"). Patients with no identifiable RTT clock-start date, so not band-able; an **additive** term to `Total All` on the rows where it is populated. `rtt_semantics.md` §4.1. |
| 120 | `Total All` | integer | 0.00 | 3,576 | Pathway count for the row. 1A/1B: `= Total` where unknown is blank, `= Total + unknown` where populated (extending to all rows uses the missing-as-zero convention). 2/2A: `= sum of observed bands`. 3: standalone count of new clock starts (`observed_bandsum` is `<NA>`). Never blank. `rtt_semantics.md` §4.2. |

### Column flags (header text only — no semantics assigned)

- **total_columns** (2): `Total`, `Total All`
- **unknown_columns** (1): `Patients with unknown clock start date`
- **week_bucket_columns** (105): `Gt 00 To 01 Weeks SUM 1` … `Gt 104 Weeks SUM 1`
  (full list in `outputs/profiles/rtt_2026_06__column_flags.csv`)

## RTT Part Type → Description (observed 1:1)

| Code | Description | Rows |
|------|-------------|------|
| `Part_1A` | Completed Pathways For Admitted Patients | 18,803 |
| `Part_1B` | Completed Pathways For Non-Admitted Patients | 32,351 |
| `Part_2` | Incomplete Pathways | 63,355 |
| `Part_2A` | Incomplete Pathways with DTA | 30,548 |
| `Part_3` | New RTT Periods - All Patients | 37,354 |

Phase 2 (NHS guidance S1 §10.1.1.2): 1A/1B count pathways **completed** in the
month (admitted / non-admitted), 2/2A count pathways **open at month-end**
(2A = with a decision to admit, a **subset** of 2), 3 counts **new clock
starts** in the month. "DTA" = decision to admit. See `rtt_semantics.md` §2.

## Treatment Function Code → Name

24 distinct codes = 23 detail (18 named `C_1xx…C_502` + `X02`–`X06` "Other …"
groupers) + `C_999` "Total". Full list:
`outputs/profiles/rtt_2026_06__treatment_function.csv` and
`outputs/phase2/treatment_function_rows.csv`.

- **`C_999` ("Total") is a pre-computed treatment-function aggregate.** There
  are 23 *possible* reported non-`C_999` codes in June; an individual
  `(provider, commissioner, RTT part)` group carries **1–23** of them (only
  **18** groups carry all 23; **20,518** carry just one). Every June group has
  **exactly one** `C_999` row and **≥1** non-`C_999` row. `C_999` numerically
  equals the sum of the group's *available* non-`C_999` rows: across all
  group×column comparisons there are **0 mismatches where both sides are
  numerical**; the *both-missing* and *`C_999`-zero vs all-missing-detail*
  states are tracked separately and are **not** observed numerical equalities
  (reconciliation under the missing-value convention ≠ observed equality).
  **Analytical rule (supported):** for a selected period/provider/commissioner/
  RTT part use `C_999` **or** the reported non-`C_999` representation — never
  both. `docs/rtt_semantics.md` §6, `docs/rtt_grain_and_aggregation.md` §3/§5.
- `X02`–`X06` are documented leaf groupers ("all other treatment functions in
  the … group not reported individually", S1 §10.1.4); part of the 23-code
  reported set, not further decomposed.

## Provider / commissioner reference

- Provider Org Code → Name: 537 codes / 536 names. See mapping anomalies.
- Provider Parent (36) and full provider list:
  `outputs/profiles/rtt_2026_06__provider.csv`,
  `rtt_2026_06__provider_parent.csv`.
- Commissioner list: `rtt_2026_06__commissioner.csv`.

## Observed mapping anomalies (`rtt_2026_06__mapping_anomalies.csv`)

| Role | Kind | Key | Related |
|------|------|-----|---------|
| provider | one name, two codes | `DUCHY HOSPITAL` | `NT447`, `NVC04` |
| commissioner | blank name, many codes | _(blank)_ | `NONC`, `Y56`, `Y58`–`Y63` (8 codes) |

The 8 collision codes (`NONC`, `Y56`, `Y58`–`Y63`) all share the **empty**
commissioner name. Phase 2: `NONC` = non-English commissioner (S1 §10.1.8);
`Y`-codes = NHS-England-commissioned activity (INFERRED). Join/group on the
**code**, not the name. `docs/rtt_semantics.md` §8.

## Resolved in Phase 2 (was "deferred")

"Clock start", the admitted/non-admitted/incomplete/DTA/new-period distinction,
the `Total` / `Total All` / band arithmetic, band interval inclusivity, the
candidate key, `C_999` roll-up status, and provider-type scope are all covered
in **`docs/rtt_semantics.md`** and **`docs/rtt_grain_and_aggregation.md`**.
Still open: `docs/assumptions.md` "Carried forward" (P2-U1…P2-U6).
