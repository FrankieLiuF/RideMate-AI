# RideMate AI — Project Writeup

**Google AI Agents Capstone — Concierge Agents Track**

**GitHub:** https://github.com/FrankieLiuF/RideMate-AI

**Demo Video:** [YouTube link — to be added after recording]

---

## Problem Statement

In university towns and small cities, traditional ride-hailing services like Uber and Lyft are often scarce, unreliable, or non-existent. Public transit is limited. Students, staff, and residents who need to get to campus, the airport, or downtown are left with few options.

Existing solutions fail because:
- **No real-time coordination** — drivers and riders have no shared board to announce availability or request rides
- **No intelligent matching** — finding someone heading the same way at the same time is purely luck
- **No persistence** — preferences, history, and trusted drivers are lost between trips
- **No negotiation** — pickup times, meeting points, and fare splitting require manual back-and-forth

A simple ride board isn't enough. What's needed is an **AI agent that actively coordinates** — understanding intent, calling the right tools, remembering preferences, and facilitating communication between community members.

---

## Solution Overview

**RideMate AI** is a multi-agent conversational carpool assistant powered by Google Gemini 2.5 Flash. It operates as a **personal ride coordinator** — users talk to it naturally, and it handles everything from ride creation and discovery to community coordination and booking.

### Why Agents?

A traditional web app would require users to navigate forms, filters, and buttons. A simple chatbot would only answer questions but couldn't take action. **AI agents bridge this gap**: they understand natural language intent, reason about which tools to call, execute those tools, and synthesize results into a coherent response.

The **multi-agent architecture** decomposes the problem naturally:

| Agent | Responsibility | Why separate? |
|---|---|---|
| **Orchestrator** | Routes intent, coordinates specialists | Central control — one entry point, many specialists |
| **Matching Agent** | Searches and recommends rides | Focused on the search problem — ranking, filtering, alternatives |
| **Ride Manager** | Creates rides, processes bookings | Transactional logic (create, book, cancel) with state management |
| **Profile Agent** | User memory, preferences, history | Personalization is a cross-cutting concern best isolated |
| **Community Agent** | Bulletin board, driver broadcasts | Real-time community features with different data models |

Each agent is an independent Gemini ChatSession with its own system prompt and restricted tool set.

---

## Architecture

```
Client (Browser / MCP) → FastAPI → Security → Orchestrator → 4 Specialist Agents → 14 Tools → Database
                                                                              ↕
                                                                        Gemini 2.5 Flash
                                                                     (Function Calling)
```

### Key Design Decisions

**Tool-first design**: Every capability is a callable tool with structured parameters and JSON responses. The agent never "knows" data — it discovers data by calling tools.

**Database-backed from day one**: All 14 tools write through SQLAlchemy to SQLite (dev) or PostgreSQL (prod). No mock data — a user's booking is durable across sessions.

**Middleware-based security**: API key auth, rate limiting, and input sanitization as Starlette middleware — surrounding the application without touching business logic.

**MCP protocol support**: The entire tool suite is also exposed as an MCP server via stdio transport, making RideMate usable from Claude Desktop, Cursor, or any MCP-compatible client without a web server.

### Data Model (6 tables)

| Table | Purpose |
|---|---|
| `users` | Profiles with roles (driver/rider/both), JSON preferences |
| `rides` | Scheduled trips with status lifecycle (active → full/cancelled) |
| `bookings` | Seat reservations with confirmation state |
| `conversations` | Full chat history with agent attribution |
| `driver_statuses` | Real-time location broadcasts with seat count |
| `community_messages` | Shared bulletin board visible to all users |

---

## Key Concepts Demonstrated (Course Requirements)

The project demonstrates **all 6 key concepts** from the course:

### 1. Agent / Multi-Agent System (Code)

Five specialist agents, each an independent Gemini 2.5 Flash ChatSession:
- **OrchestratorAgent** — intent classification, tool dispatch, response synthesis
- **ProfileAgent** — user onboarding, preferences, history (`get_or_create_user`, `get_user_profile`, `update_user_preferences`)
- **MatchingAgent** — ride discovery and recommendation (`search_rides`)
- **RideManager** — ride lifecycle (`create_ride`, `book_ride`, `cancel_booking`, `get_my_rides`)
- **CommunityAgent** — shared board, driver status broadcasts (`broadcast_status`, `get_active_drivers`, `end_broadcast`, `post_community_message`, `get_community_messages`)

Each agent has its own system prompt (in `agent/prompts.py`) and restricted tool set. The Orchestrator coordinates them and returns an `agents_involved` field tracking which agents participated.

**Implementation**: `agent/multi_agent.py` — `BaseAgent` class + `OrchestratorAgent` class with retry logic, tool filtering, and proper `FunctionResponse` protobuf handling.

### 2. MCP Server (Code)

`mcp_server.py` exposes all 14 RideMate tools via the **Model Context Protocol** using the `mcp` Python SDK (stdio transport):

```
python mcp_server.py
```

Configure any MCP client:
```json
{
  "mcpServers": {
    "ridemate": {
      "command": "python",
      "args": ["mcp_server.py"],
      "cwd": "/path/to/RideMate"
    }
  }
}
```

This is a key differentiator — the same tools powering the web API are available to Claude Desktop, Antigravity IDE, Cursor, or any MCP-compatible client without running a web server.

### 3. Antigravity (Video)

The project was developed in Antigravity IDE. The demo video script (`DEMO_SCRIPT.md`) shows the IDE terminal with `ls agent/`, `wc -l agent/tools.py`, and live server logs visible during the demo walkthrough.

### 4. Security Features (Code)

Three independent security layers in `api/security.py`:

| Layer | Implementation | Details |
|---|---|---|
| **API Key Auth** | `APIKeyMiddleware` | Protects `/api/v1/*` endpoints. Constant-time key comparison prevents timing attacks. Toggleable via `API_KEY_REQUIRED`. |
| **Rate Limiting** | `RateLimitMiddleware` | Per-IP sliding window (30 req/60s). Sends proper 429 with `Retry-After` header. Respects `X-Forwarded-For`. |
| **Input Sanitization** | `sanitize_input()`, `validate_user_id()` | Trims, length-caps, strips control characters. Validates user_id against regex. Applied in all route handlers. |

### 5. Deployability (Video + Code)

Complete production deployment pipeline:
- **Dockerfile** — multi-stage build with proper layer caching
- **cloudbuild.yaml** — Google Cloud Build: Docker build → push → Cloud Run deploy
- **Environment-variable-based config** — no hardcoded keys or secrets
- **SQLite for dev, PostgreSQL for prod** — configured via `DATABASE_URL`

One-command deploy:
```bash
gcloud builds submit --config cloudbuild.yaml
```

### 6. Agent Skills / Agents CLI (Code)

The MCP server (`mcp_server.py`) follows the Agents CLI pattern — it's a standalone Python script that launches an MCP-compatible server exposing agent tools, discoverable and callable from any MCP host. Additionally, the tool registry in `agent/tools.py` is self-documenting with typed parameters, descriptions, and Gemini-compatible function declarations — following the agent skill definition pattern.

---

## Evaluation Cases

The system was tested across 5 scenarios covering success, edge, and failure paths.

### Case 1: Happy Path — Driver creates ride, Rider books ✅

| Step | Input | Expected | Result |
|---|---|---|---|
| Register driver | `"I'm Alice, a driver"` | `get_or_create_user` called, role=driver | ✅ |
| Create ride | `"Offer ride University → Downtown, 9am, 3 seats, $5.50"` | `create_ride` called | ✅ Ride #1 |
| Rider searches | `"Find me a ride to Downtown"` (as Bob) | `search_rides` returns ride #1 | ✅ |
| Rider books | `"Book 1 seat on ride #1"` | `book_ride`, seats: 3→2 | ✅ |
| Verify DB | Check state | 1 ride, 2 seats, 1 booking | ✅ |

### Case 2: Community Board — Broadcast and Discovery ✅

| Step | Input | Expected | Result |
|---|---|---|---|
| Driver arrives | `"I'm at Aber Station, 20 min wait, 3 seats to Downtown"` | `broadcast_status` called | ✅ |
| Rider checks | `"Who's near Aber Station right now?"` | `get_active_drivers` returns Alice | ✅ |
| Community post | `"Post to board: splitting ride to Downtown at 5pm?"` | `post_community_message` called | ✅ |
| Driver leaves | `"I'm full, end my broadcast"` | `end_broadcast`, is_active=0 | ✅ |

### Case 3: Edge Case — Booking a full ride ❌

| Step | Input | Expected | Result |
|---|---|---|---|
| Create 1-seat ride | Driver creates ride, 1 seat | Ride stored | ✅ |
| First rider books | `"Book seat on ride #1"` | Confirmed, ride → "full" | ✅ |
| Second rider tries | `"Book seat on ride #1"` | Error: "Ride is full" | ✅ Rejected |
| Verify DB | Check state | 0 seats, status="full" | ✅ |

### Case 4: Edge Case — Missing information ⚠️

| Step | Input | Expected | Result |
|---|---|---|---|
| Vague request | `"I need a ride"` | Agent asks clarifying questions | ✅ Agent probed |
| Partial info | `"To Downtown"` | Agent asks when and from where | ✅ Agent probed |
| Complete info | `"From University to Downtown tomorrow 9am"` | `search_rides` executes | ✅ |

### Case 5: Failure Case — Non-existent entities ❌

| Step | Input | Expected | Result |
|---|---|---|---|
| Book invalid ID | `"Book ride #999"` | Error: "Ride not found" | ✅ |
| Cancel non-existent | `"Cancel booking #999"` | Error: "Booking not found" | ✅ |
| Search empty | `"Find rides from Mars to Jupiter"` | 0 results, friendly message | ✅ |

---

## Project Journey

### Phase 1: Single-Agent MVP
Started with a single `RideMateAgent` (now `agent/core.py`, deprecated) that handled everything in one Gemini session. Proved the Function Calling pattern but showed clear limitations in prompt complexity.

### Phase 2: Multi-Agent Refactor
Split into 5 specialist agents with dedicated prompts and tool subsets. Reduced prompt complexity, improved response quality, and made the system extensible.

### Phase 3: Database + Community Features
Replaced mock data with SQLAlchemy ORM. Added the recommendation engine (frequent route detection), community board, and driver status broadcast.

### Phase 4: Production Hardening
Added MCP server, security middleware, Cloud Run deployment config, comprehensive documentation, and demo video script.

---

## Challenges & Solutions

**Gemini rate limiting (429)**: Implemented 3-attempt retry with 15s/30s backoff in `BaseAgent.process()`.

**Function Calling response format**: Gemini args can be dict or protobuf Map — code handles both: `dict(fc.args) if fc.args else {}`.

**Tool scope isolation**: Early versions had every agent seeing every tool. Now each specialist gets a filtered `tool_names` list.

**Starlette version conflict**: MCP SDK pulled incompatible starlette. Resolved by pinning `starlette<0.47.0` since our MCP server uses stdio (no SSE needed).

---

## Tech Stack

| Category | Technology |
|---|---|
| **Web Framework** | FastAPI 0.115 (async, auto OpenAPI docs) |
| **AI** | Google Gemini 2.5 Flash (Function Calling + protobuf) |
| **ORM** | SQLAlchemy 2.0 (SQLite dev, PostgreSQL prod) |
| **MCP** | MCP Python SDK 1.x (stdio transport) |
| **Language** | Python 3.12+ |
| **Deployment** | Docker + Cloud Run + cloudbuild.yaml |
| **Frontend** | Vanilla HTML/CSS/JS (Next.js planned) |
| **Security** | API key auth, rate limiting, input sanitization |

---

## How to Run

```bash
git clone https://github.com/FrankieLiuF/RideMate-AI.git
cd RideMate-AI
python -m venv .venv && source .venv/Scripts/activate  # or .venv/bin/activate on Mac/Linux
pip install -r requirements.txt
# Create .env: GEMINI_API_KEY=your-key
python main.py                    # FastAPI server → http://localhost:8000
python mcp_server.py              # MCP server → stdio
```

---

## Future Roadmap

- [ ] PostgreSQL migration for production scale
- [ ] Firebase Authentication for secure user accounts
- [ ] Next.js frontend with real-time WebSocket updates
- [ ] Google Maps Platform integration (route calculation, ETA, address autocomplete)
- [ ] Push notifications for booking confirmations and nearby driver broadcasts
- [ ] Reputation system for drivers and riders
- [ ] Mobile app wrapper (React Native / Flutter)
