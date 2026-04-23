"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from typing import List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from db.mysql import Base


class Collection(Base):
    """
    SQLAlchemy model representing a collection in the 'collections' table.
    """

    __tablename__ = "collections"

    id = Column(String(40), primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    rich_content = Column(Text, nullable=True)
    created_by = Column(String(100), nullable=True)
    is_public = Column(Integer, nullable=False, default=1, server_default="1")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CollectionTask(Base):
    """
    SQLAlchemy model representing the many-to-many relationship between collections and tasks.
    """

    __tablename__ = "collection_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    collection_id = Column(String(40), nullable=False, index=True)
    task_id = Column(String(40), nullable=False, index=True)
    task_type = Column(String(16), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("collection_id", "task_id", name="uk_collection_task"),
    )


# Pydantic models for API
class CollectionCreateRequest(BaseModel):
    """Payload for creating a collection."""

    name: str = Field(..., description="Collection name")
    description: Optional[str] = Field(None, description="Collection description")
    rich_content: Optional[str] = Field(None, description="Rich text content")
    is_public: Optional[bool] = Field(
        True, description="Whether the collection is public"
    )


class CollectionUpdateRequest(BaseModel):
    """Payload for partially updating a collection."""

    name: Optional[str] = Field(None, description="Collection name")
    description: Optional[str] = Field(None, description="Collection description")
    rich_content: Optional[str] = Field(None, description="Rich text content")
    is_public: Optional[bool] = Field(
        None, description="Whether the collection is public"
    )


class CollectionTaskAddRequest(BaseModel):
    """Payload for adding a task into a collection."""

    task_id: str = Field(..., description="Task ID")
    task_type: str = Field(..., description="Task type: http or llm")


class CollectionTaskRemoveRequest(BaseModel):
    """Payload for removing a task from a collection."""

    task_id: str = Field(..., description="Task ID")


class CollectionTaskResponse(BaseModel):
    """Response schema for a collection-task relation row."""

    id: int
    collection_id: str
    task_id: str
    task_type: str
    created_at: str


class CollectionResponse(BaseModel):
    """Response schema for collection detail/list items."""

    id: str
    name: str
    description: Optional[str]
    rich_content: Optional[str]
    created_by: Optional[str]
    is_public: bool
    created_at: str
    updated_at: str
    task_count: int = 0
