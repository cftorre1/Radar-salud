"""Assemble Pages output from the reviewed files and last accepted release."""
import argparse
import json
import shutil
from pathlib import Path


def _copy_clean(source: Path, target: Path) -> None:
    if not (source / "index.html").is_file():
        raise ValueError(f"Missing site entry point: {source}")
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


def _stamp(directory: Path, sha: str) -> None:
    product = json.loads((directory / "data/product.json").read_text(encoding="utf-8"))
    version = product.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("Checked product version is missing")
    (directory / "release.json").write_text(json.dumps({"version": version, "sha": sha}), encoding="utf-8")
    # Pages and browsers can cache JavaScript across a deploy. Pin assets to
    # this release so a new HTML document loads its matching code.
    for name,asset in (("index.html","app.js"),("admin/product.html","product.js")):
        page=directory / name
        if page.is_file():
            html=page.read_text(encoding="utf-8")
            html=html.replace(f'src="{asset}"',f'src="{asset}?v={sha}"')
            page.write_text(html,encoding="utf-8")


def assemble(mode: str, accepted: Path, checked: Path, output: Path, sha: str) -> None:
    if not sha or len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha.lower()):
        raise ValueError("A full candidate commit SHA is required")
    if not (checked / "admin/product.html").is_file() or not (checked / "data/product.json").is_file():
        raise ValueError("Incomplete checked candidate")
    if mode == "staging":
        _copy_clean(accepted, output)
        _copy_clean(checked, output / "staging")
        _stamp(output / "staging", sha)
    elif mode == "production":
        _copy_clean(checked, output)
        _stamp(output, sha)
        _copy_clean(checked, output / "staging")
        _stamp(output / "staging", sha)
    else:
        raise ValueError(f"Unsupported mode: {mode}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("staging", "production"))
    p.add_argument("--accepted", type=Path, required=True)
    p.add_argument("--checked", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--sha", required=True)
    a = p.parse_args()
    assemble(a.mode, a.accepted, a.checked, a.output, a.sha)
