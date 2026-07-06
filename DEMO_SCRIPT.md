# RideMate AI — Demo Video Script (~5 minutes)

## Before You Record

1. Delete `ridemate.db` (fresh start)
2. Open **Antigravity IDE** terminal, run: `python main.py`
3. Open browser, pin these tabs:
   - **Tab A**: `http://localhost:8000` (the demo app)
   - **Tab B**: `http://localhost:8000/docs` (Swagger API docs)
4. Have `api/security.py` and `cloudbuild.yaml` open in editor tabs
5. Make sure the Antigravity IDE terminal is visible on screen
6. Start screen recording (Win+G for Game Bar, or OBS)

---

## The Script

### Part 1 — Intro (0:00 - 0:30)

**Screen: Show Tab A (demo app) with the purple welcome card visible**

> "Hi, I'm Frankie. This is RideMate AI — a personal ride coordinator built for the Google AI Agents Capstone, Concierge Agents track."

**Switch to Antigravity IDE terminal. Run: `ls agent/`**

> "RideMate uses five specialist Gemini agents: a Coordinator that routes intent, a Discovery agent for finding rides, a Bookings agent for reservations, a Board agent for the community, and a Profile agent for user memory."

**In terminal, run: `wc -l agent/tools.py`**

> "Fourteen structured tools handle everything from ride creation to community broadcasting, all backed by a SQLite database with persistent memory across sessions."

> 🔑 **KEY CONCEPT — Multi-Agent System**: 5 independent Gemini ChatSessions, each with its own system prompt and restricted tool set.

**Switch to Tab B (Swagger UI)**

> "The full API is documented with Swagger — request schemas, response models, everything typed and self-documenting."

---

### Part 2 — Driver Broadcasts Their Location (0:30 - 1:05)

**Switch to Tab A (demo app). Click the ☀️/🌙 toggle**

> "Here's the interface. Claymorphism design, light and dark mode. These colored pills at the top light up to show which agents are active in each response."

**Click the "📍 Arrived" quick button**

> "Let's start with a driver. This button simulates a driver arriving at a pickup spot and broadcasting their location."

**Wait for response. Point to the agent trail below the message.**

> "Three agents lit up — Coordinator, Board, and Profile. The system registered the driver, broadcasted their location to the community, and stored their profile."

**Switch to Antigravity IDE terminal. Point to the log lines.**

> "In the terminal: Profile agent registered the driver, Board agent called `broadcast_status`. Every tool call is logged and traceable."

**Switch back to Tab A. Click the 📍 Drivers tab on the right.**

> "The driver is now live on the Drivers tab — there's Alice, with a LIVE green dot. Any rider nearby can find her instantly."

---

### Part 3 — Rider Searches and Books (1:05 - 1:45)

**Click back to chat. Click the "🔍 Search" quick button**

> "Now from a rider's perspective. I'll search for rides to Downtown."

**Wait for response**

> "The Discovery agent searched the database and found Alice's ride. Departure time, available seats, price — all from the database, not mock data."

**Type in chat:**

`Book ride #1 for me, 1 seat`

**Wait for response**

> "The Bookings agent confirmed. One seat deducted — database updated in real time: 3 seats → 2 remaining."

> 🔑 **KEY CONCEPT — Agent Skills / Tools**: All 14 tools return structured JSON via Gemini Function Calling with proper `FunctionResponse` protobuf messages.

---

### Part 4 — Community Board (1:45 - 2:15)

**Click the 📋 Board tab on the right**

> "The community board — a shared bulletin board where riders and drivers coordinate in real time."

**Click the "📋 Post" quick button**

> "I'll post a message to the board."

**Point to the newly appeared board card**

> "The message appears instantly for everyone. Anyone opening the app sees this on the Board tab. No polling, no refresh — it's live."

---

### Part 5 — Personalized Recommendations (2:15 - 3:00)

**Click the ✨ Suggested tab on the right**

> "This is personalized recommendations. It analyzes booking history and detects frequent routes — no user configuration needed."

**Point to the welcome card with stats**

> "Two rides taken, one frequent route detected. If a matching ride is available, I get a one-click 'Book Now' button right in the card."

**Point to the recommendation card**

> "University-to-Downtown twice — flagged as a frequent route. The agent learns my patterns and proactively suggests rides. This is memory-driven personalization."

> 🔑 **KEY CONCEPT — Memory**: 6 SQLAlchemy tables persist across sessions. User preferences, ride history, and frequent routes survive server restarts.

**Click the ☀️/🌙 toggle**

> "And dark mode, of course. Works across all tabs."

---

### Part 6 — MCP Server (3:00 - 3:30)

> ⭐ **CRITICAL: This section demonstrates the MCP Server key concept. Do not skip.**

**Switch to Antigravity IDE terminal. Run:**

```bash
python mcp_server.py
```

**Show the startup output: "RideMate AI MCP Server starting... Exposing 14 tools via MCP stdio transport"**

> "Now the critical part — RideMate runs as an MCP server. One command: `python mcp_server.py`. All fourteen tools are exposed via the Model Context Protocol over standard input/output."

**Open the MCP config file or explain the setup**

> "Any MCP-compatible client — Claude Desktop, Cursor, or Antigravity IDE itself — can connect to it. You add a three-line JSON config pointing to `mcp_server.py`, and the client can call `find_rides`, `reserve_seat`, `read_community_board` — all through natural language, no web server needed."

**Show mcp_server.py in the editor, scroll through some @mcp.tool() decorators**

> "Each tool is a Python function with an `@mcp.tool()` decorator. Typed parameters, docstrings, structured returns. The same fourteen tools powering the web API are available over MCP — same code, two protocols."

> 🔑 **KEY CONCEPT — MCP Server**: Standalone stdio server using the MCP Python SDK. Tools are decorated with `@mcp.tool()` and discoverable by any MCP client.

---

### Part 7 — Security + Deployment (3:30 - 4:05)

> ⭐ **This section demonstrates Security and Deployability key concepts.**

**Switch to editor. Open `api/security.py`. Scroll through the three classes.**

> "Three security layers protect the API."

**Point to APIKeyMiddleware**

> "First, API key authentication. Protects all `/api/v1/` routes with constant-time key comparison — prevents timing attacks. Toggleable: off in dev, on in production."

**Point to RateLimitMiddleware**

> "Second, rate limiting. Sliding-window per IP — default 30 requests per 60 seconds. Sends proper 429 responses with `Retry-After` headers. Respects `X-Forwarded-For` for proxied deployments."

**Point to sanitize_input function**

> "Third, input sanitization. Every user input is trimmed, length-capped, and stripped of control characters before it reaches any agent or database."

> 🔑 **KEY CONCEPT — Security Features**: API key auth + sliding-window rate limiter + input sanitization on all endpoints.

**Open `cloudbuild.yaml` in the editor**

> "And for deployment — one command deploys to Cloud Run: `gcloud builds submit`. Docker build, push to Container Registry, deploy to Cloud Run — fully automated in `cloudbuild.yaml`. Environment-variable-based config, no hardcoded secrets."

> 🔑 **KEY CONCEPT — Deployability**: Docker + Cloud Build + Cloud Run. One-command deploy, serverless, scales to zero.

---

### Part 8 — Architecture Wrap-up (4:05 - 4:40)

**Switch to Tab B (Swagger UI). Scroll through all endpoints.**

> "All fourteen tools, request schemas, and response models documented at `/docs`. Every API interaction uses typed Pydantic models with validation."

**Show the terminal with `python main.py` logs running**

> "RideMate AI demonstrates all six key concepts of the course:"

**Count on fingers as you list them:**

> "One — Multi-agent system with five specialist Gemini agents."
> "Two — MCP server exposing all tools via Model Context Protocol."
> "Three — Antigravity IDE as the development environment."
> "Four — Security: API key auth, rate limiting, input sanitization."
> "Five — Cloud Run deployment with automated build pipeline."
> "Six — Agent skills with fourteen structured, documented tools."

**Show GitHub repo in browser: `https://github.com/FrankieLiuF/RideMate-AI`**

> "Code is at github.com/FrankieLiuF/RideMate-AI. The README includes a Mermaid architecture diagram, full setup instructions, and deployment guide. Thank you for watching."

---

## 📋 Key Concept Checklist for Recording

Use this while recording to make sure nothing is missed:

| Key Concept | Where | Time |
|---|---|---|
| ✅ Agent / Multi-Agent | Part 1 — 5 agents intro | 0:00-0:30 |
| ✅ MCP Server | Part 6 — `python mcp_server.py` | 3:00-3:30 |
| ✅ Antigravity | IDE visible throughout + Part 1 terminal | Throughout |
| ✅ Security | Part 7 — `api/security.py` walkthrough | 3:30-3:50 |
| ✅ Deployability | Part 7 — `cloudbuild.yaml` | 3:50-4:05 |
| ✅ Agent Skills / Tools | Part 3 — 14 tools + Swagger | 1:05-1:45 |

---

## Recording Tips

- **Speak 20% slower than you think you need to**
- **Don't rush between clicks** — let the API response come back
- **Zoom the terminal** so text is readable: Ctrl+Plus
- **Keep mouse still** when you're talking
- **Do a dry run first** without recording
- **Parts 6 & 7 are the most important** — they cover 3 key concepts that can't be shown in the web demo alone. Give them extra time.

## After Recording

1. Upload to YouTube as "Unlisted"
2. Copy the YouTube link
3. Paste into Kaggle Writeup → Submit
