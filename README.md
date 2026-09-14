# RiskSignal: Evidence-Gated Energy-Supply Resilience at the Strait of Hormuz

Reproducibility release for the study **“Explainable AI for Energy-Supply Resilience at the Strait of Hormuz: Fusing Maritime Advisories, Insurance Signals, and Public Telemetry.”**

## Release status

This repository packages the offline analysis code, reviewed metadata, provenance hashes/URLs, derived physical-flow data used by the sensitivity analysis, final reports, and figures. It intentionally **does not redistribute third-party maritime advisories, insurer publications, web captures, or PDF evidence archives**.

The Phase 4 evidence gate is **BLOCKED**. The released outputs therefore do **not** claim improved calibration, generalized warning lead-time, or superior fusion performance. The file `outputs/reports/source_only_and_fusion_metrics.csv` is intentionally header-only because the gate prevented performance estimation.

## Key reproducible findings

- Reviewed Phase 4 metadata: 291 rows.
- Eleven unresolved positive/update mappings remain ineligible for verified historical-warning claims.
- Evidence gate: blocked; 3 independent clusters qualify versus a required minimum of 10.
- Flow-sensitivity analysis: E051 detected in 216/216 specifications.
- In the 108 specifications using 50%–90% shortfall thresholds, the major-to-catastrophic transition is dated 2026-03-01.
- MARAD/UKMTO signals dated 2026-02-28 are one day before that escalation, but after the canonical initial degradation on 2026-02-26; this is a single-case escalation result, not a generalized lead-time claim.

See `docs/RERUN_RESULTS_SUMMARY.md` for the exact interpretation.

## Repository layout

- `src/risksignal/` — offline analysis and registry code.
- `data/manual/` — pipeline-compatible reviewed metadata and adjudication tables.
- `data/provenance/` — source URLs, hashes, evidence IDs, and provenance metadata; no source documents.
- `data/processed/` — derived Strait of Hormuz physical-flow snapshot used by the sensitivity analysis.
- `outputs/reports/` — final CSV/JSON/Markdown results, including blocked-gate artifacts.
- `outputs/figures/` — final figures.
- `docs/` — rerun summary, pipeline changes, patch, hashes, and run notes.
- `release_templates/` — citation and Zenodo metadata templates to complete before a public archival release.

## Offline rerun

Create an environment and install dependencies:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Run the public-release analysis:

```bash
python run_pipeline.py
```

The default command reruns:

1. `phase4_evaluate`
2. `phase4_figures`
3. `flow_sensitivity`
4. `flow_sensitivity_figures`

No network collection/download stage is included in this release runner.

### Registry reconstruction limitation

`phase4_registry` is included for transparency, but a from-scratch registry reconstruction requires the original local third-party evidence corpus under `data/evidence/phase4/`. Those source documents are intentionally not distributed here. The release instead supplies the reviewed registry, coverage table, source-map hashes/URLs, and gate result used by the final evaluation.

Attempting `python run_pipeline.py --steps phase4_registry` without the local evidence corpus exits with an explanatory message.

## External source classes

The evidence-review layer covers public material from MARAD, UKMTO warnings/advisories, Joint War Committee/Lloyd's Market Association material, and Gard maritime-risk communications. The physical-flow sensitivity analysis uses a derived snapshot originating from IMF PortWatch Strait of Hormuz chokepoint telemetry. Third-party source documents remain subject to their original providers' terms and are not licensed by this repository.

## Review and historical-warning eligibility

Adjudication is authoritative in the released metadata. The 11 unresolved mappings are retained for auditability but carry an ineligible historical-warning claim status. Do not reinterpret them as verified pre-onset warning evidence.

## Anonymous review repository

For double-blind review, this release is mirrored through the anonymous review endpoint:

`https://anonymous.4open.science/r/RiskSignal_Hormuz_Reproducibility-FF67`

Do not expose author identities through repository ownership, citation metadata, ORCID, or Zenodo creator metadata before the venue permits de-anonymization.

## Licensing

- Code: MIT License (`LICENSE`).
- Original repository documentation: CC BY 4.0 where stated in `DATA_AND_CONTENT_LICENSE.md`.
- Third-party source material and source-derived data: not relicensed here; original provider terms apply.

## Citation / Zenodo

`release_templates/CITATION.cff.template` and `release_templates/.zenodo.json.template` contain placeholders. Fill the final author list and DOI only after confirming submission/public-release timing.
