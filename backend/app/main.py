# backend/app/main.py
import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.db import init_db_pool, close_db_pool, check_db_health
from app.config import settings
from app.api.query_routes import router as query_router
from app.api.matter_routes import router as matter_router
from app.api.sources_routes import router as sources_router
from app.api.quarantine_routes import router as quarantine_router
from app.api.radar_routes import router as radar_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB pool on startup (fails gracefully if local DB offline)
    try:
        await asyncio.wait_for(init_db_pool(), timeout=1.0)
    except Exception:
        pass
    yield
    # Close DB pool on shutdown
    try:
        await asyncio.wait_for(close_db_pool(), timeout=1.0)
    except Exception:
        pass

app = FastAPI(
    title="Official Email Intelligence System",
    description="3-Layer Direct-Method Email Intelligence System API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(query_router)
app.include_router(matter_router)
app.include_router(sources_router)
app.include_router(quarantine_router)
app.include_router(radar_router)

@app.get("/health")
async def health_check():
    """
    Verifies system readiness, PostgreSQL status, and API availability.
    """
    try:
        db_status = await asyncio.wait_for(check_db_health(), timeout=0.8)
        return {
            "status": "healthy",
            "phase": "Phase 9 - React Institutional Cockpit",
            "db": db_status,
            "mcp_tools": 6,
            "cockpit_ready": True
        }
    except Exception as e:
        return {
            "status": "degraded_demo_mode",
            "phase": "Phase 9 - React Institutional Cockpit",
            "db_error": str(e),
            "mcp_tools": 6,
            "cockpit_ready": True,
            "note": "Running in high-fidelity mock/demo mode for offline demonstration"
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
