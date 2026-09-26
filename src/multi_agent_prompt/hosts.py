"""Per-agent-CLI provisioning for the `/prompt` integration.

`map hosts install` wires `/prompt` into whatever agent CLIs this machine
actually runs, by writing each host's command/skill template and hook script
into that host's *own* config root:

- opencode: a command file whose ``!`map pop` `` template substitution reads,
  archives, and clears the draft at prompt-build time — no hook needed.
- claude (Claude Code): a command file with an `@`-include of the staged copy,
  plus a `UserPromptExpansion` hook that runs `map pop --stage` first.
- agy (Antigravity CLI): a frontmatter-only skill (the `/prompt` trigger) plus
  a `PreInvocation` hook that pops locally and injects the result as a user
  message.
- grok (xAI Build): a flat command file whose body is a minimal read-only
  contract, plus a `UserPromptSubmit` hook that stages the pop the body reads.

Which root each host uses follows the platform this `map` runs on (Windows:
`%USERPROFILE%` / `%APPDATA%`; elsewhere: `~` / `$XDG_CONFIG_HOME`). Run it in
each shell you use — PowerShell on Windows wires the native-Windows agy, WSL
wires the WSL one, and so on.

Installer policy, deliberately conservative:
- Our files never replace *different* content without `--force`; identical
  content is a no-op (idempotent re-install), missing files are created.
- `settings.json` / `hooks.json` merges only ever *add* (or replace our own)
  entries — user hooks are never removed or reformatted beyond our key.
- JSON that isn't parseable is reported and left untouched.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

HOSTS = ("opencode", "claude", "agy", "grok")

_HOOK_DIR = "hooks"
_HOOK_SOURCE = {
    "claude": "hosts/claude/prompt-pop.py",
    "agy": "hosts/agy/prompt-pop.py",
    "grok": "hosts/grok/prompt-pop.py",
}
_COMMAND_SOURCE = {
    "opencode": "commands/opencode/prompt.md",
    "claude": "commands/claude/prompt.md",
    "agy": "commands/agy/prompt.md",
    "grok": "commands/grok/prompt.md",
}
_COMMAND_DEST = {
    "opencode": "commands/prompt.md",
    "claude": "commands/prompt.md",
    "agy": "skills/prompt/SKILL.md",
    "grok": "commands/prompt.md",
}
_HOOK_SCRIPT_NAME = "map-prompt-pop.py"
_AGY_HOOKS_KEY = "map-prompt-pop"
_GROK_HOOK_FILE = "hooks/map-prompt.json"
_TIMEOUT_S = 15


def known_host(name: str) -> bool:
    return name in HOSTS


def home_dir() -> Path:
    return Path(os.environ.get("MAP_HOSTS_HOME") or Path.home())


def on_windows() -> bool:
    return os.name == "nt"


def config_root(name: str) -> Path | None:
    home = home_dir()
    if on_windows():
        appdata = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
        roots = {
            "opencode": appdata / "opencode",
            "claude": home / ".claude",
            "agy": home / ".gemini" / "config",
            "grok": home / ".grok",
        }
    else:
        xdg = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
        roots = {
            "opencode": xdg / "opencode",
            "claude": home / ".claude",
            "agy": home / ".gemini" / "config",
            "grok": home / ".grok",
        }
    return roots.get(name)


def _payload(rel: str) -> str:
    """Read a wiring template from the package payload, falling back to the
    repo checkout (dev source): `src/multi_agent_prompt/_payload/` in the
    installed wheel mirrors `commands/` and `hosts/` (pyproject
    force-include)."""
    pkg = Path(__file__).with_name("_payload") / rel
    checkout = Path(__file__).resolve().parents[2] / rel
    for candidate in (pkg, checkout):
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    raise FileNotFoundError(f"host wiring payload missing: {rel}")


def files_for(name: str) -> list[tuple[str, str]]:
    """(destination path relative to the host root, payload source path)."""
    rels: list[tuple[str, str]] = [(_COMMAND_DEST[name], _COMMAND_SOURCE[name])]
    if name in _HOOK_SOURCE:
        rels.append((f"{_HOOK_DIR}/{_HOOK_SCRIPT_NAME}", _HOOK_SOURCE[name]))
    return rels


def hook_command(name: str, root: Path) -> str:
    """The shell command that runs a host's installed hook script."""
    del name  # same script name + layout for every hooked host
    script = root / _HOOK_DIR / _HOOK_SCRIPT_NAME
    return f'"{sys.executable}" "{script}"'


def json_spec(name: str, root: Path) -> tuple[str, object | None]:
    """(config file path relative to the host root, the JSON entry we add).

    Returns (path, None) for hosts with no config JSON (opencode, grok —
    grok's hook lives in its own file generated as the entry)."""
    if name == "claude":
        entry: dict[str, object] = {
            "hooks": {
                "UserPromptExpansion": [
                    {
                        "hooks": [
                            {"type": "command", "command": hook_command(name, root), "timeout": _TIMEOUT_S}
                        ]
                    }
                ]
            }
        }
        return "settings.json", entry
    if name == "agy":
        entry = {
            _AGY_HOOKS_KEY: {
                "PreInvocation": [
                    {"type": "command", "command": hook_command(name, root), "timeout": _TIMEOUT_S}
                ]
            }
        }
        return "hooks.json", entry
    if name == "grok":
        entry = {
            "hooks": {
                "UserPromptSubmit": [
                    {
                        "hooks": [
                            {"type": "command", "command": hook_command(name, root), "timeout": _TIMEOUT_S}
                        ]
                    }
                ]
            }
        }
        return _GROK_HOOK_FILE, entry
    return "", None


def _first_command(obj: object) -> str:
    """Recursively find the first non-empty "command" string in a hook entry
    (works for all three shapes: claude's UserPromptExpansion group, agy's
    flat hook object, and grok's UserPromptSubmit group)."""
    if isinstance(obj, dict):
        cmd = obj.get("command")
        if isinstance(cmd, str) and cmd:
            return cmd
        for value in obj.values():
            found = _first_command(value)
            if found:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _first_command(value)
            if found:
                return found
    return ""


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} has invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"{path} does not contain a JSON object")
    return value


def _merge_entry(name: str, loaded: dict, entry: object) -> dict:
    """Add our hook entry to an existing config object (never touch others)."""
    if name == "claude":
        group = _claude_group(entry)
        if group is None:
            return loaded
        hooks = loaded.setdefault("hooks", {})
        if not isinstance(hooks, dict):
            raise ValueError("settings.json 'hooks' is not an object")
        groups = hooks.setdefault("UserPromptExpansion", [])
        if not isinstance(groups, list):
            raise ValueError("settings.json 'hooks.UserPromptExpansion' is not a list")
        if not any(_first_command(g) == _first_command(group) for g in groups):
            groups.append(group)
    elif name == "agy":
        value = entry.get(_AGY_HOOKS_KEY) if isinstance(entry, dict) else None
        if isinstance(value, dict) and _first_command(loaded.get(_AGY_HOOKS_KEY)) != _first_command(value):
            loaded[_AGY_HOOKS_KEY] = value
    elif name == "grok":
        if isinstance(entry, dict):
            loaded.clear()
            loaded.update(entry)
    return loaded


def _claude_group(entry: object) -> object | None:
    """settings.json stores a *list of groups* under 'hooks.UserPromptExpansion'
    where each group is {'hooks': [{type, command, timeout}]}. Extract that
    single group from our file-shaped entry."""
    if not isinstance(entry, dict):
        return None
    groups = entry.get("hooks", {}).get("UserPromptExpansion") if isinstance(entry.get("hooks"), dict) else None
    if isinstance(groups, list) and groups:
        return groups[0]
    return None


def _drop_entry(name: str, loaded: dict, entry: object) -> dict:
    """Remove our hook entry from a config object; leave everything else."""
    if name == "claude":
        hooks = loaded.get("hooks")
        if isinstance(hooks, dict):
            groups = hooks.get("UserPromptExpansion")
            if isinstance(groups, list):
                removed = _first_command(entry)
                kept = [g for g in groups if _first_command(g) != removed]
                if len(kept) != len(groups):
                    if kept:
                        hooks["UserPromptExpansion"] = kept
                    else:
                        del hooks["UserPromptExpansion"]
                    if not hooks:
                        del loaded["hooks"]
    elif name == "agy":
        if _first_command(loaded.get(_AGY_HOOKS_KEY)) == _first_command(entry):
            del loaded[_AGY_HOOKS_KEY]
    return loaded


def _dump_json(obj: dict) -> str:
    return json.dumps(obj, indent=2) + "\n"


def _prune_empty_dirs(dest: Path, stop: Path) -> None:
    """Remove directories that uninstalling emptied, up to (not including)
    the host config root."""
    parent = dest.parent
    while parent.is_dir() and parent != stop and parent != parent.parent:
        try:
            parent.rmdir()
        except OSError:
            return
        parent = parent.parent


def install_host(name: str, root: Path, *, force: bool = False, dry_run: bool = False) -> tuple[bool, list[str]]:
    lines: list[str] = []
    ok = True
    for rel, payload_rel in files_for(name):
        dest = root / rel
        content = _payload(payload_rel)
        if dry_run:
            lines.append(f"  [dry-run] would write {dest}")
            continue
        if dest.exists():
            if dest.read_text(encoding="utf-8") == content:
                lines.append(f"  ok {dest} (up to date)")
                continue
            if not force:
                lines.append(f"  skip {dest} (exists with different content — use --force to replace)")
                ok = False
                continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        lines.append(f"  wrote {dest}")

    rel, entry = json_spec(name, root)
    if entry is not None:
        path = root / rel
        try:
            loaded = _read_json(path)
            before = copy.deepcopy(loaded)
            merged = _merge_entry(name, loaded, entry)
        except (ValueError, TypeError) as exc:
            lines.append(f"  error {path}: {exc} (left untouched)")
            return False, lines
        changed = merged != before
        if dry_run:
            lines.append(f"  [dry-run] would {'update' if changed else 'leave'} {path} (hook {'missing' if changed else 'present'})")
        elif changed:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_dump_json(merged), encoding="utf-8")
            lines.append(f"  updated {path}")
        else:
            lines.append(f"  ok {path} (hook entry already installed)")
    return ok, lines


def status_host(name: str, root: Path) -> list[str]:
    lines = [f"{name}  root: {root} ({'present' if root.is_dir() else 'not detected'})"]
    for rel, payload_rel in files_for(name):
        dest = root / rel
        if not dest.exists():
            lines.append(f"    {rel}: missing")
        elif dest.read_text(encoding="utf-8") == _payload(payload_rel):
            lines.append(f"    {rel}: installed (up to date)")
        else:
            lines.append(f"    {rel}: differs (user-modified or older install)")
    rel, entry = json_spec(name, root)
    if entry is not None:
        path = root / rel
        try:
            loaded = _read_json(path)
            before = copy.deepcopy(loaded)
            merged = _merge_entry(name, loaded, entry)
            state = "hook entry installed" if merged == before else "hook entry missing"
        except (ValueError, TypeError):
            state = "unreadable JSON (not touched)"
        lines.append(f"    {rel}: {state}")
    return lines


def uninstall_host(name: str, root: Path, *, force: bool = False, dry_run: bool = False) -> tuple[bool, list[str]]:
    lines: list[str] = []
    ok = True
    for rel, payload_rel in files_for(name):
        dest = root / rel
        if not dest.exists():
            lines.append(f"  ok {dest} (not present)")
            continue
        if dest.read_text(encoding="utf-8") == _payload(payload_rel) or force:
            if dry_run:
                lines.append(f"  [dry-run] would remove {dest}")
            else:
                dest.unlink()
                lines.append(f"  removed {dest}")
                _prune_empty_dirs(dest, root)
        else:
            lines.append(f"  skip {dest} (modified since install — use --force)")
            ok = False

    rel, entry = json_spec(name, root)
    if entry is not None:
        path = root / rel
        if name == "grok":
            if path.exists():
                if dry_run:
                    lines.append(f"  [dry-run] would remove {path}")
                else:
                    path.unlink()
                    lines.append(f"  removed {path}")
            else:
                lines.append(f"  ok {path} (not present)")
            return ok, lines
        try:
            loaded = _read_json(path)
            before = copy.deepcopy(loaded)
            dropped = _drop_entry(name, loaded, entry)
        except (ValueError, TypeError) as exc:
            lines.append(f"  error {path}: {exc} (left untouched)")
            return False, lines
        if dropped == before:
            lines.append(f"  ok {path} (no hook entry to remove)")
        elif not dropped:
            if dry_run:
                lines.append(f"  [dry-run] would remove {path}")
            else:
                path.unlink()
                lines.append(f"  removed {path}")
        else:
            if dry_run:
                lines.append(f"  [dry-run] would remove our hook entry from {path}")
            else:
                path.write_text(_dump_json(dropped), encoding="utf-8")
                lines.append(f"  removed our hook entry from {path}")
    return ok, lines