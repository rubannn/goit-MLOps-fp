"""Rolls back Production to the version it held immediately before the last
promotion, in a single command (B4).

Reads the `previous_production_version` tag set by promote_model.py on the
current Production version, restores that version to Production, and archives
the bad one. Then restarts the production Deployment so it reloads the model.
"""

import os
import subprocess

from dotenv import load_dotenv
from mlflow.tracking import MlflowClient

load_dotenv()

MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
REGISTERED_MODEL_NAME = os.environ.get("REGISTERED_MODEL_NAME", "movielens-recommender")


def main() -> None:
    client = MlflowClient(tracking_uri=MLFLOW_TRACKING_URI)

    current_prod = client.get_latest_versions(REGISTERED_MODEL_NAME, stages=["Production"])
    if not current_prod:
        raise SystemExit(f"No version of '{REGISTERED_MODEL_NAME}' is currently in Production.")

    bad_version = current_prod[0]
    previous_version = bad_version.tags.get("previous_production_version")
    if not previous_version:
        raise SystemExit(
            f"v{bad_version.version} has no 'previous_production_version' tag — "
            "nothing recorded to roll back to. Was it promoted via promote_model.py?"
        )

    client.transition_model_version_stage(
        name=REGISTERED_MODEL_NAME,
        version=previous_version,
        stage="Production",
        archive_existing_versions=True,
    )
    print(f"Rolled back {REGISTERED_MODEL_NAME}: v{bad_version.version} -> Archived, v{previous_version} -> Production")

    subprocess.run(
        ["kubectl", "rollout", "restart", "deployment/movielens-inference-stable", "-n", "production"],
        check=True,
    )
    print("Triggered rollout restart of production deployment.")


if __name__ == "__main__":
    main()
