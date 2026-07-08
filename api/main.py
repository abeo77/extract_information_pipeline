"""FastAPI application."""

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.batch_routes import jobs_router, router as batch_router
from api.routes.evaluation_routes import router as evaluation_router
from api.routes.pipeline_routes import router as pipeline_router
from api.routes.result_routes import router as result_router
from api.routes.upload_routes import router as upload_router

load_dotenv()

app = FastAPI(title="Contract Keyword Pipeline")

frontend_origins = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router)
app.include_router(batch_router)
app.include_router(jobs_router)
app.include_router(pipeline_router)
app.include_router(result_router)
app.include_router(evaluation_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
