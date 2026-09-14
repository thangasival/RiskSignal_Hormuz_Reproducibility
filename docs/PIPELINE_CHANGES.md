# Phase 4 Reviewed-Metadata Pipeline Changes

## Scope

This update is a conservative overlay on `RiskSignal_Public_Data_Pipeline_Phase4_v1.0.3.zip`. It converts the human-reviewed workbook into pipeline metadata and makes historical-warning eligibility an explicit gate. It does **not** add or recollect evidence.

## Metadata changes

`data/manual/phase4_evidence_metadata.csv` now contains 291 rows:

- 203 rows preserved from the workbook `Existing_Metadata` sheet.
- 88 rows converted from the workbook `Document_Review` sheet.
- 247 rows have a physically available local evidence artifact in the reconstructed existing-evidence root.
- 44 rows are retained as `metadata_reference_only`; they do not count as direct physical evidence.
- 11 accepted positive/update mappings are marked `ineligible_unresolved_historical_availability` and cannot support verified historical-warning claims.

Additional audit fields preserve review provenance: `evidence_storage_type`, `review_origin`, `review_id`, `evidence_id`, both reviewer decisions, historical-availability status, prior-episode overlap status, review action, claim eligibility, and the original representative path.

Separate exports preserve the workbook review layers:

- `data/manual/phase4_review_decisions.csv`
- `data/manual/phase4_coverage_review.csv`
- `data/manual/phase4_source_map_reviewed.csv`

## Registry logic changes

`src/risksignal/build_multi_episode_registry.py` now:

1. Retains metadata-reference-only rows without treating them as present evidence.
2. Adds `evidence_present` and evidence-storage/provenance fields to the registry.
3. Treats `excluded` records as audit-only records, not positive signals.
4. Requires a signal family and timing date only for warning claims that are actually eligible.
5. Requires local evidence presence, historical eligibility, direct-source status, accepted review, pre-onset timing, and clear prior-episode overlap before a row can become `clean_pre_onset_signal`.
6. Excludes missing evidence from required-source coverage.
7. Counts unresolved positive/update mappings as `historical_warning_eligibility_issues` at episode level.
8. Makes zero unresolved historical-warning mappings a global gate requirement.
9. Reports physical-evidence rows, metadata-reference-only rows, and unresolved historical-warning mappings explicitly.

## Figure logic change

`src/risksignal/make_phase4_figures.py` now prints the unresolved historical-warning mapping count on the blocked fusion-comparison figure and states that historical-availability evidence must be completed before performance estimation.

## Deliberately unchanged

- Evidence-gate thresholds remain 10 independent clusters, 3 temporal-test clusters, and 90% required episode coverage.
- The Phase 4 evaluator still writes empty source/fusion metrics when the gate is blocked.
- The flow-sensitivity methodology and thresholds are unchanged.
- No collection backend was executed.
- No unresolved date or historical-availability field was imputed.

See `PHASE4_REVIEWED_PIPELINE_CHANGES.patch` for the exact source diff.
