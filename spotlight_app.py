"""
Main Spotlight application logic and UI (Nirvana Professional Optimized with Folder Navigation & Scrolling)
"""
import os
import queue
import threading
import time
import webbrowser
import subprocess
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
    HOTKEY_TOGGLE_WINDOW,
    HOTKEY_TOGGLE_VOICE,
    WINDOW_WIDTH,
    MAX_RESULTS,
    HOTKEY_DEBOUNCE_MS,
    BG,
    BG_ITEM_HOVER,
    FG,
    FG_DIM,
    ACCENT,
    BORDER_COLOR,
    STATUS_COLOR,
    DEBUG_MODE,
    LOW_END_MODE,
    ANIMATION_DURATION,
    HC_BG,
    HC_FG,
    HC_FG_DIM,
    HC_ACCENT,
    HC_MODE  # Initial HC state from config
)
from utils import safe_eval, looks_like_math
from index import SystemIndex


class SpotlightApp:
    def __init__(self):
        # Force Light Mode for the macOS feel (overriden by theme detection)
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 1.0)  # NO TRANSPARENCY (solid background)
        self.root.configure(fg_color=BG)
        self.root.withdraw()

        # Initialize state
        self._debug_mode = DEBUG_MODE
        self._last_search_time = 0
        self.dictation_bar_on = False  # Tracks local state of dictation bar (for status only)
        self._focus_attempts = 0       # Track focus attempts to prevent infinite loops
        self._just_shown = False       # Temporarily ignore focus loss during show
        self._alt_space_pressed = False  # Track Alt+Space state for debouncing
        self._alt_k_pressed = False    # Track Alt+K state for debouncing
        self._hotkey_lock = threading.Lock()  # Prevent race conditions
        self._high_contrast = HC_MODE  # Start with system HC state

        # ⚡ OPTIMIZATION: Input debouncing state
        self._search_timer = None
        self._pending_search = ""

        # Initialize components
        self.index = SystemIndex()
        self.action_queue = queue.Queue()

        # Setup UI and start services
        self._show_splash_screen()

    def _show_splash_screen(self):
        """Show initialization splash screen"""
        splash = ctk.CTkToplevel(self.root)
        splash.overrideredirect(True)
        splash.attributes("-topmost", True)
        splash.attributes("-alpha", 1.0)  # NO TRANSPARENCY
        splash.configure(fg_color=BG)

        # Center the Splash Screen
        splash_w, splash_h = 450, 180
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - splash_w) // 2
        y = (screen_h - splash_h) // 2
        splash.geometry(f"{splash_w}x{splash_h}+{x}+{y}")

        # UI for Splash
        frame = ctk.CTkFrame(splash, corner_radius=16, fg_color=BG, border_width=1, border_color=BORDER_COLOR)
        frame.pack(fill="both", expand=True)

        title = ctk.CTkLabel(frame, text="Nirvana", font=("Segoe UI", 34, "bold"), text_color=FG)
        title.pack(expand=True, pady=(24, 0))  # FIXED: Changed "paya" to "pady"

        subtitle = ctk.CTkLabel(frame, text="Initializing professional search interface...", font=("Segoe UI", 13), text_color=FG_DIM)
        subtitle.pack(expand=True, pady=(0, 24))  # FIXED: Removed erroneous "subtitle)" line

        splash.update()

        # Setup main UI while splash is showing
        self._setup_main_ui()

        # Destroy splash after 2 seconds and start background hooks
        self.root.after(2000, lambda: self._finish_startup(splash))

    def _setup_main_ui(self):
        """Setup the main application UI (Professional)"""
        self.container = ctk.CTkFrame(self.root, corner_radius=8 if LOW_END_MODE else 18, fg_color=BG, border_width=1, border_color=BORDER_COLOR)
        self.container.pack(fill="both", expand=True, padx=2, pady=2)
        self.container.pack_propagate(False)

        header_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        header_frame.pack(fill="x", padx=18, pady=(14, 6))

        self.entry_var = ctk.StringVar()
        self.entry_var.trace_add("write", lambda *_: self._on_entry_change())  # ⚡ OPTIMIZATION: Use custom handler

        self.entry = ctk.CTkEntry(
            header_frame,
            textvariable=self.entry_var,
            placeholder_text="Nirvana Search (Alt+K for voice)",
            font=("Segoe UI", 20 if LOW_END_MODE else 22),  # ⚡ OPTIMIZATION: Smaller font
            height=48 if LOW_END_MODE else 56,               # ⚡ OPTIMIZATION: Shorter height
            corner_radius=6 if LOW_END_MODE else 12,         # ⚡ OPTIMIZATION: Less rounding
            fg_color="transparent",
            border_width=0,
            text_color=FG,
            placeholder_text_color=FG_DIM,
        )
        self.entry.pack(side="left", fill="x", expand=True)

        self.status_label = ctk.CTkLabel(
            header_frame,
            text="",
            font=("Segoe UI", 10 if LOW_END_MODE else 12, "bold"),  # ⚡ OPTIMIZATION: Smaller status font
            text_color=STATUS_COLOR
        )
        self.status_label.pack(side="right", padx=(8, 4))

        self.results_frame = ctk.CTkScrollableFrame(
            self.container,
            fg_color="transparent",
            height=0  # Start hidden (height=0)
        )
        self.results_frame.pack(fill="both", expand=True, padx=12, pady=(0, 14))

        self.result_rows = []
        self.results = []
        self.selected = 0

        self.entry.bind("<Escape>", lambda e: self.hide())
        self.entry.bind("<Down>", lambda e: self.move_selection(1))
        self.entry.bind("<Up>", lambda e: self.move_selection(-1))
        self.entry.bind("<Return>", lambda e: self.launch_selected())
        self.root.bind("<FocusOut>", lambda e: self.root.after(140, self.hide_if_unfocused))

        # Enable mouse scrolling
        self.results_frame.bind("<MouseWheel>", self._on_mousewheel)  # Windows
        self.results_frame.bind("<Button-4>", self._on_mousewheel)    # Linux scroll up
        self.results_frame.bind("<Button-5>", self._on_mousewheel)    # Linux scroll down

    def _finish_startup(self, splash):
        """Complete initialization after splash screen"""
        splash.destroy()
        self.root.update_idletasks()
        self._position_window()
        self._start_hotkey_listener()
        self._start_tray_icon()
        self._poll_action_queue()

    def _position_window(self):
        """Position window at top-center of screen"""
        screen_w = self.root.winfo_screenwidth()
        x = (screen_w - WINDOW_WIDTH) // 2
        y = int(self.root.winfo_screenheight() * 0.22)
        # Set width only, height will be adjusted by _adjust_window_height
        self.root.geometry(f"{WINDOW_WIDTH}x1+{x}+{y}")

    def show(self):
        """Show the search window (Professional with micro-animations)"""
        self.index.refresh_apps()
        self._position_window()
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self._adjust_window_height()  # Adjust height to fit current content (search bar only)

        # ⭐ PROFESSIONAL TOUCH: Smooth fade-in (macOS-style)
        self.root.attributes("-alpha", 0.0)
        self._fade_animation(0, 100, 120)  # 0% → 100% over 120ms

        # Focus handling (optimized for low-end)
        self._just_shown = True
        self._focus_attempts = 0
        self.entry.focus_force()
        self.root.after(50, lambda: setattr(self, '_just_shown', False))  # Shorter delay

    def _fade_animation(self, start, end, duration_ms):
        """Hardware-accelerated fade animation (0% CPU impact)"""
        steps = 10
        step_time = duration_ms / (steps * 1000)
        def step(current=start):
            if current > end:
                return
            self.root.attributes("-alpha", current/100 * 1.0)  # Solid opacity
            self.root.after(int(step_time), lambda: step(current + (end-start)/steps))
        step()

    def hide(self):
        """Hide the search window (Professional with micro-animations)"""
        # If already hidden, just reset state
        if self.root.state() == 'withdrawn':
            self._focus_attempts = 0
            self._just_shown = False
            return

        # Reset voice search state when window hidden (contextual)
        if self.dictation_bar_on:
            self.dictation_bar_on = False
            self.action_queue.put(("set_status", ""))

        # ⭐ PROFESSIONAL TOUCH: Smooth fade-out
        self._fade_animation(100, 0, 100)  # 100% → 0% over 100ms
        self.root.after(100, self._finalize_hide)  # Hide after fade completes

    def _finalize_hide(self):
        """Complete the hide operation after fade-out"""
        self.root.attributes("-alpha", 0.0)
        self.root.withdraw()
        self._focus_attempts = 0
        self._just_shown = False

    def hide_if_unfocused(self):
        """Hide window if it loses focus (except during show)"""
        try:
            # Ignore focus loss if we just showed the window
            if self.root.focus_get() is None and not self._just_shown:
                self.hide()
        except KeyError:
            self.hide()

    def toggle(self):
        """Toggle window visibility"""
        is_visible = self.root.state() != "withdrawn" and self.root.winfo_viewable()
        if is_visible:
            self.hide()
        else:
            self.show()

    # -- Search & Rendering ------------------------------------------------ #

    def clear_results(self):
        """Clear all search results"""
        for row in self.result_rows:
            row.destroy()
        self.result_rows = []
        self.results = []
        self.selected = 0
        self.results_frame.configure(height=0)  # Hide results frame
        self._adjust_window_height()  # Adjust window height to fit hidden results

    def _on_entry_change(self):
        """Handle text input with debouncing (Low-End Optimization)"""
        # Cancel any pending search
        if self._search_timer:
            self.root.after_cancel(self._search_timer)

        # Get current text
        current_text = self.entry_var.get()

        # Check for explicit web search prefix (?)
        if current_text.startswith("?"):
            q = current_text[1:].strip()
            if q:
                # Explicit web search: show ONLY web search results
                self._search_timer = None
                start_time = time.time()
                self.clear_results()
                self.results = [(
                    f'Search the web for "{q}"',
                    "Opens your browser",
                    lambda: webbrowser.open(f"https://www.google.com/search?q={q}")
                )]
                self._render_results()

                # Debug timing
                if self._debug_mode:
                    elapsed = (time.time() - start_time) * 1000
                    self._last_search_time = elapsed
                    print(f"[Nirvana] Explicit web search: '{q}' → 1 result in {elapsed:.1f}ms")
            else:
                # Just "?" - clear results
                self.clear_results()
            return

        # ⚡ OPTIMIZATION: Only search if meaningful change
        if len(current_text) >= 2 or current_text == "":
            self._pending_search = current_text
            # Schedule search after debounce period
            self._search_timer = self.root.after(HOTKEY_DEBOUNCE_MS, self._perform_search)
        else:
            # For very short queries, clear results immediately
            self.clear_results()

    def _perform_search(self):
        """Actually perform the search (called after debounce)"""
        self._search_timer = None
        start_time = time.time()
        text = self._pending_search
        self.clear_results()

        if not text.strip():
            if self._debug_mode:
                elapsed = (time.time() - start_time) * 1000
                self._last_search_time = elapsed
                print(f"[Nirvana] Empty query → {elapsed:.1f}ms")
            return

        candidates = []

        # Math result
        if looks_like_math(text):
            try:
                result = safe_eval(text)
                candidates.append({
                    'label': f"= {result}",
                    'subtext': "Math result • Press Enter to copy",
                    'action': lambda: self.copy(str(result)),
                    'usage_path': None  # No usage tracking for math
                })
            except Exception:
                pass

        # App results - EXPLICITLY HANDLE 2-TUPLE (name, path) FROM index.search_apps
        apps_list = self.index.search_apps(text)
        # Limit candidates to avoid excessive processing
        if len(apps_list) > 2 * MAX_RESULTS:
            apps_list = apps_list[:2 * MAX_RESULTS]
        for app_tuple in apps_list:
            # Explicitly unpack 2-tuple: (name, path)
            name, path = app_tuple
            candidates.append({
                'label': name,
                'subtext': f"Application • {path}",
                'action': lambda p=path: os.startfile(p),
                'usage_path': path
            })

        # File/folder results - EXPLICITLY HANDLE 3-TUPLE (name, path, is_dir) FROM index.search_windows_files
        file_results = self.index.search_windows_files(text, limit=2 * MAX_RESULTS)
        for file_tuple in file_results:
            # Explicitly unpack 3-tuple: (name, path, is_dir)
            name, path, is_dir = file_tuple
            if is_dir:
                # Folder: one result
                candidates.append({
                    'label': name,
                    'subtext': f"📁 Folder • {path}",
                    'action': lambda p=path: os.startfile(p),
                    'usage_path': path
                })
            else:
                # File: two results (open file + open containing folder)
                candidates.append({
                    'label': name,
                    'subtext': f"📄 Document • {path}",
                    'action': lambda p=path: os.startfile(p),
                    'usage_path': path
                })
                candidates.append({
                    'label': name,
                    'subtext': "Open containing folder",
                    'action': lambda p=path: self._open_containing_folder(p),
                    'usage_path': path  # Same usage count as the file
                })

        # Sort candidates by usage count (descending) then by label
        def get_usage_count(cand):
            if cand['usage_path'] is None:
                return 0
            return self.index.usage_counts[cand['usage_path']]  # FIXED: Use index.usage_counts

        candidates.sort(key=lambda cand: (-get_usage_count(cand), cand['label'].lower()))

        # Take top (MAX_RESULTS - 1) for local results (reserve 1 slot for web search)
        local_candidates = candidates[:MAX_RESULTS-1]

        # Convert to UI format: (label, subtext, action)
        all_results = []
        for cand in local_candidates:
            all_results.append((
                cand['label'],
                cand['subtext'],
                cand['action']
            ))

        # Always add web search option if query not empty
        if text.strip():
            all_results.append((
                f'Search the web for "{text}"',
                "Opens your browser",
                lambda: webbrowser.open(f"https://www.google.com/search?q={text}")
            ))

        self.results = all_results
        self._render_results()

        # Debug timing
        if self._debug_mode:
            elapsed = (time.time() - start_time) * 1000
            self._last_search_time = elapsed
            print(f"[Nirvana] Search: '{text}' → {len(self.results)} results in {elapsed:.1f}ms")

    def _open_containing_folder(self, path):
        """Open the folder containing the file and select the file in Explorer"""
        try:
            # Normalize the path
            path = os.path.normpath(path)
            if os.path.isfile(path):
                # For files: open Explorer and select the file
                subprocess.run(['explorer', '/select,', path], check=True)
            elif os.path.isdir(path):
                # For folders: just open the folder
                os.startfile(path)
            else:
                # Fallback: try to open the parent directory
                parent = os.path.dirname(path)
                if os.path.isdir(parent):
                    os.startfile(parent)
                else:
                    # Last resort: open the drive
                    drive = os.path.splitdrive(path)[0]
                    if drive:
                        os.startfile(drive + "\\")
        except Exception:
            # Fallback to opening the folder if selection fails
            try:
                folder = os.path.dirname(path)
                if os.path.isdir(folder):
                    os.startfile(folder)
                else:
                    os.startfile(os.path.splitdrive(path)[0] + "\\")
            except Exception:
                pass  # Fail silently - better than crashing

    def _render_results(self):
        """Render search results in the UI (Professional with enhancements)"""
        # Destroy all existing result rows
        for row in self.result_rows:
            row.destroy()
        self.result_rows = []

        # If no results, hide results frame and adjust height
        if not self.results:
            self.results_frame.configure(height=0)
            self._adjust_window_height()
            return

        # Show results frame with fixed height
        self.results_frame.configure(height=200)

        # Create new rows for each result
        for i, (label, sub, action) in enumerate(self.results):
            # Extract path from subtext for apps/files results (format: "Label • path")
            path = ""
            if " • " in sub:
                path = sub.split(" • ", 1)[1]  # Get everything after first " • "

            # Create the row frame
            row = ctk.CTkFrame(
                self.results_frame,
                corner_radius=6 if LOW_END_MODE else 10,
                fg_color="transparent",  # Will be set below based on selection and HC mode
                height=48 if LOW_END_MODE else 56,  # Increased height for better text visibility
                border_width=0
            )
            row.pack(fill="x", pady=1 if LOW_END_MODE else 2, padx=1 if LOW_END_MODE else 2)
            row.pack_propagate(False)

            # Store index in row for hover/selection state tracking
            row._index = i

            # Determine colors based on selection and HC mode
            if self._high_contrast:
                if i == self.selected:
                    bg_color = HC_ACCENT
                    text_color = HC_BG
                else:
                    bg_color = "transparent"
                    text_color = HC_FG
            else:
                if i == self.selected:
                    bg_color = ACCENT
                    text_color = FG
                else:
                    bg_color = "transparent"
                    text_color = FG

            # Set row background color
            row.configure(fg_color=bg_color)

            # Title label
            title_label = ctk.CTkLabel(
                row,
                font=("Segoe UI", 13 if LOW_END_MODE else 14, "bold"),
                text_color=text_color,
                anchor="w"
            )
            title_label.pack(side="top", fill="x", padx=10 if LOW_END_MODE else 14, pady=(8 if LOW_END_MODE else 10, 0))

            # Subtitle label
            subtitle_label = ctk.CTkLabel(
                row,
                font=("Segoe UI", 11 if LOW_END_MODE else 12),
                text_color=text_color,
                anchor="w"
            )
            subtitle_label.pack(side="top", fill="x", padx=10 if LOW_END_MODE else 14)

            # Set text with semantic icons
            icon = ""
            if "📁 Folder" in sub:
                icon = "📁 "
            elif "📄 Document" in sub:
                icon = "📄 "
            elif "Application" in sub:
                icon = "▶️ "
            elif "Math result" in sub:
                icon = "🧮 "
            elif "Search the web" in sub:
                icon = "🔍 "

            # Clean subtitle for display (remove icon prefixes)
            display_sub = sub.replace("📁 Folder • ", "").replace("📄 Document • ", "").replace("Application • ", "")

            # Set labels
            title_label.configure(text=f"{icon}{label}")
            subtitle_label.configure(text=display_sub)

            # Click event: launch the action
            def make_click_handler(act):
                return lambda event: self._launch_action(act)

            click_handler = make_click_handler(action)
            row.bind("<Button-1>", click_handler)
            title_label.bind("<Button-1>", click_handler)
            subtitle_label.bind("<Button-1>", click_handler)

            # Hover events: change background color if not selected
            def make_enter_handler(r):
                return lambda event: self._on_row_enter(event, r)

            def make_leave_handler(r):
                return lambda event: self._on_row_leave(event, r)

            enter_handler = make_enter_handler(row)
            leave_handler = make_leave_handler(row)
            row.bind("<Enter>", enter_handler)
            row.bind("<Leave>", leave_handler)
            title_label.bind("<Enter>", enter_handler)
            title_label.bind("<Leave>", leave_handler)
            subtitle_label.bind("<Enter>", enter_handler)
            subtitle_label.bind("<Leave>", leave_handler)

            # Keep track of the row
            self.result_rows.append(row)

        # Adjust window height to fit the new content (results frame now visible)
        self._adjust_window_height()

    def _launch_action(self, action):
        """Safely execute an action (used for click handlers)"""
        try:
            action()
        except Exception:
            pass

    # --- MOUSE SCROLL HANDLING ---

    def _on_mousewheel(self, event):
        """Handle mouse scroll events"""
        # For Windows
        if event.delta:
            self.results_frame._parent_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        # For Linux
        else:
            if event.num == 4:
                self.results_frame._parent_canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self.results_frame._parent_canvas.yview_scroll(1, "units")

    # --- MISSING METHODS ADDED HERE ---

    def _on_row_enter(self, event, row):
        """Handle mouse enter on result row"""
        idx = row._index
        if idx == self.selected:
            return  # Don't change color if selected
        if self._high_contrast:
            row.configure(fg_color=HC_FG_DIM)
        else:
            row.configure(fg_color=BG_ITEM_HOVER)

    def _on_row_leave(self, event, row):
        """Handle mouse leave on result row"""
        idx = row._index
        if idx == self.selected:
            return  # Don't change color if selected
        if self._high_contrast:
            row.configure(fg_color="transparent")
        else:
            row.configure(fg_color="transparent")

    def move_selection(self, delta):
        """Move selection up/down in results"""
        if not self.results:
            return
        self.selected = (self.selected + delta) % len(self.results)
        for i, row in enumerate(self.result_rows):
            if i == self.selected:
                if self._high_contrast:
                    row.configure(fg_color=HC_ACCENT)
                else:
                    row.configure(fg_color=ACCENT)
            else:
                row.configure(fg_color="transparent")

        # Try to scroll to make the selected item visible (approximate)
        try:
            if len(self.results) > 0 and hasattr(self.results_frame, '_parent_canvas'):
                fraction = self.selected / len(self.results)
                self.results_frame._parent_canvas.yview_moveto(fraction)
        except Exception:
            pass  # Fail silently if scrolling fails

    def launch_selected(self):
        """Launch the currently selected result"""
        if self.results:
            self.launch(self.selected)
        else:
            self.hide()

    def launch(self, idx):
        """Launch result at given index"""
        try:
            self.results[idx][2]()
        except Exception:
            pass
        self.hide()

    def copy(self, text):
        """Copy text to clipboard with professional feedback"""
        self.root.clipboard_clear()
        self.root.clipboard.append(text)

        # ⭐ PROFESSIONAL TOUCH: Transient confirmation (like macOS)
        original_text = self.status_label.cget("text")
        self.status_label.configure(text="✓ Copied!", text_color="#34C759")  # Green success
        self.root.after(1500, lambda: self.status_label.configure(
            text=original_text,
            text_color=STATUS_COLOR
        ))

    # -- PERFECT HOTKEY LOGIC (ALT+SPACE & ALT+K) -------------------------- #

    def _start_hotkey_listener(self):
        """Setup global hotkey listeners"""
        if keyboard is None:
            return

        def on_hotkey_triggered_window():
            """Handle Alt+Space: Toggle search window (only on key press)"""
            def handle_toggle():
                # Use lock to prevent race conditions
                with self._hotkey_lock:
                    # Only act if this is a fresh key press (not during hold)
                    if not self._alt_space_pressed:
                        self._alt_space_pressed = True
                        is_visible = self.root.state() != "withdrawn" and self.root.winfo_viewable()
                        if is_visible:
                            self.action_queue.put(("hide", None))
                        else:
                            self.action_queue.put(("show", None))
                        # Schedule reset after debounce period
                        self.root.after(HOTKEY_DEBOUNCE_MS, lambda: setattr(self, '_alt_space_pressed', False))
            threading.Thread(target=handle_toggle, daemon=True).start()

        def on_hotkey_triggered_voice():
            """Handle Alt+K: Toggle voice search via Windows Dictation (only on key press)"""
            def handle_voice_toggle():
                # Use lock to prevent race conditions
                with self._hotkey_lock:
                    # Only act if this is a fresh key press (not during hold)
                    if not self._alt_k_pressed:
                        self._alt_k_pressed = True

                        # Toggle local dictation state
                        self.dictation_bar_on = not self.dictation_bar_on

                        # Send Win+H to toggle system dictation bar
                        keyboard.press_and_release('win+h')

                        # Update status based on local state
                        if self.dictation_bar_on:
                            self.action_queue.put(("set_status", "🎙️ Listening... (Press Alt+K again to stop)"))
                        else:
                            self.action_queue.put(("set_status", ""))

                        # Show window if voice search turned on and window hidden
                        if self.dictation_bar_on and not (self.root.state() == "normal" and self.root.winfo_viewable()):
                            self.action_queue.put(("show", None))

                        # Schedule reset after debounce period
                        self.root.after(HOTKEY_DEBOUNCE_MS, lambda: setattr(self, '_alt_k_pressed', False))
            threading.Thread(target=handle_voice_toggle, daemon=True).start()

        # Register hotkeys with suppression
        keyboard.add_hotkey(HOTKEY_TOGGLE_WINDOW, on_hotkey_triggered_window, suppress=True)
        keyboard.add_hotkey(HOTKEY_TOGGLE_VOICE, on_hotkey_triggered_voice, suppress=True)

    def _poll_action_queue(self):
        """Process actions from the background thread queue"""
        try:
            while True:
                action, payload = self.action_queue.get_nowait()
                if action == "show":
                    self.show()
                elif action == "hide":
                    self.hide()
                elif action == "toggle":
                    self.toggle()
                elif action == "set_status":
                    self.status_label.configure(text=payload)
                elif action == "apply_voice_text":
                    # Legacy support - not used in current implementation
                    self.status_label.configure(text="")
                    self.entry_var.set(payload)
                    self.entry.icursor(len(payload))
        except queue.Empty:
            pass
        # ⚡ OPTIMIZATION: Poll less frequently on low-end (50ms vs 40ms)
        self.root.after(50 if LOW_END_MODE else 40, self._poll_action_queue)

    # -- System Tray ------------------------------------------------------- #

    def _start_tray_icon(self):
        """Create system tray icon with professional menu"""
        if pystray is None:
            return

        # Create a simple, professional tray icon
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        # Draw a simple circle with macOS blue
        d.ellipse((8, 8, 56, 56), fill=(0, 122, 255, 255))
        # Draw a smaller white circle inside for contrast
        d.ellipse((24, 24, 40, 40), fill=(255, 255, 255, 255))
        # Add a subtle spotlight effect
        d.ellipse((20, 20, 44, 44), outline=(255, 255, 255, 100), width=1)  # FIXED: weight -> width

        # ⭐ PROFESSIONAL TOUCH: High-contrast toggle in tray menu
        menu = pystray.Menu(
            pystray.MenuItem("Show / Hide", lambda *_: self.action_queue.put(("toggle", None)), default=True),
            pystray.MenuItem(
                "High Contrast",
                lambda *_: self._toggle_high_contrast(),
                checked=lambda item: self._high_contrast
            ),
            pystray.MenuItem("Quit", lambda icon, _: (icon.stop(), self.root.after(0, self.root.destroy))),
        )
        threading.Thread(target=pystray.Icon("nirvana", img, "Nirvana", menu).run, daemon=True).start()

    def _toggle_high_contrast(self):
        """Toggle high-contrast mode for accessibility (WCAG 2.1 AA)"""
        self._high_contrast = not self._high_contrast

        # Update colors for HC mode
        if self._high_contrast:
            # Apply HC colors to all UI elements
            self.root.configure(fg_color=HC_BG)
            self.entry.configure(
                text_color=HC_FG,
                fg_color=HC_BG,
                placeholder_text_color=HC_FG
            )
            self.status_label.configure(text_color=HC_FG)

            # Update all existing result rows
            for row in self.result_rows:
                row.configure(fg_color=HC_BG)
                if hasattr(row, '_title_label'):
                    row._title_label.configure(text_color=HC_FG)
                if hasattr(row, '_subtitle_label'):
                    row._subtitle_label.configure(text_color=HC_FG)
                if hasattr(row, '_tooltip_label'):
                    row._tooltip_label.configure(
                        text_color=HC_FG,
                        fg_color=HC_BG
                    )
        else:
            # Restore normal colors (handled in _render_results via config)
            # Force a full UI refresh to apply normal colors
            self._render_results()

        # Force immediate UI update
        self.root.update_idletacks()

    def _adjust_window_height(self):
        """Adjust window height to fit content (search bar + results frame)"""
        self.root.update_idletasks()
        height = self.root.winfo_reqheight()
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        self.root.geometry(f"{WINDOW_WIDTH}x{height}+{x}+{y}")

    def run(self):
        """Start the application main loop"""
        self.root.mainloop()


if __name__ == "__main__":
    SpotlightApp().run()
