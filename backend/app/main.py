import sys
from pathlib import Path

# Ensure 'backend' directory is in sys.path so 'app' imports resolve regardless of launch command
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import ROOT, settings

app = FastAPI(title="Bangalore Voice Nav", version="0.1.0")
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok", "env": settings.app_env}


# must stay last so it doesn't shadow the API routes
frontend_dir = Path(ROOT) / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")