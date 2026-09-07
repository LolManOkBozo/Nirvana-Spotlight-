"""
System index for apps, files, and folders search (Low-End Optimized)
"""
import os
from pathlib import Path
from functools import lru_cache

import win32com.client
import pythoncom

from config import SHORTCUT_DIRS, MAX_RESULTS, LOW_END_MODE


class SystemIndex:
    def __init__(self):
        self.apps = []
        self.refresh_apps()

        # Initialize COM exactly once for the main thread
        if pythoncom:
            pythoncom.CoInitialize()

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
        """Search for applications by name"""
        q = query.lower().strip()
        # ⚡ OPTIMIZATION: Early exit for empty/very short queries
        if len(q) < 2:
            return []

        starts, contains = [], []
        for name, path in self.apps:
            low = name.lower()
            if low.startswith(q):
                starts.append((name, path))
            elif q in low:
                contains.append((name, path))
        starts.sort(key=lambda x: x[0].lower())
        contains.sort(key=lambda x: x[0].lower())
        return starts + contains

    @lru_cache(maxsize=16 if LOW_END_MODE else 32)  # ⚡ OPTIMIZATION: Smaller cache on low-end
    def _cached_file_search(self, query: str):
        """Cached Windows Search API call (LRU cache for repeated queries)"""
        if not win32com or not pythoncom or not query.strip():
            return []

        # ⚡ OPTIMIZATION: Skip search for trivial queries
        if len(query.strip()) < 2:
            return []

        try:
            conn = win32com.client.Dispatch("ADODB.Connection")
            conn.Open("Provider=Search.CollatorDSO;Extended Properties='Application=Windows';")

            term_esc = query.replace("'", "''").strip()
            sql = f"SELECT System.ItemNameDisplay, System.ItemPathDisplay FROM SystemIndex WHERE System.FileName LIKE '%{term_esc}%' ORDER BY System.Search.Rank DESC"

            rs = win32com.client.Dispatch("ADODB.Recordset")
            rs.Open(sql, conn)

            results = []
            # ⚡ OPTIMIZATION: Early exit if we get enough results fast
            while not rs.EOF and len(results) < MAX_RESULTS:
                name = rs.Fields.Item("System.ItemNameDisplay").Value
                path = rs.Fields.Item("System.ItemPathDisplay").Value
                if name and path:
                    is_dir = os.path.isdir(path)
                    results.append((name, path, is_dir))
                rs.MoveNext()

            rs.Close()
            conn.Close()
            return results
        except Exception:
            # Silently fail - Windows Search might not be available/indexed
            return []

    def search_windows_files(self, query: str, limit=MAX_RESULTS):
        """Public interface for file search with caching"""
        return self._cached_file_search(query.strip())[:limit]
