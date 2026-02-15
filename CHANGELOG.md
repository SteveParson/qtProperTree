# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `Ctrl+Up` / `Ctrl+Down` keyboard shortcuts to move the selected tree item up or down among its siblings, available in the Edit menu and right-click context menu. Moves are fully undoable.
- `ProperTreeApp.show_settings()` and `show_converter()` — Settings and Value Converter dialogs can now be opened from the File menu.

### Fixed
- CI: replaced deprecated `macos-13` GitHub Actions runner with `macos-15-intel` for x86_64 builds.
- CI: build release tags now use a `YYYY-MM-DD` date format instead of the full commit SHA.
- Drag-and-drop: locked the dragged item to the one clicked at mouse-down, preventing children from being grabbed instead when the cursor drifted during a drag.
- Drag-and-drop: hovering over an expanded sibling's children no longer causes the dragged item to be inserted inside that sibling; it now always reorders at the same level.
- Drag-and-drop: added hysteresis to prevent items from oscillating when the cursor rests near a row boundary after a swap.

### Changed
- Settings dialog: controls for unimplemented settings (color themes, font customisation, new plist default type, OC snapshot version, force schema update, warn on external modification) are now greyed out with a "Not yet implemented" tooltip.
