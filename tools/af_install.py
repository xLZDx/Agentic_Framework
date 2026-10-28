#!/usr/bin/env python
"""Install the generated deploy/ output into ~/.claude and ~/.codex (opt-in, reversible).

  python tools/af_install.py [--claude-home DIR] [--codex-home DIR] [--only claude|codex] [--dry-run]

Rules: files that differ and are not ours are never overwritten (reported as SKIPPED); every
settings.json edit is preceded by a timestamped backup; hooks are merged idempotently. An
install manifest (af-install-manifest.json) is written under each home so removal is exact:
`python tools/af_install.py --uninstall`.
"""
from __future__ import annotations

import argparse
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


def put(src: Path, dst: Path, manifest: list, log: list, dry: bool, force_owned: set) -> None:
    new = render(src.read_text(encoding="utf-8")) if src.suffix in (".md", ".toml", ".json") else None
    data = new.encode("utf-8") if new is not None else src.read_bytes()
    if dst.exists():
        if dst.read_bytes() == data:
            log.append(f"SAME     {dst}")
            if str(dst) in force_owned:
                manifest.append(str(dst))
            return
        if str(dst) not in force_owned:
            log.append(f"SKIPPED  {dst} (exists, differs, not installed by us)")
            return
    log.append(f"WRITE    {dst}")
    if not dry:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
    manifest.append(str(dst))


def copy_tree(src: Path, dst: Path, manifest, log, dry, owned) -> None:
    for f in sorted(p for p in src.rglob("*") if p.is_file()):
        put(f, dst / f.relative_to(src), manifest, log, dry, owned)


def load_manifest(home: Path) -> list:
    f = home / MANIFEST
    return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else []


def merge_hooks(settings: Path, log: list, dry: bool) -> bool:
    hooks = json.loads(render((FW / "deploy" / "claude" / "settings.hooks.json").read_text(encoding="utf-8")))["hooks"]
    cur = json.loads(settings.read_text(encoding="utf-8")) if settings.is_file() else {}
    cur.setdefault("hooks", {})
    changed = False
    for event, entries in hooks.items():
        have = cur["hooks"].setdefault(event, [])
        for entry in entries:
            if any(MARK in h.get("command", "") for e in have for h in e.get("hooks", [])):
                continue
            have.append(entry)
            changed = True
    if not changed:
        log.append(f"SAME     {settings} (hooks already present)")
        return False
    log.append(f"MERGE    {settings} (+af hooks; backup first)")
    if not dry:
        if settings.is_file():
            shutil.copy2(settings, settings.with_name(settings.name + f".bak-af-{datetime.now():%Y%m%d%H%M%S}"))
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps(cur, indent=2) + "\n", encoding="utf-8")
    return True


def remove_hooks(settings: Path, log: list, dry: bool) -> None:
    if not settings.is_file():
        return
    cur = json.loads(settings.read_text(encoding="utf-8"))
    for event in list(cur.get("hooks", {})):
        cur["hooks"][event] = [e for e in cur["hooks"][event]
                               if not any(MARK in h.get("command", "") for h in e.get("hooks", []))]
        if not cur["hooks"][event]:
            del cur["hooks"][event]
    log.append(f"UNMERGE  {settings}")
    if not dry:
        shutil.copy2(settings, settings.with_name(settings.name + f".bak-af-{datetime.now():%Y%m%d%H%M%S}"))
        settings.write_text(json.dumps(cur, indent=2) + "\n", encoding="utf-8")


def install_claude(home: Path, log, dry) -> None:
    dep = FW / "deploy" / "claude"
    prev = set(load_manifest(home))
    manifest: list = []
    copy_tree(dep / "agents", home / "agents", manifest, log, dry, prev)
    copy_tree(dep / "skills", home / "skills", manifest, log, dry, prev)
    merge_hooks(home / "settings.json", log, dry)
    if not dry:
        (home / MANIFEST).write_text(json.dumps(sorted(set(manifest) | prev), indent=2), encoding="utf-8")


def install_codex(home: Path, log, dry) -> None:
    dep = FW / "deploy" / "codex"
    prev = set(load_manifest(home))
    manifest: list = []
    copy_tree(dep / "agents", home / "agents", manifest, log, dry, prev)
    copy_tree(dep / "skills", home / "skills", manifest, log, dry, prev)
    copy_tree(dep / "prompts", home / "prompts", manifest, log, dry, prev)
    if not dry:
        (home / MANIFEST).write_text(json.dumps(sorted(set(manifest) | prev), indent=2), encoding="utf-8")


def uninstall(home: Path, log, dry, claude: bool) -> None:
    for f in load_manifest(home):
        p = Path(f)
        if p.is_file():
            log.append(f"REMOVE   {p}")
            if not dry:
                p.unlink()
    if claude:
        remove_hooks(home / "settings.json", log, dry)
    if not dry and (home / MANIFEST).exists():
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
    for name, home, fn in (("claude", Path(a.claude_home), install_claude), ("codex", Path(a.codex_home), install_codex)):
        if a.only and a.only != name:
            continue
        if a.uninstall:
            uninstall(home, log, a.dry_run, name == "claude")
        else:
            fn(home, log, a.dry_run)
    print("\n".join(log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
