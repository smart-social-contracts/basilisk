"""
Basilisk OS — Status enums for task/process management.

These enums are used by the task execution system inside the canister.
Only task-related statuses are included here; application-level statuses
(e.g. TradeStatus, DisputeStatus) belong in the application layer (realms).
"""

from enum import Enum


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskExecutionStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
