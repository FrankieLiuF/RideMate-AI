"""DB-backed tools for the RideMate multi-agent system."""
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from database.db import SessionLocal
from database.models import User, Ride, Booking, DriverStatus, CommunityMessage


# ── User / Profile Tools ────────────────────────────────────────────

def get_or_create_user(user_id: str, name: Optional[str] = None, role: str = "rider") -> Dict[str, Any]:
    """Get an existing user or create a new one.

    If the user already exists but a more-permissive role is requested
    (e.g., upgrading from 'rider' to 'both' or 'driver'), the role is updated.
    This allows Gemini to upgrade a user's role during a conversation.
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            user = User(user_id=user_id, name=name or user_id, role=role)
            db.add(user)
        else:
            # Update name if a real name is provided (not just user_id)
            if name and name != user_id:
                user.name = name
            # Upgrade role if a more-permissive one is requested
            # Hierarchy: rider < driver/both → allow upgrade, never downgrade
            if role in ("driver", "both") and user.role == "rider":
                user.role = role
        db.commit()
        db.refresh(user)
        return {
            "status": "success",
            "user": {"id": user.id, "user_id": user.user_id, "name": user.name, "role": user.role},
        }
    finally:
        db.close()


def update_user_preferences(user_id: str, preferences: Dict[str, Any]) -> Dict[str, Any]:
    """Update user preferences (e.g., preferred times, avoid tolls)."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            return {"status": "error", "message": "User not found"}
        current = dict(user.preferences or {})
        current.update(preferences)
        user.preferences = current
        db.commit()
        return {"status": "success", "preferences": current}
    finally:
        db.close()


def get_user_profile(user_id: str) -> Dict[str, Any]:
    """Get a user's profile, stats, and preferences."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            return {"status": "error", "message": "User not found"}
        rides_offered = db.query(Ride).filter(Ride.driver_id == user.id).count()
        bookings = db.query(Booking).filter(Booking.rider_id == user.id).count()
        return {
            "status": "success",
            "user": {
                "user_id": user.user_id,
                "name": user.name,
                "role": user.role,
                "preferences": user.preferences,
                "rides_offered": rides_offered,
                "total_bookings": bookings,
            },
        }
    finally:
        db.close()


# ── Ride Management Tools ───────────────────────────────────────────

def create_ride(
    user_id: str,
    from_location: str,
    to_location: str,
    departure_time: str,
    available_seats: int,
    price: float,
    notes: str = "",
) -> Dict[str, Any]:
    """Create a new ride listing."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            return {"status": "error", "message": "User not found. Please register first."}
        if user.role not in ("driver", "both"):
            return {"status": "error", "message": "Only drivers can create rides. Set your role to 'driver' or 'both'."}

        ride = Ride(
            driver_id=user.id,
            from_location=from_location,
            to_location=to_location,
            departure_time=departure_time,
            available_seats=available_seats,
            price=price,
            notes=notes,
        )
        db.add(ride)
        db.commit()
        db.refresh(ride)
        return {
            "status": "success",
            "message": f"Ride created! ID: {ride.id}",
            "ride": {
                "id": ride.id,
                "driver": user.name,
                "from": ride.from_location,
                "to": ride.to_location,
                "departure": ride.departure_time,
                "available_seats": ride.available_seats,
                "price": ride.price,
            },
        }
    finally:
        db.close()


def search_rides(
    from_location: str = "",
    to_location: str = "",
    max_results: int = 5,
) -> Dict[str, Any]:
    """Search for available rides matching location criteria."""
    db = SessionLocal()
    try:
        query = db.query(Ride).filter(Ride.status == "active")
        if from_location:
            query = query.filter(Ride.from_location.ilike(f"%{from_location}%"))
        if to_location:
            query = query.filter(Ride.to_location.ilike(f"%{to_location}%"))
        rides = query.limit(max_results).all()
        return {
            "status": "success",
            "total_found": len(rides),
            "results": [
                {
                    "id": r.id,
                    "driver": r.driver.name,
                    "from": r.from_location,
                    "to": r.to_location,
                    "departure": r.departure_time,
                    "available_seats": r.available_seats,
                    "price": r.price,
                }
                for r in rides
            ],
        }
    finally:
        db.close()


def book_ride(user_id: str, ride_id: int, seats: int = 1) -> Dict[str, Any]:
    """Book seats on a ride."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            return {"status": "error", "message": "User not found"}

        ride = db.query(Ride).filter(Ride.id == ride_id).first()
        if not ride:
            return {"status": "error", "message": "Ride not found"}
        if ride.status != "active":
            return {"status": "error", "message": f"Ride is {ride.status}"}
        if ride.available_seats < seats:
            return {"status": "error", "message": f"Only {ride.available_seats} seats available"}

        booking = Booking(ride_id=ride.id, rider_id=user.id, seats=seats, status="confirmed")
        ride.available_seats -= seats
        if ride.available_seats == 0:
            ride.status = "full"
        db.add(booking)

        # Sync the driver's active broadcast so the Drivers tab reflects the new seat count
        driver_user_id = ride.driver.user_id
        active_broadcast = db.query(DriverStatus).filter(
            DriverStatus.user_id == driver_user_id,
            DriverStatus.is_active == 1,
        ).first()
        if active_broadcast:
            active_broadcast.seats_available = ride.available_seats

        db.commit()
        db.refresh(booking)
        return {
            "status": "success",
            "message": f"Booking confirmed! Ride from {ride.from_location} to {ride.to_location} on {ride.departure_time}.",
            "booking": {"id": booking.id, "ride_id": ride.id, "seats": seats, "status": "confirmed"},
        }
    finally:
        db.close()


def cancel_booking(user_id: str, booking_id: int) -> Dict[str, Any]:
    """Cancel a booking and free up seats."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            return {"status": "error", "message": "User not found"}

        booking = db.query(Booking).filter(Booking.id == booking_id, Booking.rider_id == user.id).first()
        if not booking:
            return {"status": "error", "message": "Booking not found"}
        if booking.status == "cancelled":
            return {"status": "error", "message": "Booking is already cancelled"}

        booking.status = "cancelled"
        ride = booking.ride
        ride.available_seats += booking.seats
        if ride.status == "full":
            ride.status = "active"

        # Sync driver's active broadcast seat count
        driver_user_id = ride.driver.user_id
        active_broadcast = db.query(DriverStatus).filter(
            DriverStatus.user_id == driver_user_id,
            DriverStatus.is_active == 1,
        ).first()
        if active_broadcast:
            active_broadcast.seats_available = ride.available_seats

        db.commit()
        return {"status": "success", "message": f"Booking #{booking.id} cancelled. Seats freed up."}
    finally:
        db.close()


def get_my_rides(user_id: str, role_filter: str = "all") -> Dict[str, Any]:
    """Get rides associated with a user — as driver or rider."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            return {"status": "error", "message": "User not found"}

        result = {}
        if role_filter in ("all", "driver"):
            result["as_driver"] = [
                {
                    "id": r.id, "from": r.from_location, "to": r.to_location,
                    "departure": r.departure_time, "seats": r.available_seats,
                    "price": r.price, "status": r.status,
                }
                for r in db.query(Ride).filter(Ride.driver_id == user.id).all()
            ]
        if role_filter in ("all", "rider"):
            bookings = db.query(Booking).filter(Booking.rider_id == user.id).all()
            result["as_rider"] = [
                {
                    "booking_id": b.id, "ride_id": b.ride.id,
                    "from": b.ride.from_location, "to": b.ride.to_location,
                    "departure": b.ride.departure_time, "status": b.status,
                }
                for b in bookings
            ]
        return {"status": "success", **result}
    finally:
        db.close()


# ── Concierge / Recommendation Tools ──────────────────────────────────

def get_recommendations(user_id: str) -> Dict[str, Any]:
    """Proactively recommend rides based on user history, preferences, and saved routes."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            return {"status": "error", "message": "User not found"}

        # 1. Analyze past bookings for frequent routes
        past_bookings = db.query(Booking).filter(Booking.rider_id == user.id).all()
        route_counts: Dict[str, int] = {}
        for b in past_bookings:
            key = f"{b.ride.from_location}|{b.ride.to_location}"
            route_counts[key] = route_counts.get(key, 0) + 1

        # 2. Check saved preferences
        prefs = user.preferences or {}
        saved_routes = prefs.get("saved_routes", [])

        # 3. Find matching active rides
        recommendations = []
        seen_ride_ids = set()

        # From frequent routes (3+ times)
        frequent_routes = [(k, v) for k, v in route_counts.items() if v >= 2]
        for route_key, count in sorted(frequent_routes, key=lambda x: -x[1]):
            parts = route_key.split("|")
            if len(parts) == 2:
                matches = db.query(Ride).filter(
                    Ride.status == "active",
                    Ride.from_location.ilike(f"%{parts[0]}%"),
                    Ride.to_location.ilike(f"%{parts[1]}%"),
                ).limit(3).all()
                for ride in matches:
                    if ride.id not in seen_ride_ids:
                        seen_ride_ids.add(ride.id)
                        recommendations.append({
                            "ride_id": ride.id,
                            "driver": ride.driver.name,
                            "from": ride.from_location,
                            "to": ride.to_location,
                            "departure": ride.departure_time,
                            "seats": ride.available_seats,
                            "price": ride.price,
                            "reason": f"You've taken this route {count} times before",
                        })

        # From saved routes
        for sr in saved_routes:
            matches = db.query(Ride).filter(
                Ride.status == "active",
                Ride.from_location.ilike(f"%{sr.get('from', '')}%"),
                Ride.to_location.ilike(f"%{sr.get('to', '')}%"),
            ).limit(2).all()
            for ride in matches:
                if ride.id not in seen_ride_ids:
                    seen_ride_ids.add(ride.id)
                    recommendations.append({
                        "ride_id": ride.id,
                        "driver": ride.driver.name,
                        "from": ride.from_location,
                        "to": ride.to_location,
                        "departure": ride.departure_time,
                        "seats": ride.available_seats,
                        "price": ride.price,
                        "reason": "Matches your saved route",
                    })

        # 4. Stats
        total_bookings = len(past_bookings)
        saved_prefs = list(prefs.keys()) if prefs else []

        return {
            "status": "success",
            "recommendations": recommendations[:8],
            "stats": {
                "total_bookings": total_bookings,
                "frequent_routes": len(frequent_routes),
                "saved_preferences": saved_prefs,
            },
        }
    finally:
        db.close()


# ── Community Board & Driver Status Tools ─────────────────────────────

def broadcast_status(
    user_id: str,
    location: str,
    status_message: str,
    seats_available: int = 0,
    destination: str = "",
) -> Dict[str, Any]:
    """Broadcast a driver's real-time status to the community board."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            return {"status": "error", "message": "User not found"}

        # Deactivate previous statuses for this driver
        db.query(DriverStatus).filter(
            DriverStatus.user_id == user_id, DriverStatus.is_active == 1
        ).update({"is_active": 0})

        status = DriverStatus(
            user_id=user_id,
            driver_name=user.name,
            location=location,
            status_message=status_message,
            seats_available=seats_available,
            destination=destination,
        )
        db.add(status)
        db.commit()
        db.refresh(status)
        return {
            "status": "success",
            "message": f"Status broadcasted: {user.name} is at {location} — {status_message}",
            "broadcast": {
                "id": status.id,
                "driver": user.name,
                "location": location,
                "message": status_message,
                "seats": seats_available,
                "destination": destination,
            },
        }
    finally:
        db.close()


def get_active_drivers(location: str = "") -> Dict[str, Any]:
    """Get a list of currently active drivers on the community board."""
    db = SessionLocal()
    try:
        query = db.query(DriverStatus).filter(DriverStatus.is_active == 1)
        if location:
            query = query.filter(DriverStatus.location.ilike(f"%{location}%"))
        drivers = query.order_by(DriverStatus.created_at.desc()).limit(20).all()
        return {
            "status": "success",
            "total": len(drivers),
            "drivers": [
                {
                    "id": d.id,
                    "name": d.driver_name,
                    "location": d.location,
                    "message": d.status_message,
                    "seats": d.seats_available,
                    "destination": d.destination,
                    "since": d.created_at.isoformat() if d.created_at else "",
                }
                for d in drivers
            ],
        }
    finally:
        db.close()


def end_broadcast(user_id: str) -> Dict[str, Any]:
    """End a driver's active status broadcast."""
    db = SessionLocal()
    try:
        count = db.query(DriverStatus).filter(
            DriverStatus.user_id == user_id, DriverStatus.is_active == 1
        ).update({"is_active": 0})
        db.commit()
        return {"status": "success", "message": f"Ended {count} active broadcast(s)"}
    finally:
        db.close()


def post_community_message(
    user_id: str,
    content: str,
    location: str = "",
) -> Dict[str, Any]:
    """Post a message to the shared community board visible to all users."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            return {"status": "error", "message": "User not found"}

        msg = CommunityMessage(
            user_id=user_id,
            author_name=user.name,
            content=content,
            location=location,
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return {
            "status": "success",
            "message": "Message posted to community board!",
            "post": {"id": msg.id, "author": user.name, "content": content, "location": location},
        }
    finally:
        db.close()


def get_community_messages(limit: int = 20) -> Dict[str, Any]:
    """Get recent messages from the community bulletin board."""
    db = SessionLocal()
    try:
        messages = (
            db.query(CommunityMessage)
            .order_by(CommunityMessage.created_at.desc())
            .limit(limit)
            .all()
        )
        return {
            "status": "success",
            "total": len(messages),
            "messages": [
                {
                    "id": m.id,
                    "author": m.author_name,
                    "content": m.content,
                    "location": m.location,
                    "time": m.created_at.isoformat() if m.created_at else "",
                }
                for m in reversed(messages)
            ],
        }
    finally:
        db.close()


# ── Tool Registry ────────────────────────────────────────────────────

TOOLS_REGISTRY: Dict[str, Dict[str, Any]] = {
    # Profile tools
    "get_or_create_user": {
        "function": get_or_create_user,
        "description": "Get an existing user by user_id or create a new one",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "user_id": {"type": "STRING", "description": "Unique user identifier"},
                "name": {"type": "STRING", "description": "User's display name"},
                "role": {"type": "STRING", "description": "User role: 'driver', 'rider', or 'both'"},
            },
            "required": ["user_id"],
        },
    },
    "update_user_preferences": {
        "function": update_user_preferences,
        "description": "Save or update user preferences (preferred times, routes, etc.)",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "user_id": {"type": "STRING", "description": "Unique user identifier"},
                "preferences": {"type": "OBJECT", "description": "Key-value preferences dict"},
            },
            "required": ["user_id", "preferences"],
        },
    },
    "get_user_profile": {
        "function": get_user_profile,
        "description": "Get a user's full profile including stats and preferences",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "user_id": {"type": "STRING", "description": "Unique user identifier"},
            },
            "required": ["user_id"],
        },
    },
    # Ride tools
    "create_ride": {
        "function": create_ride,
        "description": "Create a new carpool ride listing as a driver",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "user_id": {"type": "STRING", "description": "Driver's user ID"},
                "from_location": {"type": "STRING", "description": "Pickup location"},
                "to_location": {"type": "STRING", "description": "Dropoff location"},
                "departure_time": {"type": "STRING", "description": "Departure time (ISO 8601 format)"},
                "available_seats": {"type": "INTEGER", "description": "Number of available seats"},
                "price": {"type": "NUMBER", "description": "Price per seat in USD"},
                "notes": {"type": "STRING", "description": "Optional notes about the ride"},
            },
            "required": ["user_id", "from_location", "to_location", "departure_time", "available_seats", "price"],
        },
    },
    "search_rides": {
        "function": search_rides,
        "description": "Search for available rides by pickup and/or dropoff location",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "from_location": {"type": "STRING", "description": "Pickup location (partial match supported)"},
                "to_location": {"type": "STRING", "description": "Dropoff location (partial match supported)"},
                "max_results": {"type": "INTEGER", "description": "Maximum results to return"},
            },
            "required": [],
        },
    },
    "book_ride": {
        "function": book_ride,
        "description": "Book seats on a specific ride",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "user_id": {"type": "STRING", "description": "Rider's user ID"},
                "ride_id": {"type": "INTEGER", "description": "ID of the ride to book"},
                "seats": {"type": "INTEGER", "description": "Number of seats to book"},
            },
            "required": ["user_id", "ride_id"],
        },
    },
    "cancel_booking": {
        "function": cancel_booking,
        "description": "Cancel a booking and free up the seats",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "user_id": {"type": "STRING", "description": "User ID who made the booking"},
                "booking_id": {"type": "INTEGER", "description": "ID of the booking to cancel"},
            },
            "required": ["user_id", "booking_id"],
        },
    },
    "get_my_rides": {
        "function": get_my_rides,
        "description": "Get all rides a user is involved in — as driver or rider",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "user_id": {"type": "STRING", "description": "User ID"},
                "role_filter": {"type": "STRING", "description": "'driver', 'rider', or 'all'"},
            },
            "required": ["user_id"],
        },
    },
    # Concierge tools
    "get_recommendations": {
        "function": get_recommendations,
        "description": "Proactively recommend rides for a user based on their booking history, frequent routes, and saved preferences. Call this when greeting a returning user or when they ask 'what's available for me?'",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "user_id": {"type": "STRING", "description": "User ID to get recommendations for"},
            },
            "required": ["user_id"],
        },
    },
    # Community board tools
    "broadcast_status": {
        "function": broadcast_status,
        "description": "Broadcast your real-time status to the community — use when you arrive at a pickup spot and want riders to know you are waiting",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "user_id": {"type": "STRING", "description": "Your user ID"},
                "location": {"type": "STRING", "description": "Your current location (e.g., 'Aber Station parking lot')"},
                "status_message": {"type": "STRING", "description": "What you want to tell others (e.g., 'Waiting here for the next 20 minutes, 3 seats available')"},
                "seats_available": {"type": "INTEGER", "description": "Number of seats you have"},
                "destination": {"type": "STRING", "description": "Where you are headed (optional)"},
            },
            "required": ["user_id", "location", "status_message"],
        },
    },
    "get_active_drivers": {
        "function": get_active_drivers,
        "description": "See all drivers currently active and waiting — use to find who is nearby and available right now",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "location": {"type": "STRING", "description": "Filter by location (optional, e.g., 'Aber Station')"},
            },
            "required": [],
        },
    },
    "end_broadcast": {
        "function": end_broadcast,
        "description": "End your active status broadcast when you leave or are full",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "user_id": {"type": "STRING", "description": "Your user ID"},
            },
            "required": ["user_id"],
        },
    },
    "post_community_message": {
        "function": post_community_message,
        "description": "Post a message to the shared community bulletin board — all users can see it",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "user_id": {"type": "STRING", "description": "Your user ID"},
                "content": {"type": "STRING", "description": "Message content"},
                "location": {"type": "STRING", "description": "Optional location tag"},
            },
            "required": ["user_id", "content"],
        },
    },
    "get_community_messages": {
        "function": get_community_messages,
        "description": "Read recent messages from the shared community bulletin board",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "limit": {"type": "INTEGER", "description": "Max messages to return"},
            },
            "required": [],
        },
    },
}


def get_tool_definitions():
    """Return tool definitions in Gemini-compatible format."""
    function_declarations = []
    for name, tool in TOOLS_REGISTRY.items():
        function_declarations.append({
            "name": name,
            "description": tool["description"],
            "parameters": tool["parameters"],
        })
    return [{"function_declarations": function_declarations}]


def execute_tool(tool_name: str, tool_args: Dict) -> Dict:
    """Execute a tool by name and return the result."""
    if tool_name not in TOOLS_REGISTRY:
        return {"status": "error", "message": f"Unknown tool: {tool_name}"}
    try:
        return TOOLS_REGISTRY[tool_name]["function"](**tool_args)
    except Exception as e:
        return {"status": "error", "message": str(e)}
