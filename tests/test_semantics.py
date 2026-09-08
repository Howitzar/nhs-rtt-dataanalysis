"""Tests for :mod:`nhs_rtt.semantics` (Phase 2, post-remediation + closure).

Three clearly separated groups:

* ``TestCodeCorrectness``            — pure logic on tiny synthetic frames.
* ``TestRawImmutability``            — the raw file is never written.
* ``TestJune2026DatasetInvariants``  — regression locks for the observed values
  of ``data/raw/rtt_2026_06.csv``. NOT NHS-domain guarantees; skipped if absent.

Synthetic tests that only exercise *non-schema* logic load their miniature CSV
with ``require_full_band_schema=False`` (helper ``_load``); the Phase 2
production band-schema gate is exercised separately by ``TestCodeCorrectness``'s
``*_band_schema*`` tests with a realistic 105-band header.

Each test maps to a substantive behaviour or an independent-audit finding
(P2-A01 … P2-A10, P2-R01). Phase 1 tests are unaffected.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest

from nhs_rtt import semantics as S

JUNE = Path(__file__).resolve().parents[1] / "data" / "raw" / "rtt_2026_06.csv"
JUNE_SHA256 = "edc3927e4a0065855ad3b2347e7f82688e687b065406eefb49e2f67a9cd67f02"


@pytest.fixture(scope="module")
def june_df():
    if not JUNE.exists():
        pytest.skip("June 2026 raw file not present")
    return S.load_rtt_csv(JUNE)


# --- miniature schema: a clean 4-band sequence (not the production 105) -------
_LABELS = [
    "Period", "Provider Org Code", "Provider Org Name",
    "Commissioner Org Code", "Commissioner Org Name",
    "RTT Part Type", "RTT Part Description",
    "Treatment Function Code", "Treatment Function Name",
]
_BANDS = ["Gt 00 To 01 Weeks SUM 1", "Gt 01 To 02 Weeks SUM 1",
          "Gt 02 To 03 Weeks SUM 1", "Gt 03 Weeks SUM 1"]
_TAIL = ["Total", "Patients with unknown clock start date", "Total All"]
HEADER = _LABELS + _BANDS + _TAIL

# --- realistic full 105-band schema for the extract-gate tests ---------------
_FULL_BANDS = S.expected_week_band_names()
FULL_HEADER = _LABELS + _FULL_BANDS + _TAIL


def _row(provider="RAA", comm="00A", part="Part_2", tfc="C_100",
         tfn="General Surgery Service", bands=("", "", "", ""),
         total="", unknown="", total_all=""):
    return ["RTT-June-2026", provider, "PROVIDER A", comm, "COMM A", part,
            {"Part_2": "Incomplete Pathways",
             "Part_1A": "Completed Pathways For Admitted Patients",
             "Part_3": "New RTT Periods - All Patients"}.get(part, "Incomplete Pathways"),
            tfc, tfn, *[str(b) for b in bands], str(total), str(unknown), str(total_all)]


def _full_row(part="Part_2", tfc="C_100", tfn="General Surgery Service",
              first_band="1", total_all="1", total="", unknown=""):
    bands = [first_band] + ["0"] * 104
    return ["RTT-June-2026", "RAA", "P", "00A", "C", part,
            "Incomplete Pathways", tfc, tfn, *bands, str(total), str(unknown), str(total_all)]


def _mini_csv(tmp_path: Path, rows, name="mini.csv", header=None) -> Path:
    p = tmp_path / name
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header or HEADER)
        w.writerows(rows)
    return p


def _load(p: Path, **kw):
    """Load a miniature synthetic CSV, bypassing the production 105-band gate."""
    return S.load_rtt_csv(p, require_full_band_schema=False, **kw)


# ========================================================================= #
class TestCodeCorrectness:

    # --- week-band identification -----------------------------------------
    def test_parse_week_band(self):
        assert S.parse_week_band("Gt 17 To 18 Weeks SUM 1") == (17, 18)
        assert S.parse_week_band("Gt 104 Weeks SUM 1") == (104, None)
        with pytest.raises(ValueError):
            S.parse_week_band("Total All")

    def test_week_band_columns_order_and_broken_sequence(self):
        assert S.week_band_columns(HEADER) == _BANDS
        with pytest.raises(ValueError, match="sequence is not clean"):
            S.week_band_columns(["Gt 00 To 01 Weeks", "Gt 05 To 06 Weeks"])

    def test_bands_up_to_weeks(self):
        cols = [f"Gt {i:02d} To {i+1:02d} Weeks SUM 1" for i in range(20)] + ["Gt 20 Weeks SUM 1"]
        b18 = S.bands_up_to_weeks(cols, 18)
        assert b18[0] == "Gt 00 To 01 Weeks SUM 1"
        assert b18[-1] == "Gt 17 To 18 Weeks SUM 1"
        assert len(b18) == 18 and "Gt 20 Weeks SUM 1" not in b18

    def test_expected_week_band_names_is_canonical_105(self):
        names = S.expected_week_band_names()
        assert len(names) == 105
        assert names[0] == "Gt 00 To 01 Weeks SUM 1"
        assert names[103] == "Gt 103 To 104 Weeks SUM 1"
        assert names[104] == "Gt 104 Weeks SUM 1"

    # --- P2-A09: the FULL 105-band extract-schema gate -------------------
    def test_band_schema_accepts_exact_105(self, tmp_path: Path):
        p = _mini_csv(tmp_path, [_full_row(total_all=1)], header=FULL_HEADER)
        assert S.validate_extract(p)["ok"] is True
        df = S.load_rtt_csv(p)                       # production gate, default
        assert len(S.week_band_columns(df.columns.tolist())) == 105

    @pytest.mark.parametrize("mutate,expect", [
        ("drop_all", "expected 105 week-band columns, found 0"),
        ("keep_one", "found 1"),
        ("drop_first", "missing expected week-band column"),
        ("drop_open_end", "missing expected week-band column"),
        ("drop_interior", "missing expected week-band column"),
        ("duplicate_band", "duplicate week-band column"),
        ("extra_band", "unexpected week-band-like column"),
    ])
    def test_band_schema_rejects_malformed(self, tmp_path: Path, mutate, expect):
        bands = list(_FULL_BANDS)
        if mutate == "drop_all":
            bands = []
        elif mutate == "keep_one":
            bands = [bands[5]]                       # a single 5-6 week band
        elif mutate == "drop_first":
            bands = bands[1:]
        elif mutate == "drop_open_end":
            bands = bands[:-1]
        elif mutate == "drop_interior":
            del bands[50]
        elif mutate == "duplicate_band":
            bands = bands + [bands[10]]
        elif mutate == "extra_band":
            bands = bands + ["Gt 200 To 201 Weeks SUM 1"]
        header = _LABELS + bands + _TAIL
        p = tmp_path / "bad_schema.csv"
        with p.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerow((["RTT-June-2026", "RAA", "P", "00A", "C", "Part_2",
                         "Incomplete Pathways", "C_100", "GS"]
                        + ["0"] * len(bands) + ["", "", "1"]))
        rep = S.validate_extract(p)
        assert rep["ok"] is False
        assert rep["expected_band_schema_ok"] is False
        assert any(expect in prob for prob in rep["problems"]), rep["problems"]
        with pytest.raises(ValueError):
            S.load_rtt_csv(p)                        # production default rejects it

    # --- loader / NA policy (P2-A09) ------------------------------------
    def test_load_preserves_blank_vs_zero(self, tmp_path: Path):
        df = _load(_mini_csv(tmp_path, [_row(bands=(5, 0, "", ""), total_all=5)]))
        assert str(df["Gt 00 To 01 Weeks SUM 1"].dtype) == "Int64"
        assert df.loc[0, "Gt 01 To 02 Weeks SUM 1"] == 0
        assert pd.isna(df.loc[0, "Gt 02 To 03 Weeks SUM 1"])

    def test_load_keeps_literal_NA_tokens_as_strings(self, tmp_path: Path):
        df = _load(_mini_csv(tmp_path, [_row(comm="NULL", total_all=1)]))
        assert df.loc[0, "Commissioner Org Code"] == "NULL"
        assert df["Commissioner Org Code"].notna().all()

    def test_load_rejects_duplicate_headers(self, tmp_path: Path):
        bad = list(HEADER)
        bad[2] = "Provider Org Code"
        p = _mini_csv(tmp_path, [_row(total_all=1)], header=bad)
        with pytest.raises(ValueError, match="duplicate header"):
            _load(p)
        assert S.validate_extract(p, require_full_band_schema=False)["ok"] is False

    def test_load_rejects_missing_key_column(self, tmp_path: Path):
        bad = [h for h in HEADER if h != "Treatment Function Code"]
        p = tmp_path / "nokey.csv"
        with p.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(bad)
            w.writerow(_row(total_all=1)[:len(bad)])
        with pytest.raises(ValueError, match="missing key column"):
            _load(p)

    def test_load_rejects_negative(self, tmp_path: Path):
        p = _mini_csv(tmp_path, [_row(bands=(-1, 0, 0, 0), total_all=0)])
        with pytest.raises(ValueError, match="negative"):
            _load(p)

    # --- observed_band_sum: <NA> iff all bands missing (P2-A01) --------
    def test_observed_band_sum_semantics(self, tmp_path: Path):
        df = _load(_mini_csv(tmp_path, [
            _row(part="Part_3", bands=("", "", "", ""), total_all=7),
            _row(part="Part_2", bands=(2, "", 3, ""), total_all=5),
        ]))
        s = S.observed_band_sum(df, _BANDS)
        assert pd.isna(s.iloc[0])
        assert s.iloc[1] == 5

    # --- reconciliation coverage + verdict discipline (P2-A02/A04) -----
    def test_reconciliation_reports_coverage_and_convention(self, tmp_path: Path):
        df = _load(_mini_csv(tmp_path, [
            _row(part="Part_1A", bands=(2, 3, 0, 1), total=6, unknown=4, total_all=10),
            _row(part="Part_1A", bands=(1, 0, 0, 0), total=1, unknown="", total_all=1),
        ]))
        r = S.reconciliation_summary(df)
        tu = r[(r["rule"] == "Total + unknown == Total All") & (r["policy"] == "strict")].iloc[0]
        assert tu["n_in_subset"] == 1 and tu["n_evaluated"] == 1 and tu["verdict"] == "HOLDS"
        tt = r[r["rule"] == "Total == Total All"].iloc[0]
        assert tt["n_in_subset"] == 1 and tt["verdict"] == "HOLDS"
        mz = r[r["rule"] == "Total + unknown(missing->0) == Total All"].iloc[0]
        assert mz["policy"] == "missing-as-zero"
        assert mz["n_convention_rows"] == 1
        assert mz["n_missing_operand"] == 0
        assert mz["n_match"] == 2 and mz["n_mismatch"] == 0
        assert mz["verdict"] == "HOLDS (missing-as-zero convention)"

    def test_reconciliation_partial_verdict_when_rows_excluded(self, tmp_path: Path):
        df = _load(_mini_csv(tmp_path, [_row(part="Part_3", bands=("", "", "", ""), total_all=9)]))
        row = S.reconciliation_summary(df).iloc[0]
        assert row["n_excluded_missing"] == 1
        assert row["verdict"].startswith("PARTIAL")
        assert row["verdict"] != "HOLDS"

    def test_reconciliation_fails_on_broken_row(self, tmp_path: Path):
        df = _load(_mini_csv(tmp_path, [
            _row(part="Part_2", bands=(1, 1, 0, 0), total_all=2),
            _row(part="Part_2", bands=(1, 1, 0, 0), total_all=9),
        ]))
        row = S.reconciliation_summary(df)
        row = row[(row["part"] == "Part_2") & (row["rule"] == "observed_bandsum == Total All")].iloc[0]
        assert row["verdict"] == "FAILS" and row["n_mismatch"] == 1
        assert row["diff_min"] == -7 and row["n_match"] == 1

    def test_reconciliation_coverage_by_part_partitions(self, tmp_path: Path):
        df = _load(_mini_csv(tmp_path, [
            _row(part="Part_1A", bands=(1, 0, 0, 0), total=1, unknown=0, total_all=1),
            _row(part="Part_1A", bands=(2, 0, 0, 0), total=2, unknown="", total_all=2),
        ]))
        cov = S.reconciliation_coverage_by_part(df).set_index("part")
        assert cov.loc["Part_1A", "unknown_present_subset"] == 1
        assert cov.loc["Part_1A", "unknown_blank_subset"] == 1
        assert bool(cov.loc["Part_1A", "covers_all_rows"]) is True

    # --- P2-R01: missing-as-zero must NOT certify undefined comparisons -
    def test_missing_as_zero_excludes_missing_total_all(self, tmp_path: Path):
        # one valid completed row + one with Total All missing
        df = _load(_mini_csv(tmp_path, [
            _row(part="Part_1A", bands=(0, 0, 0, 0), total=0, unknown=0, total_all=0),
            _row(part="Part_1A", bands=(0, 0, 0, 0), total=0, unknown=0, total_all=""),
        ]))
        r = S.reconciliation_summary(df)
        for rule in ("Total + unknown(missing->0) == Total All",
                     "observed_bandsum + unknown(missing->0) == Total All"):
            row = r[r["rule"] == rule].iloc[0]
            assert row["n_in_subset"] == 2
            assert row["n_evaluated"] == 1
            assert row["n_missing_operand"] == 1
            assert row["n_match"] == 1
            assert row["verdict"].startswith("PARTIAL")

    def test_missing_as_zero_all_total_all_missing_no_typeerror(self, tmp_path: Path):
        df = _load(_mini_csv(tmp_path, [
            _row(part="Part_1A", bands=(0, 0, 0, 0), total=0, unknown=0, total_all=""),
            _row(part="Part_1A", bands=(0, 0, 0, 0), total=0, unknown=0, total_all=""),
        ]))
        r = S.reconciliation_summary(df)          # must not raise
        row = r[r["rule"] == "Total + unknown(missing->0) == Total All"].iloc[0]
        assert row["n_evaluated"] == 0 and row["n_excluded_missing"] == 2
        assert pd.isna(row["diff_min"]) and row["verdict"].startswith("PARTIAL")

    def test_missing_total_is_not_zero_filled(self, tmp_path: Path):
        df = _load(_mini_csv(tmp_path, [
            _row(part="Part_1A", bands=(1, 0, 0, 0), total="", unknown=0, total_all=1),
        ]))
        r = S.reconciliation_summary(df)
        row = r[r["rule"] == "Total + unknown(missing->0) == Total All"].iloc[0]
        assert row["n_evaluated"] == 0            # missing Total -> excluded, not a match
        assert row["verdict"].startswith("PARTIAL")

    def test_authorised_blank_unknown_still_holds(self, tmp_path: Path):
        df = _load(_mini_csv(tmp_path, [
            _row(part="Part_1A", bands=(3, 0, 0, 0), total=3, unknown="", total_all=3),
        ]))
        r = S.reconciliation_summary(df)
        row = r[r["rule"] == "Total + unknown(missing->0) == Total All"].iloc[0]
        assert row["n_convention_rows"] == 1 and row["n_match"] == 1
        assert row["verdict"] == "HOLDS (missing-as-zero convention)"

    def test_ordinary_valid_reconciliation(self, tmp_path: Path):
        df = _load(_mini_csv(tmp_path, [
            _row(part="Part_1A", bands=(2, 3, 0, 1), total=6, unknown=2, total_all=8),
            _row(part="Part_1A", bands=(1, 0, 0, 0), total=1, unknown="", total_all=1),
        ]))
        exp = S.reconciliation_summary(df).query("expected")
        assert exp["verdict"].str.startswith("HOLDS").all()   # both subsets populated

    # --- candidate key (P2-A09) --------------------------------------
    def test_candidate_key_detects_duplicate(self, tmp_path: Path):
        dup = _row(part="Part_2", tfc="C_100", total_all=1)
        df = _load(_mini_csv(tmp_path, [dup, list(dup), _row(part="Part_2", tfc="C_101", total_all=1)]))
        rep = S.candidate_key_report(df, S.CANDIDATE_KEY)
        assert rep["is_unique"] is False and rep["n_excess_rows"] == 1 and rep["usable"] is False

    def test_candidate_key_missing_column_is_not_unique_true(self):
        df = pd.DataFrame({"Provider Org Code": ["A", "B"], "Total All": [1, 2]})
        rep = S.candidate_key_report(df, S.CANDIDATE_KEY)
        assert rep["is_unique"] is None and rep["usable"] is False
        assert "Treatment Function Code" in rep["missing_cols"]

    def test_candidate_key_usable_requires_nonmissing_key_cells(self):
        df = pd.DataFrame({
            "Period": ["p", "p"], "Provider Org Code": ["A", "B"],
            "Commissioner Org Code": ["c", pd.NA], "RTT Part Type": ["Part_2", "Part_2"],
            "Treatment Function Code": ["C_100", "C_101"],
        })
        rep = S.candidate_key_report(df, S.CANDIDATE_KEY)
        assert rep["is_unique"] is True and rep["n_key_cells_missing"] == 1 and rep["usable"] is False

    # --- aggregate_vs_detail hardening (P2-A04/A08) -----------------
    def _agg_kwargs(self):
        return dict(agg_col="Treatment Function Code", agg_value="C_999",
                    group_cols=["Provider Org Code", "Commissioner Org Code", "RTT Part Type"],
                    value_cols=_BANDS + _TAIL)

    def test_aggregate_vs_detail_clean_group(self, tmp_path: Path):
        rows = [
            _row(tfc="C_100", bands=(1, 0, 0, 0), total_all=1),
            _row(tfc="C_101", bands=(2, 0, 0, 0), total_all=2),
            _row(tfc="C_999", tfn="Total", bands=(3, 0, 0, 0), total_all=3),
        ]
        res = S.aggregate_vs_detail(_load(_mini_csv(tmp_path, rows)), **self._agg_kwargs())
        assert res["reconciles_numeric"] is True and res["acceptable"] is True
        assert res["n_agg_only_groups"] == 0 and res["n_detail_only_groups"] == 0

    def test_aggregate_vs_detail_orphan_and_dup_and_zero_missing(self, tmp_path: Path):
        rows = [
            _row(provider="A", tfc="C_100", bands=(1, 0, 0, 0), total_all=1),
            _row(provider="B", tfc="C_999", tfn="Total", bands=(1, 0, 0, 0), total_all=1),
            _row(provider="C", tfc="C_999", tfn="Total", bands=(1, 0, 0, 0), total_all=1),
            _row(provider="C", tfc="C_999", tfn="Total", bands=(1, 0, 0, 0), total_all=1),
            _row(provider="C", tfc="C_100", bands=(2, 0, 0, 0), total_all=2),
            _row(provider="D", tfc="C_999", tfn="Total", bands=(0, 0, 0, 0), total_all=0),
            _row(provider="D", tfc="C_100", bands=("", "", "", ""), total_all=0),
        ]
        res = S.aggregate_vs_detail(_load(_mini_csv(tmp_path, rows)), **self._agg_kwargs())
        assert res["n_detail_only_groups"] == 1
        assert res["n_agg_only_groups"] == 1
        assert res["n_groups_multiple_agg_rows"] == 1
        assert res["cmp_agg_zero_vs_all_missing_detail"] >= 1
        assert res["reconciles_numeric"] is False and res["acceptable"] is False

    def test_aggregate_missing_vs_numeric_detail_not_acceptable(self, tmp_path: Path):
        # single group: C_999 Total All missing, one detail row Total All = 9
        rows = [
            _row(tfc="C_100", bands=(0, 0, 0, 0), total_all=9),
            _row(tfc="C_999", tfn="Total", bands=(0, 0, 0, 0), total_all=""),
        ]
        res = S.aggregate_vs_detail(_load(_mini_csv(tmp_path, rows)), **self._agg_kwargs())
        assert res["cmp_other_missing"] >= 1
        assert res["acceptable"] is False               # policy-aware overall
        assert res["reconciles_missing_as_zero"] is False

    # --- Part_2A subset conformance (P2-A05) -----------------------
    def test_part2a_subset_conformance_flags_violation(self, tmp_path: Path):
        rows = [
            _row(provider="X", comm="c", tfc="C_100", part="Part_2", total_all=5),
            _row(provider="X", comm="c", tfc="C_100", part="Part_2A", total_all=3),
            _row(provider="Y", comm="c", tfc="C_100", part="Part_2", total_all=1),
            _row(provider="Y", comm="c", tfc="C_100", part="Part_2A", total_all=4),
        ]
        res = S.part_2a_subset_conformance(_load(_mini_csv(tmp_path, rows)))
        assert res["n_violations"] == 1
        v = res["violations"].iloc[0]
        assert v["Provider Org Code"] == "Y" and v["part_2a"] == 4 and v["part_2"] == 1
        assert "Preserve source values" in res["disposition"]

    # --- NONC split (P2-A03) --------------------------------------
    def test_nonc_prevalence_has_no_pathway_total(self, tmp_path: Path):
        rows = [_row(comm="NONC", part="Part_2", tfc="C_999", tfn="Total", total_all=5),
                _row(comm="NONC", part="Part_2", tfc="C_100", total_all=5),
                _row(comm="00A", part="Part_2", total_all=9)]
        prev = S.nonc_prevalence(_load(_mini_csv(tmp_path, rows)))
        assert prev["n_rows"] == 2
        assert "pathways" not in prev and "total_all_pathways" not in prev
        assert "not mandatory" in prev["coverage_note"]

    def test_nonc_pathways_by_part_one_representation(self, tmp_path: Path):
        rows = [_row(comm="NONC", part="Part_2", tfc="C_999", tfn="Total", total_all=5),
                _row(comm="NONC", part="Part_2", tfc="C_100", total_all=3),
                _row(comm="NONC", part="Part_2", tfc="C_101", total_all=2)]
        df = _load(_mini_csv(tmp_path, rows))
        c999 = S.nonc_pathways_by_part(df, representation="C_999").set_index("RTT Part Type")
        detail = S.nonc_pathways_by_part(df, representation="detail").set_index("RTT Part Type")
        assert c999.loc["Part_2", "pathways"] == 5
        assert detail.loc["Part_2", "pathways"] == 5
        assert bool(c999.loc["Part_2", "do_not_sum_across_parts"]) is True

    def test_nonc_raw_checksum_is_labelled_uninterpreted(self, tmp_path: Path):
        rows = [_row(comm="NONC", part="Part_2", tfc="C_999", tfn="Total", total_all=5),
                _row(comm="NONC", part="Part_2", tfc="C_100", total_all=5)]
        chk = S.nonc_raw_cell_checksum(_load(_mini_csv(tmp_path, rows)))
        assert chk["raw_total_all_sum_all_nonc_rows"] == 10
        assert "double-counts" in chk["warning"]

    # --- 18-week measure (P2-A06) -------------------------------
    def test_incomplete_within_18wk_math(self, tmp_path: Path):
        cols = [f"Gt {i:02d} To {i+1:02d} Weeks SUM 1" for i in range(19)] + ["Gt 19 Weeks SUM 1"]
        header = _LABELS + cols + _TAIL
        p = tmp_path / "op.csv"
        with p.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerow(["RTT-June-2026", "RAA", "P", "00A", "C", "Part_2", "Incomplete Pathways",
                        "C_999", "Total"] + ["1"] * 18 + ["0", "2"] + ["", "", "20"])
            w.writerow(["RTT-June-2026", "RAA", "P", "NONC", "", "Part_2", "Incomplete Pathways",
                        "C_999", "Total"] + ["5"] * 18 + ["0", "0"] + ["", "", "90"])
        r = S.incomplete_within_18wk(_load(p), exclude_nonc=True)
        assert r["n_bands_used"] == 18 and r["within_18wk"] == 18 and r["total_all"] == 20
        assert r["pct_within_18wk"] == 90.0
        assert "benchmark_june_2026_spn_unestimated" in r

    # --- controlled examples (P2-A10) --------------------------
    def test_controlled_examples_shape(self, june_df):
        ex = S.controlled_examples(june_df)
        notes = " ".join(ex["note"])
        assert "unknown>0" in notes
        assert "unknown blank" in notes
        assert "DATA-QUALITY" in notes
        p3 = ex[ex["RTT Part Type"] == "Part_3"]
        assert len(p3) and p3["observed_bandsum"].isna().all()


# ========================================================================= #
class TestRawImmutability:

    def test_assert_raw_unchanged_roundtrip(self, tmp_path: Path):
        p = _mini_csv(tmp_path, [_row(total_all=1)])
        before = p.read_bytes()
        digest = S.assert_raw_unchanged(p)
        _load(p)
        assert S.assert_raw_unchanged(p, digest) == digest
        assert p.read_bytes() == before

    def test_assert_raw_unchanged_detects_change(self, tmp_path: Path):
        p = _mini_csv(tmp_path, [_row(total_all=1)])
        with pytest.raises(AssertionError):
            S.assert_raw_unchanged(p, "0" * 64)


# ========================================================================= #
@pytest.mark.skipif(not JUNE.exists(), reason="June 2026 raw file not present")
class TestJune2026DatasetInvariants:
    """Regression locks for observed values of rtt_2026_06.csv. NOT domain
    guarantees; may differ for another month."""

    def test_raw_sha256_unchanged(self, june_df):
        assert S.assert_raw_unchanged(JUNE, JUNE_SHA256) == JUNE_SHA256

    def test_shape_and_bands(self, june_df):
        assert june_df.shape == (182411, 121)
        assert S.week_band_columns(june_df.columns.tolist()) == S.expected_week_band_names()
        assert S.validate_extract(JUNE)["expected_band_schema_ok"] is True

    def test_expected_identities_hold_with_full_coverage(self, june_df):
        r = S.reconciliation_summary(june_df)
        exp = r[r["expected"]]
        assert len(exp) == 12
        assert exp["verdict"].str.startswith("HOLDS").all(), \
            exp[~exp["verdict"].str.startswith("HOLDS")].to_dict("records")
        strict = exp[exp["policy"] == "strict"]
        assert (strict["n_excluded_missing"] == 0).all()
        mz = exp[exp["policy"] == "missing-as-zero"]
        assert (mz["n_missing_operand"] == 0).all()          # no missing required operand in June

    def test_completed_unknown_blank_counts(self, june_df):
        r = S.reconciliation_summary(june_df).set_index(["part", "rule"])
        assert r.loc[("Part_1A", "Total + unknown == Total All"), "n_in_subset"] == 12771
        assert r.loc[("Part_1A", "Total == Total All"), "n_in_subset"] == 6032
        assert r.loc[("Part_1B", "Total + unknown == Total All"), "n_in_subset"] == 21346
        assert r.loc[("Part_1B", "Total == Total All"), "n_in_subset"] == 11005
        bz = S.blank_zero_summary(june_df).set_index("part")
        assert bz.loc["Part_1A", "unknown_blank"] == 6032
        assert bz.loc["Part_1B", "unknown_blank"] == 11005

    def test_candidate_key(self, june_df):
        assert S.candidate_key_report(june_df, S.CANDIDATE_KEY)["usable"] is True
        no_period = [c for c in S.CANDIDATE_KEY if c != "Period"]
        assert S.candidate_key_report(june_df, no_period)["is_unique"] is True
        four = [c for c in S.CANDIDATE_KEY if c != "Treatment Function Code"]
        assert S.candidate_key_report(june_df, four)["is_unique"] is False
        no_comm = [c for c in S.CANDIDATE_KEY if c != "Commissioner Org Code"]
        assert S.candidate_key_report(june_df, no_comm)["is_unique"] is False

    def test_c999_reconciliation_states(self, june_df):
        band_cols = S.week_band_columns(june_df.columns.tolist())
        res = S.aggregate_vs_detail(
            june_df, agg_col="Treatment Function Code", agg_value="C_999",
            group_cols=["Provider Org Code", "Commissioner Org Code", "RTT Part Type"],
            value_cols=band_cols + S.NUMERIC_TAIL_COLS)
        assert res["n_common_groups"] == 40636
        assert res["n_agg_only_groups"] == 0 and res["n_detail_only_groups"] == 0
        assert res["n_groups_multiple_agg_rows"] == 0
        assert res["cmp_numeric_mismatch"] == 0
        assert res["cmp_both_missing"] == 928416
        assert res["cmp_agg_zero_vs_all_missing_detail"] == 588157
        assert res["cmp_other_missing"] == 0
        assert res["detail_rows_per_group_min"] == 1
        assert res["detail_rows_per_group_max"] == 23
        assert res["n_groups_one_detail_row"] == 20518
        assert res["n_groups_at_max_detail_rows"] == 18
        assert res["acceptable"] is True

    def test_nonc(self, june_df):
        prev = S.nonc_prevalence(june_df)
        assert prev["n_rows"] == 2993 and prev["n_providers"] == 119
        by_part = S.nonc_pathways_by_part(june_df, representation="C_999").set_index("RTT Part Type")
        assert by_part.loc["Part_1A", "pathways"] == 1224
        assert by_part.loc["Part_1B", "pathways"] == 4478
        assert by_part.loc["Part_2", "pathways"] == 31156
        assert by_part.loc["Part_2A", "pathways"] == 7734
        assert by_part.loc["Part_3", "pathways"] == 6649
        assert S.nonc_raw_cell_checksum(june_df)["raw_total_all_sum_all_nonc_rows"] == 102482

    def test_part2a_subset_exception_RTG_84H(self, june_df):
        res = S.part_2a_subset_conformance(june_df)
        assert res["n_violations"] == 2
        v = res["violations"].set_index("Treatment Function Code")
        for tfc in ("C_502", "C_999"):
            assert v.loc[tfc, "Provider Org Code"] == "RTG"
            assert v.loc[tfc, "Commissioner Org Code"] == "84H"
            assert v.loc[tfc, "part_2a"] == 2 and v.loc[tfc, "part_2"] == 1

    def test_same_month_totals_match_june_spn(self, june_df):
        chk = S.same_month_totals_check(june_df).set_index("measure")
        assert chk["matches"].all()
        assert chk.loc["incomplete (Part_2)", "raw_file_value"] == 7147562
        assert chk.loc["completed admitted (Part_1A)", "raw_file_value"] == 318650
        assert chk.loc["completed non-admitted (Part_1B)", "raw_file_value"] == 1307837
        assert chk.loc["new RTT periods (Part_3)", "raw_file_value"] == 1930912
        b = S.incomplete_within_18wk(june_df, exclude_nonc=True)["benchmark_june_2026_spn_unestimated"]
        assert b["total_all_matches"] is True and b["pct_matches_1dp"] is True

    def test_part3_is_count_only(self, june_df):
        bz = S.blank_zero_summary(june_df).set_index("part")
        assert bz.loc["Part_3", "rows_all_bands_blank"] == bz.loc["Part_3", "n_rows"]
        assert bz.loc["Part_3", "Total_blank"] == bz.loc["Part_3", "n_rows"]
        assert bz.loc["Part_3", "unknown_blank"] == bz.loc["Part_3", "n_rows"]
        assert bz.loc["Part_3", "TotalAll_pos"] == bz.loc["Part_3", "n_rows"]
