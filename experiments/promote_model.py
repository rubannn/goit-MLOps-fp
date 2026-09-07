"""Promotes a Model Registry version from Staging to Production.

This is a deliberate, separate action from training (B2) — run manually or
triggered explicitly in CI, never automatically after a training run. The
previous Production version is archived (not deleted), so rollback.py can
restore it immediately.

Usage:
    python promote_model.py [--version N]

Without --version, promotes the highest-numbered version currently in Staging.
"""

import argparse
import os

from dotenv import load_dotenv
from mlflow.tracking import MlflowClient

from audit_log import audit_event

load_dotenv()

MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
REGISTERED_MODEL_NAME = os.environ.get("REGISTERED_MODEL_NAME", "movielens-recommender")


def latest_staging_version(client: MlflowClient) -> str:
    versions = client.get_latest_versions(REGISTERED_MODEL_NAME, stages=["Staging"])
    if not versions:
        raise SystemExit(f"No version of '{REGISTERED_MODEL_NAME}' is currently in Staging.")
    return max(versions, key=lambda v: int(v.version)).version


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", help="Model version to promote (default: latest Staging)")
    args = parser.parse_args()

    client = MlflowClient(tracking_uri=MLFLOW_TRACKING_URI)
    version = args.version or latest_staging_version(client)

    current_prod = client.get_latest_versions(REGISTERED_MODEL_NAME, stages=["Production"])
    previous_version = current_prod[0].version if current_prod else None
    if previous_version:
        print(f"Current Production version: v{previous_version} (will be archived)")

    client.transition_model_version_stage(
        name=REGISTERED_MODEL_NAME,
        version=version,
        stage="Production",
        archive_existing_versions=True,
    )
    # recorded so rollback.py knows exactly which version to restore, rather than
    # guessing from the (possibly multi-entry) Archived stage
    client.set_model_version_tag(
        REGISTERED_MODEL_NAME, version, "previous_production_version", previous_version or ""
    )
    audit_event(
        "promote_to_production",
        model_name=REGISTERED_MODEL_NAME,
        version=version,
        previous_production_version=previous_version,
    )
    print(f"Promoted {REGISTERED_MODEL_NAME} v{version} -> Production")
    print("Next: roll out the production deployment so it picks up the new model")
    print("  kubectl rollout restart deployment/movielens-inference-stable -n production")


if __name__ == "__main__":
    main()
