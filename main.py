from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

from database.db import init_db
from api.routes import router
from api.security import APIKeyMiddleware, RateLimitMiddleware

# Initialize database tables on startup
init_db()

app = FastAPI(
    title="RideMate AI — Multi-Agent Carpool Assistant",
    description="5-agent Gemini-powered system: ride search, booking, community board, driver status broadcast",
    version="0.1.0",
)

# Serve static files (demo page)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── Security Middleware (order matters: innermost → outermost) ──────────
#
# Request flow: CORS → RateLimit → APIKey → App
# CORS is outermost to handle preflight OPTIONS before auth/rate checks

# API Key authentication (innermost — protects /api/v1/*)
# Only active when API_KEY_REQUIRED=true in .env (off by default in dev)
app.add_middleware(APIKeyMiddleware)

# Rate limiting (per-IP sliding window, configurable)
# 30 req / 60s default — configurable via RATE_LIMIT_MAX / RATE_LIMIT_WINDOW
app.add_middleware(RateLimitMiddleware)

# CORS configuration (outermost — handles preflight before auth)
# allow Next.js frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(router)


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the demo chat interface."""
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True  # Auto-reload during development
    )

