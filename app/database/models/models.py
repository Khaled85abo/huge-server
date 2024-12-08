from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, Text, Boolean, ForeignKey, DateTime, func, Enum, UniqueConstraint
from datetime import datetime
from app.database.models.base_model import Base



class User(Base):
    __tablename__ = "user"

    org: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)

    # Relationships
    jobs = relationship("Job", back_populates="user")
    sessions = relationship("Session", back_populates="user")

    def __repr__(self):
        return f"<User={self.name}>"

class Session(Base):
    __tablename__ = "sessions"

    session_token: Mapped[str] = mapped_column(String(255), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    last_accessed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ip_address: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    user_agent: Mapped[str] = mapped_column(String(255), nullable=False)

    # Relationship
    user = relationship("User", back_populates="sessions")

class Job(Base):
    __tablename__ = "job"

    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    source_storage: Mapped[str] = mapped_column(String(255), nullable=False)
    dest_storage: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    errors: Mapped[str] = mapped_column(Text, nullable=True)


    # Relationship
    user = relationship("User", back_populates="jobs")
