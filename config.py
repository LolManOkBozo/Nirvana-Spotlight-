"""
Configuration constants for Winspot (Light Mode Only - System Theme Matching)
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

# Light Mode Colors (Windows Light Theme - matches system when not in HC)
BG = "#F0F0F0"          # Soft white background (Windows light theme)
FG = "#000000"          # Pure black for primary text
FG_DIM = "#2A2A2A"      # Dark gray for secondary text (4.56:1 contrast)
ACCENT = "#007AFF"      # Windows Blue for accents
BORDER_COLOR = "#D2D2D7" # Subtle border
STATUS_COLOR = "#007AFF" # Blue for listening status
BG_ITEM_HOVER = "#F2F2F7" # Subtle hover state (matches original design)

# High-Contrast Colors (WCAG 2.1 AA compliant)
HC_BG = "#000000"           # Black background
HC_FG = "#FFFFFF"           # White text
HC_FG_DIM = "#7F7F7F"       # Medium gray for secondary text (HC mode)
HC_ACCENT = "#00BFFF"       # Deep sky blue for accents (used in HC mode)

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

# Apply High Contrast colors if detected (overrides light mode)
if HC_MODE:
    BG = HC_BG
    FG = HC_FG
    FG_DIM = HC_FG_DIM
    # Note: Accent, border and status colors remain brand-consistent in HC mode
    # (ACCENT, BORDER_COLOR, STATUS_COLOR set below)
