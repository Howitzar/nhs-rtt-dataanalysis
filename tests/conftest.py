"""Shared fixtures for the profiling tests.

Fixtures build **tiny** synthetic CSVs that imitate the shape of an NHS RTT
monthly extract (identifier columns + a short *contiguous* week-bucket
sequence + Total / unknown columns). No real NHS data is used or downloaded.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# A miniature RTT-like schema. The week buckets form a clean contiguous
# sequence (0-1, 1-2, 2-3) followed by one open-ended band (Gt 03 Weeks) whose
# lower bound matches — so a well-formed fixture is *structurally clean*.
HEADER = [
    "Period",
    "Provider Parent Org Code", "Provider Parent Name",
    "Provider Org Code", "Provider Org Name",
    "Commissioner Org Code", "Commissioner Org Name",
    "RTT Part Type", "RTT Part Description",
    "Treatment Function Code", "Treatment Function Name",
    "Gt 00 To 01 Weeks SUM 1", "Gt 01 To 02 Weeks SUM 1",
    "Gt 02 To 03 Weeks SUM 1", "Gt 03 Weeks SUM 1",
    "Total", "Patients with unknown clock start date", "Total All",
]
N_COLS = len(HEADER)  # 18

_ROWS = [
    ["RTT-April-2026", "QAA", "PARENT ICB A", "RAA", "PROVIDER ALPHA",
     "00A", "COMM ONE", "Part_2", "Incomplete Pathways",
     "C_100", "General Surgery Service", "5", "3", "", "1", "8", "1", "9"],
    ["RTT-April-2026", "QAA", "PARENT ICB A", "RAB", "PROVIDER BETA",
     "00A", "COMM ONE", "Part_2", "Incomplete Pathways",
     "C_110", "Trauma and Orthopaedic Service", "", "2", "1", "0", "3", "", "3"],
    ["RTT-April-2026", "QBB", "PARENT ICB B", "RAC", "PROVIDER GAMMA",
     "00B", "", "Part_1A", "Completed Pathways For Admitted Patients",
     "C_999", "Total", "10", "0", "0", "0", "10", "0", "10"],
]


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> Path:
    import csv

    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return path


@pytest.fixture
def valid_csv(tmp_path: Path) -> Path:
    """A well-formed miniature RTT extract, 3 distinct rows, no anomalies."""
    return _write_csv(tmp_path / "rtt_mini.csv", HEADER, _ROWS)


@pytest.fixture
def duplicated_csv(tmp_path: Path) -> Path:
    """As ``valid_csv`` but the first data row is repeated twice more."""
    rows = _ROWS + [list(_ROWS[0]), list(_ROWS[0])]
    return _write_csv(tmp_path / "rtt_dupes.csv", HEADER, rows)


@pytest.fixture
def near_duplicate_csv(tmp_path: Path) -> Path:
    """Two rows whose fields differ only by where a '|' sits across adjacent
    columns — a naive '|'.join serialisation would alias them; exact
    whole-row equality must not."""
    # Adjacent columns 3/4 (Provider Org Code / Name): moving the split point
    # across the '|' yields the SAME "|".join(row) string but different rows.
    a = list(_ROWS[0]); a[3] = "RAA|X"; a[4] = "Y"
    b = list(_ROWS[0]); b[3] = "RAA"; b[4] = "X|Y"
    return _write_csv(tmp_path / "rtt_near_dupe.csv", HEADER, [a, b])


@pytest.fixture
def header_only_csv(tmp_path: Path) -> Path:
    """A file with a header but zero data rows."""
    return _write_csv(tmp_path / "rtt_header_only.csv", HEADER, [])


@pytest.fixture
def truly_empty_csv(tmp_path: Path) -> Path:
    """A zero-byte file — no header at all."""
    p = tmp_path / "rtt_empty.csv"
    p.write_text("", encoding="utf-8")
    return p


@pytest.fixture
def no_identifiers_csv(tmp_path: Path) -> Path:
    """All columns are numeric buckets — no identifier columns bind."""
    header = ["Gt 00 To 01 Weeks SUM 1", "Gt 01 To 02 Weeks SUM 1", "Total"]
    rows = [["1", "2", "3"], ["4", "5", "9"]]
    return _write_csv(tmp_path / "rtt_no_ids.csv", header, rows)


@pytest.fixture
def name_collision_csv(tmp_path: Path) -> Path:
    """Two provider codes share one provider name (a real NHS pattern)."""
    a = list(_ROWS[0])
    b = list(_ROWS[1])
    b[3] = "RZZ"               # different Provider Org Code
    b[4] = "PROVIDER ALPHA"    # same Provider Org Name as row a
    return _write_csv(tmp_path / "rtt_name_collision.csv", HEADER, [a, b])


@pytest.fixture
def duplicate_header_csv(tmp_path: Path) -> Path:
    """`Provider Org Code` appears twice — role binding must refuse it."""
    header = list(HEADER)
    header[4] = "Provider Org Code"   # was 'Provider Org Name'
    return _write_csv(tmp_path / "rtt_dup_header.csv", header, [list(_ROWS[0])])


@pytest.fixture
def unterminated_quote_csv(tmp_path: Path) -> Path:
    """A row with broken quoting: text immediately after a closed quote."""
    good = ",".join(HEADER) + "\n"
    ok_row = ",".join(_ROWS[0]) + "\n"
    bad_row = '"PROVIDER"BROKEN,rest,of,line\n'
    p = tmp_path / "rtt_bad_quote.csv"
    p.write_text(good + ok_row + bad_row, encoding="utf-8")
    return p


@pytest.fixture
def bom_csv(tmp_path: Path) -> Path:
    """UTF-8 file with a leading BOM; utf-8-sig must strip it."""
    p = tmp_path / "rtt_bom.csv"
    body = ",".join(HEADER) + "\n" + ",".join(_ROWS[0]) + "\n"
    p.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    return p


@pytest.fixture
def ragged_csv(tmp_path: Path) -> Path:
    """One row is three fields short of the header width."""
    short = list(_ROWS[0])[:-3]
    return _write_csv(tmp_path / "rtt_ragged.csv", HEADER, [list(_ROWS[1]), short])
