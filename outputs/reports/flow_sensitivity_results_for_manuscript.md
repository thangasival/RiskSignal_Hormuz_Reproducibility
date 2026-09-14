# Physical-Flow Sensitivity Results for Manuscript

## Completed checks

- **216** outcome specifications: 4 training-only baselines, 6 shortfall thresholds, 3 persistence rules and 3 recovery rules.
- The 1 March target anchor falls inside a detected disruption interval in **216/216** specifications. A target-local onset (26 February or 1 March) is identified in **213/216**; **3** low-threshold specifications merge the target with a preceding episode.
- All **108/108** specifications with 50%–90% shortfall thresholds place major-to-catastrophic onset on **1 March 2026**.
- Pre-2024 selectivity improves sharply with severity: median background episode rates are **1.6/year at 50%**, **0.4/year at 70%**, and **0.0/year at 90%** across the corresponding 36 configurations per threshold. These are background detections, not labeled false positives, because the training period can contain real disruptions.
- The canonical 30%/two-day definition identifies early degradation on **26 February 2026**; requiring three or five consecutive days moves this stage to **1 March 2026**.
- Automated single-change-point dates are: **n_total=2026-03-02, n_tanker=2026-03-01, capacity=2026-03-02, capacity_tanker=2026-03-02**.
- A MARAD record (effective date) and a UKMTO advisory (issue date) are dated **28 February**, one daily observation interval before the major/catastrophic stage. This is case-specific escalation timing after initial degradation, not clean lead before all disruption.
- Under the canonical episode definition, E051 ranks first among 51 episodes on cumulative tanker-capacity loss and also ranks first on duration, severe days and maximum shortfall. These correlated ranks are descriptive only.

## Defensible claim

Across 108 training-only baseline and persistence/recovery specifications with 50%–90% shortfall thresholds, the major-disruption transition is invariant at 1 March 2026. MARAD and UKMTO records dated 28 February precede this escalation by one daily observation interval, after the canonical initial degradation has already begun.

## Claims that remain unsupported

- That the signals anticipated the initial 26 February degradation.
- That insurance signals provided pre-escalation lead time.
- That one-day escalation lead generalizes beyond E051.

## Required limitation

IMF PortWatch is an AIS-derived proxy. All vessel-count and capacity fields shift sharply near 1–2 March, while document evidence independently corroborates operational disruption. A PortWatch observation-regime break cannot be eliminated with this dataset alone and must be acknowledged explicitly.
