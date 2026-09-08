"""Focused closure tests for the Codex Phase 3 audit findings P3-A01 … P3-A07
(`docs/phase3_codex_audit.md`). Each test reproduces the audit's own scenario.

Synthetic only — no test reads ``data/raw/``.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import pandas as pd
import pytest

from nhs_rtt import crossmonth as X
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
_PERIOD = {"2026-04": "RTT-April-2026", "2026-05": "RTT-May-2026", "2026-06": "RTT-June-2026"}


def _row(month="2026-06", provider="RAA", comm="00A", part="Part_2", tfc="C_100",
         first_band="1", total_all="1", total="", unknown=""):
    bands = [str(first_band)] + ["0"] * 104
    return [_PERIOD[month], provider, "PROV A", comm, "COMM A", part,
            "Incomplete Pathways", tfc, tfn_for(tfc), *bands,
            str(total), str(unknown), str(total_all)]


def tfn_for(tfc):
    return "Total" if tfc == "C_999" else "General Surgery Service"


def _write(path: Path, rows, header=HEADER) -> Path:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return path


def _month_csv(d: Path, month: str, rows=None, name=None) -> Path:
    rows = rows or [_row(month, tfc="C_100"), _row(month, tfc="C_101")]
    return _write(d / (name or f"rtt_{month.replace('-', '_')}.csv"), rows)


def _registry_file(d: Path, entries: list[dict], name="manifest.json") -> Path:
    p = d / name
    p.write_text(json.dumps({"sources": entries}), encoding="utf-8")
    return p


def _entry(path: Path, *, month=None, file=None, selected=True):
    return {"reporting_period": month or I.parse_production_filename(path.name),
            "file": file or path.name, "sha256": I.sha256_file(path), "selected": selected}


def _raw_with_registry(tmp_path: Path, months: dict[str, list | None]):
    tmp_path.mkdir(parents=True, exist_ok=True)
    raw = tmp_path / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    entries = []
    for month, rows in months.items():
        p = _month_csv(raw, month, rows=rows)
        entries.append(_entry(p))
    return raw, _registry_file(tmp_path, entries)


# ========================================================================= #
class TestA01_IntendedSourceCompleteness:

    def test_full_run_succeeds(self, tmp_path: Path):
        raw, reg = _raw_with_registry(tmp_path, {"2026-05": None, "2026-06": None})
        res = X.run_phase3(raw_dir=raw, registry_path=reg,
                           out_dir=tmp_path / "out", write_parquet=True)
        assert res.ok is True and res.combined_rows == 4
        assert res.missing_intended == [] and res.required_months == ["2026-05", "2026-06"]

    def test_removing_an_intended_source_fails_and_does_not_republish(self, tmp_path: Path):
        raw, reg = _raw_with_registry(tmp_path, {"2026-05": None, "2026-06": None})
        first = X.run_phase3(raw_dir=raw, registry_path=reg,
                             out_dir=tmp_path / "out", write_parquet=True)
        assert first.ok is True and first.combined_rows == 4
        gen1 = X.verify_publication(tmp_path / "out")["generation_id"]

        (raw / "rtt_2026_05.csv").rename(raw / "rtt_2026_05.csv.bak")   # source disappears
        second = X.run_phase3(raw_dir=raw, registry_path=reg,
                              out_dir=tmp_path / "out", write_parquet=True)
        assert second.ok is False
        assert second.missing_intended == ["2026-05"]
        assert second.combined_rows is None and second.parquet is None
        # the earlier successful publication is untouched, not redefined to June-only
        pub = X.verify_publication(tmp_path / "out")
        assert pub["valid"] is True and pub["generation_id"] == gen1 and pub["combined_rows"] == 4

    def test_registered_month_never_present_fails(self, tmp_path: Path):
        raw, reg = _raw_with_registry(tmp_path, {"2026-05": None, "2026-06": None})
        entries = json.loads(Path(reg).read_text())
        entries["sources"].append({
            "reporting_period": "2026-04", "file": "rtt_2026_04.csv",
            "sha256": "a" * 64, "selected": True})
        Path(reg).write_text(json.dumps(entries), encoding="utf-8")
        res = X.run_phase3(raw_dir=raw, registry_path=reg,
                           out_dir=tmp_path / "out", write_parquet=True)
        assert res.ok is False and res.missing_intended == ["2026-04"]
        assert res.parquet is None

    def test_explicit_subset_is_recorded(self, tmp_path: Path):
        raw, reg = _raw_with_registry(tmp_path, {"2026-06": None})
        entries = json.loads(Path(reg).read_text())
        for m in ("2026-04", "2026-05"):
            entries["sources"].append({
                "reporting_period": m, "file": f"rtt_{m.replace('-', '_')}.csv",
                "sha256": ("b" if m == "2026-04" else "c") * 64, "selected": True})
        Path(reg).write_text(json.dumps(entries), encoding="utf-8")

        res = X.run_phase3(raw_dir=raw, registry_path=reg, out_dir=tmp_path / "out",
                           write_parquet=True, require_months=["2026-06"])
        assert res.ok is True and res.requested_subset == ["2026-06"]
        assert res.required_months == ["2026-06"] and res.combined_rows == 2
        assert any("explicit requested subset" in n for n in res.notes)


class TestA02_MonthBoundProvenance:

    def _june_under_may_registry(self, tmp_path: Path):
        raw = tmp_path / "raw"
        raw.mkdir()
        june = _month_csv(raw, "2026-06")
        reg = _registry_file(tmp_path, [{
            "reporting_period": "2026-05", "file": "rtt_2026_05.csv",
            "sha256": I.sha256_file(june), "selected": True}])
        return raw, june, reg

    def test_accept_month_rejects_cross_month_digest(self, tmp_path: Path):
        raw, june, reg = self._june_under_may_registry(tmp_path)
        rep = I.accept_month(june, registry=I.SourceRegistry.load(reg))
        assert rep.accepted is False
        assert any("authorises reporting month 2026-05" in b for b in rep.blocking)

    def test_end_to_end_rejects_cross_month_digest(self, tmp_path: Path):
        raw, june, reg = self._june_under_may_registry(tmp_path)
        res = X.run_phase3(raw_dir=raw, registry_path=reg,
                           out_dir=tmp_path / "out", write_parquet=True)
        assert res.ok is False and res.parquet is None
        assert res.acceptance["2026-06"].accepted is False


class TestA03_ImmutableSnapshotBinding:
    """Residual P3-A03: hash + validation + load + accepted frame all come from
    one immutable snapshot; a mutable-path change during the load window cannot
    misbind the accepted bytes."""

    def test_accepted_frame_holds_A_not_later_B(self, tmp_path: Path):
        p = _month_csv(tmp_path, "2026-06", rows=[_row("2026-06", tfc="C_100", total_all="7")])
        rep = I.accept_month(p, expected_sha256=I.sha256_file(p))
        assert rep.accepted is True and rep.frame is not None
        _write(p, [_row("2026-06", tfc="C_100", total_all="99")])          # file changes to B afterwards
        assert int(rep.frame["Total All"].iloc[0]) == 7                    # bound to the snapshot (A)
        combined = X.combine_months([X.MonthPayload("2026-06", p.name, rep.sha256, rep.frame)])
        assert int(combined["Total All"].iloc[0]) == 7                     # B never published

    def test_changed_and_restored_original_does_not_misbind(self, tmp_path: Path, monkeypatch):
        # Codex counterexample: mutate the ORIGINAL source to B only for the load
        # window, then restore A before acceptance finishes.
        p = _month_csv(tmp_path, "2026-06", rows=[_row("2026-06", tfc="C_100", total_all="7")])
        a_bytes = p.read_bytes()
        sha_a = I.sha256_file(p)
        b_path = _write(tmp_path / "b.csv", [_row("2026-06", tfc="C_100", total_all="99")])
        b_bytes = b_path.read_bytes()
        real_load = S.load_rtt_csv

        def sneaky_load(target, *a, **k):
            p.write_bytes(b_bytes)                       # revision process hits the ORIGINAL path
            try:
                return real_load(target, *a, **k)       # target is the private snapshot (still A)
            finally:
                p.write_bytes(a_bytes)                  # original restored to A

        monkeypatch.setattr(I._sem, "load_rtt_csv", sneaky_load)
        rep = I.accept_month(p, expected_sha256=sha_a)
        assert rep.accepted is True
        assert rep.sha256 == sha_a == rep.sha256_after
        assert int(rep.frame["Total All"].iloc[0]) == 7                    # from the snapshot, not B
        assert p.read_bytes() == a_bytes                                   # original untouched at end

    def test_change_before_snapshot_rejects_via_discovery_digest(self, tmp_path: Path):
        p = _month_csv(tmp_path, "2026-06", rows=[_row("2026-06", tfc="C_100", total_all="7")])
        stale = I.sha256_file(p)
        _write(p, [_row("2026-06", tfc="C_100", total_all="99")])          # changed before acceptance read
        rep = I.accept_month(p, expected_sha256="9" * 64, discovery_sha256=stale)
        assert rep.accepted is False and rep.frame is None
        assert any("changed between discovery and" in b for b in rep.blocking)

    def test_change_after_snapshot_is_a_warning_not_a_block(self, tmp_path: Path):
        p = _month_csv(tmp_path, "2026-06", rows=[_row("2026-06", tfc="C_100", total_all="7")])
        sha_a = I.sha256_file(p)
        rep = I.accept_month(p, expected_sha256=sha_a)
        # (no mutation during acceptance -> accepted); now mutate and re-run
        _write(p, [_row("2026-06", tfc="C_100", total_all="99")])
        rep2 = I.accept_month(p, expected_sha256=sha_a)                     # snapshot is now B
        assert rep2.accepted is False                                      # digest != expected A
        assert rep.accepted is True and not rep.warnings

    def test_rejected_report_clears_frame(self, tmp_path: Path):
        bands = list(_BANDS); del bands[10]
        header = _LABELS + bands + _TAIL
        row = (["RTT-June-2026", "RAA", "P", "00A", "C", "Part_2", "Incomplete Pathways",
                "C_100", "GS"] + ["0"] * len(bands) + ["", "", "1"])
        p = _write(tmp_path / "rtt_2026_06.csv", [row], header=header)
        rep = I.accept_month(p, expected_sha256=I.sha256_file(p))
        assert rep.accepted is False and rep.frame is None

    def test_provenance_basename_is_original_not_snapshot(self, tmp_path: Path):
        raw, reg = _raw_with_registry(tmp_path, {"2026-06": None})
        res = X.run_phase3(raw_dir=raw, registry_path=reg,
                           out_dir=tmp_path / "out", write_parquet=True)
        assert res.payloads[0].source_file == "rtt_2026_06.csv"
        assert res.acceptance["2026-06"].filename == "rtt_2026_06.csv"
        assert "nhs_rtt_snap_" not in res.acceptance["2026-06"].path
        combined = pd.read_parquet(res.parquet["parquet_path"])
        assert set(combined["source_file"]) == {"rtt_2026_06.csv"}

    def test_run_phase3_payload_is_the_bound_frame(self, tmp_path: Path):
        raw, reg = _raw_with_registry(tmp_path, {"2026-06": None})
        res = X.run_phase3(raw_dir=raw, registry_path=reg,
                           out_dir=tmp_path / "out", write_parquet=False)
        assert res.payloads[0].df is res.acceptance["2026-06"].frame       # no reopen

    def test_raw_source_untouched_by_acceptance(self, tmp_path: Path):
        p = _month_csv(tmp_path, "2026-06")
        before = p.read_bytes()
        I.accept_month(p, expected_sha256=I.sha256_file(p))
        assert p.read_bytes() == before


class TestA04_PublicationGenerationIntegrity:

    def _publish(self, tmp_path, months, out):
        raw, reg = _raw_with_registry(tmp_path, months)
        return X.run_phase3(raw_dir=raw, registry_path=reg, out_dir=out, write_parquet=True)

    def test_successful_publication_self_verifies(self, tmp_path: Path):
        out = tmp_path / "out"
        res = self._publish(tmp_path, {"2026-06": None}, out)
        assert res.publication["valid"] is True
        m = json.loads((out / X.GENERATION_MARKER).read_text())
        sc = json.loads((out / "rtt_combined.ingest_manifest.json").read_text())
        assert sc["run"]["generation_id"] == m["generation_id"]
        assert X.verify_publication(out)["valid"] is True

    def test_interrupted_commit_leaves_pair_invalid_then_recoverable(self, tmp_path: Path, monkeypatch):
        out = tmp_path / "out"
        self._publish(tmp_path, {"2026-06": None}, out)                    # generation 1
        gen1 = X.verify_publication(out)["generation_id"]

        raw2, reg2 = _raw_with_registry(tmp_path / "g2", {"2026-05": None, "2026-06": None})
        real_replace = os.replace
        calls = {"n": 0}

        def flaky(src, dst, *a, **k):
            calls["n"] += 1
            if calls["n"] == 2:                                           # after parquet, before sidecar
                raise OSError("simulated interrupted publication")
            return real_replace(src, dst, *a, **k)

        monkeypatch.setattr(X._os, "replace", flaky)
        with pytest.raises((X.PublicationError, OSError)):
            X.run_phase3(raw_dir=raw2, registry_path=reg2, out_dir=out, write_parquet=True)
        monkeypatch.undo()

        bad = X.verify_publication(out)
        assert bad["valid"] is False and "mismatch" in bad["reason"].lower()

        rec = X.restore_previous_generation(out)
        assert rec["restored"] is True and rec["verify"]["valid"] is True
        assert X.verify_publication(out)["generation_id"] == gen1

    def test_rejected_rerun_after_success_keeps_previous(self, tmp_path: Path):
        out = tmp_path / "out"
        raw, reg = _raw_with_registry(tmp_path, {"2026-05": None, "2026-06": None})
        first = X.run_phase3(raw_dir=raw, registry_path=reg, out_dir=out, write_parquet=True)
        assert first.ok is True
        (raw / "rtt_2026_05.csv").unlink()
        second = X.run_phase3(raw_dir=raw, registry_path=reg, out_dir=out, write_parquet=True)
        assert second.ok is False and second.parquet is None
        assert X.verify_publication(out)["valid"] is True                 # gen 1 preserved

    def test_consumer_detects_tampered_parquet(self, tmp_path: Path):
        out = tmp_path / "out"
        self._publish(tmp_path, {"2026-06": None}, out)
        (out / "rtt_combined.parquet").write_bytes(b"not a parquet any more")
        v = X.verify_publication(out)
        assert v["valid"] is False


class TestR01_VerifierValidatesRowCount:
    """P3-R01: verify_publication must not trust an unchecked marker row count."""

    def _publish(self, tmp_path, out):
        raw, reg = _raw_with_registry(tmp_path, {"2026-06": None})
        X.run_phase3(raw_dir=raw, registry_path=reg, out_dir=out, write_parquet=True)

    def test_valid_publication_returns_verified_row_count(self, tmp_path: Path):
        out = tmp_path / "out"
        self._publish(tmp_path, out)
        v = X.verify_publication(out)
        assert v["valid"] is True and v["combined_rows"] == 2

    def test_tampered_marker_row_count_is_invalid(self, tmp_path: Path):
        out = tmp_path / "out"
        self._publish(tmp_path, out)
        mk = out / X.GENERATION_MARKER
        m = json.loads(mk.read_text())
        m["combined_rows"] = 999999
        mk.write_text(json.dumps(m, indent=2))
        v = X.verify_publication(out)
        assert v["valid"] is False and "row-count" in v["reason"]

    def test_sidecar_row_count_mismatch_is_invalid(self, tmp_path: Path):
        out = tmp_path / "out"
        self._publish(tmp_path, out)
        sc_path = out / "rtt_combined.ingest_manifest.json"
        sc = json.loads(sc_path.read_text())
        sc["deterministic"]["combined_rows"] = 12345
        sc_path.write_text(json.dumps(sc, indent=2))
        mk = out / X.GENERATION_MARKER
        m = json.loads(mk.read_text())
        m["sidecar_sha256"] = X._sha256_path(sc_path)          # keep the hash check happy
        mk.write_text(json.dumps(m, indent=2))
        v = X.verify_publication(out)
        assert v["valid"] is False and "row-count" in v["reason"]

    def test_actual_parquet_row_mismatch_is_invalid(self, tmp_path: Path):
        out = tmp_path / "out"
        self._publish(tmp_path, out)
        pq_path = out / "rtt_combined.parquet"
        df = pd.read_parquet(pq_path)
        pd.concat([df, df], ignore_index=True).to_parquet(pq_path, engine="pyarrow", index=False)
        mk = out / X.GENERATION_MARKER
        m = json.loads(mk.read_text())
        m["parquet_sha256"] = X._sha256_path(pq_path)          # keep the hash check happy
        mk.write_text(json.dumps(m, indent=2))
        v = X.verify_publication(out)
        assert v["valid"] is False and "row-count" in v["reason"]

    def test_missing_marker_row_count_field_is_invalid(self, tmp_path: Path):
        out = tmp_path / "out"
        self._publish(tmp_path, out)
        mk = out / X.GENERATION_MARKER
        m = json.loads(mk.read_text())
        del m["combined_rows"]
        mk.write_text(json.dumps(m, indent=2))
        v = X.verify_publication(out)
        assert v["valid"] is False and "combined_rows" in v["reason"]


class TestR02_ValidBackupRotation:
    """P3-R02: .prev must hold the last KNOWN-VALID generation, and restore
    reports success only when the restored trio verifies."""

    def _pub(self, tmp_path, subdir, months, out):
        raw, reg = _raw_with_registry(tmp_path / subdir, months)
        return raw, reg, X.run_phase3(raw_dir=raw, registry_path=reg, out_dir=out,
                                      write_parquet=True)

    def _flaky_replace(self, monkeypatch, fail_on_call):
        real = os.replace
        n = {"i": 0}

        def flaky(src, dst, *a, **k):
            n["i"] += 1
            if n["i"] == fail_on_call:
                raise OSError(f"simulated failure on os.replace call {fail_on_call}")
            return real(src, dst, *a, **k)

        monkeypatch.setattr(X._os, "replace", flaky)

    def test_valid_generation_rotates_to_prev(self, tmp_path: Path):
        out = tmp_path / "out"
        self._pub(tmp_path, "g1", {"2026-06": None}, out)                   # gen 1 (2 rows)
        self._pub(tmp_path, "g2", {"2026-05": None, "2026-06": None}, out)  # gen 2 (4 rows)
        # .prev now holds gen 1, which must still verify
        rec = X.restore_previous_generation(out)
        assert rec["restored"] is True and rec["verify"]["combined_rows"] == 2

    def test_failed_retry_preserves_valid_prev(self, tmp_path: Path, monkeypatch):
        out = tmp_path / "out"
        self._pub(tmp_path, "g1", {"2026-06": None}, out)                   # gen 1 (2 rows), valid
        raw2, reg2, _ = None, None, None

        # gen-2 attempt: fail AFTER the first replace -> current trio mixed/invalid, .prev = gen1
        self._flaky_replace(monkeypatch, fail_on_call=2)
        raw2, reg2 = _raw_with_registry(tmp_path / "g2", {"2026-05": None, "2026-06": None})
        with pytest.raises((X.PublicationError, OSError)):
            X.run_phase3(raw_dir=raw2, registry_path=reg2, out_dir=out, write_parquet=True)
        monkeypatch.undo()
        assert X.verify_publication(out)["valid"] is False                 # current invalid

        # retry: fail BEFORE the first replace -> rotation must be SKIPPED (current invalid)
        self._flaky_replace(monkeypatch, fail_on_call=1)
        with pytest.raises((X.PublicationError, OSError)):
            X.run_phase3(raw_dir=raw2, registry_path=reg2, out_dir=out, write_parquet=True)
        monkeypatch.undo()

        rec = X.restore_previous_generation(out)
        assert rec["restored"] is True                                     # .prev is still valid gen 1
        assert rec["verify"]["valid"] is True and rec["verify"]["combined_rows"] == 2

    def test_invalid_prev_is_not_reported_restorable(self, tmp_path: Path):
        out = tmp_path / "out"
        self._pub(tmp_path, "g1", {"2026-06": None}, out)
        self._pub(tmp_path, "g2", {"2026-05": None, "2026-06": None}, out)  # creates .prev (gen1)
        (out / "rtt_combined.parquet.prev").write_bytes(b"corrupt")
        rec = X.restore_previous_generation(out)
        assert rec["restored"] is False and "does not verify" in rec["reason"]

    def test_no_backup_available(self, tmp_path: Path):
        out = tmp_path / "out"
        self._pub(tmp_path, "g1", {"2026-06": None}, out)                   # first publish -> no .prev
        rec = X.restore_previous_generation(out)
        assert rec["restored"] is False and "no complete previous" in rec["reason"]


class TestA05_ReservedProvenanceColumns:

    @pytest.mark.parametrize("reserved", list(I.RESERVED_PROVENANCE_COLUMNS))
    def test_source_with_reserved_column_rejected(self, tmp_path: Path, reserved):
        header = _LABELS + [reserved] + _BANDS + _TAIL
        row = (["RTT-June-2026", "RAA", "P", "00A", "C", "Part_2", "Incomplete Pathways",
                "C_100", "GS", "original source value"] + ["1"] + ["0"] * 104 + ["", "", "1"])
        p = _write(tmp_path / "rtt_2026_06.csv", [row], header=header)
        rep = I.accept_month(p, expected_sha256=I.sha256_file(p))
        assert rep.accepted is False
        assert rep.reserved_provenance_columns_present == [reserved]
        assert any("reserved Phase 3 provenance column" in b for b in rep.blocking)

    def test_combine_defensive_collision(self, tmp_path: Path):
        p = _month_csv(tmp_path, "2026-06")
        df = S.load_rtt_csv(p)
        df = df.assign(source_file="already here")
        with pytest.raises(X.ReservedColumnError):
            X.combine_months([X.MonthPayload("2026-06", p.name, "x" * 64, df)])

    def test_ordinary_121_column_source_unaffected(self, tmp_path: Path):
        p = _month_csv(tmp_path, "2026-06")
        rep = I.accept_month(p, expected_sha256=I.sha256_file(p))
        assert rep.accepted is True
        combined = X.combine_months([X.MonthPayload("2026-06", p.name, rep.sha256, rep.frame)])
        assert combined.shape[1] == len(HEADER) + 4
        assert set(combined["source_file"]) == {p.name}


class TestA06_BackupSuffixClassification:

    def test_backup_suffixes_are_malformed_candidates(self, tmp_path: Path):
        _month_csv(tmp_path, "2026-06")
        for n in ("rtt_2026_04.csv.bak", "rtt_2026_05.csv~", "rtt_2026_03.csv.tmp"):
            (tmp_path / n).write_text("x", encoding="utf-8")
        (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
        d = I.discover_sources(tmp_path)
        assert d.production_files == ["rtt_2026_06.csv"]
        assert set(d.malformed_candidates) == {
            "rtt_2026_04.csv.bak", "rtt_2026_05.csv~", "rtt_2026_03.csv.tmp"}
        assert "notes.txt" in d.ignored and "manifest.json" not in d.malformed_candidates

    def test_backup_file_is_not_ingestible(self):
        with pytest.raises(ValueError):
            I.parse_production_filename("rtt_2026_04.csv.bak")


class TestA07_StructuredInvalidInput:

    def test_fractional_count_is_structured_rejection(self, tmp_path: Path):
        p = _write(tmp_path / "rtt_2026_06.csv",
                   [_row("2026-06", tfc="C_100", total_all="1.5")])
        rep = I.accept_month(p, expected_sha256=I.sha256_file(p))       # must not raise
        assert rep.accepted is False
        assert any(b.startswith("load:") for b in rep.blocking)

    def test_null_manifest_entry_is_structured_rejection(self, tmp_path: Path):
        reg = tmp_path / "manifest.json"
        reg.write_text(json.dumps({"sources": [None]}), encoding="utf-8")
        with pytest.raises(ValueError, match="must be a JSON object"):
            I.SourceRegistry.load(reg)

    def test_non_string_registry_field_rejected(self, tmp_path: Path):
        reg = tmp_path / "manifest.json"
        reg.write_text(json.dumps({"sources": [
            {"reporting_period": 202604, "file": "rtt_2026_04.csv",
             "sha256": "a" * 64, "selected": True}]}), encoding="utf-8")
        with pytest.raises(ValueError, match="must be a string"):
            I.SourceRegistry.load(reg)
