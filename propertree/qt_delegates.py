import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLineEdit, QStyledItemDelegate

# Column indices in the model
COL_KEY = 0
COL_TYPE = 1
COL_VALUE = 2

MENU_CODE = "\u21d5"


class PlistItemDelegate(QStyledItemDelegate):
    """Delegate for inline editing of plist tree items.

    Handles:
    - Key editing (column 0) for dict children
    - Type selection popup (column 1)
    - Value editing (column 2) with validation
    - Boolean toggle and type menus via popup
    """

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window

    def createEditor(self, parent, option, index):
        col = index.column()
        if col == COL_TYPE:
            # Type column - show popup menu instead of editor
            return None
        item = self.window.item_from_index(index)
        if item is None:
            return None

        if col == COL_KEY:
            # Check if parent is an array - can't edit array keys
            parent_item = item.parent()
            if parent_item is not None:
                parent_type = self.window.get_check_type_from_item(parent_item)
                if parent_type == "array":
                    return None
            elif item == self.window.root_item():
                # Can't edit Root key if it's a collection
                root_type = self.window.get_check_type_from_item(item)
                if root_type in ("dictionary", "array"):
                    return None

        if col == COL_VALUE:
            node_type = self.window.get_check_type_from_item(item)
            if node_type in ("dictionary", "array"):
                return None  # Can't edit collection values
            if node_type == "boolean":
                return None  # Handled by popup

        editor = QLineEdit(parent)
        editor.setFrame(False)
        return editor

    def setEditorData(self, editor, index):
        if isinstance(editor, QLineEdit):
            col = index.column()
            value = index.data(Qt.DisplayRole) or ""
            if col == COL_VALUE:
                item = self.window.item_from_index(index)
                if item is not None:
                    node_type = self.window.get_check_type_from_item(item)
                    if node_type == "data":
                        # Strip angle brackets for editing
                        value = value.replace("<", "").replace(">", "")
            editor.setText(str(value))
            editor.selectAll()

    def setModelData(self, editor, model, index):
        if not isinstance(editor, QLineEdit):
            return
        col = index.column()
        value = editor.text()
        item = self.window.item_from_index(index)
        if item is None:
            return

        if col == COL_KEY:
            # Validate unique key name
            parent_item = item.parent()
            if parent_item is None:
                parent_item = model.invisibleRootItem()
            for row in range(parent_item.rowCount()):
                sibling = parent_item.child(row, COL_KEY)
                if sibling is not None and sibling is not item and sibling.text() == value:
                    from PySide6.QtWidgets import QMessageBox

                    QApplication.beep()
                    QMessageBox.warning(self.window, "Invalid Key Name", "That key name already exists in that dict.")
                    return
            old_text = item.text()
            if value != old_text:
                self.window.add_undo(
                    [
                        {
                            "type": "edit",
                            "item": item,
                            "old_key": old_text,
                            "old_type": self.window.get_item_data(item, COL_TYPE),
                            "old_value": self.window.get_item_data(item, COL_VALUE),
                        }
                    ]
                )
                item.setText(value)
                self.window.mark_edited()

        elif col == COL_VALUE:
            node_type = self.window.get_check_type_from_item(item)
            # Handle "today"/"now" for dates
            if node_type == "date" and value.lower() in ("today", "now"):
                value = datetime.datetime.now().strftime("%b %d, %Y %I:%M:%S %p")
            # Validate
            result = self.window.qualify_value(value, node_type)
            if result[0] is False:
                from PySide6.QtWidgets import QMessageBox

                QApplication.beep()
                QMessageBox.warning(self.window, result[1], result[2])
                return
            value = result[1]
            old_value = self.window.get_item_data(item, COL_VALUE)
            if value != old_value:
                self.window.add_undo(
                    [
                        {
                            "type": "edit",
                            "item": item,
                            "old_key": item.text(),
                            "old_type": self.window.get_item_data(item, COL_TYPE),
                            "old_value": old_value,
                        }
                    ]
                )
                type_item = item.parent()
                if type_item is None:
                    type_item = self.window.model.invisibleRootItem()
                row = item.row()
                value_item = type_item.child(row, COL_VALUE)
                if value_item is not None:
                    value_item.setText(str(value))
                self.window.mark_edited()

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)
