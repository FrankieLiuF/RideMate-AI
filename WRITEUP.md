# RideMate AI — Project Writeup

**5-Day AI Agents: Intensive Vibe Coding Course With Google — Capstone Submission**

**Track:** Concierge Agents

**GitHub:** https://github.com/FrankieLiuF/RideMate-AI

**Demo Video:** [Paste YouTube link here after uploading]

---

## Problem Statement

In university towns and small cities, traditional ride-hailing services like Uber and Lyft are scarce or non-existent. Public transit is limited. Students, staff, and residents resort to informal group chats or simply hoping to find someone heading the same way.

Existing solutions fail because:

- **No real-time coordination** — drivers and riders have no shared live board to announce availability or request rides
- **No intelligent matching** — finding someone heading the same way at the same time is purely luck
- **No persistence** — preferences, routes, and trusted drivers are lost between trips; every ride search starts from scratch
- **No negotiation** — pickup times, meeting points, and fare splitting require manual back-and-forth across different apps

A simple ride board isn't enough. What's needed is an **AI agent that actively coordinates** — understanding natural language intent, calling tools, remembering preferences, and facilitating community communication in real time.

---

## Solution Overview

**RideMate AI** is a multi-agent conversational carpool assistant powered by Google Gemini 2.5 Flash. Users talk naturally — "I need a ride to Downtown tomorrow morning" or "Offering 3 seats from University Campus at 9am" — and the AI handles ride creation, discovery, booking, community coordination, and personalised recommendations.

### Multi-Agent Architecture

The problem decomposes naturally into specialist agents, each with its own Gemini ChatSession, system prompt, and tool subset:

| Agent | Responsibility | Tool Set |
|---|---|---|
| **Orchestrator** | Intent routing, specialist coordination, response synthesis | All tools (dispatcher only) |
| **Matching Agent** | Ride search, ranking, personalised recommendations | `search_rides`, `get_recommendations` |
| **Ride Manager** | Ride lifecycle: create, book, cancel | `create_ride`, `book_ride`, `cancel_booking`, `get_my_rides` |
| **Profile Agent** | User memory, preferences, onboarding | `get_or_create_user`, `get_user_profile`, `update_user_preferences` |
| **Community Agent** | Bulletin board, driver broadcasts | `broadcast_status`, `get_active_drivers`, `end_broadcast`, `post_community_message`, `get_community_messages` |

Each agent operates independently — the Orchestrator routes intent to the right specialist, executes tool calls, and synthesises the response. The `agents_involved` field tracks which agents contributed, enabling frontend transparency and debugging.

Key design choice: `create_ride` auto-triggers `broadcast_status` internally — drivers appear on the live Drivers tab immediately without the AI needing to "remember" a separate broadcast step. Broadcasts auto-expire after 15 minutes of inactivity to prevent stale listings.

---

## Architecture

```
Client (Browser / MCP) → FastAPI → Security Middleware → Orchestrator → 4 Specialist Agents → 14 Tools → Database
                                                                              ↕
                                                                        Gemini 2.5 Flash
                                                                     (Function Calling)
```

### Key Decisions

**Tool-first design**: Every capability is a callable Python function with typed parameters and structured JSON responses. Gemini never "knows" data — it discovers data by calling tools. This mirrors real-world agent architecture: the LLM reasons, tools act.

**Database-backed**: All 14 tools write through SQLAlchemy to SQLite (dev) or PostgreSQL (prod). No mock data — bookings persist across sessions, and the recommendation engine learns from real history.

**Middleware-based security**: API key auth (constant-time comparison), sliding-window rate limiting (30 req/60s with `Retry-After`), and input sanitisation live as independent Starlette middleware — wrapping the app without touching business logic.

**MCP protocol**: `mcp_server.py` exposes all 14 tools via stdio transport. The same tools powering the web API are callable from Claude Desktop, Antigravity, or any MCP client — no web server needed. This demonstrates MCP as a practical integration, not a standalone exercise.

### Data Model (6 Tables)

| Table | Purpose |
|---|---|
| `users` | Profiles with roles, JSON preferences, saved routes |
| `rides` | Trips with status lifecycle (active → full/cancelled), seat tracking |
| `bookings` | Seat reservations linked to user and ride |
| `conversations` | Chat history with agent attribution |
| `driver_statuses` | Real-time broadcasts with seat count, 15-min auto-expiry |
| `community_messages` | Shared bulletin board visible to all |

### Interactive Demo UI

A single-page demo (`static/index.html`) with four tabs: Chat (natural language + quick-action buttons + tool-call trail), Suggested (personalised recommendations + all active rides fetched in parallel, deduplicated client-side), Board (live bulletin board with cache-busting), and Drivers (real-time broadcasts, 15s auto-refresh). Dark/light theme included.

---

## Key Concepts Demonstrated

### 1. Agent / Multi-Agent System

Five specialist agents in `agent/multi_agent.py` — each an independent Gemini 2.5 Flash ChatSession with retry logic (3 attempts, 15s/30s backoff), tool filtering, and protobuf/dict handling. System prompts in `agent/prompts.py` define clear role boundaries and output constraints per agent.

### 2. MCP Server

`mcp_server.py` exposes all 14 tools via MCP stdio transport. Configure any MCP client with a JSON entry pointing to the script — the tools become available as native function calls. This integrates the course's MCP concept directly into the project rather than treating it as a separate exercise.

### 3. Antigravity

Entire project developed in Antigravity IDE. The demo video shows terminal usage, live server logs, and the full dev workflow within the IDE.

### 4. Security

Three independent layers in `api/security.py`: API key auth (`hmac.compare_digest`), per-IP sliding-window rate limiter (429 + `Retry-After`), and input sanitisation (length cap, control character strip, regex validation). All toggleable via env vars.

### 5. Deployability

Dockerfile + `cloudbuild.yaml` for one-command Cloud Run deployment. Zero-code-change switch between SQLite and PostgreSQL via `DATABASE_URL`. All secrets via environment variables.

### 6. Agent Skills / Agents CLI

Tool registry in `agent/tools.py` is self-documenting with typed parameters, docstrings, and Gemini-compatible function declarations generated at runtime. MCP server follows the Agents CLI pattern — standalone script, stdio transport, discoverable tools.

---

## Key Technical Features

### Recommendation Engine

Multi-strategy pipeline in `get_recommendations`: (1) frequent route detection from booking history (same from→to ≥3 times), (2) home/work location inference from booking patterns, (3) saved route matching against user preferences, (4) fallback to recent active rides for new users. All queries exclude the user's own rides and sort by recency. The frontend fetches both personalised recommendations and all active rides in parallel via the fast `/api/v1/rides/active` endpoint, deduplicating client-side — ensuring every user sees relevant content.

### Real-Time Community Features

Driver status broadcasts with real-time location, destination, and seat count. Auto-expiry after 15 minutes prevents stale data. `book_ride` and `cancel_booking` automatically sync `seats_available` to the broadcast table. Community bulletin board with persistent messages visible to all users.

---

## Evaluation Cases

### Case 1: Happy Path — Create & Book ✅
Alice (driver) registers, creates a ride (University → Downtown, 3 seats, $5.50), auto-broadcast fires. Bob (rider) searches "Find me a ride to Downtown" → `search_rides` returns Alice's ride. Bob books 1 seat → seats decrement to 2, broadcast updated. DB verified: 1 ride, 2 seats, 1 booking.

### Case 2: Community Board — Broadcast & Discovery ✅
Driver broadcasts arrival at Aber Station (3 seats, 20 min). Rider queries "Who's near Aber Station?" → `get_active_drivers` returns the driver. Community post made. Driver ends broadcast → `is_active=0`.

### Case 3: Booking a Full Ride ❌
1-seat ride created. First rider books successfully (seats→0, status→"full"). Second rider attempts booking → rejected with "Ride is full". DB verified: 0 seats, no duplicate booking.

### Case 4: Missing Information (Clarification) ⚠️
Vague "I need a ride" → agent asks where and when. Partial "To Downtown" → agent asks departure location. Complete "University to Downtown tomorrow 9am" → search executes. New user with no history → fallback shows recent active rides.

### Case 5: Non-Existent Entities ❌
Booking ride #999 → "Ride not found". Cancelling booking #999 → "Booking not found". Searching "Mars to Jupiter" → 0 results, friendly message.

---

## Project Journey

**Phase 1 — Single-Agent MVP**: One Gemini session handling everything. Proved Function Calling worked, but the monolithic prompt degraded as tools grew.

**Phase 2 — Multi-Agent Refactor**: Split into 5 specialists with focused prompts and restricted tool subsets. Response quality improved significantly.

**Phase 3 — Database + Community**: Replaced mock data with SQLAlchemy ORM (6 tables). Built recommendation engine, community board, driver broadcasts.

**Phase 4 — Production Hardening**: MCP server, security middleware, Cloud Run deploy config, Dockerfile, interactive demo frontend.

**Phase 5 — Polish & UX**: Auto-broadcast on ride creation, fast `/api/v1/rides/active` endpoint, fallback recommendations, parallel frontend fetching with deduplication.

---

## Challenges & Solutions

**Gemini 429 rate limiting**: 3-attempt retry with exponential backoff (15s/30s) in `BaseAgent.process()`.

**Function Calling format variance**: Gemini returns args as dict or protobuf Map — `dict(fc.args) if fc.args else {}` handles both.

**Tool scope isolation**: Early versions let every agent see all tools. Fixed with `tool_names` allowlists per specialist.

**Dependency conflicts**: MCP SDK pulled incompatible starlette. Resolved by pinning `starlette<0.47.0` (stdio transport doesn't need SSE).

**Stale driver broadcasts**: Auto-expiry after 15 minutes; `book_ride`/`cancel_booking` sync seat counts to the broadcast table.

**Empty state for new users**: Fallback recommendations + parallel frontend fetching ensures content is always visible.

---

## Tech Stack

| Category | Technology |
|---|---|
| **Framework** | FastAPI 0.115 (async, auto OpenAPI docs) |
| **AI** | Google Gemini 2.5 Flash (Function Calling) |
| **ORM** | SQLAlchemy 2.0 (SQLite dev, PostgreSQL prod) |
| **MCP** | MCP Python SDK 1.x (stdio transport) |
| **Language** | Python 3.12+ |
| **Deployment** | Docker + Cloud Run + cloudbuild.yaml |
| **Frontend** | Vanilla HTML/CSS/JS, dark/light mode |
| **Security** | API key auth, rate limiter, input sanitisation |
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
- [ ] Next.js frontend with TypeScript, Tailwind CSS, shadcn/ui
- [ ] Google Maps Platform integration (route calculation, ETA, address autocomplete)
- [ ] Real-time WebSocket updates for broadcasts and booking notifications
- [ ] Push notifications via Firebase Cloud Messaging
- [ ] Reputation and rating system
- [ ] Mobile app wrapper (React Native / Flutter)
