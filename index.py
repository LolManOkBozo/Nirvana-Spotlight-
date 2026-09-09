"""
System index for apps, files, and folders search (Optimized with WinRT, Cache & Usage Tracking)
"""
import os
import re
import sys
import threading
import time
import webbrowser
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


class SystemIndex:
    def __init__(self):
        self.apps = []
        self.refresh_apps()

        # Initialize COM exactly once for the main thread
        if pythoncom:
            pythoncom.CoInitialize()

        # Initialize cache database
        self._init_cache_db()

        # Initialize usage tracking
        self.usage_counts = defaultdict(int)
        self._load_usage_counts()

        # Preload common searches in background (skip on low-end to save resources)
        if not LOW_END_MODE:
            threading.Thread(target=self._preload_common_searches, daemon=True).start()

    def _init_cache_db(self):
        """Initialize SQLite cache database"""
        self.cache_db = sqlite3.connect(str(CACHE_DIR / "search_cache.db"), check_same_thread=False)
        self.cache_db.execute("""
            CREATE TABLE IF NOT EXISTS search_cache (
                query TEXT PRIMARY KEY,
                results TEXT,  -- JSON serialized
                timestamp REAL
            )
        """)
        self.cache_db.commit()
        self.cache_lock = threading.Lock()

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
            pass  # Fail silently - usage tracking is non-critical

    def _increment_usage(self, path: str):
        """Increment usage count for a path and persist"""
        self.usage_counts[path] += 1
        # Debounce saves to avoid excessive disk writes
        if hasattr(self, '_last_usage_save'):
            if time.time() - self._last_usage_save < 5:  # Save at most every 5 seconds
                return
        self._save_usage_counts()
        self._last_usage_save = time.time()

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
                        # Delete expired entry
                        self.cache_db.execute("DELETE FROM search_cache WHERE query = ?", (query,))
                        self.cache_db.commit()
        except Exception:
            pass  # Fail silently - fall back to live search
        return None

    def _save_to_cache(self, query: str, results):
        """Save results to cache with current timestamp"""
        try:
            with self.cache_lock:
                # Remove expired entries first (simple cleanup)
                self.cache_db.execute(
                    "DELETE FROM search_cache WHERE timestamp < ?",
                    (time.time() - CACHE_EXPIRY_SECONDS * 2,)
                )
                # Insert or replace
                self.cache_db.execute(
                    "INSERT OR REPLACE INTO search_cache (query, results, timestamp) VALUES (?, ?, ?)",
                    (query, json.dumps(results), time.time())
                )
                self.cache_db.commit()
        except Exception:
            pass  # Fail silently - cache is optional

    def refresh_apps(self):
        """Refresh the list of installed applications from Start Menu"""
        found = {}
        for base in SHORTCUT_DIRS:
            if not base.exists():
                continue
            for path in base.rglob("*.lnk"):
                name = path.stem
                found[name.lower()] = (name, str(path))
        self.apps = list(found.values())

    def search_apps(self, query: str):
        """Search for applications by name with usage-based prioritization"""
        q = query.lower().strip()
        if len(q) < 2:
            return []

        starts, contains = [], []
        for name, path in self.apps:
            low = name.lower()
            if low.startswith(q):
                starts.append((name, path))
            elif q in low:
                contains.append((name, path))

        # Sort by usage count (descending) then by name
        starts.sort(key=lambda x: (-self.usage_counts[x[1]], x[0].lower()))
        contains.sort(key=lambda x: (-self.usage_counts[x[1]], x[0].lower()))
        return starts + contains

    def _cached_file_search(self, query: str):
        """Cached Windows Search API call with WinRT fallback and usage tracking"""
        # Check cache first
        cached = self._get_from_cache(query)
        if cached is not None:
            return cached

        # If not in cache, perform search
        results = []

        # Try WinRT first (faster, available on Win10+)
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
                    is_dir = False  # WinRT StorageFileQueryResult only returns files
                    results.append((name, path, is_dir))
                    if len(results) >= MAX_RESULTS:
                        break
            except Exception:
                pass  # Fall back to COM if WinRT fails

        # Fall back to COM if WinRT failed or unavailable
        if not results and win32com.client and pythoncom:
            try:
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
                pass  # Fail silently - return empty results

        # Save to cache and increment usage for each result path
        if results:
            self._save_to_cache(query, results)
            for _, path, _ in results:
                self._increment_usage(path)

        return results

    def search_windows_files(self, query: str, limit=MAX_RESULTS):
        """Public interface for file search with caching and usage prioritization"""
        results = self._cached_file_search(query)
        if not results:
            return []

        # Sort by usage count (descending) then by name
        results.sort(key=lambda x: (-self.usage_counts[x[1]], x[0].lower()))
        return results[:limit]

    def _preload_common_searches(self):
        """Preload common searches in background thread"""
        common = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j",
                  "k", "l", "m", "n", "o", "p", "q", "r", "s", "t",
                  "u", "v", "w", "x", "y", "z", "doc", "pic", "vid"]
        for term in common:
            # Run search in background (don't block UI)
            threading.Thread(
                target=lambda t=term: self._cached_file_search(t),
                daemon=True
            ).start()
            # Small delay to avoid overwhelming system
            time.sleep(0.05)
 