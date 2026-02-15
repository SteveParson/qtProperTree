# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the application
uv run python main.py

# Install dependencies
uv sync --group dev

# Run tests
uv run pytest

# Run a single test
uv run pytest tests/test_plist_window.py::test_name

# Lint and format
uv run ruff check .
uv run ruff format .

# Build macOS app bundle (produces .app and .dmg)
uv run pyinstaller --windowed --icon propertree/shortcut.icns \
  --osx-bundle-identifier com.steveparson.qtpropertree \
  --add-data propertree/menu.plist:propertree \
  --add-data propertree/snapshot.plist:propertree \
  main.py
```

## Architecture

**qtProperTree** is a Qt/Python plist editor (port of [ProperTree](https://github.com/corpnewt/ProperTree)) with OpenCore config support.

### Component Relationships

```
main.py
  └── ProperTreeApp (qt_app.py)       # Application controller & global state
        ├── PlistWindow (qt_plist_window.py)  # One per open file
        │     └── PlistItemDelegate (qt_delegates.py)  # Inline cell editing
        ├── SettingsWindow (qt_settings_window.py)
        ├── ConverterWindow (qt_converter_window.py)
        └── Background workers (qt_workers.py)
```

### Key Modules

- **`plist.py`** — Custom plist parser that monkey-patches `plistlib` to support `0x` hex integers in XML plists and preserve key order.
- **`qt_app.py`** (`ProperTreeApp`) — Owns settings, window lifecycle, theme detection (polling via platform-specific subprocesses), and file operations. Settings persisted to `propertree/settings.json`.
- **`qt_plist_window.py`** (`PlistWindow`) — The bulk of the application (~2800 lines). Uses a 3-column `QStandardItemModel` (Key, Type, Value). Implements undo/redo with dual `deque` stacks, custom drag-drop with hysteresis, find/replace, OC snapshot, and right-click context menus.
- **`config_tex_info.py`** — Parses OpenCore's `Configuration.tex` (LaTeX) to provide context-sensitive help in the right-click menu.

### Data Flow

1. `ProperTreeApp.open_plist()` → `PlistWindow.open_plist()` → `plist.load()` parses file
2. Parsed data populates `QStandardItemModel` (tree view)
3. Edits go through `PlistItemDelegate`, which validates and calls `add_undo()` before committing
4. Save: `PlistWindow.save_plist()` → `plist.dump()` serializes tree back to XML or binary

### Undo/Redo

Each undoable operation records a dict with `action`, `item`, `parent`, `row`, and snapshot of previous/new values pushed to `undo_stack` (max 200, configurable). `undo_stack` and `redo_stack` are `collections.deque`.

### Column Constants

```python
COL_KEY   = 0
COL_TYPE  = 1
COL_VALUE = 2
```

### Testing

Tests use `pytest` with a session-scoped `qapp` fixture (avoids multiple `QApplication` instances) and a `FakeController` mock for `ProperTreeApp`. Tests live in `tests/test_plist_window.py`.

### CI/CD

GitHub Actions (`.github/workflows/build-macos.yml`) builds DMGs for both arm64 and x86_64 macOS on push to main or version tags, releasing as `build-YYYY-MM-DD` prereleases.
