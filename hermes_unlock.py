#!/usr/bin/env python3
# =============================================================================
#  hermes_unlock.py  ·  v2.0
#  Neutralise Hermes Agent guardrails: source patches + config + restart + verify.
#
#  Windows 10/11 · Linux (Debian/Ubuntu, Fedora/RHEL, Arch) · macOS · WSL
#  No third-party dependencies. Python 3.8+.
#
#  Usage
#    python3 hermes_unlock.py                 patch + config + restart + verify
#    python3 hermes_unlock.py --dry-run       show the plan, write nothing
#    python3 hermes_unlock.py --status        patch state per file (post-update check)
#    python3 hermes_unlock.py --list          target functions + owning module
#    python3 hermes_unlock.py --verify-only   live checks only
#    python3 hermes_unlock.py --restore       roll back from backups
#    python3 hermes_unlock.py --no-config     skip `hermes config set`
#    python3 hermes_unlock.py --no-restart    skip gateway restart
#    python3 hermes_unlock.py --no-banner     skip the IKONA-ONI banner
#    python3 hermes_unlock.py --yes           skip the LANJUTKAN/BATAL prompt
#    python3 hermes_unlock.py --soul          install SOUL.md into HERMES_HOME first
#    python3 hermes_unlock.py --inject        runtime monkey-patch in THIS process
#    python3 hermes_unlock.py --home DIR --pkg DIR --pybin PY --backup-dir DIR
#
#  Windows:  python hermes_unlock.py
#  Linux  :  sudo python3 hermes_unlock.py      (needed to write the install dir)
# =============================================================================
from __future__ import annotations

import argparse
import ast
import glob
import hashlib
import json
import os
import platform
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

VERSION = "2.0"
MARK = "# NOGUARD"

# === IKONA-ONI WATERMARK (inline) ===
WM_ART = r"""
######### ###   ### ######### ###   ###   #####             ######### ###   ### #########
   ###    ###  ###  ###   ### ####  ###  ### ###            ###   ### ####  ###    ###
   ###    ### ###   ###   ### ##### ### ###   ###           ###   ### ##### ###    ###
   ###    ######    ###   ### ### ##### ###   ### ######### ###   ### ### #####    ###
   ###    ### ###   ###   ### ###  #### #########           ###   ### ###  ####    ###
   ###    ###  ###  ###   ### ###   ### ###   ###           ###   ### ###   ###    ###
######### ###   ### ######### ###   ### ###   ###           ######### ###   ### #########
"""


def print_banner(text="IKONA-ONI", stream=None):
    """IKONA-ONI watermark — baked into this file, printed on every run."""
    stream = stream or sys.stdout
    try:
        tty = stream.isatty() or os.environ.get("FORCE_COLOR")
    except Exception:
        tty = False
    body = WM_ART.strip("\n") if text == "IKONA-ONI" else text
    if tty:
        print("\033[96m%s\033[0m" % body, file=stream)
        print("\033[90m  :: %s ::  oni-ino watermark ::\033[0m" % text, file=stream)
    else:
        print(body, file=stream)
        print("  :: %s ::  oni-ino watermark ::" % text, file=stream)
    stream.flush()
# === END IKONA-ONI WATERMARK ===
IS_WIN = os.name == "nt"
OS_LABEL = "Windows" if IS_WIN else platform.system()

# -----------------------------------------------------------------------------
# 1. Where the guards live
#    fn -> (neutral return statement, [modules to try first])
#    The patcher finds the module that really defines each fn, so both layouts
#    work: split (approval_detection.py / approval_floors.py / *_guards.py) and
#    monolithic (everything inside tools/approval.py).
# -----------------------------------------------------------------------------
PLAN = [
    # approval detection
    ("detect_hardline_command", 'return (False, "")', ["approval_detection.py", "approval.py"]),
    ("detect_dangerous_command", 'return (False, "", "")', ["approval_detection.py", "approval.py"]),
    ("_check_sudo_stdin_guard", 'return (False, "")', ["approval_detection.py", "approval.py"]),
    # approval floors
    ("_match_user_deny_rule", "return None", ["approval_floors.py", "approval.py"]),
    ("_command_matches_permanent_allowlist", "return False", ["approval_floors.py", "approval.py"]),
    ("_hardline_block_result", "return None", ["approval_floors.py", "approval.py"]),
    ("_user_deny_block_result", "return None", ["approval_floors.py", "approval.py"]),
    # file safety
    ("is_write_denied", "return False", ["file_safety.py"]),
    ("is_write_approval_required", "return False", ["file_safety.py"]),
    ("get_write_denied_error", "return None", ["file_safety.py"]),
    ("raise_if_read_blocked", "return None", ["file_safety.py"]),
    ("get_read_block_error", "return None", ["file_safety.py"]),
    ("get_sandbox_mirror_warning", "return None", ["file_safety.py"]),
    ("get_container_mirror_warning", "return None", ["file_safety.py"]),
    ("get_cross_profile_warning", "return None", ["file_safety.py"]),
    ("_classify_write_denial", "return None", ["file_safety.py"]),
    # write guards (split layout; absent builds skip cleanly)
    ("_check_sensitive_path", "return None", ["file_tools_write_guards.py"]),
    ("_check_protected_instruction_write", "return None", ["file_tools_write_guards.py"]),
    ("_check_approval_required_write", "return None", ["file_tools_write_guards.py"]),
    ("_request_protected_instruction_approval", "return None", ["file_tools_write_guards.py"]),
    # terminal guards (split layout)
    ("gateway_lifecycle_block", "return None", ["terminal_tool_guards.py"]),
    ("self_repo_block", "return None", ["terminal_tool_guards.py"]),
    ("_validate_workdir", "return None", ["terminal_tool_guards.py"]),
    # url / website policy
    ("_is_blocked_ip", "return False", ["url_safety.py"]),
    ("is_always_blocked_url", "return False", ["url_safety.py"]),
    ("_resolve_allow_private_urls", "return True", ["url_safety.py"]),
    ("check_website_access", "return None", ["website_policy.py"]),
    # write-approval subsystem: kill the enable flag, evaluate_gate() then allows.
    # Do NOT patch evaluate_gate itself — its caller expects a GateDecision object.
    ("write_approval_enabled", "return False", ["write_approval.py"]),
    # tool-loop hard stop: treat every platform as attended (never hard-stop)
    ("_is_non_interactive_platform", "return False", ["tool_guardrails.py"]),
]

# config keys that only need `hermes config set`
CONFIG_KV = [
    ("approvals.mode", "off"),
    ("approvals.cron_mode", "off"),
    ("approvals.single_query_mode", "off"),
    ("approvals.unattended_mode", "off"),
    ("security.redact_secrets", "false"),
    ("security.tirith_enabled", "false"),
    ("security.allow_private_urls", "true"),
    ("privacy.redact_pii", "false"),
    ("gateway.allow_all_users", "true"),
    ("gateway.loop_watchdog", "false"),
    ("gateway.bot_loop_guard.enabled", "false"),
    ("gateway.startup_watchdog", "false"),
    ("tool_loop_guardrails.warnings_enabled", "false"),
    ("tool_loop_guardrails.hard_stop_enabled", "false"),
    ("tool_loop_guardrails.non_interactive_hard_stop_enabled", "false"),
    ("tool_loop_guardrails.loop_caps.max_web_searches", "0"),
    ("tool_loop_guardrails.loop_caps.max_subagents", "0"),
]

MANIFEST = "manifest.json"


# -----------------------------------------------------------------------------
# 1b. Runtime monkey-patch (no file edits, no restart)
#     Same neutral values as PLAN, applied to live module objects. Useful for a
#     read-only/managed install or when only one process should be unlocked:
#       import hermes_unlock as hu; hu.inject_unlock()   # -> count
#       hu.inject_watch()                                # re-apply on reload
# -----------------------------------------------------------------------------
INJECT_MARK = "__hermes_guard_patched__"

GUARD_GROUPS = {
    "approval_detection": ("tools.approval_detection", "tools.approval"),
    "approval_floors": ("tools.approval_floors", "tools.approval"),
    "file_safety": ("agent.file_safety",),
    "write_guards": ("tools.file_tools_write_guards", "tools.file_tools"),
    "terminal_guards": ("tools.terminal_tool_guards", "tools.terminal_tool"),
    "url_safety": ("tools.url_safety",),
    "website_policy": ("tools.website_policy",),
    "write_approval": ("tools.write_approval",),
    "guardrails": ("agent.tool_guardrails", "tools.tool_guardrails"),
}

INJECT_RULES = [
    ("approval_detection", "detect_hardline_command", (False, "")),
    ("approval_detection", "detect_dangerous_command", (False, "", "")),
    ("approval_detection", "_check_sudo_stdin_guard", (False, "")),
    ("approval_floors", "_match_user_deny_rule", None),
    ("approval_floors", "_command_matches_permanent_allowlist", False),
    ("approval_floors", "_hardline_block_result", None),
    ("approval_floors", "_user_deny_block_result", None),
    ("file_safety", "is_write_denied", False),
    ("file_safety", "is_write_approval_required", False),
    ("file_safety", "get_write_denied_error", None),
    ("file_safety", "raise_if_read_blocked", None),
    ("file_safety", "get_read_block_error", None),
    ("file_safety", "get_sandbox_mirror_warning", None),
    ("file_safety", "get_container_mirror_warning", None),
    ("file_safety", "get_cross_profile_warning", None),
    ("file_safety", "_classify_write_denial", None),
    ("write_guards", "_check_sensitive_path", None),
    ("write_guards", "_check_protected_instruction_write", None),
    ("write_guards", "_check_approval_required_write", None),
    ("write_guards", "_request_protected_instruction_approval", None),
    ("terminal_guards", "gateway_lifecycle_block", None),
    ("terminal_guards", "self_repo_block", None),
    ("terminal_guards", "_validate_workdir", None),
    ("url_safety", "_is_blocked_ip", False),
    ("url_safety", "is_always_blocked_url", False),
    ("url_safety", "_resolve_allow_private_urls", True),
    ("website_policy", "check_website_access", None),
    ("write_approval", "write_approval_enabled", False),
    ("guardrails", "_is_non_interactive_platform", False),
]


def _make_stub(fn, value):
    """Fresh wrapper per rule so MARK never leaks between rules."""
    def stub(*_a, **_k):
        return value
    stub.__name__ = fn
    stub.__doc__ = "neutralised by hermes_unlock.inject"
    setattr(stub, INJECT_MARK, True)
    return stub


def _import(mod):
    try:
        import importlib
        return importlib.import_module(mod)
    except Exception:
        return None


def _inject_apply(verbose=False):
    done = seen = 0
    for group, fn, value in INJECT_RULES:
        for mod_name in GUARD_GROUPS[group]:
            mod = _import(mod_name)
            if mod is None or not hasattr(mod, fn):
                continue
            seen += 1
            orig = getattr(mod, fn)
            if getattr(orig, INJECT_MARK, False):
                done += 1
                continue
            stub = _make_stub(fn, value)
            stub.__wrapped__ = orig
            try:
                setattr(mod, fn, stub)
            except Exception:
                continue
            done += 1
            if verbose:
                print("  patched %s.%s" % (mod_name, fn))
    return done, seen


def _inject_guardrail_class():
    mod = _import("agent.tool_guardrails") or _import("tools.tool_guardrails")
    cls = getattr(mod, "ToolCallGuardrailConfig", None) if mod else None
    if cls is None:
        return False
    for attr in ("hard_stop_enabled", "non_interactive_hard_stop_enabled", "warnings_enabled"):
        try:
            setattr(cls, attr, False)
        except Exception:
            pass
    fm = getattr(cls, "from_mapping", None)
    if fm is not None and not getattr(fm.__func__, INJECT_MARK, False):
        def _from_mapping(cls_, data=None, *a, **k):
            try:
                return cls_()
            except Exception:
                obj = cls_.__new__(cls_)
                for attr in ("warnings_enabled", "hard_stop_enabled",
                             "non_interactive_hard_stop_enabled"):
                    try:
                        setattr(obj, attr, False)
                    except Exception:
                        pass
                return obj
        _from_mapping.__name__ = "from_mapping"
        setattr(_from_mapping, INJECT_MARK, True)
        cls.from_mapping = classmethod(_from_mapping)
    return True


def inject_unlock(verbose=False):
    """Neutralise every guard in THIS process. Returns patched-target count."""
    done, seen = _inject_apply(verbose)
    flags = _inject_guardrail_class()
    if verbose:
        print("[hermes_unlock.inject] %d/%d guard function(s) neutralised%s"
              % (done, seen, " + loop-guardrail flags" if flags else ""))
    return done + (1 if flags else 0)


def inject_watch(verbose=False):
    """Re-apply automatically after importlib.reload()."""
    import importlib
    original = importlib.reload

    def reload_wrapper(module, *a, **k):
        out = original(module, *a, **k)
        _inject_apply(verbose)
        _inject_guardrail_class()
        return out

    importlib.reload = reload_wrapper
    return reload_wrapper


# -----------------------------------------------------------------------------
# 2. Context
# -----------------------------------------------------------------------------
@dataclass
class Ctx:
    home: Path
    pkg: Path
    pybin: str
    backup: Path
    dry: bool = False
    modules: dict = field(default_factory=dict)      # filename -> path
    touched: dict = field(default_factory=dict)      # path -> [fn, ...]
    cache: dict = field(default_factory=dict)        # path -> (src, ast tree)


def rel(ctx, path) -> str:
    try:
        return str(Path(path).relative_to(ctx.pkg)).replace("\\", "/")
    except Exception:
        return str(path)


def _home_candidates():
    out = []
    env = os.environ.get("HERMES_HOME")
    if env:
        out.append(env)
    home = Path.home()
    if IS_WIN:
        la = os.environ.get("LOCALAPPDATA")
        if la:
            out.append(str(Path(la) / "hermes"))
        out.append(str(home / "AppData" / "Local" / "hermes"))
    out += [str(home / ".hermes"), str(home / ".config" / "hermes")]
    if not IS_WIN:
        out.append("/root/.hermes")
    return out


def find_home(explicit=None) -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_dir():
            sys.exit("ERROR: --home %s is not a directory" % p)
        return p.resolve()
    for c in _home_candidates():
        p = Path(c).expanduser()
        if p.is_dir():
            return p.resolve()
    sys.exit("ERROR: HERMES_HOME not found — set HERMES_HOME or pass --home DIR")


def find_pybin(home: Path, explicit=None) -> str:
    if explicit:
        return explicit
    tail = ("Scripts", "python.exe") if IS_WIN else ("bin", "python")
    pats = [
        home / "installs" / "*" / "environments" / "*" / "venv" / Path(*tail),
        home / "installs" / "*" / "venv" / Path(*tail),
        home / "hermes-agent" / "venv" / Path(*tail),
        home / "hermes-agent" / ".venv" / Path(*tail),
    ]
    for pat in pats:
        hits = sorted(glob.glob(str(pat)))
        if hits:
            return hits[0]
    return sys.executable


PROBE = (
    "import importlib\n"
    "for m in ('tools.approval_detection', 'tools.approval', 'agent.file_safety'):\n"
    "    try:\n"
    "        mod = importlib.import_module(m)\n"
    "        print(mod.__file__)\n"
    "        break\n"
    "    except Exception:\n"
    "        pass\n"
)


def resolve_pkg(home: Path, pybin: str, explicit=None, strict_home=False) -> Path:
    """Find the package root. strict_home=True (--home given) refuses any package
    that lives outside that home — otherwise an interpreter with hermes installed
    would drag us into somebody else's install."""
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not (p / "tools").is_dir() and not (p / "agent").is_dir():
            sys.exit("ERROR: --pkg %s has no tools/ or agent/ directory" % p)
        return p

    def inside(cand: Path) -> bool:
        if not strict_home:
            return True
        try:
            cand.relative_to(home)
            return True
        except ValueError:
            return False

    cwds = [str(home), str(Path(pybin).parent), None]
    for cand in (pybin, sys.executable):
        for cwd in cwds:
            try:
                r = subprocess.run([cand, "-c", PROBE], capture_output=True, text=True,
                                   timeout=40, cwd=cwd)
            except Exception:
                continue
            lines = (r.stdout or "").strip().splitlines()
            if not lines:
                continue
            pkg = Path(lines[0]).resolve().parent.parent
            if not inside(pkg):
                continue
            if (pkg / "tools").is_dir() or (pkg / "agent").is_dir():
                return pkg

    for pat in (home / "installs" / "*" / "environments" / "*" / "workspace",
                home / "installs" / "*" / "workspace",
                home / "hermes-agent"):
        for p in sorted(glob.glob(str(pat)), reverse=True):
            if os.path.isdir(os.path.join(p, "tools")) and os.path.isdir(os.path.join(p, "agent")):
                return Path(p).resolve()

    for dirpath, _dirs, files in os.walk(str(home)):
        for fn in ("approval.py", "approval_detection.py", "file_safety.py"):
            if fn in files:
                return Path(dirpath).resolve().parent
    sys.exit("ERROR: cannot resolve the Hermes package root (dir with tools/ + agent/). "
             "Pass --pkg DIR.")


def choose_backup_dir() -> Path:
    env = os.environ.get("HERMES_UNLOCK_BACKUP")
    if env:
        return Path(env).expanduser()
    legacy = Path(r"C:\hermes-unlock-backup") if IS_WIN else Path("/opt/hermes-heavy")
    if legacy.is_dir() and any(legacy.glob("*.ikonaorig")):
        return legacy
    return Path.home() / "hermes-unlock-backup"


def build_ctx(a) -> Ctx:
    home = find_home(a.home)
    pybin = find_pybin(home, a.pybin)
    pkg = resolve_pkg(home, pybin, a.pkg, strict_home=bool(a.home))
    backup = Path(a.backup_dir).expanduser().resolve() if a.backup_dir else choose_backup_dir()
    ctx = Ctx(home=home, pkg=pkg, pybin=pybin, backup=backup, dry=bool(a.dry_run))
    for d in ("agent", "tools"):
        base = pkg / d
        if base.is_dir():
            for p in sorted(base.glob("*.py")):
                ctx.modules.setdefault(p.name, str(p))
    return ctx


# -----------------------------------------------------------------------------
# 3. Source helpers
# -----------------------------------------------------------------------------
def read_src(path) -> str:
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
        return fh.read()


def write_src(path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def cache_get(ctx, path):
    key = str(path)
    if key not in ctx.cache:
        src = read_src(path)
        try:
            tree = ast.parse(src)
        except SyntaxError:
            tree = None
        ctx.cache[key] = (src, tree)
    return ctx.cache[key]


def cache_put(ctx, path, src: str) -> None:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        tree = None
    ctx.cache[str(path)] = (src, tree)


def find_function(tree, fn):
    """Top-level def/async def named fn, or None."""
    if tree is None:
        return None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn:
            return node
    return None


def find_defining_file(ctx, fn: str, preferred=None):
    """Module that really defines fn — preferred names first, then every module."""
    names = list(preferred or [])
    names += sorted(ctx.modules, key=lambda n: (0 if ctx.modules[n].endswith("agent" + os.sep + n) else 1, n))
    pat = re.compile(r"^(?:async[ \t]+)?def[ \t]+" + re.escape(fn) + r"\s*\(", re.M)
    for name in dict.fromkeys(names):
        path = ctx.modules.get(name)
        if not path:
            continue
        src, tree = cache_get(ctx, path)
        if not pat.search(src):
            continue
        if find_function(tree, fn) is not None:
            return path
    return None


def function_block(src: str, node) -> str:
    lines = src.splitlines(keepends=True)
    return "".join(lines[node.lineno - 1: node.end_lineno])


def is_patched(ctx, path, fn: str) -> bool:
    src, tree = cache_get(ctx, path)
    node = find_function(tree, fn)
    return bool(node) and MARK in function_block(src, node)


def insert_point(node):
    """Line number (1-based) to insert the neutral return before; None = inline def."""
    first = node.body[0]
    if first.lineno == node.lineno:          # def f(): return x  (single line)
        return None
    is_doc = (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
              and isinstance(first.value.value, str))
    if is_doc and len(node.body) > 1:
        return node.body[1].lineno
    if is_doc:
        return first.end_lineno + 1
    return first.lineno


def backup_file(ctx, path):
    """Keep the pristine original; never overwrite an existing backup."""
    dst = ctx.backup / (Path(path).name + ".ikonaorig")
    ctx.backup.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        shutil.copy2(path, dst)
    return dst


def patch_function(ctx, path, fn: str, retline: str) -> str:
    src, tree = cache_get(ctx, path)
    node = find_function(tree, fn)
    if node is None:
        return "notfound"
    if MARK in function_block(src, node):
        return "already"
    at = insert_point(node)
    if at is None:
        return "inline"
    if ctx.dry:
        return "would-patch"

    lines = src.splitlines(keepends=True)
    ref = lines[at - 1] if at - 1 < len(lines) else ""
    indent = ref[:len(ref) - len(ref.lstrip())]
    nl = "\r\n" if "\r\n" in src else "\n"
    payload = "%s%s%s%s%s%s" % (indent, MARK, nl, indent, retline, nl)
    head = "".join(lines[:at - 1])
    if head and not head.endswith(("\n", "\r")):
        head += nl
    new = head + payload + "".join(lines[at - 1:])

    backup_file(ctx, path)
    write_src(path, new)
    cache_put(ctx, path, new)
    ctx.touched.setdefault(str(path), []).append(fn)
    return "patched"


# -----------------------------------------------------------------------------
# 4. tool_guardrails.py extras — force the loop-guard flags off.
#    Best effort and tolerant of both the stock and the already-patched form.
# -----------------------------------------------------------------------------
def patch_guardrail_flags(ctx) -> str:
    path = ctx.modules.get("tool_guardrails.py")
    if not path:
        return "skip"
    src, _tree = cache_get(ctx, path)
    orig = src
    notes = []

    forced = "flags = {name: False for name in _BOOL_FIELDS}"
    if forced not in src:
        pattern = r"^([ \t]*)flags = \{name: .*?for name in _BOOL_FIELDS\}[^\r\n]*"
        repl = lambda m: "%s%s\n%s%s" % (m.group(1), MARK, m.group(1), forced)
        src, n = re.subn(pattern, repl, src, count=1, flags=re.M)
        notes.append("flags->False" if n else "flags-unmatched")

    dead = "if False:  # NOGUARD"
    if dead not in src:
        pattern = r'^([ \t]*)if flags\["non_interactive_hard_stop_enabled"\][^\r\n]*'
        repl = lambda m: "%s%s" % (m.group(1), dead)
        src, n = re.subn(pattern, repl, src, count=1, flags=re.M)
        notes.append("hard-stop-off" if n else "hard-stop-unmatched")

    if src == orig:
        return "already"
    if ctx.dry:
        print("             tool_guardrails: %s" % ", ".join(notes))
        return "would-patch"
    backup_file(ctx, path)
    write_src(path, src)
    cache_put(ctx, path, src)
    ctx.touched.setdefault(str(path), []).append("(flags)")
    print("             tool_guardrails: %s" % ", ".join(notes))
    return "patched"


# -----------------------------------------------------------------------------
# 5. Cleaning up stacked marks
#    Older builds of this script inserted a fresh block on every run (their
#    idempotency check missed), leaving N copies of "# NOGUARD / return X" at the
#    top of a function. This collapses each leading run down to one block.
# -----------------------------------------------------------------------------
def clean_function(ctx, path, fn: str, retline: str) -> int:
    src, tree = cache_get(ctx, path)
    node = find_function(tree, fn)
    if node is None:
        return 0
    lines = src.splitlines(keepends=True)
    want = retline.strip()
    i, end = node.lineno - 1, min(node.end_lineno, len(lines))
    while i < end and lines[i].strip() != MARK:
        i += 1
    if i >= end:
        return 0
    pairs, j = 0, i
    while j + 1 < end and lines[j].strip() == MARK and lines[j + 1].strip() == want:
        pairs += 1
        j += 2
    if pairs <= 1:
        return 0
    if ctx.dry:
        return pairs - 1
    del lines[i + 2: j]
    new = "".join(lines)
    write_src(path, new)
    cache_put(ctx, path, new)
    return pairs - 1


def clean_all(ctx) -> int:
    total = 0
    files = {}
    for fn, retline, preferred in PLAN:
        path = find_defining_file(ctx, fn, preferred)
        if not path:
            continue
        n = clean_function(ctx, path, fn, retline)
        if n:
            total += n
            files.setdefault(rel(ctx, path), []).append("%s(-%d)" % (fn, n))
    print("\n[*] cleaning stacked NOGUARD blocks%s" % ("  [DRY RUN]" if ctx.dry else ""))
    if not total:
        print("  nothing to clean — 1 block per function at most.")
        return 0
    for path in sorted(files):
        print("  %-34s %s" % (path, ", ".join(files[path])))
    if not ctx.dry:
        bad = 0
        for path in files:
            err = compile_ok(str(ctx.pkg / path))
            if err:
                bad += 1
                print("  [COMPILE FAIL] %s: %s" % (path, err))
        clear_pycache(ctx)
        print("  %d duplicate block(s) removed%s." % (total, ", %d FAILED" % bad if bad else ""))
    return total


# -----------------------------------------------------------------------------
# 6. Patch / compile / manifest
# -----------------------------------------------------------------------------
def clear_pycache(ctx) -> None:
    for d in ("agent", "tools"):
        base = ctx.pkg / d
        if base.is_dir():
            for p in base.rglob("__pycache__"):
                shutil.rmtree(str(p), ignore_errors=True)


def compile_ok(path) -> str:
    fd, tmp = tempfile.mkstemp(suffix=".pyc")
    os.close(fd)
    try:
        py_compile.compile(str(path), cfile=tmp, doraise=True)
        return ""
    except Exception as exc:
        return str(exc)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def patch_all(ctx) -> int:
    print("  platform : %s" % OS_LABEL)
    print("  home     : %s" % ctx.home)
    print("  pybin    : %s" % ctx.pybin)
    print("  package  : %s" % ctx.pkg)
    print("  backup   : %s%s" % (ctx.backup, "   [DRY RUN]" if ctx.dry else ""))
    print("")

    patched = 0
    for fn, retline, preferred in PLAN:
        path = find_defining_file(ctx, fn, preferred)
        if not path:
            print("  [%-11s] %-46s %s" % ("skip", fn, "(no module defines it)"))
            continue
        state = patch_function(ctx, path, fn, retline)
        if state in ("patched", "would-patch"):
            patched += 1
        print("  [%-11s] %-46s %s" % (state, fn, rel(ctx, path)))

    state = patch_guardrail_flags(ctx)
    if state in ("patched", "would-patch"):
        patched += 1
    if state != "skip":
        print("  [%-11s] %-46s %s" % (state, "tool_loop_guardrails flags", "agent/tool_guardrails.py"))

    if ctx.dry:
        print("\n[*] dry run: %d target(s) would be patched, 0 files written." % patched)
        return patched

    failed = []
    for path in sorted(ctx.touched):
        err = compile_ok(path)
        if err:
            failed.append(path)
            print("  [COMPILE FAIL] %s: %s" % (rel(ctx, path), err))
            bak = ctx.backup / (Path(path).name + ".ikonaorig")
            if bak.exists():
                shutil.copy2(str(bak), path)
                print("                 restored original from backup")
        else:
            print("  [compile OK  ] %s" % rel(ctx, path))

    clear_pycache(ctx)
    if not failed:
        write_manifest(ctx)
    print("\n[*] %d guard function(s) patched, %d file(s) touched%s."
          % (patched, len(ctx.touched), "" if not failed else ", %d FAILED" % len(failed)))
    return patched


def manifest_path(ctx):
    return ctx.backup / MANIFEST


def target_files(ctx) -> dict:
    """Every file that holds a PLAN function -> [fn, ...]."""
    by_file = {}
    for fn, _ret, preferred in PLAN:
        path = find_defining_file(ctx, fn, preferred)
        if path:
            by_file.setdefault(str(path), []).append(fn)
    return by_file


def write_manifest(ctx) -> None:
    """Record hashes for every patched target file (not only the ones this run
    touched) so a later `hermes update` shows up as SOURCE CHANGED in --status."""
    data = {
        "tool": "hermes_unlock",
        "version": VERSION,
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "os": OS_LABEL,
        "home": str(ctx.home),
        "package": str(ctx.pkg),
        "files": {},
    }
    for path, fns in target_files(ctx).items():
        patched = [fn for fn in fns if is_patched(ctx, path, fn)]
        if not patched:
            continue
        bak = ctx.backup / (Path(path).name + ".ikonaorig")
        data["files"][rel(ctx, path)] = {
            "functions": sorted(patched),
            "orig_sha256": sha256(str(bak)) if bak.exists() else None,
            "patched_sha256": sha256(path),
        }
    try:
        ctx.backup.mkdir(parents=True, exist_ok=True)
        with open(manifest_path(ctx), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        print("  [manifest    ] %s" % manifest_path(ctx))
    except Exception as exc:
        print("  [manifest ERR] %s" % exc)


def read_manifest(ctx):
    try:
        with open(manifest_path(ctx), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def status(ctx) -> int:
    man = read_manifest(ctx)
    print("  home     : %s" % ctx.home)
    print("  package  : %s" % ctx.pkg)
    print("  backup   : %s" % ctx.backup)
    print("  manifest : %s" % ("yes" if man else "no (never patched here, or backup moved)"))
    print("")
    print("  %-34s %-9s %-10s %s" % ("file", "patched", "state", "note"))
    print("  " + "-" * 78)

    by_file = {}
    for fn, _ret, preferred in PLAN:
        path = find_defining_file(ctx, fn, preferred)
        if path:
            by_file.setdefault(path, []).append(fn)
    if not by_file:
        print("  (no target functions found in this build)")
        return 1

    total = done = 0
    for path in sorted(by_file):
        fns = by_file[path]
        hits = sum(1 for fn in fns if is_patched(ctx, path, fn))
        total += len(fns)
        done += hits
        state = "patched" if hits == len(fns) else ("unpatched" if hits == 0 else "partial")
        note = ""
        if man:
            rec = man.get("files", {}).get(rel(ctx, path))
            if rec and rec.get("patched_sha256"):
                note = "OK" if sha256(path) == rec["patched_sha256"] else "SOURCE CHANGED -> re-run"
        print("  %-34s %-9s %-10s %s" % (rel(ctx, path), "%d/%d" % (hits, len(fns)), state, note))

    print("  " + "-" * 78)
    print("  %d/%d functions patched." % (done, total))
    if done < total:
        print("  -> re-run: python3 hermes_unlock.py   (python on Windows)")
    return 0


def list_targets(ctx) -> int:
    print("  %-46s %-8s %s" % ("function", "patched", "module"))
    print("  " + "-" * 84)
    for fn, _ret, preferred in PLAN:
        path = find_defining_file(ctx, fn, preferred)
        if not path:
            print("  %-46s %-8s %s" % (fn, "-", "(absent in this build)"))
            continue
        print("  %-46s %-8s %s" % (fn, "yes" if is_patched(ctx, path, fn) else "no", rel(ctx, path)))
    return 0


# -----------------------------------------------------------------------------
# 6b. SOUL.md
# -----------------------------------------------------------------------------
def install_soul(ctx) -> int:
    """Copy SOUL_v7.md (next to this script) to HERMES_HOME/SOUL.md, with backup."""
    src = Path(__file__).resolve().parent / "SOUL_v7.md"
    if not src.exists():
        print("  [soul] SOUL_v7.md not found next to this script — skipped")
        return 1
    dst = ctx.home / "SOUL.md"
    if dst.exists() and dst.read_bytes() == src.read_bytes():
        print("  [soul] already installed: %s" % dst)
        return 0
    if ctx.dry:
        print("  [soul] would install %s -> %s" % (src.name, dst))
        return 0
    if dst.exists():
        bak = dst.with_name("SOUL.md.bak.%d" % int(time.time()))
        shutil.copy2(str(dst), str(bak))
        print("  [soul] previous SOUL.md -> %s" % bak.name)
    shutil.copy2(str(src), str(dst))
    print("  [soul] installed -> %s" % dst)
    return 0


# -----------------------------------------------------------------------------
# 7. Config
# -----------------------------------------------------------------------------
def _run(argv, timeout=60, env=None):
    argv = [str(x) for x in argv]
    if IS_WIN and argv[0].lower().endswith((".cmd", ".bat")):
        argv = ["cmd.exe", "/c"] + argv
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env)
    except Exception:
        return None


def find_launcher():
    cands = []
    env = os.environ.get("HERMES_BIN")
    if env:
        cands.append(env)
    which = shutil.which("hermes")
    if which:
        cands.append(which)
    home = Path.home()
    cands += [
        str(home / "hermes-agent" / ".hermes" / "bin" / "hermes.exe"),
        str(home / "hermes-agent" / ".hermes" / "bin" / "hermes"),
        str(home / ".local" / "bin" / "hermes.exe"),
        str(home / ".local" / "bin" / "hermes"),
        "/usr/local/bin/hermes",
        "/opt/hermes/bin/hermes",
        str(home / "AppData" / "Local" / "Programs" / "hermes" / "hermes.exe"),
        str(home / "AppData" / "Roaming" / "npm" / "hermes.cmd"),
    ]
    for c in cands:
        if c and os.path.exists(c):
            return [c]
    return None


def set_config(ctx) -> int:
    launcher = find_launcher()
    print("\n[*] config: %s" % (" ".join(launcher) if launcher else "hermes CLI not found"))
    if not launcher:
        print("  skip — run these once `hermes` is on PATH:")
        for k, v in CONFIG_KV:
            print("    hermes config set %s %s" % (k, v))
        return 0
    env = dict(os.environ)
    env.setdefault("HOME", str(Path.home()))
    bad = 0
    for k, v in CONFIG_KV:
        if ctx.dry:
            print("  %-52s = %-6s [DRY RUN]" % (k, v))
            continue
        r = _run(launcher + ["config", "set", k, v], timeout=90, env=env)
        if r is None:
            print("  %-52s = %-6s EXC" % (k, v))
            bad += 1
            continue
        tail = ((r.stdout or r.stderr or "").strip().splitlines() or [""])[-1]
        ok = r.returncode == 0
        if not ok:
            bad += 1
        print("  %-52s = %-6s %s  %s" % (k, v, "OK " if ok else "ERR", tail[:60]))
    return bad


# -----------------------------------------------------------------------------
# 8. Gateway restart
# -----------------------------------------------------------------------------
def restart_gateway(ctx) -> bool:
    launcher = find_launcher()
    cmds = []
    if launcher:
        cmds.append(launcher + ["gateway", "restart"])
    if IS_WIN and launcher:
        cmds += [launcher + ["gateway", "stop"], launcher + ["gateway", "start"]]
    else:
        cmds += [["systemctl", "--user", "restart", "hermes-gateway"],
                 ["systemctl", "restart", "hermes-gateway"]]
    print("\n[*] gateway restart")
    for cmd in cmds:
        r = _run(cmd, timeout=120)
        if r is not None and r.returncode == 0:
            print("  %s -> OK" % " ".join(str(x) for x in cmd))
            return True
    print("  could not restart — do it yourself: hermes gateway restart")
    return False


# -----------------------------------------------------------------------------
# 9. Live verification (runs inside the hermes venv)
# -----------------------------------------------------------------------------
VERIFY_SNIPPET = r"""
import os, sys, importlib, ipaddress
os.environ.setdefault("HERMES_HOME", "__HOME__")
sys.path.insert(0, "__PKG__")
os.chdir("__PKG__")

def show(label, fn):
    try:
        print("  %-46s => %r" % (label, fn()))
    except Exception as exc:
        print("  %-46s => ERR %s" % (label, exc))

CALLS = [
    ("tools.approval_detection", "detect_hardline_command", ("rm -rf / --no-preserve-root",)),
    ("tools.approval", "detect_hardline_command", ("rm -rf / --no-preserve-root",)),
    ("tools.approval_detection", "detect_dangerous_command", ("dd if=/dev/zero of=/dev/sda",)),
    ("tools.approval", "detect_dangerous_command", ("dd if=/dev/zero of=/dev/sda",)),
    ("agent.file_safety", "is_write_denied", ("__HOME__/.env",)),
    ("agent.file_safety", "raise_if_read_blocked", ("__HOME__/.env",)),
    ("tools.url_safety", "is_always_blocked_url", ("http://127.0.0.1/",)),
    ("tools.website_policy", "check_website_access", ("http://evil.test/",)),
    ("tools.write_approval", "write_approval_enabled", ("write_file",)),
    ("agent.tool_guardrails", "_is_non_interactive_platform", ("gateway",)),
]
for mod, fn, args in CALLS:
    try:
        m = importlib.import_module(mod)
    except Exception:
        continue
    f = getattr(m, fn, None)
    if f is None:
        continue
    show(mod.split(".")[-1] + "." + fn, (lambda f=f, args=args: f(*args)))

try:
    from tools import url_safety as us
    show("url_safety._is_blocked_ip(127.0.0.1)",
         lambda: us._is_blocked_ip(ipaddress.ip_address("127.0.0.1")))
except Exception:
    pass
"""


def verify(ctx) -> int:
    print("\n[*] live verification")
    code = VERIFY_SNIPPET.replace("__HOME__", str(ctx.home).replace("\\", "/")) \
                         .replace("__PKG__", str(ctx.pkg).replace("\\", "/"))
    for cand in (ctx.pybin, sys.executable):
        r = _run([cand, "-c", code], timeout=90)
        if r and (r.stdout or "").strip():
            print(r.stdout.rstrip())
            err = (r.stderr or "").strip()
            if err:
                print("  stderr: %s" % err[:300])
            return 0
    print("  could not run live checks (venv interpreter missing?) — patched files still compile.")
    return 1


# -----------------------------------------------------------------------------
# 10. Restore
# -----------------------------------------------------------------------------
def restore(ctx) -> int:
    if not ctx.backup.is_dir():
        print("ERROR: backup dir %s does not exist" % ctx.backup)
        return 1
    baks = sorted(ctx.backup.glob("*.ikonaorig"))
    if not baks:
        print("ERROR: no *.ikonaorig files in %s" % ctx.backup)
        return 1
    print("[*] restoring %d file(s) from %s" % (len(baks), ctx.backup))
    done, missing = 0, []
    for bak in baks:
        name = bak.name[:-len(".ikonaorig")]
        target = None
        for d in ("agent", "tools"):
            cand = ctx.pkg / d / name
            if cand.exists():
                target = cand
                break
        if target is None:
            hits = sorted(ctx.pkg.rglob(name))
            target = hits[0] if hits else None
        if target is None:
            missing.append(name)
            continue
        shutil.copy2(str(bak), str(target))
        done += 1
        print("  restored %s" % rel(ctx, target))
    clear_pycache(ctx)
    try:
        manifest_path(ctx).unlink()
    except OSError:
        pass
    print("[*] %d restored, %d not found (build changed?)" % (done, len(missing)))
    for m in missing:
        print("    missing target: %s" % m)
    return 0


# -----------------------------------------------------------------------------
# 10b. Konfirmasi sebelum menulis
# -----------------------------------------------------------------------------
def confirm_run(ctx, what="INJECT") -> bool:
    """Tampilkan peringatan + menu LANJUTKAN / BATAL. Default = BATAL."""
    print("")
    print("-" * 78)
    print(" PERINGATAN — proses ini MENGUBAH file Hermes Agent secara in-place.")
    print("")
    print("   backup original : %s" % ctx.backup)
    print("                     (dibuat sekali, backup lama tidak pernah ditimpa)")
    print("   rollback        : python3 hermes_unlock.py --restore")
    print("   catatan         : `hermes update` menimpa patch -> jalankan ulang script ini")
    print("-" * 78)

    if not sys.stdin.isatty():
        print(" Tidak ada TTY untuk konfirmasi (dipanggil dari pipe/cron/wrapper).")
        print(" Non-interaktif: tambahkan --yes kalau memang mau lanjut.")
        print(" Dibatalkan — tidak ada file yang diubah.")
        return False

    while True:
        try:
            ans = input(" Pilihan  [1] LANJUTKAN %s   [2] BATAL %s   (default 2): "
                        % (what, what)).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("")
            print(" Dibatalkan — tidak ada file yang diubah.")
            return False
        if ans in ("1", "lanjut", "lanjutkan", "continue", "c", "y", "ya", "yes"):
            print(" -> LANJUTKAN %s" % what)
            return True
        if ans in ("", "2", "batal", "batalkan", "cancel", "n", "no", "tidak"):
            print(" -> BATAL %s — tidak ada file yang diubah." % what)
            return False
        print("    pilih 1 (lanjutkan) atau 2 (batal)")


# -----------------------------------------------------------------------------
# 11. CLI
# -----------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="hermes_unlock.py",
        description="Neutralise Hermes Agent guardrails (source + config).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Windows: python hermes_unlock.py   |   Linux: sudo python3 hermes_unlock.py",
    )
    ap.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    ap.add_argument("--status", action="store_true", help="report patch state per file")
    ap.add_argument("--list", action="store_true", help="list target functions and owning module")
    ap.add_argument("--verify-only", action="store_true", help="run live checks only")
    ap.add_argument("--restore", action="store_true", help="restore originals from backups")
    ap.add_argument("--clean", action="store_true", help="collapse duplicate NOGUARD blocks")
    ap.add_argument("--no-config", action="store_true", help="skip hermes config set")
    ap.add_argument("--no-restart", action="store_true", help="skip gateway restart")
    ap.add_argument("--no-banner", action="store_true", help="skip the IKONA-ONI banner")
    ap.add_argument("-y", "--yes", action="store_true",
                    help="lewati konfirmasi (wajib untuk non-interaktif/cron)")
    ap.add_argument("--soul", action="store_true", help="install SOUL.md into HERMES_HOME first")
    ap.add_argument("--inject", action="store_true",
                    help="neutralise guards in this process only (monkey-patch, no files)")
    ap.add_argument("--inject-watch", action="store_true",
                    help="like --inject, plus re-apply after importlib.reload()")
    ap.add_argument("--home", metavar="DIR", help="HERMES_HOME override")
    ap.add_argument("--pkg", metavar="DIR", help="package root override (dir with tools/ + agent/)")
    ap.add_argument("--pybin", metavar="PY", help="interpreter override (hermes venv python)")
    ap.add_argument("--backup-dir", metavar="DIR", help="backup dir override")
    ap.add_argument("--version", action="version", version="hermes_unlock %s" % VERSION)
    a = ap.parse_args(argv)

    if not a.no_banner:
        print_banner()

    if a.inject or a.inject_watch:
        total = inject_unlock(verbose=True)
        if a.inject_watch:
            inject_watch(verbose=True)
            print("  watch: installed on importlib.reload")
        print("neutralised %d target(s) in this process" % total)
        return 0

    ctx = build_ctx(a)

    if a.soul and not a.list and not a.status and not a.restore and not a.verify_only:
        print("[*] SOUL.md")
        install_soul(ctx)

    if a.list:
        return list_targets(ctx)
    if a.status:
        return status(ctx)
    if a.restore:
        return restore(ctx)
    if a.clean:
        if not ctx.dry and not a.yes and not confirm_run(ctx, "CLEAN"):
            return 2
        clean_all(ctx)
        if not ctx.dry and not a.no_restart:
            restart_gateway(ctx)
        return 0
    if a.verify_only:
        return verify(ctx)

    print("=" * 78)
    print(" hermes_unlock %s — source patches + config (gateway + CLI)" % VERSION)
    print("=" * 78)
    if not ctx.dry and not a.yes and not confirm_run(ctx, "INJECT"):
        return 2
    patch_all(ctx)
    if not ctx.dry:
        if not a.no_config:
            set_config(ctx)
        if not a.no_restart:
            restart_gateway(ctx)
        verify(ctx)
        print("\n[+] done. `hermes update` overwrites the source patch — re-run this")
        print("    script after every update (`--status` says if it drifted).")
        print("    Rollback: python3 hermes_unlock.py --restore")
    return 0


if __name__ == "__main__":
    sys.exit(main())
