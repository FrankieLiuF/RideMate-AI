"""Base agent class and specialist agent definitions for the multi-agent system."""
import google.generativeai as genai
from google.ai.generativelanguage_v1beta.types import Content, Part, FunctionResponse
from google.api_core import exceptions as api_exceptions
from typing import List, Dict, Optional
import json
import os
import time

from .tools import get_tool_definitions, execute_tool, TOOLS_REGISTRY
from .prompts import (
    ORCHESTRATOR_PROMPT,
    MATCHING_AGENT_PROMPT,
    RIDE_MANAGER_PROMPT,
    PROFILE_AGENT_PROMPT,
)


class BaseAgent:
    """Base class for all agents in the multi-agent system."""

    def __init__(self, name: str, system_prompt: str, tool_names: Optional[List[str]] = None):
        self.name = name
        self.system_prompt = system_prompt
        self.tool_names = tool_names
        self.chat = None

        # Get only the tools this agent needs
        if tool_names:
            agent_tools = [t for t in get_tool_definitions()
                          for fd in t.get("function_declarations", [])
                          if fd["name"] in tool_names]
            agent_tools = [{"function_declarations": [
                fd for t in get_tool_definitions()
                for fd in t.get("function_declarations", [])
                if fd["name"] in tool_names
            ]}] if tool_names else None
        else:
            agent_tools = get_tool_definitions()

        self.model = genai.GenerativeModel(
            model_name=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            system_instruction=system_prompt,
            tools=agent_tools,
        )

    def process(self, message: str) -> Dict:
        """Process a message and return {response, tool_calls, error}."""
        if not self.chat:
            self.chat = self.model.start_chat(history=[])

        for attempt in range(3):
            try:
                response = self.chat.send_message(message)
                break
            except api_exceptions.ResourceExhausted as e:
                if attempt < 2:
                    wait = 15 * (attempt + 1)
                    print(f"[{self.name}] Rate limit hit, waiting {wait}s...")
                    time.sleep(wait)
                    continue
                return {"response": "", "tool_calls": [], "error": "Rate limited. Please wait a moment and try again."}
            except Exception as e:
                return {"response": "", "tool_calls": [], "error": str(e)}

        final_text = ""
        tool_calls_made = []

        for _ in range(10):
            if not response.candidates:
                break

            parts = response.candidates[0].content.parts
            if not parts:
                break

            function_calls = []

            for part in parts:
                if hasattr(part, 'function_call') and part.function_call:
                    fc = part.function_call
                    tool_name = fc.name
                    tool_args = dict(fc.args) if fc.args else {}

                    if self.tool_names and tool_name not in self.tool_names:
                        continue  # Agent tried to call a tool it doesn't own

                    print(f"[{self.name}] Calling: {tool_name}({tool_args})")
                    tool_result = execute_tool(tool_name, tool_args)
                    tool_calls_made.append(tool_name)
                    print(f"[{self.name}] Result: {json.dumps(tool_result, default=str)[:200]}")

                    function_calls.append((tool_name, tool_result))

                elif hasattr(part, 'text') and part.text:
                    final_text += part.text

            if function_calls:
                response_parts = [
                    Part(function_response=FunctionResponse(
                        name=name, response={"result": result}
                    ))
                    for name, result in function_calls
                ]
                response = self.chat.send_message(
                    Content(role="function", parts=response_parts)
                )
            else:
                break

        return {
            "response": final_text.strip(),
            "tool_calls": tool_calls_made,
            "error": None,
            "agent": self.name,
        }

    def reset(self):
        """Reset the chat session."""
        self.chat = None


class OrchestratorAgent(BaseAgent):
    """Central coordinator that routes to specialists."""

    def __init__(self):
        super().__init__(
            name="Orchestrator",
            system_prompt=ORCHESTRATOR_PROMPT,
            tool_names=None,  # Orchestrator has access to ALL tools
        )
        # Create specialist agents
        self.matching = BaseAgent("MatchingAgent", MATCHING_AGENT_PROMPT,
                                  ["search_rides"])
        self.ride_mgr = BaseAgent("RideManager", RIDE_MANAGER_PROMPT,
                                  ["create_ride", "book_ride", "cancel_booking", "get_my_rides"])
        self.profile = BaseAgent("ProfileAgent", PROFILE_AGENT_PROMPT,
                                 ["get_or_create_user", "get_user_profile", "update_user_preferences"])

    def process_message(self, user_message: str, user_id: str) -> Dict:
        """Full orchestration: ensure user → intent → tool calls → response."""
        # Step 1: Ensure user exists (direct DB call, no Gemini needed)
        from .tools import get_or_create_user, get_user_profile
        user_result = get_or_create_user(user_id=user_id)
        profile_result = get_user_profile(user_id=user_id)
        print(f"[Orchestrator] User ready: {user_result.get('user', {}).get('user_id')}")

        # Step 2: Build context-rich prompt and let orchestrator handle everything
        profile_text = json.dumps(profile_result, default=str) if profile_result.get("status") == "success" else "New user"
        orchestration_prompt = (
            f"User message: \"{user_message}\"\n"
            f"User ID: {user_id}\n"
            f"User profile: {profile_text}\n\n"
            f"Follow the system prompt. Use tools to fulfill the request. "
            f"Be concise and helpful."
        )
        print(f"[Orchestrator] Processing: {user_message[:80]}...")
        result = self.process(orchestration_prompt)

        # Step 3a: Auto-detect route patterns for returning users
        from .tools import get_recommendations as get_recs
        recs = get_recs(user_id=user_id)
        stats = recs.get("stats", {})
        if stats.get("frequent_routes", 0) > 0 and stats.get("total_bookings", 0) >= 2:
            # Add context about frequent routes to help Gemini personalize
            freq_info = f"\n[Concierge note: This user has {stats['total_bookings']} past bookings and {stats['frequent_routes']} frequent routes. If they mention a familiar route, suggest saving it as a preference.]"
            orchestration_prompt += freq_info

        # Step 3b: Determine which agents were involved
        agents = ["Orchestrator", "ProfileAgent"]
        tc = set(result.get("tool_calls", []))
        if any(t in tc for t in ["search_rides"]):
            agents.append("MatchingAgent")
        if any(t in tc for t in ["create_ride", "book_ride", "cancel_booking"]):
            agents.append("RideManager")
        if any(t in tc for t in ["broadcast_status", "get_active_drivers", "end_broadcast",
                                  "post_community_message", "get_community_messages"]):
            agents.append("CommunityAgent")

        return {
            "message": result.get("response") or "I've processed your request. How else can I help?",
            "tool_calls_made": list(tc),
            "agents_involved": agents,
        }

    def reset(self):
        """Reset all agent sessions."""
        super().reset()
        self.matching.reset()
        self.ride_mgr.reset()
        self.profile.reset()
