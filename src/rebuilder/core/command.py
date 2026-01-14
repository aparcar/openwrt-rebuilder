"""Command execution utilities."""

import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from subprocess import CompletedProcess, run

logger = logging.getLogger(__name__)


class CommandError(Exception):
    """Raised when a command fails."""

    def __init__(self, cmd: Sequence[str], returncode: int, stderr: str = ""):
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"Command {cmd} failed with code {returncode}: {stderr}")


@dataclass
class CommandRunner:
    """Executes shell commands with consistent configuration."""

    cwd: Path = field(default_factory=Path.cwd)
    env: dict[str, str] = field(default_factory=dict)
    timeout: int | None = None

    def run(
        self,
        cmd: Sequence[str] | str,
        *,
        capture: bool = False,
        ignore_errors: bool = False,
        shell: bool = False,
        input_data: str | None = None,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> CompletedProcess[str]:
        """Run a command.

        Args:
            cmd: Command to run (list of args or string if shell=True).
            capture: Whether to capture stdout/stderr.
            ignore_errors: If False, raise CommandError on non-zero exit.
            shell: Run command through the shell.
            input_data: Data to send to stdin.
            cwd: Working directory (overrides instance default).
            env: Additional environment variables (merged with instance env).
            timeout: Command timeout in seconds (overrides instance default).

        Returns:
            CompletedProcess with the result.

        Raises:
            CommandError: If command fails and ignore_errors is False.
        """
        work_dir = cwd or self.cwd
        cmd_str = cmd if isinstance(cmd, str) else " ".join(str(c) for c in cmd)
        logger.info(f"Running: {cmd_str} in {work_dir}")

        # Merge environment
        current_env = os.environ.copy()
        current_env.update(self.env)
        if env:
            current_env.update(env)

        proc = run(
            cmd,
            cwd=work_dir,
            capture_output=capture,
            text=True,
            env=current_env,
            timeout=timeout or self.timeout,
            shell=shell,
            input=input_data,
            umask=0o22,
        )

        if proc.returncode and not ignore_errors:
            logger.error(f"Command failed: {cmd_str}")
            if capture and proc.stderr:
                logger.error(f"stderr: {proc.stderr}")
            raise CommandError(
                cmd if isinstance(cmd, list) else [cmd],
                proc.returncode,
                proc.stderr if capture else "",
            )

        if capture and proc.stderr:
            logger.debug(f"stderr: {proc.stderr}")

        return proc


def run_command(
    cmd: Sequence[str] | str,
    cwd: Path | str = ".",
    *,
    capture: bool = False,
    ignore_errors: bool = False,
    shell: bool = False,
    input_data: str | None = None,
    env: dict[str, str] | None = None,
    timeout: int | None = None,
) -> CompletedProcess[str]:
    """Convenience function to run a command.

    This is a simpler interface for one-off commands.
    For repeated commands with shared configuration, use CommandRunner.
    """
    runner = CommandRunner(cwd=Path(cwd), env=env or {}, timeout=timeout)
    return runner.run(
        cmd,
        capture=capture,
        ignore_errors=ignore_errors,
        shell=shell,
        input_data=input_data,
    )
