"""
System index for apps, files, and folders search (Optimized with Cache, Scoring & Usage Tracking)
"""
import os
import re
import sys
import threading
import time
import sqlite3
import json
from pathlib import Path
from collections import defaultdict

import win32com.client
import pythoncom

try:
    from winsdk.windows.storage.search import *
    from winsdk.windows.storage import *
    WINRT_AVAILABLE = True
except ImportError:
    WINRT_AVAILABLE = False

from config import (
    SHORTCUT_DIRS,
    MAX_RESULTS,
    LOW_END_MODE,
    CACHE_EXPIRY_SECONDS,
    CACHE_DIR,
    USAGE_FILE
)
from utils import matches_acronym


class SystemIndex:
    def __init__(self):
        self.apps = []
        self._last_usage_save = 0
        self.cache_lock = threading.Lock()

        # Initialize cache database with WAL mode for speed
        self._init_cache_db()

        # Initialize usage tracking
        self.usage_counts = defaultdict(int)
        self._load_usage_counts()

        # Initial background scan of apps
        self.refresh_apps()

        # Preload common searches in background (skip on low-end to save resources)
        if not LOW_END_MODE:
            threading.Thread(target=self._preload_common_searches, daemon=True).start()

    def _init_cache_db(self):
        """Initialize SQLite cache database with WAL mode for fast concurrent operations"""
        self.cache_db = sqlite3.connect(str(CACHE_DIR / "search_cache.db"), check_same_thread=False)
        with self.cache_lock:
            self.cache_db.execute("PRAGMA journal_mode=WAL;")
            self.cache_db.execute("PRAGMA synchronous=NORMAL;")
            self.cache_db.execute("""
                CREATE TABLE IF NOT EXISTS search_cache (
                    query TEXT PRIMARY KEY,
                    results TEXT,  -- JSON serialized
                    timestamp REAL
                )
            """)
            self.cache_db.commit()

    def _load_usage_counts(self):
        """Load usage counts from JSON file"""
        if USAGE_FILE.exists():
            try:
                with open(USAGE_FILE, 'r') as f:
                    data = json.load(f)
                    self.usage_counts = defaultdict(int, data)
            except Exception:
                self.usage_counts = defaultdict(int)

    def _save_usage_counts(self):
        """Save usage counts to JSON file"""
        try:
            with open(USAGE_FILE, 'w') as f:
                json.dump(dict(self.usage_counts), f)
        except Exception:
            pass

    def record_launch(self, path: str):
        """Increment usage count when the user actually launches an item"""
        if not path:
            return
        self.usage_counts[path] += 1
        # Debounce saves to avoid excessive disk writes
        now = time.time()
        if now - self._last_usage_save > 3:
            self._save_usage_counts()
            self._last_usage_save = now

    def _get_from_cache(self, query: str):
        """Get results from cache if not expired"""
        try:
            with self.cache_lock:
                cursor = self.cache_db.execute(
                    "SELECT results, timestamp FROM search_cache WHERE query = ?",
                    (query,)
                )
                row = cursor.fetchone()
                if row:
                    results_json, timestamp = row
                    if time.time() - timestamp < CACHE_EXPIRY_SECONDS:
                        return json.loads(results_json)
                    else:
                        self.cache_db.execute("DELETE FROM search_cache WHERE query = ?", (query,))
                        self.cache_db.commit()
        except Exception:
            pass
        return None

    def _save_to_cache(self, query: str, results):
        """Save results to cache with current timestamp"""
        try:
            with self.cache_lock:
                self.cache_db.execute(
                    "DELETE FROM search_cache WHERE timestamp < ?",
                    (time.time() - CACHE_EXPIRY_SECONDS * 2,)
                )
                self.cache_db.execute(
                    "INSERT OR REPLACE INTO search_cache (query, results, timestamp) VALUES (?, ?, ?)",
                    (query, json.dumps(results), time.time())
                )
                self.cache_db.commit()
        except Exception:
            pass

    def refresh_apps(self):
        """Refresh the list of installed applications from Start Menu and shortcuts"""
        found = {}

        # Built-in Windows system utilities
        builtin_tools = [
            ("Calculator", "calc.exe"),
            ("Notepad", "notepad.exe"),
            ("Paint", "mspaint.exe"),
            ("Task Manager", "taskmgr.exe"),
            ("Control Panel", "control.exe"),
            ("Settings", "ms-settings:"),
            ("File Explorer", "explorer.exe"),
            ("Snipping Tool", "snippingtool.exe"),
            ("Registry Editor", "regedit.exe"),
            ("Command Prompt", "cmd.exe"),
            ("Windows PowerShell", "powershell.exe"),
            ("Windows Terminal", "wt.exe"),
        ]
        for name, cmd in builtin_tools:
            found[name.lower()] = (name, cmd)

        for base in SHORTCUT_DIRS:
            if not base.exists():
                continue
            try:
                for path in base.rglob("*.lnk"):
                    name = path.stem
                    if name.lower() not in found:
                        found[name.lower()] = (name, str(path))
            except Exception:
                continue
        self.apps = list(found.values())

    def search_apps(self, query: str):
        """Search for applications with acronym, prefix, and usage scoring"""
        q = query.lower().strip()
        if not q:
            return []

        scored = []
        for name, path in self.apps:
            low = name.lower()
            score = 0
            if low == q:
                score = 160
            elif low.startswith(q):
                score = 110
            elif any(part.startswith(q) for part in re.split(r"[\s\-_]+", low)):
                score = 85
            elif matches_acronym(q, name):
                score = 75
            elif q in low:
                score = 45

            if score > 0:
                # Add usage weighting (up to +60 points for frequently launched apps)
                score += min(self.usage_counts.get(path, 0) * 4, 60)
                scored.append((score, name, path))

        scored.sort(key=lambda item: (-item[0], item[1].lower()))
        return [(name, path) for _, name, path in scored]

    def _cached_file_search(self, query: str):
        """Perform Windows search with caching and fallback"""
        cached = self._get_from_cache(query)
        if cached is not None:
            return cached

        results = []

        # Try WinRT first if available
        if WINRT_AVAILABLE:
            try:
                query_str = f'"*{query}*"'
                searcher = StorageFileQueryResult.CreateWithOptions(
                    KnownFolders.AllApplications,
                    QueryOptions(CommonFileQuery.OrderByName, [query_str]),
                    None
                )
                files = searcher.GetFiles()
                for file in files:
                    name = file.Name
                    path = file.Path
                    results.append((name, path, False))
                    if len(results) >= MAX_RESULTS:
                        break
            except Exception:
                pass

        # COM Windows Search fallback
        if not results:
            co_init = False
            try:
                pythoncom.CoInitialize()
                co_init = True
                conn = win32com.client.Dispatch("ADODB.Connection")
                conn.Open("Provider=Search.CollatorDSO;Extended Properties='Application=Windows';")

                term_esc = query.replace("'", "''").strip()
                sql = f"SELECT System.ItemNameDisplay, System.ItemPathDisplay FROM SystemIndex WHERE System.FileName LIKE '%{term_esc}%' ORDER BY System.Search.Rank DESC"

                rs = win32com.client.Dispatch("ADODB.Recordset")
                rs.Open(sql, conn)

                while not rs.EOF and len(results) < MAX_RESULTS:
                    name = rs.Fields.Item("System.ItemNameDisplay").Value
                    path = rs.Fields.Item("System.ItemPathDisplay").Value
                    if name and path:
                        is_dir = os.path.isdir(path)
                        results.append((name, path, is_dir))
                    rs.MoveNext()

                rs.Close()
                conn.Close()
            except Exception:
                pass
            finally:
                if co_init:
                    try:
                        pythoncom.CoUninitialize()
                    except Exception:
                        pass

        if results:
            self._save_to_cache(query, results)

        return results

    def search_windows_files(self, query: str, limit=MAX_RESULTS):
        """Public interface for file search with usage prioritization"""
        results = self._cached_file_search(query)
        if not results:
            return []

        results.sort(key=lambda x: (-self.usage_counts[x[1]], x[0].lower()))
        return results[:limit]

    def _preload_common_searches(self):
        """Preload common searches in background thread"""
        common = ["doc", "pdf", "txt", "code", "download"]
        for term in common:
            try:
                self._cached_file_search(term)
            except Exception:
                pass
            time.sleep(0.1)

 