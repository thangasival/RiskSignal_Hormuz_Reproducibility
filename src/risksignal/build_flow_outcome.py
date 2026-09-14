from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .utils import ensure_dirs, load_config, project_root, write_json


def _cyclic_distance(day: pd.Series, target: int, period: int = 366) -> pd.Series:
    direct = (day - target).abs()
    return np.minimum(direct, period - direct)


def estimate_expected_capacity(
    frame: pd.DataFrame,
    *,
    observed_column: str,
    baseline_end: str | pd.Timestamp,
    seasonal_half_window_days: int = 15,
) -> tuple[pd.Series, dict[str, Any]]:
    """Estimate expected capacity using only the pre-specified baseline period.

    A circular day-of-year median smooths across a +/- window. A robust weekday
    multiplier is then estimated from baseline residual ratios. No post-baseline
    observation contributes to either component.
    """
    dates = pd.to_datetime(frame["date"], errors="coerce")
    observed = pd.to_numeric(frame[observed_column], errors="coerce")
    cutoff = pd.Timestamp(baseline_end)
    baseline_mask = dates.le(cutoff) & observed.notna()
    baseline = pd.DataFrame(
        {
            "date": dates.loc[baseline_mask],
            "observed": observed.loc[baseline_mask],
        }
    )
    if len(baseline) < 365:
        raise ValueError(
            f"Expected at least 365 baseline observations, found {len(baseline)}"
        )
    baseline["day_of_year"] = baseline["date"].dt.dayofyear
    baseline["weekday"] = baseline["date"].dt.dayofweek
    fallback = float(baseline["observed"].median())
    if not np.isfinite(fallback) or fallback <= 0:
        raise ValueError("Baseline tanker capacity has no positive finite median")

    seasonal: dict[int, float] = {}
    for target_day in range(1, 367):
        distance = _cyclic_distance(baseline["day_of_year"], target_day)
        sample = baseline.loc[
            distance.le(seasonal_half_window_days), "observed"
        ]
        value = float(sample.median()) if not sample.empty else fallback
        seasonal[target_day] = value if np.isfinite(value) and value > 0 else fallback

    baseline_seasonal = baseline["day_of_year"].map(seasonal).astype(float)
    ratio = baseline["observed"] / baseline_seasonal.replace(0, np.nan)
    weekday_factor = ratio.groupby(baseline["weekday"]).median().to_dict()
    for weekday in range(7):
        weekday_factor.setdefault(weekday, 1.0)
    centre = float(np.median(list(weekday_factor.values())))
    if not np.isfinite(centre) or centre <= 0:
        centre = 1.0
    weekday_factor = {
        int(day): float(np.clip(value / centre, 0.5, 1.5))
        for day, value in weekday_factor.items()
    }

    all_day_of_year = dates.dt.dayofyear
    all_weekday = dates.dt.dayofweek
    expected = (
        all_day_of_year.map(seasonal).astype(float)
        * all_weekday.map(weekday_factor).astype(float)
    )
    metadata = {
        "method": "training-only circular day-of-year median with weekday multiplier",
        "baseline_end": cutoff.strftime("%Y-%m-%d"),
        "baseline_observations": int(len(baseline)),
        "seasonal_half_window_days": int(seasonal_half_window_days),
        "baseline_observed_median": fallback,
        "weekday_factors": weekday_factor,
    }
    return expected, metadata


def identify_episodes(
    severe: Iterable[bool],
    *,
    minimum_consecutive_severe_days: int = 2,
    recovery_days: int = 3,
) -> tuple[np.ndarray, np.ndarray]:
    """Return episode IDs and onset flags.

    An episode is confirmed when the required number of consecutive severe days
    begins. It remains active across short recoveries and closes only after the
    specified number of consecutive non-severe days. Final recovery days are
    excluded from the episode.
    """
    values = np.asarray(list(severe), dtype=bool)
    n = len(values)
    episode_ids = np.zeros(n, dtype=int)
    onset = np.zeros(n, dtype=int)
    active = False
    episode = 0
    recovery_run = 0

    for index in range(n):
        if not active:
            stop = index + minimum_consecutive_severe_days
            confirmed = stop <= n and bool(values[index:stop].all())
            if not confirmed:
                continue
            episode += 1
            active = True
            onset[index] = 1

        if values[index]:
            recovery_run = 0
            episode_ids[index] = episode
        else:
            recovery_run += 1
            episode_ids[index] = episode
            if recovery_run >= recovery_days:
                episode_ids[index - recovery_run + 1 : index + 1] = 0
                active = False
                recovery_run = 0

    return episode_ids, onset


def add_future_onset_targets(
    frame: pd.DataFrame, horizons: Iterable[int]
) -> pd.DataFrame:
    out = frame.copy()
    maximum_date = out["date"].max()
    for horizon in sorted({int(value) for value in horizons}):
        if horizon <= 0:
            raise ValueError("Forecast horizons must be positive")
        future_onsets = pd.concat(
            [out["episode_onset"].shift(-lag) for lag in range(1, horizon + 1)],
            axis=1,
        ).max(axis=1, skipna=True)
        fully_observed = out["date"].le(maximum_date - pd.Timedelta(days=horizon))
        target = pd.Series(np.nan, index=out.index, dtype=float)
        target.loc[fully_observed] = future_onsets.loc[fully_observed].astype(int)
        out[f"target_flow_episode_onset_next_{horizon}d"] = target
    return out


def construct_flow_outcomes(
    frame: pd.DataFrame,
    *,
    observed_column: str = "capacity_tanker",
    baseline_end: str = "2023-12-31",
    seasonal_half_window_days: int = 15,
    severe_shortfall_fraction: float = 0.30,
    minimum_consecutive_severe_days: int = 2,
    recovery_days: int = 3,
    horizons: Iterable[int] = (1, 3, 7),
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    out = frame.copy()
    if "date" not in out or observed_column not in out:
        raise ValueError(f"Input must contain date and {observed_column}")
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    out[observed_column] = pd.to_numeric(out[observed_column], errors="coerce")
    out = out.dropna(subset=["date", observed_column]).sort_values("date")
    if out["date"].duplicated().any():
        raise ValueError("Flow outcome input contains duplicate dates")
    expected_dates = pd.date_range(out["date"].min(), out["date"].max(), freq="D")
    if len(expected_dates) != len(out) or not out["date"].reset_index(drop=True).equals(
        pd.Series(expected_dates)
    ):
        raise ValueError("Flow outcome input must contain one row for every calendar day")
    if not 0 < severe_shortfall_fraction < 1:
        raise ValueError("severe_shortfall_fraction must be between zero and one")

    expected, baseline_metadata = estimate_expected_capacity(
        out,
        observed_column=observed_column,
        baseline_end=baseline_end,
        seasonal_half_window_days=seasonal_half_window_days,
    )
    out["expected_tanker_capacity"] = expected.to_numpy()
    out["tanker_capacity_loss"] = np.maximum(
        0.0, out["expected_tanker_capacity"] - out[observed_column]
    )
    out["tanker_capacity_shortfall_fraction"] = (
        out["tanker_capacity_loss"] / out["expected_tanker_capacity"].replace(0, np.nan)
    )
    out["severe_flow_shortfall"] = (
        out["tanker_capacity_shortfall_fraction"].ge(severe_shortfall_fraction)
    ).astype(int)
    episode_ids, onset = identify_episodes(
        out["severe_flow_shortfall"].astype(bool),
        minimum_consecutive_severe_days=minimum_consecutive_severe_days,
        recovery_days=recovery_days,
    )
    out["flow_episode_id"] = episode_ids
    out["episode_onset"] = onset
    out = add_future_onset_targets(out, horizons)

    episode_rows: list[dict[str, Any]] = []
    for episode_id, group in out.loc[out["flow_episode_id"].gt(0)].groupby(
        "flow_episode_id"
    ):
        episode_rows.append(
            {
                "flow_episode_id": int(episode_id),
                "start_date": group["date"].min(),
                "end_date": group["date"].max(),
                "duration_days": int(len(group)),
                "severe_days": int(group["severe_flow_shortfall"].sum()),
                "episode_tanker_capacity_loss": float(
                    group["tanker_capacity_loss"].sum()
                ),
                "maximum_shortfall_fraction": float(
                    group["tanker_capacity_shortfall_fraction"].max()
                ),
            }
        )
    episodes = pd.DataFrame(episode_rows)
    if not episodes.empty:
        loss_map = episodes.set_index("flow_episode_id")[
            "episode_tanker_capacity_loss"
        ]
        out["episode_tanker_capacity_loss"] = out["flow_episode_id"].map(loss_map)
    else:
        out["episode_tanker_capacity_loss"] = np.nan

    metadata = {
        "observed_column": observed_column,
        "severe_shortfall_fraction": float(severe_shortfall_fraction),
        "minimum_consecutive_severe_days": int(minimum_consecutive_severe_days),
        "recovery_days": int(recovery_days),
        "forecast_horizons_days": sorted({int(value) for value in horizons}),
        "baseline": baseline_metadata,
    }
    return out.reset_index(drop=True), episodes, metadata


def _split_name(date: pd.Timestamp, validation_start: pd.Timestamp, test_start: pd.Timestamp) -> str:
    if date >= test_start:
        return "test"
    if date >= validation_start:
        return "validation"
    return "training"


def build(config_path: str | Path | None = None) -> tuple[Path, Path, Path]:
    config = load_config(config_path)
    cfg = config.get("flow_outcome", {})
    root = project_root()
    ensure_dirs()
    source_path = root / str(
        cfg.get("source_file", "data/raw/portwatch_hormuz_daily.csv")
    )
    if not source_path.exists():
        raise FileNotFoundError(
            f"Missing {source_path}; run the portwatch step before flow_outcome"
        )

    outcomes, episodes, metadata = construct_flow_outcomes(
        pd.read_csv(source_path),
        observed_column=str(cfg.get("observed_column", "capacity_tanker")),
        baseline_end=str(cfg.get("baseline_end", "2023-12-31")),
        seasonal_half_window_days=int(cfg.get("seasonal_half_window_days", 15)),
        severe_shortfall_fraction=float(cfg.get("severe_shortfall_fraction", 0.30)),
        minimum_consecutive_severe_days=int(
            cfg.get("minimum_consecutive_severe_days", 2)
        ),
        recovery_days=int(cfg.get("recovery_days", 3)),
        horizons=cfg.get("forecast_horizons_days", [1, 3, 7]),
    )
    validation_start = pd.Timestamp(cfg.get("validation_start", "2024-01-01"))
    test_start = pd.Timestamp(cfg.get("test_start", "2026-01-01"))
    if not episodes.empty:
        episodes["split"] = episodes["start_date"].apply(
            lambda value: _split_name(pd.Timestamp(value), validation_start, test_start)
        )

    outcome_path = root / "data" / "processed" / "hormuz_flow_outcomes.csv"
    episode_path = root / "outputs" / "reports" / "flow_episodes.csv"
    report_path = root / "outputs" / "reports" / "flow_outcome_report.json"
    outcomes.to_csv(outcome_path, index=False, date_format="%Y-%m-%d")
    episodes.to_csv(episode_path, index=False, date_format="%Y-%m-%d")

    split_counts = (
        episodes["split"].value_counts().to_dict() if not episodes.empty else {}
    )
    total_episodes = int(len(episodes))
    test_episodes = int(split_counts.get("test", 0))
    report = {
        **metadata,
        "source_path": str(source_path.relative_to(root)),
        "rows": int(len(outcomes)),
        "first_date": outcomes["date"].min().strftime("%Y-%m-%d"),
        "last_date": outcomes["date"].max().strftime("%Y-%m-%d"),
        "severe_days": int(outcomes["severe_flow_shortfall"].sum()),
        "episode_count": total_episodes,
        "episode_count_by_split": split_counts,
        "test_episode_count": test_episodes,
        "episode_density_gate": "pass"
        if total_episodes >= 10 and test_episodes >= 3
        else "fail",
        "episode_density_gate_rule": "at least 10 total episodes and at least 3 test episodes",
        "primary_horizon_days": int(cfg.get("primary_horizon_days", 7)),
        "outcome_path": str(outcome_path.relative_to(root)),
        "episode_path": str(episode_path.relative_to(root)),
    }
    write_json(report, report_path)
    print(f"Wrote {outcome_path}")
    print(f"Wrote {episode_path}")
    print(f"Wrote {report_path}")
    print(
        f"Episode-density gate: {report['episode_density_gate']} "
        f"({total_episodes} total; {test_episodes} test)"
    )
    return outcome_path, episode_path, report_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build physical Hormuz tanker-flow outcomes and disruption episodes"
    )
    parser.add_argument("--config", default=None)
    arguments = parser.parse_args()
    build(arguments.config)
