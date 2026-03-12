"""
bos — Basilisk OS entities for IC canisters.

Drop this file into your canister's src/ directory to get task/process management.
Then in main.py:  from bos import Task, TaskSchedule, TaskExecution

Depends on: ic-python-db, ic-python-logging (both pip-installable).
"""

from ic_python_db import (
    Boolean,
    Entity,
    Integer,
    ManyToOne,
    OneToMany,
    OneToOne,
    String,
    TimestampedMixin,
)
from ic_python_logging import get_logger

logger = get_logger("bos")


# ---------------------------------------------------------------------------
# Status enums
# ---------------------------------------------------------------------------

class TaskStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class TaskExecutionStatus:
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# TaskExecution — record of a single task execution attempt
# ---------------------------------------------------------------------------

class TaskExecution(Entity, TimestampedMixin):
    """Record of a single task execution attempt."""

    __alias__ = "name"
    name = String(max_length=256)
    task = ManyToOne("Task", "executions")
    status = String(max_length=50, default=TaskExecutionStatus.IDLE)
    result = String(max_length=5000)

    def _logger_name(self):
        return "task_%s_%s" % (self.task._id, self._id)

    def logger(self):
        return get_logger(self._logger_name())

    def __repr__(self):
        return (
            f"TaskExecution(name={self.name}, status={self.status}, "
            f"result={self.result!r:.60})"
        )


# ---------------------------------------------------------------------------
# TaskStep — single step in a multi-step workflow
# ---------------------------------------------------------------------------

class TaskStep(Entity, TimestampedMixin):
    """
    A single step in a task execution.

    IC canisters cannot mix sync and async in the same call.
    TaskSteps solve this by breaking work into sequential steps:
      Step 1 (sync): local computation
      Step 2 (async): inter-canister call
      Step 3 (sync): process results
    """

    call = OneToOne("Call", "task_step")
    status = String(max_length=32, default="pending")
    run_next_after = Integer(default=0)
    timer_id = Integer()
    task = ManyToOne("Task", "steps")


# ---------------------------------------------------------------------------
# TaskSchedule — when and how often to run
# ---------------------------------------------------------------------------

class TaskSchedule(Entity, TimestampedMixin):
    """Schedule for running a Task at specified intervals."""

    __alias__ = "name"
    name = String(max_length=256)
    disabled = Boolean()
    task = ManyToOne("Task", "schedules")
    run_at = Integer()
    repeat_every = Integer()
    last_run_at = Integer()

    def serialize(self):
        return {
            "_id": str(self._id),
            "_type": "TaskSchedule",
            "name": self.name,
            "task_id": str(self.task._id) if self.task else None,
            "disabled": self.disabled,
            "run_at": self.run_at,
            "repeat_every": self.repeat_every,
            "last_run_at": self.last_run_at,
        }

    def __str__(self):
        return (
            f"TaskSchedule(name={self.name}, "
            f"repeat_every={self.repeat_every})"
        )


# ---------------------------------------------------------------------------
# Task — primary work unit
# ---------------------------------------------------------------------------

class Task(Entity, TimestampedMixin):
    """
    Task entity — a unit of work that can be scheduled and executed.

    Part of the Basilisk OS process management layer.
    """

    __alias__ = "name"
    name = String(max_length=256)
    metadata = String(max_length=256)
    status = String(max_length=32, default=TaskStatus.PENDING)
    step_to_execute = Integer(default=0)
    # Relationships
    steps = OneToMany("TaskStep", "task")
    schedules = OneToMany("TaskSchedule", "task")
    executions = OneToMany("TaskExecution", "task")

    def new_task_execution(self):
        execution_name = "taskexec_%s_%s" % (self._id, self._id)
        return TaskExecution(
            name=execution_name,
            task=self,
            status=TaskExecutionStatus.IDLE,
            result="",
        )
