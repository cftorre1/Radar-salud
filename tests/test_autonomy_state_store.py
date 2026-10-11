"""Real Git races, not mocks of optimistic state update behavior."""

import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from scripts.autonomy_state_store import (
    GitStateStore,
    ImmutableEvidenceConflict,
    Mutation,
    RetryExhausted,
    StateStoreError,
    UnsafeStatePath,
)


class StateStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="autonomy-store-test-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.remote = self.root / "remote.git"
        self.seed = self.root / "seed"
        self.git("init", "--bare", "--quiet", str(self.remote))
        self.git("init", "--quiet", str(self.seed))
        self.git("-C", str(self.seed), "config", "user.name", "Test")
        self.git("-C", str(self.seed), "config", "user.email", "test@example.invalid")
        self.git("-C", str(self.seed), "checkout", "-b", "autopilot-state")
        state = self.seed / "data/autopilot/state.json"
        state.parent.mkdir(parents=True)
        state.write_text(json.dumps({"count": 0, "writers": []}))
        evidence = self.seed / "data/autopilot/evidence/seed.json"
        evidence.parent.mkdir()
        evidence.write_text('{"seed": true}\n')
        (self.seed / "source.py").write_text("original product source\n")
        self.git("-C", str(self.seed), "add", "data/autopilot/state.json",
                 "data/autopilot/evidence/seed.json", "source.py")
        self.git("-C", str(self.seed), "commit", "--quiet", "-m", "seed")
        self.git("-C", str(self.seed), "remote", "add", "origin", self.remote.as_uri())
        self.git("-C", str(self.seed), "push", "--quiet", "origin", "autopilot-state")

    @staticmethod
    def git(*args):
        return subprocess.run(["git", *args], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, check=True).stdout.decode().strip()

    def store(self, **kwargs):
        return GitStateStore(self.remote.as_uri(), initial_backoff=0, **kwargs)

    def test_conflicting_writers_retry_reducer_and_preserve_both_updates(self):
        barrier = threading.Barrier(2)
        reducer_calls = {"a": 0, "b": 0}

        def writer(name):
            def reduce(snapshot):
                reducer_calls[name] += 1
                state = snapshot.read_json("data/autopilot/state.json")
                if reducer_calls[name] == 1:
                    barrier.wait(timeout=10)
                state["count"] += 1
                state["writers"].append(name)
                return Mutation({
                    "data/autopilot/state.json": json.dumps(state),
                    f"data/autopilot/evidence/{name}.json": json.dumps({"writer": name}),
                }, value=state["count"])
            return self.store().transact(reduce)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(writer, "a")
            second = pool.submit(writer, "b")
            results = [first.result(timeout=20), second.result(timeout=20)]
        state = self.store().read_snapshot()
        self.assertEqual(state.read_json("data/autopilot/state.json")["count"], 2)
        self.assertEqual(set(state.read_json("data/autopilot/state.json")["writers"]), {"a", "b"})
        self.assertEqual(sorted(result.attempts for result in results), [1, 2])
        self.assertEqual(sum(reducer_calls.values()), 3)
        self.assertEqual(set(result.value for result in results), {1, 2})
        self.assertEqual(state.read_json("data/autopilot/evidence/a.json"), {"writer": "a"})
        self.assertEqual(state.read_json("data/autopilot/evidence/b.json"), {"writer": "b"})

    def test_identical_candidate_up_to_date_push_is_not_a_second_remote_write(self):
        barrier = threading.Barrier(2)
        first_published = threading.Event()
        pushes = {}
        initial = self.store().read_snapshot().commit

        def writer(name):
            store = self.store()
            # Identical candidate identity is explicit, independent of wall
            # clock scheduling or how long the two commit-tree calls take.
            store.environment.update(GIT_AUTHOR_DATE="2026-10-11T00:00:00+00:00",
                                     GIT_COMMITTER_DATE="2026-10-11T00:00:00+00:00")
            original_git = store._git

            def ordered_push(git_dir, *args, **kwargs):
                if args[:2] != ("push", "--porcelain"):
                    return original_git(git_dir, *args, **kwargs)
                if name == "second":
                    self.assertTrue(first_published.wait(timeout=10))
                result = original_git(git_dir, *args, **kwargs)
                pushes[name] = {"refspec": args[-1], "stdout": result.stdout,
                                "returncode": result.returncode}
                if name == "first":
                    first_published.set()
                return result

            def reduce(snapshot):
                barrier.wait(timeout=10)
                return Mutation({"data/autopilot/episode.json": '{"episode":"once","generation":1}\n',
                                 "data/autopilot/evidence/fixed-episode.json": '{"event":"once"}\n'},
                                "one fixed episode")

            with patch.object(store, "_git", side_effect=ordered_push):
                return store.transact(reduce)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(writer, name) for name in ("first", "second")]
            first, second = [future.result(timeout=20) for future in futures]
        self.assertEqual(pushes["first"]["refspec"], pushes["second"]["refspec"])
        self.assertEqual(pushes["second"]["returncode"], 0)
        self.assertTrue(any(line.startswith(b"=\t") for line in pushes["second"]["stdout"].splitlines()))
        self.assertTrue(first.changed)
        self.assertFalse(second.changed)
        self.assertEqual(first.commit, second.commit)
        self.assertEqual([first.attempts, second.attempts], [1, 1])
        self.assertEqual([first.value, second.value], ["one fixed episode"] * 2)
        self.assertEqual(self.git("--git-dir", str(self.remote), "rev-list", "--count",
                                  initial + "..refs/heads/autopilot-state"), "1")
        snapshot = self.store().read_snapshot()
        self.assertEqual(snapshot.read_json("data/autopilot/episode.json"), {"episode": "once", "generation": 1})
        self.assertEqual(snapshot.read_json("data/autopilot/evidence/fixed-episode.json"), {"event": "once"})

    def test_reducer_revalidates_fencing_after_competing_claim(self):
        # The engine owns lease rules; prove a rejected old-token write is
        # re-evaluated rather than blindly replayed on the winner's commit.
        store = self.store()
        store.transact(lambda snapshot: Mutation({"data/autopilot/lease.json":
            json.dumps({"token": "old", "generation": 1})}))
        ready = threading.Event()
        resume = threading.Event()
        calls = []

        class LostLease(Exception):
            pass

        def old_writer(snapshot):
            lease = snapshot.read_json("data/autopilot/lease.json")
            calls.append(lease["generation"])
            if lease["token"] != "old" or lease["generation"] != 1:
                raise LostLease()
            if len(calls) == 1:
                ready.set()
                self.assertTrue(resume.wait(timeout=10))
            return Mutation({"data/autopilot/lease.json": json.dumps({**lease, "closed": True})})

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(store.transact, old_writer)
            self.assertTrue(ready.wait(timeout=10))
            self.store().transact(lambda snapshot: Mutation({"data/autopilot/lease.json":
                json.dumps({"token": "new", "generation": 2})}))
            resume.set()
            with self.assertRaises(LostLease):
                future.result(timeout=20)
        self.assertEqual(calls, [1, 2])
        self.assertEqual(self.store().read_snapshot().read_json("data/autopilot/lease.json"),
                         {"token": "new", "generation": 2})

    def test_success_without_recognized_exact_target_ref_status_fails_closed(self):
        before = self.store().read_snapshot().commit
        for output in (b"Done\n", b"=\tsha:refs/heads/unrelated\t[up to date]\n",
                       b"=\trefs/heads/autopilot-state\t[up to date]\n",
                       b"?\tsha:refs/heads/autopilot-state\tunknown\n",
                       b"=\tsha:refs/heads/autopilot-state\t[up to date]\n"
                       b" \tsha:refs/heads/autopilot-state\told..new\n"):
            with self.subTest(output=output):
                store = self.store()
                original_git = store._git
                def unexpected_push(git_dir, *args, **kwargs):
                    if args[:2] == ("push", "--porcelain"):
                        return subprocess.CompletedProcess(args, 0, output, b"")
                    return original_git(git_dir, *args, **kwargs)
                with patch.object(store, "_git", side_effect=unexpected_push), \
                     self.assertRaisesRegex(StateStoreError, "recognized target-ref"):
                    store.transact(lambda snapshot: Mutation({"data/autopilot/new.json": "{}"}))
                self.assertEqual(self.store().read_snapshot().commit, before)

    def test_published_evidence_cannot_be_replaced(self):
        store = self.store()
        before = store.read_snapshot().commit
        with self.assertRaises(ImmutableEvidenceConflict):
            store.transact(lambda snapshot: Mutation({
                "data/autopilot/evidence/seed.json": '{"seed": false}\n'}))
        after = store.read_snapshot()
        self.assertEqual(after.commit, before)
        self.assertEqual(after.read_json("data/autopilot/evidence/seed.json"), {"seed": True})

    def test_unchanged_state_does_not_create_material_progress(self):
        store = self.store()
        before = store.read_snapshot().commit
        result = store.transact(lambda snapshot: Mutation({
            "data/autopilot/state.json": snapshot.read("data/autopilot/state.json")}, "noop"))
        self.assertFalse(result.changed)
        self.assertEqual(result.commit, before)
        self.assertEqual(result.value, "noop")
        self.assertEqual(result.attempts, 1)

    def test_only_explicit_allowed_paths_are_committed(self):
        # Caller changes must never leak through an ambient git add -A.
        (self.seed / "source.py").write_text("uncommitted caller edit\n")
        (self.seed / "untracked.secret").write_text("caller secret\n")
        store = GitStateStore(repository=self.seed, initial_backoff=0)
        result = store.transact(lambda snapshot: Mutation({"data/autopilot/new.json": "{}"}))
        changed_paths = self.git("--git-dir", str(self.remote), "diff-tree", "--no-commit-id",
                                 "--name-only", "-r", result.commit).splitlines()
        self.assertEqual(changed_paths, ["data/autopilot/new.json"])
        self.assertEqual(self.git("--git-dir", str(self.remote), "show",
                                 f"{result.commit}:source.py"), "original product source")
        for path in ("source.py", "../state.json", "/data/autopilot/state.json",
                     "data/autopilot/../bad", "data/autopilot//bad", "data\\autopilot\\bad"):
            with self.subTest(path=path), self.assertRaises(UnsafeStatePath):
                store.transact(lambda snapshot: Mutation({path: "forbidden"}))

    def test_snapshot_is_remote_authoritative_and_immutable(self):
        store = self.store()
        old = store.read_snapshot()
        self.assertNotIn("source.py", old.paths())
        with self.assertRaises(TypeError):
            old.files["data/autopilot/state.json"] = b"{}"
        store.transact(lambda snapshot: Mutation({"data/autopilot/new.json": '{"new":true}'}))
        self.assertIsNone(old.read("data/autopilot/new.json"))
        self.assertEqual(store.read_snapshot().read_json("data/autopilot/new.json"), {"new": True})

    def test_push_rejections_have_bounded_retries(self):
        hook = self.remote / "hooks/pre-receive"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        calls = []
        sleeps = []
        store = GitStateStore(self.remote.as_uri(), max_attempts=3,
                              initial_backoff=0.001, max_backoff=0.002, sleep=sleeps.append)
        before = store.read_snapshot().commit

        def reduce(snapshot):
            calls.append(snapshot.commit)
            return Mutation({"data/autopilot/new.json": "{}"})

        with self.assertRaises(RetryExhausted):
            store.transact(reduce)
        self.assertEqual(calls, [before] * 3)
        self.assertEqual(len(sleeps), 2)
        self.assertTrue(all(0 <= delay <= 0.002 for delay in sleeps))
        self.assertEqual(store.read_snapshot().commit, before)

    def test_missing_remote_state_branch_does_not_bootstrap(self):
        store = GitStateStore(self.remote.as_uri(), branch="missing-state", initial_backoff=0)
        with self.assertRaises(StateStoreError):
            store.read_snapshot()
        with self.assertRaises(StateStoreError):
            store.transact(lambda snapshot: Mutation({"data/autopilot/new.json": "{}"}))

    def test_matching_checkout_auth_is_inherited_without_command_line_secret(self):
        remote = "https://github.com/example/repository.git"
        header = "AUTHORIZATION: basic test-secret-value"
        self.git("-C", str(self.seed), "config", "http.https://github.com/.extraheader", header)
        self.git("-C", str(self.seed), "config", "http.https://elsewhere.invalid/.extraheader",
                 "AUTHORIZATION: basic unrelated-secret")
        original_run = subprocess.run
        command_arguments = []

        def observe(args, **kwargs):
            command_arguments.append(args)
            return original_run(args, **kwargs)

        with patch("scripts.autonomy_state_store.subprocess.run", side_effect=observe):
            store = GitStateStore(remote, repository=self.seed)
        values = [value for key, value in store.environment.items() if key.startswith("GIT_CONFIG_VALUE_")]
        self.assertIn(header, values)
        self.assertNotIn("AUTHORIZATION: basic unrelated-secret", values)
        self.assertTrue(all(header not in argument for args in command_arguments for argument in args))
        error = subprocess.CompletedProcess([], 1, b"", header.encode())
        self.assertNotIn("test-secret-value", store._error_detail(error))


if __name__ == "__main__":
    unittest.main()
