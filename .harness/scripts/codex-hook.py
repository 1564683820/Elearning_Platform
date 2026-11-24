"""Codex project hooks. Keep checks local, read-only, and scoped to the turn."""

import ast
import hashlib
from importlib.util import resolve_name
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
CONTEXT = (
    "Elearning: use AGENTS.md → .harness/AGENTS.md for task routing. "
    "For code changes, read .harness/rules/architecture.md and .harness/rules/verification.md. "
    "Run the relevant Task checks before delivery."
)
MIGRATION_ROOTS = (
    "server/database/alembic/versions/",
    "server/database/alembic_agent/versions/",
)


def git(*args, check=True):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, check=check, timeout=4
    )


def snapshot():
    """Capture Git-visible paths and lightweight working-tree fingerprints."""
    records = git(
        "--no-optional-locks", "status", "--porcelain=v1", "-z",
        "--untracked-files=all", "--no-renames",
    ).stdout
    files = {}
    for record in records.split(b"\0"):
        if not record:
            continue
        path = os.fsdecode(record[3:])
        try:
            info = (ROOT / path).lstat()
            stamp = [info.st_mtime_ns, info.st_size]
        except FileNotFoundError:
            stamp = []
        files[path] = [record[:2].decode("ascii"), *stamp]
    return files


def state_file(event):
    # Keep at most one baseline per worktree and session.
    key = json.dumps([str(ROOT), event["session_id"]])
    digest = hashlib.sha256(key.encode()).hexdigest()
    return Path(tempfile.gettempdir()) / f"elearning-hook-{digest}.json"


def check_python(relative):
    path = ROOT / relative
    if not path.is_file() or not path.resolve().is_relative_to(ROOT):
        return []
    try:
        tree = ast.parse(path.read_bytes())
    except SyntaxError as error:
        return [f"{relative}:{error.lineno}: invalid Python syntax."]

    if not relative.startswith("server/app/services/"):
        return []
    package = ".".join(PurePosixPath(relative).parts[1:-1])
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports = [name.name for name in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                try:
                    module = resolve_name("." * node.level + module, package)
                except ImportError:
                    continue
            imports = [module, *(f"{module}.{name.name}" for name in node.names)]
        else:
            continue
        if any(name == layer or name.startswith(f"{layer}.")
               for name in imports for layer in ("app.api", "app.routers")):
            return [f"{relative}:{node.lineno}: services must not import HTTP routers."]
    return []


def check_changes(before, after):
    issues = []
    for relative in sorted(after):
        status = after[relative][0]
        if before.get(relative) == after[relative]:
            continue
        path = PurePosixPath(relative)
        if status[0] in "AMT" and (
            path.name == "project.private.config.json"
            or path.name == ".env"
            or (path.name.startswith(".env.") and path.name != ".env.example")
        ):
            issues.append(f"{relative}: local configuration is staged. Review the staging area.")
        elif (status[0] != "D" and (ROOT / relative).exists()
              and (relative.startswith("client/dist/") or "node_modules" in path.parts
                   or "__pycache__" in path.parts or path.name.endswith(".tsbuildinfo"))):
            issues.append(f"{relative}: generated path is visible to Git. Review the diff.")
        elif relative.startswith(MIGRATION_ROOTS) and git(
            "cat-file", "-e", f"HEAD:{relative}", check=False
        ).returncode == 0:
            issues.append(f"{relative}: an existing migration changed. Review the migration policy.")
        elif relative.startswith("server/app/") and relative.endswith(".py"):
            issues.extend(check_python(relative))
    return issues


def run(event):
    kind = event.get("hook_event_name")
    if kind not in {"UserPromptSubmit", "Stop"} or event.get("agent_id"):
        return {}
    if not event.get("session_id") or not event.get("turn_id"):
        return {"systemMessage": "Elearning hook skipped: missing session or turn ID."}

    state = state_file(event)
    baseline = json.loads(state.read_text(encoding="utf-8")) if state.is_file() else {}
    if kind == "UserPromptSubmit":
        # A continuation may re-enter this hook with the same turn ID.
        if baseline.get("turn_id") != event["turn_id"]:
            state.write_text(json.dumps({
                "turn_id": event["turn_id"], "files": snapshot(),
            }), encoding="utf-8")
        return {"hookSpecificOutput": {"hookEventName": kind, "additionalContext": CONTEXT}}

    if baseline.get("turn_id") != event["turn_id"]:
        return {"systemMessage": "Elearning hook skipped: turn baseline unavailable."}
    issues = check_changes(baseline["files"], snapshot())
    if issues:
        message = "Elearning turn check:\n" + "\n".join(issues[:5])
        if len(issues) > 5:
            message += f"\n{len(issues) - 5} more. Inspect the Git diff."
        if not event.get("stop_hook_active"):
            return {"decision": "block", "reason": (
                message + "\nReview only this turn's changes. Preserve unrelated user edits."
            )}
        state.unlink(missing_ok=True)
        return {"systemMessage": message}
    state.unlink(missing_ok=True)
    return {}


if __name__ == "__main__":
    try:
        result = run(json.load(sys.stdin.buffer))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        result = {"systemMessage": f"Elearning hook could not check this turn ({type(error).__name__})."}
    print(json.dumps(result))
