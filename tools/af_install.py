#!/usr/bin/env python
"""Install the generated deploy/ output into ~/.claude and ~/.codex (opt-in, reversible).

  python tools/af_install.py [--claude-home DIR] [--codex-home DIR] [--only claude|codex] [--dry-run]
  python tools/af_install.py --uninstall

Rules
- A file that differs and is not ours is never overwritten (SKIPPED).
- Each installed file is recorded with the sha256 of the bytes we wrote (af-install-manifest.json).
  A refresh or an uninstall touches a file only while it still has that hash; a file the user edited
  is kept (MODIFIED) and a recoverable copy is not needed because nothing is overwritten or deleted.
- settings.json edits are preceded by a timestamped backup. Framework hooks are identified by their
  `af_cli.py hook` command; stale ones (moved checkout) are replaced and each event keeps exactly one.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

FW = Path(__file__).resolve().parents[1]
FW_POSIX = FW.as_posix()
MARK = "af_cli.py hook"
MANIFEST = "af-install-manifest.json"


def render(text: str) -> str:
    return text.replace("{fw}", FW_POSIX)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_manifest(home: Path) -> dict:
    """path -> sha256 of what we wrote. A legacy list manifest is migrated by hashing current files."""
    f = home / MANIFEST
    if not f.is_file():
        return {}
    raw = json.loads(f.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return raw
    return {p: sha(Path(p).read_bytes()) for p in raw if Path(p).is_file()}


def save_manifest(home: Path, manifest: dict) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def put(src: Path, dst: Path, manifest: dict, prev: dict, log: list, dry: bool) -> None:
    if src.suffix in (".md", ".toml", ".json"):
        data = render(src.read_text(encoding="utf-8")).encode("utf-8")
    else:
        data = src.read_bytes()
    key = str(dst)
    if dst.exists():
        cur = sha(dst.read_bytes())
        if cur == sha(data):
            log.append(f"SAME     {dst}")
            if key in prev:  # an identical pre-existing file we never created stays the user's
                manifest[key] = cur
            return
        if key not in prev:
            log.append(f"SKIPPED  {dst} (exists, differs, not installed by us)")
            return
        if prev[key] != cur:
            log.append(f"MODIFIED {dst} (edited since install; kept as is)")
            manifest[key] = prev[key]
            return
    log.append(f"WRITE    {dst}")
    if not dry:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
    manifest[key] = sha(data)


def copy_tree(src: Path, dst: Path, manifest, prev, log, dry) -> None:
    for f in sorted(p for p in src.rglob("*") if p.is_file()):
        put(f, dst / f.relative_to(src), manifest, prev, log, dry)


def _is_ours(entry: dict) -> bool:
    return any(MARK in h.get("command", "") for h in entry.get("hooks", []))


def merge_hooks(settings: Path, log: list, dry: bool) -> None:
    want = json.loads(render((FW / "deploy" / "claude" / "settings.hooks.json").read_text(encoding="utf-8")))["hooks"]
    cur = json.loads(settings.read_text(encoding="utf-8")) if settings.is_file() else {}
    new = json.loads(json.dumps(cur))
    new.setdefault("hooks", {})
    for event, entries in want.items():
        kept = [e for e in new["hooks"].get(event, []) if not _is_ours(e)]
        new["hooks"][event] = kept + entries
    if new == cur:
        log.append(f"SAME     {settings} (framework hooks current)")
        return
    log.append(f"MERGE    {settings} (framework hooks set to current path; backup first)")
    if not dry:
        if settings.is_file():
            shutil.copy2(settings, settings.with_name(settings.name + f".bak-af-{datetime.now():%Y%m%d%H%M%S}"))
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps(new, indent=2) + "\n", encoding="utf-8")


def remove_hooks(settings: Path, log: list, dry: bool) -> None:
    if not settings.is_file():
        return
    cur = json.loads(settings.read_text(encoding="utf-8"))
    new = json.loads(json.dumps(cur))
    for event in list(new.get("hooks", {})):
        new["hooks"][event] = [e for e in new["hooks"][event] if not _is_ours(e)]
        if not new["hooks"][event]:
            del new["hooks"][event]
    if new == cur:
        return
    log.append(f"UNMERGE  {settings}")
    if not dry:
        shutil.copy2(settings, settings.with_name(settings.name + f".bak-af-{datetime.now():%Y%m%d%H%M%S}"))
        settings.write_text(json.dumps(new, indent=2) + "\n", encoding="utf-8")


def missing_external_skills_note(home: Path) -> str:
    """Skills the framework only references (external_skills) must exist in the target home."""
    cfg = json.loads((FW / "core" / "framework.json").read_text(encoding="utf-8"))
    missing = [s for s in cfg.get("external_skills", []) if not (home / "skills" / s / "SKILL.md").exists()]
    if not missing:
        return "EXTERNAL-SKILLS ok: every external skill is present"
    return "EXTERNAL-SKILLS MISSING (agents reference them; install them separately): " + ", ".join(missing)


def install(home: Path, target: str, log: list, dry: bool) -> None:
    dep = FW / "deploy" / target
    prev = load_manifest(home)
    manifest: dict = {}
    for sub in ("agents", "skills") + (("prompts",) if target == "codex" else ()):
        copy_tree(dep / sub, home / sub, manifest, prev, log, dry)
    if target == "claude":
        merge_hooks(home / "settings.json", log, dry)
    log.append(missing_external_skills_note(home))
    # entries we no longer ship stay tracked so uninstall can still find them
    for k, v in prev.items():
        manifest.setdefault(k, v)
    if not dry:
        save_manifest(home, manifest)


def uninstall(home: Path, claude: bool, log: list, dry: bool) -> None:
    remaining: dict = {}
    for f, h in load_manifest(home).items():
        p = Path(f)
        if not p.is_file():
            continue
        if sha(p.read_bytes()) != h:
            log.append(f"KEPT     {p} (edited since install)")
            remaining[f] = h
            continue
        log.append(f"REMOVE   {p}")
        if not dry:
            p.unlink()
    if claude:
        remove_hooks(home / "settings.json", log, dry)
    if not dry and (home / MANIFEST).exists():
        if remaining:
            save_manifest(home, remaining)
        else:
            (home / MANIFEST).unlink()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--claude-home", default=str(Path.home() / ".claude"))
    ap.add_argument("--codex-home", default=str(Path.home() / ".codex"))
    ap.add_argument("--only", choices=["claude", "codex"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    a = ap.parse_args()
    log: list = []
    for name, home in (("claude", Path(a.claude_home)), ("codex", Path(a.codex_home))):
        if a.only and a.only != name:
            continue
        if a.uninstall:
            uninstall(home, name == "claude", log, a.dry_run)
        else:
            install(home, name, log, a.dry_run)
    print("\n".join(log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
