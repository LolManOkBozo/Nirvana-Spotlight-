"""
Configuration constants for Nirvana Spotlight (macOS / Windows 11 Modernized)
"""
import os
import ctypes
import winreg
from pathlib import Path

# Hotkeys
HOTKEY_TOGGLE_WINDOW = "alt+space"
HOTKEY_TOGGLE_VOICE = "alt+k"

# Window dimensions & limits
WINDOW_WIDTH = 680
MAX_RESULTS = 8
HOTKEY_DEBOUNCE_MS = 120  # Fast, responsive typing debounce

# Themes & Color Palettes
THEMES = {
    "light": {
        "BG": "#F5F5F7",
        "CARD_BG": "#FFFFFF",
        "FG": "#1D1D1F",
        "FG_DIM": "#6E6E73",
        "ACCENT": "#007AFF",
        "ACCENT_FG": "#FFFFFF",
        "ACCENT_SUB": "#DCEEFF",
        "ACCENT_BADGE": "#0056B3",
        "BORDER_COLOR": "#D2D2D7",
        "BG_ITEM_HOVER": "#E8E8ED",
        "BADGE_BG": "#E2E2E7",
        "BADGE_FG": "#48484A",
        "STATUS_COLOR": "#007AFF",
        "CTK_MODE": "light"
    },
    "dark": {
        "BG": "#1E1E22",
        "CARD_BG": "#26262B",
        "FG": "#F2F2F7",
        "FG_DIM": "#8E8E93",
        "ACCENT": "#0A84FF",
        "ACCENT_FG": "#FFFFFF",
        "ACCENT_SUB": "#CFE4FF",
        "ACCENT_BADGE": "#005CBD",
        "BORDER_COLOR": "#36363D",
        "BG_ITEM_HOVER": "#2F2F36",
        "BADGE_BG": "#34343B",
        "BADGE_FG": "#AEAEB2",
        "STATUS_COLOR": "#0A84FF",
        "CTK_MODE": "dark"
    },
    "high_contrast": {
        "BG": "#000000",
        "CARD_BG": "#000000",
        "FG": "#FFFFFF",
        "FG_DIM": "#A0A0A0",
        "ACCENT": "#00BFFF",
        "ACCENT_FG": "#000000",
        "ACCENT_SUB": "#1A1A1A",
        "ACCENT_BADGE": "#004080",
        "BORDER_COLOR": "#FFFFFF",
        "BG_ITEM_HOVER": "#222222",
        "BADGE_BG": "#111111",
        "BADGE_FG": "#00BFFF",
        "STATUS_COLOR": "#00BFFF",
        "CTK_MODE": "dark"
    }
}

def detect_system_theme() -> str:
    """Detect whether Windows is in High Contrast, Dark, or Light mode"""
    try:
        # Check High Contrast (SPI_GETHIGHCONTRAST = 0x0042)
        if ctypes.windll.user32.SystemParametersInfoW(0x0042, 0, None, 0):
            return "high_contrast"
    except Exception:
        pass

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        if value == 0:
            return "dark"
    except Exception:
        pass

    return "light"

# Initial detected theme
INITIAL_THEME = detect_system_theme()
CURRENT_PALETTE = THEMES[INITIAL_THEME]

# Compatibility aliases for legacy imports
BG = CURRENT_PALETTE["BG"]
FG = CURRENT_PALETTE["FG"]
FG_DIM = CURRENT_PALETTE["FG_DIM"]
ACCENT = CURRENT_PALETTE["ACCENT"]
BORDER_COLOR = CURRENT_PALETTE["BORDER_COLOR"]
STATUS_COLOR = CURRENT_PALETTE["STATUS_COLOR"]
BG_ITEM_HOVER = CURRENT_PALETTE["BG_ITEM_HOVER"]

HC_BG = THEMES["high_contrast"]["BG"]
HC_FG = THEMES["high_contrast"]["FG"]
HC_FG_DIM = THEMES["high_contrast"]["FG_DIM"]
HC_ACCENT = THEMES["high_contrast"]["ACCENT"]
HC_MODE = (INITIAL_THEME == "high_contrast")

# Shortcut directories for app detection
SHORTCUT_DIRS = [
    Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
]

# Performance flags
LOW_END_MODE = False
ANIMATION_DURATION = 0 if LOW_END_MODE else 120

# WinRT availability
try:
    from winsdk.windows.storage.search import *
    from winsdk.windows.storage import *
    WINRT_AVAILABLE = True
except ImportError:
    WINRT_AVAILABLE = False

# Cache settings
CACHE_EXPIRY_SECONDS = 300  # 5 minutes
CACHE_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Winspot"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
USAGE_FILE = CACHE_DIR / "usage_counts.json"

# Debug mode
import sys
DEBUG_MODE = hasattr(sys, 'gettrace') and sys.gettrace()

