"""FastAPI application."""

from fastapi import FastAPI
from dotenv import load_dotenv

from api.routes.evaluation_routes import router as evaluation_router
from api.routes.pipeline_routes import router as pipeline_router
from api.routes.result_routes import router as result_router
from api.routes.upload_routes import router as upload_router

load_dotenv()

app = FastAPI(title="Contract Keyword Pipeline")
app.include_router(upload_router)
app.include_router(pipeline_router)
app.include_router(result_router)
app.include_router(evaluation_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
