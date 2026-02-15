# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `Ctrl+Up` / `Ctrl+Down` keyboard shortcuts to move the selected tree item up or down among its siblings, available in the Edit menu and right-click context menu. Moves are fully undoable.
- `ProperTreeApp.show_settings()` and `show_converter()` — Settings and Value Converter dialogs can now be opened from the File menu.
- **Color theming** — Highlight color, alternating row colors (#1 and #2), and column header/background color are now fully configurable in Settings. Text color inversion flags (header, row #1, row #2, highlight) and the "Header Text Ignores BG Color" option are also wired up.
- **Custom font** — Settings now applies the chosen font family and/or font size to the tree view immediately and persists across sessions.
- **Restore appearance defaults** — The Light Mode Colors, Dark Mode Colors, Highlight Color, and Font Defaults buttons in Settings are now active.
- **Default New Plist Type** — The "Default New Plist Type" combo in Settings now controls whether new (File → New) plist files default to XML or Binary format.
- **Window opacity** — The opacity slider in Settings now takes effect on all open windows immediately.

### Fixed
- CI: replaced deprecated `macos-13` GitHub Actions runner with `macos-15-intel` for x86_64 builds.
- CI: build release tags now use a `YYYY-MM-DD` date format instead of the full commit SHA.
- CI: release descriptions now show the contents of the topmost CHANGELOG.md section instead of unrelated auto-generated commit messages.
- CI: Linux AppImage build added; releases now include a pre-built `x86_64` AppImage compatible with Fedora 36+, Ubuntu 22.04+, Debian 12+, and other glibc 2.35+ distributions.
- Drag-and-drop: locked the dragged item to the one clicked at mouse-down, preventing children from being grabbed instead when the cursor drifted during a drag.
- Drag-and-drop: hovering over an expanded sibling's children no longer causes the dragged item to be inserted inside that sibling; it now always reorders at the same level.
- Drag-and-drop: added hysteresis to prevent items from oscillating when the cursor rests near a row boundary after a swap.

### Changed
- Settings dialog: controls for settings that are not yet implemented (OC Snapshot Target Version, Force Update Snapshot Schema, Warn If Files Are Externally Modified) remain greyed out with a "Not yet implemented" tooltip. All appearance and font controls are now active.
