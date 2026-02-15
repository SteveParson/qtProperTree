# What is it?

qtProperTree is a cross-platform GUI plist editor written in Python and Qt (PySide6).

## Features

- [x] Cross-platform - works on macOS, Windows, and Linux
- [x] Document-based to support multiple windows
- [x] Node drag and drop to reorder
- [x] Copy and paste
- [x] Find/Replace - allows searching keys or values
- [x] Ordered - or unordered - dictionary support
- [x] Full undo-redo stack
- [x] Expanded integer casting to allow for hex integers (eg. `0xFFFF`) in xml `<integer>` tags
- [x] Context-aware right-click menu that includes template info to OpenCore or Clover config.plist files
- [x] OC (Clean) Snapshot to walk the contents of ACPI, Drivers, Kexts, and Tools for OpenCore config.plist files
- [x] Value converter that supports Base64, Hex, Ascii, and Decimal

***

## Getting qtProperTree

### Downloading The Repo As A ZIP File

On any system you can choose the green `Code` button, followed by the `Download ZIP` button (or click [here](https://github.com/SteveParson/qtProperTree/archive/refs/heads/master.zip)) to download the entire repo as a zip file (note, this does not allow you to update via `git pull` - any updates would require you to download the repo again in the same fashion).

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

## FAQ

* **What does OC Snapshot do?**

  The OC Snapshot function will prompt you to select an OC folder, then walk the contents of the ACPI, Kexts, Tools, and Drivers directories within that folder - comparing all entries to the current document's `ACPI -> Add`, `Kernel -> Add`, `Misc -> Tools`, and `UEFI -> Drivers` respectively.  It will add or remove entries as needed, and also ensures kext load order by comparing each kext's `CFBundleIdentifier` to all other kexts' `OSBundleLibraries` within their Info.plist - making sure that any kext that is relied on by others is loaded before them.  It will also warn if it detects duplicate `CFBundleIdentifiers` (with support for `MinKernel`, `MaxKernel`, and `MatchKernel` overlap checks), and offer to disable all after the first found.  It checks for disabled parent kexts with enabled child kexts as well.  The schema used is (by default) determined by comparing the MD5 hash of the `OpenCore.efi` file to a known list of Acidanthera debug/release versions.  If the MD5 hash does not match any known version, it will fall back to the newest schema in the script's `snapshot.plist`.  This behavior can be customized in the Settings per the `OC Snapshot Target Version` menu.

* **What is the difference between OC Snapshot and OC Clean Snapshot?**

  Both snapshot variants accomplish the same tasks - they just leverage different starting points.  An OC **Clean** Snapshot will first clear out `ACPI -> Add`, `Kernel -> Add`, `Misc -> Tools`, and `UEFI -> Drivers`, then add everything from within the respective ACPI, Kexts, Tools, and Drivers directory anew.  A regular OC Snapshot starts with the information within the current document for those four locations, and only pulls changes - adding and removing entries as needed.

* **When should I use an OC Clean Snapshot vs an OC Snapshot?**

  Typically, an OC **Clean** Snapshot should only be used the first time you snapshot to ensure any sample entries in the config.plist are removed and added anew.  Every subsequent snapshot should be a regular OC Snapshot to ensure any customizations you've made are preserved.

* **How can I have qtProperTree open when I double-click a .plist file?**

  On macOS you can associate `.plist` files with the qtProperTree application.

  On Windows, you can associate `.plist` files with `qtpropertree` to add an `Open with qtProperTree` option to the context menu when right-clicking .plist files.
