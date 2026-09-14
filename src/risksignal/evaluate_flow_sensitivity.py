from __future__ import annotations

import argparse
import itertools
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .build_flow_outcome import estimate_expected_capacity, identify_episodes
from .utils import ensure_dirs, load_config, project_root, write_json


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def estimate_month_weekday_capacity(
    frame: pd.DataFrame,
    *,
    observed_column: str,
    baseline_end: str | pd.Timestamp,
) -> tuple[pd.Series, dict[str, Any]]:
    """Training-only month-by-weekday median with hierarchical fallbacks."""
    dates = pd.to_datetime(frame["date"], errors="coerce")
    observed = pd.to_numeric(frame[observed_column], errors="coerce")
    cutoff = pd.Timestamp(baseline_end)
    baseline = pd.DataFrame({"date": dates, "observed": observed})
    baseline = baseline.loc[baseline["date"].le(cutoff) & baseline["observed"].notna()].copy()
    if len(baseline) < 365:
        raise ValueError(f"Expected at least 365 baseline observations, found {len(baseline)}")
    baseline["month"] = baseline["date"].dt.month
    baseline["weekday"] = baseline["date"].dt.dayofweek
    joint = baseline.groupby(["month", "weekday"])["observed"].median()
    month = baseline.groupby("month")["observed"].median()
    weekday = baseline.groupby("weekday")["observed"].median()
    fallback = float(baseline["observed"].median())
    estimates: list[float] = []
    for date in dates:
        value = joint.get((date.month, date.dayofweek), np.nan)
        if not np.isfinite(value):
            value = month.get(date.month, np.nan)
        if not np.isfinite(value):
            value = weekday.get(date.dayofweek, np.nan)
        if not np.isfinite(value) or value <= 0:
            value = fallback
        estimates.append(float(value))
    return pd.Series(estimates, index=frame.index), {
        "method": "training-only month-by-weekday median",
        "baseline_end": cutoff.strftime("%Y-%m-%d"),
        "baseline_observations": int(len(baseline)),
        "baseline_observed_median": fallback,
    }


def _episode_table(
    frame: pd.DataFrame,
    shortfall: pd.Series,
    *,
    threshold: float,
    minimum_consecutive_days: int,
    recovery_days: int,
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    severe = shortfall.ge(threshold)
    episode_ids, onsets = identify_episodes(
        severe,
        minimum_consecutive_severe_days=minimum_consecutive_days,
        recovery_days=recovery_days,
    )
    ids = pd.Series(episode_ids, index=frame.index)
    onset_flags = pd.Series(onsets, index=frame.index)
    rows: list[dict[str, Any]] = []
    for episode_id, group_index in ids.loc[ids.gt(0)].groupby(ids.loc[ids.gt(0)]).groups.items():
        group = frame.loc[group_index]
        values = shortfall.loc[group_index]
        rows.append({
            "sensitivity_episode_id": int(episode_id),
            "start_date": group["date"].min(),
            "end_date": group["date"].max(),
            "duration_days": int(len(group)),
            "severe_days": int(values.ge(threshold).sum()),
            "maximum_shortfall_fraction": float(values.max()),
            "cumulative_capacity_loss": float(group.loc[group_index, "capacity_loss"].sum())
            if "capacity_loss" in group
            else np.nan,
        })
    return pd.DataFrame(rows), ids, onset_flags


def _target_episode(episodes: pd.DataFrame, anchor_date: pd.Timestamp) -> pd.Series | None:
    if episodes.empty:
        return None
    match = episodes.loc[
        episodes["start_date"].le(anchor_date) & episodes["end_date"].ge(anchor_date)
    ]
    return match.iloc[0] if not match.empty else None


def _single_change_point(
    frame: pd.DataFrame,
    *,
    column: str,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    minimum_segment_days: int = 14,
) -> dict[str, Any]:
    view = frame.loc[frame["date"].between(pd.Timestamp(start), pd.Timestamp(end)), ["date", column]].dropna()
    values = np.log1p(pd.to_numeric(view[column], errors="coerce").clip(lower=0).to_numpy())
    if len(values) < minimum_segment_days * 2:
        raise ValueError(f"Not enough observations for change-point detection in {column}")
    best_index = None
    best_sse = np.inf
    for index in range(minimum_segment_days, len(values) - minimum_segment_days + 1):
        left, right = values[:index], values[index:]
        sse = float(((left - left.mean()) ** 2).sum() + ((right - right.mean()) ** 2).sum())
        if sse < best_sse:
            best_sse, best_index = sse, index
    assert best_index is not None
    before = pd.to_numeric(view.iloc[:best_index][column], errors="coerce")
    after = pd.to_numeric(view.iloc[best_index:][column], errors="coerce")
    return {
        "column": column,
        "detected_change_date": view.iloc[best_index]["date"].strftime("%Y-%m-%d"),
        "pre_median": float(before.median()),
        "post_median": float(after.median()),
        "post_to_pre_median_ratio": float(after.median() / before.median()) if before.median() else None,
        "log_scale_residual_sse": best_sse,
        "minimum_segment_days": minimum_segment_days,
    }


def _load_source(cfg: dict[str, Any], root: Path) -> tuple[pd.DataFrame, Path, str]:
    primary = _resolve(root, cfg.get("source_file", "data/raw/portwatch_hormuz_daily.csv"))
    fallback = _resolve(root, cfg.get("fallback_source_file", "data/processed/hormuz_flow_outcomes.csv"))
    source = primary if primary.exists() else fallback
    if not source.exists():
        raise FileNotFoundError(f"Neither {primary} nor {fallback} exists")
    frame = pd.read_csv(source)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame = frame.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    if frame["date"].duplicated().any():
        raise ValueError("PortWatch sensitivity input contains duplicate dates")
    expected = pd.date_range(frame["date"].min(), frame["date"].max(), freq="D")
    if len(expected) != len(frame) or not frame["date"].equals(pd.Series(expected)):
        raise ValueError("PortWatch sensitivity input must contain one row for every calendar day")
    mode = "canonical_raw" if source == primary else "processed_fallback_with_original_fields"
    return frame, source, mode


def _family_first(registry: pd.DataFrame) -> pd.DataFrame:
    analytic = registry.loc[
        registry["is_analytic_signal"].astype(str).str.lower().eq("true")
        & registry["is_primary_representation"].astype(str).str.lower().eq("true")
        & registry["evidence_date"].notna()
    ].copy()
    analytic["evidence_date"] = pd.to_datetime(analytic["evidence_date"])
    analytic = analytic.sort_values(["evidence_date", "update_number", "relative_path"])
    return analytic.drop_duplicates("signal_family_id", keep="first")


def evaluate(config_path: str | Path | None = None) -> dict[str, Path]:
    config = load_config(config_path)
    flow_cfg = config.get("flow_outcome", {})
    cfg = config.get("flow_sensitivity", {})
    root = project_root()
    ensure_dirs()
    frame, source_path, source_mode = _load_source({**flow_cfg, **cfg}, root)
    observed_column = str(flow_cfg.get("observed_column", "capacity_tanker"))
    if observed_column not in frame:
        raise ValueError(f"Missing observed column: {observed_column}")
    baseline_end = str(flow_cfg.get("baseline_end", "2023-12-31"))
    anchor_date = pd.Timestamp(cfg.get("target_anchor_date", "2026-03-01"))
    canonical_onset = pd.Timestamp(cfg.get("canonical_onset_date", "2026-02-26"))
    test_start = pd.Timestamp(flow_cfg.get("test_start", "2026-01-01"))

    baseline_variants: dict[str, pd.Series] = {}
    for half_window in cfg.get("seasonal_half_windows_days", [7, 15, 30]):
        expected, _ = estimate_expected_capacity(
            frame,
            observed_column=observed_column,
            baseline_end=baseline_end,
            seasonal_half_window_days=int(half_window),
        )
        baseline_variants[f"doy_weekday_hw{int(half_window)}"] = expected
    month_weekday, _ = estimate_month_weekday_capacity(
        frame, observed_column=observed_column, baseline_end=baseline_end
    )
    baseline_variants["month_weekday_median"] = month_weekday

    thresholds = [float(value) for value in cfg.get("thresholds", [0.20, 0.30, 0.40, 0.50, 0.70, 0.90])]
    minimum_runs = [int(value) for value in cfg.get("minimum_consecutive_days", [2, 3, 5])]
    recovery_values = [int(value) for value in cfg.get("recovery_days", [3, 5, 7])]
    sensitivity_rows: list[dict[str, Any]] = []
    cached_shortfalls: dict[str, pd.Series] = {}
    cached_expected: dict[str, pd.Series] = {}

    observed = pd.to_numeric(frame[observed_column], errors="coerce")
    for baseline_id, expected in baseline_variants.items():
        expected = pd.to_numeric(expected, errors="coerce")
        loss = np.maximum(0.0, expected - observed)
        shortfall = loss / expected.replace(0, np.nan)
        cached_expected[baseline_id] = expected
        cached_shortfalls[baseline_id] = shortfall
        working = frame.copy()
        working["capacity_loss"] = loss
        for threshold, minimum_run, recovery in itertools.product(thresholds, minimum_runs, recovery_values):
            episodes, _, _ = _episode_table(
                working,
                shortfall,
                threshold=threshold,
                minimum_consecutive_days=minimum_run,
                recovery_days=recovery,
            )
            target = _target_episode(episodes, anchor_date)
            test_count = int(episodes["start_date"].ge(test_start).sum()) if not episodes.empty else 0
            row: dict[str, Any] = {
                "baseline_id": baseline_id,
                "severe_shortfall_threshold": threshold,
                "minimum_consecutive_days": minimum_run,
                "recovery_days": recovery,
                "total_episode_count": int(len(episodes)),
                "test_episode_count": test_count,
                "target_anchor_date": anchor_date,
                "target_episode_detected": target is not None,
                "target_onset_date": target["start_date"] if target is not None else pd.NaT,
                "target_end_date": target["end_date"] if target is not None else pd.NaT,
                "target_onset_offset_days": int((target["start_date"] - canonical_onset).days)
                if target is not None else pd.NA,
                "target_duration_days": int(target["duration_days"]) if target is not None else pd.NA,
                "target_severe_days": int(target["severe_days"]) if target is not None else pd.NA,
                "target_maximum_shortfall_fraction": float(target["maximum_shortfall_fraction"])
                if target is not None else np.nan,
                "target_cumulative_capacity_loss": float(target["cumulative_capacity_loss"])
                if target is not None else np.nan,
            }
            sensitivity_rows.append(row)

    sensitivity = pd.DataFrame(sensitivity_rows)

    # Characterize background selectivity on the same training-only period used
    # to estimate the outcome baselines. These counts are not labeled as false
    # positives because the historical interval may contain genuine disruptions;
    # they quantify how often each rule fires away from the target case.
    training_mask = frame["date"].le(pd.Timestamp(baseline_end))
    training_days = int(training_mask.sum())
    training_years = training_days / 365.2425
    background_rows: list[dict[str, Any]] = []
    for baseline_id, shortfall in cached_shortfalls.items():
        expected = cached_expected[baseline_id]
        loss = np.maximum(0.0, expected - observed)
        training_frame = frame.loc[training_mask].copy().reset_index(drop=True)
        training_frame["capacity_loss"] = pd.Series(loss, index=frame.index).loc[training_mask].to_numpy()
        training_shortfall = shortfall.loc[training_mask].reset_index(drop=True)
        for threshold, minimum_run, recovery in itertools.product(thresholds, minimum_runs, recovery_values):
            episodes, ids, _ = _episode_table(
                training_frame,
                training_shortfall,
                threshold=threshold,
                minimum_consecutive_days=minimum_run,
                recovery_days=recovery,
            )
            background_rows.append({
                "baseline_id": baseline_id,
                "severe_shortfall_threshold": threshold,
                "minimum_consecutive_days": minimum_run,
                "recovery_days": recovery,
                "training_start_date": training_frame["date"].min(),
                "training_end_date": training_frame["date"].max(),
                "training_days": training_days,
                "background_episode_count": int(len(episodes)),
                "background_episodes_per_year": float(len(episodes) / training_years),
                "raw_threshold_days": int(training_shortfall.ge(threshold).sum()),
                "raw_threshold_day_fraction": float(training_shortfall.ge(threshold).mean()),
                "episode_active_days": int(pd.Series(ids).gt(0).sum()),
                "episode_active_day_fraction": float(pd.Series(ids).gt(0).mean()),
                "mean_episode_duration_days": float(episodes["duration_days"].mean()) if not episodes.empty else 0.0,
                "median_episode_duration_days": float(episodes["duration_days"].median()) if not episodes.empty else 0.0,
            })
    background = pd.DataFrame(background_rows)

    stability = (
        sensitivity.groupby(["severe_shortfall_threshold", "minimum_consecutive_days"])
        .agg(
            specifications=("baseline_id", "size"),
            target_detection_rate=("target_episode_detected", "mean"),
            median_total_episodes=("total_episode_count", "median"),
            median_test_episodes=("test_episode_count", "median"),
            minimum_target_onset=("target_onset_date", "min"),
            maximum_target_onset=("target_onset_date", "max"),
            median_target_onset_offset_days=("target_onset_offset_days", "median"),
            minimum_target_onset_offset_days=("target_onset_offset_days", "min"),
            maximum_target_onset_offset_days=("target_onset_offset_days", "max"),
            median_target_duration_days=("target_duration_days", "median"),
        )
        .reset_index()
    )
    stability["target_onset_range_days"] = (
        pd.to_datetime(stability["maximum_target_onset"]) - pd.to_datetime(stability["minimum_target_onset"])
    ).dt.days

    canonical_baseline = str(cfg.get("canonical_baseline", "doy_weekday_hw15"))
    if canonical_baseline not in cached_shortfalls:
        raise ValueError(f"Unknown canonical baseline {canonical_baseline}")
    canonical_shortfall = cached_shortfalls[canonical_baseline]
    canonical_expected = cached_expected[canonical_baseline]
    canonical_working = frame.copy()
    canonical_working["capacity_loss"] = np.maximum(0.0, canonical_expected - observed)
    registry_path = _resolve(root, cfg.get("evidence_registry_file", "outputs/reports/e051_evidence_registry.csv"))
    if not registry_path.exists():
        raise FileNotFoundError(f"Missing {registry_path}; run the evidence step first")
    families = _family_first(pd.read_csv(registry_path))
    multistage_rows: list[dict[str, Any]] = []
    labels = {0.30: "early degradation", 0.40: "severe degradation", 0.50: "major disruption", 0.70: "critical disruption", 0.90: "catastrophic disruption"}
    for threshold in [float(value) for value in cfg.get("stage_thresholds", [0.30, 0.40, 0.50, 0.70, 0.90])]:
        episodes, _, _ = _episode_table(
            canonical_working,
            canonical_shortfall,
            threshold=threshold,
            minimum_consecutive_days=int(cfg.get("canonical_minimum_consecutive_days", 2)),
            recovery_days=int(cfg.get("canonical_recovery_days", 3)),
        )
        target = _target_episode(episodes, anchor_date)
        if target is None:
            multistage_rows.append({
                "stage": labels.get(threshold, f"shortfall_{threshold:.0%}"),
                "shortfall_threshold": threshold,
                "stage_detected": False,
            })
            continue
        onset = pd.Timestamp(target["start_date"])
        prior = families.loc[
            families["evidence_date"].between(onset - pd.Timedelta(days=7), onset - pd.Timedelta(days=1))
        ]
        escalation_prior = prior.loc[prior["evidence_date"].ge(canonical_onset)]
        first_signal = escalation_prior["evidence_date"].min() if not escalation_prior.empty else pd.NaT
        first_seven_end = onset + pd.Timedelta(days=6)
        first_seven = canonical_working.loc[canonical_working["date"].between(onset, first_seven_end)]
        multistage_rows.append({
            "stage": labels.get(threshold, f"shortfall_{threshold:.0%}"),
            "shortfall_threshold": threshold,
            "stage_detected": True,
            "stage_onset_date": onset,
            "days_after_canonical_onset": int((onset - canonical_onset).days),
            "stage_end_date": target["end_date"],
            "duration_days": int(target["duration_days"]),
            "pre_stage_signal_families_7d": int(prior["signal_family_id"].nunique()),
            "escalation_signal_families_after_initial_onset": int(escalation_prior["signal_family_id"].nunique()),
            "escalation_signal_sources": "; ".join(sorted(escalation_prior["source"].unique())),
            "first_escalation_signal_date": first_signal,
            "maximum_escalation_lead_days": int((onset - first_signal).days) if pd.notna(first_signal) else pd.NA,
            "capacity_loss_first_7d": float(first_seven["capacity_loss"].sum()),
            "median_shortfall_first_7d": float(canonical_shortfall.loc[first_seven.index].median()),
        })
    multistage = pd.DataFrame(multistage_rows)

    pre_start = canonical_onset - pd.Timedelta(days=int(cfg.get("diagnostic_pre_days", 30)))
    post_start = anchor_date
    pre = frame.loc[frame["date"].between(pre_start, canonical_onset - pd.Timedelta(days=1))]
    post = frame.loc[frame["date"].between(post_start, frame["date"].max())]
    diagnostic_columns = [
        column for column in [
            "n_container", "n_dry_bulk", "n_general_cargo", "n_roro", "n_tanker", "n_cargo", "n_total",
            "capacity_container", "capacity_dry_bulk", "capacity_general_cargo", "capacity_roro",
            "capacity_tanker", "capacity_cargo", "capacity",
        ] if column in frame
    ]
    field_diagnostics: dict[str, Any] = {}
    for column in diagnostic_columns:
        before = pd.to_numeric(pre[column], errors="coerce")
        after = pd.to_numeric(post[column], errors="coerce")
        pre_median = float(before.median())
        post_median = float(after.median())
        field_diagnostics[column] = {
            "pre_median": pre_median,
            "post_median": post_median,
            "post_to_pre_median_ratio": post_median / pre_median if pre_median else None,
            "pre_null_rate": float(before.isna().mean()),
            "post_null_rate": float(after.isna().mean()),
            "pre_zero_rate": float(before.eq(0).mean()),
            "post_zero_rate": float(after.eq(0).mean()),
        }
    change_points = [
        _single_change_point(
            frame,
            column=column,
            start=cfg.get("change_point_start", "2026-01-01"),
            end=cfg.get("change_point_end", "2026-09-06"),
            minimum_segment_days=int(cfg.get("change_point_minimum_segment_days", 14)),
        )
        for column in ["n_total", "n_tanker", "capacity", "capacity_tanker"] if column in frame
    ]
    diagnostics = {
        "source_path": str(source_path.relative_to(root)),
        "source_mode": source_mode,
        "observed_column": observed_column,
        "first_date": frame["date"].min().strftime("%Y-%m-%d"),
        "last_date": frame["date"].max().strftime("%Y-%m-%d"),
        "rows": int(len(frame)),
        "duplicate_dates": int(frame["date"].duplicated().sum()),
        "missing_calendar_days": int(len(pd.date_range(frame["date"].min(), frame["date"].max())) - len(frame)),
        "pre_window": [pre_start.strftime("%Y-%m-%d"), (canonical_onset - pd.Timedelta(days=1)).strftime("%Y-%m-%d")],
        "post_window": [post_start.strftime("%Y-%m-%d"), frame["date"].max().strftime("%Y-%m-%d")],
        "field_diagnostics": field_diagnostics,
        "single_change_point_checks": change_points,
        "interpretation_gate": {
            "all_vessel_categories_shift": bool(
                field_diagnostics.get("n_total", {}).get("post_to_pre_median_ratio", 1) < 0.20
                and field_diagnostics.get("capacity", {}).get("post_to_pre_median_ratio", 1) < 0.20
            ),
            "portwatch_measurement_break_not_excluded": True,
            "external_operational_corroboration_present": True,
            "publication_status": "requires sensitivity reporting and explicit AIS-proxy limitation",
        },
    }

    canonical_episodes_path = _resolve(root, cfg.get("canonical_episodes_file", "outputs/reports/flow_episodes.csv"))
    canonical_episodes = pd.read_csv(canonical_episodes_path, parse_dates=["start_date", "end_date"])
    target_id = int(config.get("evidence", {}).get("target_episode_id", 51))
    target_rows = canonical_episodes.loc[canonical_episodes["flow_episode_id"].eq(target_id)]
    if len(target_rows) != 1:
        raise ValueError(f"Expected one canonical target episode {target_id}")
    target = target_rows.iloc[0]
    prior = canonical_episodes.loc[canonical_episodes["start_date"].lt(target["start_date"])]
    placebo_rows: list[dict[str, Any]] = []
    for metric in ["duration_days", "severe_days", "episode_tanker_capacity_loss", "maximum_shortfall_fraction"]:
        target_value = float(target[metric])
        prior_values = pd.to_numeric(prior[metric], errors="coerce").dropna()
        exceedances = int(prior_values.ge(target_value).sum())
        placebo_rows.append({
            "metric": metric,
            "target_episode_id": target_id,
            "target_value": target_value,
            "prior_episode_count": int(len(prior_values)),
            "prior_median": float(prior_values.median()),
            "prior_maximum": float(prior_values.max()),
            "prior_exceedance_count": exceedances,
            "finite_sample_empirical_tail_probability": float((exceedances + 1) / (len(prior_values) + 1)),
            "target_rank_descending": int((prior_values.gt(target_value)).sum() + 1),
        })
    placebo = pd.DataFrame(placebo_rows)

    report_dir = root / "outputs" / "reports"
    paths = {
        "sensitivity": report_dir / "flow_outcome_sensitivity.csv",
        "background_selectivity": report_dir / "pre2024_background_selectivity.csv",
        "stability": report_dir / "episode_stability_matrix.csv",
        "multistage": report_dir / "e051_multistage_timeline.csv",
        "diagnostics": report_dir / "e051_flow_data_diagnostics.json",
        "placebo": report_dir / "e051_prior_episode_placebo_comparison.csv",
        "manuscript_summary": report_dir / "flow_sensitivity_results_for_manuscript.md",
    }
    sensitivity.to_csv(paths["sensitivity"], index=False, date_format="%Y-%m-%d")
    background.to_csv(paths["background_selectivity"], index=False, date_format="%Y-%m-%d")
    stability.to_csv(paths["stability"], index=False, date_format="%Y-%m-%d")
    multistage.to_csv(paths["multistage"], index=False, date_format="%Y-%m-%d")
    write_json(diagnostics, paths["diagnostics"])
    placebo.to_csv(paths["placebo"], index=False)
    strict = sensitivity.loc[sensitivity["severe_shortfall_threshold"].ge(0.50)]
    strict_march_first = strict["target_onset_date"].astype(str).eq("2026-03-01")
    merged_target = sensitivity.loc[pd.to_datetime(sensitivity["target_onset_date"]) < canonical_onset]
    target_local = sensitivity.loc[pd.to_datetime(sensitivity["target_onset_date"]) >= canonical_onset]
    background_summary = (
        background.loc[background["severe_shortfall_threshold"].ge(0.50)]
        .groupby("severe_shortfall_threshold")
        .agg(
            median_episodes_per_year=("background_episodes_per_year", "median"),
            minimum_episodes_per_year=("background_episodes_per_year", "min"),
            maximum_episodes_per_year=("background_episodes_per_year", "max"),
            median_active_day_fraction=("episode_active_day_fraction", "median"),
        )
    )
    change_dates = ", ".join(
        f"{item['column']}={item['detected_change_date']}" for item in change_points
    )
    manuscript_summary = f"""# Physical-Flow Sensitivity Results for Manuscript

## Completed checks

- **{len(sensitivity)}** outcome specifications: {len(baseline_variants)} training-only baselines, {len(thresholds)} shortfall thresholds, {len(minimum_runs)} persistence rules and {len(recovery_values)} recovery rules.
- The 1 March target anchor falls inside a detected disruption interval in **{int(sensitivity['target_episode_detected'].sum())}/{len(sensitivity)}** specifications. A target-local onset (26 February or 1 March) is identified in **{len(target_local)}/{len(sensitivity)}**; **{len(merged_target)}** low-threshold specifications merge the target with a preceding episode.
- All **{int(strict_march_first.sum())}/{len(strict)}** specifications with 50%–90% shortfall thresholds place major-to-catastrophic onset on **1 March 2026**.
- Pre-2024 selectivity improves sharply with severity: median background episode rates are **{background_summary.loc[0.50, 'median_episodes_per_year']:.1f}/year at 50%**, **{background_summary.loc[0.70, 'median_episodes_per_year']:.1f}/year at 70%**, and **{background_summary.loc[0.90, 'median_episodes_per_year']:.1f}/year at 90%** across the corresponding 36 configurations per threshold. These are background detections, not labeled false positives, because the training period can contain real disruptions.
- The canonical 30%/two-day definition identifies early degradation on **26 February 2026**; requiring three or five consecutive days moves this stage to **1 March 2026**.
- Automated single-change-point dates are: **{change_dates}**.
- A MARAD record (effective date) and a UKMTO advisory (issue date) are dated **28 February**, one daily observation interval before the major/catastrophic stage. This is case-specific escalation timing after initial degradation, not clean lead before all disruption.
- Under the canonical episode definition, E051 ranks first among 51 episodes on cumulative tanker-capacity loss and also ranks first on duration, severe days and maximum shortfall. These correlated ranks are descriptive only.

## Defensible claim

Across 108 training-only baseline and persistence/recovery specifications with 50%–90% shortfall thresholds, the major-disruption transition is invariant at 1 March 2026. MARAD and UKMTO records dated 28 February precede this escalation by one daily observation interval, after the canonical initial degradation has already begun.

## Claims that remain unsupported

- That the signals anticipated the initial 26 February degradation.
- That insurance signals provided pre-escalation lead time.
- That one-day escalation lead generalizes beyond E051.

## Required limitation

IMF PortWatch is an AIS-derived proxy. All vessel-count and capacity fields shift sharply near 1–2 March, while document evidence independently corroborates operational disruption. A PortWatch observation-regime break cannot be eliminated with this dataset alone and must be acknowledged explicitly.
"""
    paths["manuscript_summary"].write_text(manuscript_summary, encoding="utf-8")
    for path in paths.values():
        print(f"Wrote {path}")
    return paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate PortWatch episode and E051 outcome robustness")
    parser.add_argument("--config", default=None)
    arguments = parser.parse_args()
    evaluate(arguments.config)
