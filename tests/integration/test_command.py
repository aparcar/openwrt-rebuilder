"""Integration tests for command execution."""

from pathlib import Path

import pytest

from rebuilder.core.command import CommandError, CommandRunner, run_command


class TestCommandRunner:
    """Integration tests for CommandRunner."""

    def test_run_simple_command(self, tmp_path: Path):
        """Test running a simple command."""
        runner = CommandRunner(cwd=tmp_path)
        result = runner.run(["echo", "hello"], capture=True)
        assert result.returncode == 0
        assert result.stdout.strip() == "hello"

    def test_run_with_env(self, tmp_path: Path):
        """Test running command with environment variables."""
        runner = CommandRunner(cwd=tmp_path, env={"TEST_VAR": "test_value"})
        result = runner.run(["sh", "-c", "echo $TEST_VAR"], capture=True)
        assert result.stdout.strip() == "test_value"

    def test_run_in_directory(self, tmp_path: Path):
        """Test running command in specific directory."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        runner = CommandRunner(cwd=subdir)
        result = runner.run(["pwd"], capture=True)
        assert result.stdout.strip() == str(subdir)

    def test_run_failing_command(self, tmp_path: Path):
        """Test that failing command raises error."""
        runner = CommandRunner(cwd=tmp_path)
        with pytest.raises(CommandError) as exc_info:
            runner.run(["false"])
        assert exc_info.value.returncode == 1

    def test_run_failing_command_ignored(self, tmp_path: Path):
        """Test that failing command can be ignored."""
        runner = CommandRunner(cwd=tmp_path)
        result = runner.run(["false"], ignore_errors=True)
        assert result.returncode == 1

    def test_run_with_shell(self, tmp_path: Path):
        """Test running command with shell."""
        runner = CommandRunner(cwd=tmp_path)
        result = runner.run("echo hello && echo world", shell=True, capture=True)
        assert "hello" in result.stdout
        assert "world" in result.stdout

    def test_run_with_input(self, tmp_path: Path):
        """Test running command with input."""
        runner = CommandRunner(cwd=tmp_path)
        result = runner.run(["cat"], capture=True, input_data="test input")
        assert result.stdout == "test input"


class TestRunCommandFunction:
    """Tests for the run_command convenience function."""

    def test_simple_command(self, tmp_path: Path):
        """Test running a simple command."""
        result = run_command(["echo", "test"], cwd=tmp_path, capture=True)
        assert result.stdout.strip() == "test"

    def test_with_env(self, tmp_path: Path):
        """Test running with environment variables."""
        result = run_command(
            ["sh", "-c", "echo $MY_VAR"],
            cwd=tmp_path,
            capture=True,
            env={"MY_VAR": "hello"},
        )
        assert result.stdout.strip() == "hello"
