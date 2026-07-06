"""
MCP (Model Context Protocol) Server for RideMate AI.

Exposes the multi-agent carpool system's tools to any MCP-compatible client
(e.g., Claude Desktop, Antigravity IDE, Cursor, etc.) via stdio transport.

Start with: python mcp_server.py
Configure in client's mcp_servers.json:
  { "mcpServers": { "ridemate": { "command": "python", "args": ["mcp_server.py"] } } }
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv(override=True)

from mcp.server import FastMCP
from database.db import init_db
from agent.tools import (
    search_rides,
    create_ride,
    book_ride,
    cancel_booking,
    get_my_rides,
    get_or_create_user,
    get_user_profile,
    update_user_preferences,
    get_recommendations,
    get_active_drivers,
    broadcast_status,
    end_broadcast,
    post_community_message,
    get_community_messages,
)

# Initialize database tables on startup
init_db()

# ── MCP Server ─────────────────────────────────────────────────────────

mcp = FastMCP(
    "RideMate AI",
    instructions="Multi-agent carpool assistant — search, book, and coordinate rides in university towns. Use tools to help users find rides, create listings, manage bookings, and interact with the community board.",
)


# ── Ride Discovery Tools ────────────────────────────────────────────────

@mcp.tool()
def find_rides(from_location: str = "", to_location: str = "", max_results: int = 5) -> dict:
    """Search for available carpool rides by pickup and/or dropoff location.

    Args:
        from_location: Pickup location (partial match supported, e.g. "University")
        to_location: Dropoff location (partial match supported, e.g. "Downtown")
        max_results: Maximum number of results to return (default 5)
    """
    return search_rides(from_location=from_location, to_location=to_location, max_results=max_results)


@mcp.tool()
def find_active_drivers(location: str = "") -> dict:
    """See all drivers currently active and broadcasting their location on the community board.

    Args:
        location: Optional location filter (e.g. "Aber Station")
    """
    return get_active_drivers(location=location)


# ── Ride Management Tools ────────────────────────────────────────────────

@mcp.tool()
def create_new_ride(
    user_id: str,
    from_location: str,
    to_location: str,
    departure_time: str,
    available_seats: int,
    price: float,
    notes: str = "",
) -> dict:
    """Create a new carpool ride listing as a driver.

    Args:
        user_id: Your unique user identifier
        from_location: Pickup location
        to_location: Dropoff location
        departure_time: Departure time in ISO 8601 format (e.g. "2025-07-15T09:00:00")
        available_seats: Number of available seats
        price: Price per seat in USD
        notes: Optional notes about the ride
    """
    return create_ride(
        user_id=user_id,
        from_location=from_location,
        to_location=to_location,
        departure_time=departure_time,
        available_seats=available_seats,
        price=price,
        notes=notes,
    )


@mcp.tool()
def reserve_seat(user_id: str, ride_id: int, seats: int = 1) -> dict:
    """Book one or more seats on a specific ride.

    Args:
        user_id: Your unique user identifier
        ride_id: ID of the ride to book
        seats: Number of seats to reserve (default 1)
    """
    return book_ride(user_id=user_id, ride_id=ride_id, seats=seats)


@mcp.tool()
def cancel_reservation(user_id: str, booking_id: int) -> dict:
    """Cancel an existing booking and free up the seats.

    Args:
        user_id: Your user ID
        booking_id: ID of the booking to cancel
    """
    return cancel_booking(user_id=user_id, booking_id=booking_id)


@mcp.tool()
def get_user_rides(user_id: str, role_filter: str = "all") -> dict:
    """Get all rides associated with a user — as driver, rider, or both.

    Args:
        user_id: Your user ID
        role_filter: "driver", "rider", or "all" (default)
    """
    return get_my_rides(user_id=user_id, role_filter=role_filter)


# ── Profile & Personalization Tools ──────────────────────────────────────

@mcp.tool()
def register_user(user_id: str, name: str = "", role: str = "rider") -> dict:
    """Register a new user or retrieve an existing one.

    Args:
        user_id: Unique user identifier
        name: Display name (defaults to user_id if empty)
        role: "driver", "rider", or "both" (default "rider")
    """
    return get_or_create_user(user_id=user_id, name=name, role=role)


@mcp.tool()
def get_profile(user_id: str) -> dict:
    """Get a user's full profile including stats, preferences, and ride history.

    Args:
        user_id: Your user ID
    """
    return get_user_profile(user_id=user_id)


@mcp.tool()
def save_preferences(user_id: str, preferences: dict) -> dict:
    """Save or update user preferences (frequent routes, preferred times, etc.).

    Args:
        user_id: Your user ID
        preferences: Dictionary of preference key-value pairs
    """
    return update_user_preferences(user_id=user_id, preferences=preferences)


@mcp.tool()
def get_personalized_recommendations(user_id: str) -> dict:
    """Get personalized ride recommendations based on booking history and saved preferences.

    Args:
        user_id: Your user ID
    """
    return get_recommendations(user_id=user_id)


# ── Community Board Tools ────────────────────────────────────────────────

@mcp.tool()
def read_community_board(limit: int = 20) -> dict:
    """Read recent messages from the shared community bulletin board.

    Args:
        limit: Maximum number of messages to return (default 20)
    """
    return get_community_messages(limit=limit)


@mcp.tool()
def post_to_board(user_id: str, content: str, location: str = "") -> dict:
    """Post a message to the shared community board visible to all users.

    Args:
        user_id: Your user ID
        content: Message content to post
        location: Optional location tag
    """
    return post_community_message(user_id=user_id, content=content, location=location)


@mcp.tool()
def broadcast_driver_status(user_id: str, location: str, status_message: str, seats_available: int = 0, destination: str = "") -> dict:
    """Broadcast your real-time location and status as a driver to the community board.

    Args:
        user_id: Your user ID
        location: Your current location (e.g. "Aber Station parking lot")
        status_message: Status message for riders (e.g. "Waiting here for 20 min, 3 seats available")
        seats_available: Number of available seats in your car
        destination: Where you're headed (optional)
    """
    return broadcast_status(
        user_id=user_id, location=location, status_message=status_message,
        seats_available=seats_available, destination=destination,
    )


@mcp.tool()
def end_driver_broadcast(user_id: str) -> dict:
    """End your active driver status broadcast (when you leave or are full).

    Args:
        user_id: Your user ID
    """
    return end_broadcast(user_id=user_id)


# ── Entry Point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("RideMate AI MCP Server starting...", file=sys.stderr)
    print("   Exposing 14 tools via MCP stdio transport", file=sys.stderr)
    print("   Connect from Claude Desktop, Antigravity IDE, or any MCP client", file=sys.stderr)
    mcp.run()
