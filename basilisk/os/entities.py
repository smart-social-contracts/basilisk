"""
Basilisk OS — Core entities for task/process management.

These entity definitions run inside the canister and depend on ic-python-db.
They are the canonical Basilisk OS definitions; realms imports from here.

Entities:
    Task          — A unit of work that can be scheduled and executed.
    TaskStep      — A single step in a multi-step task workflow.
    TaskSchedule  — Schedule for running a Task at specified intervals.
    TaskExecution — Record of a single task execution attempt.
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

from .status import TaskExecutionStatus

logger = get_logger("basilisk.os.entities")


# ---------------------------------------------------------------------------
# TaskExecution — execution record
# ---------------------------------------------------------------------------

class TaskExecution(Entity, TimestampedMixin):
    """Record of a single task execution attempt."""

    __alias__ = "name"
    name = String(max_length=256)
    task = ManyToOne("Task", "executions")
    status = String(max_length=50)  # "completed", "failed", "running"
    result = String(max_length=5000)

    def _logger_name(self):
        return "task_%s_%s" % (self.task._id, self._id)

    def logger(self):
        return get_logger(self._logger_name())

    def __repr__(self) -> str:
        return (
            f"TaskExecution(\n"
            f"  name={self.name}\n"
            f"  task={self.task}\n"
            f"  status={self.status}\n"
            f"  logger_name={self._logger_name()}\n"
            f"  result={self.result}\n"
            f")"
        )


# ---------------------------------------------------------------------------
# TaskStep — single step in a multi-step workflow
# ---------------------------------------------------------------------------

class TaskStep(Entity, TimestampedMixin):
    """
    Represents a single step in a task execution.

    ICP canisters cannot mix sync and async in the same function.
    TaskSteps solve this by allowing:
      - Step 1 (Sync): Local computation
      - Step 2 (Async): Inter-canister call with yield
      - Step 3 (Sync): Process results
    """

    call = OneToOne("Call", "task_step")
    status = String(max_length=32, default="pending")
    run_next_after = Integer(default=0)  # seconds to wait before next step
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
        """Convert TaskSchedule to dictionary for JSON serialization."""
        return {
            "_id": str(self._id),
            "_type": "TaskSchedule",
            "name": self.name,
            "task_id": (
                str(self.task._id) if hasattr(self, "task") and self.task else None
            ),
            "disabled": self.disabled,
            "run_at": self.run_at,
            "repeat_every": self.repeat_every,
            "last_run_at": self.last_run_at,
        }

    def __json__(self):
        """Make TaskSchedule JSON serializable."""
        return self.serialize()

    def __str__(self):
        return (
            f"TaskSchedule(name={self.name}, "
            f"run_at={self.run_at}, "
            f"repeat_every={self.repeat_every})"
        )


# ---------------------------------------------------------------------------
# Task — the primary work unit
# ---------------------------------------------------------------------------

class Task(Entity, TimestampedMixin):
    """
    Task entity — part of the GGG (Generalized Global Governance) standard.

    Represents a unit of work that can be scheduled and executed.
    """

    __alias__ = "name"
    name = String(max_length=256)
    metadata = String(max_length=256)
    status = String(max_length=32, default="pending")
    step_to_execute = Integer(default=0)
    # Relationships
    steps = OneToMany("TaskStep", "task")
    schedules = OneToMany("TaskSchedule", "task")
    executions = OneToMany("TaskExecution", "task")

    def new_task_execution(self) -> TaskExecution:
        execution_name = "taskexec_%s_%s" % (self._id, self._id)
        execution = TaskExecution(
            name=execution_name,
            task=self,
            status=TaskExecutionStatus.IDLE,
            result="",
        )
        return execution
