"""
Database Models — Repository Metadata
======================================
Adapted from Mohit's models.py. Uses the shared SQLAlchemy Base
so all models live in the same database.
"""

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import String, Integer, ForeignKey, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("tenant_id", "full_name", name="uq_repository_tenant_full_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tenants.id"), index=True, nullable=True
    )
    owner: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    full_name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(255), default="")
    language: Mapped[Optional[str]] = mapped_column(String(50))
    stars: Mapped[int] = mapped_column(Integer, default=0)
    forks: Mapped[int] = mapped_column(Integer, default=0)
    open_issues: Mapped[int] = mapped_column(Integer, default=0)

    # Extended fields
    readme: Mapped[Optional[str]] = mapped_column(Text)
    topics: Mapped[Optional[str]] = mapped_column(Text)
    default_branch: Mapped[Optional[str]] = mapped_column(String(100), default="main")
    license_name: Mapped[Optional[str]] = mapped_column(String(100))
    is_archived: Mapped[bool] = mapped_column(default=False)

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    commits: Mapped[List["Commit"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    contributors: Mapped[List["Contributor"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    file_trees: Mapped[List["FileTree"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )


class Commit(Base):
    __tablename__ = "commits"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tenants.id"), index=True, nullable=True
    )
    repo_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"))
    commit_hash: Mapped[str] = mapped_column(String(40), index=True)
    author_name: Mapped[Optional[str]] = mapped_column(String(100))
    message: Mapped[Optional[str]] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime)

    repository: Mapped["Repository"] = relationship(back_populates="commits")


class Contributor(Base):
    __tablename__ = "contributors"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tenants.id"), index=True, nullable=True
    )
    repo_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"))
    username: Mapped[str] = mapped_column(String(100), index=True)
    profile_url: Mapped[Optional[str]] = mapped_column(String(255))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(255))
    total_commits: Mapped[int] = mapped_column(Integer, default=0)

    repository: Mapped["Repository"] = relationship(back_populates="contributors")


class FileTree(Base):
    __tablename__ = "file_trees"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tenants.id"), index=True, nullable=True
    )
    repo_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"))
    file_path: Mapped[str] = mapped_column(Text)
    file_type: Mapped[str] = mapped_column(String(50))
    size: Mapped[Optional[int]] = mapped_column(Integer)

    repository: Mapped["Repository"] = relationship(back_populates="file_trees")
