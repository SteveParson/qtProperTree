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
