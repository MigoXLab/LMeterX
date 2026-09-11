"""Unified dispatch queue for regular load-test tasks."""

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    String,
    UniqueConstraint,
    func,
)

from db.mysql import Base


class TaskDispatchQueue(Base):
    """Scheduling projection shared by LLM and HTTP tasks.

    Business configuration remains in the type-specific task tables.  The
    monotonically increasing ``queue_seq`` is the sole ordering key used when
    engines claim regular tasks.
    """

    __tablename__ = "task_dispatch_queue"
    __table_args__ = (
        UniqueConstraint("task_type", "task_id", name="uk_dispatch_task"),
        Index(
            "idx_dispatch_cluster_status_seq",
            "cluster_id",
            "status",
            "queue_seq",
        ),
    )

    queue_seq = Column(BigInteger, primary_key=True, autoincrement=True)
    task_type = Column(String(16), nullable=False)
    task_id = Column(String(40), nullable=False)
    cluster_id = Column(String(64), nullable=False, default="local")
    status = Column(String(16), nullable=False, default="created")
    engine_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    claimed_at = Column(DateTime, nullable=True)
