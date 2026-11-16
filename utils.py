"""
Utility functions for Nirvana Spotlight
"""
import ast
import ctypes
import operator
import os
import re
import subprocess
import webbrowser

# Safe math operations mapping
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

def safe_eval(expr: str):
    """Safely evaluate mathematical expressions"""
    def _eval(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](_eval(node.operand))
        raise ValueError("unsupported expression")

    tree = ast.parse(expr, mode="eval")
    return _eval(tree.body)

def looks_like_math(text: str) -> bool:
    """Check if text looks like a mathematical expression"""
    cleaned = text.strip()
    if not cleaned:
        return False
    return bool(re.fullmatch(r"[0-9\.\s\+\-\*\/\%\(\)\^]+", cleaned)) and any(c.isdigit() for c in cleaned)

def truncate_path(path: str, max_len: int = 52) -> str:
    """Truncate path with middle ellipsis for clean single-line UI presentation"""
    if not path or len(path) <= max_len:
        return path
    half = (max_len - 3) // 2
    return f"{path[:half]}...{path[-half:]}"

def matches_acronym(query: str, target: str) -> bool:
    """Check if query matches acronym formed by target words (e.g., 'vsc' -> 'Visual Studio Code')"""
    q = query.lower().strip()
    if not q or len(q) < 2:
        return False
    words = re.findall(r"[A-Za-z0-9]+", target)
    if not words:
        return False
    acronym = "".join(w[0].lower() for w in words)
    return q in acronym or acronym.startswith(q)

def is_url(text: str) -> bool:
    """Check if query is a direct URL or domain address"""
    t = text.strip().lower()
    if t.startswith(("http://", "https://", "ftp://")):
        return True
    if re.fullmatch(r"[a-z0-9\-]+\.(com|org|net|io|dev|app|edu|gov|co|uk|de|ai)(\/[^\s]*)?", t):
        return True
    return False

def open_url(url: str):
    """Open URL ensuring it has a web scheme"""
    target = url.strip()
    if not target.startswith(("http://", "https://")):
        target = "https://" + target
    webbrowser.open(target)

def is_terminal_command(text: str) -> bool:
    """Check if query is an explicit terminal execution prefixed with '>'"""
    return text.strip().startswith(">")

def run_terminal_command(cmd_text: str):
    """Execute command in Windows cmd terminal"""
    cmd = cmd_text.strip().lstrip(">").strip()
    if cmd:
        subprocess.Popen(f'start cmd /k "{cmd}"', shell=True)

def empty_recycle_bin():
    """Empty Windows Recycle Bin silently without confirmation dialog"""
    try:
        # SHERB_NOCONFIRMATION = 0x0001, SHERB_NOPROGRESSUI = 0x0002, SHERB_NOSOUND = 0x0004
        ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x0007)
    except Exception:
        pass

def get_system_command(text: str):
    """Match system-level commands like lock, sleep, recycle bin, restart, shutdown"""
    t = text.strip().lower()
    commands = {
        "lock": {
            "label": "Lock Workstation",
            "subtext": "Lock this Windows PC immediately",
            "icon": "🔒",
            "badge": "SYS",
            "action": lambda: ctypes.windll.user32.LockWorkStation()
        },
        "sleep": {
            "label": "Sleep PC",
            "subtext": "Put system to sleep",
            "icon": "🌙",
            "badge": "SYS",
            "action": lambda: ctypes.windll.PowrProf.SetSuspendState(0, 1, 0)
        },
        "empty trash": {
            "label": "Empty Recycle Bin",
            "subtext": "Permanently delete files in Recycle Bin",
            "icon": "🗑️",
            "badge": "SYS",
            "action": empty_recycle_bin
        },
        "empty recycle bin": {
            "label": "Empty Recycle Bin",
            "subtext": "Permanently delete files in Recycle Bin",
            "icon": "🗑️",
            "badge": "SYS",
            "action": empty_recycle_bin
        },
        "restart": {
            "label": "Restart Computer",
            "subtext": "Reboot the operating system",
            "icon": "🔄",
            "badge": "SYS",
            "action": lambda: os.system("shutdown /r /t 0")
        },
        "shutdown": {
            "label": "Shut Down Computer",
            "subtext": "Power off system",
            "icon": "🛑",
            "badge": "SYS",
            "action": lambda: os.system("shutdown /s /t 0")
        }
    }
    return commands.get(t)

