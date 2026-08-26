#!/usr/bin/env python3
"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.

Usage:
    python run_tests.py                   # Run all tests
    python run_tests.py --task-lifecycle  # Run task lifecycle tests only
    python run_tests.py --task-poller     # Run task poller tests only
    python run_tests.py --locust-runner   # Run locust runner tests only
    python run_tests.py --coverage        # Run with coverage report
    python run_tests.py --html            # Generate HTML coverage report
    python run_tests.py --verbose         # Verbose output
"""

import argparse
import subprocess  # nosec B404 - subprocess usage is controlled and validated
import sys
from pathlib import Path

# Security: Define allowed commands and arguments to prevent command injection
ALLOWED_COMMANDS = {
    "python": ["-m", "pytest"],
}

ALLOWED_PYTEST_ARGS = {
    "-v",
    "--verbose",
    "--cov=.",
    "--cov-report=term-missing",
    "--cov-report=html",
    "tests/",
    "tests/test_task_lifecycle.py",
    "tests/test_task_poller.py",
    "tests/test_locust_runner.py",
}


def validate_command(command):
    """Validate that the command is safe to execute.

    Args:
        command (list): Command to validate

    Returns:
        bool: True if command is safe, False otherwise

    Raises:
        ValueError: If command contains unsafe elements
    """
    if not command or len(command) < 2:
        raise ValueError("Command must have at least 2 elements")

    # Check if the base command is allowed
    base_cmd = command[0]
    if base_cmd not in ALLOWED_COMMANDS:
        raise ValueError(f"Command '{base_cmd}' is not in allowed commands list")

    # Check if the command structure matches expected pattern
    expected_start = ALLOWED_COMMANDS[base_cmd]
    if command[1 : 1 + len(expected_start)] != expected_start:
        raise ValueError(
            f"Command structure doesn't match expected pattern for '{base_cmd}'"
        )

    # Validate all arguments are in allowed set
    for arg in command[1 + len(expected_start) :]:
        if not any(
            arg.startswith(allowed) or arg == allowed for allowed in ALLOWED_PYTEST_ARGS
        ):
            raise ValueError(f"Argument '{arg}' is not in allowed arguments list")

    return True


def run_command(command, description=""):
    """Execute a shell command and handle output.

    Args:
        command (list): Command to execute as a list of strings
        description (str): Optional description of what the command does

    Returns:
        bool: True if command executed successfully, False otherwise
    """
    print(f"\n{'='*60}")
    if description:
        print(f"Running: {description}")
    print(f"Command: {' '.join(command)}")
    print(f"{'='*60}")

    try:
        # Security: Validate command before execution
        validate_command(command)

        # nosec B603 - command is validated against whitelist above
        result = subprocess.run(
            command, capture_output=True, text=True, check=False
        )  # nosec

        # Print output
        if result.stdout:
            print(result.stdout)

        if result.stderr:
            print("STDERR:", result.stderr)

        return result.returncode == 0

    except ValueError as e:
        print(f"Security validation failed: {e}")
        return False
    except Exception as e:
        print(f"Error executing command: {e}")
        return False


def main():
    """Main function to parse arguments and run tests.

    Returns:
        int: Exit code (0 for success, 1 for failure)
    """
    parser = argparse.ArgumentParser(
        description="Test runner for performance testing engine service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_tests.py                    # Run all tests
  python run_tests.py --task-lifecycle  # Run task lifecycle tests only
  python run_tests.py --coverage        # Run with coverage report
  python run_tests.py --html --coverage # Generate HTML coverage report
        """,
    )

    # Test selection options
    parser.add_argument(
        "--task-lifecycle", action="store_true", help="Run task lifecycle tests only"
    )

    parser.add_argument(
        "--task-poller", action="store_true", help="Run task poller tests only"
    )

    parser.add_argument(
        "--locust-runner", action="store_true", help="Run locust runner tests only"
    )

    # Output options
    parser.add_argument(
        "--coverage", action="store_true", help="Generate coverage report"
    )

    parser.add_argument(
        "--html", action="store_true", help="Generate HTML format coverage report"
    )

    parser.add_argument("--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Check if tests directory exists
    tests_dir = Path("tests")
    if not tests_dir.exists():
        print(f"Error: Tests directory '{tests_dir}' not found!")
        print("Please run this script from the st_engine directory.")
        return 1

    # Build pytest command
    cmd = ["python", "-m", "pytest"]

    # Determine which tests to run
    if args.task_lifecycle:
        cmd.append("tests/test_task_lifecycle.py")
        test_description = "Task Lifecycle Tests"
    elif args.task_poller:
        cmd.append("tests/test_task_poller.py")
        test_description = "Task Poller Tests"
    elif args.locust_runner:
        cmd.append("tests/test_locust_runner.py")
        test_description = "Locust Runner Tests"
    else:
        cmd.append("tests/")
        test_description = "All Tests"

    # Add verbose flag
    if args.verbose:
        cmd.append("-v")
    else:
        cmd.append("-v")  # Always use verbose for better output

    # Add coverage options
    if args.coverage:
        cmd.extend(["--cov=.", "--cov-report=term-missing"])
        if args.html:
            cmd.append("--cov-report=html")

    # Run the tests
    print(f"Starting test execution for: {test_description}")
    success = run_command(cmd, f"Running {test_description}")

    if success:
        print(f"\n✅ All tests passed successfully!")
        if args.coverage and args.html:
            print("📊 HTML coverage report generated in 'htmlcov/' directory")
    else:
        print(f"\n❌ Some tests failed!")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
