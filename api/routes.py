"""API routes for the RideMate multi-agent system."""
from fastapi import APIRouter, HTTPException
from typing import Dict
from models.schemas import AgentRequest, AgentResponse
from agent.multi_agent import OrchestratorAgent
from api.security import sanitize_input, validate_user_id

router = APIRouter(prefix="/api/v1", tags=["agent"])

# Agent instances cache (one orchestrator per user)
agent_cache: Dict[str, OrchestratorAgent] = {}


def get_agent(user_id: str) -> OrchestratorAgent:
    """Get or create an orchestrator for a user."""
    if user_id not in agent_cache:
        agent_cache[user_id] = OrchestratorAgent()
    return agent_cache[user_id]


def _check_user_id(user_id: str) -> None:
    """Validate user_id format; raises 400 if invalid."""
    if not validate_user_id(user_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid user_id format. Use 1-64 alphanumeric characters, underscores, or hyphens.",
        )


@router.post("/chat", response_model=AgentResponse)
async def chat(request: AgentRequest):
    """Send a message to the multi-agent system.

    User message is sanitized before processing: whitespace trimmed,
    length capped at 2000 chars, control characters stripped.
    """
    try:
        user_id = sanitize_input(request.user_id, max_length=64)
        message = sanitize_input(request.message, max_length=2000)

        _check_user_id(user_id)

        if not message:
            raise HTTPException(status_code=400, detail="Message cannot be empty.")

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
        raise
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print("=" * 50)
        print("ERROR IN CHAT:")
        print(error_detail)
        print("=" * 50)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset")
async def reset_conversation(user_id: str):
    """Reset a user's conversation with all agents."""
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
    """Health check with agent session count."""
    return {"status": "healthy", "active_sessions": len(agent_cache)}


@router.get("/board")
async def get_board():
    """Get community board messages (direct DB, no Gemini)."""
    from agent.tools import get_community_messages
    return get_community_messages(limit=30)


@router.get("/drivers/active")
async def get_active():
    """Get currently active driver broadcasts (direct DB, no Gemini)."""
    from agent.tools import get_active_drivers
    return get_active_drivers()


@router.get("/welcome/{user_id}")
async def welcome_back(user_id: str):
    """Personalized concierge greeting with stats and recommendations."""
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
    """Quick test endpoint."""
    return {"message": "API is working!"}
