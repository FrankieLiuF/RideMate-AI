from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime, timezone

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    role = Column(String(20), default="rider")  # "driver", "rider", "both"
    preferences = Column(JSON, default=dict)  # {"avoid_tolls": true, "prefer_morning": true}
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    rides_offered = relationship("Ride", back_populates="driver")
    bookings = relationship("Booking", back_populates="rider")


class Ride(Base):
    __tablename__ = "rides"

    id = Column(Integer, primary_key=True, autoincrement=True)
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    from_location = Column(String(200), nullable=False)
    to_location = Column(String(200), nullable=False)
    departure_time = Column(String(30), nullable=False)  # ISO 8601
    available_seats = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    status = Column(String(20), default="active")  # "active", "full", "cancelled"
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    driver = relationship("User", back_populates="rides_offered")
    bookings = relationship("Booking", back_populates="ride")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ride_id = Column(Integer, ForeignKey("rides.id"), nullable=False)
    rider_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    seats = Column(Integer, default=1)
    status = Column(String(20), default="pending")  # "pending", "confirmed", "cancelled"
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    ride = relationship("Ride", back_populates="bookings")
    rider = relationship("User", back_populates="bookings")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # "user", "assistant", "system"
    content = Column(Text, nullable=False)
    agent_name = Column(String(50), default="orchestrator")
    tool_calls = Column(JSON, default=None)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class DriverStatus(Base):
    """Real-time driver status broadcast (e.g., 'waiting at Aber Station')."""

    __tablename__ = "driver_statuses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), nullable=False, index=True)
    driver_name = Column(String(100), nullable=False)
    location = Column(String(200), nullable=False)
    status_message = Column(Text, nullable=False)  # "Waiting at Aber Station, leaving in 20 min"
    seats_available = Column(Integer, default=0)
    destination = Column(String(200), default="")
    is_active = Column(Integer, default=1)  # 1=active, 0=ended
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class CommunityMessage(Base):
    """Shared community board messages visible to all users."""

    __tablename__ = "community_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), nullable=False)
    author_name = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    location = Column(String(200), default="")  # Optional location tag
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
