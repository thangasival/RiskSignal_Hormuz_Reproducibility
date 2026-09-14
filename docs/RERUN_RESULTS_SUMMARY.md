# RiskSignal ICASF 2027 — Final Offline Rerun Summary

## Evidence conversion

- Pipeline metadata rows: **291**
- Preserved prior metadata rows: **203**
- Newly adjudicated mappings: **88**
- Physical local evidence rows: **247**
- Metadata-reference-only rows: **44**
- Unresolved positive/update historical-warning mappings kept ineligible: **11**

## Phase 4 gate

Status: **BLOCKED**

| Requirement | Observed | Minimum / required | Result |
| --- | ---: | ---: | :---: |
| Eligible independent clusters | 3 | 10 | Fail |
| Eligible temporal-test clusters | 3 | 3 | Pass |
| Direct source classes | 5 | 2 | Pass |
| Unresolved historical-warning mappings | 11 | 0 | Fail |

Complete clusters are E038, E042 and E045. E051 is 7/8 on required source-window coverage (87.5%), below the 90% threshold. The source-only/fusion metrics file is intentionally empty and the cluster-bootstrap report is `blocked`.

## Physical-flow sensitivity

- Outcome specifications: **216**
- E051 detected: **216/216**
- Specifications using 50%-90% shortfall thresholds: **108/108** place the major-to-catastrophic transition on **2026-03-01**.
- Canonical 30% / two-consecutive-day definition places early degradation on **2026-02-26**.
- MARAD and UKMTO contribute two signal families dated **2026-02-28**, one day before the 1 March major/catastrophic stage.
- This is **escalation lead**, not lead before the initial 26 February degradation.
- E051 ranks first among 51 telemetry-defined episodes for duration, severe days, cumulative tanker-capacity loss and maximum shortfall; the descriptive rank tail is 1/51 = 0.0196 for each metric.

## Claims authorized by this rerun

The rerun supports a robust E051 major-disruption transition and a one-day single-case escalation lead for MARAD/UKMTO relative to that transition.

## Claims not authorized

The rerun does **not** authorize claims of generalized warning lead time, improved calibration, source-fusion performance, insurance-signal lead time, or prediction of physical disruption by the legacy Brent-stress classifier.
