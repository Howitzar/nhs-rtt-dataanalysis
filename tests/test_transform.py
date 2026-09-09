"""Tests for :mod:`nhs_rtt.transform` (Phase 4 — transformation, data quality
and the analytical dataset).

Synthetic only — no test reads ``data/raw/`` or the real publication. Fixtures
build a real 105-band header from :func:`nhs_rtt.semantics.expected_week_band_names`,
load it through the frozen :func:`nhs_rtt.semantics.load_rtt_csv`, and combine it
through the frozen :func:`nhs_rtt.crossmonth.combine_months`, so every Phase 4
invariant is exercised against genuinely Phase-3-shaped input (125 columns,
nullable dtypes, ``<NA>`` missingness, the four provenance columns).
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from nhs_rtt import crossmonth as X
from nhs_rtt import ingest as I
from nhs_rtt import semantics as S
from nhs_rtt import transform as T


def _sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _rewrite_long(df: pd.DataFrame, path) -> None:
    """Re-serialize a (possibly mutated) long frame with the exact production
    Arrow schema — models a fault introduced *after* the real write."""
    tbl = pa.Table.from_pandas(df[T.LONG_COLUMNS], schema=T._long_arrow_schema(),
                               preserve_index=False)
    pq.write_table(tbl, str(path))

_LABELS = [
    "Period", "Provider Parent Org Code", "Provider Parent Name",
    "Provider Org Code", "Provider Org Name",
    "Commissioner Parent Org Code", "Commissioner Parent Name",
    "Commissioner Org Code", "Commissioner Org Name",
    "RTT Part Type", "RTT Part Description",
    "Treatment Function Code", "Treatment Function Name",
]
_BANDS = S.expected_week_band_names()
_TAIL = ["Total", "Patients with unknown clock start date", "Total All"]
HEADER = _LABELS + _BANDS + _TAIL
_PERIOD = {"2026-04": "RTT-April-2026", "2026-05": "RTT-May-2026", "2026-06": "RTT-June-2026"}
_PART_DESC = {
    "Part_1A": "Completed Pathways For Admitted Patients",
    "Part_1B": "Completed Pathways For Non-Admitted Patients",
    "Part_2": "Incomplete Pathways",
    "Part_2A": "Incomplete Pathways with DTA",
    "Part_3": "New RTT Periods - All Patients",
}


def _row(month, *, provider="RAA", pname=None, comm="00A", cname="COMM ONE",
         part="Part_2", tfc="C_100", tfn=None, bands=None, first_band=1,
         total="", unknown="", total_all=1, bands_blank=False):
    if bands is None:
        bands = [""] * 105 if bands_blank else [str(first_band)] + ["0"] * 104
    pname = pname or f"PROV {provider}"
    tfn = tfn or ("Total" if tfc == "C_999" else "General Surgery Service")
    return [_PERIOD[month], "QAA", "PARENT A", provider, pname,
            "QAA", "PARENT A", comm, cname, part, _PART_DESC[part],
            tfc, tfn, *bands, str(total), str(unknown), str(total_all)]


def _write_csv(path: Path, rows) -> Path:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        w.writerows(rows)
    return path


def _payload(tmp_path: Path, month: str, rows) -> X.MonthPayload:
    name = f"rtt_{month.replace('-', '_')}.csv"
    p = _write_csv(tmp_path / name, rows)
    return X.MonthPayload(reporting_month=month, source_file=name,
                          source_sha256=I.sha256_file(p), df=S.load_rtt_csv(p))


def _combined(tmp_path: Path, rows_by_month: dict[str, list]) -> pd.DataFrame:
    payloads = [_payload(tmp_path, m, rows) for m, rows in rows_by_month.items()]
    return X.combine_months(payloads)


def _vin(combined: pd.DataFrame, tmp_path: Path) -> T.VerifiedInput:
    return T.VerifiedInput(
        df=combined.reset_index(drop=True), interim_dir=tmp_path,
        generation_id="g" * 64, combined_rows=len(combined),
        parquet_sha256="p" * 64,
        verification={"valid": True, "generation_id": "g" * 64,
                      "combined_rows": len(combined)},
    )


@pytest.fixture
def simple_combined(tmp_path: Path) -> pd.DataFrame:
    return _combined(tmp_path, {
        "2026-04": [
            _row("2026-04", part="Part_1A", tfc="C_100", first_band=3, total=3, total_all=3),
            _row("2026-04", part="Part_2", tfc="C_100", first_band=5, total_all=5),
            _row("2026-04", part="Part_2", tfc="C_999", first_band=5, total_all=5),
            _row("2026-04", part="Part_2A", tfc="C_100", first_band=2, total_all=2),
            _row("2026-04", part="Part_3", tfc="C_999", bands_blank=True, total_all=9),
            _row("2026-04", part="Part_2", tfc="C_100", comm="NONC", first_band=1, total_all=1),
        ],
        "2026-06": [
            _row("2026-06", part="Part_2", tfc="C_100", first_band=7, total_all=7),
            _row("2026-06", part="Part_2", tfc="C_101", first_band=1, total_all=1),
        ],
    })


# ========================================================================= #
class TestInputGate:

    def _publish(self, tmp_path: Path) -> Path:
        payloads = [_payload(tmp_path, "2026-06", [
            _row("2026-06", part="Part_2", tfc="C_100"),
            _row("2026-06", part="Part_2", tfc="C_101")])]
        combined = X.combine_months(payloads)
        out = tmp_path / "interim"
        X.write_combined_parquet(combined, out, payloads=payloads)
        return out

    def test_accepts_a_verified_publication(self, tmp_path: Path):
        out = self._publish(tmp_path)
        vin = T.load_verified_publication(out)
        assert vin.combined_rows == 2
        assert list(vin.df.columns[-4:]) == X.PROVENANCE_COLS

    def test_rejects_when_marker_missing(self, tmp_path: Path):
        out = self._publish(tmp_path)
        (out / X.GENERATION_MARKER).unlink()
        with pytest.raises(T.PublicationNotVerifiedError):
            T.load_verified_publication(out)

    def test_rejects_when_marker_tampered(self, tmp_path: Path):
        out = self._publish(tmp_path)
        marker = out / X.GENERATION_MARKER
        m = json.loads(marker.read_text())
        m["combined_rows"] = 999999
        marker.write_text(json.dumps(m))
        with pytest.raises(T.PublicationNotVerifiedError):
            T.load_verified_publication(out)

    def test_does_not_write_to_interim(self, tmp_path: Path):
        out = self._publish(tmp_path)
        before = {p.name: p.stat().st_mtime_ns for p in out.iterdir()}
        T.load_verified_publication(out)
        after = {p.name: p.stat().st_mtime_ns for p in out.iterdir()}
        assert before == after

    def test_run_phase4_refuses_unverified_input(self, tmp_path: Path):
        (tmp_path / "empty").mkdir()
        with pytest.raises(T.PublicationNotVerifiedError):
            T.run_phase4(interim_dir=tmp_path / "empty", out_dir=tmp_path / "proc")

    def test_run_phase4_refuses_out_dir_equal_to_interim(self, tmp_path: Path):
        out = self._publish(tmp_path)
        with pytest.raises(T.TransformError, match="must not be"):
            T.run_phase4(interim_dir=out, out_dir=out)


class TestAnalyticalWide:

    def test_row_conservation_and_grain(self, simple_combined, tmp_path):
        wide = T.build_analytical_wide(_vin(simple_combined, tmp_path))
        assert len(wide) == len(simple_combined)
        krep = S.candidate_key_report(wide, S.CANDIDATE_KEY)
        assert krep["usable"] and krep["is_unique"]

    def test_source_values_and_missingness_preserved(self, simple_combined, tmp_path):
        wide = T.build_analytical_wide(_vin(simple_combined, tmp_path))
        src = simple_combined.sort_values(["reporting_month", "source_row_index"]).reset_index(drop=True)
        a = src.astype(object).where(pd.notna(src), None)
        b = wide[src.columns].astype(object).where(pd.notna(wide[src.columns]), None)
        assert a.equals(b)
        # a Part_3 row keeps every band <NA>; a populated row keeps its explicit 0
        p3 = wide[wide["RTT Part Type"] == "Part_3"].iloc[0]
        assert p3[_BANDS].isna().all()
        p2 = wide[wide["RTT Part Type"] == "Part_2"].iloc[0]
        assert p2["Gt 05 To 06 Weeks SUM 1"] == 0        # explicit zero, not <NA>

    def test_no_blanket_fillna_zero(self, simple_combined, tmp_path):
        wide = T.build_analytical_wide(_vin(simple_combined, tmp_path))
        # rows that were all-blank bands in the source are still all-<NA>
        assert int(wide[_BANDS].isna().all(axis=1).sum()) == \
            int(simple_combined[_BANDS].isna().all(axis=1).sum()) == 1

    def test_derived_classifications(self, simple_combined, tmp_path):
        wide = T.build_analytical_wide(_vin(simple_combined, tmp_path))
        assert (wide["is_treatment_function_total"] ==
                (wide["Treatment Function Code"] == "C_999")).all()
        assert (wide["is_nonc_commissioner"] ==
                (wide["Commissioner Org Code"] == "NONC")).all()
        assert wide.loc[wide["RTT Part Type"] == "Part_1A",
                        "rtt_part_event_basis"].eq("completed_admitted_in_month").all()
        assert wide.loc[wide["RTT Part Type"] == "Part_3",
                        "rtt_part_carries_bands"].eq(False).all()
        assert wide.loc[wide["RTT Part Type"].isin(["Part_2", "Part_2A"]),
                        "rtt_part_is_month_end_snapshot"].all()
        assert not wide.loc[wide["RTT Part Type"] == "Part_3",
                            "rtt_part_is_month_end_snapshot"].any()

    def test_time_metadata_from_reporting_month(self, simple_combined, tmp_path):
        wide = T.build_analytical_wide(_vin(simple_combined, tmp_path))
        apr = wide[wide["reporting_month"] == "2026-04"].iloc[0]
        assert apr["reporting_year"] == 2026
        assert apr["reporting_month_num"] == 4
        assert apr["reporting_month_name"] == "April"
        assert pd.Timestamp(apr["reporting_period_start_date"]) == pd.Timestamp("2026-04-01")
        assert apr["Period"] == "RTT-April-2026"            # raw Period untouched

    def test_dq_all_bands_missing_and_total_missing(self, simple_combined, tmp_path):
        wide = T.build_analytical_wide(_vin(simple_combined, tmp_path))
        assert (wide["dq_all_bands_missing"] == wide[_BANDS].isna().all(axis=1)).all()
        assert (wide["dq_total_missing"] == wide["Total"].isna()).all()

    def test_dq_part2a_flags_preserve_and_flag(self, tmp_path):
        # month with 1 violation (2A=2 > 2=1) and 1 unmatched Part_2A group
        combined = _combined(tmp_path, {"2026-05": [
            _row("2026-05", part="Part_2", tfc="C_100", total_all=1),
            _row("2026-05", part="Part_2A", tfc="C_100", total_all=2),   # violation
            _row("2026-05", part="Part_2A", tfc="C_205", total_all=1),   # unmatched
        ]})
        wide = T.build_analytical_wide(_vin(combined, tmp_path))
        viol = wide[wide["dq_part2a_gt_part2"]]
        assert len(viol) == 1 and viol.iloc[0]["Treatment Function Code"] == "C_100"
        assert viol.iloc[0]["Total All"] == 2                # not capped
        assert int(wide["dq_part2a_no_matching_part2"].sum()) == 1
        # frozen conformance agrees
        conf = S.part_2a_subset_conformance(wide)
        assert conf["n_violations"] == 1 and conf["n_without_matching_part_2"] == 1

    def test_deterministic(self, simple_combined, tmp_path):
        v = _vin(simple_combined, tmp_path)
        pd.testing.assert_frame_equal(T.build_analytical_wide(v), T.build_analytical_wide(v))


class TestWaitBandMetadata:

    def test_derived_from_frozen_contract(self):
        meta = T.wait_band_metadata()
        assert len(meta) == T.N_WAIT_BANDS == 105
        assert meta["wait_band_label"].tolist() == S.expected_week_band_names()
        assert meta["wait_band_order"].tolist() == list(range(1, 106))

    def test_boundaries_and_open_ended(self):
        meta = T.wait_band_metadata().set_index("wait_band_order")
        assert (meta.loc[1, "wait_band_lower_weeks"], meta.loc[1, "wait_band_upper_weeks"]) == (0, 1)
        assert (meta.loc[18, "wait_band_lower_weeks"], meta.loc[18, "wait_band_upper_weeks"]) == (17, 18)
        assert meta.loc[105, "wait_band_lower_weeks"] == 104
        assert pd.isna(meta.loc[105, "wait_band_upper_weeks"])
        assert bool(meta.loc[105, "is_open_ended"]) is True
        assert int(meta["is_open_ended"].sum()) == 1

    def test_derived_day_ranges_follow_p2u6_formula(self):
        meta = T.wait_band_metadata().set_index("wait_band_order")
        assert (meta.loc[1, "wait_band_lower_days"], meta.loc[1, "wait_band_upper_days"]) == (0, 7)
        # band n-(n+1): days 7n+1 .. 7(n+1)  -> band order = n+1
        assert (meta.loc[18, "wait_band_lower_days"], meta.loc[18, "wait_band_upper_days"]) == (7 * 17 + 1, 7 * 18)
        assert meta.loc[105, "wait_band_lower_days"] == 729
        assert pd.isna(meta.loc[105, "wait_band_upper_days"])


class TestWaitingBandLong:

    def test_dense_cardinality(self, simple_combined, tmp_path):
        wide = T.build_analytical_wide(_vin(simple_combined, tmp_path))
        long = T.build_waiting_band_long(wide, block_rows=3)
        assert len(long) == len(wide) * 105
        per_parent = long.groupby(["source_file", "source_row_index"]).size()
        assert (per_parent == 105).all()
        assert long["wait_band_label"].drop_duplicates().sort_values().tolist() == \
            sorted(S.expected_week_band_names())
        assert int(long.duplicated(
            subset=["source_file", "source_row_index", "wait_band_order"]).sum()) == 0

    def test_band_order_ascending_per_parent(self, simple_combined, tmp_path):
        wide = T.build_analytical_wide(_vin(simple_combined, tmp_path))
        long = T.build_waiting_band_long(wide, block_rows=100)
        g = long.groupby(["source_file", "source_row_index"])["wait_band_order"]
        assert g.apply(lambda s: s.tolist() == list(range(1, 106))).all()

    def test_missingness_preserved_zero_vs_na(self, simple_combined, tmp_path):
        wide = T.build_analytical_wide(_vin(simple_combined, tmp_path))
        long = T.build_waiting_band_long(wide, block_rows=100)
        # the Part_3 parent contributes 105 <NA> pathway_count rows
        p3 = wide[wide["RTT Part Type"] == "Part_3"].iloc[0]
        seg = long[(long["source_file"] == p3["source_file"]) &
                   (long["source_row_index"] == p3["source_row_index"])]
        assert seg["pathway_count"].isna().all()
        # a populated parent: exactly one positive band, 104 explicit zeros, 0 <NA>
        pop = wide[wide["RTT Part Type"] == "Part_1A"].iloc[0]
        seg = long[(long["source_file"] == pop["source_file"]) &
                   (long["source_row_index"] == pop["source_row_index"])]
        assert seg["pathway_count"].isna().sum() == 0
        assert (seg["pathway_count"] == 0).sum() == 104
        assert (seg["pathway_count"] > 0).sum() == 1

    def test_cell_level_reconciliation(self, simple_combined, tmp_path):
        wide = T.build_analytical_wide(_vin(simple_combined, tmp_path))
        long = T.build_waiting_band_long(wide, block_rows=4)
        rec = T.reconcile_long_against_wide(wide, long)
        assert rec["value_mismatches"] == 0 and rec["na_state_mismatches"] == 0
        assert rec["cells"] == len(wide) * 105

    def test_lineage_every_long_row_has_a_parent(self, simple_combined, tmp_path):
        wide = T.build_analytical_wide(_vin(simple_combined, tmp_path))
        long = T.build_waiting_band_long(wide, block_rows=5)
        parents = set(map(tuple, wide[["source_file", "source_row_index"]].to_numpy()))
        got = set(map(tuple, long[["source_file", "source_row_index"]].drop_duplicates().to_numpy()))
        assert got == parents
        assert long["source_sha256"].nunique() == wide["source_sha256"].nunique()

    def test_streamed_write_matches_in_memory(self, simple_combined, tmp_path):
        wide = T.build_analytical_wide(_vin(simple_combined, tmp_path))
        mem = T.build_waiting_band_long(wide, block_rows=7)
        res = T.write_waiting_band_long(wide, tmp_path / "long.parquet", block_rows=7)
        assert res.rows == res.expected_rows == len(mem)
        disk = pd.read_parquet(tmp_path / "long.parquet").astype(mem.dtypes.to_dict())
        pd.testing.assert_frame_equal(
            disk.sort_values(["source_file", "source_row_index", "wait_band_order"]).reset_index(drop=True),
            mem.sort_values(["source_file", "source_row_index", "wait_band_order"]).reset_index(drop=True),
        )
        assert res.na_count == int(mem["pathway_count"].isna().sum())
        assert res.zero_count == int((mem["pathway_count"] == 0).sum())

    def test_open_band_upper_is_null(self, simple_combined, tmp_path):
        wide = T.build_analytical_wide(_vin(simple_combined, tmp_path))
        long = T.build_waiting_band_long(wide, block_rows=100)
        open_rows = long[long["wait_band_label"] == "Gt 104 Weeks SUM 1"]
        assert open_rows["wait_band_upper_weeks"].isna().all()
        assert (open_rows["wait_band_lower_weeks"] == 104).all()
        assert (long[long["wait_band_order"] < 105]["wait_band_upper_weeks"].notna()).all()


class TestReport:

    def _run(self, simple_combined, tmp_path):
        wide = T.build_analytical_wide(_vin(simple_combined, tmp_path))
        meta = T.wait_band_metadata()
        res = T.write_waiting_band_long(wide, tmp_path / "long.parquet", block_rows=100)
        long = pd.read_parquet(tmp_path / "long.parquet")
        rec = T.reconcile_long_against_wide(wide, long)
        rep = T.build_transformation_report(
            _vin(simple_combined, tmp_path), wide, res, meta, long_reconciliation=rec)
        return wide, rep

    def test_report_structure(self, simple_combined, tmp_path):
        _, rep = self._run(simple_combined, tmp_path)
        for key in ("input_integrity", "transformation_integrity", "missingness",
                    "semantic_diagnostics", "row_level_quality_conditions",
                    "dataset_level_diagnostics", "dense_long_benchmark", "outputs"):
            assert key in rep
        assert rep["transformation_integrity"]["wide_row_conservation_ok"] is True
        assert rep["transformation_integrity"]["long_cardinality_ok"] is True
        assert rep["missingness"]["no_blanket_fillna_zero"] is True
        for flag in T.DQ_FLAG_COLS:
            assert flag in rep["row_level_quality_conditions"]

    def test_report_separates_row_level_from_dataset_level(self, simple_combined, tmp_path):
        _, rep = self._run(simple_combined, tmp_path)
        assert set(rep["row_level_quality_conditions"]) == set(T.DQ_FLAG_COLS)
        assert "mapping" in rep["dataset_level_diagnostics"]
        assert "part_2a_subset_by_month" in rep["semantic_diagnostics"]

    def test_markdown_render(self, simple_combined, tmp_path):
        _, rep = self._run(simple_combined, tmp_path)
        md = T.render_report_markdown(rep)
        assert md.startswith("# Phase 4")
        assert "Dense-long benchmark" in md and "Part_2A" in md


class TestRunPhase4EndToEnd:

    def test_end_to_end_small(self, tmp_path: Path):
        payloads = [
            _payload(tmp_path, "2026-05", [
                _row("2026-05", part="Part_2", tfc="C_100", first_band=4, total_all=4),
                _row("2026-05", part="Part_2A", tfc="C_100", first_band=1, total_all=1),
                _row("2026-05", part="Part_3", tfc="C_999", bands_blank=True, total_all=9)]),
            _payload(tmp_path, "2026-06", [
                _row("2026-06", part="Part_2", tfc="C_100", first_band=2, total_all=2)]),
        ]
        combined = X.combine_months(payloads)
        interim = tmp_path / "interim"
        X.write_combined_parquet(combined, interim, payloads=payloads)

        res = T.run_phase4(interim_dir=interim, out_dir=tmp_path / "processed",
                           block_rows=2, write_long=True, reconcile_long=True)
        assert res.ok is True
        assert res.wide_rows == len(combined) == 4
        assert res.long_result.rows == 4 * 105 == res.long_result.expected_rows
        assert res.long_reconciliation["value_mismatches"] == 0
        for name in (T.ANALYTICAL_WIDE_PARQUET, T.WAITING_BAND_LONG_PARQUET,
                     T.WAIT_BAND_METADATA_PARQUET, T.TRANSFORM_REPORT_JSON,
                     T.TRANSFORM_REPORT_MD):
            assert (tmp_path / "processed" / name).exists()
        rep = json.loads((tmp_path / "processed" / T.TRANSFORM_REPORT_JSON).read_text())
        assert rep["transformation_integrity"]["long_cardinality_ok"] is True

    def test_end_to_end_is_deterministic(self, tmp_path: Path):
        payloads = [_payload(tmp_path, "2026-06", [
            _row("2026-06", part="Part_2", tfc="C_100", first_band=3, total_all=3),
            _row("2026-06", part="Part_2", tfc="C_101", first_band=1, total_all=1)])]
        combined = X.combine_months(payloads)
        interim = tmp_path / "interim"
        X.write_combined_parquet(combined, interim, payloads=payloads)

        o1, o2 = tmp_path / "p1", tmp_path / "p2"
        T.run_phase4(interim_dir=interim, out_dir=o1, block_rows=1)
        T.run_phase4(interim_dir=interim, out_dir=o2, block_rows=1)
        for name in (T.ANALYTICAL_WIDE_PARQUET, T.WAITING_BAND_LONG_PARQUET,
                     T.WAIT_BAND_METADATA_PARQUET):
            assert _sha(o1 / name) == _sha(o2 / name), name


# ========================================================================= #
# Codex Phase 4 audit remediation — adversarial regression                    #
# ========================================================================= #

def _publish_phase3(tmp_path: Path, rows_by_month: dict[str, list], *,
                     sub="interim") -> tuple[Path, pd.DataFrame]:
    payloads = [_payload(tmp_path, m, r) for m, r in rows_by_month.items()]
    combined = X.combine_months(payloads)
    out = tmp_path / sub
    X.write_combined_parquet(combined, out, payloads=payloads)
    return out, combined


class TestP4A01InputBinding:
    """P4-A01 — the consumed frame / digest / generation must always refer to
    the *verified immutable snapshot*, never to whatever the live path holds at
    read time."""

    def _pub(self, tmp_path):
        return _publish_phase3(tmp_path, {"2026-06": [
            _row("2026-06", part="Part_2", tfc="C_100", first_band=5, total_all=5),
            _row("2026-06", part="Part_2", tfc="C_101", first_band=1, total_all=1)]})

    def test_digest_generation_and_frame_agree_with_marker(self, tmp_path):
        interim, combined = self._pub(tmp_path)
        marker = json.loads((interim / X.GENERATION_MARKER).read_text())
        vin = T.load_verified_publication(interim)
        assert vin.parquet_sha256 == marker["parquet_sha256"]
        assert vin.generation_id == marker["generation_id"]
        assert len(vin.df) == marker["combined_rows"] == len(combined)

    def test_change_after_verification_is_rejected_on_next_load(self, tmp_path):
        interim, _ = self._pub(tmp_path)
        T.load_verified_publication(interim)                     # ok once
        # mutate the live publication parquet (same row count, one value changed)
        df = pd.read_parquet(interim / T.PHASE3_PUBLICATION_PARQUET)
        df.loc[0, "Total All"] = 999
        df.to_parquet(interim / T.PHASE3_PUBLICATION_PARQUET, index=False)
        with pytest.raises(T.PublicationNotVerifiedError):
            T.load_verified_publication(interim)

    def test_change_and_restore_during_read_uses_snapshot(self, tmp_path, monkeypatch):
        interim, combined = self._pub(tmp_path)
        live = interim / T.PHASE3_PUBLICATION_PARQUET
        good_bytes = live.read_bytes()
        marker = json.loads((interim / X.GENERATION_MARKER).read_text())
        real_read = T.pd.read_parquet

        def racing_read(path, *a, **k):
            # scribble on the LIVE publication, then restore it, then delegate
            live.write_bytes(b"CORRUPT" + good_bytes[7:])
            live.write_bytes(good_bytes)
            return real_read(path, *a, **k)

        monkeypatch.setattr(T.pd, "read_parquet", racing_read)
        vin = T.load_verified_publication(interim)
        monkeypatch.undo()
        assert vin.parquet_sha256 == marker["parquet_sha256"]
        assert vin.generation_id == marker["generation_id"]
        assert list(vin.df["Total All"]) == list(
            combined.sort_values(T._WIDE_SORT_COLS)["Total All"])

    def test_change_during_read_not_restored_still_returns_verified_snapshot(
            self, tmp_path, monkeypatch):
        interim, combined = self._pub(tmp_path)
        live = interim / T.PHASE3_PUBLICATION_PARQUET
        real_read = T.pd.read_parquet

        def corrupting_read(path, *a, **k):
            live.write_bytes(b"not a parquet file at all")     # left corrupted
            return real_read(path, *a, **k)

        monkeypatch.setattr(T.pd, "read_parquet", corrupting_read)
        vin = T.load_verified_publication(interim)              # snapshot read: fine
        monkeypatch.undo()
        assert len(vin.df) == len(combined)
        # a fresh load now sees the corrupted live file and refuses
        with pytest.raises(T.PublicationNotVerifiedError):
            T.load_verified_publication(interim)

    def test_missing_and_tampered_marker_still_rejected(self, tmp_path):
        interim, _ = self._pub(tmp_path)
        m = interim / X.GENERATION_MARKER
        doc = json.loads(m.read_text())
        doc["combined_rows"] = 123456
        m.write_text(json.dumps(doc))
        with pytest.raises(T.PublicationNotVerifiedError):
            T.load_verified_publication(interim)
        m.unlink()
        with pytest.raises(T.PublicationNotVerifiedError):
            T.load_verified_publication(interim)


class TestP4A02PersistedLongValidation:
    """P4-A02 — mandatory bounded-memory validation of the *persisted* long
    Parquet must reject every listed fault, including faults introduced after
    serialization."""

    @pytest.fixture
    def wml(self, tmp_path, simple_combined):
        wide = T.build_analytical_wide(_vin(simple_combined, tmp_path))
        meta = T.wait_band_metadata()
        lp = tmp_path / "long.parquet"
        T.write_waiting_band_long(wide, lp, meta=meta, block_rows=3)
        return wide, meta, lp

    def test_valid_persisted_long_passes(self, wml):
        wide, meta, lp = wml
        r = T.validate_persisted_long(lp, wide, meta, batch_rows=97)
        assert r["rows"] == len(wide) * 105 == r["expected_rows"]
        assert r["value_mismatches"] == r["na_state_mismatches"] == r["identity_mismatches"] == 0

    def _expect_reject(self, wide, meta, lp, mutate):
        df = pd.read_parquet(lp)
        df = mutate(df)
        _rewrite_long(df, lp)
        with pytest.raises((T.LineageError, T.CardinalityError)):
            T.validate_persisted_long(lp, wide, meta, batch_rows=97)

    def test_repeated_band(self, wml):
        w, m, lp = wml
        self._expect_reject(w, m, lp, lambda d: d.drop(index=5).reset_index(drop=True)
                            .pipe(lambda x: pd.concat([x.iloc[:5], x.iloc[[4]], x.iloc[5:]],
                                                      ignore_index=True)))

    def test_missing_band(self, wml):
        w, m, lp = wml
        self._expect_reject(w, m, lp, lambda d: d.drop(index=10).reset_index(drop=True))

    def test_reordered_bands(self, wml):
        w, m, lp = wml
        def mut(d):
            idx = list(range(len(d)))
            idx[3], idx[7] = idx[7], idx[3]
            return d.iloc[idx].reset_index(drop=True)
        self._expect_reject(w, m, lp, mut)

    def test_wrong_band_order_value(self, wml):
        w, m, lp = wml
        self._expect_reject(w, m, lp, lambda d: d.assign(
            wait_band_order=d["wait_band_order"].mask(d.index == 4, 99).astype("Int16")))

    def test_wrong_band_label(self, wml):
        w, m, lp = wml
        self._expect_reject(w, m, lp, lambda d: d.assign(
            wait_band_label=d["wait_band_label"].mask(d.index == 4, "WRONG")))

    def test_wrong_bounds(self, wml):
        w, m, lp = wml
        self._expect_reject(w, m, lp, lambda d: d.assign(
            wait_band_lower_weeks=d["wait_band_lower_weeks"].mask(d.index == 4, 77).astype("Int16")))

    def test_swapped_cell_values(self, wml):
        w, m, lp = wml
        def mut(d):
            d = d.copy()
            a, b = d.loc[0, "pathway_count"], d.loc[1, "pathway_count"]
            d.loc[0, "pathway_count"], d.loc[1, "pathway_count"] = b, a
            return d
        self._expect_reject(w, m, lp, mut)

    def test_zero_changed_to_na(self, wml):
        w, m, lp = wml
        def mut(d):
            d = d.copy()
            i = d.index[(d["pathway_count"] == 0)][0]
            d.loc[i, "pathway_count"] = pd.NA
            return d
        self._expect_reject(w, m, lp, mut)

    def test_na_changed_to_zero(self, wml):
        w, m, lp = wml
        def mut(d):
            d = d.copy()
            i = d.index[d["pathway_count"].isna()][0]
            d.loc[i, "pathway_count"] = 0
            return d
        self._expect_reject(w, m, lp, mut)

    def test_wrong_provider_identity(self, wml):
        w, m, lp = wml
        self._expect_reject(w, m, lp, lambda d: d.assign(
            **{"Provider Org Code": d["Provider Org Code"].mask(d.index == 4, "WRONG")}))

    def test_wrong_source_sha(self, wml):
        w, m, lp = wml
        self._expect_reject(w, m, lp, lambda d: d.assign(
            source_sha256=d["source_sha256"].mask(d.index == 4, "deadbeef")))

    def test_duplicate_observation(self, wml):
        w, m, lp = wml
        self._expect_reject(w, m, lp, lambda d: pd.concat([d, d.iloc[[0]]], ignore_index=True))

    def test_extra_observation(self, wml):
        w, m, lp = wml
        def mut(d):
            extra = d.iloc[[0]].copy()
            extra["wait_band_order"] = pd.array([106], dtype="Int16")
            return pd.concat([d, extra], ignore_index=True)
        self._expect_reject(w, m, lp, mut)

    def test_wrong_schema(self, wml):
        w, m, lp = wml
        df = pd.read_parquet(lp).rename(columns={"pathway_count": "count"})
        pq.write_table(pa.Table.from_pandas(df, preserve_index=False), str(lp))
        with pytest.raises(T.LineageError):
            T.validate_persisted_long(lp, w, m)

    def test_run_phase4_rejects_post_write_corruption(self, tmp_path, monkeypatch):
        interim, combined = _publish_phase3(tmp_path, {"2026-06": [
            _row("2026-06", part="Part_2", tfc="C_100", first_band=3, total_all=3),
            _row("2026-06", part="Part_2", tfc="C_101", first_band=1, total_all=1)]})
        real_chunk = T._dense_long_chunk

        def bad_chunk(block, band_cols, meta):
            tbl = real_chunk(block, band_cols, meta)
            order = tbl.column("wait_band_order").to_pylist()
            fixed = pa.array([1] * len(order), type=pa.int16())
            return tbl.set_column(tbl.schema.get_field_index("wait_band_order"),
                                  "wait_band_order", fixed)

        monkeypatch.setattr(T, "_dense_long_chunk", bad_chunk)
        out = tmp_path / "processed"
        with pytest.raises((T.LineageError, T.CardinalityError, T.Phase4PublicationError)):
            T.run_phase4(interim_dir=interim, out_dir=out, block_rows=2)
        # nothing coherent was published
        assert T.verify_phase4_publication(out)["valid"] is False


class TestP4A02ReconcileHardened:
    """P4-A02 — the in-memory helper must no longer accept duplicates, extra
    observations or wrong identity metadata."""

    @pytest.fixture
    def wl(self, tmp_path, simple_combined):
        wide = T.build_analytical_wide(_vin(simple_combined, tmp_path))
        long = T.build_waiting_band_long(wide, block_rows=4)
        return wide, long

    def test_valid_reconciles(self, wl):
        wide, long = wl
        r = T.reconcile_long_against_wide(wide, long)
        assert r["value_mismatches"] == 0 and r["cells"] == len(wide) * 105

    def test_rejects_duplicate_observation(self, wl):
        wide, long = wl
        dup = pd.concat([long, long.iloc[[0]]], ignore_index=True)
        with pytest.raises((T.LineageError, T.CardinalityError)):
            T.reconcile_long_against_wide(wide, dup)

    def test_rejects_wrong_identity_metadata(self, wl):
        wide, long = wl
        bad = long.copy()
        bad.loc[bad.index[:5], "source_sha256"] = "WRONG"
        with pytest.raises(T.LineageError):
            T.reconcile_long_against_wide(wide, bad)

    def test_rejects_wrong_label(self, wl):
        wide, long = wl
        bad = long.copy()
        bad.loc[bad.index[0], "wait_band_label"] = "WRONG"
        with pytest.raises(T.LineageError):
            T.reconcile_long_against_wide(wide, bad)


class TestP4A03CoherentPublication:
    """P4-A03 — the Phase 4 output set is one atomic, self-verifying generation;
    a failed rerun never leaves an accepted mixed set."""

    def _run(self, tmp_path, interim, out, first_band=3, **kw):
        return T.run_phase4(interim_dir=interim, out_dir=out, block_rows=2, **kw)

    def test_publishes_and_self_verifies(self, tmp_path):
        interim, combined = _publish_phase3(tmp_path, {"2026-06": [
            _row("2026-06", part="Part_2", tfc="C_100", first_band=3, total_all=3)]})
        out = tmp_path / "processed"
        res = self._run(tmp_path, interim, out)
        assert res.ok and res.publication["valid"]
        assert (out / T.PHASE4_MANIFEST).exists()
        v = T.verify_phase4_publication(out)
        assert v["valid"] and v["phase3_generation_id"] == res.generation_id
        assert v["waiting_band_long_rows"] == v["analytical_wide_rows"] * 105

    def test_manifest_binds_phase3_and_every_output_hash(self, tmp_path):
        interim, _ = _publish_phase3(tmp_path, {"2026-06": [
            _row("2026-06", part="Part_2", tfc="C_100", first_band=3, total_all=3)]})
        out = tmp_path / "processed"
        self._run(tmp_path, interim, out)
        m = json.loads((out / T.PHASE4_MANIFEST).read_text())
        assert m["phase3_input"]["generation_id"]
        for key in ("analytical_wide", "wait_band_metadata", "waiting_band_long",
                    "report_json", "report_md"):
            e = m["outputs"][key]
            assert _sha(out / e["file"]) == e["sha256"]

    def test_tampering_one_parquet_fails_verification(self, tmp_path):
        interim, _ = _publish_phase3(tmp_path, {"2026-06": [
            _row("2026-06", part="Part_2", tfc="C_100", first_band=3, total_all=3)]})
        out = tmp_path / "processed"
        self._run(tmp_path, interim, out)
        p = out / T.ANALYTICAL_WIDE_PARQUET
        b = bytearray(p.read_bytes())
        b[-20] ^= 0xFF
        p.write_bytes(bytes(b))
        assert T.verify_phase4_publication(out)["valid"] is False

    def test_swapping_an_old_output_fails_verification(self, tmp_path):
        interim, _ = _publish_phase3(tmp_path, {"2026-06": [
            _row("2026-06", part="Part_2", tfc="C_100", first_band=3, total_all=3)]})
        out = tmp_path / "processed"
        self._run(tmp_path, interim, out)                      # generation A
        # regenerate Phase 3 with a changed value -> generation B
        (interim).rename(tmp_path / "interim_A")
        _publish_phase3(tmp_path, {"2026-06": [
            _row("2026-06", part="Part_2", tfc="C_100", first_band=99, total_all=99)]})
        self._run(tmp_path, interim, out)                      # generation B (rotates A -> *.prev)
        assert T.verify_phase4_publication(out)["valid"] is True
        # splice A's wide back in
        (out / (T.ANALYTICAL_WIDE_PARQUET + ".prev")).replace(out / T.ANALYTICAL_WIDE_PARQUET)
        assert T.verify_phase4_publication(out)["valid"] is False

    def test_failure_during_replace_leaves_detectable_invalid_then_recovers(
            self, tmp_path, monkeypatch):
        interim, _ = _publish_phase3(tmp_path, {"2026-06": [
            _row("2026-06", part="Part_2", tfc="C_100", first_band=3, total_all=3)]})
        out = tmp_path / "processed"
        self._run(tmp_path, interim, out)                      # generation A (valid)
        assert T.verify_phase4_publication(out)["valid"]

        # regenerate Phase 3 with a changed value so generation B genuinely differs
        interim.rename(tmp_path / "interim_A")
        _publish_phase3(tmp_path, {"2026-06": [
            _row("2026-06", part="Part_2", tfc="C_100", first_band=42, total_all=42)]})

        real_replace = T._os.replace
        calls = {"n": 0}

        def flaky_replace(src, dst):
            calls["n"] += 1
            if calls["n"] == 2:                                # fail mid-commit
                raise OSError("injected replace failure")
            return real_replace(src, dst)

        monkeypatch.setattr(T._os, "replace", flaky_replace)
        with pytest.raises(OSError):
            self._run(tmp_path, interim, out)                  # attempt generation B
        monkeypatch.undo()
        # consumer must NOT accept the mixed set
        assert T.verify_phase4_publication(out)["valid"] is False
        # previous valid generation is recoverable
        rr = T.restore_previous_phase4_generation(out)
        assert rr["restored"] is True
        assert T.verify_phase4_publication(out)["valid"] is True
        # a clean retry then succeeds
        res = self._run(tmp_path, interim, out)
        assert res.ok and T.verify_phase4_publication(out)["valid"] is True

    def test_transient_windows_lock_on_replace_is_retried(self, tmp_path, monkeypatch):
        interim, _ = _publish_phase3(tmp_path, {"2026-06": [
            _row("2026-06", part="Part_2", tfc="C_100", first_band=3, total_all=3)]})
        out = tmp_path / "processed"
        real_replace = T._os.replace
        state = {"n": 0}

        def flaky(src, dst):
            state["n"] += 1
            if state["n"] in (2, 3):                           # dst briefly "locked"
                raise PermissionError("[WinError 5] Access is denied")
            return real_replace(src, dst)

        monkeypatch.setattr(T._os, "replace", flaky)
        monkeypatch.setattr(T._time, "sleep", lambda *_a: None)
        res = self._run(tmp_path, interim, out)
        monkeypatch.undo()
        assert res.ok and T.verify_phase4_publication(out)["valid"] is True

    def test_persistent_permission_error_on_replace_propagates(self, tmp_path, monkeypatch):
        interim, _ = _publish_phase3(tmp_path, {"2026-06": [
            _row("2026-06", part="Part_2", tfc="C_100", first_band=3, total_all=3)]})
        out = tmp_path / "processed"
        monkeypatch.setattr(T._time, "sleep", lambda *_a: None)
        monkeypatch.setattr(T._os, "replace",
                            lambda s, d: (_ for _ in ()).throw(PermissionError("locked forever")))
        with pytest.raises(PermissionError):
            self._run(tmp_path, interim, out)
        monkeypatch.undo()

    def test_failure_before_first_replace_leaves_previous_generation_intact(
            self, tmp_path, monkeypatch):
        interim, _ = _publish_phase3(tmp_path, {"2026-06": [
            _row("2026-06", part="Part_2", tfc="C_100", first_band=3, total_all=3)]})
        out = tmp_path / "processed"
        self._run(tmp_path, interim, out)
        m_before = (out / T.PHASE4_MANIFEST).read_bytes()

        monkeypatch.setattr(T, "build_phase4_manifest",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        with pytest.raises(RuntimeError):
            self._run(tmp_path, interim, out)
        monkeypatch.undo()
        assert (out / T.PHASE4_MANIFEST).read_bytes() == m_before
        assert T.verify_phase4_publication(out)["valid"] is True


class TestP4A04DeterminismContract:
    """P4-A04 — separate logical determinism (across block sizes) from physical
    byte repeatability (fixed configuration only)."""

    def _interim(self, tmp_path):
        interim, _ = _publish_phase3(tmp_path, {
            "2026-05": [_row("2026-05", part="Part_2", tfc="C_100", first_band=4, total_all=4),
                        _row("2026-05", part="Part_2A", tfc="C_100", first_band=1, total_all=1),
                        _row("2026-05", part="Part_3", tfc="C_999", bands_blank=True, total_all=9)],
            "2026-06": [_row("2026-06", part="Part_2", tfc="C_100", first_band=2, total_all=2)]})
        return interim

    def test_physical_byte_repeatability_fixed_config(self, tmp_path):
        interim = self._interim(tmp_path)
        a, b = tmp_path / "a", tmp_path / "b"
        T.run_phase4(interim_dir=interim, out_dir=a, block_rows=3)
        T.run_phase4(interim_dir=interim, out_dir=b, block_rows=3)
        for name in (T.ANALYTICAL_WIDE_PARQUET, T.WAIT_BAND_METADATA_PARQUET,
                     T.WAITING_BAND_LONG_PARQUET):
            assert _sha(a / name) == _sha(b / name), name

    def test_logical_equality_across_block_sizes(self, tmp_path):
        interim = self._interim(tmp_path)
        outs = {}
        for bs in (1, 2, 3, 7):                                # 7 -> non-divisible final block
            o = tmp_path / f"bs{bs}"
            T.run_phase4(interim_dir=interim, out_dir=o, block_rows=bs)
            outs[bs] = o
        # wide + metadata are block-size independent -> byte identical
        for bs in (2, 3, 7):
            for name in (T.ANALYTICAL_WIDE_PARQUET, T.WAIT_BAND_METADATA_PARQUET):
                assert _sha(outs[1] / name) == _sha(outs[bs] / name), (name, bs)
        # long: logical content identical even where the file hash differs
        base = pd.read_parquet(outs[1] / T.WAITING_BAND_LONG_PARQUET)
        for bs in (2, 3, 7):
            other = pd.read_parquet(outs[bs] / T.WAITING_BAND_LONG_PARQUET)
            pd.testing.assert_frame_equal(base, other)
            assert list(other.dtypes) == list(base.dtypes)

    def test_report_deterministic_content_vs_variable_metadata(self, tmp_path):
        interim = self._interim(tmp_path)
        r1 = T.run_phase4(interim_dir=interim, out_dir=tmp_path / "r1", block_rows=2).report
        r2 = T.run_phase4(interim_dir=interim, out_dir=tmp_path / "r2", block_rows=7).report
        assert r1 != r2                                        # timestamps / durations / layout differ
        assert T.deterministic_report_view(r1) == T.deterministic_report_view(r2)

    def test_phase4_generation_id_stable_across_runs_and_block_sizes(self, tmp_path):
        interim = self._interim(tmp_path)
        ids = set()
        for i, bs in enumerate((2, 2, 3, 7)):
            res = T.run_phase4(interim_dir=interim, out_dir=tmp_path / f"g{i}", block_rows=bs)
            ids.add(res.phase4_generation_id)
        assert len(ids) == 1                                   # analytical identity, not physical hash


class TestP4A05DQSemantics:
    """P4-A05 — Part_2A counterpart semantics, structural-condition wording,
    and the enforced reporting-date resolution."""

    def _wide(self, tmp_path, rows):
        combined = _combined(tmp_path, {"2026-05": rows})
        return T.build_analytical_wide(_vin(combined, tmp_path))

    def test_missing_part2_counterpart(self, tmp_path):
        wide = self._wide(tmp_path, [
            _row("2026-05", part="Part_2", tfc="C_100", total_all=5),
            _row("2026-05", part="Part_2A", tfc="C_205", total_all=1)])   # no Part_2 C_205
        r = wide[wide["Treatment Function Code"] == "C_205"].iloc[0]
        assert bool(r["dq_part2a_no_matching_part2"]) is True
        assert bool(r["dq_part2a_gt_part2"]) is False
        assert r["Total All"] == 1

    def test_present_part2_counterpart_with_na_total_all(self, tmp_path):
        # Part_2 row exists at the key but its Total All is <NA> (Part_3-style blank)
        combined = _combined(tmp_path, {"2026-05": [
            _row("2026-05", part="Part_2", tfc="C_100", bands_blank=True, total_all=""),
            _row("2026-05", part="Part_2A", tfc="C_100", total_all=1)]})
        # sanity: the frozen conformance helper also treats this as "no usable comparator"
        conf = S.part_2a_subset_conformance(combined)
        wide = T.build_analytical_wide(_vin(combined, tmp_path))
        r = wide[wide["RTT Part Type"] == "Part_2A"].iloc[0]
        assert bool(r["dq_part2a_no_matching_part2"]) is True
        assert bool(r["dq_part2a_gt_part2"]) is False
        assert conf["n_without_matching_part_2"] == 1
        # source Part_2 Total All is preserved as <NA>, not coerced
        p2 = wide[wide["RTT Part Type"] == "Part_2"].iloc[0]
        assert pd.isna(p2["Total All"])

    def test_present_numeric_counterpart_conformant(self, tmp_path):
        wide = self._wide(tmp_path, [
            _row("2026-05", part="Part_2", tfc="C_100", total_all=5),
            _row("2026-05", part="Part_2A", tfc="C_100", total_all=2)])
        r = wide[wide["RTT Part Type"] == "Part_2A"].iloc[0]
        assert bool(r["dq_part2a_no_matching_part2"]) is False
        assert bool(r["dq_part2a_gt_part2"]) is False

    def test_numeric_violation_flagged_not_capped(self, tmp_path):
        wide = self._wide(tmp_path, [
            _row("2026-05", part="Part_2", tfc="C_100", total_all=1),
            _row("2026-05", part="Part_2A", tfc="C_100", total_all=2)])
        r = wide[wide["RTT Part Type"] == "Part_2A"].iloc[0]
        assert bool(r["dq_part2a_gt_part2"]) is True
        assert bool(r["dq_part2a_no_matching_part2"]) is False
        assert r["Total All"] == 2                              # preserved, not capped

    def test_reporting_date_dtype_enforced_and_serialized(self, tmp_path):
        interim, _ = _publish_phase3(tmp_path, {"2026-06": [
            _row("2026-06", part="Part_2", tfc="C_100", first_band=3, total_all=3)]})
        out = tmp_path / "processed"
        T.run_phase4(interim_dir=interim, out_dir=out, block_rows=2)
        wide = pd.read_parquet(out / T.ANALYTICAL_WIDE_PARQUET)
        assert str(wide["reporting_period_start_date"].dtype) == T.REPORTING_DATE_DTYPE
        schema = pq.ParquetFile(str(out / T.ANALYTICAL_WIDE_PARQUET)).schema_arrow
        field = schema.field("reporting_period_start_date")
        assert pa.types.is_timestamp(field.type) and field.type.unit == "us"
        rep = json.loads((out / T.TRANSFORM_REPORT_JSON).read_text())
        assert rep["transformation_integrity"]["reporting_period_start_date_dtype"] == T.REPORTING_DATE_DTYPE


# ========================================================================= #
# Phase 4 closure-audit residuals — P4-R01 / P4-R02 / P4-R03                  #
# ========================================================================= #

_BIG = 2 ** 53 + 1          # exceeds float64 integer precision


class TestP4R01ExactBandBounds:
    """P4-R01 — the secondary reconciler must reject missing / wrong band bounds,
    never let an unknown comparison pass via a skip-NA reduction."""

    @pytest.fixture
    def wl(self, tmp_path, simple_combined):
        wide = T.build_analytical_wide(_vin(simple_combined, tmp_path))
        long = T.build_waiting_band_long(wide, block_rows=4)
        return wide, long

    def test_valid_bounds_pass(self, wl):
        wide, long = wl
        assert T.reconcile_long_against_wide(wide, long)["value_mismatches"] == 0

    def test_open_ended_final_upper_na_passes(self, wl):
        wide, long = wl
        # the >104 band already carries NA upper in a correct build
        assert long.loc[long["wait_band_order"] == 105, "wait_band_upper_weeks"].isna().all()
        T.reconcile_long_against_wide(wide, long)               # no raise

    def test_all_lower_null_fails(self, wl):
        wide, long = wl
        bad = long.copy()
        bad["wait_band_lower_weeks"] = pd.array([pd.NA] * len(bad), dtype="Int16")
        with pytest.raises(T.LineageError):
            T.reconcile_long_against_wide(wide, bad)

    def test_missing_closed_band_upper_fails(self, wl):
        wide, long = wl
        bad = long.copy()
        i = bad.index[bad["wait_band_order"] == 3][0]
        bad.loc[i, "wait_band_upper_weeks"] = pd.NA
        with pytest.raises(T.LineageError):
            T.reconcile_long_against_wide(wide, bad)

    def test_numeric_upper_on_open_band_fails(self, wl):
        wide, long = wl
        bad = long.copy()
        bad.loc[bad["wait_band_order"] == 105, "wait_band_upper_weeks"] = pd.array(
            [105] * int((bad["wait_band_order"] == 105).sum()), dtype="Int16")
        with pytest.raises(T.LineageError):
            T.reconcile_long_against_wide(wide, bad)

    def test_wrong_numeric_lower_fails(self, wl):
        wide, long = wl
        bad = long.copy()
        i = bad.index[bad["wait_band_order"] == 4][0]
        bad.loc[i, "wait_band_lower_weeks"] = 77
        with pytest.raises(T.LineageError):
            T.reconcile_long_against_wide(wide, bad)

    def test_wrong_numeric_upper_fails(self, wl):
        wide, long = wl
        bad = long.copy()
        i = bad.index[bad["wait_band_order"] == 4][0]
        bad.loc[i, "wait_band_upper_weeks"] = 88
        with pytest.raises(T.LineageError):
            T.reconcile_long_against_wide(wide, bad)

    def test_existing_duplicate_and_identity_rejections_retained(self, wl):
        wide, long = wl
        with pytest.raises((T.LineageError, T.CardinalityError)):
            T.reconcile_long_against_wide(wide, pd.concat([long, long.iloc[[0]]], ignore_index=True))
        bad = long.copy()
        bad.loc[bad.index[0], "wait_band_label"] = "WRONG"
        with pytest.raises(T.LineageError):
            T.reconcile_long_against_wide(wide, bad)


def _big_value_combined(tmp_path: Path, values: list[int]) -> pd.DataFrame:
    """A one-month combined frame whose first band cell carries each of `values`
    (one row per value, distinct TFC), the rest zeros; blank -> <NA>."""
    tfcs = ["C_100", "C_101", "C_102", "C_110", "C_120", "C_130", "C_140", "C_150"]
    rows = []
    for v, tfc in zip(values, tfcs):
        first = "" if v is None else str(v)
        bands = [first] + ["0"] * 104
        rows.append(_row("2026-06", part="Part_2", tfc=tfc, bands=bands,
                         total_all=(1 if v is None else max(v, 1))))
    return _combined(tmp_path, {"2026-06": rows})


class TestP4R02IntegerExactPersistedValidation:
    """P4-R02 — validate_persisted_long compares pathway_count as exact int64,
    never through float64 (no 2**53 rounding)."""

    def _wml(self, tmp_path, values):
        combined = _big_value_combined(tmp_path, values)
        wide = T.build_analytical_wide(_vin(combined, tmp_path))
        meta = T.wait_band_metadata()
        lp = tmp_path / "long.parquet"
        T.write_waiting_band_long(wide, lp, meta=meta, block_rows=1)
        return wide, meta, lp

    def test_boundary_values_unchanged_validate(self, tmp_path):
        wide, meta, lp = self._wml(tmp_path, [0, 27, None, 2 ** 53, _BIG, 2 ** 53 + 2])
        r = T.validate_persisted_long(lp, wide, meta, batch_rows=17)
        assert r["value_mismatches"] == 0 and r["na_state_mismatches"] == 0
        assert r["identity_mismatches"] == 0
        assert r["source_na_cells"] == 1          # the one blank first-band cell (value None)
        assert r["positive_cells"] == 4           # 27, 2**53, 2**53+1, 2**53+2 first bands

    def test_writer_preserves_big_integer_and_schema(self, tmp_path):
        wide, meta, lp = self._wml(tmp_path, [_BIG, 7])
        long = pd.read_parquet(lp)
        assert int(long.loc[long["pathway_count"] == _BIG, "pathway_count"].iloc[0]) == _BIG
        assert str(pq.ParquetFile(str(lp)).schema_arrow.field("pathway_count").type) == "int64"

    def _mutate_persisted(self, lp, frm, to):
        long = pd.read_parquet(lp)
        i = long.index[long["pathway_count"] == frm][0]
        long.loc[i, "pathway_count"] = to
        _rewrite_long(long, lp)

    def test_big_minus_one_on_disk_is_rejected(self, tmp_path):
        wide, meta, lp = self._wml(tmp_path, [_BIG, 7])
        self._mutate_persisted(lp, _BIG, 2 ** 53)              # 2**53+1 -> 2**53
        with pytest.raises(T.LineageError):
            T.validate_persisted_long(lp, wide, meta, batch_rows=17)

    def test_big_plus_one_on_disk_is_rejected(self, tmp_path):
        wide, meta, lp = self._wml(tmp_path, [_BIG, 7])
        self._mutate_persisted(lp, _BIG, 2 ** 53 + 2)          # 2**53+1 -> 2**53+2
        with pytest.raises(T.LineageError):
            T.validate_persisted_long(lp, wide, meta, batch_rows=17)

    def test_zero_to_na_and_na_to_zero_still_rejected(self, tmp_path):
        wide, meta, lp = self._wml(tmp_path, [0, None, 5])
        long = pd.read_parquet(lp)
        long.loc[long.index[(long["pathway_count"] == 0)][0], "pathway_count"] = pd.NA
        _rewrite_long(long, lp)
        with pytest.raises(T.LineageError):
            T.validate_persisted_long(lp, wide, meta, batch_rows=17)
        wide, meta, lp = self._wml(tmp_path, [0, None, 5])
        long = pd.read_parquet(lp)
        long.loc[long.index[long["pathway_count"].isna()][0], "pathway_count"] = 0
        _rewrite_long(long, lp)
        with pytest.raises(T.LineageError):
            T.validate_persisted_long(lp, wide, meta, batch_rows=17)

    def test_mixed_batch_large_ints_and_nulls(self, tmp_path):
        wide, meta, lp = self._wml(tmp_path, [_BIG, None, 2 ** 53, None, 9])
        # a single batch spanning several parents (large ints beside NAs)
        r = T.validate_persisted_long(lp, wide, meta, batch_rows=1_000_000)
        assert r["value_mismatches"] == 0 and r["batches"] == 1


class TestP4R03ManifestContractEnforced:
    """P4-R03 — verify_phase4_publication enforces the complete publication
    contract; every Codex counterexample returns structured valid=False."""

    @pytest.fixture
    def published(self, tmp_path):
        interim, _ = _publish_phase3(tmp_path, {"2026-06": [
            _row("2026-06", part="Part_2", tfc="C_100", first_band=3, total_all=3),
            _row("2026-06", part="Part_2", tfc="C_101", first_band=1, total_all=1)]})
        out = tmp_path / "processed"
        res = T.run_phase4(interim_dir=interim, out_dir=out, block_rows=1)
        assert res.ok
        return interim, out

    def _manifest(self, out):
        return json.loads((out / T.PHASE4_MANIFEST).read_text())

    def _write_manifest(self, out, m):
        (out / T.PHASE4_MANIFEST).write_text(json.dumps(m, indent=2))

    def _mutate(self, out, fn):
        m = self._manifest(out)
        fn(m)
        self._write_manifest(out, m)
        r = T.verify_phase4_publication(out)
        assert isinstance(r, dict) and r.get("valid") is False, r
        assert "reason" in r and r["reason"]

    def test_intact_publication_passes(self, published):
        _, out = published
        r = T.verify_phase4_publication(out)
        assert r["valid"] is True
        assert r["phase4_generation_id"] and r["phase3_generation_id"]

    def test_report_json_entry_and_file_removed(self, published):
        _, out = published
        (out / T.TRANSFORM_REPORT_JSON).unlink()
        self._mutate(out, lambda m: m["outputs"].pop("report_json"))

    def test_report_md_entry_and_file_removed(self, published):
        _, out = published
        (out / T.TRANSFORM_REPORT_MD).unlink()
        self._mutate(out, lambda m: m["outputs"].pop("report_md"))

    def test_wait_band_metadata_entry_and_file_removed(self, published):
        _, out = published
        (out / T.WAIT_BAND_METADATA_PARQUET).unlink()
        self._mutate(out, lambda m: m["outputs"].pop("wait_band_metadata"))

    def test_wide_entry_removed_is_structured_not_keyerror(self, published):
        _, out = published
        self._mutate(out, lambda m: m["outputs"].pop("analytical_wide"))

    def test_long_entry_removed(self, published):
        _, out = published
        self._mutate(out, lambda m: m["outputs"].pop("waiting_band_long"))

    def test_false_phase4_generation_id(self, published):
        _, out = published
        self._mutate(out, lambda m: m.__setitem__("phase4_generation_id", "a" * 64))

    def test_false_phase3_generation_id(self, published):
        _, out = published
        self._mutate(out, lambda m: m["phase3_input"].__setitem__("generation_id", "b" * 64))

    def test_false_consumed_phase3_hash(self, published):
        _, out = published
        self._mutate(out, lambda m: m["phase3_input"].__setitem__("consumed_parquet_sha256", "c" * 64))

    def test_false_phase3_combined_rows(self, published):
        _, out = published
        self._mutate(out, lambda m: m["phase3_input"].__setitem__("combined_rows", 999))

    def test_false_parquet_schema_claim(self, published):
        _, out = published
        self._mutate(out, lambda m: m["outputs"]["analytical_wide"].__setitem__("schema", ["WRONG"]))

    def test_false_parquet_column_count(self, published):
        _, out = published
        self._mutate(out, lambda m: m["outputs"]["analytical_wide"].__setitem__("columns", 999))

    def test_false_parquet_column_names(self, published):
        _, out = published
        self._mutate(out, lambda m: m["outputs"]["waiting_band_long"].__setitem__(
            "column_names", ["x"] * 14))

    def test_false_parquet_byte_size(self, published):
        _, out = published
        self._mutate(out, lambda m: m["outputs"]["analytical_wide"].__setitem__("bytes", 1))

    def test_false_parquet_row_count(self, published):
        _, out = published
        self._mutate(out, lambda m: m["outputs"]["analytical_wide"].__setitem__("rows", 999))

    def test_wait_band_metadata_rows_not_105(self, published):
        _, out = published
        self._mutate(out, lambda m: m.__setitem__("wait_band_metadata_rows", 104))

    def test_bands_per_parent_not_105(self, published):
        _, out = published
        self._mutate(out, lambda m: m.__setitem__("bands_per_parent", 1))

    def test_cardinality_assertion_false(self, published):
        _, out = published
        self._mutate(out, lambda m: m.__setitem__("long_equals_wide_times_bands", False))

    def test_long_rows_not_wide_times_105(self, published):
        _, out = published
        self._mutate(out, lambda m: m.__setitem__(
            "waiting_band_long_rows", m["analytical_wide_rows"] * 105 + 1))

    def test_report_json_hash_mismatch(self, published):
        _, out = published
        self._mutate(out, lambda m: m["outputs"]["report_json"].__setitem__("sha256", "d" * 64))

    def test_report_json_identity_disagrees(self, published):
        _, out = published
        rep = json.loads((out / T.TRANSFORM_REPORT_JSON).read_text())
        rep["input_integrity"]["phase3_generation_id"] = "z" * 64
        (out / T.TRANSFORM_REPORT_JSON).write_text(json.dumps(rep, indent=2))
        m = self._manifest(out)
        m["outputs"]["report_json"]["sha256"] = _sha(out / T.TRANSFORM_REPORT_JSON)
        m["outputs"]["report_json"]["bytes"] = (out / T.TRANSFORM_REPORT_JSON).stat().st_size
        self._write_manifest(out, m)
        r = T.verify_phase4_publication(out)
        assert r["valid"] is False and "disagrees" in r["reason"]

    def test_tampered_individual_parquet(self, published):
        _, out = published
        p = out / T.WAIT_BAND_METADATA_PARQUET
        b = bytearray(p.read_bytes()); b[-16] ^= 0xFF; p.write_bytes(bytes(b))
        r = T.verify_phase4_publication(out)
        assert r["valid"] is False

    def test_swapped_old_output(self, tmp_path):
        interim, _ = _publish_phase3(tmp_path, {"2026-06": [
            _row("2026-06", part="Part_2", tfc="C_100", first_band=3, total_all=3)]})
        out = tmp_path / "processed"
        T.run_phase4(interim_dir=interim, out_dir=out, block_rows=1)     # gen A
        interim.rename(tmp_path / "interim_A")
        _publish_phase3(tmp_path, {"2026-06": [
            _row("2026-06", part="Part_2", tfc="C_100", first_band=9, total_all=9)]})
        T.run_phase4(interim_dir=interim, out_dir=out, block_rows=1)     # gen B (rotates A->*.prev)
        assert T.verify_phase4_publication(out)["valid"] is True
        (out / (T.ANALYTICAL_WIDE_PARQUET + ".prev")).replace(out / T.ANALYTICAL_WIDE_PARQUET)
        assert T.verify_phase4_publication(out)["valid"] is False

    def test_malformed_output_entry(self, published):
        _, out = published
        self._mutate(out, lambda m: m["outputs"].__setitem__("analytical_wide", "not-an-object"))

    def test_redirected_noncanonical_filename(self, published):
        _, out = published
        self._mutate(out, lambda m: m["outputs"]["report_md"].__setitem__("file", "../evil.md"))

    def test_extra_output_key(self, published):
        _, out = published
        self._mutate(out, lambda m: m["outputs"].__setitem__(
            "bonus", {"file": "bonus.txt", "sha256": "e" * 64, "bytes": 1}))

    def test_phase_field_wrong(self, published):
        _, out = published
        self._mutate(out, lambda m: m.__setitem__("phase", 5))

    def test_generation_id_recompute_matches_shared_function(self, published):
        _, out = published
        m = self._manifest(out)
        recomputed = T.compute_phase4_generation_id(
            phase3_generation_id=m["phase3_input"]["generation_id"],
            phase3_consumed_parquet_sha256=m["phase3_input"]["consumed_parquet_sha256"],
            analytical_wide_sha256=_sha(out / T.ANALYTICAL_WIDE_PARQUET),
            wait_band_metadata_sha256=_sha(out / T.WAIT_BAND_METADATA_PARQUET),
            analytical_wide_rows=m["analytical_wide_rows"],
            waiting_band_long_rows=m["waiting_band_long_rows"])
        assert recomputed == m["phase4_generation_id"]

    def test_fixed_and_varied_block_sizes_and_backup_restore_still_pass(self, tmp_path):
        interim, _ = _publish_phase3(tmp_path, {
            "2026-05": [_row("2026-05", part="Part_2", tfc="C_100", first_band=4, total_all=4),
                        _row("2026-05", part="Part_3", tfc="C_999", bands_blank=True, total_all=9)],
            "2026-06": [_row("2026-06", part="Part_2", tfc="C_100", first_band=2, total_all=2)]})
        a = T.run_phase4(interim_dir=interim, out_dir=tmp_path / "a", block_rows=2)
        b = T.run_phase4(interim_dir=interim, out_dir=tmp_path / "b", block_rows=7)
        assert T.verify_phase4_publication(tmp_path / "a")["valid"] is True
        assert T.verify_phase4_publication(tmp_path / "b")["valid"] is True
        assert a.phase4_generation_id == b.phase4_generation_id
        # rerun into a to create a *.prev, then restore
        T.run_phase4(interim_dir=interim, out_dir=tmp_path / "a", block_rows=2)
        rr = T.restore_previous_phase4_generation(tmp_path / "a")
        assert rr["restored"] is True
        assert T.verify_phase4_publication(tmp_path / "a")["valid"] is True

    def test_malformed_current_manifest_not_eligible_for_backup_rotation(self, tmp_path):
        interim, _ = _publish_phase3(tmp_path, {"2026-06": [
            _row("2026-06", part="Part_2", tfc="C_100", first_band=3, total_all=3)]})
        out = tmp_path / "processed"
        T.run_phase4(interim_dir=interim, out_dir=out, block_rows=1)     # gen A (valid)
        # corrupt the current manifest so it no longer verifies
        m = self._manifest(out); m["bands_per_parent"] = 999
        self._write_manifest(out, m)
        assert T.verify_phase4_publication(out)["valid"] is False
        # a new run must NOT rotate the malformed current gen into *.prev
        interim.rename(tmp_path / "interim_A")
        _publish_phase3(tmp_path, {"2026-06": [
            _row("2026-06", part="Part_2", tfc="C_100", first_band=8, total_all=8)]})
        T.run_phase4(interim_dir=interim, out_dir=out, block_rows=1)     # gen B
        assert T.verify_phase4_publication(out)["valid"] is True
        assert not (out / (T.PHASE4_MANIFEST + ".prev")).exists()
