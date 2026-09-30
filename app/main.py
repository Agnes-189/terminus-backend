import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Core & Infrastructure Config
from app.core.config import settings
from app.core.database import Base, engine
from app.core.migrations import run_startup_migrations
from app.core.middleware import ObservabilityMiddleware
from app.core.telemetry import setup_telemetry_logging

# Optional Handlers & Schema Overrides
try:
    from app.core.errors import register_error_handlers
except ImportError:
    register_error_handlers = None

try:
    from app.core.openapi import custom_openapi_schema
except ImportError:
    custom_openapi_schema = None

# Background Services & Async Queue Workers
from app.services.cron import scheduler
from app.services.event_processor import event_processor
from app.services.solana_listener import listen_to_solana_events
from app.services.watchdog import check_heartbeats

# API Routers
from app.api import (
    auth,
    beneficiary,
    claims,
    dual_sign,
    heartbeat,
    identity,
    observability,
    ocr,
    vault,
    webhooks,
)

logger = logging.getLogger("terminus.main")

# Initialize structured JSON logging
setup_telemetry_logging(log_level=settings.LOG_LEVEL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application Lifespan Event Handler.
    Manages startup execution (migrations, background queue workers) and graceful shutdown.
    """
    logger.info("Starting Terminus Protocol Engine...")

    # 1. Run Alembic Database Migrations on Startup
    try:
        run_startup_migrations()
    except Exception as exc:
        logger.warning(f"Startup migration warning (falling back to ORM table creation): {exc}")
        Base.metadata.create_all(bind=engine)

    # 2. Start Background Cron Task Scheduler
    if settings.FEATURE_ENABLE_CRON_SCHEDULER:
        try:
            scheduler.start()
            logger.info("Background cron scheduler started.")
        except Exception as exc:
            logger.error(f"Failed to start cron scheduler: {exc}")

    # 3. Launch Async Queue Workers & Event Listeners
    event_worker_task = asyncio.create_task(event_processor.start_worker())
    watchdog_task = asyncio.create_task(check_heartbeats())
    
    solana_ws_task = None
    if settings.FEATURE_ENABLE_SOLANA_WS:
        solana_ws_task = asyncio.create_task(listen_to_solana_events())

    logger.info("🚀 Terminus Protocol Engine Online & Fully Operational.")

    yield  # Application accepts incoming HTTP requests during this window

    # --- Graceful Shutdown Sequence ---
    logger.info("Initiating graceful shutdown for Terminus Protocol Engine...")

    # Stop Webhook Event Processor Worker
    event_processor.stop_worker()
    event_worker_task.cancel()

    # Cancel Background Watchdog & Listener Tasks
    watchdog_task.cancel()
    if solana_ws_task:
        solana_ws_task.cancel()

    # Stop Cron Scheduler
    if settings.FEATURE_ENABLE_CRON_SCHEDULER:
        try:
            scheduler.stop()
        except Exception:
            pass

    # Await cleanup of background task cancellation
    await asyncio.gather(
        event_worker_task,
        watchdog_task,
        *([solana_ws_task] if solana_ws_task else []),
        return_exceptions=True
    )
    logger.info("Terminus Protocol Engine shutdown complete.")


# Initialize FastAPI Application Context
app = FastAPI(
    title=settings.PROJECT_NAME,
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Custom Exception Handlers & OpenAPI Schema Customizer
if register_error_handlers:
    register_error_handlers(app)

if custom_openapi_schema:
    app.openapi = lambda: custom_openapi_schema(app)

# Observability, Latency Tracing, and Prometheus Middleware
app.add_middleware(ObservabilityMiddleware)

# Cross-Origin Resource Sharing (CORS) Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Route Registrations
app.include_router(observability.router)  # Exposes /metrics, /health/readiness, /health/detailed
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["Auth"])
app.include_router(heartbeat.router, prefix=f"{settings.API_V1_STR}/heartbeat", tags=["Heartbeat"])
app.include_router(ocr.router, prefix=f"{settings.API_V1_STR}/ocr", tags=["OCR"])
app.include_router(vault.router, prefix=f"{settings.API_V1_STR}/vault", tags=["Vault"])
app.include_router(claims.router, prefix=f"{settings.API_V1_STR}/claims", tags=["Claims"])
app.include_router(identity.router, prefix=f"{settings.API_V1_STR}/identity", tags=["Identity"])
app.include_router(webhooks.router, prefix=f"{settings.API_V1_STR}/webhooks", tags=["Webhooks"])
app.include_router(dual_sign.router, prefix=f"{settings.API_V1_STR}/dual-sign", tags=["Dual Sign"])
app.include_router(beneficiary.router, prefix=f"{settings.API_V1_STR}/beneficiary", tags=["Beneficiary"])


@app.get("/", tags=["System Information"])
async def root():
    """Root endpoint providing service status and health indicators."""
    return {
        "status": "active",
        "project": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "api_version": "v1",
        "docs_url": "/docs",
        "metrics_url": "/metrics",
        "health_url": "/health/detailed"
    }
