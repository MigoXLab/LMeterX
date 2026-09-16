"""Dataset persistence and API schemas."""

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from db.mysql import Base

DATASET_TYPES = frozenset({"business", "llm", "a2a", "mcp"})
MAX_DATASET_TAGS = 10
MAX_DATASET_TAG_LENGTH = 50


def normalize_dataset_types(values: List[str]) -> List[str]:
    """Normalize and validate the multi-select dataset type labels."""
    normalized = list(dict.fromkeys(str(value).strip().lower() for value in values))
    if not normalized or any(value not in DATASET_TYPES for value in normalized):
        raise ValueError(
            "dataset_types must contain one or more of: business, llm, a2a, mcp"
        )
    return normalized


def normalize_dataset_tags(values: List[str]) -> List[str]:
    """Normalize free-form dataset tags while preserving their display casing."""
    normalized: List[str] = []
    seen = set()
    for value in values:
        tag = str(value).strip()
        if not tag:
            continue
        if len(tag) > MAX_DATASET_TAG_LENGTH:
            raise ValueError(
                f"dataset tags must not exceed {MAX_DATASET_TAG_LENGTH} characters"
            )
        key = tag.casefold()
        if key not in seen:
            seen.add(key)
            normalized.append(tag)
    if len(normalized) > MAX_DATASET_TAGS:
        raise ValueError(f"datasets support at most {MAX_DATASET_TAGS} tags")
    return normalized


class Dataset(Base):
    """A reusable JSONL dataset."""

    __tablename__ = "datasets"

    id = Column(String(40), primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    file_name = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False)
    file_size = Column(BigInteger, nullable=False, default=0)
    record_count = Column(Integer, nullable=False, default=0)
    dataset_types = Column(String(255), nullable=False)
    tags = Column(Text, nullable=False, default="[]", server_default="[]")
    created_by = Column(String(100), nullable=False, index=True)
    is_public = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class DatasetUpdateRequest(BaseModel):
    """Mutable dataset metadata (the uploaded file is immutable)."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    is_public: Optional[bool] = None
    dataset_types: Optional[List[str]] = None
    tags: Optional[List[str]] = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("Dataset name is required")
        return stripped

    @field_validator("dataset_types")
    @classmethod
    def validate_dataset_types(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        return normalize_dataset_types(value) if value is not None else None

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        return normalize_dataset_tags(value) if value is not None else None
