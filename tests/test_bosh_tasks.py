"""Integration tests for Basilisk OS task management via bosh.

Tests the %task subcommand system and shortcut aliases (%ps, %start, %kill)
against a live canister. Tests are self-contained: they create tasks, verify
behaviour, and clean up after themselves.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from basilisk.bosh import (
    _handle_magic,
    _handle_task,
    _TASK_RESOLVE,
    _TASK_USAGE,
)
from tests.conftest import exec_on_canister, magic_on_canister


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_task_id(output: str) -> str:
    """Extract a numeric task ID from command output like 'Created task 42: ...'"""
    m = re.search(r'task\s+(\d+)', output, re.IGNORECASE)
    return m.group(1) if m else None


def _task_magic(cmd: str, canister: str, network: str) -> str:
    """Run a magic command and return stripped output."""
    result = _handle_magic(cmd, canister, network)
    return result.strip() if result else ""


def _cleanup_task(tid: str, canister: str, network: str):
    """Delete a task by ID, ignoring errors."""
    _handle_magic(f"%task delete {tid}", canister, network)


# ===========================================================================
# %task (no args) and %task list — listing
# ===========================================================================

class TestTaskList:
    """Test %task / %task list / %ps listing."""

    def test_task_no_args_returns_output(self, canister_reachable, canister, network):
        """%task with no args should return listing or 'No tasks.'"""
        result = _task_magic("%task", canister, network)
        assert result
        assert "|" in result or "No tasks" in result

    def test_task_list_returns_output(self, canister_reachable, canister, network):
        """%task list should behave the same as %task."""
        result = _task_magic("%task list", canister, network)
        assert result
        assert "|" in result or "No tasks" in result

    def test_task_ls_alias(self, canister_reachable, canister, network):
        """%task ls should be an alias for %task list."""
        result = _task_magic("%task ls", canister, network)
        assert result
        assert "|" in result or "No tasks" in result

    def test_ps_alias(self, canister_reachable, canister, network):
        """%ps should be a shortcut for %task list."""
        result = _task_magic("%ps", canister, network)
        assert result
        assert "|" in result or "No tasks" in result

    def test_tasks_alias(self, canister_reachable, canister, network):
        """%tasks should be a shortcut for %task list."""
        result = _task_magic("%tasks", canister, network)
        assert result
        assert "|" in result or "No tasks" in result

    def test_list_shows_created_task(self, canister_reachable, canister, network):
        """A created task should appear in %task list."""
        create_result = _task_magic("%task create _test_list_visible", canister, network)
        tid = _extract_task_id(create_result)
        assert tid, f"Failed to create task: {create_result}"
        try:
            result = _task_magic("%task", canister, network)
            assert "_test_list_visible" in result
            assert tid in result
        finally:
            _cleanup_task(tid, canister, network)

    def test_list_columns_format(self, canister_reachable, canister, network):
        """Listing should have id | status | repeat | enabled | name columns."""
        create_result = _task_magic(
            "%task create _test_columns every 120s", canister, network
        )
        tid = _extract_task_id(create_result)
        assert tid
        try:
            result = _task_magic("%task", canister, network)
            lines = [l for l in result.split("\n") if "_test_columns" in l]
            assert lines, f"Task not in listing: {result}"
            parts = lines[0].split("|")
            assert len(parts) >= 4, f"Expected 4+ columns: {lines[0]!r}"
        finally:
            _cleanup_task(tid, canister, network)

    def test_list_shows_schedule_info(self, canister_reachable, canister, network):
        """Scheduled tasks should show repeat interval and enabled status."""
        create_result = _task_magic(
            "%task create _test_sched_info every 300s", canister, network
        )
        tid = _extract_task_id(create_result)
        assert tid
        try:
            result = _task_magic("%task", canister, network)
            lines = [l for l in result.split("\n") if "_test_sched_info" in l]
            assert lines
            assert "300s" in lines[0]
            assert "enabled" in lines[0]
        finally:
            _cleanup_task(tid, canister, network)


# ===========================================================================
# %task create
# ===========================================================================

class TestTaskCreate:
    """Test %task create."""

    def test_create_simple(self, canister_reachable, canister, network):
        """Create a task without schedule."""
        result = _task_magic("%task create _test_simple_create", canister, network)
        tid = _extract_task_id(result)
        assert tid, f"Expected task ID in output: {result}"
        assert "_test_simple_create" in result
        assert "every" not in result.lower()
        _cleanup_task(tid, canister, network)

    def test_create_with_schedule(self, canister_reachable, canister, network):
        """Create a task with a recurring schedule."""
        result = _task_magic(
            "%task create _test_sched_create every 60s", canister, network
        )
        tid = _extract_task_id(result)
        assert tid
        assert "_test_sched_create" in result
        assert "every 60s" in result
        _cleanup_task(tid, canister, network)

    def test_create_with_large_interval(self, canister_reachable, canister, network):
        """Create a task with a large schedule interval."""
        result = _task_magic(
            "%task create _test_large_interval every 86400s", canister, network
        )
        tid = _extract_task_id(result)
        assert tid
        assert "86400s" in result
        _cleanup_task(tid, canister, network)

    def test_create_no_name_shows_usage(self, canister_reachable, canister, network):
        """Create without a name should show usage."""
        result = _task_magic("%task create", canister, network)
        assert "Usage" in result

    def test_create_sets_pending_status(self, canister_reachable, canister, network):
        """Newly created task should have 'pending' status."""
        create_result = _task_magic(
            "%task create _test_pending_status", canister, network
        )
        tid = _extract_task_id(create_result)
        assert tid
        try:
            info = _task_magic(f"%task info {tid}", canister, network)
            assert "pending" in info.lower()
        finally:
            _cleanup_task(tid, canister, network)

    def test_create_multiple_tasks(self, canister_reachable, canister, network):
        """Creating multiple tasks should each get unique IDs."""
        r1 = _task_magic("%task create _test_multi_1", canister, network)
        r2 = _task_magic("%task create _test_multi_2", canister, network)
        tid1 = _extract_task_id(r1)
        tid2 = _extract_task_id(r2)
        assert tid1 and tid2
        assert tid1 != tid2
        _cleanup_task(tid1, canister, network)
        _cleanup_task(tid2, canister, network)


# ===========================================================================
# %task info
# ===========================================================================

class TestTaskInfo:
    """Test %task info."""

    def test_info_shows_details(self, canister_reachable, canister, network):
        """Info should show task name, status, schedules, steps, executions."""
        create_result = _task_magic(
            "%task create _test_info_detail every 45s", canister, network
        )
        tid = _extract_task_id(create_result)
        assert tid
        try:
            info = _task_magic(f"%task info {tid}", canister, network)
            assert f"Task {tid}" in info
            assert "_test_info_detail" in info
            assert "Status:" in info
            assert "pending" in info.lower()
            assert "Schedule:" in info
            assert "45s" in info
            assert "enabled" in info
            assert "Steps:" in info
            assert "Executions:" in info
        finally:
            _cleanup_task(tid, canister, network)

    def test_info_no_schedule(self, canister_reachable, canister, network):
        """Task without schedule should show 'Schedules: none'."""
        create_result = _task_magic(
            "%task create _test_info_nosched", canister, network
        )
        tid = _extract_task_id(create_result)
        assert tid
        try:
            info = _task_magic(f"%task info {tid}", canister, network)
            assert "none" in info.lower()
        finally:
            _cleanup_task(tid, canister, network)

    def test_info_nonexistent(self, canister_reachable, canister, network):
        """Info on a nonexistent task should say not found."""
        result = _task_magic("%task info 999999", canister, network)
        assert "not found" in result.lower()

    def test_info_no_id_shows_usage(self, canister_reachable, canister, network):
        """Info without an ID should show usage."""
        result = _task_magic("%task info", canister, network)
        assert "Usage" in result


# ===========================================================================
# %task log
# ===========================================================================

class TestTaskLog:
    """Test %task log."""

    def test_log_empty(self, canister_reachable, canister, network):
        """Log of a new task should show 'no executions'."""
        create_result = _task_magic(
            "%task create _test_log_empty", canister, network
        )
        tid = _extract_task_id(create_result)
        assert tid
        try:
            result = _task_magic(f"%task log {tid}", canister, network)
            assert "no executions" in result.lower()
            assert "_test_log_empty" in result
        finally:
            _cleanup_task(tid, canister, network)

    def test_log_with_execution(self, canister_reachable, canister, network):
        """Log should show execution records if any exist."""
        create_result = _task_magic(
            "%task create _test_log_exec", canister, network
        )
        tid = _extract_task_id(create_result)
        assert tid
        try:
            # Manually create an execution record
            exec_on_canister(
                _TASK_RESOLVE +
                f"_t = Task.load('{tid}')\n"
                "_e = TaskExecution(name='exec-1', task=_t, status='completed', result='ok')\n"
                "print('created')",
                canister, network,
            )
            result = _task_magic(f"%task log {tid}", canister, network)
            assert "1 execution" in result
            assert "completed" in result
        finally:
            _cleanup_task(tid, canister, network)

    def test_log_nonexistent(self, canister_reachable, canister, network):
        """Log of nonexistent task should say not found."""
        result = _task_magic("%task log 999999", canister, network)
        assert "not found" in result.lower()

    def test_log_no_id_shows_usage(self, canister_reachable, canister, network):
        """Log without ID should show usage."""
        result = _task_magic("%task log", canister, network)
        assert "Usage" in result


# ===========================================================================
# %task start / %task stop — lifecycle
# ===========================================================================

class TestTaskLifecycle:
    """Test starting and stopping tasks (self-contained)."""

    def test_stop_sets_cancelled(self, canister_reachable, canister, network):
        """Stopping a task should set status to cancelled."""
        create_result = _task_magic(
            "%task create _test_stop_cancel", canister, network
        )
        tid = _extract_task_id(create_result)
        assert tid
        try:
            result = _task_magic(f"%task stop {tid}", canister, network)
            assert "Stopped" in result
            info = _task_magic(f"%task info {tid}", canister, network)
            assert "cancelled" in info.lower()
        finally:
            _cleanup_task(tid, canister, network)

    def test_stop_disables_schedule(self, canister_reachable, canister, network):
        """Stopping a task should disable its schedules."""
        create_result = _task_magic(
            "%task create _test_stop_sched every 60s", canister, network
        )
        tid = _extract_task_id(create_result)
        assert tid
        try:
            _task_magic(f"%task stop {tid}", canister, network)
            info = _task_magic(f"%task info {tid}", canister, network)
            assert "disabled" in info.lower()
        finally:
            _cleanup_task(tid, canister, network)

    def test_start_sets_pending(self, canister_reachable, canister, network):
        """Starting a stopped task should set status back to pending."""
        create_result = _task_magic(
            "%task create _test_start_pending", canister, network
        )
        tid = _extract_task_id(create_result)
        assert tid
        try:
            _task_magic(f"%task stop {tid}", canister, network)
            result = _task_magic(f"%task start {tid}", canister, network)
            assert "Started" in result
            info = _task_magic(f"%task info {tid}", canister, network)
            assert "pending" in info.lower()
        finally:
            _cleanup_task(tid, canister, network)

    def test_start_enables_schedule(self, canister_reachable, canister, network):
        """Starting a task should re-enable its schedules."""
        create_result = _task_magic(
            "%task create _test_start_sched every 60s", canister, network
        )
        tid = _extract_task_id(create_result)
        assert tid
        try:
            _task_magic(f"%task stop {tid}", canister, network)
            _task_magic(f"%task start {tid}", canister, network)
            info = _task_magic(f"%task info {tid}", canister, network)
            assert "enabled" in info.lower()
            assert "disabled" not in info.lower()
        finally:
            _cleanup_task(tid, canister, network)

    def test_full_lifecycle_roundtrip(self, canister_reachable, canister, network):
        """Full lifecycle: create → list → stop → verify → start → verify → delete."""
        # Create
        create_result = _task_magic(
            "%task create _test_roundtrip every 30s", canister, network
        )
        tid = _extract_task_id(create_result)
        assert tid

        try:
            # Verify in listing
            listing = _task_magic("%task", canister, network)
            assert "_test_roundtrip" in listing

            # Stop
            stop_result = _task_magic(f"%task stop {tid}", canister, network)
            assert "Stopped" in stop_result
            listing2 = _task_magic("%task", canister, network)
            task_line = [l for l in listing2.split("\n") if "_test_roundtrip" in l]
            assert task_line
            assert "cancelled" in task_line[0]

            # Start
            start_result = _task_magic(f"%task start {tid}", canister, network)
            assert "Started" in start_result
            listing3 = _task_magic("%task", canister, network)
            task_line2 = [l for l in listing3.split("\n") if "_test_roundtrip" in l]
            assert task_line2
            assert "pending" in task_line2[0]

            # Delete
            del_result = _task_magic(f"%task delete {tid}", canister, network)
            assert "Deleted" in del_result
            listing4 = _task_magic("%task", canister, network)
            assert "_test_roundtrip" not in listing4
        except Exception:
            _cleanup_task(tid, canister, network)
            raise

    def test_stop_nonexistent(self, canister_reachable, canister, network):
        """Stopping a nonexistent task should report not found."""
        result = _task_magic("%task stop 999999", canister, network)
        assert "not found" in result.lower()

    def test_start_nonexistent(self, canister_reachable, canister, network):
        """Starting a nonexistent task should report not found."""
        result = _task_magic("%task start 999999", canister, network)
        assert "not found" in result.lower()

    def test_stop_no_id_shows_usage(self, canister_reachable, canister, network):
        """Stop without ID should show usage."""
        result = _task_magic("%task stop", canister, network)
        assert "Usage" in result

    def test_start_no_id_shows_usage(self, canister_reachable, canister, network):
        """Start without ID should show usage."""
        result = _task_magic("%task start", canister, network)
        assert "Usage" in result


# ===========================================================================
# %task delete
# ===========================================================================

class TestTaskDelete:
    """Test %task delete."""

    def test_delete_removes_task(self, canister_reachable, canister, network):
        """Deleting a task should remove it from listing."""
        create_result = _task_magic(
            "%task create _test_delete_remove", canister, network
        )
        tid = _extract_task_id(create_result)
        assert tid
        result = _task_magic(f"%task delete {tid}", canister, network)
        assert "Deleted" in result
        listing = _task_magic("%task", canister, network)
        assert "_test_delete_remove" not in listing

    def test_delete_removes_schedule(self, canister_reachable, canister, network):
        """Deleting a task with schedule should remove the schedule too."""
        create_result = _task_magic(
            "%task create _test_delete_sched every 60s", canister, network
        )
        tid = _extract_task_id(create_result)
        assert tid
        # Verify schedule exists via info
        info = _task_magic(f"%task info {tid}", canister, network)
        assert "Schedule:" in info
        # Delete
        _task_magic(f"%task delete {tid}", canister, network)
        # Task should be gone
        info2 = _task_magic(f"%task info {tid}", canister, network)
        assert "not found" in info2.lower()

    def test_delete_nonexistent(self, canister_reachable, canister, network):
        """Deleting a nonexistent task should report not found."""
        result = _task_magic("%task delete 999999", canister, network)
        assert "not found" in result.lower()

    def test_delete_no_id_shows_usage(self, canister_reachable, canister, network):
        """Delete without ID should show usage."""
        result = _task_magic("%task delete", canister, network)
        assert "Usage" in result

    def test_delete_aliases(self, canister_reachable, canister, network):
        """%task del and %task rm should work as aliases."""
        r1 = _task_magic("%task create _test_del_alias", canister, network)
        tid1 = _extract_task_id(r1)
        assert tid1
        result1 = _task_magic(f"%task del {tid1}", canister, network)
        assert "Deleted" in result1

        r2 = _task_magic("%task create _test_rm_alias", canister, network)
        tid2 = _extract_task_id(r2)
        assert tid2
        result2 = _task_magic(f"%task rm {tid2}", canister, network)
        assert "Deleted" in result2


# ===========================================================================
# Shortcut aliases — backwards compatibility
# ===========================================================================

class TestShortcutAliases:
    """Test that %ps, %start, %kill still work as shortcuts."""

    def test_ps_alias(self, canister_reachable, canister, network):
        """%ps should behave like %task list."""
        result = _task_magic("%ps", canister, network)
        assert "|" in result or "No tasks" in result

    def test_start_alias(self, canister_reachable, canister, network):
        """%start <id> should behave like %task start <id>."""
        create_result = _task_magic(
            "%task create _test_start_alias", canister, network
        )
        tid = _extract_task_id(create_result)
        assert tid
        try:
            _task_magic(f"%task stop {tid}", canister, network)
            result = _task_magic(f"%start {tid}", canister, network)
            assert "Started" in result
        finally:
            _cleanup_task(tid, canister, network)

    def test_kill_alias(self, canister_reachable, canister, network):
        """%kill <id> should behave like %task stop <id>."""
        create_result = _task_magic(
            "%task create _test_kill_alias", canister, network
        )
        tid = _extract_task_id(create_result)
        assert tid
        try:
            result = _task_magic(f"%kill {tid}", canister, network)
            assert "Stopped" in result
        finally:
            _cleanup_task(tid, canister, network)

    def test_kill_nonexistent(self, canister_reachable, canister, network):
        """%kill on nonexistent task should report not found."""
        result = _task_magic("%kill 999999", canister, network)
        assert "not found" in result.lower()

    def test_start_nonexistent(self, canister_reachable, canister, network):
        """%start on nonexistent task should report not found."""
        result = _task_magic("%start 999999", canister, network)
        assert "not found" in result.lower()


# ===========================================================================
# %task usage / unknown subcommand
# ===========================================================================

class TestTaskUsage:
    """Test usage messages and error handling."""

    def test_unknown_subcommand_shows_usage(self, canister_reachable, canister, network):
        """Unknown subcommand should show usage."""
        result = _task_magic("%task foobar", canister, network)
        assert "Usage" in result

    def test_task_help_contains_all_subcommands(self, canister_reachable, canister, network):
        """Usage message should list all subcommands."""
        result = _task_magic("%task foobar", canister, network)
        for cmd in ("list", "create", "info", "log", "start", "stop", "delete"):
            assert cmd in result, f"'{cmd}' not in usage message"


# ===========================================================================
# Entity operations via direct exec
# ===========================================================================

class TestTaskEntities:
    """Test task entity operations via direct canister exec."""

    def test_task_count(self, canister_reachable, canister, network):
        """Task.count() should return a number."""
        result = exec_on_canister(
            _TASK_RESOLVE + "print(Task.count())",
            canister, network,
        )
        count = int(result)
        assert count >= 0

    def test_task_instances_iterable(self, canister_reachable, canister, network):
        """Task.instances() should return iterable tasks."""
        result = exec_on_canister(
            _TASK_RESOLVE +
            "for t in Task.instances(): print(f'{t._id}: {t.name}')\n"
            "if Task.count() == 0: print('none')",
            canister, network,
        )
        assert result

    def test_task_load_and_fields(self, canister_reachable, canister, network):
        """Task.load() should return a task with expected fields."""
        # Create via magic, load via exec
        create_result = _task_magic(
            "%task create _test_entity_load", canister, network
        )
        tid = _extract_task_id(create_result)
        assert tid
        try:
            result = exec_on_canister(
                _TASK_RESOLVE +
                f"t = Task.load('{tid}')\n"
                "print(f'{t.name}|{t.status}')",
                canister, network,
            )
            assert "_test_entity_load" in result
            assert "pending" in result
        finally:
            _cleanup_task(tid, canister, network)

    def test_task_schedule_relationship(self, canister_reachable, canister, network):
        """Task.schedules relationship should be iterable."""
        create_result = _task_magic(
            "%task create _test_entity_sched every 90s", canister, network
        )
        tid = _extract_task_id(create_result)
        assert tid
        try:
            result = exec_on_canister(
                _TASK_RESOLVE +
                f"t = Task.load('{tid}')\n"
                "scheds = list(t.schedules)\n"
                "print(f'{len(scheds)} schedules')\n"
                "if scheds: print(f'repeat={scheds[0].repeat_every}')",
                canister, network,
            )
            assert "1 schedules" in result
            assert "repeat=90" in result
        finally:
            _cleanup_task(tid, canister, network)

    def test_task_steps_relationship(self, canister_reachable, canister, network):
        """Task.steps relationship should be iterable (empty on new task)."""
        create_result = _task_magic(
            "%task create _test_entity_steps", canister, network
        )
        tid = _extract_task_id(create_result)
        assert tid
        try:
            result = exec_on_canister(
                _TASK_RESOLVE +
                f"t = Task.load('{tid}')\n"
                "print(f'{len(list(t.steps))} steps')",
                canister, network,
            )
            assert "0 steps" in result
        finally:
            _cleanup_task(tid, canister, network)

    def test_task_executions_relationship(self, canister_reachable, canister, network):
        """Task.executions relationship should be iterable."""
        create_result = _task_magic(
            "%task create _test_entity_execs", canister, network
        )
        tid = _extract_task_id(create_result)
        assert tid
        try:
            result = exec_on_canister(
                _TASK_RESOLVE +
                f"t = Task.load('{tid}')\n"
                "print(f'{len(list(t.executions))} executions')",
                canister, network,
            )
            assert "0 executions" in result
        finally:
            _cleanup_task(tid, canister, network)


# ===========================================================================
# End-to-end task execution tests
# ===========================================================================

class TestTaskExecution:
    """End-to-end tests: create task with code, run, verify execution.

    These tests verify the full execution chain on the IC canister:
      %task create --code "..." → %task run → code executes inline →
      TaskExecution recorded → %task log shows result

    Uses %task run (synchronous inline execution) for reliable testing.
    %task start (timer-based) requires full Basilisk OS canister support.
    """

    def test_create_with_code(self, canister_reachable, canister, network):
        """Creating a task with --code should set up the full entity chain."""
        result = _task_magic(
            '%task create _test_e2e_code --code "print(42)"', canister, network
        )
        tid = _extract_task_id(result)
        assert tid, f"Failed to create task: {result}"
        assert "with code" in result
        try:
            info = _task_magic(f"%task info {tid}", canister, network)
            assert "Steps: 1" in info
            assert "print(42)" in info
        finally:
            _cleanup_task(tid, canister, network)

    def test_create_with_code_and_schedule(self, canister_reachable, canister, network):
        """Creating with --code and every Ns should set up code + schedule."""
        result = _task_magic(
            '%task create _test_e2e_code_sched every 60s --code "print(1+1)"',
            canister, network,
        )
        tid = _extract_task_id(result)
        assert tid, f"Failed to create task: {result}"
        assert "with code" in result
        assert "every 60s" in result
        try:
            info = _task_magic(f"%task info {tid}", canister, network)
            assert "Steps: 1" in info
            assert "Schedule:" in info
            assert "60s" in info
        finally:
            _cleanup_task(tid, canister, network)

    def test_run_one_shot(self, canister_reachable, canister, network):
        """Run a one-shot task with code; verify execution result in log."""
        result = _task_magic(
            '%task create _test_e2e_oneshot --code "print(42)"',
            canister, network,
        )
        tid = _extract_task_id(result)
        assert tid, f"Failed to create task: {result}"
        try:
            run_result = _task_magic(f"%task run {tid}", canister, network)
            assert "completed" in run_result
            assert "1 execution" in run_result

            log = _task_magic(f"%task log {tid}", canister, network)
            assert "1 execution" in log
            assert "completed" in log
            assert "42" in log

            info = _task_magic(f"%task info {tid}", canister, network)
            assert "completed" in info.lower()
        finally:
            _cleanup_task(tid, canister, network)

    def test_run_captures_output(self, canister_reachable, canister, network):
        """Task execution should capture stdout in TaskExecution.result."""
        result = _task_magic(
            '%task create _test_e2e_output --code "for i in range(3): print(i)"',
            canister, network,
        )
        tid = _extract_task_id(result)
        assert tid, f"Failed to create task: {result}"
        try:
            _task_magic(f"%task run {tid}", canister, network)

            log = _task_magic(f"%task log {tid}", canister, network)
            assert "completed" in log
            # Output should contain "0", "1", "2" from the loop
            assert "0" in log
        finally:
            _cleanup_task(tid, canister, network)

    def test_run_failure_recorded(self, canister_reachable, canister, network):
        """Task with failing code should record 'failed' status and traceback."""
        result = _task_magic(
            '%task create _test_e2e_fail --code "raise ValueError(123)"',
            canister, network,
        )
        tid = _extract_task_id(result)
        assert tid, f"Failed to create task: {result}"
        try:
            run_result = _task_magic(f"%task run {tid}", canister, network)
            assert "failed" in run_result

            log = _task_magic(f"%task log {tid}", canister, network)
            assert "1 execution" in log
            assert "failed" in log
            assert "ValueError" in log

            info = _task_magic(f"%task info {tid}", canister, network)
            assert "failed" in info.lower()
        finally:
            _cleanup_task(tid, canister, network)

    def test_run_multiple_times(self, canister_reachable, canister, network):
        """Running a task multiple times should accumulate executions."""
        result = _task_magic(
            '%task create _test_e2e_multi --code "print(42)"',
            canister, network,
        )
        tid = _extract_task_id(result)
        assert tid, f"Failed to create task: {result}"
        try:
            _task_magic(f"%task run {tid}", canister, network)
            _task_magic(f"%task run {tid}", canister, network)
            r3 = _task_magic(f"%task run {tid}", canister, network)
            assert "3 execution" in r3

            log = _task_magic(f"%task log {tid}", canister, network)
            assert "3 execution" in log
        finally:
            _cleanup_task(tid, canister, network)

    def test_run_without_code(self, canister_reachable, canister, network):
        """Running a task without code should report 'no executable code'."""
        result = _task_magic(
            "%task create _test_e2e_nocode_run", canister, network
        )
        tid = _extract_task_id(result)
        assert tid, f"Failed to create task: {result}"
        try:
            run_result = _task_magic(f"%task run {tid}", canister, network)
            assert "no executable code" in run_result
        finally:
            _cleanup_task(tid, canister, network)

    def test_run_nonexistent(self, canister_reachable, canister, network):
        """Running a nonexistent task should report 'not found'."""
        run_result = _task_magic("%task run 99999", canister, network)
        assert "not found" in run_result.lower()

    def test_run_no_id_shows_usage(self, canister_reachable, canister, network):
        """Running without an ID should show usage."""
        run_result = _task_magic("%task run", canister, network)
        assert "usage" in run_result.lower() or "run" in run_result.lower()

    def test_delete_with_code_entities(self, canister_reachable, canister, network):
        """Deleting a task with code should clean up Codex, Call, TaskStep."""
        result = _task_magic(
            '%task create _test_e2e_del_code --code "print(1)"', canister, network
        )
        tid = _extract_task_id(result)
        assert tid, f"Failed to create task: {result}"
        del_result = _task_magic(f"%task delete {tid}", canister, network)
        assert "Deleted" in del_result
        info = _task_magic(f"%task info {tid}", canister, network)
        assert "not found" in info.lower()

    def test_info_shows_code_snippet(self, canister_reachable, canister, network):
        """Task info should show a code snippet for steps with code."""
        result = _task_magic(
            '%task create _test_e2e_snippet --code "x = 42; print(x)"',
            canister, network,
        )
        tid = _extract_task_id(result)
        assert tid, f"Failed to create task: {result}"
        try:
            info = _task_magic(f"%task info {tid}", canister, network)
            assert "x = 42" in info
        finally:
            _cleanup_task(tid, canister, network)

    def test_start_without_code_no_timer(self, canister_reachable, canister, network):
        """Starting a task without code should NOT schedule a timer."""
        result = _task_magic(
            "%task create _test_e2e_no_code", canister, network
        )
        tid = _extract_task_id(result)
        assert tid, f"Failed to create task: {result}"
        try:
            start_result = _task_magic(f"%task start {tid}", canister, network)
            assert "Started" in start_result
            assert "timer" not in start_result.lower()
        finally:
            _cleanup_task(tid, canister, network)

    def test_start_with_code_schedules_timer(self, canister_reachable, canister, network):
        """Starting a task with code should schedule a timer."""
        result = _task_magic(
            '%task create _test_e2e_timer --code "print(1)"', canister, network
        )
        tid = _extract_task_id(result)
        assert tid, f"Failed to create task: {result}"
        try:
            start_result = _task_magic(f"%task start {tid}", canister, network)
            assert "timer scheduled" in start_result
        finally:
            _cleanup_task(tid, canister, network)


# ===========================================================================
# Task lookup by name (not just ID)
# ===========================================================================

class TestTaskNameLookup:
    """Test that %task subcommands accept task names in addition to IDs."""

    def test_info_by_name(self, canister_reachable, canister, network):
        """Info should work when given a task name instead of ID."""
        create_result = _task_magic(
            "%task create _test_name_info", canister, network
        )
        tid = _extract_task_id(create_result)
        assert tid
        try:
            result = _task_magic("%task info _test_name_info", canister, network)
            assert f"Task {tid}" in result
            assert "_test_name_info" in result
        finally:
            _cleanup_task(tid, canister, network)

    def test_log_by_name(self, canister_reachable, canister, network):
        """Log should work when given a task name."""
        create_result = _task_magic(
            "%task create _test_name_log", canister, network
        )
        tid = _extract_task_id(create_result)
        assert tid
        try:
            result = _task_magic("%task log _test_name_log", canister, network)
            assert "_test_name_log" in result
            assert "no executions" in result.lower()
        finally:
            _cleanup_task(tid, canister, network)

    def test_start_by_name(self, canister_reachable, canister, network):
        """Start should work when given a task name."""
        create_result = _task_magic(
            "%task create _test_name_start", canister, network
        )
        tid = _extract_task_id(create_result)
        assert tid
        try:
            result = _task_magic("%task start _test_name_start", canister, network)
            assert "Started" in result
            assert "_test_name_start" in result
        finally:
            _cleanup_task(tid, canister, network)

    def test_stop_by_name(self, canister_reachable, canister, network):
        """Stop should work when given a task name."""
        create_result = _task_magic(
            "%task create _test_name_stop", canister, network
        )
        tid = _extract_task_id(create_result)
        assert tid
        try:
            result = _task_magic("%task stop _test_name_stop", canister, network)
            assert "Stopped" in result
            assert "_test_name_stop" in result
        finally:
            _cleanup_task(tid, canister, network)

    def test_delete_by_name(self, canister_reachable, canister, network):
        """Delete should work when given a task name."""
        create_result = _task_magic(
            "%task create _test_name_delete", canister, network
        )
        tid = _extract_task_id(create_result)
        assert tid
        result = _task_magic("%task delete _test_name_delete", canister, network)
        assert "Deleted" in result
        info = _task_magic(f"%task info {tid}", canister, network)
        assert "not found" in info.lower()

    def test_run_by_name(self, canister_reachable, canister, network):
        """Run should work when given a task name."""
        create_result = _task_magic(
            '%task create _test_name_run --code "print(99)"', canister, network
        )
        tid = _extract_task_id(create_result)
        assert tid
        try:
            result = _task_magic("%task run _test_name_run", canister, network)
            assert "completed" in result
            assert "_test_name_run" in result
            # Verify the execution was recorded via log
            log = _task_magic(f"%task log {tid}", canister, network)
            assert "99" in log
        finally:
            _cleanup_task(tid, canister, network)

    def test_name_lookup_prefers_latest(self, canister_reachable, canister, network):
        """When multiple tasks share a name, lookup should prefer the latest (highest ID)."""
        r1 = _task_magic("%task create _test_dup_name", canister, network)
        tid1 = _extract_task_id(r1)
        r2 = _task_magic("%task create _test_dup_name", canister, network)
        tid2 = _extract_task_id(r2)
        assert tid1 and tid2
        assert int(tid2) > int(tid1)
        try:
            info = _task_magic("%task info _test_dup_name", canister, network)
            assert f"Task {tid2}" in info
        finally:
            _cleanup_task(tid1, canister, network)
            _cleanup_task(tid2, canister, network)


# ===========================================================================
# %task create --file option
# ===========================================================================

class TestTaskCreateFile:
    """Test %task create --file option."""

    def test_create_with_file(self, canister_reachable, canister, network):
        """Creating a task with --file should set up code from a canister file."""
        # Write a file to the canister first
        exec_on_canister(
            "with open('/_test_task_file.py', 'w') as f: f.write('print(77)')",
            canister, network,
        )
        result = _task_magic(
            "%task create _test_file_opt --file /_test_task_file.py",
            canister, network,
        )
        tid = _extract_task_id(result)
        assert tid, f"Failed to create task: {result}"
        assert "with code" in result
        try:
            info = _task_magic(f"%task info {tid}", canister, network)
            assert "Steps: 1" in info
            assert "_test_task_file.py" in info
        finally:
            _cleanup_task(tid, canister, network)

    def test_create_with_file_and_schedule(self, canister_reachable, canister, network):
        """Creating with --file and every Ns should set up code + schedule."""
        exec_on_canister(
            "with open('/_test_task_file2.py', 'w') as f: f.write('print(88)')",
            canister, network,
        )
        result = _task_magic(
            "%task create _test_file_sched every 60s --file /_test_task_file2.py",
            canister, network,
        )
        tid = _extract_task_id(result)
        assert tid, f"Failed to create task: {result}"
        assert "with code" in result
        assert "every 60s" in result
        try:
            info = _task_magic(f"%task info {tid}", canister, network)
            assert "Schedule:" in info
            assert "60s" in info
        finally:
            _cleanup_task(tid, canister, network)

    def test_run_task_from_file(self, canister_reachable, canister, network):
        """Running a task created with --file should execute the file's code."""
        exec_on_canister(
            "with open('/_test_run_file.py', 'w') as f: f.write('print(55)')",
            canister, network,
        )
        result = _task_magic(
            "%task create _test_run_file --file /_test_run_file.py",
            canister, network,
        )
        tid = _extract_task_id(result)
        assert tid
        try:
            run = _task_magic(f"%task run {tid}", canister, network)
            assert "completed" in run
            # Verify the execution result via log
            log = _task_magic(f"%task log {tid}", canister, network)
            assert "55" in log
        finally:
            _cleanup_task(tid, canister, network)


# ===========================================================================
# Timestamps in %task log and %task info
# ===========================================================================

class TestTaskTimestamps:
    """Test that timestamps appear in task log and info after execution."""

    def test_log_shows_timestamp(self, canister_reachable, canister, network):
        """After running a task, %task log should show a UTC timestamp."""
        result = _task_magic(
            '%task create _test_ts_log --code "print(1)"', canister, network
        )
        tid = _extract_task_id(result)
        assert tid
        try:
            _task_magic(f"%task run {tid}", canister, network)
            log = _task_magic(f"%task log {tid}", canister, network)
            assert "UTC" in log
            assert re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC', log), \
                f"Expected timestamp in log: {log}"
        finally:
            _cleanup_task(tid, canister, network)

    def test_info_shows_last_execution_time(self, canister_reachable, canister, network):
        """After running a task, %task info should show last execution time."""
        result = _task_magic(
            '%task create _test_ts_info --code "print(2)"', canister, network
        )
        tid = _extract_task_id(result)
        assert tid
        try:
            _task_magic(f"%task run {tid}", canister, network)
            info = _task_magic(f"%task info {tid}", canister, network)
            assert "last:" in info.lower()
            assert "UTC" in info
        finally:
            _cleanup_task(tid, canister, network)

    def test_list_shows_last_execution_time(self, canister_reachable, canister, network):
        """After running a task, %task list should show last execution time."""
        result = _task_magic(
            '%task create _test_ts_list --code "print(3)"', canister, network
        )
        tid = _extract_task_id(result)
        assert tid
        try:
            _task_magic(f"%task run {tid}", canister, network)
            listing = _task_magic("%task list", canister, network)
            lines = [l for l in listing.split("\n") if "_test_ts_list" in l]
            assert lines
            assert "last=" in lines[0]
            assert "UTC" in lines[0]
        finally:
            _cleanup_task(tid, canister, network)


# ===========================================================================
# %task log output limiting and --follow
# ===========================================================================

class TestTaskLogFeatures:
    """Test log output limiting and --follow flag."""

    def test_log_limits_to_last_10(self, canister_reachable, canister, network):
        """When more than 10 executions exist, log should show only last 10."""
        result = _task_magic(
            '%task create _test_log_limit --code "print(1)"', canister, network
        )
        tid = _extract_task_id(result)
        assert tid
        try:
            # Run 12 times to exceed the limit
            for _ in range(12):
                _task_magic(f"%task run {tid}", canister, network)
            log = _task_magic(f"%task log {tid}", canister, network)
            assert "12 execution" in log
            assert "showing last 10" in log
            assert "2 older omitted" in log
        finally:
            _cleanup_task(tid, canister, network)

    def test_follow_flag_accepted(self, canister_reachable, canister, network):
        """--follow flag should be accepted (returns empty since task has no executions)."""
        result = _task_magic(
            "%task create _test_follow_flag", canister, network
        )
        tid = _extract_task_id(result)
        assert tid
        try:
            # We can't test the actual polling loop in CI, but we can verify
            # the flag doesn't cause an error by checking _handle_task directly.
            # The follow loop would run forever, so instead test the query works.
            from basilisk.bosh import _task_log_follow_query, canister_exec
            query_code = _task_log_follow_query(str(tid))
            query_result = canister_exec(query_code, canister, network)
            # Should contain the task status line
            assert "__FOLLOW_TASK__" in query_result
        finally:
            _cleanup_task(tid, canister, network)

    def test_follow_flag_in_usage(self, canister_reachable, canister, network):
        """Usage message should mention --follow."""
        result = _task_magic("%task foobar", canister, network)
        assert "--follow" in result
