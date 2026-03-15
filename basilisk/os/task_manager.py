"""
Basilisk OS — Task Scheduling Framework

Timer-based task scheduling for the Internet Computer supporting one-time and
recurring tasks with multi-step workflows.

Core Entities (defined in entities module):
  Codex -> Call -> TaskStep -> Task -> TaskSchedule

Execution Flow:
  1. create_scheduled_task() -> TaskManager._update_timers()
  2. ic.set_timer() schedules first step
  3. Timer fires -> executes code -> _check_and_schedule_next_step()
  4. For recurring: sets timer for next cycle (self-perpetuating, no heartbeat)

Key Use Case - Sync/Async Separation:
  IC canisters cannot mix sync and async in same function. TaskSteps solve this:
    Step 1 (Sync): Local computation
    Step 2 (Async): Inter-canister call with yield
    Step 3 (Sync): Process results
"""

import traceback
from typing import Callable, List

from .entities import Task, TaskExecution, TaskSchedule, TaskStep
from .status import TaskExecutionStatus, TaskStatus

# These imports only work inside the canister runtime
from _cdk import Async, Duration, ic, void
from ic_python_logging import get_logger

logger = get_logger("basilisk.os.task_manager")


def get_now() -> int:
    """Get current IC time in seconds."""
    return int(round(ic.time() / 1e9))


def _format_logs(logs_data) -> str:
    """Format logs from run_code result into a string for storage.

    Args:
        logs_data: Either a list of log dicts from get_logs(), or a string

    Returns:
        Formatted string of logs, truncated to 4999 chars
    """
    if not logs_data:
        return "No logs captured"

    if isinstance(logs_data, str):
        return logs_data[:4999]

    if isinstance(logs_data, list):
        formatted_lines = []
        for log in logs_data:
            if isinstance(log, dict):
                level = log.get("level", "INFO")
                msg = log.get("message", "")
                formatted_lines.append(f"[{level}] {msg}")
            else:
                formatted_lines.append(str(log))
        return "\n".join(formatted_lines)[:4999]

    return str(logs_data)[:4999]


def _check_and_schedule_next_step(task: Task) -> void:
    """Check if task has more steps and schedule the next one."""
    try:
        logger.info(
            f"Checking next step for task {task.name}. "
            f"Current step: {task.step_to_execute}, Total steps: {len(task.steps)}"
        )

        if task.step_to_execute < len(task.steps):
            step = list(task.steps)[task.step_to_execute]
            logger.info(
                f"Scheduling next step {task.step_to_execute}/{len(task.steps)} "
                f"for task {task.name}"
            )

            callback_function = _create_timer_callback(step, task)
            step.timer_id = ic.set_timer(
                Duration(step.run_next_after), callback_function
            )
            step.status = TaskStatus.RUNNING
            task.step_to_execute += 1
        else:
            logger.info(f"Task {task.name} completed all steps")
            task.status = TaskStatus.COMPLETED

            now = get_now()

            # Check if this is a recurring task and schedule next execution
            for schedule in task.schedules:
                if schedule.repeat_every and schedule.repeat_every > 0:
                    logger.info(
                        f"Task {task.name} is recurring, scheduling next "
                        f"execution in {schedule.repeat_every}s"
                    )
                    task.status = TaskStatus.RUNNING
                    task.step_to_execute = 0
                    # Reset all step statuses
                    for step in task.steps:
                        step.status = TaskStatus.PENDING
                    step = list(task.steps)[task.step_to_execute]
                    callback_function = _create_timer_callback(step, task)

                    in_seconds = schedule.repeat_every

                    logger.info(f"schedule.last_run_at : {schedule.last_run_at}")
                    logger.info(f"schedule.repeat_every: {schedule.repeat_every}")
                    logger.info(f"now                  : {now}")
                    logger.info(f"in_seconds           : {in_seconds}")

                    schedule.last_run_at = now

                    if schedule.disabled:
                        logger.info(
                            f"Skipping disabled schedule for task {task.name}"
                        )
                        continue

                    logger.info(f"Scheduling time in {in_seconds} seconds")
                    step.timer_id = ic.set_timer(
                        Duration(in_seconds), callback_function
                    )

    except Exception as e:
        logger.error(
            f"Error checking next step for task {task.name}: "
            f"{traceback.format_exc()}"
        )


def _create_timer_callback(step: TaskStep, task: Task) -> Callable:
    """Create a timer callback function for task execution.

    NOTE: This MUST be a module-level function, not a class method.
    Closures created inside class methods do not survive as IC timer
    callbacks in the basilisk WASM runtime.
    """
    # Capture entity IDs for re-loading inside callback
    step_id = str(step._id)
    task_id = str(task._id)
    is_async = step.call.is_async

    def timer_callback():
        # CRITICAL: The Rust ic_set_timer closure calls ic_cdk::trap() if the
        # Python callback raises ANY exception, rolling back all state changes
        # (including TaskExecution records).  We must catch everything here.
        try:
            # Re-load entities inside callback to avoid stale references
            _task = Task.load(task_id)
            _step = list(_task.steps)[
                [str(s._id) for s in _task.steps].index(step_id)
            ]
            logger.info(
                f"Executing {'async' if is_async else 'sync'} timer callback "
                f"for task {_task.name}"
            )
            task_execution = _task.new_task_execution()
            try:
                task_execution.status = TaskExecutionStatus.RUNNING
                result = _step.call._function(task_execution)()
                logger.info(f"Timer callback completed with result: {result}")

                task_execution.status = TaskExecutionStatus.COMPLETED
                _step.status = TaskStatus.COMPLETED
                _check_and_schedule_next_step(_task)
            except Exception as e:
                logger.error(f"Timer callback failed: {e}")
                logger.error(traceback.format_exc())

                task_execution.status = TaskExecutionStatus.FAILED
                task_execution.result = str(e)[:4999]

                _step.status = TaskStatus.FAILED
                _task.status = TaskStatus.FAILED
        except Exception as e:
            logger.error(f"Timer callback setup error: {e}")
            logger.error(traceback.format_exc())

    return timer_callback


class TaskManager:
    """Manages task scheduling and execution via IC timers."""

    tasks: List[Task] = []
    last_execution: int = 0
    task_to_execute: Task = None

    def add_task(self, task: Task) -> void:
        self.tasks.append(task)

    def __repr__(self) -> str:
        return (
            f"TaskManager(tasks={self.tasks}, "
            f"task_to_execute={self.task_to_execute})"
        )

    def _update_timers(self) -> void:
        logger.info("Updating timers")
        # Load tasks individually from database (not Task.instances() which
        # fails atomically if any related entity is missing)
        all_tasks = []
        if Task.count() > 0:
            max_id = Task.max_id()
            for tid in range(1, max_id + 1):
                try:
                    t = Task.load(str(tid))
                    if t:
                        all_tasks.append(t)
                except Exception:
                    logger.warning(f"Skipping Task {tid} due to load error")
        if not all_tasks:
            all_tasks = self.tasks
        logger.info(f"Found {len(all_tasks)} tasks in database")

        now = get_now()
        logger.info(f"Current time: {now}")

        for task in all_tasks:
            logger.info(f"Checking task {task.name}: {task.status}")
            if task.status == TaskStatus.PENDING:
                for schedule in task.schedules:
                    try:
                        logger.info(
                            f"Checking schedule {schedule.name}:\n"
                            f"Disabled: {schedule.disabled}\n"
                            f"run_at: {schedule.run_at}\n"
                            f"repeat_every: {schedule.repeat_every}\n"
                            f"last_run_at: {schedule.last_run_at}"
                        )

                        if schedule.disabled:
                            logger.info(
                                f"Skipping disabled schedule for task {task.name}"
                            )
                            continue

                        should_execute = False

                        if schedule.run_at and schedule.run_at > now:
                            logger.info(
                                "Skipping schedule because run_at is in the future"
                            )
                            should_execute = False
                        elif schedule.run_at and schedule.run_at <= now:
                            if not schedule.last_run_at or schedule.last_run_at == 0:
                                logger.info(
                                    "Executing schedule because run_at is in the past"
                                )
                                should_execute = True
                        elif not schedule.run_at or schedule.run_at == 0:
                            if not schedule.last_run_at or schedule.last_run_at == 0:
                                logger.info(
                                    "Executing schedule because last_run_at is not set"
                                )
                                should_execute = True

                        if schedule.repeat_every and schedule.repeat_every > 0:
                            if schedule.last_run_at and schedule.last_run_at > 0:
                                if now >= schedule.last_run_at + schedule.repeat_every:
                                    logger.info(
                                        "Executing schedule because interval has passed"
                                    )
                                    should_execute = True

                        if should_execute:
                            logger.info(
                                f"Scheduling task {task.name} for immediate execution"
                            )

                            if task.step_to_execute >= len(task.steps):
                                logger.error(
                                    f"Task {task.name} step_to_execute out of bounds"
                                )
                                continue

                            step = list(task.steps)[task.step_to_execute]
                            logger.info(
                                f"Starting task {task.name} - executing step "
                                f"{task.step_to_execute}/{len(task.steps)}"
                            )

                            callback_function = _create_timer_callback(step, task)
                            schedule.last_run_at = now
                            step.timer_id = ic.set_timer(
                                Duration(step.run_next_after), callback_function
                            )
                            step.status = TaskStatus.RUNNING
                            task.status = TaskStatus.RUNNING
                            task.step_to_execute += 1
                    except Exception as e:
                        logger.error(
                            f"Error scheduling task {task.name}: "
                            f"{traceback.format_exc()}"
                        )

        logger.info("No pending tasks to execute")

    def run(self) -> void:
        """Run the task manager — check all schedules and start pending tasks."""
        self._update_timers()
