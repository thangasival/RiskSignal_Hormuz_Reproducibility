from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Any

import pandas as pd

from .prepare_phase4_collection import build_tasks
from .utils import ensure_dirs, load_config, project_root, write_json


REGISTRY_COLUMNS = [
    "task_id", "episode_cluster_id", "flow_episode_id", "phase4_split", "dependency_group",
    "relative_path", "sha256", "size_bytes", "evidence_present", "evidence_storage_type",
    "source_class", "document_id", "signal_family_id", "document_role", "evidence_date",
    "issue_date", "publication_date", "effective_date", "expiry_date", "geographic_scope",
    "window_type", "is_zero_result_capture", "is_direct_official", "is_update", "parent_family_id",
    "reviewer_1", "reviewer_2", "adjudication_status", "notes", "review_origin", "review_id",
    "evidence_id", "reviewer_1_decision", "reviewer_2_decision", "historical_availability_status",
    "prior_episode_overlap_status", "review_action", "claim_eligibility_status",
    "onset_date", "days_from_onset", "active_flow_episode_id", "clean_pre_onset_signal",
    "independent_episode_unit",
]

COVERAGE_ROLES = {"positive_signal", "update", "zero_result_capture"}
AUDIT_ROLES_WITHOUT_SIGNAL = {
    "archive_capture", "archive_capture_pending_classification", "methodology", "access_limitation",
    "candidate_document_pending_classification", "excluded",
}


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _truth(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _best_date(row: pd.Series) -> pd.Timestamp | None:
    for column in ["publication_date", "issue_date", "effective_date"]:
        value = pd.to_datetime(row.get(column), errors="coerce")
        if pd.notna(value):
            return pd.Timestamp(value).normalize()
    return None


def build_registry(
    manifest: pd.DataFrame,
    metadata: pd.DataFrame,
    evidence_root: Path,
    all_flow_episodes: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if metadata.empty:
        return pd.DataFrame(columns=REGISTRY_COLUMNS)
    tasks = build_tasks(manifest)
    valid_tasks = set(tasks["task_id"])
    records: list[dict[str, Any]] = []
    manifest_index = manifest.set_index("episode_cluster_id")
    for index, row in metadata.iterrows():
        task_id = str(row.get("task_id", "")).strip()
        if task_id not in valid_tasks:
            raise ValueError(f"Metadata row {index + 2} has an unknown task_id: {task_id}")
        cluster = str(row.get("episode_cluster_id", "")).strip()
        if cluster not in manifest_index.index:
            raise ValueError(f"Metadata row {index + 2} has an unknown episode_cluster_id: {cluster}")
        task = tasks.loc[tasks["task_id"].eq(task_id)].iloc[0]
        if cluster != task["episode_cluster_id"]:
            raise ValueError(f"Metadata row {index + 2} task and episode IDs disagree")
        coded_source = str(row.get("source_class", "")).strip()
        if coded_source and coded_source != task["source_class"]:
            raise ValueError(f"Metadata row {index + 2} source_class disagrees with its task")
        coded_window = str(row.get("window_type", "")).strip()
        if coded_window and coded_window != task["window_type"]:
            raise ValueError(f"Metadata row {index + 2} window_type disagrees with its task")
        relative = str(row.get("relative_path", "")).strip().replace("\\", "/")
        path = evidence_root / relative
        try:
            path.resolve().relative_to(evidence_root.resolve())
        except ValueError as exc:
            raise ValueError(f"Metadata row {index + 2} points outside the Phase 4 evidence root") from exc
        evidence_present = bool(relative and path.is_file())
        if evidence_present and path.name == "PLACE_EVIDENCE_HERE.txt":
            raise ValueError("Placeholder files cannot be registered as evidence")
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if evidence_present else ""
        evidence_date = _best_date(row)
        episode = manifest_index.loc[cluster]
        onset = pd.Timestamp(episode["onset_date"]).normalize()
        zero = _truth(row.get("is_zero_result_capture"))
        update = _truth(row.get("is_update"))
        direct = _truth(row.get("is_direct_official"))
        family = str(row.get("signal_family_id", "")).strip()
        role = str(row.get("document_role", "")).strip()
        status = str(row.get("adjudication_status", "")).strip().lower()
        claim_eligibility = str(row.get("claim_eligibility_status", "")).strip().lower()
        historical_warning_eligible = role in {"positive_signal", "update"} and claim_eligibility in {"eligible", "legacy_accepted"}
        if historical_warning_eligible and not family:
            raise ValueError(f"Metadata row {index + 2} requires signal_family_id for an eligible positive document")
        if historical_warning_eligible and evidence_date is None:
            raise ValueError(f"Metadata row {index + 2} requires issue/publication/effective date for an eligible claim")
        if historical_warning_eligible and evidence_date is not None and not (
            pd.Timestamp(task["date_from"]) <= evidence_date <= pd.Timestamp(task["date_to"])
        ):
            raise ValueError(f"Metadata row {index + 2} eligible signal date falls outside its fixed task window")
        if update and not str(row.get("parent_family_id", "")).strip():
            raise ValueError(f"Metadata row {index + 2} marks an update without parent_family_id")
        active_flow_episode_id: int | None = None
        if evidence_date is not None and all_flow_episodes is not None and not all_flow_episodes.empty:
            active = all_flow_episodes.loc[
                all_flow_episodes["start_date"].le(evidence_date)
                & all_flow_episodes["end_date"].ge(evidence_date)
            ]
            if not active.empty:
                active_flow_episode_id = int(active.iloc[0]["flow_episode_id"])
        overlap_status = str(row.get("prior_episode_overlap_status", "")).strip().lower()
        overlap_clear = overlap_status in {"clear", "legacy_reviewed", "not_applicable", ""}
        clean = bool(
            evidence_present and historical_warning_eligible and not zero and direct and not update
            and status == "accepted" and evidence_date is not None
            and pd.Timestamp(task["date_from"]) <= evidence_date <= pd.Timestamp(task["date_to"])
            and task["window_type"] == "pre_onset" and evidence_date < onset
            and active_flow_episode_id is None and overlap_clear
        )
        records.append({
            "task_id": task_id,
            "episode_cluster_id": cluster,
            "flow_episode_id": int(episode["flow_episode_id"]),
            "phase4_split": episode["phase4_split"],
            "dependency_group": episode["dependency_group"],
            "relative_path": relative,
            "sha256": digest,
            "size_bytes": path.stat().st_size if evidence_present else 0,
            "evidence_present": evidence_present,
            "evidence_storage_type": str(row.get("evidence_storage_type", "")).strip() or ("local_original" if evidence_present else "metadata_reference_only"),
            "source_class": task["source_class"],
            "document_id": str(row.get("document_id", "")).strip() or digest[:16],
            "signal_family_id": family,
            "document_role": role,
            "evidence_date": evidence_date,
            "issue_date": pd.to_datetime(row.get("issue_date"), errors="coerce"),
            "publication_date": pd.to_datetime(row.get("publication_date"), errors="coerce"),
            "effective_date": pd.to_datetime(row.get("effective_date"), errors="coerce"),
            "expiry_date": pd.to_datetime(row.get("expiry_date"), errors="coerce"),
            "geographic_scope": str(row.get("geographic_scope", "")).strip(),
            "window_type": task["window_type"],
            "is_zero_result_capture": zero,
            "is_direct_official": direct,
            "is_update": update,
            "parent_family_id": str(row.get("parent_family_id", "")).strip(),
            "reviewer_1": str(row.get("reviewer_1", "")).strip(),
            "reviewer_2": str(row.get("reviewer_2", "")).strip(),
            "adjudication_status": status,
            "notes": str(row.get("notes", "")).strip(),
            "review_origin": str(row.get("review_origin", "")).strip(),
            "review_id": str(row.get("review_id", "")).strip(),
            "evidence_id": str(row.get("evidence_id", "")).strip(),
            "reviewer_1_decision": str(row.get("reviewer_1_decision", "")).strip(),
            "reviewer_2_decision": str(row.get("reviewer_2_decision", "")).strip(),
            "historical_availability_status": str(row.get("historical_availability_status", "")).strip(),
            "prior_episode_overlap_status": str(row.get("prior_episode_overlap_status", "")).strip(),
            "review_action": str(row.get("review_action", "")).strip(),
            "claim_eligibility_status": str(row.get("claim_eligibility_status", "")).strip(),
            "onset_date": onset,
            "days_from_onset": None if evidence_date is None else int((evidence_date - onset).days),
            "active_flow_episode_id": active_flow_episode_id,
            "clean_pre_onset_signal": clean,
            "independent_episode_unit": episode["dependency_group"],
        })
    registry = pd.DataFrame(records, columns=REGISTRY_COLUMNS)
    return registry


def coverage_table(manifest: pd.DataFrame, tasks: pd.DataFrame, registry: pd.DataFrame) -> pd.DataFrame:
    accepted = registry.loc[
        registry["evidence_present"]
        & registry["is_direct_official"]
        & registry["adjudication_status"].isin(["accepted", "not_required"])
        & registry["document_role"].isin(COVERAGE_ROLES)
    ] if not registry.empty else registry
    completed = set(accepted["task_id"]) if not accepted.empty else set()
    rows: list[dict[str, Any]] = []
    for episode in manifest.itertuples(index=False):
        subset = tasks.loc[tasks["episode_cluster_id"].eq(episode.episode_cluster_id)]
        required = []
        for window in ["pre_onset", "onset"]:
            for source in ["MARAD", "UKMTO_WARNING", "UKMTO_ADVISORY"]:
                required.append(f"{episode.episode_cluster_id}_{source}_{window}")
            insurance = [
                f"{episode.episode_cluster_id}_IUA_JWC_LMA_{window}",
                f"{episode.episode_cluster_id}_GARD_{window}",
            ]
            required.append(next((task for task in insurance if task in completed), insurance[0]))
        completed_required = sum(task in completed for task in required)
        positive_families = 0
        clean_families = 0
        unresolved = 0
        double_coding_issues = 0
        historical_warning_eligibility_issues = 0
        if not registry.empty:
            episode_records = registry.loc[registry["episode_cluster_id"].eq(episode.episode_cluster_id)]
            positives = episode_records.loc[
                episode_records["evidence_present"]
                & episode_records["document_role"].eq("positive_signal")
                & ~episode_records["is_zero_result_capture"]
                & ~episode_records["is_update"]
                & episode_records["adjudication_status"].eq("accepted")
            ]
            positive_families = int(positives["signal_family_id"].replace("", pd.NA).nunique())
            clean_families = int(positives.loc[positives["clean_pre_onset_signal"], "signal_family_id"].nunique())
            unresolved = int((~episode_records["adjudication_status"].isin(["accepted", "not_required"])).sum())
            positive_pre = episode_records.loc[
                episode_records["document_role"].eq("positive_signal")
                & ~episode_records["is_zero_result_capture"]
                & episode_records["window_type"].eq("pre_onset")
                & ~episode_records["is_update"]
                & episode_records["adjudication_status"].eq("accepted")
            ]
            double_coding_issues = int((
                positive_pre["reviewer_1"].eq("")
                | positive_pre["reviewer_2"].eq("")
                | positive_pre["reviewer_1"].eq(positive_pre["reviewer_2"])
            ).sum())
            historical_warning_eligibility_issues = int((
                episode_records["document_role"].isin(["positive_signal", "update"])
                & episode_records["adjudication_status"].eq("accepted")
                & ~episode_records["claim_eligibility_status"].str.lower().isin(["eligible", "legacy_accepted"])
            ).sum())
        rows.append({
            "episode_cluster_id": episode.episode_cluster_id,
            "phase4_split": episode.phase4_split,
            "dependency_group": episode.dependency_group,
            "total_collection_tasks": int(len(subset)),
            "completed_collection_tasks": int(subset["task_id"].isin(completed).sum()),
            "required_coverage_units": len(required),
            "completed_required_units": completed_required,
            "required_coverage_fraction": completed_required / len(required),
            "positive_signal_families": positive_families,
            "clean_pre_onset_families": clean_families,
            "unresolved_metadata_rows": unresolved,
            "double_coding_issues": double_coding_issues,
            "historical_warning_eligibility_issues": historical_warning_eligibility_issues,
            "episode_complete": completed_required == len(required) and unresolved == 0 and double_coding_issues == 0 and historical_warning_eligibility_issues == 0,
        })
    return pd.DataFrame(rows)


def evaluate_gate(coverage: pd.DataFrame, registry: pd.DataFrame, cfg: dict[str, Any]) -> dict[str, Any]:
    minimum_clusters = int(cfg.get("minimum_independent_clusters", 10))
    minimum_test = int(cfg.get("minimum_test_clusters", 3))
    minimum_coverage = float(cfg.get("minimum_episode_coverage", 0.90))
    eligible = coverage.loc[
        coverage["required_coverage_fraction"].ge(minimum_coverage)
        & coverage["unresolved_metadata_rows"].eq(0)
        & coverage["double_coding_issues"].eq(0)
        & coverage["historical_warning_eligibility_issues"].eq(0)
    ]
    independent = int(eligible["dependency_group"].nunique())
    test_clusters = int(eligible.loc[eligible["phase4_split"].eq("test"), "dependency_group"].nunique())
    source_classes = int(registry.loc[
        registry["evidence_present"]
        & registry["is_direct_official"]
        & registry["adjudication_status"].isin(["accepted", "not_required"])
        & registry["document_role"].isin(COVERAGE_ROLES),
        "source_class",
    ].nunique()) if not registry.empty else 0
    unresolved_historical = int(coverage["historical_warning_eligibility_issues"].sum())
    checks = {
        "minimum_independent_episode_clusters": independent >= minimum_clusters,
        "minimum_temporal_test_clusters": test_clusters >= minimum_test,
        "minimum_two_direct_source_classes": source_classes >= 2,
        "no_unresolved_metadata_in_eligible_clusters": bool(
            eligible["unresolved_metadata_rows"].eq(0).all()
            and eligible["double_coding_issues"].eq(0).all()
            and eligible["historical_warning_eligibility_issues"].eq(0).all()
        ),
        "no_unresolved_historical_warning_mappings": unresolved_historical == 0,
    }
    return {
        "status": "pass" if all(checks.values()) else "blocked",
        "checks": checks,
        "thresholds": {
            "minimum_independent_clusters": minimum_clusters,
            "minimum_test_clusters": minimum_test,
            "minimum_episode_coverage": minimum_coverage,
        },
        "observed": {
            "eligible_independent_clusters": independent,
            "eligible_test_clusters": test_clusters,
            "direct_source_classes": source_classes,
            "registered_evidence_rows": int(len(registry)),
            "physical_evidence_rows": int(registry["evidence_present"].sum()) if not registry.empty else 0,
            "metadata_reference_only_rows": int((~registry["evidence_present"]).sum()) if not registry.empty else 0,
            "unresolved_historical_warning_mappings": unresolved_historical,
        },
        "interpretation": "Physical-onset fusion evaluation is authorized only when status is pass.",
    }


def render_readiness_report(coverage: pd.DataFrame, gate: dict[str, Any]) -> str:
    observed = gate["observed"]
    thresholds = gate["thresholds"]
    authorized = gate["status"] == "pass"
    lines = [
        "# Phase 4 Scientific-Readiness Report",
        "",
        "## Decision",
        "",
        (
            "The multi-episode fusion evaluation is **authorized**."
            if authorized
            else "The multi-episode fusion evaluation is **not authorized** because the evidence gate is blocked."
        ),
        "",
        "## Gate status",
        "",
        "| Requirement | Observed | Minimum | Passed |",
        "| --- | ---: | ---: | :---: |",
        (
            f"| Independent episode clusters | {observed['eligible_independent_clusters']} | "
            f"{thresholds['minimum_independent_clusters']} | "
            f"{'Yes' if gate['checks']['minimum_independent_episode_clusters'] else 'No'} |"
        ),
        (
            f"| Temporal-test clusters | {observed['eligible_test_clusters']} | "
            f"{thresholds['minimum_test_clusters']} | "
            f"{'Yes' if gate['checks']['minimum_temporal_test_clusters'] else 'No'} |"
        ),
        (
            f"| Direct source classes | {observed['direct_source_classes']} | 2 | "
            f"{'Yes' if gate['checks']['minimum_two_direct_source_classes'] else 'No'} |"
        ),
        "",
        "## Episode status",
        "",
        "| Episode | Split | Required coverage | Double-coding issues | Historical-warning issues | Clean pre-onset families | Complete |",
        "| --- | --- | ---: | ---: | ---: | ---: | :---: |",
    ]
    for row in coverage.itertuples(index=False):
        lines.append(
            f"| {row.episode_cluster_id} | {row.phase4_split} | "
            f"{row.completed_required_units}/{row.required_coverage_units} "
            f"({100 * row.required_coverage_fraction:.1f}%) | {row.double_coding_issues} | "
            f"{row.historical_warning_eligibility_issues} | {row.clean_pre_onset_families} | "
            f"{'Yes' if row.episode_complete else 'No'} |"
        )
    lines.extend([
        "",
        "## Interpretation",
        "",
        f"Registered metadata rows: **{observed['registered_evidence_rows']}**; physical local evidence rows: **{observed['physical_evidence_rows']}**; metadata-reference-only rows: **{observed['metadata_reference_only_rows']}**.",
        "",
        f"Unresolved historical-warning mappings kept ineligible: **{observed['unresolved_historical_warning_mappings']}**.",
        "",
        "An episode with zero clean pre-onset families remains a valid negative case once coverage and review requirements are complete. Do not interpret complete coverage as proof of advance warning. While the gate is blocked, source-only and fusion performance files must remain empty and no general lead-time, calibration or action-precision claim is authorized.",
        "",
    ])
    return "\n".join(lines)


def build(config_path: str | Path | None = None) -> tuple[Path, Path, Path, Path, Path]:
    config = load_config(config_path)
    cfg = config.get("phase4", {})
    root = project_root()
    ensure_dirs()
    manifest = pd.read_csv(_resolve(root, cfg.get("manifest_file", "data/manual/phase4_episode_manifest.csv")))
    metadata_path = _resolve(root, cfg.get("metadata_file", "data/manual/phase4_evidence_metadata.csv"))
    metadata = pd.read_csv(metadata_path, dtype=str).fillna("")
    evidence_root = _resolve(root, cfg.get("evidence_root", "data/evidence/phase4"))
    tasks = build_tasks(manifest)
    all_episodes_path = _resolve(root, cfg.get("all_flow_episodes_file", "outputs/reports/flow_episodes.csv"))
    all_flow_episodes = pd.read_csv(all_episodes_path, parse_dates=["start_date", "end_date"])
    registry = build_registry(manifest, metadata, evidence_root, all_flow_episodes)
    coverage = coverage_table(manifest, tasks, registry)
    gate = evaluate_gate(coverage, registry, cfg)

    report_dir = root / "outputs" / "reports"
    registry_path = report_dir / "multi_episode_evidence_registry.csv"
    links_path = report_dir / "episode_signal_family_links.csv"
    coverage_path = report_dir / "episode_evidence_coverage.csv"
    lead_path = report_dir / "clean_lead_time_results.csv"
    gate_path = report_dir / "evidence_coverage_gate.json"
    readiness_path = report_dir / "phase4_readiness_report.md"
    registry.to_csv(registry_path, index=False, date_format="%Y-%m-%d")
    link_columns = ["episode_cluster_id", "flow_episode_id", "phase4_split", "dependency_group", "source_class", "signal_family_id", "evidence_date", "days_from_onset", "active_flow_episode_id", "clean_pre_onset_signal", "is_update"]
    registry.reindex(columns=link_columns).to_csv(links_path, index=False, date_format="%Y-%m-%d")
    coverage.to_csv(coverage_path, index=False)
    accepted_tasks = set(registry.loc[
        registry["evidence_present"]
        & registry["is_direct_official"]
        & registry["adjudication_status"].isin(["accepted", "not_required"])
        & registry["document_role"].isin(COVERAGE_ROLES),
        "task_id",
    ]) if not registry.empty else set()
    documented_tasks = set(registry["task_id"]) if not registry.empty else set()
    task_status = tasks[[
        "task_id", "episode_cluster_id", "source_class", "window_type", "date_from", "date_to"
    ]].copy()
    task_status["status"] = task_status["task_id"].map(
        lambda value: "complete" if value in accepted_tasks else ("pending_review" if value in documented_tasks else "pending_collection")
    )
    task_status.to_csv(report_dir / "phase4_collection_status.csv", index=False)
    leads = registry.loc[registry["clean_pre_onset_signal"]].copy() if not registry.empty else registry.copy()
    lead_columns = ["episode_cluster_id", "phase4_split", "dependency_group", "source_class", "signal_family_id", "evidence_date", "onset_date", "days_from_onset"]
    leads.reindex(columns=lead_columns).to_csv(lead_path, index=False, date_format="%Y-%m-%d")
    write_json(gate, gate_path)
    readiness_path.write_text(render_readiness_report(coverage, gate), encoding="utf-8")
    print(f"Phase 4 evidence gate: {gate['status']}")
    print(f"Wrote {registry_path}")
    print(f"Wrote {coverage_path}")
    print(f"Wrote {gate_path}")
    print(f"Wrote {readiness_path}")
    return registry_path, links_path, coverage_path, lead_path, gate_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Phase 4 multi-episode evidence registry")
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    build(args.config)
