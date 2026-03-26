"""
AutoRef Backend — FastAPI Application
AI-Powered Job Outreach Automation
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from database import init_db
from routers import generate, send, followup, dashboard
from routers import settings as settings_router
from services.scheduler_service import scheduler_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup and shutdown."""
    # Startup
    init_db()
    print("✅ Database initialized")
    scheduler_service.start()
    yield
    # Shutdown
    scheduler_service.stop()
    print("🛑 Shutting down...")


app_settings = get_settings()

app = FastAPI(
    title="AutoRef API",
    description="AI-Powered Job Outreach Automation Backend",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[app_settings.frontend_url, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(generate.router)
app.include_router(send.router)
app.include_router(followup.router)
app.include_router(dashboard.router)
app.include_router(settings_router.router)


@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "autoref-api", "version": "0.1.0"}


@app.get("/")
def root():
    return {
        "message": "Welcome to AutoRef API",
        "docs": "/docs",
        "health": "/health",
    }
