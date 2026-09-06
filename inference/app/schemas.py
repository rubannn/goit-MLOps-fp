from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    user_id: int = Field(..., ge=1, description="MovieLens user id")
    movie_id: int = Field(..., ge=1, description="MovieLens movie id")


class PredictResponse(BaseModel):
    user_id: int
    movie_id: int
    predicted_rating: float


class RecommendRequest(BaseModel):
    user_id: int = Field(..., ge=1, description="MovieLens user id")
    top_n: int = Field(10, ge=1, le=50, description="Number of recommendations to return")


class RecommendedMovie(BaseModel):
    movie_id: int
    title: str
    predicted_rating: float


class RecommendResponse(BaseModel):
    user_id: int
    recommendations: list[RecommendedMovie]
