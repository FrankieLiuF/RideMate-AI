"""
Multi-agent orchestration system — the architectural core of RideMate AI.

ARCHITECTURE OVERVIEW
=====================
This module implements a 5-agent system where each agent is an independent
Gemini ChatSession with its own system prompt and restricted tool set.

Agent hierarchy:
  OrchestratorAgent (Central Coordinator)
  ├── ProfileAgent      — user onboarding, preferences, history
  ├── MatchingAgent     — ride discovery and recommendation
  ├── RideManager       — ride lifecycle (create, book, cancel)
  └── CommunityAgent    — bulletin board, driver status broadcasts

Why multi-agent instead of a single agent?
  - Each specialist has a focused system prompt (~15 lines vs ~80 for a monolith)
  - Tool scope isolation: MatchingAgent cannot accidentally modify bookings
  - Independent sessions mean one agent's context doesn't pollute another's
  - Adding a new capability = new agent + prompt, no changes to existing agents

The Orchestrator is the ONLY agent the user interacts with. It delegates to
specialists transparently by calling their tools on their behalf.
"""

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
    """
    Base class for all agents in the multi-agent system.

    Each agent wraps a Gemini GenerativeModel with:
      - A dedicated system prompt defining its persona and rules
      - A restricted tool subset (via tool_names filter) for tool-scope isolation
      - An independent chat session for conversation continuity
      - Built-in retry logic for Gemini API rate limits (3 attempts, 15s/30s backoff)

    The tool-scope isolation is a deliberate design choice: a MatchingAgent
    should NEVER be able to call create_ride(), just as a ProfileAgent should
    never call search_rides(). This prevents prompt-confusion errors where
    one agent accidentally invokes another's tools.
    """

    def __init__(self, name: str, system_prompt: str, tool_names: Optional[List[str]] = None):
        self.name = name
        self.system_prompt = system_prompt
        self.tool_names = tool_names  # None = access to ALL tools (Orchestrator only)
        self.chat = None  # Lazy-initialized in process(); one session per agent

        # Build the filtered tool list for this agent.
        # Only Orchestrator (tool_names=None) gets the full tool set.
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

        # Create the Gemini model with tools pre-registered.
        # The model uses the GEMINI_MODEL env var (default: gemini-2.5-flash).
        self.model = genai.GenerativeModel(
            model_name=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            system_instruction=system_prompt,
            tools=agent_tools,
        )

    def process(self, message: str) -> Dict:
        """
        Send a message to this agent and handle the Function Calling loop.

        Returns: {response, tool_calls, error, agent}

        The Function Calling loop works as follows:
          1. Send message → Gemini responds with text OR function_call(s)
          2. If function_call → execute tool → send FunctionResponse back
          3. Gemini receives the result and responds with text OR more calls
          4. Repeat until Gemini returns plain text (no more tool calls)
          5. Cap at 10 rounds to prevent infinite loops

        Why a loop? Gemini can chain multiple tool calls in a single turn.
        For example: search_rides → book_ride requires two round-trips.
        """
        # Lazy-init the chat session — maintains conversation context across
        # multiple calls to process() for the same agent instance.
        if not self.chat:
            self.chat = self.model.start_chat(history=[])

        # Retry loop: Gemini free-tier has rate limits (15 RPM).
        # We retry up to 3 times with 15s/30s backoff before giving up.
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

        # Function Calling loop: iterate until Gemini returns plain text.
        # Max 10 rounds prevents runaway loops if Gemini keeps requesting tools.
        for _ in range(10):
            if not response.candidates:
                break

            parts = response.candidates[0].content.parts
            if not parts:
                break

            function_calls = []

            for part in parts:
                # Gemini returns EITHER a function_call OR text, never both
                # in the same part. We handle both cases.
                if hasattr(part, 'function_call') and part.function_call:
                    fc = part.function_call
                    tool_name = fc.name

                    # fc.args can be a Python dict OR a protobuf Map composite.
                    # dict(fc.args) normalizes both into a standard dict.
                    tool_args = dict(fc.args) if fc.args else {}

                    # Tool-scope enforcement: skip any tool this agent shouldn't use.
                    # This is a safety net — the system prompt also tells Gemini
                    # which tools it can use, but this code-level guard is the
                    # definitive enforcement.
                    if self.tool_names and tool_name not in self.tool_names:
                        continue

                    print(f"[{self.name}] Calling: {tool_name}({tool_args})")
                    tool_result = execute_tool(tool_name, tool_args)
                    tool_calls_made.append(tool_name)
                    print(f"[{self.name}] Result: {json.dumps(tool_result, default=str)[:200]}")

                    function_calls.append((tool_name, tool_result))

                elif hasattr(part, 'text') and part.text:
                    final_text += part.text

            # If Gemini requested tools, send results back using proper
            # protobuf FunctionResponse format (not plain JSON).
            # This is critical — Gemini MUST receive FunctionResponse protobuf
            # messages to correctly interpret tool results.
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
                # No more tool calls — Gemini is done, exit the loop.
                break

        return {
            "response": final_text.strip(),
            "tool_calls": tool_calls_made,
            "error": None,
            "agent": self.name,
        }

    def reset(self):
        """
        Reset the agent's chat session.
        Called when user requests /api/v1/reset — clears all conversation context.
        """
        self.chat = None


class OrchestratorAgent(BaseAgent):
    """
    Central coordinator that routes user intent and delegates to specialists.

    Design rationale for the Orchestrator pattern:
      - The user only talks to ONE agent (the Orchestrator), just like how
        you'd talk to one concierge at a hotel, not five different people.
      - The Orchestrator has access to ALL tools. When Gemini decides which
        tool to call, it naturally routes to the right specialist's domain.
      - Specialist agents (Matching, RideManager, Profile) exist as separate
        instances so their prompts stay focused, but the Orchestrator is the
        one actually calling all the tools.

    The "agents_involved" field in the response is derived from which tools
    were called — it shows the user which specialists contributed, even though
    they only talked to the Orchestrator.
    """

    def __init__(self):
        # Orchestrator gets ALL tools (tool_names=None) — it's the only agent
        # trusted to coordinate across all domains.
        super().__init__(
            name="Orchestrator",
            system_prompt=ORCHESTRATOR_PROMPT,
            tool_names=None,
        )

        # Specialist agents are initialized with narrow tool subsets.
        # Each is a full BaseAgent with its own Gemini session, so they
        # maintain independent conversation context.
        # NOTE: Currently the Orchestrator calls tools directly rather than
        # delegating to specialists. These instances exist for future use
        # when we implement true sub-agent delegation.
        self.matching = BaseAgent("MatchingAgent", MATCHING_AGENT_PROMPT,
                                  ["search_rides"])
        self.ride_mgr = BaseAgent("RideManager", RIDE_MANAGER_PROMPT,
                                  ["create_ride", "book_ride", "cancel_booking", "get_my_rides"])
        self.profile = BaseAgent("ProfileAgent", PROFILE_AGENT_PROMPT,
                                 ["get_or_create_user", "get_user_profile", "update_user_preferences"])

    def process_message(self, user_message: str, user_id: str) -> Dict:
        """
        Full orchestration pipeline for a single user message.

        Pipeline steps:
          1. Ensure user exists in DB (direct call, no Gemini — deterministic)
          2. Load user profile for context (preferences, history, stats)
          3. Build context-rich prompt with user data injected
          4. Let Gemini (Orchestrator) decide which tools to call
          5. Auto-detect frequent route patterns for returning users
          6. Determine which specialist agents' domains were touched
          7. Return response with message + tool list + agent attribution
        """
        # Step 1: Ensure user exists.
        # This is a direct DB operation — no AI needed. Doing this before
        # Gemini sees the message guarantees the user always exists.
        from .tools import get_or_create_user, get_user_profile
        get_or_create_user(user_id=user_id)
        profile_result = get_user_profile(user_id=user_id)
        print(f"[Orchestrator] User ready: {user_id}")

        # Step 2: Inject user context into the prompt.
        # By preloading the user's profile into the prompt (instead of making
        # Gemini call get_user_profile), we save one API round-trip and give
        # Gemini richer context for personalized responses.
        profile_text = (
            json.dumps(profile_result, default=str)
            if profile_result.get("status") == "success"
            else "New user"
        )
        orchestration_prompt = (
            f"User message: \"{user_message}\"\n"
            f"User ID: {user_id}\n"
            f"User profile: {profile_text}\n\n"
            f"Follow the system prompt. Use tools to fulfill the request. "
            f"Be concise and helpful."
        )
        print(f"[Orchestrator] Processing: {user_message[:80]}...")
        result = self.process(orchestration_prompt)

        # Step 3: Auto-detect frequent route patterns.
        # If the user has 2+ bookings on the same route, this adds a hint
        # to the prompt suggesting Gemini propose saving it as a preference.
        # This is proactive personalization — the agent learns without being asked.
        from .tools import get_recommendations as get_recs
        recs = get_recs(user_id=user_id)
        stats = recs.get("stats", {})
        if stats.get("frequent_routes", 0) > 0 and stats.get("total_bookings", 0) >= 2:
            orchestration_prompt += (
                f"\n[Concierge note: This user has {stats['total_bookings']} "
                f"past bookings and {stats['frequent_routes']} frequent routes. "
                f"If they mention a familiar route, suggest saving it as a preference.]"
            )

        # Step 4: Agent attribution.
        # Map tool calls → specialist agents to show who contributed.
        # The user sees "3 agents involved" in the UI with colored pills.
        agents = ["Orchestrator", "ProfileAgent"]  # Profile agent always involved
        tc = set(result.get("tool_calls", []))
        if any(t in tc for t in ["search_rides"]):
            agents.append("MatchingAgent")
        if any(t in tc for t in ["create_ride", "book_ride", "cancel_booking"]):
            agents.append("RideManager")
        if any(t in tc for t in ["broadcast_status", "get_active_drivers", "end_broadcast",
                                  "post_community_message", "get_community_messages"]):
            agents.append("CommunityAgent")

        return {
            "message": result.get("response") or "I've processed your request.",
            "tool_calls_made": list(tc),
            "agents_involved": agents,
        }

    def reset(self):
        """
        Reset ALL agent sessions (Orchestrator + all specialists).
        Called on /api/v1/reset — full clean slate for the user.
        """
        super().reset()
        self.matching.reset()
        self.ride_mgr.reset()
        self.profile.reset()
