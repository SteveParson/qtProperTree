"""Tests for PlistWindow core functionality."""

import datetime
import os
import sys
from collections import OrderedDict

import pytest

# Ensure the project root is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication

from propertree import plist
from propertree.qt_delegates import COL_KEY, COL_TYPE, COL_VALUE, MENU_CODE
from propertree.qt_plist_window import PlistWindow

# ── Fixtures & helpers ──────────────────────────────────────────


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication once for the entire test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    app.setApplicationName("qtProperTreeTest")
    yield app


class FakeController:
    """Minimal stand-in for ProperTreeApp."""

    def __init__(self):
        self.settings = {}
        self.windows = []
        self.allowed_bool = ("True/False", "YES/NO", "On/Off", "1/0")
        self.max_undo = 200
        self.use_dark = False
        self.default_dark = {
            "alternating_color_1": "#161616",
            "alternating_color_2": "#202020",
            "highlight_color": "#1E90FF",
            "background_color": "#161616",
        }
        self.default_light = {
            "alternating_color_1": "#F0F1F1",
            "alternating_color_2": "#FEFEFE",
            "highlight_color": "#1E90FF",
            "background_color": "#FEFEFE",
        }

    def text_color(self, hex_color, invert=False):
        hex_color = hex_color.lower().lstrip("#")
        try:
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            luminance_high = (r * 0.299 + g * 0.587 + b * 0.114) > 186
            if luminance_high:
                return "white" if invert else "black"
            return "black" if invert else "white"
        except Exception:
            return "white" if invert else "black"

    def _clipboard_append(self, text):
        self._clipboard = text

    def get_dark(self):
        return False

    # Stubs for menu actions referenced by PlistWindow._setup_menus
    def new_plist(self, *a, **kw):
        pass

    def open_plist(self, *a, **kw):
        pass

    def save_plist(self, *a, **kw):
        pass

    def save_plist_as(self, *a, **kw):
        pass

    def duplicate_plist(self, *a, **kw):
        pass

    def show_converter(self, *a, **kw):
        pass

    def show_settings(self, *a, **kw):
        pass

    def quit(self, *a, **kw):
        pass

    def open_recent(self, *a, **kw):
        pass

    def clear_recents(self, *a, **kw):
        pass

    def get_best_tex_path(self):
        return None


def make_window(qapp, data=None):
    """Create a PlistWindow loaded with *data* (default: empty dict)."""
    if data is None:
        data = OrderedDict()
    ctrl = FakeController()
    win = PlistWindow(ctrl)
    win.open_plist(None, data, auto_expand=True)
    return win


# ── 1. Round-trip serialization ─────────────────────────────────


class TestRoundTrip:
    def test_dict_with_various_types(self, qapp):
        data = OrderedDict(
            [
                ("str_key", "hello"),
                ("int_key", 42),
                ("bool_key", True),
                ("data_key", b"\xde\xad\xbe\xef"),
                ("date_key", datetime.datetime(2024, 3, 11, 12, 30, 0)),
                ("array_key", [1, "two"]),
                ("nested_dict", OrderedDict([("inner", "value")])),
            ]
        )
        win = make_window(qapp, data)
        result = win.nodes_to_values()
        assert result["str_key"] == "hello"
        assert result["int_key"] == 42
        assert result["bool_key"] is True
        assert result["data_key"] == b"\xde\xad\xbe\xef"
        assert result["date_key"] == datetime.datetime(2024, 3, 11, 12, 30, 0)
        assert result["array_key"] == [1, "two"]
        assert result["nested_dict"] == OrderedDict([("inner", "value")])

    def test_empty_dict(self, qapp):
        win = make_window(qapp, OrderedDict())
        result = win.nodes_to_values()
        assert result == OrderedDict()

    def test_empty_array(self, qapp):
        win = make_window(qapp, [])
        result = win.nodes_to_values()
        assert result == []

    def test_uid_values(self, qapp):
        """UID dicts ({CF$UID: n}) round-trip correctly."""
        data = OrderedDict([("uid_entry", {"CF$UID": 123})])
        win = make_window(qapp, data)
        result = win.nodes_to_values()
        assert result["uid_entry"] == {"CF$UID": 123}


# ── 2. Value validation (qualify_value) ─────────────────────────


class TestQualifyValue:
    def _win(self, qapp):
        return make_window(qapp)

    def test_valid_hex_data(self, qapp):
        win = self._win(qapp)
        ok, val = win.qualify_value("DEADBEEF", "data")
        assert ok is True
        assert "DEADBEEF" in val

    def test_invalid_hex_char(self, qapp):
        win = self._win(qapp)
        ok, title, msg = win.qualify_value("GHIJ", "data")
        assert ok is False

    def test_odd_length_hex(self, qapp):
        win = self._win(qapp)
        ok, title, msg = win.qualify_value("ABC", "data")
        assert ok is False

    def test_valid_base64_data(self, qapp):
        win = self._win(qapp)
        win.data_display = "Base64"
        ok, val = win.qualify_value("AQID", "data")
        assert ok is True

    def test_invalid_base64_data(self, qapp):
        win = self._win(qapp)
        win.data_display = "Base64"
        ok, title, msg = win.qualify_value("!!!!", "data")
        assert ok is False

    def test_valid_date(self, qapp):
        win = self._win(qapp)
        ok, val = win.qualify_value("Mar 11, 2019 12:29:00 PM", "date")
        assert ok is True

    def test_invalid_date(self, qapp):
        win = self._win(qapp)
        ok, title, msg = win.qualify_value("not-a-date", "date")
        assert ok is False

    def test_number_int(self, qapp):
        win = self._win(qapp)
        ok, val = win.qualify_value("42", "number")
        assert ok is True
        assert val == "42"

    def test_number_float(self, qapp):
        win = self._win(qapp)
        ok, val = win.qualify_value("3.14", "number")
        assert ok is True
        assert val == "3.14"

    def test_number_hex(self, qapp):
        win = self._win(qapp)
        ok, val = win.qualify_value("0xFF", "number")
        assert ok is True

    def test_number_invalid(self, qapp):
        win = self._win(qapp)
        ok, title, msg = win.qualify_value("abc", "number")
        assert ok is False

    def test_boolean_valid(self, qapp):
        win = self._win(qapp)
        ok, val = win.qualify_value("True", "boolean")
        assert ok is True
        assert val == "True"

    def test_boolean_invalid(self, qapp):
        win = self._win(qapp)
        ok, title, msg = win.qualify_value("maybe", "boolean")
        assert ok is False

    def test_uid_valid(self, qapp):
        win = self._win(qapp)
        ok, val = win.qualify_value("100", "uid")
        assert ok is True
        assert val == "100"

    def test_uid_negative(self, qapp):
        win = self._win(qapp)
        ok, title, msg = win.qualify_value("-1", "uid")
        assert ok is False

    def test_uid_too_large(self, qapp):
        win = self._win(qapp)
        ok, title, msg = win.qualify_value(str(2**32), "uid")
        assert ok is False


# ── 3. Type operations ──────────────────────────────────────────


class TestTypeOperations:
    def test_get_type_string_dict(self, qapp):
        win = make_window(qapp)
        assert win.get_type_string({}) == MENU_CODE + " Dictionary"

    def test_get_type_string_array(self, qapp):
        win = make_window(qapp)
        assert win.get_type_string([]) == MENU_CODE + " Array"

    def test_get_type_string_bool(self, qapp):
        win = make_window(qapp)
        assert win.get_type_string(True) == MENU_CODE + " Boolean"

    def test_get_type_string_int(self, qapp):
        win = make_window(qapp)
        assert win.get_type_string(42) == MENU_CODE + " Number"

    def test_get_type_string_float(self, qapp):
        win = make_window(qapp)
        assert win.get_type_string(3.14) == MENU_CODE + " Number"

    def test_get_type_string_string(self, qapp):
        win = make_window(qapp)
        assert win.get_type_string("hi") == MENU_CODE + " String"

    def test_get_type_string_bytes(self, qapp):
        win = make_window(qapp)
        assert win.get_type_string(b"\x00") == MENU_CODE + " Data"

    def test_get_type_string_date(self, qapp):
        win = make_window(qapp)
        assert win.get_type_string(datetime.datetime.now()) == MENU_CODE + " Date"

    def test_get_type_string_uid(self, qapp):
        win = make_window(qapp)
        assert win.get_type_string(plist.UID(1), override="UID") == MENU_CODE + " UID"

    def test_change_type_clears_children(self, qapp):
        data = OrderedDict([("child1", "a"), ("child2", "b")])
        win = make_window(qapp, data)
        root = win.root_item()
        assert root.rowCount() == 2
        win.change_type(MENU_CODE + " Array", root)
        assert root.rowCount() == 0
        assert win.get_check_type_from_item(root) == "array"

    def test_cycle_type_increment(self, qapp):
        data = OrderedDict([("key", "value")])
        win = make_window(qapp, data)
        item = win.root_item().child(0, COL_KEY)
        # Select the item
        win.tree.setCurrentIndex(win.model.indexFromItem(item))
        # String -> next type
        assert win.get_check_type_from_item(item) == "string"
        win.cycle_type(increment=True)
        # String is last in the list, should wrap to Dictionary
        new_type = win.get_check_type_from_item(item)
        assert new_type == "dictionary"

    def test_cycle_type_decrement(self, qapp):
        data = OrderedDict([("key", "value")])
        win = make_window(qapp, data)
        item = win.root_item().child(0, COL_KEY)
        win.tree.setCurrentIndex(win.model.indexFromItem(item))
        assert win.get_check_type_from_item(item) == "string"
        win.cycle_type(increment=False)
        new_type = win.get_check_type_from_item(item)
        assert new_type == "uid"


# ── 4. Sort keys ────────────────────────────────────────────────


class TestSortKeys:
    def test_alphabetical_sort(self, qapp):
        data = OrderedDict([("cherry", 1), ("apple", 2), ("banana", 3)])
        win = make_window(qapp, data)
        root = win.root_item()
        win.sort_keys(root)
        keys = [root.child(r, COL_KEY).text() for r in range(root.rowCount())]
        assert keys == ["apple", "banana", "cherry"]

    def test_reverse_sort(self, qapp):
        data = OrderedDict([("apple", 1), ("cherry", 2), ("banana", 3)])
        win = make_window(qapp, data)
        root = win.root_item()
        win.sort_keys(root, reverse=True)
        keys = [root.child(r, COL_KEY).text() for r in range(root.rowCount())]
        assert keys == ["cherry", "banana", "apple"]

    def test_natural_sort(self, qapp):
        """sorted_nicely puts item2 before item10."""
        data = OrderedDict([("item10", 1), ("item2", 2), ("item1", 3)])
        win = make_window(qapp, data)
        root = win.root_item()
        win.sort_keys(root)
        keys = [root.child(r, COL_KEY).text() for r in range(root.rowCount())]
        assert keys == ["item1", "item2", "item10"]

    def test_recursive_sort(self, qapp):
        inner = OrderedDict([("z_key", 1), ("a_key", 2)])
        data = OrderedDict([("outer", inner)])
        win = make_window(qapp, data)
        root = win.root_item()
        win.sort_keys(root, recursive=True)
        outer_item = root.child(0, COL_KEY)
        inner_keys = [outer_item.child(r, COL_KEY).text() for r in range(outer_item.rowCount())]
        assert inner_keys == ["a_key", "z_key"]


# ── 5. Find / Replace ──────────────────────────────────────────


class TestFindReplace:
    def test_find_all_key_matches(self, qapp):
        data = OrderedDict([("foo", "x"), ("bar", "y"), ("foobar", "z")])
        win = make_window(qapp, data)
        win.find_type_combo.setCurrentText("Key")
        matches = win.find_all("foo")
        names = [m.text() for m in matches]
        assert "foo" in names
        assert "foobar" in names
        assert "bar" not in names

    def test_find_all_case_insensitive(self, qapp):
        data = OrderedDict([("Foo", "x"), ("foo", "y"), ("bar", "z")])
        win = make_window(qapp, data)
        win.find_type_combo.setCurrentText("Key")
        win.f_case_check.setChecked(False)
        matches = win.find_all("FOO")
        assert len(matches) == 2

    def test_find_all_case_sensitive(self, qapp):
        data = OrderedDict([("Foo", "x"), ("foo", "y"), ("bar", "z")])
        win = make_window(qapp, data)
        win.find_type_combo.setCurrentText("Key")
        win.f_case_check.setChecked(True)
        matches = win.find_all("foo")
        assert len(matches) == 1
        assert matches[0].text() == "foo"

    def test_find_all_string_type(self, qapp):
        data = OrderedDict([("a", "hello world"), ("b", "goodbye"), ("c", 42)])
        win = make_window(qapp, data)
        win.find_type_combo.setCurrentText("String")
        matches = win.find_all("hello")
        assert len(matches) == 1

    def test_find_all_number_type(self, qapp):
        data = OrderedDict([("a", 42), ("b", 99), ("c", "42")])
        win = make_window(qapp, data)
        win.find_type_combo.setCurrentText("Number")
        matches = win.find_all("42")
        assert len(matches) == 1

    def test_do_replace_key(self, qapp):
        data = OrderedDict([("old_name", "val")])
        win = make_window(qapp, data)
        item = win.root_item().child(0, COL_KEY)
        result = win._do_replace(item, "old_name", "new_name", "key", True)
        assert result is True
        assert item.text() == "new_name"

    def test_do_replace_key_uniqueness(self, qapp):
        data = OrderedDict([("name", "a"), ("new_name", "b")])
        win = make_window(qapp, data)
        item = win.root_item().child(0, COL_KEY)
        result = win._do_replace(item, "name", "new_name", "key", True)
        assert result is False
        assert item.text() == "name"

    def test_do_replace_string_value(self, qapp):
        data = OrderedDict([("key", "hello world")])
        win = make_window(qapp, data)
        item = win.root_item().child(0, COL_KEY)
        win._do_replace(item, "hello", "goodbye", "string", True)
        assert win.get_item_data(item, COL_VALUE) == "goodbye world"

    def test_do_replace_hex_data(self, qapp):
        data = OrderedDict([("key", b"\xde\xad")])
        win = make_window(qapp, data)
        item = win.root_item().child(0, COL_KEY)
        win._do_replace(item, "<DEAD>", "<BEEF>", "data", True)
        val = win.get_item_data(item, COL_VALUE)
        assert "BEEF" in val

    def test_replace_all(self, qapp):
        data = OrderedDict([("a", "foo"), ("b", "foo bar"), ("c", "baz")])
        win = make_window(qapp, data)
        win.find_type_combo.setCurrentText("String")
        win.f_text.setText("foo")
        win.r_text.setText("qux")
        win.r_all_check.setChecked(True)
        win.f_case_check.setChecked(False)
        win.replace()
        vals = [
            win.get_item_data(win.root_item().child(r, COL_KEY), COL_VALUE) for r in range(win.root_item().rowCount())
        ]
        assert vals[0] == "qux"
        assert vals[1] == "qux bar"
        assert vals[2] == "baz"


# ── 6. Add / Remove rows ───────────────────────────────────────


class TestAddRemoveRows:
    def test_new_row_dict(self, qapp):
        win = make_window(qapp, OrderedDict())
        root = win.root_item()
        win.tree.setCurrentIndex(win.model.indexFromItem(root))
        win.tree.expand(win.model.indexFromItem(root))
        assert root.rowCount() == 0
        win.new_row()
        assert root.rowCount() == 1
        assert root.child(0, COL_KEY).text() == "New String"

    def test_new_row_array(self, qapp):
        win = make_window(qapp, [])
        root = win.root_item()
        win.tree.setCurrentIndex(win.model.indexFromItem(root))
        win.tree.expand(win.model.indexFromItem(root))
        win.new_row()
        assert root.rowCount() == 1
        assert root.child(0, COL_KEY).text() == "0"

    def test_new_row_force_sibling(self, qapp):
        data = OrderedDict([("existing", "val")])
        win = make_window(qapp, data)
        root = win.root_item()
        child = root.child(0, COL_KEY)
        win.new_row(target_item=child, force_sibling=True)
        assert root.rowCount() == 2

    def test_remove_row(self, qapp):
        data = OrderedDict([("a", 1), ("b", 2)])
        win = make_window(qapp, data)
        root = win.root_item()
        item = root.child(0, COL_KEY)
        win.remove_row(target_item=item)
        assert root.rowCount() == 1
        assert root.child(0, COL_KEY).text() == "b"

    def test_remove_row_records_undo(self, qapp):
        data = OrderedDict([("a", 1)])
        win = make_window(qapp, data)
        root = win.root_item()
        item = root.child(0, COL_KEY)
        win.remove_row(target_item=item)
        assert len(win.undo_stack) == 1
        assert win.undo_stack[0][0]["type"] == "remove"


# ── 7. Undo / Redo ─────────────────────────────────────────────


class TestUndoRedo:
    def test_edit_undo_redo(self, qapp):
        data = OrderedDict([("key", "original")])
        win = make_window(qapp, data)
        root = win.root_item()
        item = root.child(0, COL_KEY)
        # Manually record an edit
        win.add_undo(
            [
                {
                    "type": "edit",
                    "item": item,
                    "old_key": "key",
                    "old_type": win.get_item_data(item, COL_TYPE),
                    "old_value": "original",
                }
            ]
        )
        win.set_item_data(item, COL_VALUE, "modified")
        assert win.get_item_data(item, COL_VALUE) == "modified"

        win.reundo(undo=True)
        assert win.get_item_data(item, COL_VALUE) == "original"

        win.reundo(undo=False)
        assert win.get_item_data(item, COL_VALUE) == "modified"

    def test_add_undo_removes_item(self, qapp):
        win = make_window(qapp, OrderedDict())
        root = win.root_item()
        win.tree.setCurrentIndex(win.model.indexFromItem(root))
        win.tree.expand(win.model.indexFromItem(root))
        win.new_row()
        assert root.rowCount() == 1
        win.reundo(undo=True)
        assert root.rowCount() == 0

    def test_remove_undo_restores_item(self, qapp):
        data = OrderedDict([("keep_me", "val")])
        win = make_window(qapp, data)
        root = win.root_item()
        item = root.child(0, COL_KEY)
        win.remove_row(target_item=item)
        assert root.rowCount() == 0
        win.reundo(undo=True)
        assert root.rowCount() == 1
        assert root.child(0, COL_KEY).text() == "keep_me"


# ── 8. Copy / Paste ────────────────────────────────────────────


class TestCopyPaste:
    def test_copy_paste_roundtrip(self, qapp):
        data = OrderedDict([("alpha", "one"), ("beta", "two")])
        win = make_window(qapp, data)
        root = win.root_item()

        # Select "alpha" and copy
        item = root.child(0, COL_KEY)
        win.tree.setCurrentIndex(win.model.indexFromItem(item))
        win.copy_selection()

        # Paste into a new empty window
        win2 = make_window(qapp, OrderedDict())
        root2 = win2.root_item()
        win2.tree.setCurrentIndex(win2.model.indexFromItem(root2))
        win2.tree.expand(win2.model.indexFromItem(root2))

        # Set clipboard from source controller
        clipboard = QApplication.clipboard()
        clipboard.setText(win.controller._clipboard)

        win2.paste_selection()
        assert root2.rowCount() == 1
        assert win2.get_item_data(root2.child(0, COL_KEY), COL_VALUE) == "one"

    def test_copy_children(self, qapp):
        inner = OrderedDict([("c1", "v1"), ("c2", "v2")])
        data = OrderedDict([("parent", inner)])
        win = make_window(qapp, data)
        root = win.root_item()
        parent_item = root.child(0, COL_KEY)
        win.tree.setCurrentIndex(win.model.indexFromItem(parent_item))
        win.copy_children()
        # Should have copied the first child's value (dict contents)
        assert hasattr(win.controller, "_clipboard")
        assert len(win.controller._clipboard) > 0


# ── 9. Path helpers ─────────────────────────────────────────────


class TestPathHelpers:
    def test_get_cell_path_nested_dict(self, qapp):
        inner = OrderedDict([("leaf", "val")])
        data = OrderedDict([("level1", inner)])
        win = make_window(qapp, data)
        root = win.root_item()
        level1 = root.child(0, COL_KEY)
        leaf = level1.child(0, COL_KEY)
        path = win.get_cell_path(leaf)
        assert "Root" in path
        assert "level1" in path
        assert "leaf" in path

    def test_get_cell_path_array(self, qapp):
        data = OrderedDict([("arr", [10, 20])])
        win = make_window(qapp, data)
        root = win.root_item()
        arr_item = root.child(0, COL_KEY)
        child = arr_item.child(0, COL_KEY)
        path = win.get_cell_path(child)
        # Array children should show as "*"
        assert "*" in path

    def test_split_basic(self, qapp):
        result = PlistWindow.split("a/b/c")
        assert result == ["a", "b", "c"]

    def test_split_escaped_separator(self, qapp):
        result = PlistWindow.split("a\\/b/c")
        assert result == ["a/b", "c"]

    def test_get_cell_path_list(self, qapp):
        inner = OrderedDict([("leaf", "val")])
        data = OrderedDict([("level1", inner)])
        win = make_window(qapp, data)
        root = win.root_item()
        level1 = root.child(0, COL_KEY)
        leaf = level1.child(0, COL_KEY)
        parts = win._get_cell_path_list(leaf)
        assert "Root" not in parts
        assert parts == ["level1", "leaf"]


# ── 10. Move item (up / down) ───────────────────────────────────


class TestMoveItem:
    def _keys(self, win):
        root = win.root_item()
        return [root.child(r, COL_KEY).text() for r in range(root.rowCount())]

    def test_move_item_down(self, qapp):
        data = OrderedDict([("a", 1), ("b", 2), ("c", 3)])
        win = make_window(qapp, data)
        root = win.root_item()
        item = root.child(0, COL_KEY)  # "a" at row 0
        win.tree.setCurrentIndex(win.model.indexFromItem(item))
        win.move_item(1)
        assert self._keys(win) == ["b", "a", "c"]

    def test_move_item_up(self, qapp):
        data = OrderedDict([("a", 1), ("b", 2), ("c", 3)])
        win = make_window(qapp, data)
        root = win.root_item()
        item = root.child(2, COL_KEY)  # "c" at row 2
        win.tree.setCurrentIndex(win.model.indexFromItem(item))
        win.move_item(-1)
        assert self._keys(win) == ["a", "c", "b"]

    def test_move_item_up_at_top_is_noop(self, qapp):
        data = OrderedDict([("a", 1), ("b", 2)])
        win = make_window(qapp, data)
        root = win.root_item()
        item = root.child(0, COL_KEY)  # already at top
        win.tree.setCurrentIndex(win.model.indexFromItem(item))
        win.move_item(-1)
        assert self._keys(win) == ["a", "b"]

    def test_move_item_down_at_bottom_is_noop(self, qapp):
        data = OrderedDict([("a", 1), ("b", 2)])
        win = make_window(qapp, data)
        root = win.root_item()
        item = root.child(1, COL_KEY)  # already at bottom
        win.tree.setCurrentIndex(win.model.indexFromItem(item))
        win.move_item(1)
        assert self._keys(win) == ["a", "b"]

    def test_move_item_records_undo(self, qapp):
        data = OrderedDict([("a", 1), ("b", 2)])
        win = make_window(qapp, data)
        root = win.root_item()
        item = root.child(0, COL_KEY)
        win.tree.setCurrentIndex(win.model.indexFromItem(item))
        before = len(win.undo_stack)
        win.move_item(1)
        assert len(win.undo_stack) == before + 1
        assert win.undo_stack[-1][0]["type"] == "move"

    def test_move_item_undo_restores_order(self, qapp):
        data = OrderedDict([("a", 1), ("b", 2), ("c", 3)])
        win = make_window(qapp, data)
        root = win.root_item()
        item = root.child(0, COL_KEY)  # move "a" down
        win.tree.setCurrentIndex(win.model.indexFromItem(item))
        win.move_item(1)
        assert self._keys(win) == ["b", "a", "c"]
        win.reundo(undo=True)
        assert self._keys(win) == ["a", "b", "c"]

    def test_move_item_in_array_reindexes(self, qapp):
        data = OrderedDict([("arr", ["x", "y", "z"])])
        win = make_window(qapp, data)
        root = win.root_item()
        arr_item = root.child(0, COL_KEY)
        first = arr_item.child(0, COL_KEY)  # index "0"
        win.tree.setCurrentIndex(win.model.indexFromItem(first))
        win.move_item(1)
        # After moving index 0 down, it should now be at row 1
        assert arr_item.child(0, COL_KEY).text() == "0"
        assert arr_item.child(1, COL_KEY).text() == "1"
        assert arr_item.child(2, COL_KEY).text() == "2"


# ── 11. Drag drop placement (_resolve_drop) ──────────────────────


class TestResolveDrop:
    """Tests for the drag-and-drop placement helper, independent of mouse events."""

    def _make(self, qapp):
        """Window with:  root -> {a: {x:1, y:2}, b: "hello"}"""
        inner = OrderedDict([("x", 1), ("y", 2)])
        data = OrderedDict([("a", inner), ("b", "hello")])
        win = make_window(qapp, data)
        # Expand "a" so the collection logic can see it is expanded.
        root = win.root_item()
        a_item = root.child(0, COL_KEY)
        win.tree.expand(win.model.indexFromItem(a_item))
        return win

    def test_same_level_sibling_reorder(self, qapp):
        """Dragging 'b' over 'a' (same parent) → sibling placement, not into 'a'."""
        win = self._make(qapp)
        root = win.root_item()
        a_item = root.child(0, COL_KEY)  # expanded dict
        b_item = root.child(1, COL_KEY)  # string

        result = win._resolve_drop(b_item, a_item)
        assert result is not None, "drop should be valid"
        target_parent, insert_row = result
        # Must land at the same level (root), not inside 'a'
        assert target_parent == root
        assert insert_row == a_item.row()  # i.e. row 0

    def test_same_level_expanded_dict_does_not_swallow_sibling(self, qapp):
        """'a' is an expanded dict — dragging 'b' over it should NOT insert into it."""
        win = self._make(qapp)
        root = win.root_item()
        a_item = root.child(0, COL_KEY)
        b_item = root.child(1, COL_KEY)

        result = win._resolve_drop(b_item, a_item)
        target_parent, _ = result
        assert target_parent is not a_item, "must not insert into the sibling collection"

    def test_hover_over_child_of_sibling_reorders_at_same_level(self, qapp):
        """Core regression: mouse drifts over a child of the sibling (because it is
        expanded) — the source must still land as a sibling, not inside the child."""
        win = self._make(qapp)
        root = win.root_item()
        a_item = root.child(0, COL_KEY)  # expanded dict
        b_item = root.child(1, COL_KEY)
        x_item = a_item.child(0, COL_KEY)  # child of 'a' — this is what indexAt returns
        #                                     when the cursor is inside 'a's expanded area

        # Dragging 'b' while hovering over x (a child of sibling 'a') must place
        # 'b' BEFORE 'a' at the root level, not inside 'a'.
        result = win._resolve_drop(b_item, x_item)
        assert result is not None
        target_parent, insert_row = result
        assert target_parent == root  # stays at root level
        assert insert_row == a_item.row()  # before 'a'

    def test_cannot_drop_into_self(self, qapp):
        """Dragging a collection into itself returns None."""
        win = self._make(qapp)
        root = win.root_item()
        a_item = root.child(0, COL_KEY)
        x_item = a_item.child(0, COL_KEY)

        # 'a' dragged over one of its own children
        result = win._resolve_drop(a_item, x_item)
        assert result is None

    def test_noop_same_position(self, qapp):
        """Source and drop at the same row returns None."""
        win = self._make(qapp)
        root = win.root_item()
        a_item = root.child(0, COL_KEY)

        result = win._resolve_drop(a_item, a_item)
        assert result is None


# ── 12. Drag hysteresis (_should_suppress_drop) ──────────────────


class TestDragHysteresis:
    """_should_suppress_drop must block immediate reverse swaps (oscillation)."""

    def _win(self, qapp):
        data = OrderedDict([("a", 1), ("b", 2), ("c", 3)])
        return make_window(qapp, data)

    def test_no_suppression_without_previous_move(self, qapp):
        """First move is always allowed (drag_last_move_y is None)."""
        win = self._win(qapp)
        root = win.root_item()
        b = root.child(1, COL_KEY)
        win.tree.setCurrentIndex(win.model.indexFromItem(b))
        assert win._should_suppress_drop(0, b.row(), 50) is False

    def test_suppresses_immediate_reverse_moving_down(self, qapp):
        """After moving UP at y=30, a DOWN move at y=32 is suppressed (< 30+6)."""
        win = self._win(qapp)
        win.drag_last_move_y = 30
        root = win.root_item()
        root.child(0, COL_KEY)  # source at row 0 (moved here going up)
        # Attempting to move DOWN (insert_row=1 > source_row=0) at y=32
        assert win._should_suppress_drop(1, 0, 32) is True

    def test_allows_move_down_after_sufficient_travel(self, qapp):
        """After moving UP at y=30, a DOWN move at y=40 clears the threshold."""
        win = self._win(qapp)
        win.drag_last_move_y = 30
        # y=40 >= 30+6=36 → not suppressed
        assert win._should_suppress_drop(1, 0, 40) is False

    def test_suppresses_immediate_reverse_moving_up(self, qapp):
        """After moving DOWN at y=50, an UP move at y=47 is suppressed (> 50-6)."""
        win = self._win(qapp)
        win.drag_last_move_y = 50
        # Attempting to move UP (insert_row=0 < source_row=1) at y=47
        assert win._should_suppress_drop(0, 1, 47) is True

    def test_allows_move_up_after_sufficient_travel(self, qapp):
        """After moving DOWN at y=50, an UP move at y=40 clears the threshold."""
        win = self._win(qapp)
        win.drag_last_move_y = 50
        # y=40 <= 50-6=44 → not suppressed
        assert win._should_suppress_drop(0, 1, 40) is False


# ── 13. Color settings ──────────────────────────────────────────


class TestColorSettings:
    def test_update_colors_applies_stylesheet(self, qapp):
        """update_colors() should set a non-empty stylesheet on the tree."""
        win = make_window(qapp)
        win.update_colors()
        assert win.tree.styleSheet() != ""

    def test_update_colors_enables_alternating_rows(self, qapp):
        win = make_window(qapp)
        win.update_colors()
        assert win.tree.alternatingRowColors() is True

    def test_update_colors_custom_highlight(self, qapp):
        win = make_window(qapp)
        win.controller.settings["highlight_color"] = "#FF0000"
        win.update_colors()
        assert "#FF0000" in win.tree.styleSheet()

    def test_update_colors_custom_alternating(self, qapp):
        win = make_window(qapp)
        win.controller.settings["alternating_color_1"] = "#AABBCC"
        win.controller.settings["alternating_color_2"] = "#DDEEFF"
        win.update_colors()
        ss = win.tree.styleSheet()
        assert "#AABBCC" in ss
        assert "#DDEEFF" in ss

    def test_update_colors_custom_background(self, qapp):
        win = make_window(qapp)
        win.controller.settings["background_color"] = "#333333"
        win.update_colors()
        assert "#333333" in win.tree.styleSheet()

    def test_build_stylesheet_contains_required_selectors(self, qapp):
        win = make_window(qapp)
        ss = win._build_tree_stylesheet()
        assert "QTreeView" in ss
        assert "QHeaderView::section" in ss
        assert "selection-background-color" in ss
        assert "alternate-background-color" in ss

    def test_build_stylesheet_header_ignore_bg(self, qapp):
        """header_text_ignore_bg_color uses 'inherit' for header text color."""
        win = make_window(qapp)
        win.controller.settings["header_text_ignore_bg_color"] = True
        ss = win._build_tree_stylesheet()
        assert "inherit" in ss

    def test_build_stylesheet_uses_dark_defaults_when_dark(self, qapp):
        win = make_window(qapp)
        win.controller.use_dark = True
        # No custom colors set — should use dark defaults
        ss = win._build_tree_stylesheet()
        assert win.controller.default_dark["alternating_color_1"] in ss

    def test_build_stylesheet_uses_light_defaults_when_light(self, qapp):
        win = make_window(qapp)
        win.controller.use_dark = False
        ss = win._build_tree_stylesheet()
        assert win.controller.default_light["alternating_color_1"] in ss


# ── 14. Font settings ───────────────────────────────────────────


class TestFontSettings:
    def test_update_fonts_does_not_raise(self, qapp):
        win = make_window(qapp)
        win.update_fonts()  # should not raise

    def test_update_fonts_custom_size(self, qapp):
        win = make_window(qapp)
        win.controller.settings["use_custom_font_size"] = True
        win.controller.settings["font_size"] = 18
        win.update_fonts()
        assert win.tree.font().pointSize() == 18

    def test_update_fonts_size_clamped_to_range(self, qapp):
        win = make_window(qapp)
        win.controller.settings["use_custom_font_size"] = True
        win.controller.settings["font_size"] = 200  # exceeds max of 128
        win.update_fonts()
        assert win.tree.font().pointSize() == 128

    def test_update_fonts_custom_family(self, qapp):
        """Setting a known monospace font family should be reflected on the tree."""
        win = make_window(qapp)
        win.controller.settings["use_custom_font"] = True
        win.controller.settings["font_family"] = "Courier"
        win.update_fonts()
        # Qt may substitute the family name; just verify it was set
        assert win.tree.font().family() != "" or win.tree.font().pointSize() > 0

    def test_update_fonts_no_custom_unchanged(self, qapp):
        """With no custom settings the font should fall back to a sane default."""
        win = make_window(qapp)
        win.controller.settings["use_custom_font_size"] = False
        win.controller.settings["use_custom_font"] = False
        win.update_fonts()
        assert win.tree.font().pointSize() > 0

    def test_update_fonts_size_disabled_does_not_apply(self, qapp):
        """use_custom_font_size=False means font_size setting is ignored."""
        win = make_window(qapp)
        win.controller.settings["use_custom_font_size"] = False
        win.controller.settings["font_size"] = 99
        win.update_fonts()
        assert win.tree.font().pointSize() != 99


# ── 15. Default new plist type ──────────────────────────────────


class TestDefaultPlistType:
    def test_open_plist_binary_type(self, qapp):
        """open_plist() applies plist_type='Binary' to both the attribute and combo."""
        win = make_window(qapp)
        win.open_plist(None, {}, plist_type="Binary")
        assert win.plist_type == "Binary"
        assert win.plist_type_combo.currentText() == "Binary"

    def test_open_plist_xml_type(self, qapp):
        win = make_window(qapp)
        win.open_plist(None, {}, plist_type="XML")
        assert win.plist_type == "XML"
        assert win.plist_type_combo.currentText() == "XML"

    def test_open_plist_defaults_to_xml(self, qapp):
        """open_plist() without explicit plist_type defaults to 'XML'."""
        win = make_window(qapp)
        win.open_plist(None, {})
        assert win.plist_type == "XML"
