from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from enum import Enum

class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

class Message(BaseModel):
    role: MessageRole
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None

class AgentRequest(BaseModel):
    """User request"""
    user_id: str
    message: str
    conversation_history: Optional[List[Message]] = []

class AgentResponse(BaseModel):
    """Agent response"""
    message: str
    tool_calls_made: List[str] = []
    agents_involved: List[str] = []
    needs_clarification: bool = False
    clarification_question: Optional[str] = None