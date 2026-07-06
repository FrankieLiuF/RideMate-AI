# RideMate AI — Demo Video Script (~3 minutes)

## Before You Record

1. Delete `ridemate.db` (fresh start)
2. Open Antigravity IDE terminal, run: `python main.py`
3. Open browser, pin these two tabs:
   - **Tab A**: `http://localhost:8000` (the demo app)
   - **Tab B**: `http://localhost:8000/docs` (Swagger API docs)
4. Make sure the Antigravity IDE terminal is visible on screen too
5. Start screen recording (Win+G opens Game Bar, or use OBS)

---

## The Script

### Part 1 — Intro (0:00 - 0:25)

**Screen: Show Tab A (demo app) with the purple welcome card visible**

> "Hi, I'm Frankie. This is RideMate AI — a personal ride coordinator built for the AI Agents Vibe Coding capstone. It's a Concierge Agents track submission."

**Switch to Antigravity IDE terminal. Run: `ls agent/`**

> "RideMate uses five specialist Gemini agents: a Coordinator that routes intent, a Discovery agent for finding rides, a Bookings agent for reservations, a Board agent for the community, and a Profile agent for user memory."

**In terminal, run: `wc -l agent/tools.py`**

> "Twelve structured tools handle everything from ride creation to community broadcasting, all backed by a SQLite database with persistent memory."

**Switch to Tab B (Swagger UI)**

> "The full API is documented with Swagger — request schemas, response models, everything typed and self-documenting. Let me show you it working live."

---

### Part 2 — Driver Broadcasts Their Location (0:25 - 0:55)

**Switch to Tab A (demo app). Click the ☀️/🌙 toggle**

> "Here's the interface. Claymorphism design, light and dark mode. And these colored pills at the top light up to show which agents are active."

**Click the "📍 Arrived" quick button**

> "Let's start with a driver. I'll click this quick button — it simulates a driver arriving at a pickup spot and broadcasting their location."

**Wait for response. Point to the agent trail below the message.**

> "Three agents lit up — Coordinator, Board, and Profile. That means the system recognized a driver, broadcast their location, and registered their profile."

**Switch to Antigravity IDE terminal. Point to the log lines.**

> "In the terminal: Profile agent registered the driver, and the Board agent called `broadcast_status` to let everyone know where they are."

**Switch back to Tab A. Click the 📍 Drivers tab on the right.**

> "The driver's status is now live on the Drivers tab — there's Alice, with a LIVE green dot. Any rider nearby can now find her."

---

### Part 3 — Rider Searches and Books (0:55 - 1:40)

**Click back to the chat input. Click the "🔍 Search" quick button**

> "Now from a rider's perspective. I'll search for rides to Downtown."

**Wait for response**

> "The Discovery agent searched the database and found the ride Alice just created. It shows departure time, seats available, and price."

**Type in chat:**

`Book ride #1 for me, 1 seat`

**Wait for response**

> "The Bookings agent confirmed the reservation. One seat deducted. The database now shows 2 seats remaining on Alice's ride."

---

### Part 4 — Community Board (1:40 - 2:10)

**Click the 📋 Board tab on the right**

> "The community board. This is where riders and drivers coordinate — it's like a shared bulletin board."

**Click the "📋 Post" quick button**

> "I'll post a message to the board."

**Point to the newly appeared board card on the right**

> "The message appears instantly for everyone to see. Anyone opening the app will see this on the Board tab."

---

### Part 5 — Personalized Recommendations (2:10 - 2:55)

**Click the ✨ Suggested tab on the right**

> "This is the personalized recommendations feature. It analyzes booking history and suggests rides based on routes I've taken before."

**Point to the welcome card with stats**

> "Two rides taken, one frequent route detected. If a matching ride is available, I get a one-click 'Book Now' button right in the card."

**Point to the recommendation card**

> "Because I've taken University-to-Downtown twice before, it's flagged as a frequent route. This is proactive — the agent learns my patterns."

**Click the ☀️/🌙 toggle**

> "And dark mode, of course. Works across all tabs."

---

### Part 6 — Architecture + Wrap-up (2:55 - 3:15)

**Switch to Tab B (Swagger UI). Scroll through the endpoints.**

> "All twelve tools, request schemas, and response models are fully documented at `/docs`. Every API interaction uses typed Pydantic models."

> "RideMate AI demonstrates all five days of the Vibe Coding course — multi-agent coordination, function calling with proper protobuf responses, persistent memory with SQLAlchemy, evaluation cases covering edge and failure paths, and production-ready Docker deployment."

**Show GitHub repo in browser: `https://github.com/FrankieLiuF/RideMate-AI`**

> "Thank you for watching. Code is at github.com/FrankieLiuF/RideMate-AI."

---

## Recording Tips

- **Speak 20% slower than you think you need to**
- **Don't rush between clicks** — let the API response come back before moving on
- **Zoom the terminal** so text is readable on video: Ctrl+Plus in terminal
- **Keep mouse still** when you're talking
- **Do a dry run first** without recording

## After Recording

1. Upload to YouTube as "Unlisted"
2. Copy the YouTube link
3. Paste into Kaggle Writeup → Submit
