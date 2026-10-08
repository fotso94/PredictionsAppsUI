"""
What code this process loaded, recorded once when it started and published by GET /health.

WHY THIS EXISTS
    The backend runs without --reload, so it serves the application tree as it stood when the
    process started, while other sessions keep editing and committing in the same checkout. The two
    tools that judge evidence against "the running code" - backend/scripts/prove_journey.py and
    scripts/test_evidence.py - could only INFER what that was, from the process start time laid
    beside file modification times, and said so. A modification time cannot show an edit made and
    undone before the start, nor an earlier edit to a file that was changed again later. The
    process itself is the one thing that can say what it loaded, so it says so here: the tree it
    loaded, digested, and the commit it stood on.

WHAT IS RECORDED
    commit                  the git HEAD sha of the repository this package lives in, or None
    commit_dirty_app_files  the paths under backend/app that differed from that commit when the
                            process started, per `git status --porcelain --untracked-files=all`
                            (paths only, relative to the repository root); None when git could not
                            answer. An empty list says the tree loaded IS the commit's
    app_tree_sha256         a digest of the application source actually on disk at the start
    app_files               how many files the digest covers
    started_at              the UTC instant the identity was computed, to the second

    It is computed ONCE, at import, which for uvicorn is the process start. Every probe is
    best-effort: git may be missing, slow, or holding a lock for a sibling session, and none of
    that may keep the API from starting, so each probe answers None when it cannot answer and
    nothing in this module raises. `source_identity()` hands out a copy; the record itself is
    never handed out.

THE DIGEST
    Two other tools reimplement it with the standard library, so that they measure the checkout
    independently of the code being measured. Word for word:

    Walk backend/app recursively, skipping any directory named __pycache__. Take every file whose
    name ends in .py. Sort their paths relative to backend/app as POSIX strings. For each path in
    that order, feed sha256 with path.encode("utf-8"), then b"\\0", then the file's bytes, then
    b"\\0". The digest is the hex sha256.

    The path is part of the digest, so a file renamed or moved changes it; the separators keep an
    empty file apart from a missing one, and a file's bytes apart from the next path.
"""

from __future__ import annotations

import copy
import hashlib
import logging
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

#: backend/app: the tree this module is part of.
APP_DIR = Path(__file__).resolve().parent.parent
#: Read-only git, invisible to sibling sessions: without GIT_OPTIONAL_LOCKS=0 a `status` refreshes
#: the index and can briefly hold index.lock, which makes a concurrent commit fail.
GIT_ENV = {"LC_ALL": "C", "GIT_OPTIONAL_LOCKS": "0"}
GIT_TIMEOUT_SECONDS = 5.0
_SHA = re.compile(r"[0-9a-f]{40,64}")


# ================================================================================ the digest
def app_tree_digest(app_dir: Path = APP_DIR) -> Tuple[str, int]:
    """(hex sha256, files digested) over the application source under `app_dir`, by the algorithm
    the module docstring states. Raises OSError when a file cannot be read: a digest over part of
    the tree would look exactly like a digest over all of it."""
    root = Path(app_dir)
    relative: List[str] = []
    for folder, folders, files in os.walk(root):
        folders[:] = [name for name in folders if name != "__pycache__"]
        relative.extend(Path(folder, name).relative_to(root).as_posix() for name in files if name.endswith(".py"))
    digest = hashlib.sha256()
    for path in sorted(relative):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update((root / path).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest(), len(relative)


# ================================================================================== the commit
def repository_root(start: Path = APP_DIR) -> Optional[Path]:
    """The nearest directory at or above `start` holding a `.git`: a directory in a checkout, a
    file (`gitdir: ...`) in a worktree. None outside any repository."""
    for candidate in (Path(start), *Path(start).parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _git(args: List[str], cwd: Path) -> Optional[str]:
    """stdout of a short git command, or None: not installed, failed, or over the timeout."""
    try:
        done = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                              timeout=GIT_TIMEOUT_SECONDS, env={**os.environ, **GIT_ENV})
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return done.stdout if done.returncode == 0 else None


def _read(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def head_by_hand(repo_root: Path) -> Optional[str]:
    """HEAD read from the repository's own files, for when git itself cannot be asked.

    `.git` is a directory in a checkout and a file naming the git directory in a worktree, whose
    branch refs live in the COMMON directory that its `commondir` file names. A branch's sha is a
    loose file under refs/ or a line of packed-refs; a detached HEAD is the sha itself.
    """
    dot_git = Path(repo_root) / ".git"
    if dot_git.is_file():
        pointer = (_read(dot_git) or "").strip()
        if not pointer.startswith("gitdir:"):
            return None
        git_dir = Path(pointer[len("gitdir:"):].strip())
        if not git_dir.is_absolute():
            git_dir = Path(os.path.normpath(Path(repo_root) / git_dir))
    elif dot_git.is_dir():
        git_dir = dot_git
    else:
        return None
    common = git_dir
    common_pointer = (_read(git_dir / "commondir") or "").strip()
    if common_pointer:
        common = Path(common_pointer) if os.path.isabs(common_pointer) else Path(os.path.normpath(git_dir / common_pointer))
    head = (_read(git_dir / "HEAD") or "").strip()
    if not head.startswith("ref:"):
        return head if _SHA.fullmatch(head) else None
    ref = head[len("ref:"):].strip()
    loose = (_read(common.joinpath(*ref.split("/"))) or "").strip()
    if _SHA.fullmatch(loose):
        return loose
    for line in (_read(common / "packed-refs") or "").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == ref and _SHA.fullmatch(parts[0]):
            return parts[0]
    return None


def git_head(repo_root: Path) -> Optional[str]:
    """`git rev-parse HEAD`, or the same answer read by hand when git could not give it."""
    answer = (_git(["rev-parse", "HEAD"], repo_root) or "").strip()
    return answer if _SHA.fullmatch(answer) else head_by_hand(repo_root)


def dirty_app_files(repo_root: Path, app_dir: Path = APP_DIR) -> Optional[List[str]]:
    """The paths under `app_dir` that differ from HEAD, modified and untracked alike, relative to
    the repository root; None when git could not say (which is not the same as none)."""
    try:
        pathspec = Path(app_dir).resolve().relative_to(Path(repo_root).resolve()).as_posix()
    except ValueError:
        return None
    out = _git(["status", "--porcelain", "--untracked-files=all", "--", pathspec], repo_root)
    if out is None:
        return None
    # "XY path", or "XY old -> new" for a rename: the path that exists now is the last one.
    return sorted(line[3:].split(" -> ")[-1].strip('"') for line in out.splitlines() if line.strip())


# ============================================================================== the identity
def compute_identity(app_dir: Path = APP_DIR, repo_root: Optional[Path] = None,
                     clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> Dict[str, Any]:
    """The identity as a plain dict. Each probe answers None rather than raising."""
    started = clock().astimezone(timezone.utc).replace(microsecond=0)
    identity: Dict[str, Any] = {"commit": None, "commit_dirty_app_files": None, "app_tree_sha256": None,
                                "app_files": 0, "started_at": started.isoformat().replace("+00:00", "Z")}
    try:
        identity["app_tree_sha256"], identity["app_files"] = app_tree_digest(app_dir)
    except Exception as exc:  # a file that vanished mid-walk; other sessions share this tree
        logger.warning(f"Source identity: the application tree could not be digested ({type(exc).__name__})")
    try:
        root = repo_root or repository_root(app_dir)
        if root is not None:
            identity["commit"] = git_head(root)
            identity["commit_dirty_app_files"] = dirty_app_files(root, app_dir)
    except Exception as exc:  # pragma: no cover - every probe already answers None on its own
        logger.warning(f"Source identity: the commit could not be read ({type(exc).__name__})")
    return identity


_IDENTITY = compute_identity()


def source_identity() -> Dict[str, Any]:
    """A copy of what this process recorded when it started."""
    return copy.deepcopy(_IDENTITY)
