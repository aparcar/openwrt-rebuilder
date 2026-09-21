"""Command execution utilities."""

import logging
import os
import re
import sys
import textwrap
import time
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from subprocess import PIPE, STDOUT, CompletedProcess, Popen, TimeoutExpired, run

logger = logging.getLogger(__name__)

TAIL_LINES = 500
"""Output lines kept from a streamed command, to explain a failure with."""

SUMMARY_LINES = 15
"""Most lines quoted back when a command fails."""

_ERROR_LINE = re.compile(
    r"""
      \*\*\*                            # make: *** [toplevel.mk:226: ...] Error 2
    | ^\s*ERROR:                        # OpenWrt: "   ERROR: package/x failed to build."
    | ^configure:\ error:
    | (?:^|\s)(?:fatal\ error|error):\s # compiler / linker diagnostics
    | ^[^:]*:\ command\ not\ found
    """,
    re.VERBOSE,
)


def summarize_output(output: str) -> list[str]:
    """Pick the lines of a failed command's output that explain the failure.

    A failing ``make -j80 V=s`` produces megabytes of output whose last lines are
    usually unrelated bookkeeping, so prefer the explicit error lines (make's
    ``***`` lines, ``ERROR:``, compiler diagnostics) and fall back to the tail
    only when the command failed without saying anything recognisable.
    """
    lines = [line.rstrip() for line in output.splitlines() if line.strip()]
    errors = [line for line in lines if _ERROR_LINE.search(line)]
    return (errors or lines)[-SUMMARY_LINES:]


def format_command(cmd: Sequence[str] | str) -> str:
    """Render a command the way it would be typed, not as a Python list."""
    if isinstance(cmd, str):
        return cmd
    return " ".join(str(c) for c in cmd)


class CommandError(Exception):
    """Raised when a command fails.

    Carries whatever output was seen so the message can quote the actual error
    instead of just an exit code.
    """

    def __init__(
        self,
        cmd: Sequence[str] | str,
        returncode: int,
        stderr: str = "",
        output: str = "",
    ):
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr
        self.output = output or stderr
        super().__init__(self._message())

    def _message(self) -> str:
        # shorten(): a shell snippet can be several lines long, and the header
        # has to stay one readable line.
        cmd = textwrap.shorten(format_command(self.cmd), width=200, placeholder=" [...]")
        header = f"{cmd} exited with code {self.returncode}"
        summary = summarize_output(self.output)
        if not summary:
            return header
        return "\n".join([header, *(f"  {line}" for line in summary)])


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
        tee: bool = False,
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
            tee: Stream output to stdout while keeping its tail for the error
                message. Use for long builds whose output should stay visible.
                Mutually exclusive with ``capture``; ``stdout``/``stderr`` on the
                result are ``None`` because the output went to the terminal.
            ignore_errors: If False, raise CommandError on non-zero exit.
            shell: Run command through the shell.
            input_data: Data to send to stdin (not supported with tee).
            cwd: Working directory (overrides instance default).
            env: Additional environment variables (merged with instance env).
            timeout: Command timeout in seconds (overrides instance default).

        Returns:
            CompletedProcess with the result.

        Raises:
            CommandError: If command fails and ignore_errors is False.
        """
        if tee and capture:
            raise ValueError("tee and capture are mutually exclusive")
        if tee and input_data is not None:
            raise ValueError("input_data is not supported with tee")

        work_dir = cwd or self.cwd
        cmd_str = format_command(cmd)
        logger.debug(f"Running: {cmd_str} in {work_dir}")

        # Merge environment
        current_env = os.environ.copy()
        current_env.update(self.env)
        if env:
            current_env.update(env)

        if tee:
            proc, tail = self._run_tee(
                cmd,
                cwd=work_dir,
                env=current_env,
                shell=shell,
                timeout=timeout or self.timeout,
            )
        else:
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
            tail = "\n".join(filter(None, (proc.stdout, proc.stderr)))

        if proc.returncode and not ignore_errors:
            # No logging here: the exception message carries the command, the
            # exit code and the error lines, and the caller decides how loud a
            # failure is.
            cmd_list: Sequence[str] = list(cmd) if not isinstance(cmd, str) else cmd
            raise CommandError(
                cmd_list,
                proc.returncode,
                proc.stderr if capture else "",
                tail,
            )

        if capture and proc.stderr:
            logger.debug(f"stderr: {proc.stderr}")

        return proc

    def _run_tee(
        self,
        cmd: Sequence[str] | str,
        *,
        cwd: Path,
        env: dict[str, str],
        shell: bool,
        timeout: int | None,
    ) -> tuple[CompletedProcess[str], str]:
        """Run a command, echoing its output while retaining the last lines."""
        kept: deque[str] = deque(maxlen=TAIL_LINES)
        deadline = time.monotonic() + timeout if timeout else None

        # stderr is merged into stdout so make's error lines stay interleaved
        # with the step they belong to.
        with Popen(
            cmd,
            cwd=cwd,
            env=env,
            shell=shell,
            stdout=PIPE,
            stderr=STDOUT,
            text=True,
            bufsize=1,
            umask=0o22,
        ) as proc:
            assert proc.stdout is not None
            for line in proc.stdout:
                sys.stdout.write(line)
                kept.append(line.rstrip("\n"))
                if deadline and time.monotonic() > deadline:
                    proc.kill()
                    raise TimeoutExpired(cmd, timeout or 0, output="\n".join(kept))
            sys.stdout.flush()
            returncode = proc.wait()

        completed: CompletedProcess[str] = CompletedProcess(
            args=cmd, returncode=returncode, stdout=None, stderr=None
        )
        return completed, "\n".join(kept)


def run_command(
    cmd: Sequence[str] | str,
    cwd: Path | str = ".",
    *,
    capture: bool = False,
    tee: bool = False,
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
        tee=tee,
        ignore_errors=ignore_errors,
        shell=shell,
        input_data=input_data,
    )
