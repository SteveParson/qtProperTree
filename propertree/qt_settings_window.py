from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFontComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QWidget,
)


class ColorSwatch(QLabel):
    """A clickable color swatch label that opens a QColorDialog on click."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)
        self.setMinimumWidth(60)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFrameShape(QFrame.Box)
        self._color = "#000000"

    def set_color(self, color):
        self._color = color
        self.setStyleSheet("background-color: {};".format(color))

    def get_color(self):
        return self._color

    def mousePressEvent(self, event):
        self.clicked.emit()


class SettingsWindow(QDialog):
    """PySide6 settings dialog for qtProperTree."""

    # Default color schemes
    DEFAULT_DARK = {
        "alternating_color_1": "#161616",
        "alternating_color_2": "#202020",
        "highlight_color": "#1E90FF",
        "background_color": "#161616",
        "invert_background_text_color": False,
        "invert_row1_text_color": False,
        "invert_row2_text_color": False,
    }
    DEFAULT_LIGHT = {
        "alternating_color_1": "#F0F1F1",
        "alternating_color_2": "#FEFEFE",
        "highlight_color": "#1E90FF",
        "background_color": "#FEFEFE",
        "invert_background_text_color": False,
        "invert_row1_text_color": False,
        "invert_row2_text_color": False,
    }

    ALLOWED_TYPES = ("XML", "Binary")
    ALLOWED_DATA = ("Hex", "Base64")
    ALLOWED_INT = ("Decimal", "Hex")
    ALLOWED_BOOL = ("True/False", "YES/NO", "On/Off", "1/0", "\u2714/\u2718")

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("qtProperTree Settings")

        self._building = False  # Guard against callbacks during load

        self._build_ui()
        self.load_settings()

        # Lock the size after the layout has been computed
        self.adjustSize()
        self.setFixedSize(self.size())

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        grid = QGridLayout(self)
        grid.setSpacing(6)
        grid.setContentsMargins(10, 10, 10, 10)

        # ---- Left column header ----
        left_header = QLabel("Functionality Options:")
        left_header.setStyleSheet("font-weight: bold;")
        grid.addWidget(left_header, 0, 0, 1, 2)

        row = 1

        # 1. Expand children
        self.chk_expand = QCheckBox("Expand Children When Opening Plist")
        self.chk_expand.toggled.connect(self._on_expand)
        grid.addWidget(self.chk_expand, row, 0, 1, 2)
        row += 1

        # 2. Xcode data
        self.chk_xcode = QCheckBox("Use Xcode-Style <data> Tags (Inline) in XML Plists")
        self.chk_xcode.toggled.connect(self._on_xcode)
        grid.addWidget(self.chk_xcode, row, 0, 1, 2)
        row += 1

        # 3. Sort dict
        self.chk_sort = QCheckBox("Ignore Dictionary Key Order")
        self.chk_sort.toggled.connect(self._on_sort)
        grid.addWidget(self.chk_sort, row, 0, 1, 2)
        row += 1

        # 4. Comment strip ignore case
        self.chk_ignore_case = QCheckBox("Ignore Case When Stripping Comments")
        self.chk_ignore_case.toggled.connect(self._on_ignore_case)
        grid.addWidget(self.chk_ignore_case, row, 0, 1, 2)
        row += 1

        # 5. Comment strip check string
        self.chk_check_string = QCheckBox("Check String Values When Stripping Comments")
        self.chk_check_string.toggled.connect(self._on_check_string)
        grid.addWidget(self.chk_check_string, row, 0, 1, 2)
        row += 1

        # 6. Comment prefix
        lbl = QLabel("Comment Prefix (default is #):")
        self.txt_comment_prefix = QLineEdit()
        self.txt_comment_prefix.setMaximumWidth(120)
        self.txt_comment_prefix.editingFinished.connect(self._on_comment_prefix)
        grid.addWidget(lbl, row, 0)
        grid.addWidget(self.txt_comment_prefix, row, 1)
        row += 1

        # 7. Default new plist type
        self.lbl_plist_type = QLabel("Default New Plist Type:")
        self.cmb_plist_type = QComboBox()
        self.cmb_plist_type.addItems(self.ALLOWED_TYPES)
        self.cmb_plist_type.currentTextChanged.connect(self._on_plist_type)
        grid.addWidget(self.lbl_plist_type, row, 0)
        grid.addWidget(self.cmb_plist_type, row, 1)
        row += 1

        # 8. Data display
        lbl = QLabel("Data Display Default:")
        self.cmb_data = QComboBox()
        self.cmb_data.addItems(self.ALLOWED_DATA)
        self.cmb_data.currentTextChanged.connect(self._on_data_type)
        grid.addWidget(lbl, row, 0)
        grid.addWidget(self.cmb_data, row, 1)
        row += 1

        # 9. Integer display
        lbl = QLabel("Integer Display Default:")
        self.cmb_int = QComboBox()
        self.cmb_int.addItems(self.ALLOWED_INT)
        self.cmb_int.currentTextChanged.connect(self._on_int_type)
        grid.addWidget(lbl, row, 0)
        grid.addWidget(self.cmb_int, row, 1)
        row += 1

        # 10. Boolean display
        lbl = QLabel("Boolean Display Default:")
        self.cmb_bool = QComboBox()
        self.cmb_bool.addItems(self.ALLOWED_BOOL)
        self.cmb_bool.currentTextChanged.connect(self._on_bool_type)
        grid.addWidget(lbl, row, 0)
        grid.addWidget(self.cmb_bool, row, 1)
        row += 1

        # 11. Snapshot version
        self.lbl_snapshot = QLabel("OC Snapshot Target Version:")
        self.cmb_snapshot = QComboBox()
        self.cmb_snapshot.currentTextChanged.connect(self._on_snapshot_version)
        grid.addWidget(self.lbl_snapshot, row, 0)
        grid.addWidget(self.cmb_snapshot, row, 1)
        row += 1

        # 12. Force snapshot schema
        self.chk_force_schema = QCheckBox("Force Update Snapshot Schema")
        self.chk_force_schema.toggled.connect(self._on_force_schema)
        grid.addWidget(self.chk_force_schema, row, 0, 1, 2)
        row += 1

        # 13. Warn if modified
        self.chk_warn_modified = QCheckBox("Warn If Files Are Externally Modified")
        self.chk_warn_modified.toggled.connect(self._on_warn_modified)
        grid.addWidget(self.chk_warn_modified, row, 0, 1, 2)
        row += 1

        # 14. Edit values before keys
        self.chk_edit_values = QCheckBox("Enter Edits Values Before Keys Where Possible")
        self.chk_edit_values.toggled.connect(self._on_edit_values)
        grid.addWidget(self.chk_edit_values, row, 0, 1, 2)
        row += 1

        # 15. Enable drag & drop
        self.chk_drag_drop = QCheckBox("Enable Row Drag & Drop")
        self.chk_drag_drop.toggled.connect(self._on_drag_drop)
        grid.addWidget(self.chk_drag_drop, row, 0, 1, 2)
        row += 1

        # 16. Drag dead zone
        lbl_drag = QLabel("Drag Dead Zone (1-100 pixels):")
        self.lbl_drag_val = QLabel("20")
        self.lbl_drag_val.setFixedWidth(30)
        self.sld_drag = QSlider(Qt.Horizontal)
        self.sld_drag.setRange(1, 100)
        self.sld_drag.setValue(20)
        self.sld_drag.valueChanged.connect(self._on_drag_zone)
        drag_widget = QWidget()
        drag_lay = QHBoxLayout(drag_widget)
        drag_lay.setContentsMargins(0, 0, 0, 0)
        drag_lay.addWidget(self.lbl_drag_val)
        drag_lay.addWidget(self.sld_drag, 1)
        grid.addWidget(lbl_drag, row, 0)
        grid.addWidget(drag_widget, row, 1)
        row += 1

        # 17. Max undo
        lbl = QLabel("Max Undo (0=unlim, 200=default):")
        self.txt_max_undo = QLineEdit()
        self.txt_max_undo.setMaximumWidth(120)
        self.txt_max_undo.editingFinished.connect(self._on_max_undo)
        grid.addWidget(lbl, row, 0)
        grid.addWidget(self.txt_max_undo, row, 1)
        row += 1

        left_max_row = row

        # ---- Vertical separator ----
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFrameShadow(QFrame.Sunken)
        grid.addWidget(sep, 0, 2, left_max_row, 1)

        # ---- Right column header ----
        right_header = QLabel("Appearance Options:")
        right_header.setStyleSheet("font-weight: bold;")
        grid.addWidget(right_header, 0, 3, 1, 2)

        rrow = 1

        # 1. Opacity
        lbl_op = QLabel("Window Opacity (25-100%):")
        self.lbl_opacity_val = QLabel("100")
        self.lbl_opacity_val.setFixedWidth(30)
        self.sld_opacity = QSlider(Qt.Horizontal)
        self.sld_opacity.setRange(25, 100)
        self.sld_opacity.setValue(100)
        self.sld_opacity.valueChanged.connect(self._on_opacity)
        op_widget = QWidget()
        op_lay = QHBoxLayout(op_widget)
        op_lay.setContentsMargins(0, 0, 0, 0)
        op_lay.addWidget(self.lbl_opacity_val)
        op_lay.addWidget(self.sld_opacity, 1)
        grid.addWidget(lbl_op, rrow, 3)
        grid.addWidget(op_widget, rrow, 4)
        rrow += 1

        # 2. Highlight color
        self.lbl_hl = QLabel("Highlight Color:")
        self.swatch_highlight = ColorSwatch()
        self.swatch_highlight.clicked.connect(lambda: self._pick_color("highlight_color", self.swatch_highlight))
        grid.addWidget(self.lbl_hl, rrow, 3)
        grid.addWidget(self.swatch_highlight, rrow, 4)
        rrow += 1

        # 3. Alternating row color 1
        self.lbl_alt1 = QLabel("Alternating Row Color #1:")
        self.swatch_alt1 = ColorSwatch()
        self.swatch_alt1.clicked.connect(lambda: self._pick_color("alternating_color_1", self.swatch_alt1))
        grid.addWidget(self.lbl_alt1, rrow, 3)
        grid.addWidget(self.swatch_alt1, rrow, 4)
        rrow += 1

        # 4. Alternating row color 2
        self.lbl_alt2 = QLabel("Alternating Row Color #2:")
        self.swatch_alt2 = ColorSwatch()
        self.swatch_alt2.clicked.connect(lambda: self._pick_color("alternating_color_2", self.swatch_alt2))
        grid.addWidget(self.lbl_alt2, rrow, 3)
        grid.addWidget(self.swatch_alt2, rrow, 4)
        rrow += 1

        # 5. Background color
        self.lbl_bg = QLabel("Column Header/BG Color:")
        self.swatch_bg = ColorSwatch()
        self.swatch_bg.clicked.connect(lambda: self._pick_color("background_color", self.swatch_bg))
        grid.addWidget(self.lbl_bg, rrow, 3)
        grid.addWidget(self.swatch_bg, rrow, 4)
        rrow += 1

        # 6. Header text ignores bg
        self.chk_header_ignore = QCheckBox("Header Text Ignores BG Color")
        self.chk_header_ignore.toggled.connect(self._on_header_ignore)
        grid.addWidget(self.chk_header_ignore, rrow, 3, 1, 2)
        rrow += 1

        # 7. Invert header text color
        self.chk_inv_bg = QCheckBox("Invert Header Text Color")
        self.chk_inv_bg.toggled.connect(self._on_inv_bg)
        grid.addWidget(self.chk_inv_bg, rrow, 3, 1, 2)
        rrow += 1

        # 8. Invert row 1 text
        self.chk_inv_r1 = QCheckBox("Invert Row #1 Text Color")
        self.chk_inv_r1.toggled.connect(self._on_inv_r1)
        grid.addWidget(self.chk_inv_r1, rrow, 3, 1, 2)
        rrow += 1

        # 9. Invert row 2 text
        self.chk_inv_r2 = QCheckBox("Invert Row #2 Text Color")
        self.chk_inv_r2.toggled.connect(self._on_inv_r2)
        grid.addWidget(self.chk_inv_r2, rrow, 3, 1, 2)
        rrow += 1

        # 10. Invert highlight text
        self.chk_inv_hl = QCheckBox("Invert Highlight Text Color")
        self.chk_inv_hl.toggled.connect(self._on_inv_hl)
        grid.addWidget(self.chk_inv_hl, rrow, 3, 1, 2)
        rrow += 1

        # 11. Custom font size
        font_size_widget = QWidget()
        fs_lay = QHBoxLayout(font_size_widget)
        fs_lay.setContentsMargins(0, 0, 0, 0)
        self.chk_font_size = QCheckBox("Use Custom Font Size")
        self.chk_font_size.toggled.connect(self._on_font_size_toggle)
        self.spn_font_size = QSpinBox()
        self.spn_font_size.setRange(1, 128)
        self.spn_font_size.setValue(10)
        self.spn_font_size.valueChanged.connect(self._on_font_size_changed)
        fs_lay.addWidget(self.chk_font_size)
        fs_lay.addWidget(self.spn_font_size, 1)
        grid.addWidget(font_size_widget, rrow, 3, 1, 2)
        rrow += 1

        # 12. Custom font family
        font_family_widget = QWidget()
        ff_lay = QHBoxLayout(font_family_widget)
        ff_lay.setContentsMargins(0, 0, 0, 0)
        self.chk_font_family = QCheckBox("Use Custom Font")
        self.chk_font_family.toggled.connect(self._on_font_family_toggle)
        self.cmb_font_family = QFontComboBox()
        self.cmb_font_family.currentFontChanged.connect(self._on_font_family_changed)
        ff_lay.addWidget(self.chk_font_family)
        ff_lay.addWidget(self.cmb_font_family, 1)
        grid.addWidget(font_family_widget, rrow, 3, 1, 2)
        rrow += 1

        # Restore appearance defaults label + separator
        self.lbl_restore = QLabel("Restore Appearance Defaults:")
        self.lbl_restore.setStyleSheet("font-weight: bold;")
        grid.addWidget(self.lbl_restore, rrow, 3, 1, 2)
        rrow += 1

        # 13. Font Defaults button
        self.btn_font_defaults = QPushButton("Font Defaults")
        self.btn_font_defaults.clicked.connect(self._on_font_defaults)
        grid.addWidget(self.btn_font_defaults, rrow, 3)

        # Light mode colors
        self.btn_light = QPushButton("Light Mode Colors")
        self.btn_light.clicked.connect(lambda: self._swap_colors("light"))
        grid.addWidget(self.btn_light, rrow, 4)
        rrow += 1

        # 14. Highlight color reset
        self.btn_hl_default = QPushButton("Highlight Color")
        self.btn_hl_default.clicked.connect(lambda: self._swap_colors("highlight"))
        grid.addWidget(self.btn_hl_default, rrow, 3)

        # Dark mode colors
        self.btn_dark = QPushButton("Dark Mode Colors")
        self.btn_dark.clicked.connect(lambda: self._swap_colors("dark"))
        grid.addWidget(self.btn_dark, rrow, 4)
        rrow += 1

        # ---- Bottom row spanning both columns ----
        bottom_row = max(left_max_row, rrow)

        # Horizontal separator
        hsep = QFrame()
        hsep.setFrameShape(QFrame.HLine)
        hsep.setFrameShadow(QFrame.Sunken)
        grid.addWidget(hsep, bottom_row, 0, 1, 5)
        bottom_row += 1

        # Check for updates
        self.chk_updates = QCheckBox("Check For Updates At Start")
        self.chk_updates.toggled.connect(self._on_check_updates)
        grid.addWidget(self.chk_updates, bottom_row, 0, 1, 2)

        # Check now button
        version_str = "?.?.?"
        if hasattr(self.controller, "version") and isinstance(self.controller.version, dict):
            version_str = self.controller.version.get("version", "?.?.?")
        self.btn_check_now = QPushButton("Check Now ({})".format(version_str))
        self.btn_check_now.clicked.connect(self._on_check_now)
        grid.addWidget(self.btn_check_now, bottom_row, 3)

        # Get Configuration.tex button
        self.btn_get_tex = QPushButton("Get Configuration.tex")
        self.btn_get_tex.clicked.connect(self._on_get_tex)
        grid.addWidget(self.btn_get_tex, bottom_row, 4)
        bottom_row += 1

        # Notify once per version
        self.chk_notify_once = QCheckBox("Only Notify Once Per Version")
        self.chk_notify_once.toggled.connect(self._on_notify_once)
        grid.addWidget(self.chk_notify_once, bottom_row, 0, 1, 2)

        # Restore all defaults button
        btn_restore = QPushButton("Restore All Defaults")
        btn_restore.clicked.connect(self._on_restore_defaults)
        grid.addWidget(btn_restore, bottom_row, 3, 1, 2)
        bottom_row += 1

        self.setLayout(grid)
        self._disable_unimplemented()

    def _disable_unimplemented(self):
        """Grey out every control whose setting is saved but not yet applied."""
        tip = "Not yet implemented"
        for w in (
            # Left column
            self.lbl_plist_type,
            self.cmb_plist_type,
            self.lbl_snapshot,
            self.cmb_snapshot,
            self.chk_force_schema,
            self.chk_warn_modified,
            # Right column — colors
            self.lbl_hl,
            self.swatch_highlight,
            self.lbl_alt1,
            self.swatch_alt1,
            self.lbl_alt2,
            self.swatch_alt2,
            self.lbl_bg,
            self.swatch_bg,
            self.chk_header_ignore,
            self.chk_inv_bg,
            self.chk_inv_r1,
            self.chk_inv_r2,
            self.chk_inv_hl,
            # Right column — fonts
            self.chk_font_size,
            self.spn_font_size,
            self.chk_font_family,
            self.cmb_font_family,
            # Restore appearance defaults section
            self.lbl_restore,
            self.btn_font_defaults,
            self.btn_light,
            self.btn_hl_default,
            self.btn_dark,
        ):
            w.setEnabled(False)
            w.setToolTip(tip)

    # ------------------------------------------------------------------
    # Settings load / populate
    # ------------------------------------------------------------------

    def load_settings(self):
        """Populate all widgets from controller.settings."""
        self._building = True
        s = self.controller.settings

        # Left column - functionality
        self.chk_expand.setChecked(s.get("expand_all_items_on_open", True))
        self.chk_xcode.setChecked(s.get("xcode_data", True))
        self.chk_sort.setChecked(s.get("sort_dict", False))
        self.chk_ignore_case.setChecked(s.get("comment_strip_ignore_case", False))
        self.chk_check_string.setChecked(s.get("comment_strip_check_string", True))

        prefix = s.get("comment_strip_prefix", "#")
        self.txt_comment_prefix.setText(prefix if prefix else "#")

        # Combo boxes
        self._set_combo(self.cmb_plist_type, s.get("new_plist_default_type", "XML"), self.ALLOWED_TYPES)
        self._set_combo(self.cmb_data, s.get("display_data_as", "Hex"), self.ALLOWED_DATA)
        self._set_combo(self.cmb_int, s.get("display_int_as", "Decimal"), self.ALLOWED_INT)
        self._set_combo(self.cmb_bool, s.get("display_bool_as", "True/False"), self.ALLOWED_BOOL)

        # Snapshot versions
        self._populate_snapshot_versions()
        snap_ver = s.get("snapshot_version", "Auto-detect")
        # Try to find the matching entry in the combo
        idx = self.cmb_snapshot.findText(snap_ver, Qt.MatchStartsWith)
        if idx >= 0:
            self.cmb_snapshot.setCurrentIndex(idx)
        else:
            self.cmb_snapshot.setCurrentIndex(0)  # Auto-detect

        self.chk_force_schema.setChecked(s.get("force_snapshot_schema", False))
        self.chk_warn_modified.setChecked(s.get("warn_if_modified", True))
        self.chk_edit_values.setChecked(s.get("edit_values_before_keys", False))
        self.chk_drag_drop.setChecked(s.get("enable_drag_and_drop", True))

        drag_zone = s.get("drag_dead_zone", 20)
        try:
            drag_zone = int(drag_zone)
        except (TypeError, ValueError):
            drag_zone = 20
        self.sld_drag.setValue(max(1, min(100, drag_zone)))
        self.lbl_drag_val.setText(str(self.sld_drag.value()))
        self._update_drag_enabled()

        max_undo = s.get("max_undo", 200)
        if not isinstance(max_undo, int) or max_undo < 0:
            max_undo = 200
        self.txt_max_undo.setText(str(max_undo))

        # Right column - appearance
        opacity = s.get("opacity", 100)
        try:
            opacity = int(opacity)
        except (TypeError, ValueError):
            opacity = 100
        opacity = max(25, min(100, opacity))
        self.sld_opacity.setValue(opacity)
        self.lbl_opacity_val.setText(str(opacity))

        # Color swatches
        default_colors = self.DEFAULT_DARK  # Will be overridden if controller knows mode
        if hasattr(self.controller, "use_dark"):
            default_colors = self.DEFAULT_DARK if self.controller.use_dark else self.DEFAULT_LIGHT

        self.swatch_highlight.set_color(s.get("highlight_color", default_colors["highlight_color"]))
        self.swatch_alt1.set_color(s.get("alternating_color_1", default_colors["alternating_color_1"]))
        self.swatch_alt2.set_color(s.get("alternating_color_2", default_colors["alternating_color_2"]))
        self.swatch_bg.set_color(s.get("background_color", default_colors["background_color"]))

        self.chk_header_ignore.setChecked(s.get("header_text_ignore_bg_color", False))
        self.chk_inv_bg.setChecked(s.get("invert_background_text_color", False))
        self.chk_inv_r1.setChecked(s.get("invert_row1_text_color", False))
        self.chk_inv_r2.setChecked(s.get("invert_row2_text_color", False))
        self.chk_inv_hl.setChecked(s.get("invert_hl_text_color", False))

        # Font settings
        use_custom_size = s.get("use_custom_font_size", False)
        self.chk_font_size.setChecked(use_custom_size)
        self.spn_font_size.setEnabled(use_custom_size)
        font_size = s.get("font_size", 10)
        try:
            font_size = max(1, min(128, int(font_size)))
        except (TypeError, ValueError):
            font_size = 10
        self.spn_font_size.setValue(font_size)

        use_custom_font = s.get("use_custom_font", False)
        self.chk_font_family.setChecked(use_custom_font)
        self.cmb_font_family.setEnabled(use_custom_font)
        font_family = s.get("font_family", "")
        if font_family:
            self.cmb_font_family.setCurrentFont(QFont(font_family))

        # Bottom row
        self.chk_updates.setChecked(s.get("check_for_updates_at_startup", True))
        self.chk_notify_once.setChecked(s.get("notify_once_per_version", True))
        self.chk_notify_once.setEnabled(self.chk_updates.isChecked())

        self._building = False

    def _set_combo(self, combo, value, allowed):
        """Set a combo box to the given value if it is in the allowed list."""
        if value in allowed:
            combo.setCurrentText(value)
        else:
            combo.setCurrentIndex(0)

    def _populate_snapshot_versions(self):
        """Fill the snapshot version combo with Auto-detect, Latest, and
        versions parsed from the controller's snapshot_data."""
        self.cmb_snapshot.blockSignals(True)
        self.cmb_snapshot.clear()
        choices = ["Auto-detect", "Latest"]
        snapshot_data = getattr(self.controller, "snapshot_data", None) or []
        if isinstance(snapshot_data, list):
            version_labels = []
            for snap in snapshot_data:
                if not isinstance(snap, dict):
                    continue
                min_v = snap.get("min_version", "")
                if not min_v:
                    continue
                max_v = snap.get("max_version", "Current")
                if min_v != max_v:
                    version_labels.append("{} -> {}".format(min_v, max_v))
                else:
                    version_labels.append(min_v)
            choices.extend(sorted(version_labels, reverse=True))
        self.cmb_snapshot.addItems(choices)
        self.cmb_snapshot.blockSignals(False)

    def _update_drag_enabled(self):
        """Enable/disable drag dead zone controls based on the drag & drop checkbox."""
        enabled = self.chk_drag_drop.isChecked()
        self.sld_drag.setEnabled(enabled)
        self.lbl_drag_val.setEnabled(enabled)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _settings(self):
        return self.controller.settings

    def _save(self, key, value):
        """Store a single setting and trigger a save if the controller supports it."""
        if self._building:
            return
        self.controller.settings[key] = value

    def _save_and_update_colors(self, key, value):
        self._save(key, value)
        if self._building:
            return
        if hasattr(self.controller, "update_colors"):
            self.controller.update_colors()

    def _save_and_update_fonts(self, key, value):
        self._save(key, value)
        if self._building:
            return
        if hasattr(self.controller, "update_fonts"):
            self.controller.update_fonts()

    # ------------------------------------------------------------------
    # Left column callbacks
    # ------------------------------------------------------------------

    def _on_expand(self, checked):
        self._save("expand_all_items_on_open", checked)

    def _on_xcode(self, checked):
        self._save("xcode_data", checked)

    def _on_sort(self, checked):
        self._save("sort_dict", checked)

    def _on_ignore_case(self, checked):
        self._save("comment_strip_ignore_case", checked)

    def _on_check_string(self, checked):
        self._save("comment_strip_check_string", checked)

    def _on_comment_prefix(self):
        text = self.txt_comment_prefix.text().strip()
        if not text:
            text = "#"
            self.txt_comment_prefix.setText(text)
        self._save("comment_strip_prefix", text)

    def _on_plist_type(self, text):
        self._save("new_plist_default_type", text)

    def _on_data_type(self, text):
        self._save("display_data_as", text)

    def _on_int_type(self, text):
        self._save("display_int_as", text)

    def _on_bool_type(self, text):
        self._save("display_bool_as", text)

    def _on_snapshot_version(self, text):
        if self._building:
            return
        # Store only the version number (first token before any " -> ")
        version = text.split(" ")[0] if text else "Auto-detect"
        self._save("snapshot_version", version)

    def _on_force_schema(self, checked):
        self._save("force_snapshot_schema", checked)

    def _on_warn_modified(self, checked):
        self._save("warn_if_modified", checked)

    def _on_edit_values(self, checked):
        self._save("edit_values_before_keys", checked)

    def _on_drag_drop(self, checked):
        self._save("enable_drag_and_drop", checked)
        self._update_drag_enabled()

    def _on_drag_zone(self, value):
        self.lbl_drag_val.setText(str(value))
        self._save("drag_dead_zone", value)

    def _on_max_undo(self):
        text = self.txt_max_undo.text().strip()
        try:
            val = int(text)
            if val < 0:
                val = 200
        except (ValueError, TypeError):
            val = 200
        self.txt_max_undo.setText(str(val))
        self._save("max_undo", val)

    # ------------------------------------------------------------------
    # Right column callbacks
    # ------------------------------------------------------------------

    def _on_opacity(self, value):
        self.lbl_opacity_val.setText(str(value))
        self._save("opacity", value)
        if not self._building and hasattr(self.controller, "set_window_opacity"):
            self.controller.set_window_opacity(value)

    def _pick_color(self, setting_key, swatch):
        """Open a color dialog, update the swatch and setting."""
        initial = QColor(swatch.get_color())
        color = QColorDialog.getColor(initial, self, "Pick Color")
        if not color.isValid():
            return
        hex_color = color.name()  # e.g. "#1e90ff"
        swatch.set_color(hex_color)
        self._save_and_update_colors(setting_key, hex_color)

    def _on_header_ignore(self, checked):
        self._save_and_update_colors("header_text_ignore_bg_color", checked)

    def _on_inv_bg(self, checked):
        self._save_and_update_colors("invert_background_text_color", checked)

    def _on_inv_r1(self, checked):
        self._save_and_update_colors("invert_row1_text_color", checked)

    def _on_inv_r2(self, checked):
        self._save_and_update_colors("invert_row2_text_color", checked)

    def _on_inv_hl(self, checked):
        self._save_and_update_colors("invert_hl_text_color", checked)

    def _on_font_size_toggle(self, checked):
        self.spn_font_size.setEnabled(checked)
        self._save("use_custom_font_size", checked)
        if not checked:
            self.controller.settings.pop("font_size", None)
        else:
            self._save("font_size", self.spn_font_size.value())
        if not self._building and hasattr(self.controller, "update_fonts"):
            self.controller.update_fonts()

    def _on_font_size_changed(self, value):
        if not self.chk_font_size.isChecked():
            return
        self._save_and_update_fonts("font_size", value)

    def _on_font_family_toggle(self, checked):
        self.cmb_font_family.setEnabled(checked)
        self._save("use_custom_font", checked)
        if checked:
            self._save("font_family", self.cmb_font_family.currentFont().family())
        else:
            self.controller.settings.pop("font_family", None)
        if not self._building and hasattr(self.controller, "update_fonts"):
            self.controller.update_fonts()

    def _on_font_family_changed(self, font):
        if not self.chk_font_family.isChecked():
            return
        self._save("font_family", font.family())
        if not self._building and hasattr(self.controller, "update_fonts"):
            self.controller.update_fonts()

    # ------------------------------------------------------------------
    # Button callbacks
    # ------------------------------------------------------------------

    def _on_font_defaults(self):
        """Reset font settings to defaults."""
        self.controller.settings["use_custom_font_size"] = False
        self.controller.settings.pop("font_size", None)
        self.controller.settings["use_custom_font"] = False
        self.controller.settings.pop("font_family", None)
        self.load_settings()
        if hasattr(self.controller, "update_fonts"):
            self.controller.update_fonts()

    def _swap_colors(self, mode):
        """Apply a color preset (highlight, light, or dark)."""
        if mode == "highlight":
            self.controller.settings.pop("highlight_color", None)
            self.controller.settings.pop("invert_hl_text_color", None)
        elif mode == "light":
            for key, val in self.DEFAULT_LIGHT.items():
                if key == "highlight_color":
                    continue
                self.controller.settings[key] = val
        elif mode == "dark":
            for key, val in self.DEFAULT_DARK.items():
                if key == "highlight_color":
                    continue
                self.controller.settings[key] = val
        self.load_settings()
        if hasattr(self.controller, "update_colors"):
            self.controller.update_colors()

    def _on_check_updates(self, checked):
        self._save("check_for_updates_at_startup", checked)
        self.chk_notify_once.setEnabled(checked)

    def _on_notify_once(self, checked):
        self._save("notify_once_per_version", checked)

    def _on_check_now(self):
        if hasattr(self.controller, "check_for_updates"):
            self.controller.check_for_updates(user_initiated=True)

    def _on_get_tex(self):
        if hasattr(self.controller, "get_latest_tex"):
            self.controller.get_latest_tex()

    def _on_restore_defaults(self):
        """Reset all settings to defaults."""
        self.controller.settings.clear()
        self.load_settings()
        if hasattr(self.controller, "update_colors"):
            self.controller.update_colors()
        if hasattr(self.controller, "update_fonts"):
            self.controller.update_fonts()
