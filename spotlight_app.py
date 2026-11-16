"""
Main Spotlight application logic and UI (Nirvana Spotlight - Modernized & High-Efficiency)
"""
import ctypes
import os
import queue
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

import customtkinter as ctk

try:
    import keyboard
except ImportError:
    keyboard = None

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    pystray = None

from config import (
    THEMES,
    detect_system_theme,
    INITIAL_THEME,
    HOTKEY_TOGGLE_WINDOW,
    HOTKEY_TOGGLE_VOICE,
    WINDOW_WIDTH,
    MAX_RESULTS,
    HOTKEY_DEBOUNCE_MS,
    DEBUG_MODE
)
from utils import (
    safe_eval,
    looks_like_math,
    truncate_path,
    is_url,
    open_url,
    is_terminal_command,
    run_terminal_command,
    get_system_command
)
from index import SystemIndex


class MARGINS(ctypes.Structure):
    _fields_ = [
        ("cxLeftWidth", ctypes.c_int),
        ("cxRightWidth", ctypes.c_int),
        ("cyTopHeight", ctypes.c_int),
        ("cyBottomHeight", ctypes.c_int),
    ]


class SpotlightApp:
    def __init__(self):
        # Determine theme
        self.theme_mode = "system"
        self.current_theme = INITIAL_THEME
        self.current_palette = THEMES[self.current_theme]

        ctk.set_appearance_mode(self.current_palette["CTK_MODE"])
        ctk.set_default_color_theme("blue")

        # Root Window Setup
        self.root = ctk.CTk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 1.0)
        self.root.configure(fg_color=self.current_palette["BG"])
        self.root.withdraw()

        # State tracking
        self._debug_mode = DEBUG_MODE
        self._last_search_time = 0
        self.dictation_bar_on = False
        self._just_shown = False
        self._alt_space_pressed = False
        self._alt_k_pressed = False
        self._hotkey_lock = threading.Lock()

        # Debounce and search worker management
        self._search_timer = None
        self._query_counter = 0

        # Data & Queue
        self.index = SystemIndex()
        self.action_queue = queue.Queue()
        self.results = []
        self.selected = 0

        # Features popup state & window
        self.POPUP_HEIGHT = 112
        self._popup_visible = False
        self._popup_animating = False
        self._features_popup_enabled = True
        self.popup_chip_buttons = []

        # Setup UI
        self._setup_main_ui()
        self._setup_features_popup()
        self._apply_native_window_styling()

        # Start Services
        self._start_hotkey_listener()
        self._start_tray_icon()
        self._poll_action_queue()

    def _apply_native_window_styling(self):
        """Enable Windows 11 rounded corners and native borderless drop shadow"""
        try:
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if not hwnd:
                hwnd = self.root.winfo_id()

            # DWMWA_WINDOW_CORNER_PREFERENCE = 33, 2 = DWMWCP_ROUNDED
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(ctypes.c_int(2)), ctypes.sizeof(ctypes.c_int)
            )

            # Drop shadow for borderless window
            margins = MARGINS(1, 1, 1, 1)
            ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
        except Exception:
            pass

    def _setup_features_popup(self):
        """Setup floating features card positioned on top of search bar"""
        p = self.current_palette
        self.popup_window = ctk.CTkToplevel(self.root)
        self.popup_window.overrideredirect(True)
        self.popup_window.attributes("-topmost", True)
        self.popup_window.attributes("-alpha", 0.0)
        self.popup_window.configure(fg_color=p["BG"])
        self.popup_window.withdraw()

        # Prevent the popup from ever stealing keyboard focus from entry
        try:
            self.popup_window.update_idletasks()
            hwnd = self.popup_window.winfo_id()
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            old_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, old_style | WS_EX_NOACTIVATE)

            # Rounded corners & shadow for popup
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(ctypes.c_int(2)), ctypes.sizeof(ctypes.c_int)
            )
            margins = MARGINS(1, 1, 1, 1)
            ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
        except Exception:
            pass

        # Outer card frame
        self.popup_container = ctk.CTkFrame(
            self.popup_window,
            corner_radius=12,
            fg_color=p["CARD_BG"],
            border_width=1,
            border_color=p["BORDER_COLOR"]
        )
        self.popup_container.pack(fill="both", expand=True, padx=2, pady=2)

        # Header with Title and Close button
        hdr_frame = ctk.CTkFrame(self.popup_container, fg_color="transparent")
        hdr_frame.pack(fill="x", padx=12, pady=(7, 3))

        self.popup_title = ctk.CTkLabel(
            hdr_frame,
            text="💡 Nirvana Features & Shortcuts",
            font=("Segoe UI", 12, "bold"),
            text_color=p["ACCENT"]
        )
        self.popup_title.pack(side="left")

        self.popup_sub = ctk.CTkLabel(
            hdr_frame,
            text="— click any shortcut below to try:",
            font=("Segoe UI", 11),
            text_color=p["FG_DIM"]
        )
        self.popup_sub.pack(side="left", padx=6)

        self.popup_close_btn = ctk.CTkButton(
            hdr_frame,
            text="✕",
            font=("Segoe UI", 10, "bold"),
            width=20,
            height=20,
            corner_radius=10,
            fg_color="transparent",
            hover_color=p["BG_ITEM_HOVER"],
            text_color=p["FG_DIM"],
            command=self.toggle_features_popup
        )
        self.popup_close_btn.pack(side="right")

        # 2x3 Grid of feature buttons
        grid_frame = ctk.CTkFrame(self.popup_container, fg_color="transparent")
        grid_frame.pack(fill="both", expand=True, padx=8, pady=(2, 8))
        grid_frame.grid_columnconfigure((0, 1, 2), weight=1)

        features = [
            ("🧮 Math Solver", "25 * 4"),
            ("⚡ App Launcher", "vsc"),
            ("💻 Terminal Run", "> ping 8.8.8.8"),
            ("🔒 System Actions", "lock"),
            ("🌐 Web / URL", "github.com"),
            ("🎙️ Voice Dictation", "Alt+K")
        ]

        self.popup_chip_buttons = []
        for idx, (label, example) in enumerate(features):
            row_idx = idx // 3
            col_idx = idx % 3

            def make_cmd(ex=example):
                if ex == "Alt+K":
                    return self._trigger_voice_toggle
                return lambda: self.set_query(ex)

            btn = ctk.CTkButton(
                grid_frame,
                text=f"{label}: {example}",
                font=("Segoe UI", 11),
                height=26,
                corner_radius=6,
                fg_color=p["BADGE_BG"],
                hover_color=p["BG_ITEM_HOVER"],
                text_color=p["FG"],
                command=make_cmd()
            )
            btn.grid(row=row_idx, column=col_idx, padx=3, pady=2, sticky="ew")
            self.popup_chip_buttons.append(btn)

    def _setup_main_ui(self):
        """Construct the UI layout with reusable widget pools for max efficiency"""
        p = self.current_palette

        # Outer container frame
        self.container = ctk.CTkFrame(
            self.root,
            corner_radius=14,
            fg_color=p["BG"],
            border_width=1,
            border_color=p["BORDER_COLOR"]
        )
        self.container.pack(fill="both", expand=True, padx=2, pady=2)

        # Header area: Search icon, Entry, Clear button, Status
        self.header_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=16, pady=(12, 10))

        # Search icon
        self.search_icon_label = ctk.CTkLabel(
            self.header_frame,
            text="⚡",
            font=("Segoe UI Emoji", 18),
            text_color=p["ACCENT"],
            width=26
        )
        self.search_icon_label.pack(side="left", padx=(0, 6))

        # Text input
        self.entry_var = ctk.StringVar()
        self.entry_var.trace_add("write", lambda *_: self._on_entry_change())

        self.entry = ctk.CTkEntry(
            self.header_frame,
            textvariable=self.entry_var,
            placeholder_text="Search apps, files, math, commands (>)...",
            font=("Segoe UI", 16),
            height=44,
            corner_radius=8,
            fg_color="transparent",
            border_width=0,
            text_color=p["FG"],
            placeholder_text_color=p["FG_DIM"],
        )
        self.entry.pack(side="left", fill="x", expand=True)

        # Clear button (hidden when entry is empty)
        self.clear_btn = ctk.CTkButton(
            self.header_frame,
            text="✕",
            font=("Segoe UI", 12, "bold"),
            width=22,
            height=22,
            corner_radius=11,
            fg_color=p["BADGE_BG"],
            hover_color=p["BG_ITEM_HOVER"],
            text_color=p["FG_DIM"],
            command=self._clear_input
        )

        # Status label (for Voice Search and Clipboard notifications)
        self.status_label = ctk.CTkLabel(
            self.header_frame,
            text="",
            font=("Segoe UI", 11, "bold"),
            text_color=p["STATUS_COLOR"]
        )
        self.status_label.pack(side="right", padx=(4, 2))

        # Features & Tips Toggle button
        self.tips_btn = ctk.CTkButton(
            self.header_frame,
            text="💡",
            font=("Segoe UI Emoji", 13),
            width=26,
            height=26,
            corner_radius=13,
            fg_color="transparent",
            hover_color=p["BG_ITEM_HOVER"],
            text_color=p["ACCENT"],
            command=self.toggle_features_popup
        )
        self.tips_btn.pack(side="right", padx=(2, 4))

        # Divider between input and results
        self.divider = ctk.CTkFrame(
            self.container,
            height=1,
            fg_color=p["BORDER_COLOR"]
        )

        # Container for results (non-scrollable fixed pool)
        self.results_frame = ctk.CTkFrame(
            self.container,
            fg_color="transparent"
        )

        # Pre-allocate pool of row widgets to eliminate widget destroy/create churn
        self.result_rows = []
        for i in range(MAX_RESULTS):
            row = ctk.CTkFrame(
                self.results_frame,
                corner_radius=8,
                fg_color="transparent",
                height=50,
                border_width=0
            )
            row.pack_propagate(False)

            icon_lbl = ctk.CTkLabel(
                row,
                text="▶️",
                font=("Segoe UI Emoji", 16),
                width=34,
                anchor="center"
            )
            icon_lbl.pack(side="left", padx=(10, 4), pady=6)

            text_frame = ctk.CTkFrame(row, fg_color="transparent")
            text_frame.pack(side="left", fill="both", expand=True, padx=4, pady=4)

            title_lbl = ctk.CTkLabel(
                text_frame,
                text="",
                font=("Segoe UI", 13, "bold"),
                text_color=p["FG"],
                anchor="w"
            )
            title_lbl.pack(side="top", fill="x")

            sub_lbl = ctk.CTkLabel(
                text_frame,
                text="",
                font=("Segoe UI", 11),
                text_color=p["FG_DIM"],
                anchor="w"
            )
            sub_lbl.pack(side="top", fill="x")

            badge_lbl = ctk.CTkLabel(
                row,
                text="APP",
                font=("Segoe UI", 9, "bold"),
                corner_radius=4,
                fg_color=p["BADGE_BG"],
                text_color=p["BADGE_FG"],
                width=44,
                height=20
            )
            badge_lbl.pack(side="right", padx=(4, 10), pady=15)

            key_lbl = ctk.CTkLabel(
                row,
                text="↵",
                font=("Segoe UI", 11),
                text_color=p["FG_DIM"],
                width=16
            )
            key_lbl.pack(side="right", padx=(2, 2))

            row._icon_lbl = icon_lbl
            row._text_frame = text_frame
            row._title_lbl = title_lbl
            row._sub_lbl = sub_lbl
            row._badge_lbl = badge_lbl
            row._key_lbl = key_lbl
            row._index = i

            self.result_rows.append(row)

        # Keyboard and Focus Bindings
        self.entry.bind("<Escape>", lambda e: self.hide())
        self.entry.bind("<Down>", lambda e: self.move_selection(1))
        self.entry.bind("<Up>", lambda e: self.move_selection(-1))
        self.entry.bind("<Return>", lambda e: self.launch_selected())
        self.entry.bind("<F1>", lambda e: self.toggle_features_popup())
        self.entry.bind("<Alt-f>", lambda e: self.toggle_features_popup())
        self.root.bind("<FocusOut>", lambda e: self.root.after(140, self.hide_if_unfocused))

        # Position window immediately
        self._position_window()

    def _clear_input(self):
        """Clear search input box and refocus"""
        self.entry_var.set("")
        self.entry.focus_set()

    def _position_window(self):
        """Center window at upper-third of screen and sync popup position"""
        screen_w = self.root.winfo_screenwidth()
        x = (screen_w - WINDOW_WIDTH) // 2
        y = int(self.root.winfo_screenheight() * 0.22)
        self._adjust_window_height(x, y)
        if hasattr(self, 'popup_window') and getattr(self, '_popup_visible', False):
            target_y = max(10, y - self.POPUP_HEIGHT - 10)
            self.popup_window.geometry(f"{WINDOW_WIDTH}x{self.POPUP_HEIGHT}+{x}+{target_y}")

    def _adjust_window_height(self, x=None, y=None):
        """Fit window height tightly to search bar + visible results"""
        self.root.update_idletasks()
        height = self.root.winfo_reqheight()
        if x is None:
            x = (self.root.winfo_screenwidth() - WINDOW_WIDTH) // 2
        if y is None:
            y = int(self.root.winfo_screenheight() * 0.22)
        self.root.geometry(f"{WINDOW_WIDTH}x{height}+{x}+{y}")

    def apply_theme(self, theme_name: str):
        """Apply theme dynamically across all UI widgets"""
        if theme_name == "system":
            self.current_theme = detect_system_theme()
            self.theme_mode = "system"
        else:
            self.current_theme = theme_name
            self.theme_mode = theme_name

        self.current_palette = THEMES.get(self.current_theme, THEMES["dark"])
        p = self.current_palette

        ctk.set_appearance_mode(p["CTK_MODE"])

        self.root.configure(fg_color=p["BG"])
        self.container.configure(fg_color=p["BG"], border_color=p["BORDER_COLOR"])
        self.search_icon_label.configure(text_color=p["ACCENT"])
        self.entry.configure(
            text_color=p["FG"],
            placeholder_text_color=p["FG_DIM"]
        )
        self.clear_btn.configure(
            fg_color=p["BADGE_BG"],
            hover_color=p["BG_ITEM_HOVER"],
            text_color=p["FG_DIM"]
        )
        self.status_label.configure(text_color=p["STATUS_COLOR"])
        self.divider.configure(fg_color=p["BORDER_COLOR"])

        # Update popup theme
        if hasattr(self, 'popup_container'):
            self.popup_window.configure(fg_color=p["BG"])
            self.popup_container.configure(fg_color=p["CARD_BG"], border_color=p["BORDER_COLOR"])
            self.popup_title.configure(text_color=p["ACCENT"])
            self.popup_sub.configure(text_color=p["FG_DIM"])
            self.popup_close_btn.configure(hover_color=p["BG_ITEM_HOVER"], text_color=p["FG_DIM"])
            self.tips_btn.configure(text_color=p["ACCENT"], hover_color=p["BG_ITEM_HOVER"])
            for btn in self.popup_chip_buttons:
                btn.configure(fg_color=p["BADGE_BG"], hover_color=p["BG_ITEM_HOVER"], text_color=p["FG"])

        self._update_selection_visuals()
        self._apply_native_window_styling()

    def show(self):
        """Reveal Spotlight instantly without disk blocking"""
        self._position_window()
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self._adjust_window_height()

        self._just_shown = True
        self.entry.focus_force()
        self.root.after(60, lambda: setattr(self, '_just_shown', False))

        # Show features popup on open if enabled and query is empty
        if getattr(self, '_features_popup_enabled', True) and not self.entry_var.get().strip():
            self._show_features_popup()

    def hide(self):
        """Hide the Spotlight search window and popup"""
        if self.root.state() == "withdrawn":
            return

        if self.dictation_bar_on:
            self.dictation_bar_on = False
            self.action_queue.put(("set_status", ""))

        self._hide_features_popup(immediate=True)
        self.root.withdraw()
        self._just_shown = False

    def hide_if_unfocused(self):
        """Hide window if user clicks outside (except during immediate popup)"""
        try:
            focus = self.root.focus_get()
            if focus is None and not self._just_shown:
                # Retain focus if clicked inside popup window
                if hasattr(self, 'popup_window') and self.popup_window.winfo_ismapped():
                    if self.popup_window.focus_get() is not None:
                        return
                self.hide()
        except KeyError:
            self.hide()

    def _show_features_popup(self):
        """Animate features popup smoothly popping up on top of the search bar"""
        if getattr(self, '_popup_animating', False) or self.root.state() == "withdrawn":
            return

        self._popup_animating = True
        self._popup_visible = True

        screen_w = self.root.winfo_screenwidth()
        x = (screen_w - WINDOW_WIDTH) // 2
        root_y = self.root.winfo_y()
        target_y = max(10, root_y - self.POPUP_HEIGHT - 10)
        start_y = target_y + 16  # Animate upwards into place

        self.popup_window.attributes("-alpha", 0.0)
        self.popup_window.geometry(f"{WINDOW_WIDTH}x{self.POPUP_HEIGHT}+{x}+{start_y}")
        self.popup_window.deiconify()
        self.popup_window.lift()
        self.popup_window.attributes("-topmost", True)

        steps = 10
        def step(i=1):
            if not self._popup_visible or self.root.state() == "withdrawn":
                self._popup_animating = False
                return
            progress = i / steps
            eased = 1 - (1 - progress) ** 2  # Ease out quadratic
            curr_y = int(start_y + (target_y - start_y) * eased)
            try:
                self.popup_window.attributes("-alpha", eased)
                self.popup_window.geometry(f"{WINDOW_WIDTH}x{self.POPUP_HEIGHT}+{x}+{curr_y}")
            except Exception:
                pass
            if i < steps:
                self.root.after(12, lambda: step(i + 1))
            else:
                try:
                    self.popup_window.attributes("-alpha", 1.0)
                    self.popup_window.geometry(f"{WINDOW_WIDTH}x{self.POPUP_HEIGHT}+{x}+{target_y}")
                except Exception:
                    pass
                self._popup_animating = False
        step()

    def _hide_features_popup(self, immediate=False):
        """Hide the features popup with smooth fade-out or immediately"""
        self._popup_visible = False
        if immediate or not hasattr(self, 'popup_window') or not self.popup_window.winfo_ismapped():
            if hasattr(self, 'popup_window'):
                self.popup_window.withdraw()
            self._popup_animating = False
            return

        self._popup_animating = True
        steps = 6
        def step(i=1):
            progress = i / steps
            alpha = max(0.0, 1.0 - progress)
            try:
                self.popup_window.attributes("-alpha", alpha)
            except Exception:
                pass
            if i < steps and not self._popup_visible:
                self.root.after(10, lambda: step(i + 1))
            else:
                if not self._popup_visible:
                    try:
                        self.popup_window.withdraw()
                    except Exception:
                        pass
                self._popup_animating = False
        step()

    def toggle_features_popup(self):
        """Toggle features popup on/off with animation"""
        if self._popup_visible:
            self._features_popup_enabled = False
            self._hide_features_popup()
        else:
            self._features_popup_enabled = True
            self._show_features_popup()

    def set_query(self, query_text: str):
        """Populate search bar with sample shortcut, hide popup, and execute search"""
        self.entry_var.set(query_text)
        self.entry.focus_set()
        self.entry.icursor(len(query_text))
        self._hide_features_popup()

    def _trigger_voice_toggle(self):
        """Toggle Windows voice dictation"""
        if keyboard:
            try:
                keyboard.press_and_release("win+h")
            except Exception:
                pass
        self.dictation_bar_on = not self.dictation_bar_on
        if self.dictation_bar_on:
            self.status_label.configure(text="🎙️ Listening... (Alt+K to stop)")
        else:
            self.status_label.configure(text="")

    def toggle(self):
        """Toggle window between visible and hidden"""
        is_visible = (self.root.state() != "withdrawn" and self.root.winfo_viewable())
        if is_visible:
            self.hide()
        else:
            self.show()

    # -- Non-blocking Search Engine --------------------------------------- #

    def clear_results(self):
        """Hide results and reset state"""
        self.results = []
        self.selected = 0
        for row in self.result_rows:
            row.pack_forget()
        self.divider.pack_forget()
        self.results_frame.pack_forget()
        self._adjust_window_height()

    def _on_entry_change(self):
        """Handle keystrokes with quick debounce and background execution"""
        if self._search_timer:
            self.root.after_cancel(self._search_timer)

        query = self.entry_var.get()

        # Toggle clear button and features popup visibility
        if query:
            if not self.clear_btn.winfo_ismapped():
                self.clear_btn.pack(side="right", padx=(4, 6))
            if self._popup_visible:
                self._hide_features_popup()
        else:
            if self.clear_btn.winfo_ismapped():
                self.clear_btn.pack_forget()
            if getattr(self, '_features_popup_enabled', True) and not self._popup_visible:
                self._show_features_popup()

        if not query.strip():
            self.clear_results()
            return

        self._search_timer = self.root.after(HOTKEY_DEBOUNCE_MS, self._perform_search)

    def _perform_search(self):
        """Spawn background worker to evaluate query without stalling UI thread"""
        self._search_timer = None
        self._query_counter += 1
        query_id = self._query_counter
        query = self.entry_var.get().strip()

        if not query:
            self.clear_results()
            return

        def search_worker(q: str, q_id: int):
            start_time = time.time()
            candidates = []

            # 1. Math Evaluation
            if looks_like_math(q):
                try:
                    val = safe_eval(q)
                    candidates.append({
                        'label': f"= {val}",
                        'subtext': "Math result • Press Enter to copy to clipboard",
                        'icon': "🧮",
                        'badge': "MATH",
                        'action': lambda: self.copy(str(val)),
                        'usage_path': None
                    })
                    self.action_queue.put(("render_results", (q_id, candidates)))
                    return
                except Exception:
                    pass

            # 2. Terminal Run (> ping 8.8.8.8)
            if is_terminal_command(q):
                raw_cmd = q.lstrip(">").strip()
                if raw_cmd:
                    candidates.append({
                        'label': f"Run: {raw_cmd}",
                        'subtext': "Executes command in Windows Command Prompt",
                        'icon': "💻",
                        'badge': "CMD",
                        'action': lambda cmd=raw_cmd: run_terminal_command(cmd),
                        'usage_path': None
                    })
                    self.action_queue.put(("render_results", (q_id, candidates)))
                    return

            # 3. Direct URL Navigation
            if is_url(q):
                candidates.append({
                    'label': f"Open URL: {q}",
                    'subtext': "Navigates directly in your default browser",
                    'icon': "🌐",
                    'badge': "URL",
                    'action': lambda u=q: open_url(u),
                    'usage_path': None
                })
                self.action_queue.put(("render_results", (q_id, candidates)))
                return

            # 4. Explicit Web Search (? query)
            if q.startswith("?"):
                web_q = q.lstrip("?").strip()
                if web_q:
                    res = [{
                        'label': f'Search Google for "{web_q}"',
                        'subtext': "Opens search in default browser",
                        'icon': "🔍",
                        'badge': "WEB",
                        'action': lambda: webbrowser.open(f"https://www.google.com/search?q={web_q}"),
                        'usage_path': None
                    }]
                    self.action_queue.put(("render_results", (q_id, res)))
                    return

            # 5. System Commands (Lock, Sleep, Restart, Shutdown, Empty Trash)
            sys_cmd = get_system_command(q)
            if sys_cmd:
                candidates.append({
                    'label': sys_cmd['label'],
                    'subtext': sys_cmd['subtext'],
                    'icon': sys_cmd['icon'],
                    'badge': sys_cmd['badge'],
                    'action': sys_cmd['action'],
                    'usage_path': None
                })

            # 6. Installed Applications Search
            try:
                apps = self.index.search_apps(q)
                for name, path in apps[:MAX_RESULTS]:
                    display_sub = truncate_path(path)
                    candidates.append({
                        'label': name,
                        'subtext': f"Application • {display_sub}",
                        'icon': "▶️",
                        'badge': "APP",
                        'action': lambda p=path: self._launch_file(p),
                        'usage_path': path
                    })
            except Exception:
                pass

            # 7. Indexed Files and Folders Search
            if len(candidates) < MAX_RESULTS:
                try:
                    limit = MAX_RESULTS - len(candidates)
                    file_results = self.index.search_windows_files(q, limit=limit)
                    for name, path, is_dir in file_results:
                        display_sub = truncate_path(path)
                        if is_dir:
                            candidates.append({
                                'label': name,
                                'subtext': f"Folder • {display_sub}",
                                'icon': "📁",
                                'badge': "DIR",
                                'action': lambda p=path: self._launch_file(p),
                                'usage_path': path
                            })
                        else:
                            candidates.append({
                                'label': name,
                                'subtext': f"Document • {display_sub}",
                                'icon': "📄",
                                'badge': "FILE",
                                'action': lambda p=path: self._launch_file(p),
                                'usage_path': path
                            })
                except Exception:
                    pass

            # 8. Web Search Option (appended when local search has slots)
            if len(candidates) < MAX_RESULTS and not any(c['badge'] in ('MATH', 'SYS', 'CMD', 'URL') for c in candidates):
                candidates.append({
                    'label': f'Search Google for "{q}"',
                    'subtext': "Opens query in default browser",
                    'icon': "🔍",
                    'badge': "WEB",
                    'action': lambda: webbrowser.open(f"https://www.google.com/search?q={q}"),
                    'usage_path': None
                })

            if self._debug_mode:
                elapsed = (time.time() - start_time) * 1000
                print(f"[Nirvana] Search '{q}' -> {len(candidates)} results in {elapsed:.1f}ms")

            self.action_queue.put(("render_results", (q_id, candidates[:MAX_RESULTS])))

        threading.Thread(target=search_worker, args=(query, query_id), daemon=True).start()

    def _render_results(self):
        """Render results into pre-allocated row pool without widget recreation"""
        if not self.results:
            self.clear_results()
            return

        # Ensure divider and results frame are packed
        if not self.divider.winfo_ismapped():
            self.divider.pack(fill="x", padx=14, pady=(0, 6))
        if not self.results_frame.winfo_ismapped():
            self.results_frame.pack(fill="x", padx=8, pady=(0, 8))

        # Update rows
        for i, item in enumerate(self.results):
            row = self.result_rows[i]

            row._icon_lbl.configure(text=item['icon'])
            row._title_lbl.configure(text=item['label'])
            row._sub_lbl.configure(text=item['subtext'])
            row._badge_lbl.configure(text=item['badge'])

            # Bind click handlers
            def make_click_handler(idx=i):
                return lambda event: self.launch(idx)

            handler = make_click_handler(i)
            row.bind("<Button-1>", handler)
            row._icon_lbl.bind("<Button-1>", handler)
            row._text_frame.bind("<Button-1>", handler)
            row._title_lbl.bind("<Button-1>", handler)
            row._sub_lbl.bind("<Button-1>", handler)
            row._badge_lbl.bind("<Button-1>", handler)
            row._key_lbl.bind("<Button-1>", handler)

            # Bind hover handlers
            def make_hover(r=row, idx=i):
                def enter(event):
                    if idx != self.selected:
                        r.configure(fg_color=self.current_palette["BG_ITEM_HOVER"])
                def leave(event):
                    if idx != self.selected:
                        r.configure(fg_color="transparent")
                return enter, leave

            on_enter, on_leave = make_hover(row, i)
            for widget in (row, row._icon_lbl, row._text_frame, row._title_lbl, row._sub_lbl, row._badge_lbl, row._key_lbl):
                widget.bind("<Enter>", on_enter)
                widget.bind("<Leave>", on_leave)

            if not row.winfo_ismapped():
                row.pack(fill="x", padx=4, pady=2)

        # Unpack unused rows from pool
        for i in range(len(self.results), MAX_RESULTS):
            self.result_rows[i].pack_forget()

        self._update_selection_visuals()
        self._adjust_window_height()

    def _update_selection_visuals(self):
        """Update colors of selected and unselected rows with high-contrast text"""
        p = self.current_palette
        for i in range(len(self.results)):
            row = self.result_rows[i]
            if i == self.selected:
                row.configure(fg_color=p["ACCENT"])
                row._title_lbl.configure(text_color=p["ACCENT_FG"])
                row._sub_lbl.configure(text_color=p["ACCENT_SUB"])
                row._badge_lbl.configure(fg_color=p["ACCENT_BADGE"], text_color=p["ACCENT_FG"])
                row._key_lbl.configure(text_color=p["ACCENT_FG"])
            else:
                row.configure(fg_color="transparent")
                row._title_lbl.configure(text_color=p["FG"])
                row._sub_lbl.configure(text_color=p["FG_DIM"])
                row._badge_lbl.configure(fg_color=p["BADGE_BG"], text_color=p["BADGE_FG"])
                row._key_lbl.configure(text_color=p["FG_DIM"])

    def move_selection(self, delta: int):
        """Move active selection up or down"""
        if not self.results:
            return
        self.selected = (self.selected + delta) % len(self.results)
        self._update_selection_visuals()

    def launch_selected(self):
        """Launch the currently highlighted item"""
        if self.results:
            self.launch(self.selected)
        else:
            self.hide()

    def launch(self, idx: int):
        """Safely execute action and record usage"""
        if 0 <= idx < len(self.results):
            item = self.results[idx]
            usage_path = item.get('usage_path')
            if usage_path:
                self.index.record_launch(usage_path)

            action = item.get('action')
            if action:
                try:
                    action()
                except Exception:
                    pass

        self.hide()

    def _launch_file(self, path: str):
        """Launch an executable, document, or folder"""
        try:
            os.startfile(path)
        except Exception:
            try:
                subprocess.Popen(f'explorer "{path}"', shell=True)
            except Exception:
                pass

    def copy(self, text: str):
        """Copy text to clipboard with transient feedback"""
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update()
        except Exception:
            pass

        original_text = self.status_label.cget("text")
        self.status_label.configure(text="✓ Copied!", text_color="#34C759")
        self.root.after(1400, lambda: self.status_label.configure(
            text=original_text,
            text_color=self.current_palette["STATUS_COLOR"]
        ))

    # -- Global Hotkey Listeners ------------------------------------------ #

    def _start_hotkey_listener(self):
        """Setup Alt+Space and Alt+K hotkey listeners"""
        if keyboard is None:
            return

        def on_toggle_window():
            with self._hotkey_lock:
                if not self._alt_space_pressed:
                    self._alt_space_pressed = True
                    self.action_queue.put(("toggle", None))
                    self.root.after(HOTKEY_DEBOUNCE_MS, lambda: setattr(self, '_alt_space_pressed', False))

        def on_toggle_voice():
            with self._hotkey_lock:
                if not self._alt_k_pressed:
                    self._alt_k_pressed = True
                    self.dictation_bar_on = not self.dictation_bar_on

                    # Trigger Windows Dictation
                    keyboard.press_and_release("win+h")

                    if self.dictation_bar_on:
                        self.action_queue.put(("set_status", "🎙️ Listening... (Alt+K to stop)"))
                        self.action_queue.put(("show", None))
                    else:
                        self.action_queue.put(("set_status", ""))

                    self.root.after(HOTKEY_DEBOUNCE_MS, lambda: setattr(self, '_alt_k_pressed', False))

        try:
            keyboard.add_hotkey(HOTKEY_TOGGLE_WINDOW, on_toggle_window, suppress=True)
            keyboard.add_hotkey(HOTKEY_TOGGLE_VOICE, on_toggle_voice, suppress=True)
        except Exception:
            pass

    # -- Action Queue Polling ---------------------------------------------- #

    def _poll_action_queue(self):
        """Process actions posted from worker threads"""
        try:
            while True:
                action, payload = self.action_queue.get_nowait()
                if action == "render_results":
                    q_id, candidates = payload
                    if q_id == self._query_counter:
                        self.results = candidates
                        self.selected = 0
                        self._render_results()
                elif action == "show":
                    self.show()
                elif action == "hide":
                    self.hide()
                elif action == "toggle":
                    self.toggle()
                elif action == "set_status":
                    self.status_label.configure(text=payload)
                elif action == "set_theme":
                    self.apply_theme(payload)
                elif action == "refresh_index":
                    threading.Thread(target=self.index.refresh_apps, daemon=True).start()
        except queue.Empty:
            pass

        self.root.after(30, self._poll_action_queue)

    # -- System Tray ------------------------------------------------------- #

    def _start_tray_icon(self):
        """Create Windows system tray icon with modern menu"""
        if pystray is None:
            return

        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((6, 6, 58, 58), fill=(0, 122, 255, 255))
        d.ellipse((22, 22, 42, 42), fill=(255, 255, 255, 255))

        menu = pystray.Menu(
            pystray.MenuItem("Show / Hide (Alt+Space)", lambda *_: self.action_queue.put(("toggle", None)), default=True),
            pystray.MenuItem(
                "Theme",
                pystray.Menu(
                    pystray.MenuItem("System Default", lambda *_: self.action_queue.put(("set_theme", "system")), checked=lambda _: self.theme_mode == "system"),
                    pystray.MenuItem("Dark Mode", lambda *_: self.action_queue.put(("set_theme", "dark")), checked=lambda _: self.theme_mode == "dark"),
                    pystray.MenuItem("Light Mode", lambda *_: self.action_queue.put(("set_theme", "light")), checked=lambda _: self.theme_mode == "light"),
                    pystray.MenuItem("High Contrast", lambda *_: self.action_queue.put(("set_theme", "high_contrast")), checked=lambda _: self.theme_mode == "high_contrast"),
                )
            ),
            pystray.MenuItem("Refresh App Index", lambda *_: self.action_queue.put(("refresh_index", None))),
            pystray.MenuItem("Quit", lambda icon, _: (icon.stop(), self.root.after(0, self.root.destroy))),
        )

        threading.Thread(target=pystray.Icon("nirvana", img, "Nirvana Spotlight", menu).run, daemon=True).start()

    def run(self):
        """Start the application"""
        self.show()
        self.root.mainloop()


if __name__ == "__main__":
    SpotlightApp().run()
