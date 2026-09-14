from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .build_flow_outcome import estimate_expected_capacity
from .utils import ensure_dirs, load_config, project_root


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def make_figures(config_path: str | Path | None = None) -> tuple[Path, Path]:
    config = load_config(config_path)
    flow_cfg = config.get("flow_outcome", {})
    cfg = config.get("flow_sensitivity", {})
    root = project_root()
    ensure_dirs()
    report_dir = root / "outputs" / "reports"
    figure_dir = root / "outputs" / "figures"
    sensitivity_path = report_dir / "flow_outcome_sensitivity.csv"
    multistage_path = report_dir / "e051_multistage_timeline.csv"
    registry_path = _resolve(root, cfg.get("evidence_registry_file", "outputs/reports/e051_evidence_registry.csv"))
    for path in [sensitivity_path, multistage_path, registry_path]:
        if not path.exists():
            raise FileNotFoundError(f"Missing {path}; run flow_sensitivity first")

    sensitivity = pd.read_csv(sensitivity_path)
    grouped = (
        sensitivity.groupby(["severe_shortfall_threshold", "minimum_consecutive_days"])
        .agg(
            median_episode_count=("total_episode_count", "median"),
            median_onset_offset=("target_onset_offset_days", "median"),
            onset_offset_low=("target_onset_offset_days", "min"),
            onset_offset_high=("target_onset_offset_days", "max"),
        )
        .reset_index()
    )
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    colors = {2: "#2f6690", 3: "#3a7d44", 5: "#b85c38"}
    for minimum_days, group in grouped.groupby("minimum_consecutive_days"):
        group = group.sort_values("severe_shortfall_threshold")
        label = f"{minimum_days} consecutive days"
        axes[0].plot(
            group["severe_shortfall_threshold"] * 100,
            group["median_episode_count"],
            marker="o", label=label, color=colors.get(int(minimum_days)),
        )
        onset_group = group.loc[group["severe_shortfall_threshold"].ge(0.30)]
        axes[1].plot(
            onset_group["severe_shortfall_threshold"] * 100,
            onset_group["median_onset_offset"],
            marker="o", label=label, color=colors.get(int(minimum_days)),
        )
        axes[1].fill_between(
            onset_group["severe_shortfall_threshold"] * 100,
            onset_group["onset_offset_low"], onset_group["onset_offset_high"],
            color=colors.get(int(minimum_days)), alpha=0.12,
        )
    axes[0].set_title("Episode count varies with outcome definition")
    axes[0].set_ylabel("Median number of episodes")
    axes[1].set_title("E051 onset shifts at stricter thresholds")
    axes[1].set_ylabel("Days after 26 February 2026")
    axes[1].axhline(0, color="#555555", linestyle="--", linewidth=1)
    axes[1].text(
        0.02, 0.96,
        "20% omitted: some rules merge the target with a prior episode",
        transform=axes[1].transAxes, va="top", fontsize=8, color="#555555",
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.8, "pad": 2},
    )
    for axis in axes:
        axis.set_xlabel("Severe shortfall threshold (%)")
        axis.grid(alpha=0.2)
        axis.spines[["top", "right"]].set_visible(False)
        axis.legend(frameon=False, fontsize=8)
    fig.suptitle("Physical-flow outcome sensitivity across training-only baselines and recovery rules", fontsize=12)
    fig.tight_layout()
    sensitivity_figure = figure_dir / "figure_5_flow_outcome_sensitivity.png"
    fig.savefig(sensitivity_figure, dpi=300, bbox_inches="tight")
    plt.close(fig)

    primary = _resolve(root, cfg.get("source_file", "data/raw/portwatch_hormuz_daily.csv"))
    fallback = _resolve(root, cfg.get("fallback_source_file", "data/processed/hormuz_flow_outcomes.csv"))
    source = primary if primary.exists() else fallback
    frame = pd.read_csv(source, parse_dates=["date"]).sort_values("date")
    observed_column = str(flow_cfg.get("observed_column", "capacity_tanker"))
    expected, _ = estimate_expected_capacity(
        frame,
        observed_column=observed_column,
        baseline_end=str(flow_cfg.get("baseline_end", "2023-12-31")),
        seasonal_half_window_days=int(cfg.get("canonical_seasonal_half_window_days", 15)),
    )
    observed = pd.to_numeric(frame[observed_column], errors="coerce")
    frame["shortfall"] = np.maximum(0.0, expected - observed) / expected.replace(0, np.nan)
    view = frame.loc[frame["date"].between("2026-01-27", "2026-03-15")].copy()
    registry = pd.read_csv(registry_path)
    signals = registry.loc[
        registry["is_analytic_signal"].astype(str).str.lower().eq("true")
        & registry["is_primary_representation"].astype(str).str.lower().eq("true")
        & registry["evidence_date"].notna()
    ].copy()
    signals["evidence_date"] = pd.to_datetime(signals["evidence_date"])
    signals = signals.sort_values(["evidence_date", "update_number"]).drop_duplicates("signal_family_id")
    signals = signals.loc[signals["evidence_date"].between("2026-01-27", "2026-03-15")]

    fig, ax = plt.subplots(figsize=(11, 5.2))
    ax.plot(view["date"], view["shortfall"] * 100, color="#203864", linewidth=2, label="Tanker-capacity shortfall")
    for threshold, color in [(30, "#6aa84f"), (50, "#f1c232"), (70, "#e69138"), (90, "#cc0000")]:
        ax.axhline(threshold, color=color, linestyle=":" if threshold < 90 else "--", linewidth=1, alpha=0.8)
        ax.text(view["date"].min(), threshold + 1.2, f"{threshold}%", color=color, fontsize=8)
    ax.axvline(pd.Timestamp("2026-02-26"), color="#111111", linewidth=1.5, label="Early degradation onset")
    ax.axvline(pd.Timestamp("2026-03-01"), color="#b22222", linewidth=1.5, label="Catastrophic-stage onset")
    source_colors = {"UKMTO": "#1f77b4", "MARAD": "#ff7f0e", "Gard": "#2ca02c", "IUA-JWC/LMA": "#9467bd", "UKMTO-JMIC": "#8c564b"}
    seen: set[str] = set()
    for date, group in signals.groupby("evidence_date"):
        for index, (_, signal) in enumerate(group.iterrows()):
            source_name = str(signal["source"])
            label = f"{source_name} signal" if source_name not in seen else None
            seen.add(source_name)
            ax.scatter(date, 104 + index * 2.2, s=42, color=source_colors.get(source_name, "#555555"), label=label, zorder=5)
    ax.set_ylim(0, 114)
    ax.set_ylabel("Estimated tanker-capacity shortfall (%)")
    ax.set_xlabel("Date")
    ax.set_title("E051 exhibits an early-degradation stage followed by near-total collapse")
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=7))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.grid(alpha=0.2)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper left")
    fig.autofmt_xdate(rotation=0)
    fig.tight_layout()
    multistage_figure = figure_dir / "figure_6_e051_multistage_outcome.png"
    fig.savefig(multistage_figure, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {sensitivity_figure}")
    print(f"Wrote {multistage_figure}")
    return sensitivity_figure, multistage_figure


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create physical-flow sensitivity figures")
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    make_figures(args.config)
