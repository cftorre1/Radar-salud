"""Read-only deterministic plans for narrowly recognized transport failures.

Approved task scope authorizes planning; a pre-supplied human patch is not needed.
This module never applies a plan, calls a model, runs task-provided commands,
changes product files, commits or promotes refs. The recovery executor retains
reproduction, exact-hash validation, directed/LIVE gates and candidate authority.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit


PATH = "src/radar_salud/scouts.py"
TASK = "source_repair_mutualities_lane_2026_10_11"
SLUGS = {"clinicas_achs_salud", "achs_seguro_laboral"}
STRATEGY = "achs_ascii_http_uri_utf8_percent_encoding_v1"
MAX_REPLACEMENT_BYTES = 24_576
MAX_FILE_BYTES = 262_144
OLD = '''def fetch_html(url: str, timeout: int = 20) -> str:
    req = Request(url, headers={"User-Agent": "RadarSaludBot/0.1 (+public-source-monitor)"})
    with urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")
'''
NEW = '''def fetch_html(url: str, timeout: int = 20) -> str:
    if not url.isascii():
        from urllib.parse import quote, urlsplit
        parsed = urlsplit(url)
        if parsed.scheme in {"http", "https"}:
            boundary = url.find("://") + 3 + len(parsed.netloc)
            prefix, target = url[:boundary], url[boundary:]
            url = prefix + "".join(char if char.isascii() else quote(char, safe="") for char in target)
    req = Request(url, headers={"User-Agent": "RadarSaludBot/0.1 (+public-source-monitor)"})
    with urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")
'''


def digest(raw):
    return hashlib.sha256(raw.encode("utf-8") if isinstance(raw, str) else raw).hexdigest()


def diagnostic(status, reason, *, kind="executor_capability_missing"):
    return {"status": status, "strategy": None, "plan": None,
            "diagnostic": {"kind": kind, "reason": reason, "human_required": False},
            "material_progress": False, "product_files_written": False,
            "paid_calls": 0, "evidence": []}


def _git(root, *arguments):
    try:
        result = subprocess.run(["git", *arguments], cwd=root, text=True,
                                capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _matched_request(source_result, source_slug):
    if not isinstance(source_result, dict) or source_result.get("slug") != source_slug:
        return None
    requests = source_result.get("requests")
    if not isinstance(requests, list):
        return None
    for request in requests:
        if not isinstance(request, dict) or request.get("status") != "FAIL":
            continue
        error, url = request.get("error"), request.get("url")
        if not isinstance(error, str) or not isinstance(url, str) or len(url) > 8192:
            continue
        if not re.search(r"UnicodeEncodeError:\s*'ascii' codec can't encode character", error):
            continue
        try:
            parsed = urlsplit(url)
        except ValueError:
            continue
        if (parsed.scheme != "https" or parsed.netloc not in {"www.achs.cl", "achs.cl"}
                or parsed.username or parsed.password or not parsed.path.startswith("/centro-de-noticias/noticia/")):
            continue
        target = parsed.path + ("?" + parsed.query if parsed.query else "")
        # Bind the actual failing codepoint, rather than treat an opaque
        # RuntimeError or a Unicode word elsewhere in the log as a strategy.
        escaped = re.search(r"\\+(?:x([0-9a-fA-F]{2})|u([0-9a-fA-F]{4})|U([0-9a-fA-F]{8}))", error)
        if escaped:
            try:
                char = chr(int(next(group for group in escaped.groups() if group), 16))
            except (ValueError, StopIteration):
                continue
            if ord(char) > 127 and char in target:
                return {"url": url, "error": error, "codepoint": "U+" + format(ord(char), "04X")}
    return None


def plan_repair(root, task, failure_log, *, source_slug, source_result, allowed_paths, observed_hashes):
    """Return an exact JSON plan or a precise capability/authority diagnostic.

    ``observed_hashes`` maps observed editable paths to their full-file SHA256.
    Unsupported failures never return an empty successful plan or silently
    select a broader rewrite/model fallback. Only the canonical known function
    shape can license this one-file transport strategy.
    """
    if (not isinstance(task, dict) or task.get("id") != TASK
            or task.get("status") not in {"approved", "in_progress"}
            or task.get("blocked_by") or task.get("depends_on")):
        return diagnostic("REJECTED", "Task lacks current unblocked approved mutualities scope", kind="planner_scope_rejected")
    if source_slug not in SLUGS:
        return diagnostic("UNSUPPORTED", "No deterministic strategy is registered for this source/failure")
    request = _matched_request(source_result, source_slug)
    if request is None:
        return diagnostic("UNSUPPORTED", "No bound ACHS ASCII HTTP URI UnicodeEncodeError was demonstrated")
    if not isinstance(failure_log, str) or "UnicodeEncodeError" not in failure_log or "ascii" not in failure_log:
        return diagnostic("REJECTED", "Structured failure has no corresponding observed reproduction log", kind="planner_context_rejected")
    if (not isinstance(allowed_paths, (list, tuple, set, frozenset)) or PATH not in allowed_paths
            or not isinstance(observed_hashes, dict)
            or not re.fullmatch(r"[a-f0-9]{64}", str(observed_hashes.get(PATH, "")))):
        return diagnostic("REJECTED", "Shared fetch_html is not an observed editable file with a full SHA256", kind="planner_context_rejected")
    root = Path(root).resolve()
    branch = _git(root, "branch", "--show-current")
    head = _git(root, "rev-parse", "HEAD")
    if (not branch or branch in {"main", "master", "production", "production-stable", "prod"}
            or not re.fullmatch(r"[a-f0-9]{40}", str(task.get("input_sha", "")))
            or head != task["input_sha"]):
        return diagnostic("REJECTED", "Read-only planner requires the exact task-bound isolated candidate SHA", kind="planner_scope_rejected")
    path = root / PATH
    if (not path.is_file() or any(parent.is_symlink() for parent in (path, *path.parents))
            or path.stat().st_nlink != 1 or path.stat().st_size > MAX_FILE_BYTES
            or _git(root, "ls-files", "--error-unmatch", "--", PATH) != PATH):
        return diagnostic("REJECTED", "Observed scout must be a bounded tracked regular file without links", kind="planner_context_rejected")
    raw = path.read_bytes()
    if digest(raw) != observed_hashes[PATH]:
        return diagnostic("REJECTED", "Observed scout SHA256 is stale; no plan generated", kind="planner_context_rejected")
    try:
        text = raw.decode("utf-8")
        tree = ast.parse(text)
    except (UnicodeError, SyntaxError):
        return diagnostic("UNSUPPORTED", "Observed scout source shape is not the recognized UTF-8 Python contract")
    functions = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "fetch_html"]
    imports = [node for node in tree.body if isinstance(node, ast.ImportFrom) and node.module == "urllib.request"]
    if (text.count(OLD) != 1 or len(functions) != 1
            or ast.dump(functions[0], include_attributes=False) != ast.dump(ast.parse(OLD).body[0], include_attributes=False)
            or not any({"Request", "urlopen"}.issubset({item.name for item in node.names if not item.asname}) for node in imports)):
        return diagnostic("UNSUPPORTED", "fetch_html differs from the exact recognized canonical function; no heuristic rewrite")
    candidate = text.replace(OLD, NEW, 1)
    if len(OLD.encode()) + len(NEW.encode()) > MAX_REPLACEMENT_BYTES or len(candidate.encode()) > MAX_FILE_BYTES:
        return diagnostic("REJECTED", "Recognized replacement exceeds the deterministic repair bound", kind="planner_context_rejected")
    compile(candidate, PATH, "exec")
    evidence = {"source_slug": source_slug, "request": request, "path": PATH,
                "observed_sha256": observed_hashes[PATH], "failure_sha256": digest(failure_log),
                "source_result_sha256": digest(json.dumps(source_result, sort_keys=True, ensure_ascii=False)),
                "input_sha": head, "task_id": task["id"]}
    return {"status": "PLANNED", "strategy": STRATEGY,
            "plan": {"schema_version": 1, "replacements": [{"path": PATH, "sha256": digest(raw), "old": OLD, "new": NEW}]},
            "diagnostic": None, "material_progress": False, "product_files_written": False,
            "paid_calls": 0, "evidence": [evidence]}
