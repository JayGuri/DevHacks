# backend/app.py — FastAPI application entry point
"""
ARFL Platform Web Backend
=========================
Serves REST APIs + WebSocket for the React frontend.
Bridges the existing FL engine for real-time federated learning simulation.

Run with:
    cd backend && python app.py

Or:
    cd backend && uvicorn app:app --reload --port 8000
"""

import os
import sys
import logging
from pathlib import Path

from dotenv import load_dotenv

ROOT_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(ROOT_ENV_PATH, override=False)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("arfl.app")

# Import DB init
from db.database import init_db

# Import route modules
from auth.routes import router as auth_router
from projects.routes import router as projects_router
from join_requests.routes import router as join_requests_router
from notifications.routes import router as notifications_router
from training.routes import router as training_router


# --------------------------------------------------------------------------
# App factory
# --------------------------------------------------------------------------

app = FastAPI(
    title="ARFL Platform — Web Backend",
    description=(
        "REST API + WebSocket backend for the Asynchronous Robust Federated Learning platform. "
        "Bridges the FL engine (aggregation, SABD, DP, Byzantine attacks) with the React frontend."
    ),
    version="1.0.0",
)

# CORS — allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173"
    ).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# Register routers
# --------------------------------------------------------------------------

app.include_router(auth_router, prefix="/api", tags=["Auth"])
app.include_router(projects_router, prefix="/api", tags=["Projects"])
app.include_router(join_requests_router, prefix="/api", tags=["Join Requests"])
app.include_router(notifications_router, prefix="/api", tags=["Notifications"])
app.include_router(training_router, prefix="/api", tags=["Training"])


# --------------------------------------------------------------------------
# Startup event
# --------------------------------------------------------------------------

@app.on_event("startup")
def on_startup():
    """Initialize database tables on startup."""
    logger.info("ARFL Backend starting up...")
    init_db()
    logger.info("Database initialized (SQLite)")
    logger.info("ARFL Backend ready — http://localhost:%s", os.getenv("PORT", "8000"))
    logger.info("API docs available at http://localhost:%s/docs", os.getenv("PORT", "8000"))


# --------------------------------------------------------------------------
# Health check
# --------------------------------------------------------------------------

@app.get("/health", tags=["System"])
def health_check():
    """Health check endpoint."""
    from training.coordinator import _coordinators
    return {
        "status": "ok",
        "service": "arfl-backend",
        "activeTrainingSessions": len(_coordinators),
    }


# --------------------------------------------------------------------------
# Entrypoint
# --------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info",
    )
