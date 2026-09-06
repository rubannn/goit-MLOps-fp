import os
from functools import lru_cache

import mlflow.pyfunc
import pandas as pd

MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow.mlops-system.svc.cluster.local:5000")
REGISTERED_MODEL_NAME = os.environ.get("REGISTERED_MODEL_NAME", "movielens-recommender")
MODEL_STAGE = os.environ.get("MODEL_STAGE", "Staging")
MOVIES_PATH = os.environ.get("MOVIES_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "movies.csv"))
RATINGS_PATH = os.environ.get("RATINGS_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "ratings.csv"))


class RecommenderModel:
    def __init__(self):
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        model_uri = f"models:/{REGISTERED_MODEL_NAME}/{MODEL_STAGE}"
        self.model = mlflow.pyfunc.load_model(model_uri)
        self.movies = pd.read_csv(MOVIES_PATH)
        self.ratings = pd.read_csv(RATINGS_PATH)
        self.stage = MODEL_STAGE

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
