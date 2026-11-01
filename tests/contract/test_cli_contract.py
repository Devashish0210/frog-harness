"""Contract tests for CLI command parsing and help definitions."""

import pytest
from frognano_harness.cli import build_parser


def test_cli_parser_all_14_commands_registered() -> None:
    parser = build_parser()
    subparsers_action = next(
        action for action in parser._actions if action.dest == "command"
    )
    expected_commands = {
        "init",
        "validate",
        "plan",
        "run",
        "resume",
        "status",
        "task",
        "retry",
        "approve",
        "reject",
        "report",
        "logs",
        "verify",
        "audit",
    }
    registered_commands = set(subparsers_action.choices.keys())
    assert expected_commands.issubset(registered_commands)


def test_cli_init_args() -> None:
    parser = build_parser()
    args = parser.parse_args(["init", "--endpoint", "http://127.0.0.1:8080/v1", "--model", "frognano", "--force"])
    assert args.command == "init"
    assert args.endpoint == "http://127.0.0.1:8080/v1"
    assert args.model == "frognano"
    assert args.force is True


def test_cli_validate_args() -> None:
    parser = build_parser()
    args = parser.parse_args(["validate", "--tasks", "specs/002/tasks.md", "--json"])
    assert args.command == "validate"
    assert args.tasks == "specs/002/tasks.md"
    assert args.json is True


def test_cli_plan_args() -> None:
    parser = build_parser()
    args = parser.parse_args(["plan", "--tasks", "specs/002/tasks.md", "--ascii", "--json"])
    assert args.command == "plan"
    assert args.ascii is True
    assert args.json is True


def test_cli_run_args() -> None:
    parser = build_parser()
    args = parser.parse_args(["run", "--task", "T001", "--max-retries", "2", "--unattended", "--timeout", "180"])
    assert args.command == "run"
    assert args.task == "T001"
    assert args.max_retries == 2
    assert args.unattended is True
    assert args.timeout == 180


def test_cli_resume_args() -> None:
    parser = build_parser()
    args = parser.parse_args(["resume", "--run-id", "run_123", "--unattended"])
    assert args.command == "resume"
    assert args.run_id == "run_123"
    assert args.unattended is True


def test_cli_status_args() -> None:
    parser = build_parser()
    args = parser.parse_args(["status", "--json", "--watch"])
    assert args.command == "status"
    assert args.json is True
    assert args.watch is True


def test_cli_task_args() -> None:
    parser = build_parser()
    args = parser.parse_args(["task", "T005", "--json"])
    assert args.command == "task"
    assert args.task_id == "T005"
    assert args.json is True


def test_cli_retry_args() -> None:
    parser = build_parser()
    args = parser.parse_args(["retry", "T005", "--force"])
    assert args.command == "retry"
    assert args.task_id == "T005"
    assert args.force is True


def test_cli_approval_args() -> None:
    parser = build_parser()
    args_app = parser.parse_args(["approve", "APP-1234"])
    assert args_app.command == "approve"
    assert args_app.approval_id == "APP-1234"

    args_rej = parser.parse_args(["reject", "APP-1234", "--reason", "Not authorized"])
    assert args_rej.command == "reject"
    assert args_rej.approval_id == "APP-1234"
    assert args_rej.reason == "Not authorized"


def test_cli_report_args() -> None:
    parser = build_parser()
    args = parser.parse_args(["report", "--output", ".harness/reports", "--format", "both"])
    assert args.command == "report"
    assert args.output == ".harness/reports"
    assert args.format == "both"


def test_cli_logs_args() -> None:
    parser = build_parser()
    args = parser.parse_args(["logs", "T001", "--tail", "50", "--tool", "run_command"])
    assert args.command == "logs"
    assert args.task_id == "T001"
    assert args.tail == 50
    assert args.tool == "run_command"


def test_cli_verify_args() -> None:
    parser = build_parser()
    args = parser.parse_args(["verify", "T001"])
    assert args.command == "verify"
    assert args.task_id == "T001"

    args_all = parser.parse_args(["verify", "--all"])
    assert args_all.command == "verify"
    assert args_all.all is True


def test_cli_audit_args() -> None:
    parser = build_parser()
    args = parser.parse_args(["audit", "--verify-chain", "--tool-call", "TC-1049", "--json"])
    assert args.command == "audit"
    assert args.verify_chain is True
    assert args.tool_call == "TC-1049"
    assert args.json is True
