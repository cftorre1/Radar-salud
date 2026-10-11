"""Explicit processing cohorts intersect an already discovered durable queue.

Selection is an execution view. It never discovers news, changes eligibility,
reorders work, reopens terminal decisions or supplies an editorial verdict.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from .pulso_source import article_url

SOURCE = "pulso_latercera"


@dataclass(frozen=True)
class QueueSelection:
    path: str
    sha256: str
    urls: tuple[str, ...]


def load_queue_selection(path, sources):
    """Read a strict canonical URL manifest; source isolation is mandatory."""
    if sources != [SOURCE]:
        raise ValueError("--queue-selection requires --sources pulso_latercera only")
    selected_path = Path(path)
    content = selected_path.read_bytes()
    try:
        value = json.loads(content)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid queue selection JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("Queue selection must be an object")
    if value.get("source", value.get("source_id")) != SOURCE:
        raise ValueError("Queue selection source must be pulso_latercera")
    if "source_id" in value and value["source_id"] != SOURCE:
        raise ValueError("Queue selection source_id must be pulso_latercera")
    urls = value.get("urls")
    if not isinstance(urls, list) or not urls:
        raise ValueError("Queue selection urls must be a nonempty list")
    for url in urls:
        if not isinstance(url, str):
            raise ValueError("Queue selection URLs must be strings")
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.netloc != "www.latercera.com"
                or parsed.query or parsed.fragment or article_url(url) != url):
            raise ValueError(f"Queue selection requires a canonical publisher article URL: {url}")
    if len(set(urls)) != len(urls):
        raise ValueError("Queue selection contains duplicate URLs")
    return QueueSelection(str(selected_path), hashlib.sha256(content).hexdigest(), tuple(urls))


def select_ready(selection, queue_items, ready):
    """Validate presence after discovery, then retain normal ready ordering.

    A missing or ambiguous durable URL fails before any processing attempt.
    Terminal rows are valid existing identities but can never become ready.
    """
    requested = set(selection.urls)
    matches = {}
    for key, item in queue_items.items():
        if item.get("source") != SOURCE:
            continue
        url = article_url(item.get("raw", {}).get("url"))
        if url in requested:
            if url in matches:
                raise ValueError(f"Queue selection URL has multiple durable queue identities: {url}")
            matches[url] = (key, item)
    missing = requested - matches.keys()
    if missing:
        raise ValueError("Queue selection URLs absent from existing Pulso queue: " + ", ".join(sorted(missing)))
    selected = [(key, item) for key, item in ready
                if item.get("source") == SOURCE
                and article_url(item.get("raw", {}).get("url")) in requested
                and item.get("status") in ("pending", "retry")]
    ready_urls = [article_url(item["raw"]["url"]) for _, item in selected]
    terminal = sorted(url for url, (_, item) in matches.items()
                      if item.get("status") in ("published", "rejected", "archived"))
    not_due = sorted(url for url, (_, item) in matches.items()
                     if item.get("status") in ("pending", "retry") and url not in ready_urls)
    in_progress = sorted(url for url, (_, item) in matches.items() if item.get("status") == "processing")
    outside_pending = sum(item.get("source") == SOURCE
                          and item.get("status") in ("pending", "retry", "processing")
                          and article_url(item.get("raw", {}).get("url")) not in requested
                          for item in queue_items.values())
    audit = dict(source=SOURCE, path=selection.path, sha256=selection.sha256,
                 file_sha256=selection.sha256, selected_urls=list(selection.urls),
                 selected_url_count=len(selection.urls), matched_existing_url_count=len(matches),
                 ready_selected_urls=ready_urls, skipped_terminal_urls=terminal,
                 skipped_not_due_urls=not_due, skipped_in_progress_urls=in_progress,
                 outside_selection_pending_url_count=outside_pending,
                 outside_selection_pending_reason="processing_not_attempted:explicit_queue_selection_excluded",
                 reason="explicit_queue_selection")
    return selected, audit
