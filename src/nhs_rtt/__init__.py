"""nhs_rtt — reproducible ingestion and validation pipeline for NHS RTT waiting-times data."""

__version__ = "0.1.0"

# Nominal development month. The Phase 1 brief first said "April 2025"; the
# corrected instruction is to use the single supplied June 2026 file.
# Primary development dataset for Phase 1: data/raw/rtt_2026_06.csv.
# See docs/decisions.md, D-001.
DEV_MONTH = "2026-06"
