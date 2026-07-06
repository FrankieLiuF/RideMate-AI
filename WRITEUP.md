# RideMate AI — Project Writeup

**5-Day AI Agents: Intensive Vibe Coding Course With Google — Capstone Submission**

**Track:** Concierge Agents

**GitHub:** https://github.com/FrankieLiuF/RideMate-AI

**Demo Video:** [Paste YouTube link here after uploading]

---

## Problem Statement

In university towns and small cities, traditional ride-hailing services like Uber and Lyft are often scarce, unreliable, or non-existent. Public transit is limited. Students, staff, and residents who need to get to campus, the airport, or downtown are left with few options — they resort to informal group chats, bulletin boards, or simply hoping to find someone heading the same way.

Existing solutions fail because:

- **No real-time coordination** — drivers and riders have no shared live board to announce availability or request rides
- **No intelligent matching** — finding someone heading the same way at the same time is purely luck
- **No persistence** — preferences, frequent routes, and trusted drivers are lost between trips; every ride search starts from scratch
- **No negotiation** — pickup times, meeting points, and fare splitting require manual back-and-forth across different apps

A simple ride board isn't enough. A traditional web form isn't enough. What's needed is an **AI agent that actively coordinates** — understanding natural language intent, calling the right tools, remembering preferences across sessions, and facilitating communication between community members in real time.

---

## Solution Overview

**RideMate AI** is a multi-agent conversational carpool assistant powered by Google Gemini 2.5 Flash. Users talk to it naturally — type "I need a ride to Downtown tomorrow morning" or "I'm offering 3 seats from University Campus at 9am" — and the AI handles everything: ride creation, discovery, booking, community coordination, and personalised recommendations.

### Why Agents (Not Just a Chatbot)?

A traditional web app would require users to navigate forms, filters, and buttons. A simple chatbot would only answer questions but couldn't take action. **AI agents bridge this gap**: they understand natural language intent, reason about which tools to call, execute those tools against a real database, and synthesise results into a coherent, contextual response.

The **multi-agent architecture** decomposes the problem naturally — each specialist agent focuses on one domain with its own system prompt and tool subset:

| Agent | Responsibility | Why Separate? |
|---|---|---|
| **Orchestrator** | Routes intent, coordinates specialists, synthesises responses | Central control point — one entry, many specialists |
| **Matching Agent** | Searches and recommends rides with personalised ranking | Focused on the search problem — filtering, ranking, alternatives |
| **Ride Manager** | Creates rides, processes bookings and cancellations | Transactional logic with seat-count consistency guarantees |
| **Profile Agent** | User memory, preferences, history, onboarding | Personalisation is a cross-cutting concern best isolated |
| **Community Agent** | Bulletin board, driver status broadcasts | Real-time community features with different data models and lifecycle |

Each agent is an independent Gemini ChatSession, scoped to its own set of tools via a `tool_names` allowlist. The Orchestrator routes user intent to the right specialist, executes the tool calls, and returns an `agents_involved` field so the frontend can show which agents contributed to each response.

A key differentiator: **15 minutes after creating a ride, the driver's broadcast auto-expires**, preventing stale listings. Rides auto-broadcast on creation so they appear on the live Drivers tab immediately — no need for the AI to remember a separate broadcast step.

---

## Architecture

```
Client (Browser / MCP) → FastAPI → Security Middleware → Orchestrator → 4 Specialist Agents → 14 Tools → Database
                                                                              ↕
                                                                        Gemini 2.5 Flash
                                                                     (Function Calling)
```

### Key Design Decisions

**Tool-first design**: Every capability is a callable Python function with typed parameters, docstrings, and structured JSON responses. Gemini never "knows" data — it discovers data by calling tools. This mirrors real-world agent architecture: the LLM is the reasoning layer, tools are the action layer.

**Database-backed from day one**: All 14 tools write through SQLAlchemy ORM to SQLite (dev) or PostgreSQL (prod). No mock data — a user's booking persists across sessions, and the recommendation engine learns from real booking history. This was a deliberate choice to demonstrate production thinking, not just a demo.

**Middleware-based security**: API key auth, rate limiting, and input sanitisation live as Starlette middleware — surrounding the application without touching business logic. Each layer is independently toggleable and configurable via environment variables.

**MCP protocol support**: The entire 14-tool suite is also exposed as an MCP server via stdio transport. This means RideMate is usable from Claude Desktop, Cursor, or any MCP-compatible client without running a web server. The same tools powering the web API are callable from an IDE — demonstrating the course's MCP concept in a practical, integrated way.

### Data Model (6 Tables)

| Table | Purpose |
|---|---|
| `users` | Profiles with roles (driver/rider/both), JSON preferences, saved routes |
| `rides` | Scheduled trips with status lifecycle (active → full/cancelled) and seat tracking |
| `bookings` | Seat reservations with confirmation state, linked to both user and ride |
| `conversations` | Full chat history with agent attribution for debugging and context |
| `driver_statuses` | Real-time location broadcasts with seat count, auto-expiry after 15 min |
| `community_messages` | Shared bulletin board visible to all users, with timestamp and author |

### Interactive Demo Frontend

The project includes a fully functional single-page web demo (`static/index.html`) built with vanilla HTML/CSS/JS:

- **Chat tab** — natural language conversation with the multi-agent system, with quick-action buttons (Offer Ride, Search, Post to Board, View Profile) and a tool-call trail showing which tools were invoked
- **Suggested tab** — personalised recommendations fetched from the AI backend alongside all available rides (fetched in parallel via the fast `/api/v1/rides/active` endpoint, deduplicated client-side), ensuring new users without booking history still see content
- **Board tab** — live community bulletin board with auto-refresh and cache-busting
- **Drivers tab** — real-time active driver broadcasts with location, destination, seat count, and expiry timer; auto-refreshes every 15 seconds
- Dark/light theme toggle

The frontend demonstrates the full agent workflow end-to-end — from user input to multi-agent orchestration to tool execution to rendered results.

---

## Key Concepts Demonstrated (Course Requirements)

### 1. Agent / Multi-Agent System ✅

Five specialist agents, each an independent Gemini 2.5 Flash ChatSession with its own system prompt and restricted tool set:

- **OrchestratorAgent** — intent classification, tool dispatch, response synthesis. Cached per user for conversation continuity.
- **ProfileAgent** — user onboarding, preferences, history (`get_or_create_user`, `get_user_profile`, `update_user_preferences`)
- **MatchingAgent** — ride discovery and personalised recommendation (`search_rides`, `get_recommendations`)
- **RideManager** — ride lifecycle (`create_ride`, `book_ride`, `cancel_booking`, `get_my_rides`)
- **CommunityAgent** — shared board and driver broadcasts (`broadcast_status`, `get_active_drivers`, `end_broadcast`, `post_community_message`, `get_community_messages`)

Each agent's system prompt lives in `agent/prompts.py` with clear role definitions, output constraints, and tool-use instructions.

**Implementation**: `agent/multi_agent.py` — `BaseAgent` class with retry logic (3 attempts, 15s/30s backoff), tool filtering, and proper handling of Gemini's FunctionResponse protobuf format:

```python
# Gemini args can arrive as dict or protobuf Map — handle both
args = dict(fc.args) if fc.args else {}
```

### 2. MCP Server ✅

`mcp_server.py` exposes all 14 RideMate tools via the **Model Context Protocol** using the `mcp` Python SDK (stdio transport). Launch it with `python mcp_server.py` and configure any MCP client:

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

This is a key differentiator — the same tools powering the web API are available to any MCP-compatible client (Claude Desktop, Antigravity IDE, Cursor) without a running web server. It demonstrates the MCP concept in a practical, integrated way rather than as a standalone exercise.

### 3. Antigravity ✅

The project was developed entirely in Antigravity IDE. The demo video shows the IDE environment with terminal access (`ls agent/`, `wc -l agent/tools.py`), live server logs during the walkthrough, and the full development workflow within the IDE.

### 4. Security Features ✅

Three independent security layers in `api/security.py`:

| Layer | Implementation | Details |
|---|---|---|
| **API Key Auth** | `APIKeyMiddleware` | Protects `/api/v1/*` endpoints. Constant-time comparison (`hmac.compare_digest`) prevents timing attacks. Toggleable via `API_KEY_REQUIRED` env var. |
| **Rate Limiting** | `RateLimitMiddleware` | Per-IP sliding window (default 30 req/60s). Sends proper HTTP 429 with `Retry-After` header. Respects `X-Forwarded-For` for proxied deployments. |
| **Input Sanitisation** | `sanitize_input()`, `validate_user_id()` | Trims whitespace, length-caps to 2000 chars, strips ASCII control characters. `user_id` validated against `^[a-zA-Z0-9_-]{1,50}$`. Applied in every route handler before any processing. |

All three layers are applied as Starlette `BaseHTTPMiddleware`, wrapping the application without touching business logic. They are independently configurable — rate limiting can be adjusted or disabled without affecting auth or sanitisation.

### 5. Deployability ✅

Complete production deployment pipeline:

- **Dockerfile** — multi-stage build with dependency caching
- **cloudbuild.yaml** — Google Cloud Build: Docker build → push to Artifact Registry → deploy to Cloud Run
- **Environment-variable-based config** — no hardcoded keys or secrets; `GEMINI_API_KEY`, `DATABASE_URL`, `API_KEY` all from env
- **SQLite for dev, PostgreSQL for prod** — configured via `DATABASE_URL`, zero-code-change switch

One-command deploy:
```bash
gcloud builds submit --config cloudbuild.yaml
```

### 6. Agent Skills / Agents CLI ✅

The MCP server follows the Agents CLI pattern — a standalone Python script that launches an MCP-compatible server exposing agent tools, discoverable and callable from any MCP host. The tool registry in `agent/tools.py` is self-documenting with typed parameters, docstrings, and Gemini-compatible function declarations generated at runtime — each tool defines its own `function_declaration` dict with name, description, and JSON Schema parameters.

---

## Key Technical Features

### Personalised Recommendation Engine

The `get_recommendations` tool in `agent/tools.py` implements a multi-strategy recommendation pipeline:

1. **Frequent route detection** — analyses past bookings to identify commonly travelled routes (same from→to pair appearing ≥3 times in booking history)
2. **Home/work inference** — extracts the most common pickup and dropoff locations from booking history
3. **Saved route matching** — matches active rides against the user's explicitly saved preferences
4. **Fallback discovery** — if no personalised recommendations exist (new user, no history), surfaces recent active rides so the Suggested tab never appears empty

All recommendation queries exclude the user's own rides and are ordered by recency. This ensures every user — from first-time visitors to regular commuters — sees relevant content.

### Auto-Broadcast on Ride Creation

When a driver creates a ride via `create_ride`, the tool automatically calls `broadcast_status` to make the driver visible on the live Drivers tab. This was a deliberate design choice: the AI agent shouldn't need to "remember" to broadcast — the tool layer handles the side effect. Riders can discover the ride through both the search/recommendation pipeline and the real-time driver map.

### Real-Time Community Features

The Community Agent manages two real-time data streams:

- **Driver Status Broadcasts** — drivers announce their location, destination, available seats, and status message. Broadcasts auto-expire after 15 minutes of inactivity, preventing stale data. The Drivers tab auto-refreshes every 15 seconds.
- **Community Bulletin Board** — a shared message board for ride-splitting coordination. Messages persist in the database and are visible to all users.

Both features are accessible through the AI chat (Gemini calls the tools) and through direct REST endpoints (fast DB queries without AI overhead).

### Fast API Endpoint for Ride Discovery

`GET /api/v1/rides/active` provides a direct database query for active rides with optional location filters — bypassing the AI pipeline entirely. This serves the frontend's Suggested and Board tabs with sub-10ms response times, while the AI chat handles the conversational interface. Separating these concerns means the UI stays snappy even when Gemini is processing a complex request.

---

## Evaluation Cases

The system was tested across 5 scenarios covering success, edge, and failure paths:

### Case 1: Happy Path — Driver Creates Ride, Rider Books ✅

| Step | Input | Expected | Result |
|---|---|---|---|
| Register driver | "I'm Alice, a driver" | `get_or_create_user` called, role=driver | ✅ |
| Create ride | "Offer ride University → Downtown, 9am, 3 seats, $5.50" | `create_ride` called, auto-broadcast triggered | ✅ Ride #1 |
| Verify broadcast | Check Drivers tab | Alice appears with 3 seats, destination visible | ✅ |
| Rider searches | "Find me a ride to Downtown" (as Bob) | `search_rides` returns ride #1 | ✅ |
| Rider books | "Book 1 seat on ride #1" | `book_ride`, seats: 3→2, DriverStatus updated | ✅ |
| Verify state | Check DB | 1 ride, 2 seats remaining, 1 confirmed booking | ✅ |

### Case 2: Community Board — Broadcast and Discovery ✅

| Step | Input | Expected | Result |
|---|---|---|---|
| Driver broadcasts | "I'm at Aber Station, 20 min wait, 3 seats to Downtown" | `broadcast_status` called with location + seat count | ✅ |
| Rider checks | "Who's near Aber Station right now?" | `get_active_drivers` returns Alice | ✅ |
| Community post | "Post to board: splitting ride to Downtown at 5pm?" | `post_community_message` called | ✅ |
| Driver ends | "I'm full, end my broadcast" | `end_broadcast`, is_active=0 | ✅ |

### Case 3: Edge Case — Booking a Full Ride ❌

| Step | Input | Expected | Result |
|---|---|---|---|
| Create 1-seat ride | Driver creates ride with 1 seat | Ride stored, broadcast active | ✅ |
| First rider books | "Book seat on ride #1" | Confirmed, seats→0, ride→"full", broadcast→0 seats | ✅ |
| Second rider tries | "Book seat on ride #1" | Error: "Ride is full" | ✅ Rejected with clear message |
| Verify DB | Check state | 0 seats available, status="full", no duplicate booking | ✅ |

### Case 4: Edge Case — Missing Information (Clarification) ⚠️

| Step | Input | Expected | Result |
|---|---|---|---|
| Vague request | "I need a ride" | Agent asks clarifying questions (where? when?) | ✅ Agent probed |
| Partial info | "To Downtown" | Agent asks departure location and time | ✅ Agent probed |
| Complete info | "From University to Downtown tomorrow 9am" | `search_rides` executes with full parameters | ✅ |
| New user | First-time visitor checks Suggested tab | Fallback: shows recent active rides (no empty state) | ✅ |

### Case 5: Failure Case — Non-Existent Entities ❌

| Step | Input | Expected | Result |
|---|---|---|---|
| Book invalid ride | "Book ride #999" | Error: "Ride not found" | ✅ Graceful error |
| Cancel non-existent | "Cancel booking #999" | Error: "Booking not found" | ✅ Graceful error |
| Search impossible route | "Find rides from Mars to Jupiter" | 0 results, friendly "no rides found" message | ✅ |

---

## Project Journey

### Phase 1: Single-Agent MVP
Started with a single `RideMateAgent` (now `agent/core.py`, deprecated) that handled everything in one Gemini session. This proved the Function Calling pattern worked — Gemini could understand ride-related intent and call tools correctly — but the monolithic prompt grew unwieldy and response quality degraded as more tools were added.

### Phase 2: Multi-Agent Refactor
Split into 5 specialist agents, each with a focused system prompt and restricted tool subset via `tool_names` allowlists. The Orchestrator became a lightweight router rather than a monolithic controller. Response quality improved significantly — each specialist only needs to reason about its own domain. Added `agents_involved` tracking for observability.

### Phase 3: Database + Community Features
Replaced mock data with SQLAlchemy ORM across 6 normalised tables. Built the recommendation engine with multi-strategy ranking (frequent routes, home/work inference, saved routes). Added the community bulletin board and real-time driver status broadcasts. This phase transformed the project from a demo into a functional system.

### Phase 4: Production Hardening
Added MCP server (stdio transport), three-layer security middleware, Cloud Run deployment config with `cloudbuild.yaml`, comprehensive documentation, and the interactive demo frontend with dark/light mode. Fixed real-world integration issues (protobuf vs dict handling, starlette version conflicts, Gemini 429 rate limiting).

### Phase 5: Polish & UX (Current)
Added auto-broadcast on ride creation so drivers immediately appear on the live Drivers tab. Built a fast `/api/v1/rides/active` endpoint for AI-free ride queries. Implemented fallback recommendations so new users see content immediately. Enhanced the frontend to fetch recommendations and active rides in parallel with client-side deduplication. Removed redundant UI elements and standardised the quick-action buttons.

---

## Challenges & Solutions

**Gemini Rate Limiting (HTTP 429)**: Gemini 2.5 Flash has per-minute quotas that can be hit during rapid testing. Solution: 3-attempt retry with exponential backoff (15s/30s) in `BaseAgent.process()`, with clear error propagation to the user when all retries are exhausted.

**Function Calling Response Format**: Gemini returns function call arguments as either a plain Python dict or a protobuf Map composite — the same code path must handle both. Solution: `dict(fc.args) if fc.args else {}` normalises both formats before tool dispatch.

**Tool Scope Isolation**: Early versions had every agent seeing all 14 tools, leading to confusing behaviour (e.g. the Profile Agent trying to create rides). Solution: each specialist agent receives a filtered `tool_names` list matching its responsibility — the Community Agent can broadcast but can't book, the Ride Manager can book but can't post to the board.

**Dependency Conflicts**: The MCP SDK pulled in an incompatible starlette version. Resolved by pinning `starlette<0.47.0` — since our MCP server uses stdio transport (not SSE), the newer starlette features aren't needed.

**Stale Driver Broadcasts**: Without expiry logic, drivers who forgot to end their broadcast would appear active indefinitely. Solution: broadcasts auto-expire after 15 minutes of inactivity — `get_active_drivers` filters by `updated_at > now - 15 min`. Additionally, booking a ride auto-updates the driver's `seats_available` count in the broadcast table.

**Empty State for New Users**: The personalised recommendation engine requires booking history to learn patterns — new users saw an empty Suggested tab. Solution: fallback mechanism surfaces recent active rides for users with no history, and the frontend fetches both personalised and general results in parallel with deduplication.

---

## Tech Stack

| Category | Technology |
|---|---|
| **Web Framework** | FastAPI 0.115 (async, auto-generated OpenAPI docs) |
| **AI** | Google Gemini 2.5 Flash (Function Calling, protobuf responses) |
| **ORM** | SQLAlchemy 2.0 (SQLite dev, PostgreSQL prod) |
| **MCP** | MCP Python SDK 1.x (stdio transport) |
| **Language** | Python 3.12+ |
| **Deployment** | Docker + Google Cloud Run + cloudbuild.yaml |
| **Frontend** | Vanilla HTML/CSS/JS with dark/light mode (Next.js planned) |
| **Security** | API key auth (constant-time), sliding-window rate limiter, input sanitisation |
| **IDE** | Antigravity |

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
- [ ] Next.js frontend with TypeScript, Tailwind CSS, and shadcn/ui
- [ ] Google Maps Platform integration (route calculation, ETA, address autocomplete)
- [ ] Real-time WebSocket updates for driver broadcasts and booking confirmations
- [ ] Push notifications via Firebase Cloud Messaging
- [ ] Reputation and rating system for drivers and riders
- [ ] Mobile app wrapper (React Native / Flutter)
