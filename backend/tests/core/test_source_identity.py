"""
The source identity: the one account of what a process loaded that is not an inference.

These pin what would make GET /health's `source` lie or make the API fail to start: a digest that
depends on the walk order, counts files that are not application source, or cannot tell an empty
file from a missing one; a commit read from the wrong place in a worktree; a start-up that raises
because git is missing, slow or cannot be asked.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core import source_identity as si

needs_git = pytest.mark.skipif(not shutil.which("git"), reason="needs git")
SHA_A = "a" * 40
SHA_B = "b" * 40


def write(root: Path, relative: str, content: bytes = b"") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


# ================================================================================ the digest
def test_the_digest_is_the_documented_one(tmp_path):
    """The module docstring's algorithm, spelled out as one byte string: path, NUL, bytes, NUL, in
    POSIX path order, over *.py outside __pycache__ and nothing else."""
    write(tmp_path, "main.py", b"app = 1\n")
    write(tmp_path, "services/slips.py")
    write(tmp_path, "__pycache__/main.cpython-311.pyc", b"\x00compiled")
    write(tmp_path, "services/__pycache__/stale.py", b"a source file under __pycache__ is skipped")
    write(tmp_path, "notes.txt", b"not source")
    write(tmp_path, "services/data.json", b"{}")
    expected = hashlib.sha256(b"main.py\0app = 1\n\0services/slips.py\0\0").hexdigest()
    assert si.app_tree_digest(tmp_path) == (expected, 2)


def test_the_digest_follows_path_order_not_walk_order(tmp_path):
    """"a.py" sorts before "a/c.py" as a string ("." before "/"), whatever order the walk visits."""
    write(tmp_path, "b.py", b"B")
    write(tmp_path, "a/c.py", b"C")
    write(tmp_path, "a.py", b"A")
    expected = hashlib.sha256(b"a.py\0A\0a/c.py\0C\0b.py\0B\0").hexdigest()
    assert si.app_tree_digest(tmp_path) == (expected, 3)


def test_a_moved_file_and_an_empty_file_each_change_the_digest(tmp_path):
    write(tmp_path, "main.py", b"app = 1\n")
    before, _ = si.app_tree_digest(tmp_path)
    write(tmp_path, "empty.py")
    with_empty, count = si.app_tree_digest(tmp_path)
    assert with_empty != before and count == 2
    (tmp_path / "empty.py").rename(tmp_path / "moved.py")
    assert si.app_tree_digest(tmp_path)[0] not in (before, with_empty)


def test_a_file_that_cannot_be_read_fails_the_digest_rather_than_shortening_it(tmp_path, monkeypatch):
    write(tmp_path, "main.py", b"app = 1\n")
    write(tmp_path, "gone.py", b"removed between the walk and the read")
    original = Path.read_bytes

    def read_bytes(self):
        if self.name == "gone.py":
            raise FileNotFoundError(str(self))
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    with pytest.raises(OSError):
        si.app_tree_digest(tmp_path)


def test_the_digest_covers_the_real_application_tree():
    digest, count = si.app_tree_digest()
    assert len(digest) == 64 and int(digest, 16) >= 0
    sources = [p for p in si.APP_DIR.rglob("*.py") if "__pycache__" not in p.parts]
    assert count == len(sources) and Path(si.__file__) in sources


# ================================================================================== the commit
def fake_checkout(root: Path, head: str, branch: str = "main", loose: str = None, packed: str = None) -> Path:
    git_dir = root / ".git"
    write(git_dir, "HEAD", head.encode())
    if loose is not None:
        write(git_dir, f"refs/heads/{branch}", (loose + "\n").encode())
    if packed is not None:
        write(git_dir, "packed-refs", f"# pack-refs with: peeled fully-peeled sorted\n{packed} refs/heads/{branch}\n"
                                      f"^{'c' * 40}\n".encode())
    return root


def test_head_by_hand_reads_a_loose_ref(tmp_path):
    fake_checkout(tmp_path, "ref: refs/heads/main\n", loose=SHA_A)
    assert si.head_by_hand(tmp_path) == SHA_A


def test_head_by_hand_reads_packed_refs_when_the_ref_is_not_loose(tmp_path):
    fake_checkout(tmp_path, "ref: refs/heads/main\n", packed=SHA_B)
    assert si.head_by_hand(tmp_path) == SHA_B


def test_a_loose_ref_wins_over_a_stale_packed_one(tmp_path):
    fake_checkout(tmp_path, "ref: refs/heads/main\n", loose=SHA_A, packed=SHA_B)
    assert si.head_by_hand(tmp_path) == SHA_A


def test_head_by_hand_reads_a_detached_head(tmp_path):
    fake_checkout(tmp_path, SHA_B + "\n")
    assert si.head_by_hand(tmp_path) == SHA_B


def test_head_by_hand_follows_a_worktrees_gitdir_file_to_the_common_refs(tmp_path):
    """A worktree's .git is a file naming its git directory, whose HEAD names a branch whose ref
    lives in the main checkout's .git (the `commondir` pointer), loose or packed."""
    main = fake_checkout(tmp_path / "main", "ref: refs/heads/main\n", loose=SHA_A, packed=SHA_B)
    write(main / ".git", "worktrees/feature/HEAD", b"ref: refs/heads/feature\n")
    write(main / ".git", "worktrees/feature/commondir", b"../..\n")
    write(main / ".git", "refs/heads/feature", (SHA_B + "\n").encode())
    worktree = tmp_path / "worktrees" / "feature"
    write(worktree, ".git", f"gitdir: {main / '.git' / 'worktrees' / 'feature'}\n".encode())
    assert si.head_by_hand(worktree) == SHA_B
    assert si.repository_root(worktree / "backend" / "app") == worktree


@pytest.mark.parametrize("head", ["ref: refs/heads/nowhere\n", "not a sha\n", ""])
def test_an_unreadable_head_is_none_not_a_guess(tmp_path, head):
    fake_checkout(tmp_path, head, loose=None)
    assert si.head_by_hand(tmp_path) is None


def test_outside_any_repository_there_is_no_root_and_no_commit(tmp_path):
    write(tmp_path, "backend/app/main.py", b"app = 1\n")
    assert si.repository_root(tmp_path / "backend" / "app") is None
    identity = si.compute_identity(tmp_path / "backend" / "app")
    assert identity["commit"] is None and identity["commit_dirty_app_files"] is None
    assert identity["app_files"] == 1


@needs_git
def test_the_commit_by_hand_agrees_with_git_on_this_repository():
    root = si.repository_root()
    assert root is not None
    by_git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
    assert si.head_by_hand(root) == by_git
    assert si.git_head(root) == by_git


@needs_git
def test_the_dirty_list_names_what_differs_from_head_under_the_application_tree(tmp_path):
    def git(*args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false",
                        *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    app = tmp_path / "backend" / "app"
    write(app, "main.py", b"app = 1\n")
    write(tmp_path, "README.md", b"readme\n")
    git("add", "-A")
    git("commit", "-q", "-m", "first")
    assert si.dirty_app_files(tmp_path, app) == []

    write(app, "main.py", b"app = 2\n")
    write(app, "services/new.py", b"")
    write(tmp_path, "README.md", b"changed outside the application tree\n")
    assert si.dirty_app_files(tmp_path, app) == ["backend/app/main.py", "backend/app/services/new.py"]

    identity = si.compute_identity(app, repo_root=tmp_path)
    assert identity["commit"] == si.head_by_hand(tmp_path) and len(identity["commit"]) == 40
    assert identity["commit_dirty_app_files"] == ["backend/app/main.py", "backend/app/services/new.py"]
    assert identity["app_tree_sha256"] == si.app_tree_digest(app)[0] and identity["app_files"] == 2


def test_an_application_tree_outside_the_repository_has_no_dirty_list(tmp_path):
    fake_checkout(tmp_path / "repo", "ref: refs/heads/main\n", loose=SHA_A)
    assert si.dirty_app_files(tmp_path / "repo", tmp_path / "elsewhere") is None


# ============================================================================== the identity
@pytest.mark.parametrize("failure", [OSError("git: command not found"),
                                     subprocess.TimeoutExpired(["git"], si.GIT_TIMEOUT_SECONDS)])
def test_git_failing_or_hanging_leaves_the_commit_unknown_and_the_digest_intact(tmp_path, monkeypatch, failure):
    def run(*args, **kwargs):
        raise failure

    monkeypatch.setattr(si.subprocess, "run", run)
    write(tmp_path, "backend/app/main.py", b"app = 1\n")
    fake_checkout(tmp_path, "ref: refs/heads/main\n", loose=SHA_A)
    identity = si.compute_identity(tmp_path / "backend" / "app")
    assert identity["commit"] == SHA_A              # read by hand when git cannot be asked
    assert identity["commit_dirty_app_files"] is None   # which only git can say
    assert identity["app_tree_sha256"] == si.app_tree_digest(tmp_path / "backend" / "app")[0]


def test_a_tree_that_cannot_be_digested_does_not_fail_start_up(tmp_path, monkeypatch):
    def digest(app_dir):
        raise FileNotFoundError("gone")

    monkeypatch.setattr(si, "app_tree_digest", digest)
    identity = si.compute_identity(tmp_path)
    assert identity["app_tree_sha256"] is None and identity["app_files"] == 0
    assert identity["started_at"]


def test_the_start_instant_is_utc_to_the_second():
    """A clock four hours west of Greenwich reads 22:53:40.123456: recorded as 02:53:40Z next day."""
    clock = lambda: datetime(2026, 10, 7, 22, 53, 40, 123456, tzinfo=timezone(timedelta(hours=-4)))
    identity = si.compute_identity(si.APP_DIR, clock=clock)
    assert identity["started_at"] == "2026-10-08T02:53:40Z"


def test_the_identity_is_recorded_once_and_handed_out_as_copies():
    first = si.source_identity()
    assert set(first) == {"commit", "commit_dirty_app_files", "app_tree_sha256", "app_files", "started_at"}
    first["commit"] = "tampered"
    if first["commit_dirty_app_files"] is not None:
        first["commit_dirty_app_files"].append("tampered")
    second = si.source_identity()
    assert second["commit"] != "tampered" and "tampered" not in (second["commit_dirty_app_files"] or [])
    assert second == si.source_identity()


def test_the_identity_describes_this_checkout():
    identity = si.source_identity()
    assert identity["app_tree_sha256"] and len(identity["app_tree_sha256"]) == 64 and identity["app_files"] > 1
    dirty = identity["commit_dirty_app_files"]
    assert dirty is None or all(os.sep not in p[:1] and p.startswith("backend/app/") for p in dirty)
