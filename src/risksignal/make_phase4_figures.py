from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from .utils import ensure_dirs, load_config, project_root


def make_figures(config_path: str | Path | None = None) -> tuple[Path, Path]:
    load_config(config_path)
    root = project_root()
    ensure_dirs()
    report_dir = root / "outputs" / "reports"
    figure_dir = root / "outputs" / "figures"
    coverage = pd.read_csv(report_dir / "episode_evidence_coverage.csv")
    gate = json.loads((report_dir / "evidence_coverage_gate.json").read_text(encoding="utf-8"))

    fig, ax = plt.subplots(figsize=(10.5, 4.8))
    values = coverage["required_coverage_fraction"] * 100
    colors = ["#2f855a" if value >= 90 else "#c05621" for value in values]
    ax.bar(coverage["episode_cluster_id"], values, color=colors)
    ax.axhline(90, color="#203864", linestyle="--", linewidth=1.2, label="Episode coverage threshold")
    ax.set_ylim(0, 105)
    ax.set_ylabel("Required source-window coverage (%)")
    ax.set_xlabel("Independent episode cluster")
    ax.set_title("Phase 4 evidence coverage by telemetry-defined episode")
    ax.grid(axis="y", alpha=0.2)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False)
    fig.tight_layout()
    coverage_figure = figure_dir / "figure_7_phase4_evidence_coverage.png"
    fig.savefig(coverage_figure, dpi=300, bbox_inches="tight")
    plt.close(fig)

    metrics_path = report_dir / "source_only_and_fusion_metrics.csv"
    metrics = pd.read_csv(metrics_path)
    fig, ax = plt.subplots(figsize=(10.5, 4.8))
    if gate.get("status") == "pass" and not metrics.empty:
        test = metrics.loc[metrics["split"].eq("test")].sort_values("detection_rate")
        ax.barh(test["system"], test["detection_rate"] * 100, color="#2f6690")
        ax.set_xlabel("Test-episode detection rate (%)")
        ax.set_xlim(0, 105)
        ax.set_title("Source-only versus fusion detection on temporal holdout episodes")
        ax.grid(axis="x", alpha=0.2)
    else:
        observed = gate.get("observed", {})
        ax.axis("off")
        ax.text(0.5, 0.62, "Fusion comparison blocked", ha="center", va="center", fontsize=20, weight="bold", color="#9c2f2f")
        ax.text(
            0.5, 0.42,
            f"Eligible independent clusters: {observed.get('eligible_independent_clusters', 0)}\n"
            f"Eligible temporal test clusters: {observed.get('eligible_test_clusters', 0)}\n"
            f"Unresolved historical-warning mappings: {observed.get('unresolved_historical_warning_mappings', 0)}\n"
            "Complete direct-source, zero-result, and historical-availability evidence before estimating performance.",
            ha="center", va="center", fontsize=11,
        )
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    comparison_figure = figure_dir / "figure_8_phase4_source_fusion_comparison.png"
    fig.savefig(comparison_figure, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {coverage_figure}")
    print(f"Wrote {comparison_figure}")
    return coverage_figure, comparison_figure


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create Phase 4 evidence and fusion figures")
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    make_figures(args.config)
