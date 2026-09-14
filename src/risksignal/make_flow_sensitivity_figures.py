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
    background_path = report_dir / "pre2024_background_selectivity.csv"
    registry_path = _resolve(root, cfg.get("evidence_registry_file", "outputs/reports/e051_evidence_registry.csv"))
    for path in [sensitivity_path, background_path, registry_path]:
        if not path.exists():
            raise FileNotFoundError(f"Missing {path}; run flow_sensitivity first")

    sensitivity = pd.read_csv(sensitivity_path, parse_dates=["target_onset_date"])
    background = pd.read_csv(background_path)

    # Figure 1: threshold selectivity + target-onset sensitivity.
    selectivity = (
        background.groupby("severe_shortfall_threshold")
        .agg(
            median_rate=("background_episodes_per_year", "median"),
            minimum_rate=("background_episodes_per_year", "min"),
            maximum_rate=("background_episodes_per_year", "max"),
        )
        .reset_index()
    )
    onset = sensitivity.loc[sensitivity["severe_shortfall_threshold"].ge(0.30)].copy()
    onset_summary = (
        onset.groupby(["severe_shortfall_threshold", "minimum_consecutive_days"])
        .agg(
            median_offset=("target_onset_offset_days", "median"),
            min_offset=("target_onset_offset_days", "min"),
            max_offset=("target_onset_offset_days", "max"),
            specifications=("baseline_id", "size"),
        )
        .reset_index()
    )

    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.2))
    x = selectivity["severe_shortfall_threshold"].to_numpy() * 100
    y = selectivity["median_rate"].to_numpy()
    low = y - selectivity["minimum_rate"].to_numpy()
    high = selectivity["maximum_rate"].to_numpy() - y
    axes[0].errorbar(x, y, yerr=[low, high], marker="o", capsize=3, linewidth=1.5)
    axes[0].set_title("Pre-2024 background selectivity")
    axes[0].set_xlabel("Shortfall threshold (%)")
    axes[0].set_ylabel("Detected episodes per year\nmedian [min-max] across rules")
    for threshold in [50, 70, 90]:
        row = selectivity.loc[np.isclose(selectivity["severe_shortfall_threshold"] * 100, threshold)].iloc[0]
        axes[0].annotate(
            f"{row['median_rate']:.1f}/yr",
            (threshold, row["median_rate"]),
            xytext=(0, 8), textcoords="offset points", ha="center", fontsize=8,
        )

    offsets = {2: -1.3, 3: 0.0, 5: 1.3}
    markers = {2: "o", 3: "s", 5: "^"}
    for minimum_days, group in onset_summary.groupby("minimum_consecutive_days"):
        group = group.sort_values("severe_shortfall_threshold")
        gx = group["severe_shortfall_threshold"].to_numpy() * 100 + offsets[int(minimum_days)]
        gy = group["median_offset"].to_numpy()
        ylow = gy - group["min_offset"].to_numpy()
        yhigh = group["max_offset"].to_numpy() - gy
        axes[1].errorbar(
            gx, gy, yerr=[ylow, yhigh], marker=markers[int(minimum_days)],
            capsize=3, linestyle="-", linewidth=1.2,
            label=f"{int(minimum_days)}-day persistence",
        )
    axes[1].axhline(0, linestyle="--", linewidth=1)
    axes[1].axhline(3, linestyle=":", linewidth=1)
    axes[1].text(91, 3.12, "1 Mar", fontsize=8, ha="right")
    axes[1].text(91, 0.12, "26 Feb", fontsize=8, ha="right")
    axes[1].set_title("E051 target-local onset range")
    axes[1].set_xlabel("Shortfall threshold (%)")
    axes[1].set_ylabel("Days after 26 February 2026")
    axes[1].legend(frameon=False, fontsize=8, loc="best")

    for ax in axes:
        ax.grid(alpha=0.2)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Outcome selectivity and E051 onset sensitivity", fontsize=12)
    fig.tight_layout()
    sensitivity_figure = figure_dir / "figure_1_flow_selectivity_and_sensitivity.png"
    fig.savefig(sensitivity_figure, dpi=300, bbox_inches="tight")
    plt.close(fig)

    # Figure 2: E051 multistage timing at daily resolution.
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
    view = frame.loc[frame["date"].between("2026-01-27", "2026-03-07")].copy()

    registry = pd.read_csv(registry_path)
    registry["evidence_date"] = pd.to_datetime(registry["evidence_date"], errors="coerce")
    stage_signals = registry.loc[
        registry["signal_family_id"].isin(["MARAD-2026-001A", "UKMTO-ADVISORY-003-26"])
        & registry["is_primary_representation"].astype(str).str.lower().eq("true")
    ].sort_values("evidence_date").drop_duplicates("signal_family_id")
    overlap = registry.loc[
        registry["signal_family_id"].eq("UKMTO-ADVISORY-001-26")
        & registry["is_primary_representation"].astype(str).str.lower().eq("true")
    ].sort_values("evidence_date").head(1)

    fig, ax = plt.subplots(figsize=(10.6, 4.7))
    ax.plot(view["date"], view["shortfall"] * 100, linewidth=2)
    for threshold in [30, 50, 70, 90]:
        ax.axhline(threshold, linestyle=":" if threshold < 90 else "--", linewidth=1, alpha=0.75)
        ax.text(view["date"].min(), threshold + 1.3, f"{threshold}%", fontsize=8)
    ax.axvline(pd.Timestamp("2026-02-26"), linewidth=1.4, linestyle="--")
    ax.axvline(pd.Timestamp("2026-03-01"), linewidth=1.4, linestyle="-.")
    ax.annotate("Initial degradation\n26 Feb", (pd.Timestamp("2026-02-26"), 92),
                xytext=(-7, 0), textcoords="offset points", ha="right", va="center", fontsize=8)
    ax.annotate("Major/catastrophic stage\n1 Mar", (pd.Timestamp("2026-03-01"), 92),
                xytext=(7, 0), textcoords="offset points", ha="left", va="center", fontsize=8)

    # Documentary dates are shown directly rather than through a crowded legend.
    for signal in stage_signals.itertuples(index=False):
        if signal.source == "MARAD":
            ax.scatter(signal.evidence_date, 105, s=54, marker="o", zorder=5)
            ax.annotate("MARAD effective date\n28 Feb", (signal.evidence_date, 105),
                        xytext=(-10, 6), textcoords="offset points", ha="right", va="bottom", fontsize=7.5)
        else:
            ax.scatter(signal.evidence_date, 109, s=54, marker="s", zorder=5)
            ax.annotate("UKMTO issue date\n28 Feb", (signal.evidence_date, 109),
                        xytext=(10, 0), textcoords="offset points", ha="left", va="center", fontsize=7.5)
    if not overlap.empty:
        row = overlap.iloc[0]
        ax.scatter(row["evidence_date"], 104, s=48, marker="x", zorder=5)
        ax.annotate(
            "3 Feb UKMTO: contextual overlap with E050;\nnot a clean E051 warning",
            (row["evidence_date"], 104), xytext=(8, -1), textcoords="offset points",
            fontsize=7.4, va="center",
        )

    ax.set_ylim(0, 114)
    ax.set_ylabel("Estimated tanker-capacity shortfall (%)")
    ax.set_xlabel("Date")
    ax.set_title("E051: stage timing and documentary dates at daily resolution")
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=5))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.grid(alpha=0.2)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    multistage_figure = figure_dir / "figure_2_e051_multistage_timing.png"
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
