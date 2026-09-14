from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .utils import ensure_dirs, load_config, project_root


def _as_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().eq("true")


def evaluate(config_path: str | Path | None = None) -> tuple[Path, Path]:
    # Load config for consistency with the other offline modules even though the
    # sensitivity grid below is intentionally fixed and reported in the paper.
    load_config(config_path)
    root = project_root()
    ensure_dirs()
    report_dir = root / "outputs" / "reports"

    gate_path = report_dir / "evidence_coverage_gate.json"
    registry_path = report_dir / "multi_episode_evidence_registry.csv"
    coverage_path = report_dir / "episode_evidence_coverage.csv"
    for path in [gate_path, registry_path, coverage_path]:
        if not path.exists():
            raise FileNotFoundError(f"Missing {path}; use the released offline reports or rebuild the registry locally")

    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    registry = pd.read_csv(registry_path)
    coverage = pd.read_csv(coverage_path)

    # -------------------------
    # Gate-policy sensitivity
    # -------------------------
    coverage_floors = [0.75, 0.90, 1.00]
    cluster_floors = [3, 5, 10]
    minimum_test_clusters = int(gate.get("thresholds", {}).get("minimum_test_clusters", 3))
    minimum_source_classes = 2
    source_classes = int(gate.get("observed", {}).get("direct_source_classes", 0))
    unresolved = int(gate.get("observed", {}).get("unresolved_historical_warning_mappings", 0))

    policy_rows = []
    for c in coverage_floors:
        eligible = coverage.loc[
            coverage["required_coverage_fraction"].ge(c)
            & coverage["unresolved_metadata_rows"].eq(0)
            & coverage["double_coding_issues"].eq(0)
            & coverage["historical_warning_eligibility_issues"].eq(0)
        ].copy()
        independent = int(eligible["dependency_group"].nunique())
        test_clusters = int(eligible.loc[eligible["phase4_split"].eq("test"), "dependency_group"].nunique())
        for n in cluster_floors:
            checks = {
                "coverage_and_cluster_floor": independent >= n,
                "minimum_temporal_test_clusters": test_clusters >= minimum_test_clusters,
                "minimum_two_direct_source_classes": source_classes >= minimum_source_classes,
                "no_unresolved_historical_warning_mappings": unresolved == 0,
            }
            policy_rows.append({
                "minimum_episode_coverage": c,
                "minimum_independent_clusters": n,
                "eligible_independent_clusters": independent,
                "eligible_test_clusters": test_clusters,
                "direct_source_classes": source_classes,
                "unresolved_historical_warning_mappings": unresolved,
                "status": "pass" if all(checks.values()) else "blocked",
                "blocking_checks": ";".join(k for k, v in checks.items() if not v),
            })
    policy = pd.DataFrame(policy_rows)
    policy_path = report_dir / "gate_policy_sensitivity.csv"
    policy.to_csv(policy_path, index=False)

    # ----------------------------------
    # Naive versus evidence-gated ablation
    # ----------------------------------
    for col in ["evidence_present", "is_update", "clean_pre_onset_signal"]:
        if col in registry:
            registry[col] = _as_bool(registry[col])
    registry["days_from_onset"] = pd.to_numeric(registry["days_from_onset"], errors="coerce")

    current = registry.loc[
        registry["document_role"].isin(["positive_signal", "update"])
        & registry["days_from_onset"].lt(0)
    ].copy()

    ablation_rows = []

    def record(stage: str, rule: str, frame: pd.DataFrame) -> None:
        ablation_rows.append({
            "stage": stage,
            "rule": rule,
            "admitted_records": int(len(frame)),
            "admitted_episode_clusters": int(frame["episode_cluster_id"].nunique()),
            "admitted_signal_families": int(frame["signal_family_id"].nunique()),
        })

    record("naive_timestamp_only", "positive/update record with days_from_onset < 0", current)
    current = current.loc[current["evidence_present"]]
    record("require_local_evidence", "require physical local artifact", current)
    current = current.loc[~current["is_update"]]
    record("remove_updates", "exclude update records as independent signals", current)
    current = current.loc[~current["historical_availability_status"].eq("unverified")]
    record("require_historical_availability", "exclude unverified historical availability", current)
    current = current.loc[current["active_flow_episode_id"].isna()]
    record("exclude_prior_episode_overlap", "exclude records inside another active flow episode", current)

    ablation = pd.DataFrame(ablation_rows)
    ablation_path = report_dir / "naive_vs_evidence_gated_ablation.csv"
    ablation.to_csv(ablation_path, index=False)

    print(f"Wrote {policy_path}")
    print(f"Wrote {ablation_path}")
    return policy_path, ablation_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate gate-policy sensitivity and naive-vs-gated evidence ablation")
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    evaluate(args.config)
