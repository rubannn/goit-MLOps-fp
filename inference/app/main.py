import logging
import os
import time
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
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


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # HTTP 400, not FastAPI's default 422 — and no raw pydantic error internals
    # (types, input values, code locations) leaked to the client, per C1.
    log_event(
        logger,
        "request validation failed",
        level=logging.WARNING,
        method=request.method,
        path=request.url.path,
        fields=[".".join(str(p) for p in e["loc"]) for e in exc.errors()],
    )
    return JSONResponse(status_code=400, content={"detail": "invalid request body"})


# Simple fixed-window rate limit per client IP, in-app (no Ingress controller
# deployed). Known limitation: state is per-pod, not shared across replicas —
# with 9 stable + 1 canary pod in production, the effective cluster-wide limit
# is roughly RATE_LIMIT_MAX_REQUESTS times the number of pods a client happens
# to hit, not a hard global cap. Documented in THREAT_MODEL.md.
RATE_LIMIT_MAX_REQUESTS = int(os.environ.get("RATE_LIMIT_MAX_REQUESTS", "20"))
RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "10"))
RATE_LIMITED_PATHS = {"/predict", "/recommend"}
_request_log: dict[str, deque] = defaultdict(deque)


def _is_rate_limited(client_ip: str) -> bool:
    now = time.monotonic()
    window = _request_log[client_ip]
    while window and now - window[0] > RATE_LIMIT_WINDOW_SECONDS:
        window.popleft()
    if len(window) >= RATE_LIMIT_MAX_REQUESTS:
        return True
    window.append(now)
    return False


@app.middleware("http")
async def metrics_and_logging_middleware(request: Request, call_next):
    start = time.perf_counter()
    path = request.url.path

    if path in RATE_LIMITED_PATHS and _is_rate_limited(request.client.host if request.client else "unknown"):
        REQUEST_COUNT.labels(method=request.method, path=path, status="429").inc()
        ERROR_COUNT.labels(method=request.method, path=path).inc()
        log_event(logger, "rate limit exceeded", level=logging.WARNING, method=request.method, path=path)
        return JSONResponse(status_code=429, content={"detail": "too many requests"})

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
