from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pandas as pd

from .utils import ensure_dirs, load_config, project_root


SOURCE_DEFINITIONS = {
    "MARAD": {
        "url": "https://www.maritime.dot.gov/msci-alerts",
        "criteria": "Cancelled Alerts: leave geography blank; apply the exact date window; repeat keywords Hormuz, Persian Gulf, Gulf of Oman, Arabian Gulf, Iran; save the result page and every relevant alert PDF.",
    },
    "UKMTO_WARNING": {
        "url": "https://www.ukmto.org/ukmto-products/warnings/{year}",
        "criteria": "Open every month intersecting the exact date window; save the month/list capture and every warning whose issue date is inside the window. Keep zero-result month captures.",
    },
    "UKMTO_ADVISORY": {
        "url": "https://www.ukmto.org/ukmto-products/advisories/{year}",
        "criteria": "Open every month intersecting the exact date window; save the month/list capture and every advisory whose issue date is inside the window. Keep zero-result month captures.",
    },
    "IUA_JWC_LMA": {
        "url": "https://lmalloyds.com/specialist-areas/underwriting/listed-areas/",
        "criteria": "Inspect Listed Areas, Joint War Committee minutes and linked JWLA circulars issued in the exact window; save direct LMA/IUA records plus a dated zero-result capture when none exists.",
    },
    "GARD": {
        "url": "https://gard.no/",
        "criteria": "Use Gard site search with Hormuz, Persian Gulf, Gulf of Oman, war risk, Iran and navigational warning; restrict manually to the exact window; save direct Gard pages/PDFs or a dated zero-result capture.",
    },
}


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def build_tasks(manifest: pd.DataFrame) -> pd.DataFrame:
    required = {
        "episode_cluster_id", "onset_date", "phase4_split", "pre_window_start",
        "pre_window_end", "onset_window_start", "onset_window_end", "dependency_group",
    }
    missing = required.difference(manifest.columns)
    if missing:
        raise ValueError(f"Phase 4 manifest is missing columns: {sorted(missing)}")
    if manifest["episode_cluster_id"].duplicated().any():
        raise ValueError("episode_cluster_id values must be unique")
    rows: list[dict[str, object]] = []
    for episode in manifest.itertuples(index=False):
        for window_type, start_name, end_name in [
            ("pre_onset", "pre_window_start", "pre_window_end"),
            ("onset", "onset_window_start", "onset_window_end"),
        ]:
            date_from = pd.Timestamp(getattr(episode, start_name))
            date_to = pd.Timestamp(getattr(episode, end_name))
            for source_class, definition in SOURCE_DEFINITIONS.items():
                years = list(range(date_from.year, date_to.year + 1))
                if "{year}" in definition["url"]:
                    search_url = " | ".join(definition["url"].format(year=year) for year in years)
                else:
                    search_url = definition["url"]
                task_id = f"{episode.episode_cluster_id}_{source_class}_{window_type}"
                relative_dir = f"{episode.episode_cluster_id}/{source_class}/{window_type}"
                rows.append({
                    "task_id": task_id,
                    "episode_cluster_id": episode.episode_cluster_id,
                    "phase4_split": episode.phase4_split,
                    "dependency_group": episode.dependency_group,
                    "source_class": source_class,
                    "window_type": window_type,
                    "date_from": date_from.strftime("%Y-%m-%d"),
                    "date_to": date_to.strftime("%Y-%m-%d"),
                    "year": ",".join(str(year) for year in years),
                    "search_url": search_url,
                    "search_criteria": definition["criteria"],
                    "evidence_directory": relative_dir,
                    "required_artifact": "Direct official document(s), or a PDF archive/list capture proving zero results for this source-window.",
                    "status": "pending",
                })
    return pd.DataFrame(rows)


def seed_existing_e051(root: Path, evidence_root: Path, metadata_path: Path) -> int:
    """Reuse the audited Phase 3 E051 package without auto-accepting its coding."""
    legacy_root = root / "data" / "evidence" / "E051"
    legacy_registry_path = root / "outputs" / "reports" / "e051_evidence_registry.csv"
    if not legacy_root.exists() or not legacy_registry_path.exists():
        return 0
    existing = pd.read_csv(metadata_path, dtype=str).fillna("") if metadata_path.exists() else pd.DataFrame()
    if not existing.empty:
        return 0
    legacy = pd.read_csv(legacy_registry_path, dtype=str).fillna("")
    rows: list[dict[str, object]] = []
    for record in legacy.to_dict("records"):
        if str(record.get("is_primary_representation", "")).lower() != "true":
            continue
        relative = str(record["relative_path"])
        name = Path(relative).name
        source = record.get("source", "")
        doc_type = record.get("document_type", "")
        evidence_date = pd.to_datetime(record.get("evidence_date"), errors="coerce")
        zero_capture = False
        window: str | None = None
        source_class: str | None = None

        if source == "MARAD":
            source_class = "MARAD"
            if "Search_PreOnset" in name:
                window, zero_capture = "pre_onset", True
            elif doc_type == "maritime_alert" and pd.notna(evidence_date) and pd.Timestamp("2026-02-26") <= evidence_date <= pd.Timestamp("2026-03-12"):
                window = "onset"
        elif source == "UKMTO" and doc_type == "warning":
            source_class = "UKMTO_WARNING"
            if pd.notna(evidence_date) and pd.Timestamp("2026-02-26") <= evidence_date <= pd.Timestamp("2026-03-12"):
                window = "onset"
        elif source == "UKMTO" and doc_type == "advisory":
            source_class = "UKMTO_ADVISORY"
            if pd.notna(evidence_date) and pd.Timestamp("2026-01-27") <= evidence_date <= pd.Timestamp("2026-02-25"):
                window = "pre_onset"
            elif pd.notna(evidence_date) and pd.Timestamp("2026-02-26") <= evidence_date <= pd.Timestamp("2026-03-12"):
                window = "onset"
        elif source == "UKMTO" and doc_type == "archive_capture" and "Warnings_PreOnset" in name:
            source_class, window, zero_capture = "UKMTO_WARNING", "pre_onset", True
        elif source == "Gard" and pd.notna(evidence_date) and pd.Timestamp("2026-02-26") <= evidence_date <= pd.Timestamp("2026-03-12"):
            source_class, window = "GARD", "onset"
        elif source == "IUA-JWC/LMA" and pd.notna(evidence_date) and pd.Timestamp("2026-02-26") <= evidence_date <= pd.Timestamp("2026-03-12"):
            source_class, window = "IUA_JWC_LMA", "onset"

        if source_class is None or window is None:
            continue
        source_path = legacy_root / relative
        if not source_path.is_file():
            continue
        destination_dir = evidence_root / "E051" / source_class / window
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / name
        if not destination.exists():
            shutil.copy2(source_path, destination)
        relationship = record.get("evidence_relationship", "")
        is_update = relationship == "update_same_family"
        family = "" if zero_capture else record.get("signal_family_id", "")
        rows.append({
            "episode_cluster_id": "E051",
            "task_id": f"E051_{source_class}_{window}",
            "relative_path": destination.relative_to(evidence_root).as_posix(),
            "source_class": source_class,
            "document_id": record.get("document_id", ""),
            "signal_family_id": family,
            "document_role": "zero_result_capture" if zero_capture else ("update" if is_update else "positive_signal"),
            "issue_date": record.get("issue_date", ""),
            "publication_date": record.get("publication_date", ""),
            "effective_date": record.get("effective_date", ""),
            "expiry_date": "",
            "geographic_scope": record.get("geographic_scope", ""),
            "window_type": window,
            "is_zero_result_capture": str(zero_capture).lower(),
            "is_direct_official": "true",
            "is_update": str(is_update).lower(),
            "parent_family_id": family if is_update else "",
            "reviewer_1": "",
            "reviewer_2": "",
            "adjudication_status": "pending",
            "notes": "Migrated from the audited Phase 3 E051 package; review before acceptance.",
        })
    if rows:
        columns = list(pd.read_csv(metadata_path, nrows=0).columns)
        pd.DataFrame(rows).reindex(columns=columns).to_csv(metadata_path, index=False)
    return len(rows)


def prepare(config_path: str | Path | None = None) -> tuple[Path, Path]:
    config = load_config(config_path)
    cfg = config.get("phase4", {})
    root = project_root()
    ensure_dirs()
    manifest_path = _resolve(root, cfg.get("manifest_file", "data/manual/phase4_episode_manifest.csv"))
    metadata_path = _resolve(root, cfg.get("metadata_file", "data/manual/phase4_evidence_metadata.csv"))
    evidence_root = _resolve(root, cfg.get("evidence_root", "data/evidence/phase4"))
    manifest = pd.read_csv(manifest_path)
    tasks = build_tasks(manifest)

    for task in tasks.itertuples(index=False):
        directory = evidence_root / task.evidence_directory
        directory.mkdir(parents=True, exist_ok=True)
        placeholder = directory / "PLACE_EVIDENCE_HERE.txt"
        if not placeholder.exists():
            placeholder.write_text(
                f"Task: {task.task_id}\nWindow: {task.date_from} to {task.date_to}\nURL: {task.search_url}\n\n{task.search_criteria}\n",
                encoding="utf-8",
            )

    seeded = seed_existing_e051(root, evidence_root, metadata_path)

    report_dir = root / "outputs" / "reports"
    tasks_path = report_dir / "phase4_collection_tasks.csv"
    status_path = report_dir / "phase4_collection_status.csv"
    tasks.to_csv(tasks_path, index=False)
    tasks[["task_id", "episode_cluster_id", "source_class", "window_type", "status"]].to_csv(status_path, index=False)
    print(f"Wrote {tasks_path} ({len(tasks)} source-window tasks)")
    print(f"Created evidence scaffold under {evidence_root}")
    if seeded:
        print(f"Reused {seeded} E051 evidence files as pending-review metadata rows")
    return tasks_path, status_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare Phase 4 multi-episode evidence collection")
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    prepare(args.config)
