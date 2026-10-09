"""Nigraan API: checks every rupee going out, and tells you whether what's coming in will cover it."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app import errors
from app.api import core, finance
from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.models import Company
from app.services.runtime import runtime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("nigraan")


@asynccontextmanager
async def lifespan(_: FastAPI):
    s = get_settings()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seeded = db.execute(select(Company)).scalars().first() is not None
    if not seeded and s.auto_seed:
        from app.services.demo import reset

        log.info("empty database: seeding the synthetic company (seed %s)", s.seed)
        log.info("seeded: %s", reset())
    else:
        runtime.load_models(s.models_dir)
    log.info("models: %s", runtime.bundle.version)
    yield


app = FastAPI(
    title="Nigraan API",
    version="1.0.0",
    description="Finance control tower for Pakistani SMEs: fraud firewall for payments + 13-week cash forecast. "
                "ML models and deterministic code decide; the LLM only reads documents and writes explanations.",
    lifespan=lifespan,
)
errors.install(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_origin_regex=r"https://nigraan[a-z0-9\-]*\.vercel\.app",  # this project's Vercel deployments only
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(core.router, prefix="/api/v1")
app.include_router(finance.router, prefix="/api/v1")


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "model_version": runtime.bundle.version}


@app.get("/", tags=["meta"])
def root():
    return {"name": "Nigraan API", "docs": "/docs", "health": "/health"}
