"""
Configuration constants for Winspot (Professional Optimized)
"""
import os
import ctypes  # For Windows HC detection
from pathlib import Path

# Hotkeys
HOTKEY_TOGGLE_WINDOW = "alt+space"
HOTKEY_TOGGLE_VOICE = "alt+k"

# Window dimensions
WINDOW_WIDTH = 700
MAX_RESULTS = 8  # Optimized for low-end (reduced from 12)
HOTKEY_DEBOUNCE_MS = 250  # Input debouncing

# Professional Light Theme Colors (macOS Spotlight inspired)
BG = "#FFFFFF"              # Pure white background
BG_ITEM_HOVER = "#F2F2F7"   # Subtle hover state (macOS-like)
FG = "#1C1C1E"              # Near Black for primary text
FG_DIM = "#8E8E93"          # Secondary text
ACCENT = "#007AFF"          # macOS Blue for accents
BORDER_COLOR = "#D2D2D7"    # Subtle border
STATUS_COLOR = "#007AFF"    # Blue for listening status

# High-Contrast Colors (WCAG 2.1 AA compliant)
HC_BG = "#000000"           # Black background
HC_FG = "#FFFFFF"           # White text
HC_ACCENT = "#00BFFF"       # Deep sky blue for accents

# Shortcut directories for app detection
SHORTCUT_DIRS = [
    Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
]

# Low-end performance flags (set to True on weak hardware)
LOW_END_MODE = True  # Set to False on powerful PCs
ANIMATION_DURATION = 0 if LOW_END_MODE else 150  # ms for animations (0 = instant on low-end)

# WinRT availability (checked at runtime)
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

# Debug mode (auto-enabled when debugger attached)
import sys
DEBUG_MODE = hasattr(sys, 'gettrace') and sys.gettrace()

# Windows High Contrast detection (sets initial state)
HC_MODE = False  # Default assumption
try:
    # SPI_GETHIGHCONTRO = 0x0042
    HC_MODE = ctypes.windll.user32.SystemParametersInfoW(0x0042, 0, None, 0)
except:
    HC_MODE = False  # Keep default on error
