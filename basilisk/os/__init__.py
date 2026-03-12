"""
Basilisk OS — Operating system services for IC canisters.

Provides POSIX-like abstractions on top of the Basilisk CDK:

  - Task/process management (Task, TaskStep, TaskSchedule, TaskManager)
  - Filesystem (in-memory POSIX fs via frozen_stdlib_preamble)
  - Persistent storage (via ic-python-db entity ORM)
  - Logging (via ic-python-logging)

Canister-side code: entities and task_manager run *inside* the canister.
Client-side code: bosh, bosh_sshd, bosh_sftp run on the developer machine.
"""

__all__ = [
    # Status enums
    "TaskStatus",
    "TaskExecutionStatus",
    # Entities
    "Task",
    "TaskStep",
    "TaskSchedule",
    "TaskExecution",
    # Task manager
    "TaskManager",
]

# These imports will only work inside a canister (they depend on ic-python-db).
# When used client-side (e.g. in tests), import individual modules directly.
try:
    from .status import TaskStatus, TaskExecutionStatus
    from .entities import Task, TaskStep, TaskSchedule, TaskExecution
    from .task_manager import TaskManager
except ImportError:
    pass
