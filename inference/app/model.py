import hashlib
import logging
import os
from functools import lru_cache

import mlflow.artifacts
import mlflow.pyfunc
import pandas as pd
from mlflow.tracking import MlflowClient

MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow.mlops-system.svc.cluster.local:5000")
REGISTERED_MODEL_NAME = os.environ.get("REGISTERED_MODEL_NAME", "movielens-recommender")
MODEL_STAGE = os.environ.get("MODEL_STAGE", "Staging")
MOVIES_PATH = os.environ.get("MOVIES_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "movies.csv"))
RATINGS_PATH = os.environ.get("RATINGS_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "ratings.csv"))

logger = logging.getLogger("inference")


class ArtifactIntegrityError(RuntimeError):
    pass


def _verify_artifact_checksum(client: MlflowClient, run_id: str, expected_sha256: str) -> None:
    # Immutable model artifacts (C4): re-download the exact file the model was
    # registered with and hash it ourselves, rather than trusting whatever
    # mlflow.pyfunc.load_model happens to fetch — catches a tampered or
    # corrupted artifact in the store before it's ever loaded into the process.
    local_path = mlflow.artifacts.download_artifacts(run_id=run_id, artifact_path="model/python_model.pkl")
    with open(local_path, "rb") as f:
        actual_sha256 = hashlib.sha256(f.read()).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ArtifactIntegrityError(
            f"Model artifact checksum mismatch for run {run_id}: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )


class RecommenderModel:
    def __init__(self):
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        client = MlflowClient()
        mv = client.get_latest_versions(REGISTERED_MODEL_NAME, stages=[MODEL_STAGE])[0]

        expected_sha256 = mv.tags.get("artifact_sha256")
        if not expected_sha256:
            raise ArtifactIntegrityError(
                f"{REGISTERED_MODEL_NAME} v{mv.version} has no 'artifact_sha256' tag — "
                "refusing to load an unverifiable model artifact"
            )
        _verify_artifact_checksum(client, mv.run_id, expected_sha256)
        logger.info(f"Artifact checksum verified for {REGISTERED_MODEL_NAME} v{mv.version}")

        self.model = mlflow.pyfunc.load_model(f"models:/{REGISTERED_MODEL_NAME}/{MODEL_STAGE}")
        self.movies = pd.read_csv(MOVIES_PATH)
        self.ratings = pd.read_csv(RATINGS_PATH)
        self.stage = MODEL_STAGE
        self.version = mv.version

    def predict_rating(self, user_id: int, movie_id: int) -> float:
        row = pd.DataFrame({"userId": [user_id], "movieId": [movie_id]})
        return float(self.model.predict(row).iloc[0])

    def recommend(self, user_id: int, top_n: int) -> list[dict]:
        seen = set(self.ratings.loc[self.ratings.userId == user_id, "movieId"])
        candidates = self.movies.loc[~self.movies.movieId.isin(seen)]

        if candidates.empty:
            candidates = self.movies

        batch = pd.DataFrame({"userId": [user_id] * len(candidates), "movieId": candidates.movieId.values})
        scores = self.model.predict(batch)

        ranked = (
            candidates.assign(predicted_rating=scores.values)
            .sort_values("predicted_rating", ascending=False)
            .head(top_n)
        )
        return [
            {"movie_id": int(r.movieId), "title": r.title, "predicted_rating": round(float(r.predicted_rating), 3)}
            for r in ranked.itertuples()
        ]


@lru_cache(maxsize=1)
def get_model() -> RecommenderModel:
    return RecommenderModel()
