# RiskSignal: Evidence-Gated AI Evaluation for Energy-Supply Resilience at the Strait of Hormuz

Anonymous reproducibility release for the ICASF 2027 study **“Evidence-Gated AI Evaluation for Energy-Supply Resilience at the Strait of Hormuz.”**

## Release status

This repository packages the offline analysis code, adjudicated metadata, provenance hashes/URLs, derived physical-flow data, reports, and figures. It intentionally **does not redistribute third-party maritime advisories, insurer publications, web captures, or PDF evidence archives**.

The Phase 4 evidence gate is **BLOCKED**. The released outputs therefore do not claim improved calibration, generalized warning lead time, or superior fusion performance. `outputs/reports/source_only_and_fusion_metrics.csv` is intentionally header-only because the evidence gate prevented performance estimation.

## Key reproducible findings

- Phase 4 registry: 291 metadata rows; 11 unresolved positive/update mappings remain ineligible for verified historical-warning claims.
- Evidence gate: blocked; 3 independent clusters qualify versus a required minimum of 10.
- Gate-policy sensitivity: all 9 combinations of 75%/90%/100% episode coverage and 3/5/10 independent-cluster floors remain blocked when zero unresolved historical-warning mappings is retained.
- Naive-vs-gated ablation: a timestamp-only rule admits 10 apparent pre-onset records across 6 clusters; successive evidence-validity controls leave 1 clean pre-onset signal in 1 cluster.
- Flow sensitivity: the 1 March 2026 anchor lies inside a detected interval in 216/216 specifications; a target-local E051 onset is identifiable in 213/216. Three 20%/long-recovery specifications merge E051 with a prior episode.
- All 108 specifications using 50%–90% shortfall thresholds identify the major-to-catastrophic transition on 1 March 2026.
- Pre-2024 background selectivity: median detected episodes/year is 1.6 at 50%, 0.4 at 70%, and 0 at 90% shortfall. These are background detections, not labeled false positives.
- A MARAD record (effective date) and UKMTO advisory (issue date) are dated 28 February, one daily observation interval before the 1 March escalation and after the 26 February initial degradation. This is case-specific escalation timing, not generalized lead time.

See `docs/RERUN_RESULTS_SUMMARY.md` and `outputs/reports/flow_sensitivity_results_for_manuscript.md` for the exact interpretation.

## Repository layout

- `src/risksignal/` — offline analysis and registry code.
- `data/manual/` — pipeline-compatible adjudicated metadata and review tables.
- `data/provenance/` — source URLs, hashes, evidence IDs, and provenance metadata; no source documents.
- `data/processed/` — derived Strait of Hormuz physical-flow snapshot used by the sensitivity analysis.
- `outputs/reports/` — CSV/JSON/Markdown results, including blocked-gate and background-selectivity artifacts.
- `outputs/figures/` — paper figures plus Phase 4 diagnostic figures.
- `docs/` — rerun summary, pipeline changes, hashes, and run notes.
- `release_templates/` — citation and Zenodo templates for a post-review public archival release.

## Offline rerun

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python run_pipeline.py
```

The default command reruns `phase4_evaluate`, `gate_robustness`, `phase4_figures`, `flow_sensitivity`, and `flow_sensitivity_figures`. No network collection or download stage is included.

### Registry reconstruction limitation

`phase4_registry` is included for transparency, but a from-scratch registry reconstruction requires the original local third-party evidence corpus under `data/evidence/phase4/`. Those source documents are intentionally not distributed. The release instead supplies the adjudicated registry, coverage table, source-map hashes/URLs, and gate result used by the evaluation.

Attempting `python run_pipeline.py --steps phase4_registry` without that local evidence corpus exits with an explanatory message.

## External source classes

The evidence layer covers public material from MARAD, UKMTO warnings/advisories, Joint War Committee/Lloyd's Market Association material, and Gard maritime-risk communications. The physical-flow sensitivity analysis uses a derived snapshot originating from IMF PortWatch Strait of Hormuz chokepoint telemetry. Third-party source documents remain subject to their original providers' terms and are not licensed by this repository.

## Historical-warning eligibility

Adjudication is authoritative in the released metadata. The 11 unresolved mappings are retained for auditability but carry an ineligible historical-warning claim status. Do not reinterpret them as verified pre-onset warning evidence.

## Anonymous review repository

`https://anonymous.4open.science/r/RiskSignal_Hormuz_Reproducibility-FF67`

Do not expose author identities through repository ownership, citation metadata, ORCID, or Zenodo creator metadata before the venue permits de-anonymization.

## Licensing

- Code: MIT License (`LICENSE`).
- Original repository documentation: CC BY 4.0 where stated in `DATA_AND_CONTENT_LICENSE.md`.
- Third-party source material and source-derived data: not relicensed here; original provider terms apply.

## Citation / Zenodo

`release_templates/CITATION.cff.template` and `release_templates/.zenodo.json.template` intentionally retain anonymous placeholders. Complete author and DOI metadata only after double-blind review permits de-anonymization.
