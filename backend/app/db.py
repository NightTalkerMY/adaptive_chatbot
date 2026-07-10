import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from . import config

# Declaring a base for ChatSession and Messages
Base = declarative_base()


def _utcnow():
    return datetime.now(timezone.utc)

# Table for ChatSession
class ChatSession(Base):
    __tablename__ = "sessions"

    # Columns for ChatSession
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False, default="New chat")
    category = Column(String, nullable=False, default="general")
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # message attribute, has relationship with session in the Message class
    # when session is deleted, the orphan messages linked to that session also deleted
    messages = relationship(
        "Message", back_populates="session", cascade="all, delete-orphan", order_by="Message.id"
    )


# Table for Messages
class Message(Base):
    __tablename__ = "messages"

    # Column for Messages
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False, index=True)
    role = Column(String, nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    intent = Column(String, nullable=True)  # classified intent for user messages
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # session attribute, has relationship with messages in the ChatSession class
    session = relationship("ChatSession", back_populates="messages")


def _make_engine(url: str):
    if url.startswith("sqlite:///"):
        # Ensure the parent directory for the SQLite file exists.
        path = url.replace("sqlite:///", "", 1)
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url)


engine = _make_engine(config.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# Starts to create all tables
def init_db():
    Base.metadata.create_all(engine)


# 
def get_db():
    db = SessionLocal()
    try:
        yield db   # test this database that may raise exception
    finally:
        db.close() # finally close it for safely
