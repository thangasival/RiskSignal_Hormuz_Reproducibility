# RiskSignal ICASF 2027 — Offline Rerun Summary

## Evidence gate

Status: **BLOCKED**

| Requirement | Observed | Minimum / required | Result |
| --- | ---: | ---: | :---: |
| Eligible independent clusters | 3 | 10 | Fail |
| Eligible temporal-test clusters | 3 | 3 | Pass |
| Direct source classes | 5 | 2 | Pass |
| Unresolved historical-warning mappings | 11 | 0 | Fail |

The registry contains 291 metadata rows: 247 with local evidence and 44 metadata-reference-only rows. Complete clusters are E038, E042 and E045. E051 is 7/8 on required source-window coverage (87.5%), below the 90% threshold. Source-only/fusion metrics remain intentionally empty and the cluster-bootstrap report remains blocked.

## Gate robustness and evidence ablation

- Gate-policy sensitivity crossed episode-coverage floors of 75%, 90% and 100% with independent-cluster floors of 3, 5 and 10 while preserving the requirements of at least 3 temporal-test clusters, at least 2 direct source classes and 0 unresolved historical-warning mappings. All 9 policies remain **BLOCKED**.
- At 75% coverage, at most 4 independent clusters qualify; at 90% and 100%, 3 qualify. Even the most permissive tested policy (75% coverage; 3 clusters) remains blocked by the 11 unresolved historical-warning mappings.
- A timestamp-only naive rule admits 10 apparent pre-onset positive/update records across 6 episode clusters and 9 signal families. Requiring local evidence reduces this to 6 records/3 clusters; removing updates to 5/3; requiring verified historical availability to 2/2; excluding overlap with another active flow episode leaves 1 clean pre-onset record in 1 cluster.
- These outputs are in `gate_policy_sensitivity.csv` and `naive_vs_evidence_gated_ablation.csv`.

## Physical-flow sensitivity and selectivity

- 216 outcome specifications were evaluated.
- The 1 March 2026 target anchor lies inside a detected interval in 216/216 specifications.
- A target-local E051 onset on or after 26 February is identifiable in 213/216; three 20% specifications using the month-by-weekday baseline and seven-day recovery merge E051 with a prior episode.
- All 108 specifications using 50%–90% shortfall thresholds identify onset on 1 March 2026.
- Pre-2024 median background detections are 1.6/year at 50%, 0.4/year at 70%, and 0/year at 90%. These are background detections rather than labeled false positives.
- The canonical 30%/two-day definition identifies initial degradation on 26 February.
- The MARAD record uses a 28 February effective date; the UKMTO advisory uses a 28 February issue date. Both precede the 1 March escalation by one daily observation interval, after initial degradation has begun.

## Authorized interpretation

The rerun supports a specification-robust severe E051 transition and case-specific documentary timing relative to that later stage. It does not authorize generalized warning lead time, improved calibration, source-fusion performance, insurance-signal lead time, or claims that MARAD/UKMTO outperform alternative indicators.
