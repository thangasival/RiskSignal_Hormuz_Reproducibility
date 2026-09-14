from __future__ import annotations
import argparse, os, subprocess, sys
from pathlib import Path

STEPS = {
    "phase4_registry": "risksignal.build_multi_episode_registry",
    "phase4_evaluate": "risksignal.evaluate_multi_episode",
    "gate_robustness": "risksignal.evaluate_gate_robustness",
    "phase4_figures": "risksignal.make_phase4_figures",
    "flow_sensitivity": "risksignal.evaluate_flow_sensitivity",
    "flow_sensitivity_figures": "risksignal.make_flow_sensitivity_figures",
}
DEFAULT_STEPS = ["phase4_evaluate", "gate_robustness", "phase4_figures", "flow_sensitivity", "flow_sensitivity_figures"]

def run_step(module: str, config: str | None) -> None:
    root = Path(__file__).resolve().parent
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    cmd = [sys.executable, "-m", module]
    if config:
        cmd += ["--config", config]
    print("\n>>>", " ".join(cmd))
    subprocess.run(cmd, cwd=root, env=env, check=True)

def main() -> None:
    ap = argparse.ArgumentParser(description="Offline RiskSignal reproducibility runner. No collection/download steps are included.")
    ap.add_argument("--config", default="config/default_config.yaml")
    ap.add_argument("--steps", nargs="*", choices=list(STEPS), default=DEFAULT_STEPS)
    args = ap.parse_args()
    if "phase4_registry" in args.steps and not (Path(__file__).resolve().parent / "data/evidence/phase4").exists():
        raise SystemExit("phase4_registry requires the local third-party evidence corpus in data/evidence/phase4, which is intentionally not distributed in this public release.")
    for step in args.steps:
        run_step(STEPS[step], args.config)

if __name__ == "__main__":
    main()
