"""
SQLAlchemy ORM models — the persistent data layer for RideMate AI.

SCHEMA DESIGN
=============
6 normalized tables with foreign-key relationships:

  users ──1:N── rides        (one driver offers many rides)
  users ──1:N── bookings     (one rider makes many bookings)
  rides ──1:N── bookings     (one ride has many bookings)
  users ──1:N── driver_statuses   (one driver has many status broadcasts)
  users ──1:N── community_messages (one user posts many messages)
  conversations              (standalone — keyed by user_id string)

Why SQLite for development?
  - Zero configuration: no database server needed, single file on disk
  - Survives restarts: data persists across server reloads
  - Schema-identical to PostgreSQL: migration is just changing DATABASE_URL

Why JSON columns for preferences?
  - User preferences are unstructured by nature (arbitrary key-value pairs)
  - SQLite doesn't support native JSON but SQLAlchemy serializes transparently
  - Avoids an EAV (Entity-Attribute-Value) pattern that would need a separate table

Why store departure_time as String, not DateTime?
  - Gemini returns ISO 8601 strings (e.g., "2025-07-15T09:00:00")
  - Storing as string avoids timezone conversion bugs across client/server
  - Can be queried lexicographically for same-format ISO strings
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime, timezone

Base = declarative_base()


class User(Base):
    """
    Core user entity — can be a driver, rider, or both.

    Design choice: 'role' is a single string field ("driver"/"rider"/"both")
    rather than a separate roles table. For a carpool app with exactly three
    roles, a join table is over-engineering. The enum is self-documenting.

    preferences uses JSON type for flexibility — users can save any key-value
    pairs (frequent routes, avoid tolls, preferred times) without schema changes.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), unique=True, nullable=False, index=True)  # External ID from auth system
    name = Column(String(100), nullable=False)
    role = Column(String(20), default="rider")  # "driver" | "rider" | "both"
    preferences = Column(JSON, default=dict)     # Arbitrary key-value store
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Bidirectional relationships — query from either side.
    # e.g., user.rides_offered → all rides this driver created
    #       ride.driver → the User who created it
    rides_offered = relationship("Ride", back_populates="driver")
    bookings = relationship("Booking", back_populates="rider")


class Ride(Base):
    """
    A carpool ride listing created by a driver.

    Lifecycle: active → full (0 seats) | cancelled
    The status field drives the state machine — tools check it before
    allowing bookings (reject if not "active") and auto-set to "full"
    when available_seats reaches 0.
    """

    __tablename__ = "rides"

    id = Column(Integer, primary_key=True, autoincrement=True)
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    from_location = Column(String(200), nullable=False)
    to_location = Column(String(200), nullable=False)
    departure_time = Column(String(30), nullable=False)  # ISO 8601 string from Gemini
    available_seats = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)                # Per-seat price in USD
    status = Column(String(20), default="active")        # "active" | "full" | "cancelled"
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    driver = relationship("User", back_populates="rides_offered")
    bookings = relationship("Booking", back_populates="ride")


class Booking(Base):
    """
    A seat reservation linking a rider to a ride.

    When a booking is confirmed:
      1. ride.available_seats -= booking.seats
      2. If seats reach 0, ride.status → "full"
    When cancelled: the reverse — seats are freed, status may revert to "active".
    """

    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ride_id = Column(Integer, ForeignKey("rides.id"), nullable=False)
    rider_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    seats = Column(Integer, default=1)                   # How many seats reserved
    status = Column(String(20), default="pending")       # "pending" | "confirmed" | "cancelled"
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    ride = relationship("Ride", back_populates="bookings")
    rider = relationship("User", back_populates="bookings")


class Conversation(Base):
    """
    Persistent chat history — one row per message exchange.

    Stores the full conversation log with agent attribution, enabling:
      - Audit trail: who said what, which agent responded
      - Context restoration: reload history after server restart
      - Analytics: which tools are most frequently called, by whom

    Separate from Gemini's in-memory chat session — this is durable storage.
    """

    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    role = Column(String(20), nullable=False)            # "user" | "assistant" | "system"
    content = Column(Text, nullable=False)
    agent_name = Column(String(50), default="orchestrator")
    tool_calls = Column(JSON, default=None)              # Which tools were called in this turn
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class DriverStatus(Base):
    """
    Real-time driver location broadcast.

    This is the heart of the community board feature. Drivers call
    broadcast_status() to announce "I'm at [location], [N] seats to [destination]".
    Riders call get_active_drivers() to see who's nearby RIGHT NOW.

    Design choice: is_active flag (not deletion) for ending broadcasts.
    This preserves history — we can show "Alice was at Aber Station 10 min ago"
    even after she leaves, which builds trust in the community.

    user_id is a String FK to users.user_id (not users.id) because the
    tool layer identifies users by their external user_id string.
    """

    __tablename__ = "driver_statuses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), nullable=False, index=True)
    driver_name = Column(String(100), nullable=False)     # Denormalized for fast display
    location = Column(String(200), nullable=False)
    status_message = Column(Text, nullable=False)         # Free-text from driver
    seats_available = Column(Integer, default=0)
    destination = Column(String(200), default="")
    is_active = Column(Integer, default=1)                # 1=currently broadcasting, 0=ended
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class CommunityMessage(Base):
    """
    Shared bulletin board — visible to ALL users.

    Unlike DriverStatus (which is driver-specific and ephemeral),
    CommunityMessages are persistent public posts. Think of it as a
    cork board at the student union where anyone can leave a note.

    No "is_active" flag here — messages stay visible permanently.
    The board shows the most recent 20 by default.
    """

    __tablename__ = "community_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), nullable=False)
    author_name = Column(String(100), nullable=False)     # Denormalized — survives name changes
    content = Column(Text, nullable=False)
    location = Column(String(200), default="")            # Optional location tag for filtering
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
