import logging
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from .logging_config import configure_logging, log_event
from .model import get_model
from .schemas import PredictRequest, PredictResponse, RecommendRequest, RecommendResponse

logger = configure_logging()

app = FastAPI(title="MovieLens Recommender Inference")

REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["method", "path", "status"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "Request latency in seconds", ["method", "path"])
ERROR_COUNT = Counter("http_request_errors_total", "Total HTTP requests that resulted in an error", ["method", "path"])


@app.middleware("http")
async def metrics_and_logging_middleware(request: Request, call_next):
    start = time.perf_counter()
    path = request.url.path
    try:
        response = await call_next(request)
    except Exception:
        ERROR_COUNT.labels(method=request.method, path=path).inc()
        REQUEST_COUNT.labels(method=request.method, path=path, status="500").inc()
        log_event(logger, "unhandled exception", level=logging.ERROR, method=request.method, path=path)
        return JSONResponse(status_code=500, content={"detail": "internal server error"})

    duration = time.perf_counter() - start
    REQUEST_LATENCY.labels(method=request.method, path=path).observe(duration)
    REQUEST_COUNT.labels(method=request.method, path=path, status=str(response.status_code)).inc()
    if response.status_code >= 400:
        ERROR_COUNT.labels(method=request.method, path=path).inc()

    log_event(
        logger,
        "request completed",
        method=request.method,
        path=path,
        status=response.status_code,
        latency_ms=round(duration * 1000, 2),
    )
    return response


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    model = get_model()
    rating = model.predict_rating(req.user_id, req.movie_id)
    return PredictResponse(user_id=req.user_id, movie_id=req.movie_id, predicted_rating=round(rating, 3))


@app.post("/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest):
    model = get_model()
    recs = model.recommend(req.user_id, req.top_n)
    return RecommendResponse(user_id=req.user_id, recommendations=recs)
