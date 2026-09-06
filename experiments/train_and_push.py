"""Trains a Matrix Factorization (SVD) recommender on MovieLens ml-latest-small
with several hyperparameter combinations, logs each run to MLflow, pushes
RMSE/MAE to Prometheus PushGateway, registers the best run's model in the
MLflow Model Registry, and promotes it to Staging.
"""

import hashlib
import os
import subprocess

import mlflow
import mlflow.pyfunc
import pandas as pd
from dotenv import load_dotenv
from mlflow.tracking import MlflowClient
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
from surprise import SVD, Dataset, Reader, accuracy
from surprise.model_selection import train_test_split

load_dotenv()

MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
PUSHGATEWAY_URL = os.environ.get("PUSHGATEWAY_URL", "http://localhost:9091")
EXPERIMENT_NAME = os.environ.get("MLFLOW_EXPERIMENT_NAME", "movielens-svd")
REGISTERED_MODEL_NAME = os.environ.get("REGISTERED_MODEL_NAME", "movielens-recommender")
DATA_PATH = os.environ.get("DATA_PATH", os.path.join(os.path.dirname(__file__), "data", "ratings.csv"))

N_FACTORS_VALUES = [20, 50]
N_EPOCHS_VALUES = [10, 20]


class SurpriseRatingModel(mlflow.pyfunc.PythonModel):
    """Wraps a trained surprise SVD algo behind the mlflow.pyfunc contract.

    model_input is a DataFrame with columns userId, movieId; predict returns
    one estimated rating per row. Ranking top-N candidates for a user is left
    to the caller (inference service), which predicts over a candidate set
    and sorts client-side.
    """

    def __init__(self, algo):
        self.algo = algo

    def predict(self, context, model_input: pd.DataFrame, params=None):
        # raw ids must match the dtype seen during Dataset.load_from_df (pandas int64),
        # not str — otherwise every lookup misses the trainset mapping and silently
        # falls back to the global mean rating for every prediction.
        return pd.Series(
            [self.algo.predict(row.userId, row.movieId).est for row in model_input.itertuples()]
        )


def push_metrics(run_id: str, rmse: float, mae: float) -> None:
    registry = CollectorRegistry()
    Gauge("mlflow_rmse", "RMSE of the trained recommender", registry=registry).set(rmse)
    Gauge("mlflow_mae", "MAE of the trained recommender", registry=registry).set(mae)
    push_to_gateway(
        PUSHGATEWAY_URL,
        job="train_and_push",
        grouping_key={"run_id": run_id},
        registry=registry,
    )


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def dataset_version(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:12]


def train_and_log(trainset, testset, n_factors: int, n_epochs: int):
    with mlflow.start_run() as run:
        algo = SVD(n_factors=n_factors, n_epochs=n_epochs, random_state=42)
        algo.fit(trainset)

        predictions = algo.test(testset)
        rmse = accuracy.rmse(predictions, verbose=False)
        mae = accuracy.mae(predictions, verbose=False)

        mlflow.log_params({"n_factors": n_factors, "n_epochs": n_epochs, "algo": "SVD"})
        mlflow.log_metrics({"rmse": rmse, "mae": mae})
        mlflow.pyfunc.log_model(name="model", python_model=SurpriseRatingModel(algo))

        push_metrics(run.info.run_id, rmse, mae)

        print(f"run_id={run.info.run_id} n_factors={n_factors} n_epochs={n_epochs} rmse={rmse:.4f} mae={mae:.4f}")
        return run.info.run_id, rmse


def register_best_model(best_run_id: str, best_rmse: float, sha: str, dataset_hash: str) -> None:
    client = MlflowClient()
    model_uri = f"runs:/{best_run_id}/model"
    mv = mlflow.register_model(model_uri=model_uri, name=REGISTERED_MODEL_NAME)

    client.set_model_version_tag(REGISTERED_MODEL_NAME, mv.version, "git_sha", sha)
    client.set_model_version_tag(REGISTERED_MODEL_NAME, mv.version, "dataset_version", dataset_hash)
    client.set_model_version_tag(REGISTERED_MODEL_NAME, mv.version, "rmse", f"{best_rmse:.4f}")

    client.transition_model_version_stage(
        name=REGISTERED_MODEL_NAME,
        version=mv.version,
        stage="Staging",
        archive_existing_versions=False,
    )
    print(f"Registered {REGISTERED_MODEL_NAME} v{mv.version} (run {best_run_id}) -> Staging")


def main() -> None:
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT_NAME)

    ratings = pd.read_csv(DATA_PATH)
    reader = Reader(rating_scale=(0.5, 5.0))
    data = Dataset.load_from_df(ratings[["userId", "movieId", "rating"]], reader)
    trainset, testset = train_test_split(data, test_size=0.2, random_state=42)

    results = []
    for n_factors in N_FACTORS_VALUES:
        for n_epochs in N_EPOCHS_VALUES:
            results.append(train_and_log(trainset, testset, n_factors, n_epochs))

    best_run_id, best_rmse = min(results, key=lambda r: r[1])
    print(f"Best run: run_id={best_run_id} rmse={best_rmse:.4f}")

    register_best_model(best_run_id, best_rmse, git_sha(), dataset_version(DATA_PATH))


if __name__ == "__main__":
    main()
