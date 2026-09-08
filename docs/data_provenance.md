# Raw data provenance

Records what is **known** about each raw file. Contents of `data/raw/` are
git-ignored; this file is the tracked provenance record. Independent hashes
were confirmed by the Phase 1 audit (`docs/phase1_audit.md`).

## rtt_2026_06.csv — Phase 1 development dataset

| Attribute | Value |
|-----------|-------|
| Local path | `data/raw/rtt_2026_06.csv` |
| Size | 82,084,725 bytes (78.28 MiB) |
| SHA-256 | `edc3927e4a0065855ad3b2347e7f82688e687b065406eefb49e2f67a9cd67f02` |
| Physical lines | 182,412 (1 header + 182,411 data rows) |
| Columns | 121 |
| Encoding | UTF-8, **no BOM**; parses under strict `utf-8-sig` and `utf-8` |
| Period value | `RTT-June-2026` on every row |
| Source URL | **NOT SUPPLIED** — expected: NHS England RTT statistical work area, <https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/> |
| Download date/time | **NOT SUPPLIED** |
| Publisher / publication date | **NOT SUPPLIED** (NHS England; monthly RTT release) |
| Publication version / revision | **NOT SUPPLIED** (NHS revises prior months; revision status unknown) |

## rtt_2026_04.csv, rtt_2026_05.csv

Present in `data/raw/` but **out of scope for Phase 1** and not profiled. No
hashes or provenance recorded yet; to be captured if/when they enter scope.

## Open provenance actions (tracked in docs/assumptions.md)

- Obtain and record the exact source URL, download timestamp, NHS publication
  date, and whether the file is an original or revised release.
- Decide whether a machine-readable manifest (`data/raw/manifest.json`) is
  added; if so, generate it from this file so the two cannot drift.
