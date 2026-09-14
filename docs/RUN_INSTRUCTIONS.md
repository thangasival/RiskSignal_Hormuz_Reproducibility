# RiskSignal ICASF 2027 — Offline Reviewed-Metadata Rerun

## Rule: do not recollect evidence

This release is designed for an **offline rerun**. Do not run `phase4_collect`, Playwright collectors, Apify collectors, `portwatch`, or any other network-collection step when reproducing the reported results.

## Inputs used

Primary inputs:

- `RiskSignal_Public_Data_Pipeline_Phase4_v1.0.3.zip`
- `RiskSignal_Phase4_Review_Mappings_Updated.xlsx`

Existing Library evidence archives used to reconstruct the local evidence root without network access:

- `phase4.zip`
- `MARAD.zip`
- `Shared.zip`
- `UKMTO(1).zip`
- `E031.zip`
- `E051_Final_Evidence_Package.zip`

The reviewed metadata intentionally remains valid when an original reviewed artifact is unavailable locally: the row is retained as metadata-reference-only and is excluded from direct evidence coverage.

## Apply the reviewed overlay

Starting from the v1.0.3 pipeline, replace/copy these files from this release:

- `data/manual/phase4_evidence_metadata.csv`
- `data/manual/phase4_review_decisions.csv`
- `data/manual/phase4_coverage_review.csv`
- `data/manual/phase4_source_map_reviewed.csv`
- `src/risksignal/build_multi_episode_registry.py`
- `src/risksignal/make_phase4_figures.py`

If reconstructing the same local evidence state, extract the six existing evidence archives listed above into `data/evidence/phase4/` with overwrite enabled. Do not download replacements.

## Python environment

From the project root:

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Exact final rerun

Run only the requested local stages:

```bash
python run_pipeline.py --steps \
  phase4_registry \
  phase4_evaluate \
  phase4_figures \
  flow_sensitivity \
  flow_sensitivity_figures
```

Equivalent module commands are:

```bash
python -m risksignal.build_multi_episode_registry
python -m risksignal.evaluate_multi_episode
python -m risksignal.make_phase4_figures
python -m risksignal.evaluate_flow_sensitivity
python -m risksignal.make_flow_sensitivity_figures
```

`flow_sensitivity` expects the previously validated local `outputs/reports/e051_evidence_registry.csv` prerequisite that is part of the v1.0.3 project state. Do not delete it unless you intend to rebuild the E051 evidence registry from the already-local evidence files.

## Expected gate result

The expected `outputs/reports/evidence_coverage_gate.json` status is `blocked`, with:

- 3 eligible independent clusters
- 3 eligible temporal-test clusters
- 5 direct source classes
- 11 unresolved historical-warning mappings
- 291 registered metadata rows
- 247 physical local evidence rows
- 44 metadata-reference-only rows

`source_only_and_fusion_metrics.csv` should contain only its header. `episode_cluster_bootstrap.json` should report `status: blocked`.

## Expected flow-sensitivity result

`flow_sensitivity_results_for_manuscript.md` should report 216/216 anchor-interval captures, 213/216 target-local onsets, three low-threshold mergers, and 108/108 specifications at 50%-90% with onset on 2026-03-01. `pre2024_background_selectivity.csv` should also be regenerated.


