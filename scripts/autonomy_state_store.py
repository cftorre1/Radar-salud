"""Conflict-safe, remote-authoritative storage for autonomy control state.

Reducers receive a fresh remote snapshot on *every* attempt. A rejected push
never causes a snapshot to be rebased or force-pushed: the reducer is run again
against the new remote HEAD. Leases, fencing and task transitions belong in the
reducer, so their validation and state mutation share one atomic Git update.

Only explicitly supplied paths below the configured state prefixes can enter
the commit. Git plumbing and a private temporary index avoid staging files from
the caller's checkout. Evidence paths are append-only, including on retries.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import random
import subprocess
import tempfile
import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit


class StateStoreError(RuntimeError):
    """Durable state could not be read or updated safely."""


class UnsafeStatePath(StateStoreError):
    """A reducer attempted to write outside its explicit state boundary."""


class ImmutableEvidenceConflict(StateStoreError):
    """A reducer attempted to replace an already-published evidence record."""


class RetryExhausted(StateStoreError):
    """Remote updates failed after the configured bounded retry budget."""


def _canonical_path(path: str) -> str:
    if not isinstance(path, str) or not path:
        raise UnsafeStatePath("State paths must be nonempty relative strings")
    parts = path.split("/")
    if (path.startswith("/") or "\\" in path
            or any(part in ("", ".", "..") for part in parts)
            or any(ord(char) < 32 or ord(char) == 127 for char in path)):
        raise UnsafeStatePath(f"Invalid state path: {path!r}")
    return path


@dataclass(frozen=True)
class Snapshot:
    """An immutable view of one fetched commit's permitted state files."""

    commit: str
    files: Mapping[str, bytes]

    def read(self, path: str, default: Any = None) -> bytes | Any:
        return self.files.get(_canonical_path(path), default)

    def read_text(self, path: str, default: Any = None) -> str | Any:
        value = self.read(path)
        return default if value is None else value.decode("utf-8")

    def read_json(self, path: str, default: Any = None) -> Any:
        value = self.read(path)
        return default if value is None else json.loads(value)

    def paths(self) -> tuple[str, ...]:
        return tuple(sorted(self.files))


@dataclass(frozen=True)
class Mutation:
    writes: Mapping[str, str | bytes]
    value: Any = None


@dataclass(frozen=True)
class TransactionResult:
    value: Any
    commit: str
    attempts: int
    changed: bool


class GitStateStore:
    def __init__(
        self,
        remote: str | None = None,
        branch: str = "autopilot-state",
        *,
        repository: str | Path = ".",
        allowed_prefixes: tuple[str, ...] = ("data/autopilot/",),
        immutable_prefixes: tuple[str, ...] = ("data/autopilot/evidence/",),
        max_attempts: int = 8,
        initial_backoff: float = 0.05,
        max_backoff: float = 2.0,
        command_timeout: float = 60.0,
        author_name: str = "Alicanto Autonomy",
        author_email: str = "autonomy@alicanto.invalid",
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not isinstance(max_attempts, int) or max_attempts < 1:
            raise ValueError("max_attempts must be a positive integer")
        if initial_backoff < 0 or max_backoff < 0 or command_timeout <= 0:
            raise ValueError("Backoff must be nonnegative and timeout positive")
        if not allowed_prefixes:
            raise ValueError("At least one explicit state prefix is required")
        self.allowed_prefixes = self._prefixes(allowed_prefixes)
        self.immutable_prefixes = self._prefixes(immutable_prefixes)
        self.max_attempts = max_attempts
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.command_timeout = command_timeout
        self.sleep = sleep
        self.branch = branch
        self._secrets: set[str] = set()
        self.environment = os.environ.copy()
        for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
            self.environment.pop(key, None)
        self.environment.update({
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": author_name,
            "GIT_AUTHOR_EMAIL": author_email,
            "GIT_COMMITTER_NAME": author_name,
            "GIT_COMMITTER_EMAIL": author_email,
        })
        self.remote = remote or self._command(
            ["git", "-C", str(repository), "remote", "get-url", "origin"]
        ).stdout.decode().strip()
        if not self.remote or self.remote.startswith("-"):
            raise ValueError("A nonempty remote URL is required")
        self._command(["git", "check-ref-format", f"refs/heads/{branch}"])
        self._inherit_checkout_auth(repository)

    def _inherit_checkout_auth(self, repository: str | Path) -> None:
        """Carry only matching checkout HTTP auth into private Git operations.

        actions/checkout stores its token in a URL-matched local extraheader.
        A private bare repository otherwise loses that credential. Pass the
        matching header through Git's process environment, never command-line
        arguments or an on-disk credential copy.
        """
        parsed = urlsplit(self.remote)
        if parsed.scheme not in ("http", "https"):
            return
        for secret in (parsed.username, parsed.password):
            if secret:
                self._secrets.add(secret)
        headers = self._command([
            "git", "-C", str(repository), "config", "--null", "--get-urlmatch",
            "http.extraheader", self.remote,
        ], check=False)
        if headers.returncode not in (0, 1):
            raise StateStoreError("Could not inspect URL-matched checkout authentication")
        values = [value.decode("utf-8") for value in headers.stdout.split(b"\0") if value]
        if not values:
            return
        count = int(self.environment.get("GIT_CONFIG_COUNT", "0"))
        for value in values:
            self.environment[f"GIT_CONFIG_KEY_{count}"] = f"http.{self.remote}.extraheader"
            self.environment[f"GIT_CONFIG_VALUE_{count}"] = value
            self._secrets.add(value)
            # Git diagnostics can render a header value without its name.
            self._secrets.update(part for part in value.split() if len(part) >= 8)
            count += 1
        self.environment["GIT_CONFIG_COUNT"] = str(count)

    @staticmethod
    def _prefixes(prefixes: tuple[str, ...]) -> tuple[str, ...]:
        result = []
        for prefix in prefixes:
            subtree = prefix.endswith("/")
            base = _canonical_path(prefix[:-1] if subtree else prefix)
            result.append(base + "/" if subtree else base)
        return tuple(result)

    @staticmethod
    def _matches(path: str, prefixes: tuple[str, ...]) -> bool:
        return any(path.startswith(prefix) if prefix.endswith("/") else path == prefix
                   for prefix in prefixes)

    def _command(
        self,
        args: list[str],
        *,
        input: bytes | None = None,
        environment: Mapping[str, str] | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        try:
            result = subprocess.run(
                args, input=input, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=self.environment if environment is None else environment,
                timeout=self.command_timeout, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise StateStoreError(f"Git state operation failed: {type(exc).__name__}") from exc
        if check and result.returncode:
            detail = self._error_detail(result)
            raise StateStoreError(f"Git state operation failed: {detail}")
        return result

    def _error_detail(self, result: subprocess.CompletedProcess) -> str:
        # Never echo an authenticated origin URL into a workflow log.
        detail = (result.stderr + result.stdout).decode("utf-8", errors="replace")
        remote = getattr(self, "remote", "")
        if remote:
            detail = detail.replace(remote, "<state-remote>")
        for secret in sorted(self._secrets, key=len, reverse=True):
            detail = detail.replace(secret, "<redacted>")
        return detail.strip()[-2000:]

    def _git(self, git_dir: str, *args: str, **kwargs) -> subprocess.CompletedProcess:
        return self._command(["git", f"--git-dir={git_dir}", *args], **kwargs)

    def _initialize(self, git_dir: str) -> None:
        self._command(["git", "init", "--bare", "--quiet", git_dir])
        self._git(git_dir, "remote", "add", "origin", self.remote)

    def _fetch(self, git_dir: str) -> str:
        # Fetch the actual authority on every attempt; cached checkout state is
        # never a transaction base. A missing branch fails instead of seeding
        # stale or empty local state over the authority.
        self._git(git_dir, "fetch", "--quiet", "--no-tags", "origin",
                  f"refs/heads/{self.branch}")
        return self._git(git_dir, "rev-parse", "FETCH_HEAD^{commit}").stdout.decode().strip()

    def _snapshot(self, git_dir: str, commit: str) -> Snapshot:
        tree = self._git(git_dir, "ls-tree", "-rz", "--full-tree", commit).stdout
        entries: list[tuple[str, str]] = []
        for entry in tree.split(b"\0"):
            if not entry:
                continue
            metadata, encoded_path = entry.split(b"\t", 1)
            _mode, object_type, object_id = metadata.split(b" ")
            path = encoded_path.decode("utf-8")
            if self._matches(path, self.allowed_prefixes):
                _canonical_path(path)
                if object_type != b"blob":
                    raise StateStoreError(f"State path is not a file: {path}")
                entries.append((path, object_id.decode("ascii")))
        files: dict[str, bytes] = {}
        if entries:
            payload = "".join(object_id + "\n" for _, object_id in entries).encode("ascii")
            objects = self._git(git_dir, "cat-file", "--batch", input=payload).stdout
            offset = 0
            for path, expected_id in entries:
                header_end = objects.index(b"\n", offset)
                object_id, object_type, size = objects[offset:header_end].split(b" ")
                if object_id.decode("ascii") != expected_id or object_type != b"blob":
                    raise StateStoreError("Unexpected state object response")
                offset = header_end + 1
                length = int(size)
                files[path] = objects[offset:offset + length]
                offset += length + 1
        return Snapshot(commit=commit, files=MappingProxyType(files))

    def read_snapshot(self) -> Snapshot:
        with tempfile.TemporaryDirectory(prefix="alicanto-state-") as git_dir:
            self._initialize(git_dir)
            return self._snapshot(git_dir, self._fetch(git_dir))

    def _writes(self, snapshot: Snapshot, mutation: Mutation) -> dict[str, bytes]:
        writes: dict[str, bytes] = {}
        for raw_path, value in mutation.writes.items():
            path = _canonical_path(raw_path)
            if not self._matches(path, self.allowed_prefixes):
                raise UnsafeStatePath(f"Write outside permitted state paths: {path}")
            if not isinstance(value, (str, bytes)):
                raise TypeError(f"State writes require str or bytes: {path}")
            content = value.encode("utf-8") if isinstance(value, str) else value
            previous = snapshot.read(path)
            if (previous is not None and content != previous
                    and self._matches(path, self.immutable_prefixes)):
                raise ImmutableEvidenceConflict(f"Evidence already exists: {path}")
            if content != previous:
                writes[path] = content
        return writes

    def transact(
        self,
        mutator: Callable[[Snapshot], Mutation],
        *,
        message: str = "autonomy: update durable state",
    ) -> TransactionResult:
        """Atomically publish explicit reducer writes or fail within a budget.

        The reducer can run more than once and must not perform external side
        effects. Generate operation IDs once outside it. Validate lease tokens,
        expiry and fencing inside it using the snapshot passed to that attempt.
        """
        last_error = ""
        with tempfile.TemporaryDirectory(prefix="alicanto-state-") as git_dir:
            self._initialize(git_dir)
            index_environment = dict(self.environment)
            index_environment["GIT_INDEX_FILE"] = str(Path(git_dir) / "transaction.index")
            for attempt in range(1, self.max_attempts + 1):
                commit = self._fetch(git_dir)
                snapshot = self._snapshot(git_dir, commit)
                mutation = mutator(snapshot)
                if not isinstance(mutation, Mutation):
                    raise TypeError("State reducer must return Mutation")
                writes = self._writes(snapshot, mutation)
                if not writes:
                    return TransactionResult(mutation.value, commit, attempt, False)
                self._git(git_dir, "read-tree", commit, environment=index_environment)
                for path, content in sorted(writes.items()):
                    object_id = self._git(git_dir, "hash-object", "-w", "--stdin",
                                          input=content).stdout.decode().strip()
                    self._git(git_dir, "update-index", "--add", "--cacheinfo",
                              f"100644,{object_id},{path}", environment=index_environment)
                tree = self._git(git_dir, "write-tree", environment=index_environment).stdout.decode().strip()
                candidate = self._git(git_dir, "commit-tree", tree, "-p", commit,
                                      input=(message.rstrip() + "\n").encode()).stdout.decode().strip()
                pushed = self._git(git_dir, "push", "--porcelain", "origin",
                                   f"{candidate}:refs/heads/{self.branch}", check=False)
                if pushed.returncode == 0:
                    return TransactionResult(mutation.value, candidate, attempt, True)
                last_error = self._error_detail(pushed)
                if attempt < self.max_attempts:
                    ceiling = min(self.max_backoff, self.initial_backoff * 2 ** (attempt - 1))
                    self.sleep(random.uniform(0.0, ceiling))
        raise RetryExhausted(f"State publish failed after {self.max_attempts} attempts: {last_error}")
