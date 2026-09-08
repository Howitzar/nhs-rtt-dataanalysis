"""Tests for :mod:`nhs_rtt.ingest` (Phase 3 — deterministic discovery,
SHA-256 / registry provenance, Period contract, per-month acceptance).

Synthetic only — no test reads ``data/raw/``. Mirrors
``tests/test_semantics.py``: a realistic 105-band header is built from
``semantics.expected_week_band_names()`` so the frozen production gate runs for
real.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from nhs_rtt import ingest as I
from nhs_rtt import semantics as S

_LABELS = [
    "Period", "Provider Org Code", "Provider Org Name",
    "Commissioner Org Code", "Commissioner Org Name",
    "RTT Part Type", "RTT Part Description",
    "Treatment Function Code", "Treatment Function Name",
]
_BANDS = S.expected_week_band_names()
_TAIL = ["Total", "Patients with unknown clock start date", "Total All"]
HEADER = _LABELS + _BANDS + _TAIL
_HEX = "0" * 64


def _row(period="RTT-June-2026", provider="RAA", comm="00A", part="Part_2",
         tfc="C_100", tfn="General Surgery Service", first_band=1, total_all=1,
         total="", unknown=""):
    bands = [str(first_band)] + ["0"] * 104
    return [period, provider, "PROV A", comm, "COMM A", part,
            "Incomplete Pathways", tfc, tfn, *bands,
            str(total), str(unknown), str(total_all)]


def _write(path: Path, rows, header=HEADER) -> Path:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return path


def _month_file(tmp_path: Path, name="rtt_2026_06.csv", period="RTT-June-2026",
                rows=None) -> Path:
    rows = rows or [_row(period=period, tfc="C_100", total_all=1),
                    _row(period=period, tfc="C_101", total_all=1)]
    return _write(tmp_path / name, rows)


def _registry(tmp_path: Path, entries: list[dict], name="manifest.json") -> I.SourceRegistry:
    p = tmp_path / name
    p.write_text(json.dumps({"sources": entries}), encoding="utf-8")
    return I.SourceRegistry.load(p)


# ========================================================================= #
class TestFilenameContract:

    @pytest.mark.parametrize("name,expected", [
        ("rtt_2026_04.csv", "2026-04"),
        ("rtt_2000_12.csv", "2000-12"),
    ])
    def test_valid(self, name, expected):
        assert I.parse_production_filename(name) == expected

    @pytest.mark.parametrize("name", [
        "rtt_2026_4.csv", "rtt_2026_13.csv", "rtt_2026_00.csv",
        "RTT_2026_04.CSV", "rtt-2026-04.csv", "rtt_2026_04.csv.bak",
        "rtt_2026_04.txt", "weekly_2026_04.csv", "rtt_apr_2026.csv",
    ])
    def test_rejected(self, name):
        with pytest.raises(ValueError):
            I.parse_production_filename(name)


class TestPeriodContract:

    @pytest.mark.parametrize("value,expected", [
        ("RTT-April-2026", "2026-04"),
        ("RTT-june-2026", "2026-06"),
        ("  RTT-December-2025  ", "2025-12"),
    ])
    def test_valid(self, value, expected):
        assert I.parse_period_value(value) == expected

    @pytest.mark.parametrize("value", [
        "", "   ", None, "June 2026", "RTT-2026-06", "RTT-Smarch-2026",
        "RTT-April-26", "April-2026",
    ])
    def test_rejected(self, value):
        with pytest.raises(ValueError):
            I.parse_period_value(value)


class TestHashAndCounting:

    def test_sha256_stable_and_content_sensitive(self, tmp_path: Path):
        a = _month_file(tmp_path, "rtt_2026_06.csv")
        d1 = I.sha256_file(a)
        d2 = I.sha256_file(a)
        assert d1 == d2 and len(d1) == 64
        b = _write(tmp_path / "rtt_2026_05.csv",
                   [_row(period="RTT-May-2026", tfc="C_100", total_all=2)])
        assert I.sha256_file(b) != d1

    def test_count_data_rows_is_csv_aware_not_line_count(self, tmp_path: Path):
        # a quoted embedded newline: 3 physical lines, 2 CSV data records
        r0 = _row(tfc="C_100", total_all=1)
        r1 = _row(tfc="C_101", total_all=1)
        r1[2] = "PROV\nWITH NEWLINE"
        p = _write(tmp_path / "rtt_2026_06.csv", [r0, r1])
        assert I.count_data_rows(p) == 2
        assert len(S.load_rtt_csv(p)) == 2          # agrees with pandas

    def test_distinct_period_values(self, tmp_path: Path):
        p = _write(tmp_path / "rtt_2026_06.csv", [
            _row(period="RTT-June-2026"), _row(period="RTT-June-2026", tfc="C_101")])
        assert I.distinct_period_values(p) == ["RTT-June-2026"]


class TestDiscovery:

    def test_valid_malformed_and_unrelated_are_separated(self, tmp_path: Path):
        for n in ("rtt_2026_04.csv", "rtt_2026_05.csv"):
            _month_file(tmp_path, n, period="RTT-April-2026")
        for n in ("rtt_2026_4.csv", "RTT_2026_06.CSV", "rtt_2026_13.csv"):
            (tmp_path / n).write_text("x", encoding="utf-8")
        for n in ("notes.txt", "summary.csv", "readme.md"):
            (tmp_path / n).write_text("x", encoding="utf-8")

        d = I.discover_sources(tmp_path)
        assert d.production_files == ["rtt_2026_04.csv", "rtt_2026_05.csv"]
        assert d.malformed_candidates == sorted(
            ["rtt_2026_4.csv", "RTT_2026_06.CSV", "rtt_2026_13.csv"])
        assert "notes.txt" in d.ignored and "summary.csv" in d.ignored
        assert [m.reporting_month for m in d.months] == ["2026-04", "2026-05"]

    def test_order_is_deterministic_and_independent_of_creation_order(self, tmp_path: Path):
        names = ["rtt_2026_06.csv", "rtt_2026_04.csv", "rtt_2026_05.csv"]
        for n in names:
            (tmp_path / n).write_text("x", encoding="utf-8")
        d1 = I.discover_sources(tmp_path)
        # recreate in the opposite order in a second dir
        other = tmp_path / "other"
        other.mkdir()
        for n in reversed(names):
            (other / n).write_text("x", encoding="utf-8")
        d2 = I.discover_sources(other)
        assert d1.production_files == d2.production_files == sorted(names)
        assert [m.reporting_month for m in d1.months] == ["2026-04", "2026-05", "2026-06"]

    def test_month_grouping_and_single_name_contract(self, tmp_path: Path):
        (tmp_path / "rtt_2026_06.csv").write_text("x", encoding="utf-8")
        d = I.discover_sources(tmp_path)
        m = d.month("2026-06")
        assert m.files == ["rtt_2026_06.csv"]
        # the filename contract permits exactly one name per month, so on-disk
        # discovery never yields >1 candidate; the same-month/different-hash
        # (revision) path is resolved by SourceRegistry.resolve_month instead.
        assert m.multiple_candidates is False


class TestRegistry:

    def test_loads_and_validates(self, tmp_path: Path):
        reg = _registry(tmp_path, [
            {"reporting_period": "2026-04", "file": "rtt_2026_04.csv",
             "sha256": _HEX, "selected": True}])
        assert reg.entry_for_file("rtt_2026_04.csv").selected is True

    @pytest.mark.parametrize("bad", [
        {"reporting_period": "2026-4", "file": "rtt_2026_04.csv", "sha256": _HEX, "selected": True},
        {"reporting_period": "2026-04", "file": "april.csv", "sha256": _HEX, "selected": True},
        {"reporting_period": "2026-04", "file": "rtt_2026_04.csv", "sha256": "zz", "selected": True},
        {"reporting_period": "2026-04", "file": "rtt_2026_05.csv", "sha256": _HEX, "selected": True},
    ])
    def test_rejects_bad_entry(self, tmp_path: Path, bad):
        with pytest.raises(ValueError):
            _registry(tmp_path, [bad])

    def test_rejects_two_selected_same_month(self, tmp_path: Path):
        with pytest.raises(ValueError, match="selected"):
            _registry(tmp_path, [
                {"reporting_period": "2026-04", "file": "rtt_2026_04.csv",
                 "sha256": "a" * 64, "selected": True},
                {"reporting_period": "2026-04", "file": "rtt_2026_04.csv",
                 "sha256": "b" * 64, "selected": True}])

    def test_rejects_multi_hash_month_without_a_selection(self, tmp_path: Path):
        # constructed directly; two different-hash entries, none selected
        with pytest.raises(ValueError, match="need exactly 1"):
            _registry(tmp_path, [
                {"reporting_period": "2026-04", "file": "rtt_2026_04.csv",
                 "sha256": "a" * 64, "selected": False},
                {"reporting_period": "2026-04", "file": "rtt_2026_04.csv",
                 "sha256": "b" * 64, "selected": False}])


class TestRevisionResolution:

    def _reg(self, **kw):
        e = I.SourceEntry(reporting_period="2026-04", file="rtt_2026_04.csv",
                          sha256=kw.get("sha256", "a" * 64),
                          selected=kw.get("selected", True))
        return I.SourceRegistry(entries=[e])

    def test_same_hash_is_one_artifact_not_double_ingested(self):
        reg = self._reg()
        res = reg.resolve_month("2026-04", [("f1.csv", "a" * 64), ("f2.csv", "a" * 64)])
        assert res.chosen_sha256 == "a" * 64
        assert res.duplicate_files == ["f2.csv"]
        assert "identical bytes" in res.note

    def test_different_hash_without_selection_fails_closed(self):
        reg = self._reg(selected=False)
        with pytest.raises(I.AmbiguousRevisionError):
            reg.resolve_month("2026-04", [("f1.csv", "a" * 64), ("f2.csv", "b" * 64)])

    def test_explicit_selection_is_order_independent(self):
        reg = self._reg(sha256="a" * 64, selected=True)
        obs = [("f_a.csv", "a" * 64), ("f_b.csv", "b" * 64)]
        r1 = reg.resolve_month("2026-04", obs)
        r2 = reg.resolve_month("2026-04", list(reversed(obs)))
        assert r1.chosen_file == r2.chosen_file == "f_a.csv"
        assert r1.chosen_sha256 == "a" * 64


class TestAcceptMonth:

    def _reg_for(self, tmp_path: Path, path: Path) -> I.SourceRegistry:
        return _registry(tmp_path, [{
            "reporting_period": I.parse_production_filename(path.name),
            "file": path.name, "sha256": I.sha256_file(path), "selected": True}])

    def test_happy_path(self, tmp_path: Path):
        p = _month_file(tmp_path, "rtt_2026_06.csv")
        rep = I.accept_month(p, registry=self._reg_for(tmp_path, p))
        assert rep.accepted is True and rep.blocking == []
        assert rep.reporting_month == "2026-06"
        assert rep.schema_ok is True and rep.n_week_bands == 105
        assert rep.n_loaded_rows == rep.n_data_rows == 2
        assert rep.candidate_key_usable is True

    def test_requires_provenance(self, tmp_path: Path):
        p = _month_file(tmp_path, "rtt_2026_06.csv")
        rep = I.accept_month(p)                      # no registry, no expected hash
        assert rep.accepted is False
        assert any("provenance" in b for b in rep.blocking)
        ok = I.accept_month(p, expected_sha256=I.sha256_file(p))
        assert ok.accepted is True

    def test_sha_mismatch_blocks(self, tmp_path: Path):
        p = _month_file(tmp_path, "rtt_2026_06.csv")
        rep = I.accept_month(p, expected_sha256="f" * 64)
        assert rep.accepted is False
        assert any("SHA-256 mismatch" in b for b in rep.blocking)

    def test_bad_filename_blocks(self, tmp_path: Path):
        p = _month_file(tmp_path, "rtt_2026_6.csv")
        rep = I.accept_month(p, expected_sha256=I.sha256_file(p))
        assert rep.accepted is False
        assert any(b.startswith("filename:") for b in rep.blocking)

    def test_period_missing_blocks(self, tmp_path: Path):
        hdr = [h for h in HEADER if h != "Period"]
        rows = [_row(tfc="C_100")[1:], _row(tfc="C_101")[1:]]
        p = _write(tmp_path / "rtt_2026_06.csv", rows, header=hdr)
        rep = I.accept_month(p, expected_sha256=I.sha256_file(p))
        assert rep.accepted is False
        assert any("Period" in b for b in rep.blocking)

    def test_period_malformed_blocks(self, tmp_path: Path):
        p = _month_file(tmp_path, "rtt_2026_06.csv", period="June 2026")
        rep = I.accept_month(p, expected_sha256=I.sha256_file(p))
        assert any("unparseable Period" in b for b in rep.blocking)

    def test_multiple_periods_block(self, tmp_path: Path):
        p = _write(tmp_path / "rtt_2026_06.csv", [
            _row(period="RTT-June-2026", tfc="C_100"),
            _row(period="RTT-May-2026", tfc="C_101")])
        rep = I.accept_month(p, expected_sha256=I.sha256_file(p))
        assert any("multiple distinct Period" in b for b in rep.blocking)

    def test_filename_period_mismatch_blocks(self, tmp_path: Path):
        p = _month_file(tmp_path, "rtt_2026_05.csv", period="RTT-June-2026")
        rep = I.accept_month(p, expected_sha256=I.sha256_file(p))
        assert any("filename / Period disagree" in b for b in rep.blocking)

    @pytest.mark.parametrize("mutate", ["drop_interior", "duplicate", "extra"])
    def test_frozen_band_schema_still_rejects(self, tmp_path: Path, mutate):
        bands = list(_BANDS)
        if mutate == "drop_interior":
            del bands[40]
        elif mutate == "duplicate":
            bands = bands + [bands[3]]
        elif mutate == "extra":
            bands = bands + ["Gt 300 To 301 Weeks SUM 1"]
        hdr = _LABELS + bands + _TAIL
        row = (["RTT-June-2026", "RAA", "P", "00A", "C", "Part_2",
                "Incomplete Pathways", "C_100", "GS"] + ["0"] * len(bands) + ["", "", "1"])
        p = _write(tmp_path / "rtt_2026_06.csv", [row], header=hdr)
        rep = I.accept_month(p, expected_sha256=I.sha256_file(p))
        assert rep.accepted is False and rep.schema_ok is False
        assert any(b.startswith("schema:") for b in rep.blocking)

    def test_duplicate_candidate_key_blocks(self, tmp_path: Path):
        dup = _row(tfc="C_100", total_all=1)
        p = _write(tmp_path / "rtt_2026_06.csv", [dup, list(dup)])
        rep = I.accept_month(p, expected_sha256=I.sha256_file(p))
        assert rep.accepted is False
        assert any("candidate key" in b for b in rep.blocking)

    def test_whitespace_key_cell_blocks(self, tmp_path: Path):
        p = _write(tmp_path / "rtt_2026_06.csv", [
            _row(tfc="  ", total_all=1), _row(tfc="C_100", total_all=1)])
        rep = I.accept_month(p, expected_sha256=I.sha256_file(p))
        assert rep.accepted is False
        assert any("whitespace-only key cell" in b for b in rep.blocking)

    def test_missing_key_value_blocks(self, tmp_path: Path):
        p = _write(tmp_path / "rtt_2026_06.csv", [
            _row(comm="", tfc="C_100", total_all=1), _row(tfc="C_101", total_all=1)])
        rep = I.accept_month(p, expected_sha256=I.sha256_file(p))
        assert rep.accepted is False
        assert any("candidate key" in b for b in rep.blocking)

    def test_negative_value_blocks(self, tmp_path: Path):
        row = _row(tfc="C_100", total_all=1)
        row[9] = "-1"                                # first band cell
        p = _write(tmp_path / "rtt_2026_06.csv", [row, _row(tfc="C_101", total_all=1)])
        rep = I.accept_month(p, expected_sha256=I.sha256_file(p))
        assert rep.accepted is False
        assert any("load:" in b and "negative" in b for b in rep.blocking)

    def test_not_selected_release_blocks(self, tmp_path: Path):
        p = _month_file(tmp_path, "rtt_2026_06.csv")
        reg = I.SourceRegistry(entries=[
            I.SourceEntry("2026-06", "rtt_2026_06.csv", I.sha256_file(p), selected=False),
            I.SourceEntry("2026-06", "rtt_2026_06b.csv", "b" * 64, selected=True)])
        rep = I.accept_month(p, registry=reg)
        assert rep.accepted is False
        assert any(b.startswith("revision:") for b in rep.blocking)

    def test_raw_file_never_modified(self, tmp_path: Path):
        p = _month_file(tmp_path, "rtt_2026_06.csv")
        before = p.read_bytes()
        I.accept_month(p, expected_sha256=I.sha256_file(p))
        I.accept_month(p, expected_sha256="f" * 64)     # a rejecting run
        assert p.read_bytes() == before
