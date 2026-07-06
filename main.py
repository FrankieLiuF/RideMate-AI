"""
RideMate AI — FastAPI application entry point.

Start with: python main.py  (after activating venv)
Server:     http://localhost:8000
API Docs:   http://localhost:8000/docs
Health:     http://localhost:8000/health

STARTUP SEQUENCE
================
1. load_dotenv()        — read .env file into os.environ (API keys, config)
2. init_db()            — create all SQLAlchemy tables if they don't exist
3. Security middleware   — API key auth + rate limiting (order matters!)
4. CORS middleware       — outermost layer for preflight handling
5. Static files          — mount /static directory for demo page assets
6. API routes            — register /api/v1/* endpoints
"""

from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
from dotenv import load_dotenv

# Load .env before any other imports that might read os.getenv()
load_dotenv(override=True)

from database.db import init_db
from api.routes import router
from api.security import APIKeyMiddleware, RateLimitMiddleware

# Initialize database tables on startup.
# Idempotent — existing tables are skipped. Safe to run every time.
init_db()

app = FastAPI(
    title="RideMate AI — Multi-Agent Carpool Assistant",
    description="5-agent Gemini-powered system: ride search, booking, community board, driver status broadcast",
    version="0.1.0",
)

# Serve static files for the demo web interface (HTML, CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── Security Middleware (order matters: innermost → outermost) ──────────
#
# Starlette adds middleware by wrapping the app. Later additions wrap OUTSIDE
# earlier ones. So the request flow for this configuration is:
#
#   CORS → RateLimit → APIKey → App
#
# Why this order?
#   1. CORS outermost: handles browser preflight (OPTIONS) requests BEFORE
#      any auth or rate checks. Preflights are unauthenticated by design.
#   2. RateLimit next: rate-limit checks happen before expensive API key
#      validation — don't waste cycles on spam.
#   3. APIKey innermost: only authenticated requests reach the app.

# API Key authentication — protects /api/v1/* routes.
# Disabled by default in development (API_KEY_REQUIRED=false in .env).
# Enable in production by setting API_KEY_REQUIRED=true.
app.add_middleware(APIKeyMiddleware)

# Rate limiting — per-IP sliding window (30 requests / 60 seconds).
# Configurable via RATE_LIMIT_MAX and RATE_LIMIT_WINDOW env vars.
# Returns 429 Too Many Requests with Retry-After header when exceeded.
app.add_middleware(RateLimitMiddleware)

# CORS — outermost layer, handles preflight before auth.
# Currently allows localhost:3000 (Next.js dev server).
# Expand allow_origins for production deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes — all endpoints under /api/v1/
app.include_router(router)


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the interactive chat demo page."""
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/health")
async def health():
    """Simple liveness probe — returns 200 if server is running."""
    return {"status": "healthy"}


if __name__ == "__main__":
    # uvicorn with reload=True auto-restarts on code changes.
    # For production, run without reload: uvicorn main:app --host 0.0.0.0 --port 8000
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
