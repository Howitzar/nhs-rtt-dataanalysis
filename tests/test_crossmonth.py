"""Tests for :mod:`nhs_rtt.crossmonth` (Phase 3 — cross-month diagnostics,
deterministic combination, CSV -> Parquet publication).

Synthetic only. Small real ``load_rtt_csv`` frames are used so provenance
columns, dtypes and ``<NA>`` missingness are exercised end to end.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from nhs_rtt import crossmonth as X
from nhs_rtt import ingest as I
from nhs_rtt import semantics as S

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


def _row(period, provider="RAA", pname="PROV ALPHA", comm="00A", cname="COMM ONE",
         part="Part_2", tfc="C_100", tfn="General Surgery Service",
         first_band=1, total_all=1, total="", unknown="",
         pparent="QAA", pparent_name="PARENT A",
         cparent="QAA", cparent_name="PARENT A"):
    bands = [str(first_band)] + ["0"] * 104
    return [period, pparent, pparent_name, provider, pname,
            cparent, cparent_name, comm, cname, part, "Incomplete Pathways",
            tfc, tfn, *bands, str(total), str(unknown), str(total_all)]


def _write(path: Path, rows) -> Path:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        w.writerows(rows)
    return path


def _payload(tmp_path: Path, month: str, rows, name=None) -> X.MonthPayload:
    period = {"2026-04": "RTT-April-2026", "2026-05": "RTT-May-2026",
              "2026-06": "RTT-June-2026"}[month]
    rows = [r if r[0] else [period] + r[1:] for r in rows]
    name = name or f"rtt_{month.replace('-', '_')}.csv"
    p = _write(tmp_path / name, rows)
    df = S.load_rtt_csv(p)
    return X.MonthPayload(reporting_month=month, source_file=name,
                          source_sha256=I.sha256_file(p), df=df)


def _rows(period, specs):
    return [_row(period, **s) for s in specs]


# ========================================================================= #
class TestCombine:

    def test_row_conservation_and_provenance_columns(self, tmp_path: Path):
        p4 = _payload(tmp_path, "2026-04", _rows("RTT-April-2026", [
            {"tfc": "C_100"}, {"tfc": "C_101"}]))
        p6 = _payload(tmp_path, "2026-06", _rows("RTT-June-2026", [
            {"tfc": "C_100"}, {"tfc": "C_101"}, {"tfc": "C_102"}]))
        combined = X.combine_months([p6, p4])            # deliberately out of order

        assert len(combined) == 5 == len(p4.df) + len(p6.df)
        assert list(combined.columns[-4:]) == X.PROVENANCE_COLS
        assert str(combined["source_row_index"].dtype) == "Int64"
        # 0-based parsed data-row position, resets per month, ascending months
        assert combined["reporting_month"].tolist() == ["2026-04"] * 2 + ["2026-06"] * 3
        assert combined["source_row_index"].tolist() == [0, 1, 0, 1, 2]
        assert set(combined["source_sha256"]) == {p4.source_sha256, p6.source_sha256}

    def test_source_wide_structure_and_values_preserved(self, tmp_path: Path):
        p6 = _payload(tmp_path, "2026-06", _rows("RTT-June-2026", [
            {"tfc": "C_100", "first_band": 7, "total_all": 7},
            {"tfc": "C_999", "tfn": "Total", "first_band": 7, "total_all": 7}]))
        combined = X.combine_months([p6])
        assert combined.shape[1] == len(HEADER) + 4            # nothing reshaped
        assert combined.loc[0, "Gt 00 To 01 Weeks SUM 1"] == 7
        assert combined.loc[0, "Total All"] == 7
        # a blank band cell stays <NA>, not 0
        assert pd.isna(combined.loc[0, "Gt 05 To 06 Weeks SUM 1"]) is False  # it's 0
        blankp = _payload(tmp_path, "2026-05", [[
            "RTT-May-2026", "QAA", "PARENT A", "RAA", "PROV", "QAA", "PARENT A",
            "00A", "C", "Part_3", "New RTT Periods - All Patients", "C_999", "Total",
            *([""] * 105), "", "", "9"]])
        c2 = X.combine_months([blankp])
        assert bool(c2[_BANDS].isna().all(axis=1).iloc[0]) is True

    def test_combined_key_completeness_and_uniqueness_asserted(self, tmp_path: Path):
        # same key in two months that (wrongly) share a Period -> duplicate key
        dup_rows = _rows("RTT-June-2026", [{"tfc": "C_100"}])
        a = _payload(tmp_path, "2026-06", dup_rows, name="rtt_2026_06.csv")
        b = _payload(tmp_path, "2026-06", dup_rows, name="rtt_2026_06_b.csv")
        b.reporting_month = "2026-06"
        with pytest.raises(X.CombinedKeyError):
            X.combine_months([a, b])

    def test_combine_rejects_missing_key_column(self, tmp_path: Path):
        p = _payload(tmp_path, "2026-06", _rows("RTT-June-2026", [{"tfc": "C_100"}]))
        p.df = p.df.drop(columns=["Treatment Function Code"])
        with pytest.raises(X.CombinedKeyError, match="absent"):
            X.combine_months([p])

    def test_deterministic_under_payload_shuffle(self, tmp_path: Path):
        ps = [
            _payload(tmp_path, "2026-04", _rows("RTT-April-2026", [{"tfc": "C_100"}, {"tfc": "C_101"}])),
            _payload(tmp_path, "2026-05", _rows("RTT-May-2026", [{"tfc": "C_100"}])),
            _payload(tmp_path, "2026-06", _rows("RTT-June-2026", [{"tfc": "C_100"}, {"tfc": "C_102"}])),
        ]
        base = X.combine_months(ps)
        for order in ([ps[2], ps[0], ps[1]], list(reversed(ps)), [ps[1], ps[2], ps[0]]):
            out = X.combine_months(order)
            pd.testing.assert_frame_equal(out, base)


class TestDiagnostics:

    def _frames(self, tmp_path: Path):
        f5 = S.load_rtt_csv(_write(tmp_path / "m5.csv", [
            _row("RTT-May-2026", provider="RAA", pname="ALPHA", tfc="C_100"),
            _row("RTT-May-2026", provider="RAB", pname="BETA", tfc="C_101"),
        ]))
        f6 = S.load_rtt_csv(_write(tmp_path / "m6.csv", [
            _row("RTT-June-2026", provider="RAA", pname="ALPHA RENAMED", tfc="C_100"),
            _row("RTT-June-2026", provider="RZZ", pname="ZETA", tfc="C_101"),
        ]))
        return {"2026-05": f5, "2026-06": f6}

    def test_code_name_change_detected(self, tmp_path: Path):
        m = X.mapping_diagnostics(self._frames(tmp_path))
        chg = m["code_name_changes"]
        row = chg[(chg["dimension"] == "provider") & (chg["code"] == "RAA")].iloc[0]
        assert row["n_distinct_names"] == 2
        assert "ALPHA" in row["names_by_month"] and "ALPHA RENAMED" in row["names_by_month"]

    def test_membership_change_detected(self, tmp_path: Path):
        m = X.mapping_diagnostics(self._frames(tmp_path))
        mc = m["membership_changes"]
        row = mc[(mc["dimension"] == "provider") & (mc["from_month"] == "2026-05")].iloc[0]
        assert "RZZ" in row["appeared"] and "RAB" in row["disappeared"]

    def test_name_code_collision_within_month(self, tmp_path: Path):
        f = S.load_rtt_csv(_write(tmp_path / "m.csv", [
            _row("RTT-June-2026", provider="NT447", pname="DUCHY HOSPITAL", tfc="C_100"),
            _row("RTT-June-2026", provider="NVC04", pname="DUCHY HOSPITAL", tfc="C_101"),
        ]))
        col = X.mapping_diagnostics({"2026-06": f})["name_code_collisions"]
        row = col[col["name"] == "DUCHY HOSPITAL"].iloc[0]
        assert row["n_distinct_codes"] == 2 and row["scope"] == "within_month"

    def test_part2a_subset_preserved_not_capped(self, tmp_path: Path):
        f = S.load_rtt_csv(_write(tmp_path / "m.csv", [
            _row("RTT-June-2026", part="Part_2", tfc="C_100", total_all=1),
            _row("RTT-June-2026", part="Part_2A", tfc="C_100", total_all=2),
        ]))
        d = X.part2a_subset_diagnostics({"2026-06": f})
        assert int(d.loc[0, "n_violations"]) == 1
        assert "C_100(2A=2>2=1)" in d.loc[0, "violation_keys"]
        # source values untouched
        assert f[f["RTT Part Type"] == "Part_2A"]["Total All"].iloc[0] == 2
        assert f[f["RTT Part Type"] == "Part_2"]["Total All"].iloc[0] == 1

    def test_coverage_diagnostics_shape(self, tmp_path: Path):
        cov = X.coverage_diagnostics(self._frames(tmp_path))
        assert list(cov["reporting_month"]) == ["2026-05", "2026-06"]
        assert {"n_rows", "rows_Part_2", "pct_Total_blank"} <= set(cov.columns)

    def test_empty_diagnostic_frames_have_columns(self, tmp_path: Path):
        f = S.load_rtt_csv(_write(tmp_path / "m.csv", [_row("RTT-June-2026", tfc="C_100")]))
        m = X.mapping_diagnostics({"2026-06": f})
        assert list(m["code_name_changes"].columns) and len(m["code_name_changes"]) == 0


class TestParquetBoundary:

    def test_write_roundtrip_and_missingness(self, tmp_path: Path):
        blank = ["RTT-June-2026", "QAA", "PARENT A", "RAA", "PROV", "QAA",
                 "PARENT A", "00A", "C", "Part_3", "New RTT Periods - All Patients",
                 "C_999", "Total", *([""] * 105), "", "", "9"]
        normal = _row("RTT-June-2026", tfc="C_100", first_band=3, total_all=3)
        p = _payload(tmp_path, "2026-06", [[""] + normal[1:], [""] + blank[1:]])
        combined = X.combine_months([p])
        res = X.write_combined_parquet(combined, tmp_path / "out", payloads=[p])

        rc = X.roundtrip_check(res["parquet_path"], combined)
        assert rc["ok"], rc["problems"]
        back = pd.read_parquet(res["parquet_path"])
        assert bool(back[_BANDS].isna().all(axis=1).iloc[1]) is True     # Part_3 row
        assert back.loc[0, "Gt 00 To 01 Weeks SUM 1"] == 3
        assert Path(res["sidecar_path"]).exists()

    def test_sidecar_deterministic_view_excludes_run_block(self, tmp_path: Path):
        p = _payload(tmp_path, "2026-06", _rows("RTT-June-2026", [{"tfc": "C_100"}]))
        combined = X.combine_months([p])
        res = X.write_combined_parquet(combined, tmp_path / "out", payloads=[p])
        manifest = res["manifest"]
        assert "run" in manifest and "generated_utc" in manifest["run"]
        view = X.deterministic_manifest_view(res["sidecar_path"])
        assert "run" not in view
        assert view["deterministic"]["combined_rows"] == len(combined)

    def test_deterministic_manifest_view_on_dict(self):
        d = {"deterministic": {"x": 1}, "run": {"generated_utc": "now"}}
        assert X.deterministic_manifest_view(d) == {"deterministic": {"x": 1}}


class TestRunPhase3:

    def _make_raw(self, tmp_path: Path, files: dict[str, list]):
        raw = tmp_path / "raw"
        raw.mkdir()
        entries = []
        for name, rows in files.items():
            _write(raw / name, rows)
            entries.append({
                "reporting_period": I.parse_production_filename(name),
                "file": name, "sha256": I.sha256_file(raw / name), "selected": True})
        reg = tmp_path / "manifest.json"
        reg.write_text(json.dumps({"sources": entries}), encoding="utf-8")
        return raw, reg

    def test_all_months_accepted_combines_and_publishes(self, tmp_path: Path):
        raw, reg = self._make_raw(tmp_path, {
            "rtt_2026_05.csv": _rows("RTT-May-2026", [{"tfc": "C_100"}, {"tfc": "C_101"}]),
            "rtt_2026_06.csv": _rows("RTT-June-2026", [{"tfc": "C_100"}]),
        })
        res = X.run_phase3(raw_dir=raw, registry_path=reg,
                           out_dir=tmp_path / "interim", write_parquet=True)
        assert res.ok is True
        assert res.combined_rows == 3 and res.combined_key_unique is True
        assert res.roundtrip["ok"] is True
        assert [p.reporting_month for p in res.payloads] == ["2026-05", "2026-06"]

    def test_rejected_month_blocks_combination(self, tmp_path: Path):
        bad = _rows("RTT-June-2026", [{"tfc": "C_100"}])
        bad[0][0] = "RTT-May-2026"                       # filename/Period mismatch
        raw, reg = self._make_raw(tmp_path, {
            "rtt_2026_05.csv": _rows("RTT-May-2026", [{"tfc": "C_100"}]),
            "rtt_2026_06.csv": bad,
        })
        res = X.run_phase3(raw_dir=raw, registry_path=reg,
                           out_dir=tmp_path / "interim", write_parquet=True)
        assert res.ok is False
        assert res.acceptance["2026-06"].accepted is False
        assert res.combined_rows is None                 # nothing combined
        assert res.missing_intended == ["2026-06"]
        assert any("intended-source completeness" in n for n in res.notes)

    def test_malformed_candidate_surfaced_not_ingested(self, tmp_path: Path):
        raw, reg = self._make_raw(tmp_path, {
            "rtt_2026_06.csv": _rows("RTT-June-2026", [{"tfc": "C_100"}])})
        (raw / "rtt_2026_6.csv").write_text("junk", encoding="utf-8")
        res = X.run_phase3(raw_dir=raw, registry_path=reg,
                           out_dir=tmp_path / "interim", write_parquet=False)
        assert "rtt_2026_6.csv" in res.discovery.malformed_candidates
        assert any("malformed" in n for n in res.notes)
