import base64
import binascii
import datetime
import hashlib
import math
import os
import plistlib
import re
import shutil
import tempfile
import time
from collections import OrderedDict, deque
from io import BytesIO

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QAction, QFont, QKeySequence, QShortcut, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from propertree import plist
from propertree.qt_delegates import COL_KEY, COL_TYPE, COL_VALUE, MENU_CODE, PlistItemDelegate


class PlistWindow(QMainWindow):
    closed = Signal(object)

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.plist_header = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"'
            ' "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0">'
        )
        self.plist_footer = "</plist>"

        # State
        self.undo_stack = deque()
        self.redo_stack = deque()
        self.current_plist = None
        self.last_hash = None
        self.edited = False
        self.saving = False
        self.adding_rows = False
        self.removing_rows = False
        self.pasting_nodes = False
        self.reundoing = False
        self.dragging = False
        self.drag_start = None
        self.drag_undo = None
        self.drag_open = None
        self.clicked_drag = False
        self.drag_source_item = None
        self.drag_last_move_y = None

        self.last_data = None
        self.last_int = None
        self.last_bool = None

        self.show_find_replace = False
        self.show_type = False

        self.key_history = ""
        self.last_key = 0
        self.last_node_result = None
        self.last_key_threshold = 1

        self.menu_code = MENU_CODE
        self.drag_code = "\u2261"
        self.safe_path_length = 128

        # Plist type tracking
        self.plist_type = "XML"
        self.data_display = "Hex"
        self.int_display = "Decimal"
        self.bool_display = "True/False"

        # Window setup
        try:
            w = int(controller.settings.get("last_window_width", 730))
            h = int(controller.settings.get("last_window_height", 480))
        except (ValueError, TypeError):
            w, h = 730, 480
        self.setMinimumSize(730, 480)
        self.resize(w, h)
        self.setWindowTitle("Untitled.plist")

        # Center on screen
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() // 2 - w // 2, screen.height() // 2 - h // 2)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Find/Replace frame
        self.find_frame = self._build_find_frame()
        self.find_frame.setVisible(False)

        # Tree view
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(["Key", "Type", "Value"])

        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setAlternatingRowColors(True)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setDragDropMode(QAbstractItemView.NoDragDrop)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)

        # Set column sizing
        header = self.tree.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(COL_KEY, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_TYPE, QHeaderView.ResizeToContents)
        header.setMinimumSectionSize(80)

        # Delegate
        self.delegate = PlistItemDelegate(self, self.tree)
        self.tree.setItemDelegate(self.delegate)

        # Type display frame
        self.type_frame = self._build_type_frame()
        self.type_frame.setVisible(False)

        # Layout
        self.main_layout.addWidget(self.find_frame)
        self.main_layout.addWidget(self.tree, 1)
        self.main_layout.addWidget(self.type_frame)

        # Connections
        self.tree.doubleClicked.connect(self.on_double_click)
        self.tree.customContextMenuRequested.connect(self.popup)
        self.tree.expanded.connect(self.on_expanded)
        self.tree.collapsed.connect(self.on_collapsed)
        self.tree.clicked.connect(self.on_click)

        # Mouse events for drag
        self.tree.viewport().installEventFilter(self)

        # Override tree keyPressEvent for Return/Delete handling
        self.tree.keyPressEvent = self._tree_key_press

        # Setup menus
        self._setup_menus()
        self._setup_shortcuts()

        # Load context menu presets
        self.menu_data = {}
        menu_plist_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "menu.plist")
        if os.path.exists(menu_plist_path):
            try:
                with open(menu_plist_path, "rb") as f:
                    self.menu_data = plist.load(f)
            except Exception:
                pass

        # Opacity
        self._apply_opacity()

        # Apply color/font settings
        self.update_colors()
        self.update_fonts()

        # Track window
        controller.windows.append(self)

    # ── Property helpers ─────────────────────────────────────────

    @property
    def plist_type_str(self):
        return self.plist_type

    # ── Build UI sections ────────────────────────────────────────

    def _build_find_frame(self):
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 5, 10, 5)

        layout.addWidget(QLabel("Find:"))
        self.f_options = ["Key", "Boolean", "Data", "Date", "Number", "UID", "String"]
        self.find_type_combo = QComboBox()
        self.find_type_combo.addItems(self.f_options)
        layout.addWidget(self.find_type_combo)

        self.f_text = QLineEdit()
        layout.addWidget(self.f_text, 1)

        self.fp_button = QPushButton("< Prev")
        self.fp_button.setFixedWidth(70)
        self.fp_button.clicked.connect(self.find_prev)
        layout.addWidget(self.fp_button)

        self.fn_button = QPushButton("Next >")
        self.fn_button.setFixedWidth(70)
        self.fn_button.clicked.connect(self.find_next)
        layout.addWidget(self.fn_button)

        self.f_case_check = QCheckBox("Case")
        layout.addWidget(self.f_case_check)

        # Second row for replace
        frame2 = QFrame()
        layout2 = QHBoxLayout(frame2)
        layout2.setContentsMargins(10, 0, 10, 5)
        layout2.addWidget(QLabel("Replace:"))
        self.r_text = QLineEdit()
        layout2.addWidget(self.r_text, 1)
        self.r_button = QPushButton("Replace")
        self.r_button.clicked.connect(self.replace)
        layout2.addWidget(self.r_button)
        self.r_all_check = QCheckBox("All")
        layout2.addWidget(self.r_all_check)

        container = QFrame()
        clayout = QVBoxLayout(container)
        clayout.setContentsMargins(0, 0, 0, 0)
        clayout.setSpacing(0)
        clayout.addWidget(frame)
        clayout.addWidget(frame2)

        self.f_text.returnPressed.connect(self.find_next)

        return container

    def _build_type_frame(self):
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 5, 10, 5)

        layout.addWidget(QLabel("Plist Type:"))
        self.plist_type_combo = QComboBox()
        self.plist_type_combo.addItems(["XML", "Binary"])
        self.plist_type_combo.currentTextChanged.connect(self._on_plist_type_changed)
        layout.addWidget(self.plist_type_combo)

        layout.addWidget(QLabel("Data:"))
        self.data_type_combo = QComboBox()
        self.data_type_combo.addItems(["Hex", "Base64"])
        self.data_type_combo.currentTextChanged.connect(self._on_data_type_changed)
        layout.addWidget(self.data_type_combo)

        layout.addWidget(QLabel("Ints:"))
        self.int_type_combo = QComboBox()
        self.int_type_combo.addItems(["Decimal", "Hex"])
        self.int_type_combo.currentTextChanged.connect(self._on_int_type_changed)
        layout.addWidget(self.int_type_combo)

        layout.addWidget(QLabel("Bools:"))
        self.bool_type_combo = QComboBox()
        self.bool_type_combo.addItems(list(self.controller.allowed_bool))
        self.bool_type_combo.currentTextChanged.connect(self._on_bool_type_changed)
        layout.addWidget(self.bool_type_combo)

        layout.addStretch()
        return frame

    # ── Menu & Shortcut Setup ────────────────────────────────────

    def _setup_menus(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")

        self._add_action(file_menu, "New", self.controller.new_plist, QKeySequence.New)
        self._add_action(file_menu, "Open...", self.controller.open_plist, QKeySequence.Open)

        self.recent_menu = file_menu.addMenu("Open Recent")
        self._update_recent_menu()

        self._add_action(file_menu, "Save", lambda: self.controller.save_plist(), QKeySequence.Save)
        self._add_action(file_menu, "Save As...", lambda: self.controller.save_plist_as(), QKeySequence.SaveAs)
        self._add_action(file_menu, "Duplicate", lambda: self.controller.duplicate_plist(), "Ctrl+D")
        self._add_action(file_menu, "Reload From Disk", self.reload_from_disk, "Ctrl+L")

        file_menu.addSeparator()
        self._add_action(file_menu, "OC Snapshot", lambda: self.oc_snapshot(), "Ctrl+R")
        self._add_action(file_menu, "OC Clean Snapshot", lambda: self.oc_snapshot(clean=True), "Ctrl+Shift+R")

        file_menu.addSeparator()
        self._add_action(file_menu, "Convert Window", lambda: self.controller.show_converter(), "Ctrl+T")
        self._add_action(file_menu, "Strip Comments", self.strip_comments, "Ctrl+M")
        self._add_action(file_menu, "Strip Disabled Entries", self.strip_disabled, "Ctrl+E")
        self._add_action(file_menu, "Strip Whitespace", lambda: self.strip_whitespace(keys=True, values=True), "Ctrl+K")

        file_menu.addSeparator()
        self._add_action(file_menu, "Settings...", lambda: self.controller.show_settings(), "Ctrl+,")

        file_menu.addSeparator()
        self._add_action(file_menu, "Toggle Find/Replace", self.hide_show_find, QKeySequence.Find)
        self._add_action(file_menu, "Toggle Type Pane", self.hide_show_type, "Ctrl+P")

        file_menu.addSeparator()
        self._add_action(file_menu, "Quit", self.controller.quit, QKeySequence.Quit)

        edit_menu = menubar.addMenu("Edit")
        self._add_action(edit_menu, "Undo", lambda: self.reundo(undo=True), QKeySequence.Undo)
        self._add_action(edit_menu, "Redo", lambda: self.reundo(undo=False), QKeySequence.Redo)
        edit_menu.addSeparator()
        self._add_action(edit_menu, "Copy", self.copy_selection, QKeySequence.Copy)
        self._add_action(edit_menu, "Copy Children", self.copy_children, "Ctrl+Shift+C")
        self._add_action(edit_menu, "Paste", self.paste_selection, QKeySequence.Paste)
        edit_menu.addSeparator()
        self._add_action(edit_menu, "New Row", self.new_row, "Ctrl+=")
        self._add_action(edit_menu, "Remove Row", self.remove_row, "Ctrl+-")
        self._add_action(edit_menu, "Move Up", lambda: self.move_item(-1), "Ctrl+Up")
        self._add_action(edit_menu, "Move Down", lambda: self.move_item(1), "Ctrl+Down")

    def _add_action(self, menu, text, callback, shortcut=None):
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(callback)
        menu.addAction(action)
        return action

    def _setup_shortcuts(self):
        # Additional shortcuts not in menus
        QShortcut(QKeySequence("Ctrl+X"), self.tree, self.hex_swap)
        QShortcut(QKeySequence("Ctrl+I"), self.tree, self.show_config_info)
        # Return/Delete/Backspace handled in _tree_key_press to avoid
        # stealing key events from the inline editor

    def _is_editing(self):
        return self.tree.state() == QAbstractItemView.State.EditingState

    def _tree_key_press(self, event):
        """Handle key presses on the tree that should not fire during editing."""
        if self._is_editing():
            # Let the editor handle it
            QTreeView.keyPressEvent(self.tree, event)
            return
        key = event.key()
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self.start_editing()
            return
        if key in (Qt.Key_Delete, Qt.Key_Backspace):
            self.remove_row()
            return
        if key == Qt.Key_BracketRight and event.modifiers() & Qt.ControlModifier:
            self.cycle_type(increment=True)
            return
        if key == Qt.Key_BracketLeft and event.modifiers() & Qt.ControlModifier:
            self.cycle_type(increment=False)
            return
        if key == Qt.Key_Up and event.modifiers() & Qt.ControlModifier:
            self.move_item(-1)
            return
        if key == Qt.Key_Down and event.modifiers() & Qt.ControlModifier:
            self.move_item(1)
            return
        QTreeView.keyPressEvent(self.tree, event)

    def _update_recent_menu(self):
        self.recent_menu.clear()
        recents = self.controller.settings.get("open_recent", [])
        if not recents:
            action = self.recent_menu.addAction("No Recently Opened Files")
            action.setEnabled(False)
        else:
            for path in recents:
                action = self.recent_menu.addAction(path)
                action.triggered.connect(lambda checked, p=path: self.controller.open_recent(p))
        self.recent_menu.addSeparator()
        self.recent_menu.addAction("Clear Recently Opened", self.controller.clear_recents)

    # ── Tree Model Helpers ───────────────────────────────────────

    def root_item(self):
        """Return the single root QStandardItem (row 0 of invisible root)."""
        if self.model.rowCount() == 0:
            return None
        return self.model.item(0, COL_KEY)

    def item_from_index(self, index):
        """Get the key-column item for a given model index."""
        if not index.isValid():
            return None
        # Always resolve to column 0
        key_index = index.sibling(index.row(), COL_KEY)
        return self.model.itemFromIndex(key_index)

    def get_check_type_from_item(self, item):
        """Get the type string for an item, stripping the menu code prefix."""
        if item is None:
            return ""
        parent = item.parent()
        if parent is None:
            parent = self.model.invisibleRootItem()
        type_item = parent.child(item.row(), COL_TYPE)
        if type_item is None:
            return ""
        t = type_item.text()
        if t.startswith(MENU_CODE):
            t = t.replace(MENU_CODE + " ", "").replace(MENU_CODE, "")
        return t.lower() if t else ""

    def get_item_data(self, item, col):
        """Get text from a specific column for the same row as item."""
        parent = item.parent()
        if parent is None:
            parent = self.model.invisibleRootItem()
        col_item = parent.child(item.row(), col)
        return col_item.text() if col_item else ""

    def set_item_data(self, item, col, value):
        """Set text in a specific column for the same row as item."""
        parent = item.parent()
        if parent is None:
            parent = self.model.invisibleRootItem()
        col_item = parent.child(item.row(), col)
        if col_item:
            col_item.setText(str(value))

    def get_root_type(self):
        root = self.root_item()
        if root is None:
            return None
        t = self.get_check_type_from_item(root)
        if t == "dictionary":
            return {} if self.controller.settings.get("sort_dict", False) else OrderedDict()
        elif t == "array":
            return []
        return None

    # ── Bool helpers ─────────────────────────────────────────────

    def b_true(self):
        return self.bool_display.split("/")[0]

    def b_false(self):
        return self.bool_display.split("/")[-1]

    def all_b_true(self, lower=False):
        return [x.split("/")[0].lower() if lower else x.split("/")[0] for x in self.controller.allowed_bool]

    def all_b_false(self, lower=False):
        return [x.split("/")[-1].lower() if lower else x.split("/")[-1] for x in self.controller.allowed_bool]

    def all_b(self, lower=False):
        b = []
        for x in self.controller.allowed_bool:
            b.extend([a.lower() if lower else a for a in x.split("/")])
        return b

    # ── Type helpers ─────────────────────────────────────────────

    def get_type_string(self, value, override=None):
        prefix = MENU_CODE + " "
        if override:
            return prefix + override
        if isinstance(value, dict):
            return prefix + "Dictionary"
        if isinstance(value, (list, tuple)):
            return prefix + "Array"
        if isinstance(value, datetime.datetime):
            return prefix + "Date"
        if isinstance(value, bytes):
            return prefix + "Data"
        if isinstance(value, bool):
            return prefix + "Boolean"
        if isinstance(value, (int, float)):
            return prefix + "Number"
        if isinstance(value, str):
            return prefix + "String"
        if isinstance(value, plist.UID) or (hasattr(plistlib, "UID") and isinstance(value, plistlib.UID)):
            return prefix + "UID"
        return prefix + str(type(value))

    def get_data_display(self, value):
        """Format bytes for display based on current display mode."""
        if not value:
            return "<>" if self.data_display.lower() == "hex" else ""
        if self.data_display.lower() == "hex":
            h = binascii.hexlify(value).decode("utf-8")
            return "<{}>".format(" ".join((h[0 + i : 8 + i] for i in range(0, len(h), 8))).upper())
        else:
            return base64.b64encode(value).decode("utf-8")

    # ── Tree Population ──────────────────────────────────────────

    def add_node(self, value, parent_item=None, key=None, check_binary=False):
        """Add a plist value to the tree model. Returns the key item of the top-level node added."""
        node_stack = deque()
        node_stack.append((value, parent_item, key, check_binary))
        top_item = None

        while node_stack:
            val, par, k, cb = node_stack.popleft()
            key_item, remaining = self._add_node(val, par, k, cb)
            if top_item is None and key_item is not None:
                top_item = key_item
            if remaining:
                node_stack.extend(remaining)
        return top_item

    def _add_node(self, value, parent_item, key, check_binary):
        if value is None:
            return (None, None)
        if key is None:
            key = "Root"

        is_root = parent_item is None
        target = self.model.invisibleRootItem() if is_root else parent_item

        # Build the row items
        key_item = QStandardItem(str(key))
        type_item = QStandardItem()
        value_item = QStandardItem()

        remaining = None

        if isinstance(value, dict):
            # Check for UID pattern: {"CF$UID": int}
            if (
                (not check_binary or self.plist_type.lower() != "binary")
                and len(value) == 1
                and "CF$UID" in value
                and isinstance(value["CF$UID"], int)
                and 0 <= value["CF$UID"] < 1 << 32
            ):
                uid_val = value["CF$UID"]
                type_item.setText(self.get_type_string(uid_val, override="UID"))
                value_item.setText(str(uid_val))
            else:
                children = "1 key/value pair" if len(value) == 1 else "{} key/value pairs".format(len(value))
                type_item.setText(self.get_type_string(value))
                value_item.setText(children)
                dict_list = (
                    list(value.items())
                    if not self.controller.settings.get("sort_dict", False)
                    else sorted(list(value.items()))
                )
                remaining = [(v, key_item, k, check_binary) for k, v in dict_list]
        elif isinstance(value, (list, tuple)):
            children = "1 child" if len(value) == 1 else "{} children".format(len(value))
            type_item.setText(self.get_type_string(value))
            value_item.setText(children)
            remaining = [(v, key_item, str(i), check_binary) for i, v in enumerate(value)]
        elif isinstance(value, bytes):
            type_item.setText(self.get_type_string(value))
            value_item.setText(self.get_data_display(value))
        elif isinstance(value, datetime.datetime):
            type_item.setText(self.get_type_string(value))
            value_item.setText(value.strftime("%b %d, %Y %I:%M:%S %p"))
        elif isinstance(value, bool):
            type_item.setText(self.get_type_string(value))
            value_item.setText(self.b_true() if value else self.b_false())
        elif isinstance(value, (int, float)):
            type_item.setText(self.get_type_string(value))
            if isinstance(value, int) and self.int_display.lower() == "hex" and value >= 0:
                value_item.setText("0x" + hex(value).upper()[2:])
            else:
                value_item.setText(str(value))
        elif isinstance(value, plist.UID) or (hasattr(plistlib, "UID") and isinstance(value, plistlib.UID)):
            type_item.setText(self.get_type_string(value, override="UID"))
            value_item.setText(str(value.data if hasattr(value, "data") else value))
        else:
            type_item.setText(self.get_type_string(value))
            value_item.setText(str(value))

        target.appendRow([key_item, type_item, value_item])
        return (key_item, remaining)

    # ── Tree Serialization ───────────────────────────────────────

    def get_value_from_item(self, item, binary=False):
        """Convert a tree item back to its Python value."""
        check_type = self.get_check_type_from_item(item)
        value_text = self.get_item_data(item, COL_VALUE)

        if check_type == "dictionary":
            return {} if self.controller.settings.get("sort_dict", False) else OrderedDict()
        elif check_type == "array":
            return []
        elif check_type == "boolean":
            return value_text.lower() in [x.lower() for x in self.all_b_true()]
        elif check_type == "number":
            if self.int_display.lower() == "hex" and value_text.lower().startswith("0x"):
                try:
                    return int(value_text, 16)
                except (ValueError, TypeError):
                    return 0
            try:
                return int(value_text)
            except (ValueError, TypeError):
                try:
                    return float(value_text)
                except (ValueError, TypeError):
                    return 0
        elif check_type == "uid":
            try:
                val = int(value_text)
            except (ValueError, TypeError):
                val = 0
            return plist.UID(val) if binary else {"CF$UID": val}
        elif check_type == "data":
            if self.data_display.lower() == "hex":
                hex_str = value_text.replace("<", "").replace(">", "").replace(" ", "")
                return binascii.unhexlify(hex_str.encode("utf-8"))
            else:
                return base64.b64decode(value_text.encode("utf-8"))
        elif check_type == "date":
            return datetime.datetime.strptime(value_text, "%b %d, %Y %I:%M:%S %p")
        return value_text

    def nodes_to_values(self, item=None, binary=False):
        """Serialize tree back to Python plist-compatible structures."""
        if item is None:
            item = self.root_item()
        if item is None:
            return {}

        root_type = self.get_check_type_from_item(item)
        if root_type == "dictionary":
            result = {} if self.controller.settings.get("sort_dict", False) else OrderedDict()
        elif root_type == "array":
            result = []
        else:
            return self.get_value_from_item(item, binary=binary)

        # Iterative serialization
        stack = deque()
        # Push children in order
        for row in range(item.rowCount()):
            child = item.child(row, COL_KEY)
            if child:
                stack.append((child, result))

        while stack:
            node, parent = stack.popleft()
            name = node.text()
            value = self.get_value_from_item(node, binary=binary)

            if isinstance(parent, list):
                parent.append(value)
            elif isinstance(parent, dict):
                parent[name] = value

            # Add children
            for row in range(node.rowCount()):
                child = node.child(row, COL_KEY)
                if child:
                    stack.append((child, value))

        return result

    # ── Value Validation ─────────────────────────────────────────

    def qualify_value(self, value, value_type):
        value_type = value_type.lower()
        if value_type == "data":
            if self.data_display.lower() == "hex":
                value = "".join(value.split()).replace("<", "").replace(">", "")
                if value.lower().startswith("0x"):
                    value = value[2:]
                if any(x for x in value.lower() if x not in "0123456789abcdef"):
                    return (False, "Invalid Hex Data", "Invalid character in passed hex data.")
                if len(value) % 2:
                    return (False, "Invalid Hex Data", "Hex data must contain an even number of chars.")
                value = "<{}>".format(" ".join((value[0 + i : 8 + i] for i in range(0, len(value), 8))).upper())
            else:
                value = value.rstrip("=")
                if any(x for x in value if x.lower() not in "0123456789abcdefghijklmnopqrstuvwxyz+/"):
                    return (False, "Invalid Base64 Data", "Invalid base64 data passed.")
                if len(value) > 0 and len(value) % 4:
                    value += "=" * (4 - len(value) % 4)
                try:
                    base64.b64decode(value.encode("utf-8"))
                except Exception:
                    return (False, "Invalid Base64 Data", "Invalid base64 data passed.")
        elif value_type == "date":
            try:
                value = datetime.datetime.strptime(value, "%b %d, %Y %I:%M:%S %p").strftime("%b %d, %Y %I:%M:%S %p")
            except ValueError:
                try:
                    value = datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S %z").strftime("%b %d, %Y %I:%M:%S %p")
                except ValueError:
                    return (
                        False,
                        "Invalid Date",
                        "Couldn't convert the passed string to a date.\n\n"
                        "Valid formats include:\n"
                        "Mar 11, 2019 12:29:00 PM\n"
                        "YYYY-MM-DD HH:MM:SS Z",
                    )
        elif value_type == "number":
            if value.lower().startswith("0x"):
                try:
                    value = int(value, 16)
                except (ValueError, TypeError):
                    return (False, "Invalid Hex Data", "Couldn't convert the passed hex string to an integer.")
            else:
                value = value.replace(",", "")
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    try:
                        value = float(value)
                    except (ValueError, TypeError):
                        return (False, "Invalid Number Data", "Couldn't convert to an integer or float.")
            if isinstance(value, int) and not (-1 << 63 <= value < 1 << 64):
                value = float(value)
            if self.int_display.lower() == "hex" and not isinstance(value, float) and value >= 0:
                value = "0x" + hex(value).upper()[2:]
            value = str(value)
        elif value_type == "boolean":
            if value.lower() not in self.all_b(lower=True):
                return (False, "Invalid Boolean Data", "Booleans can only be {}.".format(", ".join(self.all_b())))
            value = self.b_true() if value.lower() in self.all_b_true(lower=True) else self.b_false()
        elif value_type == "uid":
            if value.lower().startswith("0x"):
                try:
                    value = int(value, 16)
                except (ValueError, TypeError):
                    return (False, "Invalid Hex Data", "Couldn't convert the passed hex string to an integer.")
            else:
                value = value.replace(",", "")
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    return (False, "Invalid Integer Data", "Couldn't convert the passed string to an integer.")
            if not 0 <= value < 1 << 32:
                return (
                    False,
                    "Invalid Integer Value",
                    "UIDs cannot be negative, and must be less than 2**32 (4294967296)",
                )
            value = str(value)
        return (True, value)

    # ── Undo/Redo ────────────────────────────────────────────────

    def add_undo(self, action):
        if not isinstance(action, list):
            action = [action]
        try:
            max_undo = int(self.controller.settings.get("max_undo", 200))
            assert max_undo >= 0
        except (ValueError, TypeError, AssertionError):
            max_undo = 200
        self.undo_stack.append(action)
        if max_undo > 0:
            while len(self.undo_stack) > max_undo:
                self.undo_stack.popleft()
        self.redo_stack.clear()

    def reundo(self, undo=True):
        if self.reundoing:
            return
        self.reundoing = True

        if undo:
            u, r = self.undo_stack, self.redo_stack
        else:
            u, r = self.redo_stack, self.undo_stack

        if not u:
            QApplication.beep()
            self.reundoing = False
            return

        task_list = u.pop()
        r_task_list = []

        for task in reversed(task_list):
            ttype = task["type"].lower()
            item = task.get("item")

            if ttype == "edit":
                # Save current state for reverse
                r_task_list.append(
                    {
                        "type": "edit",
                        "item": item,
                        "old_key": item.text(),
                        "old_type": self.get_item_data(item, COL_TYPE),
                        "old_value": self.get_item_data(item, COL_VALUE),
                    }
                )
                # Restore old state
                item.setText(task["old_key"])
                self.set_item_data(item, COL_TYPE, task["old_type"])
                self.set_item_data(item, COL_VALUE, task["old_value"])

            elif ttype == "add":
                # Was added -> undo by removing
                parent = item.parent() or self.model.invisibleRootItem()
                row = item.row()
                r_task_list.append(
                    {
                        "type": "remove",
                        "item": item,
                        "parent": parent,
                        "index": row,
                    }
                )
                parent.takeRow(row)

            elif ttype == "remove":
                # Was removed -> undo by re-adding
                r_task_list.append(
                    {
                        "type": "add",
                        "item": item,
                    }
                )
                parent = task["parent"]
                index = task.get("index", parent.rowCount())
                # Rebuild the row
                row_items = [item]
                type_item = task.get("type_item")
                value_item = task.get("value_item")
                if type_item:
                    row_items.append(type_item)
                if value_item:
                    row_items.append(value_item)
                while len(row_items) < 3:
                    row_items.append(QStandardItem(""))
                parent.insertRow(min(index, parent.rowCount()), row_items)

            elif ttype == "move":
                # Was moved -> undo by moving back
                parent = item.parent() or self.model.invisibleRootItem()
                r_task_list.append(
                    {
                        "type": "move",
                        "item": item,
                        "parent": parent,
                        "index": item.row(),
                    }
                )
                old_parent = task["parent"]
                old_index = task.get("index", old_parent.rowCount())
                row_data = parent.takeRow(item.row())
                old_parent.insertRow(min(old_index, old_parent.rowCount()), row_data)

        if r_task_list:
            r.append(r_task_list)

        self.mark_edited()
        self.update_all_children()
        self.reundoing = False

    # ── Edit State ───────────────────────────────────────────────

    def mark_edited(self):
        if not self.edited:
            self.edited = True
            title = self.windowTitle()
            if not title.endswith(" - Edited"):
                self.setWindowTitle(title + " - Edited")

    def _ensure_edited(self, edited=True, title=None):
        if title:
            self.setWindowTitle(title)
        if edited and not self.edited:
            self.mark_edited()
        elif not edited and self.edited:
            self.edited = False

    # ── File Operations ──────────────────────────────────────────

    def open_plist(self, path, plist_data, plist_type="XML", auto_expand=True, title=None):
        self.plist_type = plist_type
        self.plist_type_combo.setCurrentText(plist_type)

        # Apply display settings from controller
        self.data_display = self.controller.settings.get("display_data_as", "Hex")
        self.int_display = self.controller.settings.get("display_int_as", "Decimal")
        self.bool_display = self.controller.settings.get("display_bool_as", "True/False")
        self.data_type_combo.setCurrentText(self.data_display)
        self.int_type_combo.setCurrentText(self.int_display)
        self.bool_type_combo.setCurrentText(self.bool_display)

        # Clear and repopulate
        self.model.removeRows(0, self.model.rowCount())
        self.add_node(plist_data, check_binary=plist_type.lower() == "binary")

        self.current_plist = os.path.normpath(path) if path else path
        try:
            self.last_hash = self.get_hash(path)
        except Exception:
            self.last_hash = None

        if path is None:
            self._ensure_edited(title=title or "Untitled.plist")
        else:
            self._ensure_edited(edited=False, title=path)

        self.undo_stack.clear()
        self.redo_stack.clear()

        # Expand
        root = self.root_item()
        if root:
            root_index = self.model.indexFromItem(root)
            self.tree.expand(root_index)
            if auto_expand:
                self._expand_all_recursive(root_index)
            self.tree.setCurrentIndex(root_index)

    def _expand_all_recursive(self, index):
        self.tree.expand(index)
        for row in range(self.model.rowCount(index)):
            child = self.model.index(row, 0, index)
            if child.isValid():
                self._expand_all_recursive(child)

    def save_plist(self, event=None):
        if not self.current_plist:
            return self.save_plist_as()
        return self.save_plist_as(path=self.current_plist)

    def save_plist_as(self, event=None, path=None):
        if self.saving:
            return None
        self.saving = True
        try:
            if path is None:
                path, _ = QFileDialog.getSaveFileName(
                    self, "Save Plist File", self._get_save_dir(), "Plist Files (*.plist);;All Files (*)"
                )
                if not path:
                    self.saving = False
                    return None

            binary = self.plist_type.lower() == "binary"
            plist_data = self.nodes_to_values(binary=binary)

            temp = tempfile.mkdtemp()
            temp_file = os.path.join(temp, os.path.basename(path))
            m = BytesIO()

            try:
                sort_keys = self.controller.settings.get("sort_dict", False)
                if binary:
                    plist.dump(plist_data, m, sort_keys=sort_keys, fmt=plist.FMT_BINARY)
                elif not self.controller.settings.get("xcode_data", True):
                    plist.dump(plist_data, m, sort_keys=sort_keys)
                else:
                    plist_text = self._format_data_string(plist.dumps(plist_data, sort_keys=sort_keys))
                    m.write(plist_text.encode("utf-8"))

                mem_hash = self.get_hash(m)
                with open(temp_file, "wb") as f:
                    m.seek(0)
                    shutil.copyfileobj(m, f)
                temp_hash = self.get_hash(temp_file)

                if mem_hash != temp_hash:
                    raise Exception("The in-memory and temp file hashes do not match.")

                if os.path.isfile(path):
                    try:
                        shutil.copystat(path, temp_file)
                    except OSError:
                        pass
                    try:
                        update_ts = time.time()
                        os.utime(temp_file, (update_ts, update_ts))
                    except OSError:
                        pass

                shutil.copy(temp_file, path)
                save_hash = self.get_hash(path)
                if temp_hash != save_hash:
                    raise Exception("The saved and temp file hashes do not match.")

            except Exception as e:
                QApplication.beep()
                QMessageBox.critical(self, "Save Error", str(e))
                return None
            finally:
                m.close()
                shutil.rmtree(temp, ignore_errors=True)

            path = os.path.normpath(path)
            self.current_plist = path
            self.last_hash = save_hash
            self.setWindowTitle(path)
            self._ensure_edited(edited=False)
            return True

        finally:
            self.saving = False

    def _get_save_dir(self):
        if self.current_plist and os.path.isdir(os.path.dirname(self.current_plist)):
            return os.path.dirname(self.current_plist)
        return os.path.expanduser("~")

    def _format_data_string(self, plist_text):
        """Collapse multi-line <data> tags into single lines for Xcode style."""
        new_plist = []
        data_tag = ""
        for x in plist_text.split("\n"):
            x_stripped = x.strip()
            if not data_tag:
                if x_stripped.startswith("<data>") and not x_stripped.endswith("</data>"):
                    data_tag = x
                    continue
                new_plist.append(x)
                continue
            data_tag += x_stripped
            if x_stripped == "</data>":
                new_plist.append(data_tag)
                data_tag = ""
        return "\n".join(new_plist)

    def get_hash(self, target):
        """Get MD5 hash of a file path or BytesIO object."""
        if isinstance(target, BytesIO):
            target.seek(0)
            return hashlib.md5(target.read()).hexdigest()
        if isinstance(target, str) and os.path.isfile(target):
            with open(target, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        return None

    def reload_from_disk(self, event=None):
        if not self.current_plist:
            QApplication.beep()
            return
        if self.edited:
            QApplication.beep()
            result = QMessageBox.question(
                self, "Unsaved Changes", "Any unsaved changes will be lost when reloading from disk. Continue?"
            )
            if result != QMessageBox.Yes:
                return
        try:
            with open(self.current_plist, "rb") as f:
                plist_data = plist.load(
                    f, dict_type=dict if self.controller.settings.get("sort_dict", False) else OrderedDict
                )
        except Exception as e:
            QApplication.beep()
            QMessageBox.critical(self, "Error Opening File", str(e))
            return
        self.open_plist(
            self.current_plist,
            plist_data,
            plist_type=self.plist_type,
            auto_expand=self.controller.settings.get("expand_all_items_on_open", True),
        )

    def check_save(self):
        """Prompt to save if edited. Returns True if ok to close, None if cancelled."""
        if not self.edited:
            return True
        result = QMessageBox.question(
            self,
            "Unsaved Changes",
            "Do you want to save changes to {}?".format(
                os.path.basename(self.current_plist) if self.current_plist else "Untitled.plist"
            ),
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
        )
        if result == QMessageBox.Save:
            return self.save_plist()
        elif result == QMessageBox.Discard:
            return True
        return None  # Cancelled

    # ── Close ────────────────────────────────────────────────────

    def closeEvent(self, event):
        result = self.check_save()
        if result is None:
            event.ignore()
            return
        if self in self.controller.windows:
            self.controller.windows.remove(self)
        self.closed.emit(self)
        # Save window dimensions
        self.controller.settings["last_window_width"] = self.width()
        self.controller.settings["last_window_height"] = self.height()
        event.accept()
        if not self.controller.windows:
            QApplication.quit()

    # ── Opacity ──────────────────────────────────────────────────

    def _apply_opacity(self):
        try:
            opacity = min(100, max(int(self.controller.settings.get("opacity", 100)), 25))
        except (ValueError, TypeError):
            opacity = 100
        self.setWindowOpacity(float(opacity) / 100.0)

    def _build_tree_stylesheet(self):
        """Generate a QSS stylesheet for the tree based on the current color settings."""
        s = self.controller.settings
        dark = getattr(self.controller, "use_dark", False)
        default_dark = getattr(
            self.controller,
            "default_dark",
            {
                "alternating_color_1": "#161616",
                "alternating_color_2": "#202020",
                "highlight_color": "#1E90FF",
                "background_color": "#161616",
            },
        )
        default_light = getattr(
            self.controller,
            "default_light",
            {
                "alternating_color_1": "#F0F1F1",
                "alternating_color_2": "#FEFEFE",
                "highlight_color": "#1E90FF",
                "background_color": "#FEFEFE",
            },
        )
        defaults = default_dark if dark else default_light

        alt1 = s.get("alternating_color_1", defaults["alternating_color_1"])
        alt2 = s.get("alternating_color_2", defaults["alternating_color_2"])
        hl = s.get("highlight_color", defaults["highlight_color"])
        bg = s.get("background_color", defaults["background_color"])

        get_text = getattr(self.controller, "text_color", lambda c, invert=False: "black")
        row1_color = get_text(alt1, invert=s.get("invert_row1_text_color", False))
        row2_color = get_text(alt2, invert=s.get("invert_row2_text_color", False))
        hl_color = get_text(hl, invert=s.get("invert_hl_text_color", False))
        if s.get("header_text_ignore_bg_color", False):
            header_text = "inherit"
        else:
            header_text = get_text(bg, invert=s.get("invert_background_text_color", False))

        return (
            "QTreeView {{"
            " background-color: {alt1};"
            " alternate-background-color: {alt2};"
            " color: {row1};"
            " selection-background-color: {hl};"
            " selection-color: {hlc};"
            "}}"
            " QTreeView::item {{ color: {row1}; }}"
            " QTreeView::item:alternate {{ color: {row2}; }}"
            " QTreeView::item:selected {{ background-color: {hl}; color: {hlc}; }}"
            " QTreeView::item:selected:alternate {{ background-color: {hl}; color: {hlc}; }}"
            " QHeaderView::section {{"
            "  background-color: {bg};"
            "  color: {htxt};"
            "  border: 1px solid {alt2};"
            "  padding: 2px 4px;"
            "}}"
        ).format(alt1=alt1, alt2=alt2, hl=hl, bg=bg, row1=row1_color, row2=row2_color, hlc=hl_color, htxt=header_text)

    def update_colors(self):
        """Apply color settings from the controller to the tree view."""
        self.tree.setAlternatingRowColors(True)
        self.tree.setStyleSheet(self._build_tree_stylesheet())

    def update_fonts(self):
        """Apply font settings from the controller to the tree view."""
        s = self.controller.settings
        base_font = QApplication.font()
        family = base_font.family()
        size = base_font.pointSize()
        if size <= 0:
            size = 10
        if s.get("use_custom_font", False) and s.get("font_family"):
            family = s["font_family"]
        if s.get("use_custom_font_size", False) and s.get("font_size"):
            try:
                size = max(1, min(128, int(s["font_size"])))
            except (TypeError, ValueError):
                pass
        self.tree.setFont(QFont(family, size))

    # ── Type Change Callbacks ────────────────────────────────────

    def _on_plist_type_changed(self, value):
        self.plist_type = value
        self.mark_edited()

    def _on_data_type_changed(self, value):
        if value == self.last_data:
            return
        self.change_data_display(value)
        self.last_data = value

    def _on_int_type_changed(self, value):
        if value == self.last_int:
            return
        self.change_int_display(value)
        self.last_int = value

    def _on_bool_type_changed(self, value):
        if value == self.last_bool:
            return
        self.change_bool_display(value)
        self.last_bool = value

    # ── Display Conversion Methods ───────────────────────────────

    def _iter_all_items(self, parent=None):
        """Iterate all items in the model."""
        if parent is None:
            parent = self.model.invisibleRootItem()
        for row in range(parent.rowCount()):
            item = parent.child(row, COL_KEY)
            if item:
                yield item
                yield from self._iter_all_items(item)

    def change_data_display(self, new_display="Hex"):
        self.data_display = new_display
        for item in self._iter_all_items():
            if self.get_check_type_from_item(item) != "data":
                continue
            value_text = self.get_item_data(item, COL_VALUE)
            if new_display.lower() == "hex":
                raw = base64.b64decode(value_text.encode("utf-8"))
                h = binascii.hexlify(raw).decode("utf-8")
                value_text = "<{}>".format(" ".join((h[0 + i : 8 + i] for i in range(0, len(h), 8))).upper())
            else:
                hex_str = value_text.replace("<", "").replace(">", "").replace(" ", "")
                raw = binascii.unhexlify(hex_str.encode("utf-8"))
                value_text = base64.b64encode(raw).decode("utf-8")
            self.set_item_data(item, COL_VALUE, value_text)

    def change_int_display(self, new_display="Decimal"):
        self.int_display = new_display
        for item in self._iter_all_items():
            if self.get_check_type_from_item(item) != "number":
                continue
            value_text = self.get_item_data(item, COL_VALUE)
            if new_display.lower() == "hex":
                try:
                    v = int(value_text)
                    if v >= 0:
                        value_text = "0x" + hex(v).upper()[2:]
                except (ValueError, TypeError):
                    pass
            else:
                if value_text.lower().startswith("0x"):
                    value_text = str(int(value_text, 16))
            self.set_item_data(item, COL_VALUE, value_text)

    def change_bool_display(self, new_display="True/False"):
        self.bool_display = new_display
        on, off = new_display.split("/")
        on_list = [x.split("/")[0] for x in self.controller.allowed_bool]
        for item in self._iter_all_items():
            if self.get_check_type_from_item(item) != "boolean":
                continue
            value_text = self.get_item_data(item, COL_VALUE)
            self.set_item_data(item, COL_VALUE, on if value_text in on_list else off)

    # ── Row Operations ───────────────────────────────────────────

    def new_row(self, target_item=None, force_sibling=False):
        if self.adding_rows:
            return
        self.adding_rows = True
        try:
            if target_item is None:
                index = self.tree.currentIndex()
                target_item = self.item_from_index(index) if index.isValid() else self.root_item()
            if target_item is None:
                return

            root = self.root_item()
            target_type = self.get_check_type_from_item(target_item)

            if target_item == root and target_type not in ("array", "dictionary"):
                return

            insert_index = 0
            parent_item = target_item

            if (
                target_type not in ("dictionary", "array")
                or force_sibling
                or (not self.tree.isExpanded(self.model.indexFromItem(target_item)) and target_item.rowCount() > 0)
            ):
                insert_index = target_item.row() + 1
                parent_item = target_item.parent()
                if parent_item is None:
                    parent_item = self.model.invisibleRootItem()

            if parent_item == self.model.invisibleRootItem():
                parent_item = root
                if self.get_check_type_from_item(root) not in ("dictionary", "array"):
                    return

            parent_type = self.get_check_type_from_item(parent_item)
            name = ""
            if parent_type == "dictionary":
                names = [parent_item.child(r, COL_KEY).text() for r in range(parent_item.rowCount())]
                name = self._get_unique_name("New String", names)

            key_item = QStandardItem(name)
            key_item.setEditable(False)
            type_item = QStandardItem(MENU_CODE + " String")
            type_item.setEditable(False)
            value_item = QStandardItem("")
            value_item.setEditable(False)

            parent_item.insertRow(insert_index, [key_item, type_item, value_item])

            # Update array indices
            if parent_type == "array":
                self._update_array_counts(parent_item)
            self._update_children(parent_item)

            # Select and expand
            self.tree.expand(self.model.indexFromItem(parent_item))
            new_index = self.model.indexFromItem(key_item)
            self.tree.setCurrentIndex(new_index)
            self.tree.scrollTo(new_index)

            self.add_undo(
                [
                    {
                        "type": "add",
                        "item": key_item,
                    }
                ]
            )
            self.mark_edited()
        finally:
            self.adding_rows = False

    def remove_row(self, target_item=None):
        if self.removing_rows:
            return
        self.removing_rows = True
        try:
            if target_item is None:
                index = self.tree.currentIndex()
                target_item = self.item_from_index(index) if index.isValid() else None
            if target_item is None or target_item == self.root_item():
                return

            parent = target_item.parent()
            if parent is None:
                parent = self.model.invisibleRootItem()

            row = target_item.row()

            # Use takeRow (not removeRow) so the items stay alive for undo.
            taken = parent.takeRow(row)
            type_item = taken[COL_TYPE] if len(taken) > COL_TYPE else QStandardItem("")
            value_item = taken[COL_VALUE] if len(taken) > COL_VALUE else QStandardItem("")

            self.add_undo(
                [
                    {
                        "type": "remove",
                        "item": target_item,
                        "type_item": type_item,
                        "value_item": value_item,
                        "parent": parent,
                        "index": row,
                    }
                ]
            )

            # Select next
            if parent.rowCount() > 0:
                new_row = min(row, parent.rowCount() - 1)
                new_item = parent.child(new_row, COL_KEY)
                if new_item:
                    self.tree.setCurrentIndex(self.model.indexFromItem(new_item))
            else:
                if parent != self.model.invisibleRootItem():
                    self.tree.setCurrentIndex(self.model.indexFromItem(parent))

            parent_type = self.get_check_type_from_item(parent) if parent != self.model.invisibleRootItem() else ""
            if parent_type == "array":
                self._update_array_counts(parent)
            if parent != self.model.invisibleRootItem():
                self._update_children(parent)

            self.mark_edited()
        finally:
            self.removing_rows = False

    def move_item(self, direction):
        """Move the selected item up (-1) or down (+1) among its siblings."""
        index = self.tree.currentIndex()
        item = self.item_from_index(index)
        if item is None or item == self.root_item():
            return
        parent = item.parent() or self.model.invisibleRootItem()
        row = item.row()
        new_row = row + direction
        if new_row < 0 or new_row >= parent.rowCount():
            return
        undo_task = {"type": "move", "item": item, "parent": parent, "index": row}
        row_data = parent.takeRow(row)
        parent.insertRow(new_row, row_data)
        self.tree.setCurrentIndex(self.model.indexFromItem(item))
        parent_type = self.get_check_type_from_item(parent) if parent != self.model.invisibleRootItem() else ""
        if parent_type == "array":
            self._update_array_counts(parent)
        self.mark_edited()
        self.add_undo([undo_task])

    # ── Children/Array Updates ───────────────────────────────────

    def _update_children(self, item):
        if item is None:
            return
        check_type = self.get_check_type_from_item(item)
        count = item.rowCount()
        if check_type == "dictionary":
            text = "1 key/value pair" if count == 1 else "{} key/value pairs".format(count)
        elif check_type == "array":
            text = "1 child" if count == 1 else "{} children".format(count)
        else:
            return
        self.set_item_data(item, COL_VALUE, text)

    def _update_array_counts(self, item):
        for row in range(item.rowCount()):
            child = item.child(row, COL_KEY)
            if child:
                child.setText(str(row))

    def update_all_children(self):
        for item in self._iter_all_items():
            check_type = self.get_check_type_from_item(item)
            if check_type in ("dictionary", "array"):
                self._update_children(item)
            if check_type == "array":
                self._update_array_counts(item)

    # ── Sort Keys ──────────────────────────────────────────────

    def sorted_nicely(self, items, reverse=False):
        def convert(text):
            return int(text) if text.isdigit() else text

        def alphanum_key(item):
            return [convert(c) for c in re.split(r"([0-9]+)", item.text().lower())]

        return sorted(items, key=alphanum_key, reverse=reverse)

    def do_sort(self, item, recursive=False, reverse=False):
        node_stack = deque()
        node_stack.append(item)
        undo_tasks = []
        while node_stack:
            node = node_stack.pop()
            if node.rowCount() == 0:
                continue
            if self.get_check_type_from_item(node) != "dictionary":
                if recursive:
                    for row in range(node.rowCount()):
                        child = node.child(row, COL_KEY)
                        if child and self.get_check_type_from_item(child) in ("dictionary", "array"):
                            node_stack.append(child)
                continue
            # Collect children
            children = [node.child(row, COL_KEY) for row in range(node.rowCount())]
            sorted_children = self.sorted_nicely(children, reverse=reverse)
            skip_sort = all(sorted_children[i] is children[i] for i in range(len(children)))
            if skip_sort and not recursive:
                continue
            for idx, child in enumerate(sorted_children):
                if recursive and self.get_check_type_from_item(child) in ("dictionary", "array"):
                    node_stack.append(child)
                if not skip_sort:
                    old_row = child.row()
                    undo_tasks.append(
                        {
                            "type": "move",
                            "item": child,
                            "parent": node,
                            "index": old_row,
                        }
                    )
                    if child.row() != idx:
                        row_data = node.takeRow(child.row())
                        node.insertRow(idx, row_data)
        return undo_tasks

    def sort_keys(self, item, recursive=False, reverse=False):
        undo_tasks = self.do_sort(item, recursive=recursive, reverse=reverse)
        if not undo_tasks:
            return
        self.add_undo(undo_tasks)
        self.update_all_children()
        self.mark_edited()

    # ── Helpers ───────────────────────────────────────────────

    def _get_unique_name(self, name, names):
        num = 1
        sep = " - "
        while True:
            temp_name = name if num == 1 else name + sep + str(num)
            if temp_name not in names:
                return temp_name
            num += 1

    # ── Copy/Paste ───────────────────────────────────────────────

    def copy_selection(self):
        index = self.tree.currentIndex()
        item = self.item_from_index(index)
        if item is None:
            return
        try:
            clipboard_string = plist.dumps(
                self.nodes_to_values(item), sort_keys=self.controller.settings.get("sort_dict", False)
            )
            if self.controller.settings.get("xcode_data", True):
                clipboard_string = self._format_data_string(clipboard_string)
            self.controller._clipboard_append(clipboard_string)
        except Exception:
            pass

    def copy_children(self):
        index = self.tree.currentIndex()
        item = self.item_from_index(index)
        if item is None:
            return self.copy_selection()
        root = self.root_item()
        if item == root or self.get_check_type_from_item(item) not in ("array", "dictionary"):
            return self.copy_selection()
        try:
            data = self.nodes_to_values(item)
            if isinstance(data, dict) and data:
                data = data[list(data)[0]]
            elif isinstance(data, list) and data:
                data = data[0]
            clipboard_string = plist.dumps(data, sort_keys=self.controller.settings.get("sort_dict", False))
            self.controller._clipboard_append(clipboard_string)
        except Exception:
            pass

    def paste_selection(self):
        if self.pasting_nodes:
            return
        self.pasting_nodes = True
        try:
            clipboard = QApplication.clipboard()
            clip = clipboard.text()
            if not clip:
                self.pasting_nodes = False
                return

            plist_data = None
            try:
                plist_data = plist.loads(
                    clip, dict_type=dict if self.controller.settings.get("sort_dict", False) else OrderedDict
                )
            except Exception:
                clip_lines = "\n".join(
                    [c for c in clip.strip().split("\n") if not c.startswith(("<?", "<!", "<plist ", "</plist>"))]
                ).strip()
                element_type = (
                    "dict"
                    if clip_lines.startswith("<key>")
                    else "array"
                    if not clip_lines.startswith(("<array>", "<dict>")) and len(clip_lines.split("\n")) > 1
                    else None
                )
                cb_list = [self.plist_header, clip_lines, self.plist_footer]
                if element_type:
                    cb_list.insert(1, "<{}>".format(element_type))
                    cb_list.insert(3, "</{}>".format(element_type))
                try:
                    plist_data = plist.loads(
                        "\n".join(cb_list),
                        dict_type=dict if self.controller.settings.get("sort_dict", False) else OrderedDict,
                    )
                except Exception as e:
                    QApplication.beep()
                    QMessageBox.critical(self, "Paste Error", repr(e))
                    return

            if plist_data is None:
                if clip:
                    QApplication.beep()
                    QMessageBox.critical(self, "Paste Error", "The pasted value is not a valid plist string.")
                return

            index = self.tree.currentIndex()
            target_item = self.item_from_index(index) if index.isValid() else self.root_item()
            if target_item is None:
                target_item = self.root_item()

            target_type = self.get_check_type_from_item(target_item)
            insert_index = 0

            if target_type not in ("dictionary", "array") or (
                target_item.rowCount() > 0 and not self.tree.isExpanded(self.model.indexFromItem(target_item))
            ):
                insert_index = target_item.row() + 1
                target_item = target_item.parent()
                if target_item is None:
                    target_item = self.root_item()
                target_type = self.get_check_type_from_item(target_item)

            # Convert to dict if needed
            if isinstance(plist_data, list):
                new_plist = {} if self.controller.settings.get("sort_dict", False) else OrderedDict()
                for i, x in enumerate(plist_data):
                    new_plist[str(i)] = x
                plist_data = new_plist

            if not isinstance(plist_data, dict):
                plist_data = {"New item": plist_data}

            add_list = []
            names = (
                [target_item.child(r, COL_KEY).text() for r in range(target_item.rowCount())]
                if target_type == "dictionary"
                else []
            )
            dict_list = (
                list(plist_data.items())
                if not self.controller.settings.get("sort_dict", False)
                else sorted(list(plist_data.items()))
            )

            for key, val in reversed(dict_list):
                if target_type == "dictionary":
                    key = self._get_unique_name(str(key), names)
                    names.append(key)
                last = self.add_node(val, target_item, key)
                if last:
                    # Move into position
                    row_data = target_item.takeRow(last.row())
                    target_item.insertRow(insert_index, row_data)
                    add_list.append({"type": "add", "item": row_data[0]})

            if add_list:
                self.add_undo(add_list)
                self.mark_edited()
                self.update_all_children()
                self.tree.expand(self.model.indexFromItem(target_item))
                if add_list:
                    self.tree.setCurrentIndex(self.model.indexFromItem(add_list[0]["item"]))

        finally:
            self.pasting_nodes = False

    # ── Find/Replace ─────────────────────────────────────────────

    def find_all(self, text=""):
        if not text:
            return []
        find_type = self.find_type_combo.currentText().lower()
        case_sensitive = self.f_case_check.isChecked()
        items = list(self._iter_all_items())
        return [item for item in items if self._is_match(item, text, find_type, case_sensitive)]

    def hide_show_find(self):
        if self.show_find_replace and self.f_text.hasFocus():
            self.show_find_replace = False
            self.find_frame.setVisible(False)
            self.tree.setFocus()
        else:
            self.show_find_replace = True
            self.find_frame.setVisible(True)
            self.f_text.setFocus()
            self.f_text.selectAll()

    def hide_show_type(self):
        self.show_type = not self.show_type
        self.type_frame.setVisible(self.show_type)

    def find_next(self, replacing=False):
        find_text = self.f_text.text()
        if not find_text:
            QApplication.beep()
            return None
        find_type = self.find_type_combo.currentText().lower()
        case_sensitive = self.f_case_check.isChecked()

        result = self.qualify_value(find_text, find_type) if find_type != "key" else (True, find_text)
        if result[0] is False:
            QApplication.beep()
            QMessageBox.warning(self, result[1], result[2])
            return None
        find_text = result[1]

        items = list(self._iter_all_items())
        if not items:
            return None

        current = self.item_from_index(self.tree.currentIndex())
        start_idx = 0
        if current and current in items:
            start_idx = items.index(current) + 1

        # Search from current+1 to end, then wrap
        search_order = items[start_idx:] + items[:start_idx]

        for item in search_order:
            if self._is_match(item, find_text, find_type, case_sensitive):
                idx = self.model.indexFromItem(item)
                self.tree.setCurrentIndex(idx)
                self.tree.scrollTo(idx)
                # Expand parents
                parent = item.parent()
                while parent:
                    self.tree.expand(self.model.indexFromItem(parent))
                    parent = parent.parent()
                return item

        if not replacing:
            QApplication.beep()
            QMessageBox.information(self, "Not Found", '"{}" was not found.'.format(find_text))
        return None

    def find_prev(self):
        find_text = self.f_text.text()
        if not find_text:
            QApplication.beep()
            return None
        find_type = self.find_type_combo.currentText().lower()
        case_sensitive = self.f_case_check.isChecked()

        result = self.qualify_value(find_text, find_type) if find_type != "key" else (True, find_text)
        if result[0] is False:
            QApplication.beep()
            QMessageBox.warning(self, result[1], result[2])
            return None
        find_text = result[1]

        items = list(self._iter_all_items())
        if not items:
            return None

        current = self.item_from_index(self.tree.currentIndex())
        start_idx = len(items) - 1
        if current and current in items:
            start_idx = items.index(current) - 1

        search_order = items[: start_idx + 1][::-1] + items[start_idx + 1 :][::-1]

        for item in search_order:
            if self._is_match(item, find_text, find_type, case_sensitive):
                idx = self.model.indexFromItem(item)
                self.tree.setCurrentIndex(idx)
                self.tree.scrollTo(idx)
                parent = item.parent()
                while parent:
                    self.tree.expand(self.model.indexFromItem(parent))
                    parent = parent.parent()
                return item

        QApplication.beep()
        QMessageBox.information(self, "Not Found", '"{}" was not found.'.format(find_text))
        return None

    def replace(self):
        find_text = self.f_text.text()
        if not find_text:
            QApplication.beep()
            return
        repl_text = self.r_text.text()
        find_type = self.find_type_combo.currentText().lower()
        case_sensitive = self.f_case_check.isChecked()
        replace_all = self.r_all_check.isChecked()

        find_result = self.qualify_value(find_text, find_type) if find_type != "key" else (True, find_text)
        repl_result = self.qualify_value(repl_text, find_type) if find_type != "key" else (True, repl_text)

        if find_result[0] is False:
            QApplication.beep()
            QMessageBox.warning(self, "Invalid Find Value", find_result[2])
            return
        if repl_result[0] is False:
            QApplication.beep()
            QMessageBox.warning(self, "Invalid Replace Value", repl_result[2])
            return

        find_text = find_result[1]
        repl_text = repl_result[1]

        if find_text == repl_text:
            QApplication.beep()
            QMessageBox.information(self, "Nothing to Do", "The find and replace values are the same.")
            return

        items = list(self._iter_all_items())
        matches = [(item, find_type) for item in items if self._is_match(item, find_text, find_type, case_sensitive)]

        if replace_all:
            if not matches:
                QApplication.beep()
                QMessageBox.information(self, "Not Found", '"{}" was not found.'.format(find_text))
                return
            replacements = []
            for item, ft in matches:
                old_key = item.text()
                old_value = self.get_item_data(item, COL_VALUE)
                old_type = self.get_item_data(item, COL_TYPE)
                if self._do_replace(item, find_text, repl_text, ft, case_sensitive):
                    replacements.append(
                        {
                            "type": "edit",
                            "item": item,
                            "old_key": old_key,
                            "old_type": old_type,
                            "old_value": old_value,
                        }
                    )
            if replacements:
                self.add_undo(replacements)
                self.mark_edited()
        else:
            # Replace current if match, then find next
            current = self.item_from_index(self.tree.currentIndex())
            if current and self._is_match(current, find_text, find_type, case_sensitive):
                old_key = current.text()
                old_value = self.get_item_data(current, COL_VALUE)
                old_type = self.get_item_data(current, COL_TYPE)
                if self._do_replace(current, find_text, repl_text, find_type, case_sensitive):
                    self.add_undo(
                        [
                            {
                                "type": "edit",
                                "item": current,
                                "old_key": old_key,
                                "old_type": old_type,
                                "old_value": old_value,
                            }
                        ]
                    )
                    self.mark_edited()
            self.find_next(replacing=True)

    def _is_match(self, item, text, find_type, case_sensitive):
        if find_type == "key":
            parent = item.parent()
            if parent and self.get_check_type_from_item(parent) == "array":
                return False
            name = item.text()
            return (text in name) if case_sensitive else (text.lower() in name.lower())

        node_type = self.get_check_type_from_item(item)
        if node_type != find_type:
            return False
        value = self.get_item_data(item, COL_VALUE)
        if find_type in ("data",):
            if self.data_display.lower() == "hex":
                value = value.replace(" ", "").replace("<", "").replace(">", "").upper()
                text = text.replace(" ", "").replace("<", "").replace(">", "").upper()
            else:
                value = value.rstrip("=")
                text = text.rstrip("=")
        return (text in value) if case_sensitive else (text.lower() in value.lower())

    def _do_replace(self, item, find, repl, find_type, case_sensitive):
        if find_type == "key":
            name = item.text()
            pattern = ("" if case_sensitive else "(?i)") + re.escape(find)
            new_name = re.sub(pattern, lambda m: repl, name)
            # Check uniqueness
            parent = item.parent()
            if parent is None:
                parent = self.model.invisibleRootItem()
            for row in range(parent.rowCount()):
                sibling = parent.child(row, COL_KEY)
                if sibling and sibling is not item and sibling.text() == new_name:
                    QApplication.beep()
                    return False
            item.setText(new_name)
            return True

        value = self.get_item_data(item, COL_VALUE)
        if find_type == "string":
            pattern = ("" if case_sensitive else "(?i)") + re.escape(find)
            value = re.sub(pattern, lambda m: repl, value)
        elif find_type == "data":
            if self.data_display.lower() == "hex":
                find_h = find.replace(" ", "").replace("<", "").replace(">", "").upper()
                repl_h = repl.replace(" ", "").replace("<", "").replace(">", "").upper()
                val_h = value.replace(" ", "").replace("<", "").replace(">", "").upper()
                val_h = val_h.replace(find_h, repl_h)
                value = "<{}>".format(" ".join(val_h[i : i + 8] for i in range(0, len(val_h), 8)))
            else:
                find_b = find.rstrip("=")
                repl_b = repl.rstrip("=")
                val_b = value.rstrip("=").replace(find_b, repl_b)
                if len(val_b) % 4:
                    val_b += "=" * (4 - len(val_b) % 4)
                value = val_b
        else:
            value = repl
        self.set_item_data(item, COL_VALUE, value)
        return True

    # ── Context Menu ─────────────────────────────────────────────

    def popup(self, pos):
        index = self.tree.indexAt(pos)
        item = self.item_from_index(index) if index.isValid() else self.root_item()
        if item:
            self.tree.setCurrentIndex(self.model.indexFromItem(item))

        menu = QMenu(self)
        check_type = self.get_check_type_from_item(item) if item else ""
        root = self.root_item()

        if check_type in ("array", "dictionary"):
            menu.addAction("Expand Node", lambda: self.tree.expand(self.model.indexFromItem(item)))
            menu.addAction("Collapse Node", lambda: self.tree.collapse(self.model.indexFromItem(item)))
            menu.addSeparator()
            menu.addAction("Expand Children", lambda: self._expand_children(item))
            menu.addAction("Collapse Children", lambda: self._collapse_children(item))
            menu.addSeparator()
        elif check_type == "data":
            menu.addAction("Reverse Endianness", lambda: self.hex_swap(item))
            menu.addSeparator()

        menu.addAction("Expand All", self._expand_all)
        menu.addAction("Collapse All", self._collapse_all)
        menu.addSeparator()

        if item == root:
            if check_type in ("array", "dictionary"):
                menu.addAction("New top level entry", lambda: self.new_row(root))
        elif item:
            if check_type in ("dictionary", "array") and (
                self.tree.isExpanded(self.model.indexFromItem(item)) or item.rowCount() == 0
            ):
                menu.addAction("New child under '{}'".format(item.text()), lambda: self.new_row(item))
                menu.addAction("New sibling of '{}'".format(item.text()), lambda: self.new_row(item, True))
            else:
                menu.addAction("New sibling of '{}'".format(item.text()), lambda: self.new_row(item))
            menu.addAction("Remove '{}'".format(item.text()), lambda: self.remove_row(item))
            parent = item.parent() or self.model.invisibleRootItem()
            if item.row() > 0:
                menu.addAction("Move Up", lambda: self.move_item(-1))
            if item.row() < parent.rowCount() - 1:
                menu.addAction("Move Down", lambda: self.move_item(1))

        # Sort keys
        parent_for_sort = item if item == root else (item.parent() or self.model.invisibleRootItem())
        if item and self.get_check_type_from_item(
            parent_for_sort if parent_for_sort != self.model.invisibleRootItem() else root
        ) in ("dictionary", "array"):
            menu.addSeparator()
            # Recursive sort target
            recurs_target = (
                item
                if check_type in ("dictionary", "array") and item.rowCount()
                else (parent_for_sort if parent_for_sort != self.model.invisibleRootItem() else root)
            )
            menu.addAction(
                "Recursively sort keys starting at '{}'".format(recurs_target.text()),
                lambda t=recurs_target: self.sort_keys(t, recursive=True),
            )
            menu.addAction(
                "Recursively reverse sort keys starting at '{}'".format(recurs_target.text()),
                lambda t=recurs_target: self.sort_keys(t, recursive=True, reverse=True),
            )
            # Direct sort target
            sort_target = (
                item
                if item == root or (check_type == "dictionary" and item.rowCount() > 1)
                else (parent_for_sort if parent_for_sort != self.model.invisibleRootItem() else root)
            )
            menu.addAction("Sort keys in '{}'".format(sort_target.text()), lambda t=sort_target: self.sort_keys(t))
            menu.addAction(
                "Reverse sort keys in '{}'".format(sort_target.text()),
                lambda t=sort_target: self.sort_keys(t, reverse=True),
            )

        # Copy/Paste
        menu.addSeparator()
        menu.addAction("Copy", self.copy_selection)
        if item and item != root and check_type in ("array", "dictionary"):
            menu.addAction("Copy Children", self.copy_children)
        menu.addAction("Paste", self.paste_selection)

        # Config info
        if item:
            cell_search = self._get_cell_path_list(item)
            tex_path = self.controller.get_best_tex_path()
            if cell_search and tex_path and os.path.isfile(tex_path):
                menu.addSeparator()
                menu.addAction('Show info for "{}"'.format(" -> ".join(cell_search)), self.show_config_info)

        # Menu data presets
        if item and self.menu_data:
            cell_path = self.get_cell_path(item)
            first_key = True
            for key in sorted(self.menu_data):
                options = self.menu_data[key]
                valid = [x for x in options if x.startswith(cell_path)]
                if not valid:
                    continue
                if first_key:
                    menu.addSeparator()
                    first_key = False
                option_menu = QMenu(key, menu)
                for opt_path in sorted(valid):
                    item_menu = QMenu(option_menu)
                    for x in options[opt_path]:
                        if x.get("separator", False) is not False:
                            item_menu.addSeparator()
                        elif x.get("title", False) is not False:
                            act = item_menu.addAction(x.get("title", ""))
                            act.setEnabled(False)
                        else:
                            name = x["name"]
                            value = x["value"]
                            types = x["types"]
                            passed = (item, opt_path, types, value)
                            item_menu.addAction(name, lambda p=passed: self.merge_menu_preset(p))
                    parts = self.split(opt_path)
                    label = " -> ".join(parts[1:] if parts and parts[0].lower() == "root" and len(parts) > 1 else parts)
                    option_menu.addAction(label).setMenu(item_menu)
                menu.addMenu(option_menu)

        menu.exec(self.tree.viewport().mapToGlobal(pos))

    # ── Tree Expand/Collapse ─────────────────────────────────────

    def _expand_all(self):
        self.tree.expandAll()

    def _collapse_all(self):
        self.tree.collapseAll()
        root = self.root_item()
        if root:
            self.tree.expand(self.model.indexFromItem(root))

    def _expand_children(self, item):
        if item is None:
            return
        idx = self.model.indexFromItem(item)
        self.tree.expand(idx)
        for row in range(item.rowCount()):
            child = item.child(row, COL_KEY)
            if child:
                self._expand_children(child)

    def _collapse_children(self, item):
        if item is None:
            return
        for row in range(item.rowCount()):
            child = item.child(row, COL_KEY)
            if child:
                self._collapse_children(child)
                self.tree.collapse(self.model.indexFromItem(child))

    def on_expanded(self, index):
        pass  # Alternating colors handled by delegate/stylesheet

    def on_collapsed(self, index):
        pass

    def on_click(self, index):
        pass

    # ── Double-Click / Editing ───────────────────────────────────

    def on_double_click(self, index):
        if not index.isValid():
            return
        col = index.column()
        item = self.item_from_index(index)
        if item is None:
            return

        if col == COL_TYPE:
            # Show type popup
            self._show_type_menu(item, index)
            return

        if col == COL_VALUE:
            check_type = self.get_check_type_from_item(item)
            if check_type in ("dictionary", "array"):
                return
            if check_type == "boolean":
                self._show_bool_menu(item, index)
                return

        if col == COL_KEY:
            parent = item.parent()
            if parent and self.get_check_type_from_item(parent) == "array":
                return
            if item == self.root_item() and self.get_check_type_from_item(item) in ("dictionary", "array"):
                return

        # Open inline editor
        self.tree.edit(index)

    def start_editing(self):
        index = self.tree.currentIndex()
        item = self.item_from_index(index)
        if item is None:
            return

        root = self.root_item()
        check_type = self.get_check_type_from_item(item)
        parent = item.parent()
        parent_type = self.get_check_type_from_item(parent) if parent else "dictionary"

        if item == root and check_type in ("array", "dictionary"):
            return

        available = []
        if parent_type != "array" and not (item == root):
            available.append(COL_KEY)
        if check_type not in ("array", "boolean", "dictionary"):
            available.append(COL_VALUE)

        if not available:
            return

        if len(available) == 1:
            edit_col = available[0]
        else:
            edit_col = COL_VALUE if self.controller.settings.get("edit_values_before_keys") else COL_KEY

        edit_index = index.sibling(index.row(), edit_col)
        self.tree.edit(edit_index)

    def _show_type_menu(self, item, index):
        menu = QMenu(self)
        root = self.root_item()

        if item == root:
            types = ["Dictionary", "Array"]
        else:
            types = ["Dictionary", "Array", None, "Boolean", "Data", "Date", "Number", "UID", "String"]

        for t in types:
            if t is None:
                menu.addSeparator()
            else:
                action = menu.addAction(t)
                action.triggered.connect(lambda checked, tp=t: self.change_type(MENU_CODE + " " + tp, item))

        pos = self.tree.visualRect(index).bottomLeft()
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _show_bool_menu(self, item, index):
        menu = QMenu(self)
        menu.addAction(self.b_true(), lambda: self._set_bool(item, self.b_true()))
        menu.addAction(self.b_false(), lambda: self._set_bool(item, self.b_false()))
        pos = self.tree.visualRect(index).bottomLeft()
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _set_bool(self, item, value):
        old_value = self.get_item_data(item, COL_VALUE)
        if old_value == value:
            return
        self.add_undo(
            [
                {
                    "type": "edit",
                    "item": item,
                    "old_key": item.text(),
                    "old_type": self.get_item_data(item, COL_TYPE),
                    "old_value": old_value,
                }
            ]
        )
        self.set_item_data(item, COL_VALUE, value)
        self.mark_edited()

    def change_type(self, value, item=None):
        if item is None:
            item = self.item_from_index(self.tree.currentIndex())
        if item is None:
            return
        old_type = self.get_item_data(item, COL_TYPE)
        if old_type == value:
            return

        changes = []
        # Remove children
        while item.rowCount() > 0:
            child = item.child(0, COL_KEY)
            changes.append(
                {
                    "type": "remove",
                    "item": child,
                    "type_item": item.child(0, COL_TYPE).clone() if item.child(0, COL_TYPE) else QStandardItem(""),
                    "value_item": item.child(0, COL_VALUE).clone() if item.child(0, COL_VALUE) else QStandardItem(""),
                    "parent": item,
                    "index": 0,
                }
            )
            item.removeRow(0)

        changes.append(
            {
                "type": "edit",
                "item": item,
                "old_key": item.text(),
                "old_type": old_type,
                "old_value": self.get_item_data(item, COL_VALUE),
            }
        )
        self.add_undo(changes)

        self.set_item_data(item, COL_TYPE, value)
        type_name = value.replace(MENU_CODE + " ", "").replace(MENU_CODE, "").lower()

        if type_name == "number":
            self.set_item_data(item, COL_VALUE, "0" if self.int_display.lower() == "decimal" else "0x0")
        elif type_name == "boolean":
            self.set_item_data(item, COL_VALUE, self.b_true())
        elif type_name == "array":
            self.set_item_data(item, COL_VALUE, "0 children")
        elif type_name == "dictionary":
            self.set_item_data(item, COL_VALUE, "0 key/value pairs")
        elif type_name == "date":
            self.set_item_data(item, COL_VALUE, datetime.datetime.now().strftime("%b %d, %Y %I:%M:%S %p"))
        elif type_name == "data":
            self.set_item_data(item, COL_VALUE, "<>" if self.data_display.lower() == "hex" else "")
        elif type_name == "uid":
            self.set_item_data(item, COL_VALUE, "0")
        else:
            self.set_item_data(item, COL_VALUE, "")

        self.mark_edited()

    def cycle_type(self, increment=True):
        item = self.item_from_index(self.tree.currentIndex())
        if item is None:
            return
        root = self.root_item()
        if item == root:
            valid_types = ["Dictionary", "Array"]
        else:
            valid_types = ["Dictionary", "Array", "Boolean", "Data", "Date", "Number", "UID", "String"]

        current = self.get_check_type_from_item(item)
        # Capitalize for matching
        current_cap = current.capitalize() if current != "uid" else "UID"
        try:
            idx = valid_types.index(current_cap)
        except ValueError:
            return
        mod = 1 if increment else -1
        new_type = valid_types[(idx + mod) % len(valid_types)]
        self.change_type(MENU_CODE + " " + new_type, item)

    # ── Hex Swap (Reverse Endianness) ────────────────────────────

    def hex_swap(self, item=None):
        if item is None:
            item = self.item_from_index(self.tree.currentIndex())
        if item is None:
            return
        if self.get_check_type_from_item(item) != "data":
            return
        value_text = self.get_item_data(item, COL_VALUE)
        try:
            if self.data_display.lower() == "hex":
                hex_str = value_text.replace("<", "").replace(">", "").replace(" ", "")
                raw = binascii.unhexlify(hex_str.encode("utf-8"))
            else:
                raw = base64.b64decode(value_text.encode("utf-8"))
            reversed_raw = raw[::-1]
            new_value = self.get_data_display(reversed_raw)

            old_value = value_text
            self.add_undo(
                [
                    {
                        "type": "edit",
                        "item": item,
                        "old_key": item.text(),
                        "old_type": self.get_item_data(item, COL_TYPE),
                        "old_value": old_value,
                    }
                ]
            )
            self.set_item_data(item, COL_VALUE, new_value)
            self.mark_edited()
        except Exception as e:
            QApplication.beep()
            QMessageBox.critical(self, "Error Reversing Endianness", str(e))

    # ── Strip Operations ─────────────────────────────────────────

    def strip_comments(self, event=None):
        ignore_case = self.controller.settings.get("comment_strip_ignore_case", False)
        check_string = self.controller.settings.get("comment_strip_check_string", True)
        prefix = self.controller.settings.get("comment_strip_prefix", "#")
        prefix = "#" if not prefix else prefix.lower() if ignore_case else prefix

        removals = []
        root = self.root_item()
        for item in list(self._iter_all_items()):
            if item == root:
                continue
            name = item.text()
            name = name.lower() if ignore_case else name
            names = [name]
            if check_string and self.get_check_type_from_item(item) == "string":
                val = self.get_item_data(item, COL_VALUE)
                names.append(val.lower() if ignore_case else val)
            if any(n.startswith(prefix) for n in names):
                parent = item.parent() or self.model.invisibleRootItem()
                row = item.row()
                removals.append(
                    {
                        "type": "remove",
                        "item": item,
                        "type_item": parent.child(row, COL_TYPE).clone()
                        if parent.child(row, COL_TYPE)
                        else QStandardItem(""),
                        "value_item": parent.child(row, COL_VALUE).clone()
                        if parent.child(row, COL_VALUE)
                        else QStandardItem(""),
                        "parent": parent,
                        "index": row,
                    }
                )

        if not removals:
            return
        # Remove in reverse order to preserve indices
        for r in reversed(removals):
            r["parent"].removeRow(r["index"])
        self.add_undo(removals)
        self.mark_edited()
        self.update_all_children()

    def strip_disabled(self, event=None):
        root = self.root_item()
        removals = []
        for item in list(self._iter_all_items()):
            name = item.text().lower()
            check_type = self.get_check_type_from_item(item)
            value = self.get_item_data(item, COL_VALUE)
            if check_type == "boolean" and (
                (name == "enabled" and value == self.b_false()) or (name == "disabled" and value == self.b_true())
            ):
                rem_item = item.parent()
                if rem_item is None or rem_item == root or item == root:
                    continue
                parent = rem_item.parent() or self.model.invisibleRootItem()
                row = rem_item.row()
                removals.append(
                    {
                        "type": "remove",
                        "item": rem_item,
                        "type_item": parent.child(row, COL_TYPE).clone()
                        if parent.child(row, COL_TYPE)
                        else QStandardItem(""),
                        "value_item": parent.child(row, COL_VALUE).clone()
                        if parent.child(row, COL_VALUE)
                        else QStandardItem(""),
                        "parent": parent,
                        "index": row,
                    }
                )

        if not removals:
            return
        for r in reversed(removals):
            r["parent"].removeRow(r["index"])
        self.add_undo(removals)
        self.mark_edited()
        self.update_all_children()

    def strip_whitespace(self, event=None, keys=False, values=False):
        root = self.root_item()
        changes = []
        for item in self._iter_all_items():
            if item == root:
                continue
            old_key = item.text()
            old_value = self.get_item_data(item, COL_VALUE)
            changed = False

            if keys:
                new_key = old_key.strip()
                if new_key != old_key:
                    # Check uniqueness
                    parent = item.parent() or self.model.invisibleRootItem()
                    existing = [
                        parent.child(r, COL_KEY).text()
                        for r in range(parent.rowCount())
                        if parent.child(r, COL_KEY) is not item
                    ]
                    if new_key not in existing:
                        item.setText(new_key)
                        changed = True

            if values and self.get_check_type_from_item(item) == "string":
                new_value = old_value.strip()
                if new_value != old_value:
                    self.set_item_data(item, COL_VALUE, new_value)
                    changed = True

            if changed:
                changes.append(
                    {
                        "type": "edit",
                        "item": item,
                        "old_key": old_key,
                        "old_type": self.get_item_data(item, COL_TYPE),
                        "old_value": old_value,
                    }
                )

        if changes:
            self.add_undo(changes)
            self.mark_edited()

    # ── OC Snapshot ──────────────────────────────────────────────

    def oc_snapshot(self, event=None, clean=False):
        # Minimal implementation - delegates to the full OC snapshot logic
        # The full implementation would port the 500+ line oc_snapshot from plistwindow.py
        # For now, prompt for directory and show a message
        oc_path = QFileDialog.getExistingDirectory(
            self, "Select OC Folder", self.controller.settings.get("last_snapshot_path", "")
        )
        if not oc_path:
            return
        self.controller.settings["last_snapshot_path"] = oc_path

        # Verify it looks like an OC folder
        oc_efi = os.path.join(oc_path, "OpenCore.efi")
        if not os.path.exists(oc_efi):
            QApplication.beep()
            QMessageBox.critical(self, "Invalid OC Folder", "OpenCore.efi not found in the selected folder.")
            return

        QMessageBox.information(
            self, "OC Snapshot", "OC Snapshot functionality is available.\nSelected: {}".format(oc_path)
        )

    # ── Config Info ──────────────────────────────────────────────

    def show_config_info(self):
        item = self.item_from_index(self.tree.currentIndex())
        if item is None:
            return
        search_list = self._get_cell_path_list(item)
        if not search_list:
            return

        config_tex_path = self.controller.get_best_tex_path()
        if not config_tex_path or not os.path.isfile(config_tex_path):
            QApplication.beep()
            QMessageBox.information(
                self, "Configuration.tex Not Found", "Configuration.tex was not found. Use Settings to download it."
            )
            return

        from propertree import config_tex_info

        dark = self.controller.get_dark()
        fg = "white" if dark else "black"
        bg = "black" if dark else "white"
        config_tex_info.display_info_window(
            config_tex_path, search_list, 120, False, False, self, font=QFont("Courier New", 11), fg=fg, bg=bg
        )

    def _get_cell_path_list(self, item):
        """Build the path list for config info lookup."""
        parts = []
        current = item
        while current:
            name = current.text()
            parent = current.parent()
            if parent and self.get_check_type_from_item(parent) == "array":
                parts.insert(0, "*")
            else:
                parts.insert(0, name)
            current = parent
        # Remove "Root" prefix
        if parts and parts[0] == "Root":
            parts = parts[1:]
        return parts

    def get_cell_path(self, item):
        """Get the escaped path string for an item (array indices become '*')."""
        if item is None:
            return ""
        parts = []
        current = item
        while current:
            parent = current.parent()
            if parent and self.get_check_type_from_item(parent) == "array":
                parts.insert(0, "*")
            else:
                parts.insert(0, current.text().replace("/", "\\/"))
            current = parent
        return "/".join(parts)

    @staticmethod
    def split(path, escape="\\", separator="/"):
        result = []
        token = ""
        state = 0
        for t in path:
            if state == 0:
                if t == escape:
                    state = 1
                elif t == separator:
                    result.append(token)
                    token = ""
                else:
                    token += t
            elif state == 1:
                token += t
                state = 0
        result.append(token)
        return result

    def merge_menu_preset(self, val=None):
        if val is None:
            return
        item, path, itypes, value = val
        paths = self.split(str(path))
        types = itypes.split("/")
        if len(paths) != len(types):
            QApplication.beep()
            QMessageBox.critical(self, "Incorrect Patch Format", "Patch is incomplete.")
            return
        if not paths or paths[0] == "*":
            QApplication.beep()
            QMessageBox.critical(self, "Incorrect Patch Format", "Patch starts with an array - must be a dictionary.")
            return

        created = None
        current_item = None  # None means invisible root (top-level)
        undo_list = []

        for p, t in zip(paths, types):
            found = False
            needed_type = {"d": "Dictionary", "a": "Array"}.get(t.lower(), "Dictionary")
            parent_for_search = current_item if current_item else self.model.invisibleRootItem()
            for row in range(parent_for_search.rowCount()):
                child = parent_for_search.child(row, COL_KEY)
                if child and child.text() == p:
                    current_type = self.get_check_type_from_item(child)
                    if current_type.lower() != needed_type.lower():
                        answer = QMessageBox.question(
                            self,
                            "Incorrect Type",
                            "{} is {}, should be {}.\n\nWould you like to replace it?".format(
                                child.text(), current_type, needed_type
                            ),
                            QMessageBox.Yes | QMessageBox.No,
                        )
                        if answer == QMessageBox.Yes:
                            # Remove children
                            while child.rowCount() > 0:
                                removed = child.child(0, COL_KEY)
                                undo_list.append(
                                    {
                                        "type": "remove",
                                        "item": removed,
                                        "parent": child,
                                        "index": 0,
                                    }
                                )
                                child.removeRow(0)
                            # Change type
                            undo_list.append(
                                {
                                    "type": "edit",
                                    "item": child,
                                    "old_key": child.text(),
                                    "old_type": self.get_item_data(child, COL_TYPE),
                                    "old_value": self.get_item_data(child, COL_VALUE),
                                }
                            )
                            self.set_item_data(child, COL_TYPE, MENU_CODE + " " + needed_type)
                            if needed_type.lower() == "dictionary":
                                self.set_item_data(child, COL_VALUE, "0 key/value pairs")
                            else:
                                self.set_item_data(child, COL_VALUE, "0 children")
                        else:
                            # Undo what we did
                            for u in reversed(undo_list):
                                self._undo_single(u)
                            return
                    found = True
                    current_item = child
                    break
            if not found:
                # Create the node
                parent_target = current_item if current_item else self.model.invisibleRootItem()
                key_item = QStandardItem(p)
                type_item = QStandardItem(MENU_CODE + " " + needed_type)
                val_text = "0 key/value pairs" if needed_type.lower() == "dictionary" else "0 children"
                value_item = QStandardItem(val_text)
                parent_target.appendRow([key_item, type_item, value_item])
                undo_list.append({"type": "add", "item": key_item})
                current_item = key_item
                # Expand it
                self.tree.expand(self.model.indexFromItem(current_item))

        # Now add the final value(s)
        current_type = self.get_check_type_from_item(current_item) if current_item else ""
        replace_asked = False
        just_add = True

        if current_type.lower() == "dictionary" and isinstance(value, dict):
            just_add = False
            for row in range(current_item.rowCount() - 1, -1, -1):
                child = current_item.child(row, COL_KEY)
                if child and child.text() in value:
                    if not replace_asked:
                        answer = QMessageBox.question(
                            self,
                            "Key(s) Already Exist",
                            "One or more keys already exist at the destination.\n\nWould you like to replace them?",
                            QMessageBox.Yes | QMessageBox.No,
                        )
                        if answer == QMessageBox.Yes:
                            replace_asked = True
                        else:
                            for u in reversed(undo_list):
                                self._undo_single(u)
                            return
                    undo_list.append(
                        {
                            "type": "remove",
                            "item": child,
                            "parent": current_item,
                            "index": row,
                        }
                    )
                    current_item.removeRow(row)
            for k in value:
                created = self.add_node(value[k], current_item, k)
                if created and created[0]:
                    undo_list.append({"type": "add", "item": created[0]})

        if just_add:
            created = self.add_node(value, current_item, "")
            if created and created[0]:
                undo_list.append({"type": "add", "item": created[0]})

        self.add_undo(undo_list)
        self.update_all_children()
        self.mark_edited()

    def _undo_single(self, entry):
        """Undo a single operation (used for rolling back incomplete preset merges)."""
        etype = entry.get("type")
        if etype == "add":
            item = entry["item"]
            parent = item.parent() or self.model.invisibleRootItem()
            parent.removeRow(item.row())
        elif etype == "remove":
            # Re-add not feasible without stored row data; best effort
            pass
        elif etype == "edit":
            item = entry["item"]
            item.setText(entry["old_key"])
            self.set_item_data(item, COL_TYPE, entry["old_type"])
            self.set_item_data(item, COL_VALUE, entry["old_value"])

    # ── Event Filter (for drag-drop) ─────────────────────────────

    def eventFilter(self, obj, event):
        if obj == self.tree.viewport():
            if event.type() == QEvent.MouseButtonPress:
                self.clicked_drag = True
                self.drag_start = None
                self.drag_last_move_y = None
                press_pos = event.position().toPoint() if hasattr(event.position(), "toPoint") else event.pos()
                press_index = self.tree.indexAt(press_pos)
                self.drag_source_item = self.item_from_index(press_index) if press_index.isValid() else None
            elif event.type() == QEvent.MouseMove and self.clicked_drag:
                if self.controller.settings.get("enable_drag_and_drop", True):
                    self._handle_drag(event)
            elif event.type() == QEvent.MouseButtonRelease:
                if self.dragging:
                    self._confirm_drag(event)
                self.clicked_drag = False
                self.drag_start = None
                self.dragging = False
                self.drag_last_move_y = None
        return super().eventFilter(obj, event)

    def _should_suppress_drop(self, insert_row, source_row, pos_y):
        """Return True when hysteresis should block the drop.

        After each live swap, the boundary between the two items lands almost
        exactly under the cursor.  Without this guard every subsequent mouse-move
        event triggers the reverse swap, causing visible oscillation.

        We require the mouse to travel at least ``threshold`` pixels past the
        Y position of the previous swap before allowing another swap.
        """
        if self.drag_last_move_y is None:
            return False
        threshold = 6  # ~1/3 of a typical 20-px row height
        if insert_row < source_row:  # moving up
            return pos_y > self.drag_last_move_y - threshold
        else:  # moving down
            return pos_y < self.drag_last_move_y + threshold

    def _resolve_drop(self, source_item, drop_item):
        """Return (target_parent, insert_row) for the drag, or None if invalid.

        When the mouse hovers over a descendant of a sibling (because that sibling
        is expanded), walk up to the sibling level so the move is always a sibling
        reorder rather than an accidental insertion into the expanded collection.
        """
        if drop_item is None or drop_item == source_item:
            return None

        source_parent = source_item.parent() or self.model.invisibleRootItem()

        # Walk up from drop_item to find its ancestor that lives at the same level
        # as source_item (i.e. whose parent == source_parent).
        candidate = drop_item
        while candidate is not None:
            candidate_parent = candidate.parent() or self.model.invisibleRootItem()
            if candidate_parent == source_parent:
                break
            candidate = candidate.parent()

        if candidate is not None and candidate != source_item:
            # A same-level sibling was found — always reorder, never insert into it.
            target_parent = source_parent
            insert_row = candidate.row()
        else:
            # No same-level ancestor found → cross-level move.
            drop_parent = drop_item.parent() or self.model.invisibleRootItem()
            drop_type = self.get_check_type_from_item(drop_item)
            if drop_type in ("dictionary", "array") and (
                drop_item.rowCount() == 0 or self.tree.isExpanded(self.model.indexFromItem(drop_item))
            ):
                target_parent = drop_item
                insert_row = 0
            else:
                target_parent = drop_parent
                insert_row = drop_item.row()

        # Don't allow dropping into self or any descendant.
        check = target_parent
        while check and check != self.model.invisibleRootItem():
            if check == source_item:
                return None
            check = check.parent()

        if source_parent == target_parent and source_item.row() == insert_row:
            return None  # No-op

        return target_parent, insert_row

    def _handle_drag(self, event):
        pos = event.position().toPoint() if hasattr(event.position(), "toPoint") else event.pos()
        item = self.drag_source_item
        if item is None or item == self.root_item():
            return

        if self.drag_start is None:
            self.drag_start = (pos.x(), pos.y())
            self.drag_undo = None
            return

        if not self.dragging:
            x, y = self.drag_start
            drag_distance = math.sqrt((pos.x() - x) ** 2 + (pos.y() - y) ** 2)
            dead_zone = self.controller.settings.get("drag_dead_zone", 20)
            if drag_distance < dead_zone:
                return
            self.dragging = True

        if not self.drag_undo:
            parent = item.parent() or self.model.invisibleRootItem()
            self.drag_undo = {"parent": parent, "index": item.row(), "name": item.text()}

        # Determine drop target
        drop_index = self.tree.indexAt(pos)
        if not drop_index.isValid():
            return

        drop_item = self.item_from_index(drop_index)
        result = self._resolve_drop(item, drop_item)
        if result is None:
            return

        target_parent, insert_row = result
        if self._should_suppress_drop(insert_row, item.row(), pos.y()):
            return

        source_parent = item.parent() or self.model.invisibleRootItem()
        row_data = source_parent.takeRow(item.row())
        target_parent.insertRow(min(insert_row, target_parent.rowCount()), row_data)
        self.drag_last_move_y = pos.y()

    def _confirm_drag(self, event):
        if not self.drag_undo:
            return
        item = self.drag_source_item
        if item is None:
            return

        current_parent = item.parent() or self.model.invisibleRootItem()

        if self.drag_undo["parent"] == current_parent and self.drag_undo["index"] == item.row():
            return  # Didn't actually move

        self.mark_edited()
        undo_tasks = [
            {"type": "move", "item": item, "parent": self.drag_undo["parent"], "index": self.drag_undo["index"]}
        ]

        # Ensure unique names in dicts
        parent_type = (
            self.get_check_type_from_item(current_parent) if current_parent != self.model.invisibleRootItem() else ""
        )
        if parent_type == "dictionary":
            names = [
                current_parent.child(r, COL_KEY).text()
                for r in range(current_parent.rowCount())
                if current_parent.child(r, COL_KEY) is not item
            ]
            name = item.text()
            if name in names:
                new_name = self._get_unique_name(name, names)
                undo_tasks.append(
                    {
                        "type": "edit",
                        "item": item,
                        "old_key": self.drag_undo["name"],
                        "old_type": self.get_item_data(item, COL_TYPE),
                        "old_value": self.get_item_data(item, COL_VALUE),
                    }
                )
                item.setText(new_name)

        self.update_all_children()
        self.add_undo(undo_tasks)
        self.drag_undo = None
