#!/usr/bin/env python3
"""
Bootstrap Training Script — Smart Campus ML
============================================
Runs the full ML pipeline bootstrap for the 2024-2025 base models:

  1. Generate synthetic training datasets (canteen, library, energy)
  2. Run all three Kedro pipelines (feature engineering → XGBoost training)
  3. Log experiments and register models in MLflow
  4. Auto-promote each model's latest version to "Production" stage

Can be run in two ways:
  • Local (MLflow on localhost:5000):
      MLFLOW_TRACKING_URI=http://localhost:5000 python ml/bootstrap_training.py
  • Inside the ml-training Docker container:
      docker exec campus-ml-training python /opt/campus/ml/bootstrap_training.py

Usage:
    python ml/bootstrap_training.py [--skip-generate]
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import subprocess
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE    = Path(__file__).parent.resolve()
_ROOT    = _HERE.parent
_KEDRO   = _HERE / "kedro_project"
_DATASETS = _HERE / "datasets"

sys.path.insert(0, str(_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("bootstrap")

# ── MLflow ────────────────────────────────────────────────────────────────────
MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")

# Models to promote after training
MODEL_NAMES = [
    "campus_canteen_congestion",
    "campus_library_congestion",
    "campus_energy_forecast",
]


# =============================================================================
# Step 1 — Generate datasets
# =============================================================================

def generate_datasets():
    log.info("=" * 60)
    log.info("STEP 1: Generating synthetic training datasets (2024-2025)")
    log.info("=" * 60)

    script = _HERE / "generate_datasets.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(_ROOT),
        check=False,
    )
    if result.returncode != 0:
        log.error("Dataset generation failed — aborting.")
        sys.exit(1)

    expected = [
        _DATASETS / "canteen_congestion_2024_2025.csv",
        _DATASETS / "library_congestion_2024_2025.csv",
        _DATASETS / "energy_forecast_2024_2025.csv",
    ]
    for p in expected:
        if not p.exists():
            log.error("Expected dataset not found: %s", p)
            sys.exit(1)
        log.info("  [OK] %s  (%.1f MB)", p.name, p.stat().st_size / 1e6)


# =============================================================================
# Step 2 — Run Kedro pipelines
# =============================================================================

def run_kedro_pipelines():
    log.info("=" * 60)
    log.info("STEP 2: Running Kedro ML pipelines")
    log.info("=" * 60)

    env = {
        **os.environ,
        "MLFLOW_TRACKING_URI": MLFLOW_TRACKING_URI,
        "PYTHONWARNINGS": "ignore",
        "PYTHONPATH": str(_ROOT),
    }

    pipelines = [
        ("canteen_congestion", "Canteen Congestion XGBoost"),
        ("library_congestion", "Library Congestion XGBoost"),
        ("energy_forecast",    "Energy Forecast XGBoost"),
    ]

    for pipeline_name, description in pipelines:
        log.info("  Running pipeline: %s", description)
        result = subprocess.run(
            [sys.executable, "-W", "ignore", "-m", "kedro", "run",
             "--pipeline", pipeline_name],
            cwd=str(_KEDRO),
            env=env,
            check=False,
        )
        if result.returncode != 0:
            log.error("Pipeline '%s' failed — aborting.", pipeline_name)
            sys.exit(1)
        log.info("  [OK] %s complete.", description)


# =============================================================================
# Step 3 — Promote latest model version to Production
# =============================================================================

def promote_models():
    log.info("=" * 60)
    log.info("STEP 3: Promoting latest model versions to Production")
    log.info("=" * 60)

    import mlflow
    from mlflow.tracking import MlflowClient

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    client = MlflowClient()

    for model_name in MODEL_NAMES:
        try:
            versions = client.get_latest_versions(model_name)
            if not versions:
                log.warning("  No versions found for '%s' — skipping.", model_name)
                continue

            # Pick the newest version by version number
            latest = max(versions, key=lambda v: int(v.version))
            version_num = latest.version

            client.transition_model_version_stage(
                name=model_name,
                version=version_num,
                stage="Production",
                archive_existing_versions=True,
            )
            log.info(
                "  [OK] '%s' v%s -> Production  (run_id: %s)",
                model_name, version_num, latest.run_id,
            )
        except Exception as e:
            log.error("  ✗ Failed to promote '%s': %s", model_name, e)
            sys.exit(1)


# =============================================================================
# Step 4 — Health summary
# =============================================================================

def print_summary():
    log.info("=" * 60)
    log.info("STEP 4: Verifying Production models in MLflow")
    log.info("=" * 60)

    import mlflow
    from mlflow.tracking import MlflowClient

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    client = MlflowClient()

    all_ok = True
    for model_name in MODEL_NAMES:
        try:
            versions = client.get_latest_versions(model_name, stages=["Production"])
            if versions:
                v = versions[0]
                run = client.get_run(v.run_id)
                mae  = run.data.metrics.get("mae",  "N/A")
                rmse = run.data.metrics.get("rmse", "N/A")
                log.info(
                    "  [OK] %-35s  v%-3s  MAE=%-8s  RMSE=%s",
                    model_name, v.version,
                    f"{mae:.4f}" if isinstance(mae, float) else mae,
                    f"{rmse:.4f}" if isinstance(rmse, float) else rmse,
                )
            else:
                log.error("  ✗ No Production version for '%s'", model_name)
                all_ok = False
        except Exception as e:
            log.error("  ✗ %s: %s", model_name, e)
            all_ok = False

    if all_ok:
        log.info("")
        log.info("  🎉 All base models trained and registered in Production.")
        log.info("  MLflow UI: %s", MLFLOW_TRACKING_URI)
        log.info("")
        log.info("  The Flink prediction.py job will now pick these up automatically.")
    else:
        log.error("  Some models are not in Production — check MLflow UI.")
        sys.exit(1)


# =============================================================================
# Entry point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Bootstrap Smart Campus ML base models")
    parser.add_argument(
        "--skip-generate", action="store_true",
        help="Skip dataset generation if CSVs already exist",
    )
    args = parser.parse_args()

    log.info("")
    log.info("Smart Campus ML — Base Model Bootstrap")
    log.info("MLflow tracking URI: %s", MLFLOW_TRACKING_URI)
    log.info("")

    if args.skip_generate and all(
        (_DATASETS / f"{name}_2024_2025.csv").exists()
        for name in ("canteen_congestion", "library_congestion", "energy_forecast")
    ):
        log.info("STEP 1: Datasets already exist — skipping generation (--skip-generate).")
    else:
        generate_datasets()

    run_kedro_pipelines()
    promote_models()
    print_summary()


if __name__ == "__main__":
    main()
