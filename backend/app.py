# backend/app_mongo.py — MongoDB-based FastAPI application
"""
ARFL Platform Web Backend with MongoDB Atlas
============================================
MongoDB-powered version using Motor + Beanie for async operations.

Run with:
    cd backend && python app_mongo.py

Or:
    cd backend && uvicorn app_mongo:app --reload --port 8000
"""

import warnings

warnings.warn(
    "\n\n"
    "======================================================================\n"
    "DEPRECATION WARNING: The 'backend' directory is deprecated due to     \n"
    "architectural redundancy. The active asynchronous production          \n"
    "backend is located at 'async_federated_learning/main.py'.             \n"
    "Please migrate all systems to the async federated learning server.    \n"
    "This entry point will be removed in future releases.                  \n"
    "======================================================================\n",
    DeprecationWarning,
    stacklevel=2,
)

import os
import sys
import logging
from pathlib import Path
from contextlib import asynccontextmanager

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

# Import MongoDB connection
from db.database import connect_to_mongo, close_mongo_connection, health_check

# Import route modules
from auth.routes import router as auth_router
from projects.routes import router as projects_router
from join_requests.routes import router as join_requests_router
from notifications.routes import router as notifications_router
from training.routes import router as training_router


# --------------------------------------------------------------------------
# Lifespan context manager (startup/shutdown)
# --------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize MongoDB on startup, close on shutdown."""
    logger.info("ARFL Backend (MongoDB) starting up...")
    
    # Connect to MongoDB Atlas
    try:
        await connect_to_mongo()
        logger.info("MongoDB Atlas connected successfully")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise
    
    yield
    
    # Cleanup on shutdown
    await close_mongo_connection()
    logger.info("ARFL Backend shutting down...")


# --------------------------------------------------------------------------
# App factory
# --------------------------------------------------------------------------

app = FastAPI(
    title="ARFL Platform — Web Backend (MongoDB)",
    description=(
        "REST API + WebSocket backend for the Asynchronous Robust Federated Learning platform. "
        "Uses MongoDB Atlas for data persistence. "
        "Bridges the FL engine (aggregation, SABD, DP, Byzantine attacks) with the React frontend."
    ),
    version="2.0.0",
    lifespan=lifespan,
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
# Health check endpoints
# --------------------------------------------------------------------------

@app.get("/health", tags=["System"])
async def health_check_endpoint():
    """Health check with MongoDB status."""
    from training.coordinator import _coordinators

    mongo_status = await health_check()

    # Build per-session trust summary (avg trust only — no per-node detail at health level)
    sessions_info = {}
    for project_id, coordinator in _coordinators.items():
        nodes_dict = coordinator.node_manager.get_all_nodes_dict()
        trust_values = [float(n.get("trust", 1.0)) for n in nodes_dict.values()]
        avg_trust = round(sum(trust_values) / len(trust_values), 4) if trust_values else None
        sessions_info[project_id] = {
            "round": coordinator.current_round,
            "status": coordinator.status,
            "node_count": len(nodes_dict),
            "avg_trust": avg_trust,
        }

    return {
        "status": "ok",
        "service": "arfl-backend-mongodb",
        "database": mongo_status,
        "activeTrainingSessions": len(_coordinators),
        "sessions": sessions_info,
    }


@app.get("/", tags=["System"])
def root():
    """Root endpoint."""
    return {
        "service": "ARFL Platform Backend",
        "version": "2.0.0",
        "database": "MongoDB Atlas",
        "docs": "/docs",
    }


# --------------------------------------------------------------------------
# Entrypoint
# --------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(
        "app_mongo:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info",
    )
