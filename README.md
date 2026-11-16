# Nirvana

Professional macOS Spotlight-inspired search tool for Windows — optimized for speed, accessibility, and daily use.

## ✨ Features
- **💡 Animated Features Popup**: Floating shortcut guide directly on top of the search bar with interactive chips, spring animation, and 1-click execution (toggle with 💡 button, F1, or Alt+F)
- **⚡ Non-Blocking & Blazing Fast**: Background worker threading + SQLite WAL caching for instant typing with zero UI stutter
- **🎨 Windows 11 Fluent & macOS Aesthetic**: Rounded corners, native drop shadow, and dynamic System / Dark / Light / High-Contrast themes
- **🎯 Acronym & Smart App Search**: Find apps fast by abbreviation (e.g. `vsc` → Visual Studio Code, `calc` → Calculator, `ps` → PowerShell)
- **🏷️ Modern Category Badges**: Visual tags (`APP`, `DIR`, `FILE`, `MATH`, `SYS`, `CMD`, `URL`, `WEB`) and clean middle-truncated paths
- **🖥️ System Commands**: Quick actions for `lock`, `sleep`, `restart`, `shutdown`, and `empty trash`
- **💻 Terminal Command Runner**: Prefix query with `>` to run directly in Windows Command Prompt (e.g. `> ping 8.8.8.8`, `> ipconfig`)
- **🌐 Direct URL Navigation**: Type domains like `github.com` or URLs to open directly in your browser
- **🧮 Math Solver**: Instant calculation for math expressions + one-press copy to clipboard
- **🎙️ Voice Search**: Alt+K toggles Windows Dictation (100% offline)
- **♿ Accessibility**: WCAG 2.1 AA compliant high-contrast theme
- **📎 System Tray**: Easy theme switching, app index refresh, and toggle hotkeys

## 🚀 Installation
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the app
python main.py
