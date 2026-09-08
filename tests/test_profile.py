"""Targeted tests for :mod:`nhs_rtt.profile`.

Scope is deliberately narrow: the profiler must describe structure faithfully,
must never mutate/coerce/interpret the input, and must **not silently accept
malformed structure** on future monthly files. These tests lock in that
contract on tiny synthetic fixtures (see ``conftest.py``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nhs_rtt import profile as p
from conftest import N_COLS


# --------------------------------------------------------------------------- #
# 1. A valid CSV can be profiled
# --------------------------------------------------------------------------- #

def test_valid_csv_basic_shape(valid_csv: Path):
    prof = p.profile_csv(valid_csv)
    assert prof.n_rows == 3
    assert prof.n_cols == N_COLS
    assert prof.column_names[:2] == ["Period", "Provider Parent Org Code"]
    assert prof.duplicate_row_count == 0
    assert prof.n_ragged_rows == 0
    assert prof.structural_warnings == []
    assert prof.unbound_roles == []
    assert prof.week_bucket_sequence_warnings == []


def test_valid_csv_null_and_dtype_facts(valid_csv: Path):
    prof = p.profile_csv(valid_csv)
    by_name = {c.name: c for c in prof.columns}

    wk0 = by_name["Gt 00 To 01 Weeks SUM 1"]     # values 5, "", 10
    assert wk0.n_null == 1
    assert wk0.n_total == 3
    assert round(wk0.null_pct, 2) == 33.33
    assert wk0.inferred_dtype == "integer"
    assert wk0.numeric_min == 5.0                 # blank NOT coerced to 0
    assert by_name["Period"].inferred_dtype == "string"
    assert by_name["Period"].n_unique_est == 1


def test_profile_does_not_touch_raw_file(valid_csv: Path):
    before = valid_csv.read_bytes()
    p.profile_csv(valid_csv)
    assert valid_csv.read_bytes() == before


def test_bom_is_stripped(bom_csv: Path):
    prof = p.profile_csv(bom_csv)
    assert prof.column_names[0] == "Period"       # not "﻿Period"
    assert prof.n_cols == N_COLS


# --------------------------------------------------------------------------- #
# 2. Empty CSV handling
# --------------------------------------------------------------------------- #

def test_zero_byte_csv_raises_valueerror(truly_empty_csv: Path):
    with pytest.raises(ValueError, match="no header row"):
        p.profile_csv(truly_empty_csv)


def test_header_only_csv_profiles_with_zero_rows(header_only_csv: Path):
    prof = p.profile_csv(header_only_csv)
    assert prof.n_rows == 0
    assert prof.n_cols == N_COLS
    assert prof.duplicate_row_count == 0
    assert all(c.n_total == 0 for c in prof.columns)
    assert {c.inferred_dtype for c in prof.columns} == {"empty"}
    assert prof.structural_warnings == []


# --------------------------------------------------------------------------- #
# 3. Missing / ambiguous identifier fields
# --------------------------------------------------------------------------- #

def test_missing_identifier_columns_are_skipped_not_fatal(no_identifiers_csv: Path):
    prof = p.profile_csv(no_identifiers_csv)
    assert prof.categoricals == {}
    assert set(prof.unbound_roles) == set(p.DEFAULT_CATEGORICAL_ROLES)
    # Absence of identifier columns is not itself a structural warning...
    assert prof.structural_warnings == []
    # ...but the profile still describes what IS present.
    assert prof.n_cols == 3 and prof.n_rows == 2


def test_partial_identifier_columns_bind_only_complete_roles(tmp_path: Path):
    (tmp_path / "x.csv").write_text(
        "Provider Org Code,RTT Part Type,RTT Part Description\n"
        "RAA,Part_2,Incomplete Pathways\n",
        encoding="utf-8",
    )
    prof = p.profile_csv(tmp_path / "x.csv")
    assert "provider" not in prof.categoricals
    assert "provider" in prof.unbound_roles
    assert "rtt_part" in prof.categoricals


def test_duplicate_headers_are_flagged_and_role_left_unbound(duplicate_header_csv: Path):
    with pytest.warns(UserWarning, match="duplicate header"):
        prof = p.profile_csv(duplicate_header_csv)
    assert prof.duplicate_headers == ["Provider Org Code"]
    assert "provider" in prof.unbound_roles
    assert "provider" not in prof.categoricals
    assert any("ambiguous" in w for w in prof.structural_warnings)
    # profiling still completes and both physical columns are described
    assert prof.n_rows == 1
    assert sum(c.name == "Provider Org Code" for c in prof.columns) == 2


# --------------------------------------------------------------------------- #
# 4. Output directory / artifact creation
# --------------------------------------------------------------------------- #

def test_save_profile_creates_missing_output_dir(valid_csv: Path, tmp_path: Path):
    outdir = tmp_path / "does" / "not" / "exist"
    assert not outdir.exists()
    prof = p.profile_csv(valid_csv)
    written = p.save_profile(prof, outdir)
    assert outdir.is_dir()
    assert written and all(w.exists() for w in written)
    names = {w.name for w in written}
    assert {"rtt_mini__overview.md", "rtt_mini__columns.csv",
            "rtt_mini__column_flags.csv", "rtt_mini__mapping_anomalies.csv",
            "rtt_mini__MANIFEST.txt"} <= names


def test_empty_anomaly_csv_has_header_not_zero_bytes(valid_csv: Path, tmp_path: Path):
    prof = p.profile_csv(valid_csv)
    p.save_profile(prof, tmp_path)
    anom = (tmp_path / "rtt_mini__mapping_anomalies.csv").read_text("utf-8").splitlines()
    assert anom == ["role,kind,key,n_related,related_values"]   # header only


def test_manifest_lists_every_written_artifact(valid_csv: Path, tmp_path: Path):
    prof, written = p.profile_and_save(valid_csv, outdir=tmp_path)
    manifest = (tmp_path / "rtt_mini__MANIFEST.txt").read_text("utf-8")
    for w in written:
        assert w.name in manifest


def test_profile_and_save_roundtrip(valid_csv: Path, tmp_path: Path):
    prof, _ = p.profile_and_save(valid_csv, outdir=tmp_path / "profiles")
    assert prof.n_rows == 3
    overview = (tmp_path / "profiles" / "rtt_mini__overview.md").read_text("utf-8")
    assert "Data profile" in overview
    assert "Column flags" in overview
    assert "Structural warnings: none" in overview


# --------------------------------------------------------------------------- #
# 5. Duplicate detection (exact, not hash-approximate)
# --------------------------------------------------------------------------- #

def test_exact_duplicate_rows_are_counted(duplicated_csv: Path):
    prof = p.profile_csv(duplicated_csv)
    assert prof.n_rows == 5
    assert prof.duplicate_row_count == 2


def test_no_false_duplicates_on_distinct_rows(valid_csv: Path):
    assert p.profile_csv(valid_csv).duplicate_row_count == 0


def test_near_duplicate_rows_are_not_aliased(near_duplicate_csv: Path):
    # Would collide under a naive "|".join(row); must not under exact equality.
    prof = p.profile_csv(near_duplicate_csv)
    assert prof.n_rows == 2
    assert prof.duplicate_row_count == 0


# --------------------------------------------------------------------------- #
# 6. Malformed quoting is reported, not silently accepted
# --------------------------------------------------------------------------- #

def test_unterminated_quote_is_reported_and_profile_still_returned(
    unterminated_quote_csv: Path,
):
    with pytest.warns(UserWarning, match="CSV parse error"):
        prof = p.profile_csv(unterminated_quote_csv)
    assert prof.parse_truncated is True
    assert any("parse error" in w for w in prof.structural_warnings)
    assert prof.n_rows == 1            # the one clean row before the break


# --------------------------------------------------------------------------- #
# 7. Ragged rows count missing fields consistently
# --------------------------------------------------------------------------- #

def test_ragged_row_increments_empty_type_count(ragged_csv: Path):
    prof = p.profile_csv(ragged_csv)
    assert prof.n_ragged_rows == 1
    last = prof.columns[-1]           # "Total All" — missing from the short row
    assert last.n_null == 1
    assert last.type_counts["empty"] == 1     # not left un-incremented
    assert last.n_total == 2


# --------------------------------------------------------------------------- #
# 8. Column flagging (whole-word, header text only)
# --------------------------------------------------------------------------- #

def test_column_flags_partition_by_header_text(valid_csv: Path):
    flags = p.profile_csv(valid_csv).column_flags
    assert flags["total_columns"] == ["Total", "Total All"]
    assert flags["unknown_columns"] == ["Patients with unknown clock start date"]
    assert flags["week_bucket_columns"] == [
        "Gt 00 To 01 Weeks SUM 1", "Gt 01 To 02 Weeks SUM 1",
        "Gt 02 To 03 Weeks SUM 1", "Gt 03 Weeks SUM 1",
    ]


def test_subtotal_is_not_a_total_candidate():
    out = p.classify_columns(["Subtotal", "Total", "Grand Total", "totally_unrelated"])
    assert out["total_columns"] == ["Total", "Grand Total"]


def test_classify_columns_is_pure_and_standalone():
    out = p.classify_columns(["Total All", "Gt 52 To 53 Weeks SUM 1", "Foo"])
    assert out["total_columns"] == ["Total All"]
    assert out["week_bucket_columns"] == ["Gt 52 To 53 Weeks SUM 1"]
    assert out["unknown_columns"] == []


# --------------------------------------------------------------------------- #
# 9. Week-bucket sequence validation (structural only)
# --------------------------------------------------------------------------- #

def test_contiguous_bucket_sequence_has_no_warnings():
    assert p.check_week_bucket_sequence([
        "Gt 00 To 01 Weeks SUM 1", "Gt 01 To 02 Weeks SUM 1",
        "Gt 02 To 03 Weeks SUM 1", "Gt 03 Weeks SUM 1",
    ]) == []


def test_bucket_sequence_detects_gap():
    warns = p.check_week_bucket_sequence(
        ["Gt 00 To 01 Weeks SUM 1", "Gt 02 To 03 Weeks SUM 1"]
    )
    assert warns and any("gap or overlap" in w for w in warns)


def test_bucket_sequence_detects_non_unit_width_and_disorder():
    warns = p.check_week_bucket_sequence(
        ["Gt 00 To 05 Weeks SUM 1", "Gt 00 To 01 Weeks SUM 1"]
    )
    assert any("not one week wide" in w for w in warns)
    assert any("ascending order" in w or "gap or overlap" in w for w in warns)


def test_bucket_sequence_open_ended_must_be_last_and_aligned():
    warns = p.check_week_bucket_sequence(
        ["Gt 00 To 01 Weeks SUM 1", "Gt 09 Weeks SUM 1"]
    )
    assert any("open-ended" in w for w in warns)


def test_broken_bucket_sequence_surfaces_as_structural_warning(tmp_path: Path):
    header = ["Gt 00 To 01 Weeks SUM 1", "Gt 05 To 06 Weeks SUM 1", "Total All"]
    (tmp_path / "b.csv").write_text(",".join(header) + "\n1,2,3\n", encoding="utf-8")
    prof = p.profile_csv(tmp_path / "b.csv")
    assert prof.week_bucket_sequence_warnings
    assert any("week-bucket sequence" in w for w in prof.structural_warnings)


# --------------------------------------------------------------------------- #
# 10. Code / name mapping anomalies
# --------------------------------------------------------------------------- #

def test_one_to_one_mapping_reports_no_anomalies(valid_csv: Path):
    prof = p.profile_csv(valid_csv)
    assert prof.categoricals["provider"].mapping_anomaly_rows() == []


def test_name_shared_by_two_codes_is_flagged(name_collision_csv: Path):
    prof = p.profile_csv(name_collision_csv)
    rows = prof.categoricals["provider"].mapping_anomaly_rows()
    assert len(rows) == 1
    assert rows[0]["kind"] == "name_has_multiple_codes"
    assert rows[0]["key"] == "PROVIDER ALPHA"
    assert rows[0]["n_related"] == 2
    assert "RAA" in rows[0]["related_values"] and "RZZ" in rows[0]["related_values"]


def test_blank_names_are_labelled_separately(valid_csv: Path):
    # commissioner: 00A -> "COMM ONE" (x2), 00B -> "" (blank)
    cat = p.profile_csv(valid_csv).categoricals["commissioner"]
    assert cat.n_distinct_names_nonblank == 1
    assert cat.n_blank_name_variants == 1


# --------------------------------------------------------------------------- #
# 11. Markdown rendering does not break on pipe characters
# --------------------------------------------------------------------------- #

def test_md_table_escapes_pipe_characters():
    out = p._md_table([{"key": "A", "related_values": "X | Y | Z"}])
    header, sep, data = out.splitlines()[:3]
    assert "X \\| Y \\| Z" in data              # value pipes escaped, kept in one cell
    assert data.split(" | ") == ["| A", "X \\| Y \\| Z |"]   # exactly 2 columns
    assert sep == "| --- | --- |"               # 2-column table, not split by the value


# --------------------------------------------------------------------------- #
# 12. CLI behaviour and exit codes
# --------------------------------------------------------------------------- #

def test_cli_clean_file_returns_zero_and_writes_manifest(valid_csv: Path, tmp_path: Path):
    rc = p.main([str(valid_csv), "--outdir", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "rtt_mini__MANIFEST.txt").exists()


def test_cli_returns_two_on_structural_warning(duplicate_header_csv: Path, tmp_path: Path):
    with pytest.warns(UserWarning):
        rc = p.main([str(duplicate_header_csv), "--outdir", str(tmp_path)])
    assert rc == 2


# --------------------------------------------------------------------------- #
# 13. Token classification
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "token,expected",
    [
        ("", "empty"), ("   ", "empty"), (None, "empty"),
        ("0", "int"), ("-7", "int"), ("42", "int"), ("001", "int"),
        ("3.14", "float"), (".5", "float"),
        ("true", "bool"), ("FALSE", "bool"),
        ("2026-04-01", "date"),
        ("RTT-April-2026", "str"), ("C_999", "str"),
    ],
)
def test_classify_token(token, expected):
    assert p.classify_token(token) == expected


def test_blank_never_becomes_zero_in_type_mix(valid_csv: Path):
    prof = p.profile_csv(valid_csv)
    wk1 = {c.name: c for c in prof.columns}["Gt 01 To 02 Weeks SUM 1"]  # 3, 2, 0
    assert wk1.type_counts["empty"] == 0
    assert wk1.type_counts["int"] == 3
