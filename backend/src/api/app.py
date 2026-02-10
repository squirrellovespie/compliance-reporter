from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes.index import router as index_router
from .routes.ingest import router as ingest_router
from .routes.sections import router as sections_router
from .routes.reports import router as reports_router
from .routes.sections import router as sections_router
from .routes.admin_prompts import router as admin_prompts_router
from api.routes.admin_frameworks import router as admin_frameworks_router

from dotenv import load_dotenv

load_dotenv()


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev: allow all; tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(index_router)
app.include_router(ingest_router)
app.include_router(sections_router)
app.include_router(reports_router)
app.include_router(admin_prompts_router)
app.include_router(admin_frameworks_router)

def create_app() -> FastAPI:
    return app
