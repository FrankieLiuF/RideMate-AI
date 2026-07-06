"""
API routes for the RideMate multi-agent system.

ROUTE CATEGORIES
================
  AI-powered (uses Gemini):
    POST /api/v1/chat     — main conversation endpoint
    POST /api/v1/reset    — clear conversation and agent sessions

  Direct DB (no AI, instant response):
    GET  /api/v1/health   — liveness check + active session count
    GET  /api/v1/board    — community board messages
    GET  /api/v1/drivers/active — active driver broadcasts
    GET  /api/v1/welcome/{id}    — personalized greeting + recommendations
    GET  /api/v1/test     — quick connectivity check

SECURITY PIPELINE
=================
Every request goes through: sanitize → validate → process
  1. sanitize_input() — trim whitespace, cap length, strip control chars
  2. _check_user_id() — regex validation (alphanumeric + _ - only)
  3. process_message() — the AI pipeline
This happens BEFORE any data reaches an agent or database.

AGENT CACHING
=============
agent_cache is a per-user singleton dictionary — one OrchestratorAgent per
user_id. This preserves Gemini chat session context across requests within
the same server process. On /reset, the agent is evicted from cache.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict
from models.schemas import AgentRequest, AgentResponse
from agent.multi_agent import OrchestratorAgent
from api.security import sanitize_input, validate_user_id

router = APIRouter(prefix="/api/v1", tags=["agent"])

# Per-user agent cache — one OrchestratorAgent per user_id.
# The Orchestrator holds persistent Gemini chat sessions for its specialist
# sub-agents, so reusing instances preserves conversation context.
# In production with multiple workers, this should be replaced with Redis.
agent_cache: Dict[str, OrchestratorAgent] = {}


def get_agent(user_id: str) -> OrchestratorAgent:
    """
    Get or create a cached OrchestratorAgent for the user.

    Why cache? Each OrchestratorAgent creates 5 Gemini chat sessions
    (Orchestrator + 4 specialists). Recreating them on every request would
    lose conversation context AND waste ~2 seconds on model initialization.
    """
    if user_id not in agent_cache:
        agent_cache[user_id] = OrchestratorAgent()
    return agent_cache[user_id]


def _check_user_id(user_id: str) -> None:
    """
    Validate user_id format — security gate before any processing.

    Only allows: letters, numbers, underscores, hyphens, 1-64 chars.
    This prevents injection attacks through the user_id parameter.
    """
    if not validate_user_id(user_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid user_id format. Use 1-64 alphanumeric characters, underscores, or hyphens.",
        )


@router.post("/chat", response_model=AgentResponse)
async def chat(request: AgentRequest):
    """
    Main AI conversation endpoint — the heart of RideMate.

    Request → sanitize → validate → OrchestratorAgent → Gemini → tools → response

    The response_model=AgentResponse ensures FastAPI validates the output
    against the Pydantic schema before sending it to the client.
    """
    try:
        # Security: sanitize ALL user-supplied strings before processing.
        # This is defense-in-depth — even with middleware, routes self-protect.
        user_id = sanitize_input(request.user_id, max_length=64)
        message = sanitize_input(request.message, max_length=2000)

        # Validate user_id format — early rejection for malformed IDs.
        _check_user_id(user_id)

        # Reject empty messages early — don't waste a Gemini API call.
        if not message:
            raise HTTPException(status_code=400, detail="Message cannot be empty.")

        # Get or create the user's personal agent (with cached session).
        agent = get_agent(user_id)
        result = agent.process_message(
            user_message=message,
            user_id=user_id,
        )
        return AgentResponse(
            message=result["message"],
            tool_calls_made=result.get("tool_calls_made", []),
            agents_involved=result.get("agents_involved", ["Orchestrator"]),
        )
    except HTTPException:
        raise  # Re-raise client errors (400, 429, etc.) as-is
    except Exception as e:
        # Unexpected errors: log full traceback, return 500 with message.
        # The traceback goes to stderr (visible in terminal), not to the client.
        import traceback
        error_detail = traceback.format_exc()
        print("=" * 50)
        print("ERROR IN CHAT:")
        print(error_detail)
        print("=" * 50)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset")
async def reset_conversation(user_id: str):
    """
    Reset a user's entire conversation state.

    This evicts the OrchestratorAgent from cache, which also resets all
    5 sub-agent Gemini chat sessions. The next /chat request will create
    a fresh OrchestratorAgent with clean history.
    """
    try:
        user_id = sanitize_input(user_id, max_length=64)
        _check_user_id(user_id)

        if user_id in agent_cache:
            agent_cache[user_id].reset()
            del agent_cache[user_id]
        return {"status": "success", "message": "Conversation reset"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """
    Health check — used by load balancers and monitoring.

    Returns active session count for observability.
    Also serves as a liveness probe for Cloud Run.
    """
    return {"status": "healthy", "active_sessions": len(agent_cache)}


@router.get("/board")
async def get_board():
    """
    Get community board messages — direct DB query, no Gemini.

    This is a FAST endpoint (no AI involved). It reads the community_messages
    table directly and returns the 30 most recent posts. Used by the Board tab
    in the demo UI.
    """
    from agent.tools import get_community_messages
    return get_community_messages(limit=30)


@router.get("/drivers/active")
async def get_active():
    """
    Get currently active driver broadcasts — direct DB query, no Gemini.

    Returns all drivers with is_active=1 (currently broadcasting their location).
    Used by the Drivers tab in the demo UI to show LIVE green dots.
    """
    from agent.tools import get_active_drivers
    return get_active_drivers()


@router.get("/welcome/{user_id}")
async def welcome_back(user_id: str):
    """
    Personalized welcome endpoint — aggregates profile + recommendations.

    Called when the demo page loads. Makes 3 direct DB calls:
      1. Ensure user exists (get_or_create_user)
      2. Load full profile with stats
      3. Get personalized ride recommendations
      4. Get upcoming rides

    The frontend renders this as a rich welcome card with stats and suggestions.
    """
    from agent.tools import get_or_create_user, get_user_profile, get_recommendations, get_my_rides

    user_id = sanitize_input(user_id, max_length=64)
    _check_user_id(user_id)

    get_or_create_user(user_id=user_id)
    profile = get_user_profile(user_id=user_id)
    recs = get_recommendations(user_id=user_id)
    rides = get_my_rides(user_id=user_id)

    return {
        "status": "success",
        "user": profile.get("user", {}),
        "recommendations": recs.get("recommendations", [])[:5],
        "stats": recs.get("stats", {}),
        "upcoming_rides": rides.get("as_rider", [])[:3],
    }


@router.get("/test")
async def test():
    """Quick connectivity check — no DB, no AI, instant response."""
    return {"message": "API is working!"}
