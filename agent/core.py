"""
⚠️ DEPRECATED — Legacy single-agent implementation.

This module has been superseded by `agent/multi_agent.py`, which implements
a 5-agent orchestration system (Orchestrator + Matching + RideManager + Profile + Community).

The routes layer (`api/routes.py`) now imports from `multi_agent.py`.
This file is kept for reference only and is no longer imported by any active code.

See `agent/prompts.py` for the current agent system prompts.
"""

import google.generativeai as genai
from typing import List, Dict, Any
import os
import json

from google.ai.generativelanguage_v1beta.types import Content, Part, FunctionResponse

from .tools import get_tool_definitions, execute_tool
from .prompts import SYSTEM_PROMPT
from models.schemas import Message, AgentResponse

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

class RideMateAgent:
    def __init__(self):
        self.model = genai.GenerativeModel(
            model_name=os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp"),
            system_instruction=SYSTEM_PROMPT,
            tools=get_tool_definitions()
        )
        self.chat = None
        self.conversation_history = []

    def process_message(self, user_message: str, user_id: str, history: List[Message] = None) -> AgentResponse:
        """
        Main entry point for processing user messages

        Workflow:
        1. Build conversation context
        2. Send message to Gemini
        3. If Gemini requests a tool call -> execute the tool
        4. Return tool results to Gemini
        5. Get the final response
        """
        # 1. Initialize or resume chat session
        if not self.chat:
            self.chat = self.model.start_chat(history=[])

        # 2. Send user message
        response = self.chat.send_message(user_message)

        tool_calls_made = []
        final_response = ""

        # 3. Process tool calls (core logic)
        # Cap at 10 rounds to prevent infinite loops
        max_tool_rounds = 10
        for _ in range(max_tool_rounds):
            if not response.candidates:
                break

            parts = response.candidates[0].content.parts
            if not parts:
                break

            function_calls_in_round = []

            for part in parts:
                # 3a. Check for function calls
                if hasattr(part, 'function_call') and part.function_call:
                    fc = part.function_call
                    tool_name = fc.name
                    # fc.args may be a dict or protobuf Map — handle both
                    tool_args = dict(fc.args) if fc.args else {}

                    print(f"🔧 Calling tool: {tool_name} with args: {tool_args}")

                    # 3b. Execute the tool
                    tool_result = execute_tool(tool_name, tool_args)
                    tool_calls_made.append(tool_name)

                    print(f"✅ Tool result: {tool_result}")

                    function_calls_in_round.append((tool_name, tool_result))

                # 3c. If it is a text response, collect the text
                elif hasattr(part, 'text') and part.text:
                    final_response += part.text

            # 3d. If there were function calls, return results to Gemini
            if function_calls_in_round:
                # Build properly formatted function responses
                function_response_parts = []
                for tool_name, tool_result in function_calls_in_round:
                    function_response_parts.append(
                        Part(function_response=FunctionResponse(
                            name=tool_name,
                            response={"result": tool_result}
                        ))
                    )

                response = self.chat.send_message(
                    Content(role="function", parts=function_response_parts)
                )
            else:
                # No function calls — exit the loop
                break

        # 4. Build the response
        return AgentResponse(
            message=final_response or "I've processed your request.",
            tool_calls_made=tool_calls_made,
            needs_clarification=False  # Simplified version, can be extended later
        )

    def reset_conversation(self):
        """Reset the chat session"""
        self.chat = None
        self.conversation_history = []
