# What is it?

qtProperTree is a cross-platform GUI plist editor written in Python and Qt (PySide6).

## Disclaimer

The code in this repository was authored with the assistance of a large language model (LLM). It is provided as-is, without warranty of any kind. The maintainer takes no responsibility for bugs, data loss, or any other issues that may arise from its use. Use at your own risk.

## Acknowledgements

qtProperTree is a Qt port of [ProperTree](https://github.com/corpnewt/ProperTree) by [corpnewt](https://github.com/corpnewt). All credit for the original concept, feature set, and OpenCore integration goes to them.

## Features

- [x] Cross-platform - works on macOS, Windows, and Linux
- [x] Document-based to support multiple windows
- [x] Reorder nodes by drag and drop, or with `Ctrl+Up` / `Ctrl+Down` — moves are fully undoable
- [x] Copy and paste
- [x] Find/Replace - allows searching keys or values
- [x] Ordered - or unordered - dictionary support
- [x] Full undo-redo stack
- [x] Expanded integer casting to allow for hex integers (eg. `0xFFFF`) in xml `<integer>` tags
- [x] Context-aware right-click menu that includes template info to OpenCore or Clover config.plist files
- [x] OC (Clean) Snapshot to walk the contents of ACPI, Drivers, Kexts, and Tools for OpenCore config.plist files
- [x] Value converter that supports Base64, Hex, Ascii, and Decimal
- [x] Settings dialog (`Ctrl+,`) to configure behaviour, display defaults, drag dead zone, undo limit, and more

***

## Getting qtProperTree

### Downloading A Release

Pre-built macOS `.dmg` files (arm64 and x86_64) are available on the [releases page](https://github.com/SteveParson/qtProperTree/releases). Download the `.dmg` for your architecture, open it, and drag the app to your Applications folder.

### Cloning The Repo Via Git

```
git clone https://github.com/SteveParson/qtProperTree
cd qtProperTree
```

### Running

qtProperTree requires Python 3.12 and uses [uv](https://docs.astral.sh/uv/) for dependency management.

```
uv run python main.py
```

Or install via the project script entry point:

```
uv run qtpropertree
```

***

## Project Structure

```
qtProperTree/
├── main.py                    # Entry point
├── propertree/                # Main package
│   ├── __init__.py
│   ├── plist.py               # Plist parsing / serialization
│   ├── qt_app.py              # Application controller
│   ├── qt_plist_window.py     # Plist editor window
│   ├── qt_delegates.py        # Tree-view delegates
│   ├── qt_settings_window.py  # Settings dialog
│   ├── qt_converter_window.py # Value converter dialog
│   ├── qt_workers.py          # Background workers (update check, etc.)
│   ├── config_tex_info.py     # OpenCore Configuration.tex helpers
│   ├── settings.json          # Default settings
│   ├── menu.plist             # Context menu templates
│   └── snapshot.plist         # OC Snapshot schema data
├── tests/                     # Test suite (pytest)
└── pyproject.toml
```

***

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Z` / `Ctrl+Y` | Undo / Redo |
| `Ctrl+C` / `Ctrl+V` | Copy / Paste |
| `Ctrl+Shift+C` | Copy children |
| `Ctrl+=` | New row |
| `Ctrl+-` | Remove row |
| `Ctrl+Up` | Move selected item up |
| `Ctrl+Down` | Move selected item down |
| `Ctrl+[` / `Ctrl+]` | Cycle type backward / forward |
| `Return` | Edit selected cell |
| `Delete` / `Backspace` | Remove selected row |
| `Ctrl+F` | Toggle Find/Replace |
| `Ctrl+P` | Toggle Type pane |
| `Ctrl+R` | OC Snapshot |
| `Ctrl+Shift+R` | OC Clean Snapshot |
| `Ctrl+,` | Settings |
| `Ctrl+T` | Value Converter |

