# Raw data provenance

Records what is **known** about each raw file. Contents of `data/raw/` are
git-ignored; this file is the tracked prose provenance record. Independent
hashes were confirmed by the Phase 1 audit (`docs/phase1_audit.md`) and, for
April/May, by the Phase 3 ingestion run (`docs/phase3_ingestion.md`).

**Machine-readable registry:** `data/raw/manifest.json` (tracked) is the
authoritative *intended source set* consumed by `nhs_rtt.ingest` — reporting
period, filename, SHA-256, `selected` flag, optional revision note. This
document and the manifest must agree; the manifest is what code reads.

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

## rtt_2026_05.csv — Phase 3 cross-month validation

| Attribute | Value |
|-----------|-------|
| Local path | `data/raw/rtt_2026_05.csv` |
| Size | 80,032,366 bytes |
| SHA-256 | `fee364bc3654cf666f79d3485d26e2ada649a3418988a47aa1784e93294a5707` |
| Physical lines | 178,172 (1 header + 178,171 data rows) |
| Columns | 121 (header byte-identical to June) |
| Period value | `RTT-May-2026` on every row |
| Schema / candidate key | passes the frozen `validate_extract` 105-band gate; candidate key unique + `usable` |
| Source URL / download time / publication date / revision status | **NOT SUPPLIED** (as June) |

## rtt_2026_04.csv — Phase 3 cross-month validation

| Attribute | Value |
|-----------|-------|
| Local path | `data/raw/rtt_2026_04.csv` |
| Size | 81,624,872 bytes |
| SHA-256 | `0486aca5891a96af4f15e2f4559795138baef08b0ed580602b8c3a7aec6a56e9` |
| Physical lines | 180,782 (1 header + 180,781 data rows) |
| Columns | 121 (header byte-identical to June) |
| Period value | `RTT-April-2026` on every row |
| Schema / candidate key | passes the frozen `validate_extract` 105-band gate; candidate key unique + `usable` |
| Source URL / download time / publication date / revision status | **NOT SUPPLIED** (as June) |

## Open provenance actions (tracked in docs/assumptions.md)

- Obtain and record, per file, the exact source URL, download timestamp, NHS
  publication date, and whether the file is an original or revised release.
  These are `null` in `data/raw/manifest.json` — **not fabricated**.
- The machine-readable manifest now exists (`data/raw/manifest.json`); keep it
  and this document in agreement.
