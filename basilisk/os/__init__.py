"""
Basilisk OS — Operating system services for IC canisters.

Provides POSIX-like abstractions on top of the Basilisk CDK:

  - Task/process management (Task, TaskStep, TaskSchedule, TaskManager)
  - Wallet (ICRC-1 token registry, transfers, balance tracking)
  - Filesystem (in-memory POSIX fs via frozen_stdlib_preamble)
  - Persistent storage (via ic-python-db entity ORM)
  - Logging (via ic-python-logging)

Canister-side code: entities and task_manager run *inside* the canister.
Client-side code: shell, sshd, sftp run on the developer machine.
"""

__all__ = [
    # Status enums
    "TaskStatus",
    "TaskExecutionStatus",
    # Task entities
    "Codex",
    "Call",
    "Task",
    "TaskStep",
    "TaskSchedule",
    "TaskExecution",
    # Wallet entities
    "Token",
    "WalletBalance",
    "WalletTransfer",
    # Wallet
    "Wallet",
    # Task manager
    "TaskManager",
    # Execution
    "run_code",
    "create_task_entity_class",
]

# These imports will only work inside a canister (they depend on ic-python-db).
# When used client-side (e.g. in tests), import individual modules directly.
try:
    from .status import TaskStatus, TaskExecutionStatus
    from .entities import (
        Codex, Call, Task, TaskStep, TaskSchedule, TaskExecution,
        Token, WalletBalance, WalletTransfer,
    )
    from .wallet import Wallet
    from .task_manager import TaskManager
    from .execution import run_code, create_task_entity_class
except ImportError:
    pass
