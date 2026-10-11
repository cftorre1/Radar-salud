"""Actual stdlib URI encoding and read-only exact-plan authority checks."""
from copy import deepcopy
import http.client
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from urllib.request import Request

from scripts import autonomy_repair_planner as planner
from scripts.autonomy_recovery import validate_plan


URL = "https://www.achs.cl/centro-de-noticias/noticia/2026/comieé-paritario"
ERROR = "UnicodeEncodeError: 'ascii' codec can't encode character '\\xe9' in position 42: ordinal not in range(128)"


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="deterministic-planner-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "--quiet", "-b", "staging")
        self.git("config", "user.name", "Planner Test")
        self.git("config", "user.email", "planner@example.invalid")
        self.path = self.root / planner.PATH
        self.path.parent.mkdir(parents=True)
        self.path.write_text("from urllib.request import Request, urlopen\n\n" + planner.OLD + "\nSENTINEL = 'unchanged'\n")
        self.git("add", "--", planner.PATH)
        self.git("commit", "--quiet", "-m", "fixture canonical scout")
        self.sha = self.git("rev-parse", "HEAD")
        self.task = {"id": planner.TASK, "status": "in_progress", "depends_on": [],
                     "blocked_by": [], "input_sha": self.sha}
        self.row = {"slug": "achs_seguro_laboral", "technical_status": "error",
                    "error": "RuntimeError: source has no dated, verified detail items",
                    "requests": [{"url": URL, "status": "FAIL", "error": ERROR}]}
        self.hashes = {planner.PATH: planner.digest(self.path.read_bytes())}

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True, text=True).stdout.strip()

    def plan(self, **overrides):
        kwargs = {"source_slug": self.row["slug"], "source_result": self.row,
                  "allowed_paths": {planner.PATH}, "observed_hashes": self.hashes}
        kwargs.update(overrides)
        return planner.plan_repair(self.root, self.task, ERROR, **kwargs)

    def test_recognized_plan_is_hash_bound_valid_and_completely_read_only(self):
        raw, head, status = self.path.read_bytes(), self.git("rev-parse", "HEAD"), self.git("status", "--porcelain")
        result = self.plan()
        self.assertEqual(result["status"], "PLANNED")
        self.assertEqual(result["strategy"], planner.STRATEGY)
        changes = validate_plan(self.root, result["plan"], allowed_paths={planner.PATH})
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["original"], raw)
        self.assertIn(b"SENTINEL = 'unchanged'", changes[0]["candidate"])
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertEqual(self.git("rev-parse", "HEAD"), head)
        self.assertEqual(self.git("status", "--porcelain"), status)
        self.assertFalse(result["product_files_written"])
        self.assertEqual(result["paid_calls"], 0)

    def candidate_fetch(self):
        result = self.plan()
        replacement = result["plan"]["replacements"][0]
        captured = []
        class Response:
            headers = type("Headers", (), {"get_content_charset": lambda self: "utf-8"})()
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return "éxito".encode()
        def fetch(request, timeout):
            # This executes the same ASCII HTTP request-line encoding that
            # caused the hosted error, without opening a network connection.
            connection = http.client.HTTPConnection("example.invalid")
            connection.putrequest("GET", request.selector)
            captured.append((request.full_url, timeout, request.get_header("User-agent")))
            return Response()
        namespace = {"Request": Request, "urlopen": fetch}
        exec(compile(replacement["new"], planner.PATH, "exec"), namespace)
        return namespace["fetch_html"], captured

    def test_actual_http_ascii_encoding_failure_is_repaired_in_memory(self):
        raw = Request(URL)
        with self.assertRaises(UnicodeEncodeError):
            http.client.HTTPConnection("example.invalid").putrequest("GET", raw.selector)
        fetch, captured = self.candidate_fetch()
        self.assertEqual(fetch(URL, timeout=17), "éxito")
        self.assertEqual(captured[0], (URL.replace("é", "%C3%A9"), 17, "RadarSaludBot/0.1 (+public-source-monitor)"))

    def test_ascii_uri_byte_behavior_percent_encoding_and_query_delimiters_are_preserved(self):
        fetch, captured = self.candidate_fetch()
        urls = ["https://www.achs.cl/a%2fb%2F?x=a+b&y=%C3%A9;x=1#frag",
                "https://www.achs.cl/a;b:@!$&'()*+,=/?x=a%2Fb&empty=&q=%25#%23"]
        for url in urls:
            fetch(url)
            self.assertEqual(captured[-1][0], url)

    def test_utf8_multibyte_path_query_values_and_literal_percent_sequences(self):
        fetch, captured = self.candidate_fetch()
        urls = {"https://www.achs.cl/niño/東京?nombre=José&x=%2F+1":
                "https://www.achs.cl/ni%C3%B1o/%E6%9D%B1%E4%BA%AC?nombre=Jos%C3%A9&x=%2F+1",
                "https://www.achs.cl/%C3%A9/é?x=€;y=😀":
                "https://www.achs.cl/%C3%A9/%C3%A9?x=%E2%82%AC;y=%F0%9F%98%80"}
        for url, expected in urls.items():
            fetch(url)
            self.assertEqual(captured[-1][0], Request(expected).full_url)

    def test_unicode_authority_and_empty_delimiters_keep_original_behavior(self):
        fetch, captured = self.candidate_fetch()
        for url, expected in (("https://münchen.example/é?", "https://münchen.example/%C3%A9?"),
                              ("https://www.achs.cl/é?#", "https://www.achs.cl/%C3%A9?#"),
                              ("HTTPS://www.achs.cl/é?x=%2F", "HTTPS://www.achs.cl/%C3%A9?x=%2F")):
            fetch(url)
            self.assertEqual(captured[-1][0], Request(expected).full_url)

    def test_ascii_spaces_and_controls_are_never_percent_encoded_by_strategy(self):
        fetch, captured = self.candidate_fetch()
        for url in ("https://www.achs.cl/é space", "https://www.achs.cl/é\x01"):
            with self.subTest(url=url), self.assertRaises(http.client.InvalidURL):
                fetch(url)
        self.assertEqual(captured, [])

    def test_detached_candidate_and_unbound_reproduction_log_are_rejected(self):
        self.git("checkout", "--detach", "--quiet")
        self.assertEqual(self.plan()["status"], "REJECTED")
        self.git("checkout", "--quiet", "staging")
        result = planner.plan_repair(self.root, self.task, "opaque log", source_slug=self.row["slug"],
            source_result=self.row, allowed_paths={planner.PATH}, observed_hashes=self.hashes)
        self.assertEqual(result["status"], "REJECTED")

    def test_exact_snippet_inside_unknown_async_or_extended_function_is_unsupported(self):
        for text in ("async " + planner.OLD, planner.OLD + "    extra = True\n"):
            self.path.write_text("from urllib.request import Request, urlopen\n\n" + text)
            self.hashes = {planner.PATH: planner.digest(self.path.read_bytes())}
            self.assertEqual(self.plan()["status"], "UNSUPPORTED")

    def test_opaque_or_unrelated_failures_produce_explicit_missing_capability(self):
        for override in ({"source_slug": "mutual_seguridad"}, {"source_result": {}},
                         {"source_result": {**self.row, "slug": "different"}},
                         {"source_result": {**self.row, "requests": [{"url": URL, "status": "FAIL", "error": "RuntimeError"}]}},
                         {"source_result": {**self.row, "requests": [{"url": URL, "status": "PASS", "error": ERROR}]}}):
            with self.subTest(override=override):
                result = self.plan(**override)
                self.assertEqual(result["status"], "UNSUPPORTED")
                self.assertEqual(result["diagnostic"]["kind"], "executor_capability_missing")
                self.assertIsNone(result["plan"])

    def test_untrusted_host_ascii_only_url_or_mismatched_error_character_is_unsupported(self):
        for url in (URL.replace("www.achs.cl", "example.invalid"), URL.replace("é", "%C3%A9"),
                    URL.replace("é", "ñ"), URL.replace("https://", "http://"),
                    URL.replace("www.achs.cl", "user@www.achs.cl")):
            row = {**self.row, "requests": [{"url": url, "status": "FAIL", "error": ERROR}]}
            with self.subTest(url=url):
                self.assertEqual(self.plan(source_result=row)["status"], "UNSUPPORTED")

    def test_task_approval_blockers_and_other_scope_cannot_generate_plan(self):
        for patch in ({"id": "other"}, {"status": "paused"}, {"blocked_by": ["policy"]},
                      {"depends_on": ["unfinished"]}, {"input_sha": "b" * 40}):
            self.task = {"id": planner.TASK, "status": "in_progress", "depends_on": [],
                         "blocked_by": [], "input_sha": self.sha, **patch}
            with self.subTest(patch=patch):
                result = self.plan()
                self.assertEqual(result["status"], "REJECTED")
                self.assertIsNone(result["plan"])

    def test_approved_qa_and_fiscalization_unknown_cases_are_capability_gaps(self):
        for task_id, slug, row in (("staging_qa_failed_run_123", None, None),
                                  ("source_repair_fiscalization_lane_2026_10_11", "suseso_fiscalizacion",
                                   {"slug": "suseso_fiscalizacion", "error": "HTTPError", "requests": []})):
            with self.subTest(task_id=task_id):
                self.task = {"id": task_id, "status": "approved", "input_sha": self.sha}
                result = self.plan(source_slug=slug, source_result=row)
                self.assertEqual(result["status"], "UNSUPPORTED")
                self.assertEqual(result["diagnostic"]["kind"], "executor_capability_missing")
                self.assertFalse(result["diagnostic"]["human_required"])
                self.assertIsNone(result["plan"])

    def test_known_source_unknown_error_is_capability_gap_before_authority_guard(self):
        self.task = {"id": "already_approved_other_task", "status": "approved", "input_sha": self.sha}
        result = self.plan(source_result={**self.row, "requests": []})
        self.assertEqual(result["status"], "UNSUPPORTED")
        self.assertEqual(result["diagnostic"]["kind"], "executor_capability_missing")
        # Exact recognized ACHS evidence still cannot be repaired under that
        # unrelated task's authority, even though the task itself is approved.
        known = self.plan()
        self.assertEqual(known["status"], "REJECTED")
        self.assertEqual(known["diagnostic"]["kind"], "planner_scope_rejected")
        self.assertIsNone(known["plan"])

    def test_stale_or_unobserved_or_protected_file_never_has_fallback_plan(self):
        for override in ({"observed_hashes": {planner.PATH: "b" * 64}},
                         {"allowed_paths": {"src/radar_salud/editorial_gate.py"}},
                         {"allowed_paths": {"tests/test_scouts.py"}},
                         {"observed_hashes": {}}, {"allowed_paths": planner.PATH}):
            with self.subTest(override=override):
                result = self.plan(**override)
                self.assertEqual(result["status"], "REJECTED")
                self.assertIsNone(result["plan"])

    def test_already_repaired_or_unknown_shape_does_not_rewrite(self):
        for text in (planner.OLD.replace("timeout: int = 20", "timeout: int = 21"), planner.NEW):
            self.path.write_text("from urllib.request import Request, urlopen\n\n" + text)
            self.hashes = {planner.PATH: planner.digest(self.path.read_bytes())}
            result = self.plan()
            self.assertEqual(result["status"], "UNSUPPORTED")
            self.assertIsNone(result["plan"])

    def test_main_checkout_and_symlinks_cannot_generate_a_product_plan(self):
        self.git("branch", "-m", "main")
        self.assertEqual(self.plan()["status"], "REJECTED")
        self.git("branch", "-m", "staging")
        outside = self.root / "outside.py"
        outside.write_bytes(self.path.read_bytes())
        self.path.unlink()
        self.path.symlink_to(outside)
        self.assertEqual(self.plan()["status"], "REJECTED")


if __name__ == "__main__":
    unittest.main()
