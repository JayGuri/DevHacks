# backend/db/mongo_database.py — MongoDB Atlas connection and initialization
"""
MongoDB Atlas Database Configuration
====================================
Uses Motor (async driver) + Beanie (ODM) for async document operations.

Connection string format:
  mongodb+srv://<user>:<password>@<cluster>.mongodb.net/<database>?retryWrites=true&w=majority

Free Tier (M0):
  - 512MB storage
  - Shared RAM
  - No charge
"""

import os
import logging
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from pymongo.errors import OperationFailure

logger = logging.getLogger("arfl.mongo")

# Global MongoDB client and database instances
_mongo_client: Optional[AsyncIOMotorClient] = None
_mongo_db = None


def get_mongodb_url() -> str:
    """Get MongoDB connection string from environment."""
    url = os.getenv("MONGODB_URL") or os.getenv("MONGO_URI") or ""
    if not url:
        raise RuntimeError(
            "MONGODB_URL (or MONGO_URI) environment variable is required for MongoDB Atlas connection. "
            "Format: mongodb+srv://<user>:<password>@<cluster>.mongodb.net/<database>"
        )
    return url


def get_database_name() -> str:
    """Get database name from environment."""
    return os.getenv("DATABASE_NAME") or os.getenv("MONGO_DB") or "arfl_platform"


async def connect_to_mongo():
    """Initialize MongoDB connection and Beanie ODM."""
    global _mongo_client, _mongo_db

    if _mongo_client is not None:
        logger.info("MongoDB already connected")
        return

    try:
        mongodb_url = get_mongodb_url()
        database_name = get_database_name()

        logger.info("Connecting to MongoDB Atlas...")
        _mongo_client = AsyncIOMotorClient(
            mongodb_url,
            serverSelectionTimeoutMS=5000,  # 5 second timeout
            connectTimeoutMS=10000,
            maxPoolSize=10,
        )

        # Test connection
        await _mongo_client.admin.command('ping')
        logger.info("MongoDB Atlas connection successful")

        # Get database instance
        _mongo_db = _mongo_client[database_name]

        # Initialize Beanie with document models
        from db.mongo_models import User, Project, ProjectMember, JoinRequest, Notification, ActivityLog

        await init_beanie(
            database=_mongo_db,
            document_models=[
                User,
                Project,
                ProjectMember,
                JoinRequest,
                Notification,
                ActivityLog,
            ]
        )

        logger.info(f"Beanie ODM initialized with database: {database_name}")

        # Create indexes
        await create_indexes()

    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise


async def close_mongo_connection():
    """Close MongoDB connection."""
    global _mongo_client
    if _mongo_client is not None:
        _mongo_client.close()
        _mongo_client = None
        logger.info("MongoDB connection closed")


def get_database():
    """Get the MongoDB database instance."""
    if _mongo_db is None:
        raise RuntimeError("MongoDB not initialized. Call connect_to_mongo() first.")
    return _mongo_db


async def create_indexes():
    """Create database indexes for performance."""
    logger.info("Creating MongoDB indexes...")

    # User indexes
    from db.mongo_models import User
    try:
        await User.get_motor_collection().create_index("email", unique=True)
    except OperationFailure as exc:
        if getattr(exc, "code", None) == 86:
            logger.warning("Skipping unique email index creation due to existing conflicting index: %s", exc)
        else:
            raise

    # Project indexes
    from db.mongo_models import Project
    await Project.get_motor_collection().create_index("created_by")
    await Project.get_motor_collection().create_index("invite_code")

    # ProjectMember indexes
    from db.mongo_models import ProjectMember
    await ProjectMember.get_motor_collection().create_index([("user_id", 1), ("project_id", 1)])

    # JoinRequest indexes
    from db.mongo_models import JoinRequest
    await JoinRequest.get_motor_collection().create_index([("project_id", 1), ("status", 1)])

    # Notification indexes
    from db.mongo_models import Notification
    await Notification.get_motor_collection().create_index([("user_id", 1), ("read", 1)])

    # ActivityLog indexes
    from db.mongo_models import ActivityLog
    await ActivityLog.get_motor_collection().create_index([("project_id", 1), ("timestamp", -1)])

    logger.info("MongoDB indexes created successfully")


async def health_check() -> dict:
    """Check MongoDB connection health."""
    try:
        if _mongo_client is None:
            return {"status": "disconnected", "error": "Client not initialized"}

        # Ping server
        await _mongo_client.admin.command('ping')

        # Get server info
        server_info = await _mongo_client.server_info()

        return {
            "status": "connected",
            "database": get_database_name(),
            "version": server_info.get("version", "unknown"),
            "uptime": server_info.get("uptime", 0),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
