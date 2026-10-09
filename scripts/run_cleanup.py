"""Run every final action, preserving an earlier measurement failure."""

from contextlib import contextmanager
import shlex
import sys
from typing import Callable, Iterator


REMOTE_CLEANUP_TIMEOUT = 30


def stop_pidfile_command(pid_path: str, *, process_group: bool = False) -> str:
    """Remove a PID file only after its process/group has no live members.

    Linux ps distinguishes absent/zombie targets from signalling permission
    failures. A failed probe or stop retains the PID file and fails the command.
    """
    path = shlex.quote(pid_path)
    target = "-$pid" if process_group else "$pid"
    term = f"kill -TERM {target}" if process_group else "kill $pid"
    field = "$2" if process_group else "$1"
    return (
        "rt_tester_running() { "
        "table=$(ps -eo pid=,pgid=,stat=) || return 2; "
        f"printf '%s\\n' \"$table\" | awk -v pid=\"$pid\" "
        f"'{field} == pid && $3 !~ /^Z/ {{ found=1 }} END {{ exit !found }}'; "
        "}; "
        "rt_tester_wait() { i=0; while :; do "
        "status=0; rt_tester_running || status=$?; "
        "[ $status -eq 1 ] && return 0; "
        "[ $status -ne 0 ] && return 2; "
        "[ $i -ge 30 ] && return 1; "
        "sleep 0.1; i=$((i + 1)); done; }; "
        "rt_tester_stop() { "
        f"[ -f {path} ] || return 0; "
        f"pid=$(cat {path} 2>/dev/null || true); "
        "case $pid in ''|*[!0-9]*) echo 'invalid stop PID' >&2; return 1;; esac; "
        "[ \"$pid\" -gt 1 ] || { echo 'invalid stop PID' >&2; return 1; }; "
        f"{term} 2>/dev/null || true; "
        "if ! rt_tester_wait; then "
        f"kill -KILL {target} 2>/dev/null || true; "
        "rt_tester_wait || { echo \"could not confirm stop of PID/group $pid\" >&2; return 1; }; "
        "fi; "
        f"rm -f {path}; "
        "}; rt_tester_stop || exit $?; "
    )


@contextmanager
def final_actions(*actions: tuple[str, Callable[[], None]]) -> Iterator[None]:
    """Attempt all actions in order; raise the first failure if the body succeeded.

    An existing exception (including an interrupt) takes precedence. Secondary
    failures are reported to stderr, never substituted for the original error.
    """
    body_failed = False
    try:
        yield
    except BaseException:
        body_failed = True
        raise
    finally:
        first_error = None
        for description, action in actions:
            try:
                action()
            except BaseException as error:
                if first_error is None:
                    first_error = error
                try:
                    print(f"warning: {description} failed: {error}", file=sys.stderr)
                except BaseException:
                    # Reporting must not interrupt the remaining stop actions.
                    pass
        if first_error is not None and not body_failed:
            raise first_error
