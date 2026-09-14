from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .utils import ensure_dirs, load_config, project_root, write_json


SYSTEMS = {
    "MARAD_only": {"MARAD"},
    "UKMTO_warning_only": {"UKMTO_WARNING"},
    "UKMTO_advisory_only": {"UKMTO_ADVISORY"},
    "insurance_only": {"IUA_JWC_LMA", "GARD"},
    "advisory_fusion": {"MARAD", "UKMTO_WARNING", "UKMTO_ADVISORY"},
    "all_source_fusion": {"MARAD", "UKMTO_WARNING", "UKMTO_ADVISORY", "IUA_JWC_LMA", "GARD"},
}

METRIC_COLUMNS = [
    "system", "split", "independent_episode_clusters", "detected_clusters", "detection_rate",
    "median_lead_days_detected", "mean_lead_days_detected", "maximum_lead_days", "status",
]


def _system_episode_table(registry: pd.DataFrame, coverage: pd.DataFrame) -> pd.DataFrame:
    eligible = coverage.loc[coverage["episode_complete"]].copy()
    rows: list[dict[str, Any]] = []
    for episode in eligible.itertuples(index=False):
        signals = registry.loc[
            registry["episode_cluster_id"].eq(episode.episode_cluster_id)
            & registry["clean_pre_onset_signal"]
        ]
        for system, sources in SYSTEMS.items():
            selected = signals.loc[signals["source_class"].isin(sources)]
            detected = not selected.empty
            lead = float((-selected["days_from_onset"]).max()) if detected else np.nan
            rows.append({
                "episode_cluster_id": episode.episode_cluster_id,
                "dependency_group": episode.dependency_group,
                "phase4_split": episode.phase4_split,
                "system": system,
                "detected": detected,
                "lead_days": lead,
            })
    return pd.DataFrame(rows)


def summarize(episode_table: pd.DataFrame) -> pd.DataFrame:
    if episode_table.empty:
        return pd.DataFrame(columns=METRIC_COLUMNS)
    rows: list[dict[str, Any]] = []
    expanded = pd.concat([
        episode_table.assign(report_split=episode_table["phase4_split"]),
        episode_table.assign(report_split="all"),
    ], ignore_index=True)
    for (system, split), group in expanded.groupby(["system", "report_split"]):
        detected = group.loc[group["detected"]]
        rows.append({
            "system": system,
            "split": split,
            "independent_episode_clusters": int(group["dependency_group"].nunique()),
            "detected_clusters": int(detected["dependency_group"].nunique()),
            "detection_rate": float(group["detected"].mean()),
            "median_lead_days_detected": float(detected["lead_days"].median()) if not detected.empty else np.nan,
            "mean_lead_days_detected": float(detected["lead_days"].mean()) if not detected.empty else np.nan,
            "maximum_lead_days": float(detected["lead_days"].max()) if not detected.empty else np.nan,
            "status": "descriptive_episode_level",
        })
    return pd.DataFrame(rows, columns=METRIC_COLUMNS).sort_values(["split", "system"])


def cluster_bootstrap(episode_table: pd.DataFrame, *, replicates: int, seed: int) -> dict[str, Any]:
    test = episode_table.loc[episode_table["phase4_split"].eq("test")].copy()
    pivot = test.pivot(index="dependency_group", columns="system", values="detected")
    if pivot.empty or "all_source_fusion" not in pivot:
        return {"status": "not_estimable", "reason": "No eligible test episode clusters"}
    source_systems = [name for name in ["MARAD_only", "UKMTO_warning_only", "UKMTO_advisory_only", "insurance_only"] if name in pivot]
    rates = pivot[source_systems].mean()
    best_source = str(rates.idxmax())
    observed = float(pivot["all_source_fusion"].mean() - pivot[best_source].mean())
    groups = pivot.index.to_numpy()
    rng = np.random.default_rng(seed)
    samples = np.empty(replicates, dtype=float)
    for index in range(replicates):
        chosen = rng.choice(groups, size=len(groups), replace=True)
        sampled = pivot.loc[chosen]
        samples[index] = sampled["all_source_fusion"].mean() - sampled[best_source].mean()
    low, high = np.quantile(samples, [0.025, 0.975])
    return {
        "status": "estimated",
        "estimand": "test-cluster detection-rate difference: all-source fusion minus best source-only system",
        "best_source_only_system": best_source,
        "test_episode_clusters": int(len(groups)),
        "observed_difference": observed,
        "bootstrap_95_interval": [float(low), float(high)],
        "replicates": replicates,
        "seed": seed,
        "caution": "Episode-cluster bootstrap uncertainty is descriptive with few clusters; false-alarm precision requires control-window construction.",
    }


def evaluate(config_path: str | Path | None = None) -> tuple[Path, Path]:
    config = load_config(config_path)
    cfg = config.get("phase4", {})
    root = project_root()
    ensure_dirs()
    report_dir = root / "outputs" / "reports"
    gate_path = report_dir / "evidence_coverage_gate.json"
    registry_path = report_dir / "multi_episode_evidence_registry.csv"
    coverage_path = report_dir / "episode_evidence_coverage.csv"
    for path in [gate_path, registry_path, coverage_path]:
        if not path.exists():
            raise FileNotFoundError(f"Missing {path}; run phase4_registry first")
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    registry = pd.read_csv(registry_path)
    coverage = pd.read_csv(coverage_path)
    if "episode_complete" in coverage:
        coverage["episode_complete"] = coverage["episode_complete"].astype(str).str.lower().eq("true")
    metrics_path = report_dir / "source_only_and_fusion_metrics.csv"
    bootstrap_path = report_dir / "episode_cluster_bootstrap.json"
    if gate.get("status") != "pass":
        pd.DataFrame(columns=METRIC_COLUMNS).to_csv(metrics_path, index=False)
        write_json({
            "status": "blocked",
            "reason": "Evidence-coverage gate has not passed; no fusion-performance claim was calculated.",
            "gate_observed": gate.get("observed", {}),
        }, bootstrap_path)
        print("Phase 4 evaluation blocked by evidence-coverage gate (expected before collection).")
        return metrics_path, bootstrap_path

    if not registry.empty:
        for column in ["clean_pre_onset_signal", "is_zero_result_capture", "is_direct_official", "is_update"]:
            registry[column] = registry[column].astype(str).str.lower().eq("true")
        registry["days_from_onset"] = pd.to_numeric(registry["days_from_onset"], errors="coerce")
    episode_table = _system_episode_table(registry, coverage)
    metrics = summarize(episode_table)
    metrics.to_csv(metrics_path, index=False)
    bootstrap = cluster_bootstrap(
        episode_table,
        replicates=int(cfg.get("bootstrap_replicates", 2000)),
        seed=int(cfg.get("bootstrap_seed", 42)),
    )
    write_json(bootstrap, bootstrap_path)
    episode_table.to_csv(report_dir / "phase4_episode_system_detection.csv", index=False)
    print(f"Wrote {metrics_path}")
    print(f"Wrote {bootstrap_path}")
    return metrics_path, bootstrap_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Phase 4 source-only and fusion systems")
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    evaluate(args.config)
