# RTT grain, candidate key & aggregation safety (Phase 2)

Scope: `data/raw/rtt_2026_06.csv`. Companion to `docs/rtt_semantics.md`
(field meanings) and `outputs/phase2/` (result tables). Evidence classes as
defined there.

> **Post-remediation (2026-09-07).** "No other aggregate row type / everything
> else is disjoint detail" is narrowed to **"no additional roll-up marker
> observed"**; a `groupby` on a nullable parent column is shown with explicit
> `dropna=False` and a count-conservation check; the `RTG`/`84H`
> `Part_2A > Part_2` exception is surfaced. See
> `docs/phase2_remediation_report.md`.

---

## 1. Row grain

**What one row represents:** the RTT waiting-time distribution (or count) for

> one **provider** × one **commissioner** × one **treatment function** × one
> **RTT Part Type**, within a single reporting **period**.

* **DOCUMENTED** (S1 §10.1.1.2): "The data collection is provider and
  commissioner based." / "Returns are submitted by providers, split by
  commissioner." / "looks at RTT waiting times in weeks, split by treatment
  function." / the return has the five parts (§10.1.1.2). §10.1.4: "data
  should be submitted for the treatment functions listed below" (23 detail +
  `Total`).
* **EMPIRICALLY VALIDATED** (June): `[Period, Provider Org Code, Commissioner
  Org Code, RTT Part Type, Treatment Function Code]` has exactly one row per
  combination — 182,411 groups for 182,411 rows, 0 duplicates.

Note the grain is **not uniform in meaning across parts** (see
`docs/rtt_semantics.md` §2): 1A/1B rows describe pathways that *completed* in
the month, 2/2A rows pathways *open at month-end*, 3 rows *new clock starts*.
`RTT Part Type` is a genuine grain dimension, not a measure label.

---

## 2. Candidate composite key

**Best-supported key (June):**

```
Period · Provider Org Code · Commissioner Org Code · RTT Part Type · Treatment Function Code
```

`Period` is constant within one monthly file, so within-file the key reduces to
the last four columns. Across files, `Period` is required.

### Uniqueness evidence (`nhs_rtt.semantics.candidate_key_report`)

| Key | Unique? | Duplicate groups | Excess rows |
|---|---|---|---|
| `Period, Provider, Commissioner, RTT Part, Treatment Function Code` | **yes** | 0 | 0 |
| `Provider, Commissioner, RTT Part, Treatment Function Code` (no Period) | **yes** | 0 | 0 |
| `Provider, Commissioner, RTT Part, **Treatment Function Name**` | **yes** | 0 | 0 (name ↔ code is 1:1 in June) |
| `Provider, Provider Parent, Commissioner Parent, Commissioner, RTT Part, Treatment Function Code` | yes | 0 | 0 (parents add nothing) |
| `Provider, RTT Part, Treatment Function Code` (drop Commissioner) | **no** | 16,377 | 163,659 |
| `Provider, Commissioner, RTT Part` (drop Treatment Function) | **no** | 40,636 | 141,775 |

So all four of Provider / Commissioner / RTT Part / Treatment Function Code are
**required**; parent codes are functionally determined and redundant for the
key.

### Status

* **CONFIRMED — DATA**: the key is unique and `usable` for June 2026
  (`candidate_key_report(...)["usable"] is True` — all columns present, no
  missing key cell, no duplicate group).
* **DOCUMENTED**: the key columns match the documented collection grain
  (S1 §10.1.1.2, §10.1.4). Beyond full-key uniqueness (which would make the
  omitted-field checks trivially pass), each child code was shown to determine
  its parent code/name and description in June — stronger evidence.
* **NOT** an NHS-guaranteed primary key, and **not** a patient/pathway
  identifier. NHS England publishes no PK statement for this extract.
* **Acceptance contract (K-2, APPROVE WITH MODIFICATION).** Before relying on
  the key for any incoming file: `validate_extract(...)["ok"]` (see below); all
  five columns present; **no missing key cell**; uniqueness holds **for that
  file**; a defined policy for **revised releases** (`Period` does not
  distinguish a revision of the same month).
  `candidate_key_report(...)["is_unique"]` alone is insufficient — it is
  `None` when a column is absent and `usable` is `False` until every
  precondition passes. **No surrogate key** is introduced.

### Extract-validation gate (Phase 2 production, `validate_extract`)

`load_rtt_csv` runs `validate_extract` first (raising on failure). The gate
requires, **before pandas can mangle the header**: no duplicate header names;
the required key + measure columns; and — the full contract, not just
contiguity — the **exact canonical 105-band schema**
(`expected_week_band_names()`): exactly 105 week-band columns, first band
`Gt 00 To 01 Weeks SUM 1`, the ordered weekly sequence, open-ended final band
`Gt 104 Weeks SUM 1`, **no missing interior band**, no duplicate band, no
unexpected band-like column. It also fixes the missing-value policy
(`keep_default_na=False, na_values=[""]`) so a literal `NULL` in a code column
stays a string. This is a Phase 2 acceptance gate for the agreed extract
format — **not** a Phase 3 ingestion framework. (Generic Phase 1 band
*discovery* stays separate: `nhs_rtt.profile.classify_columns` /
`check_week_bucket_sequence`.)

---

## 3. Reported treatment-function level vs the roll-up marker

| Row type | Identifier | Count (June) | Notes |
|---|---|---|---|
| **Reported detail level** | `Treatment Function Code` ∈ the 23 reported codes (`C_100`…`C_502`, `X02`…`X06`) | 141,775 | The reported analysis level. `X02`–`X06` are themselves internally grouped ("Other …") categories (S1 §10.1.4). Detail rows **per (provider, commissioner, part) group range 1–23** — only 18 groups carry all 23; 20,518 carry just one. |
| **Roll-up marker** | `Treatment Function Code = C_999` (`Treatment Function Name = "Total"`) | 40,636 | Every group has **exactly one**. Numerically = the sum of the group's *available* non-C_999 rows on every numeric column, with **0 mismatches** under the stated zero-contribution convention for missing cells; 928,416 comparisons are both-missing and 588,157 are `C_999`-zero vs all-missing detail (`rtt_semantics.md` §6). |

**No *additional* treatment-function roll-up marker was identified** beyond
`C_999` among the reported June rows. This is "none observed", **not** a
universal guarantee — `Part_2A` overlaps `Part_2`, and absence of a sentinel
string is not proof no other roll-up could exist in another file. Treat the 23
non-`C_999` codes as the **reported** analysis level, not as clinically
indivisible populations; arithmetic equality does not prove patient-level
disjointness. The *commissioner* data files NHS England publishes do carry
sub-ICB/ICB/region/England roll-ups (S6 "Further information"); this **provider
extract** does not.

---

## 4. Aggregation-safety matrix

For each dimension: is it normally safe to **filter** on it, **group by** it,
**sum across** it (i.e. collapse it away), and **join** on it? "Sum across"
assumes you have already restricted to detail rows (`C_999` excluded) unless
noted.

| Dimension | Filter | Group by | Sum across | Join on | Conditions / caveats |
|---|---|---|---|---|---|
| `Period` | ✅ | ✅ | ⚠️ | ✅ | Single value here. Summing across months double-counts open pathways (a Part_2 pathway recurs every month it stays open) — only sum across periods for *flow* parts (1A/1B/3), never for *snapshot* parts (2/2A). |
| `Provider Org Code` | ✅ | ✅ | ✅ | ✅ | Safe. Provider-level detail; no provider aggregate rows. Independent-sector providers included — filter them out explicitly if the analysis is "NHS trusts only" (needs ODS type reference, P2-U4). |
| `Provider Org Name` | ⚠️ | ⚠️ | ⚠️ | ❌ | June: `DUCHY HOSPITAL` maps to two provider codes (`NT447`, `NVC04`). Group/join on the **code**, carry the name for display only. |
| `Provider Parent Org Code` / `Name` | ✅ | ✅ (`dropna=False`) | ✅ | ⚠️ | Label on detail rows; grouping by it aggregates the underlying provider rows. Name ↔ code 1:1 in June. A join to a *separate* parent table must validate join multiplicity (a one-to-many fan-out double counts). |
| `Commissioner Org Code` | ✅ | ✅ | ✅ | ✅ | Safe as reported detail. **Exclude `NONC`** to match England published performance; retain it for total activity **with the coverage caveat** that NONC submission is optional (S5) so NONC rows are not exhaustive of non-English activity. |
| `Commissioner Org Name` | ⚠️ | ❌ | ⚠️ | ❌ | Blank on 3,348 rows (8 codes incl. `NONC`, `Y56`, `Y58`–`Y63`). Group/join on the **code**. |
| `Commissioner Parent Org Code` / `Name` | ⚠️ | ⚠️ **use `dropna=False`** | ⚠️ | ⚠️ | Blank on 10,263 rows (NONC / NHS-England-commissioned). **Pandas `groupby` defaults to `dropna=True`** and will silently drop them — on June Part_2 / `C_999` / excl-NONC that is **489 rows / 131,509 pathways** lost (7,147,562 → 7,016,053). Always pass `dropna=False` (or an explicit "unknown parent" label — do **not** invent a commissioning meaning) and run a count-conservation check (see §4a). |
| `RTT Part Type` | ✅ | ✅ | ❌ | ✅ | **Never sum across parts.** 1A/1B/2/2A/3 are different populations on different event bases; **`Part_2A` ⊆ `Part_2`** (S1 Annex B, with 2 June count exceptions — §5) so `Part_2 + Part_2A` double-counts DTA pathways. One part per analysis. |
| `RTT Part Description` | ✅ | ✅ | ❌ | ✅ | 1:1 with `RTT Part Type`; same rule. |
| `Treatment Function Code` | ✅ | ✅ | ⚠️ | ✅ | Sum **only after excluding `C_999`**, *or* use `C_999` alone — never both (`rtt_semantics.md` §6). Detail rows per group range 1–23; a group may have as few as one. |
| `Treatment Function Name` | ✅ | ✅ | ⚠️ | ⚠️ | 1:1 with code in June; `"Total"` = `C_999`. Same rule. Prefer the code for joins. |
| 105 week-band columns | ✅ (as measures) | n/a | ✅ (sum a contiguous range) | n/a | Measures, not a dimension. Summing a contiguous prefix (e.g. bands ≤ 18) is valid; **do not reshape/melt in Phase 2**. A missing band contributes 0 **by the stated June convention only** — not a semantic rule (`rtt_semantics.md` §5). |
| `Total`, unknown-clock, `Total All` | ✅ (as measures) | n/a | ⚠️ | n/a | Meaningful only for the parts that populate them (`rtt_semantics.md` §4). `Total` / unknown-clock exist for 1A/1B only. Use `Total All` for a per-part pathway count; never sum `Total All` across parts. |

Legend: ✅ safe · ⚠️ safe with the stated condition · ❌ unsafe.

### 4a. Count-conservation check for any grouping

Whenever a `groupby` collapses a dimension, assert the measure total is
preserved:

```python
sub = df[(df["RTT Part Type"] == "Part_2")
         & (df["Treatment Function Name"] == "Total")
         & (df["Commissioner Org Code"] != "NONC")]
total = sub["Total All"].sum()
by_parent = sub.groupby("Commissioner Parent Org Code", dropna=False)["Total All"].sum()
assert by_parent.sum() == total          # dropna=False -> holds (7,147,562)
# default dropna=True would give 7,016,053 and this assert would fail
```

---

## 5. Known double-counting / data-loss risks (ranked)

1. **`C_999` + reported detail rows.** Including the `C_999` / "Total" row in
   any specialty-level `groupby().sum()` doubles the total (adding one specialty
   duplicates that specialty). Filter `Treatment Function Code != "C_999"` for
   specialty analysis, or use `C_999` alone. Direct proof: Part_2 excl-NONC,
   **all** TFC rows sum to **14,295,124**; `C_999` alone (or the reported detail
   alone) = **7,147,562**.
2. **`Part_2` + `Part_2A`.** `Part_2A` is a documented subset of `Part_2`
   (S1 Annex B). `Part_2 + Part_2A` (C_999, excl-NONC) = **8,343,076** vs
   **7,147,562** for Part_2 — it combines a population and its subset; it is
   not a waiting-list size. Also mind the **`RTG`/`84H` exception** (§6): where
   the source violates `Part_2A <= Part_2`, any subset-derived measure
   (Part_2 minus Part_2A, DTA share) must validate the invariant per group
   first — do not cap or alter the raw values.
3. **Default `groupby` on a nullable parent column** silently drops the
   `<NA>` group (`dropna=True`). June Part_2 / `C_999` / excl-NONC loses
   **489 rows / 131,509 pathways**. Use `dropna=False` + the §4a check.
4. **Summing snapshot parts across `Period`.** A `Part_2`/`Part_2A` pathway
   open for *n* months appears in *n* monthly snapshots — those are repeated
   *stock* observations, not distinct events. Cross-`Period` sums are valid
   only for the *flow* parts `Part_1A` / `Part_1B` / `Part_3` (which count
   events, still not necessarily distinct people). Not testable in this
   single-month file — carried forward (P2-U3/P2-U5).
5. **Grouping/joining on names instead of codes.** `DUCHY HOSPITAL` → 2
   provider codes; 8 commissioner codes share a blank name.
6. **Many-to-one joins to a separate organisation table.** If a later phase
   joins a parent/reference table, an unvalidated one-to-many relationship
   fans out the rows and double-counts. Validate join multiplicity; a parent
   *label already on the row* is not itself duplication.

---

## 6. `Part_2A` ⊆ `Part_2` — documented rule and June conformance

**Rule (DOCUMENTED, S1 Annex B):** the count of incomplete pathways with a
decision to admit is a subset of, hence ≤, the count of incomplete pathways —
checked "for matching provider / commissioner / treatment function".

**June conformance (`part_2a_subset_conformance`,
`outputs/phase2/part2a_subset_violations.csv`):** of 30,548 `Part_2A` groups,
all have a matching `Part_2` key and **30,546 conform**. **Two violate:**

| Provider | Commissioner | Treatment Function | Part_2A | Part_2 |
|---|---|---|---|---|
| `RTG` | `84H` | `C_502` (Gynaecology) | 2 | 1 |
| `RTG` | `84H` | `C_999` (Total) | 2 | 1 |

These are a detail row and its total, likely one underlying issue. This is a
**source data-quality exception**, not a refutation of the NHS rule.

**Disposition (decision, D-022):** preserve the source values; flag the
violations; **never cap `Part_2A` or alter `Part_2`**. Any downstream measure
that assumes `Part_2A <= Part_2` (e.g. `Part_2 − Part_2A`, DTA proportion)
must validate the invariant per group before calculating. Carried forward as
`rtt_semantics.md` P2-U7.

---

## 7. Recommended safe default for a specialty-level analysis

```python
df[
    (df["Treatment Function Code"] != "C_999")      # reported detail only
    & (df["RTT Part Type"] == "<one part>")         # never mix parts
    & (df["Commissioner Org Code"] != "NONC")       # for England performance
].groupby(
    ["Provider Org Code", "Treatment Function Code"],
    dropna=False,                                   # keep any <NA> group
)[<band range or "Total All">].sum()
# then: assert the grouped total == the pre-group total (count conservation)
```

For a provider/commissioner total across specialties, use the `C_999` row
directly with the same part and NONC filters — do not also add the detail rows.
