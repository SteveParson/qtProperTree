#!/usr/bin/env python
import base64
import binascii

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QDialog, QGridLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSizePolicy


class ConverterWindow(QDialog):
    ALLOWED_TYPES = ("Ascii", "Base64", "Decimal", "Hex", "Binary")

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Convert Values")
        self.setMinimumWidth(640)
        self._setup_ui()
        self._restore_settings()
        # Fix vertical size so the dialog is not resizable vertically
        self.adjustSize()
        self.setFixedHeight(self.sizeHint().height())

    def _setup_ui(self):
        layout = QGridLayout(self)

        # Row 0 - From
        from_label = QLabel("From:")
        self.f_combo = QComboBox()
        self.f_combo.addItems(self.ALLOWED_TYPES)
        self.f_combo.currentIndexChanged.connect(self._from_type_changed)
        self.f_text = QLineEdit()
        self.f_text.returnPressed.connect(self.convert_values)

        layout.addWidget(from_label, 0, 0)
        layout.addWidget(self.f_combo, 0, 1)
        layout.addWidget(self.f_text, 0, 2)

        # Row 1 - To
        to_label = QLabel("To:")
        self.t_combo = QComboBox()
        self.t_combo.addItems(self.ALLOWED_TYPES)
        self.t_combo.currentIndexChanged.connect(self._to_type_changed)
        self.t_text = QLineEdit()
        self.t_text.setReadOnly(True)

        layout.addWidget(to_label, 1, 0)
        layout.addWidget(self.t_combo, 1, 1)
        layout.addWidget(self.t_text, 1, 2)

        # Make the text fields stretch
        self.f_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.t_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Row 2 - Buttons
        self.s_button = QPushButton("To <--> From")
        self.s_button.clicked.connect(self.swap_convert)
        self.c_button = QPushButton("Convert")
        self.c_button.clicked.connect(self.convert_values)

        layout.addWidget(self.s_button, 2, 0, 1, 2)
        layout.addWidget(self.c_button, 2, 2, alignment=Qt.AlignRight)

        layout.setColumnStretch(2, 1)

    def _restore_settings(self):
        if self.controller is not None:
            settings = getattr(self.controller, "settings", {})
            conv_f = settings.get("convert_from_type", self.ALLOWED_TYPES[1])
            if conv_f not in self.ALLOWED_TYPES:
                conv_f = self.ALLOWED_TYPES[1]
            conv_t = settings.get("convert_to_type", self.ALLOWED_TYPES[-1])
            if conv_t not in self.ALLOWED_TYPES:
                conv_t = self.ALLOWED_TYPES[-1]
            self.f_combo.setCurrentText(conv_f)
            self.t_combo.setCurrentText(conv_t)
        else:
            self.f_combo.setCurrentText(self.ALLOWED_TYPES[1])
            self.t_combo.setCurrentText(self.ALLOWED_TYPES[-1])

    def _from_type_changed(self):
        if self.controller is not None:
            settings = getattr(self.controller, "settings", None)
            if settings is not None:
                settings["convert_from_type"] = self.f_combo.currentText()

    def _to_type_changed(self):
        if self.controller is not None:
            settings = getattr(self.controller, "settings", None)
            if settings is not None:
                settings["convert_to_type"] = self.t_combo.currentText()
        self.convert_values()

    def swap_convert(self):
        t_type = self.t_combo.currentText()
        f_type = self.f_combo.currentText()
        to_text = self.t_text.text()
        # Update settings
        if self.controller is not None:
            settings = getattr(self.controller, "settings", None)
            if settings is not None:
                settings["convert_to_type"] = f_type
                settings["convert_from_type"] = t_type
        # Block signals while swapping to avoid triggering intermediate converts
        self.f_combo.blockSignals(True)
        self.t_combo.blockSignals(True)
        self.f_combo.setCurrentText(t_type)
        self.t_combo.setCurrentText(f_type)
        self.f_combo.blockSignals(False)
        self.t_combo.blockSignals(False)
        # Move To text into From field
        self.f_text.setText(to_text)
        self.convert_values()

    def convert_values(self):
        from_value = self.f_text.text()
        if not from_value:
            return
        from_type = self.f_combo.currentText().lower()
        to_type = self.t_combo.currentText().lower()

        if from_type == "hex":
            if from_value.lower().startswith("0x"):
                from_value = from_value[2:]
            from_value = from_value.replace(" ", "").replace("<", "").replace(">", "")
            if [x for x in from_value if x.lower() not in "0123456789abcdef"]:
                QMessageBox.critical(self, "Invalid Hex Data", "Invalid character in passed hex data.")
                return
        try:
            if from_type in ("decimal", "binary"):
                from_value = "".join(from_value.split())
                from_value = "{:x}".format(int(from_value, 10 if from_type == "decimal" else 2))
                if len(from_value) % 2:
                    from_value = "0" + from_value

            if from_type == "base64":
                padded_from = from_value
                from_stripped = from_value.rstrip("=")
                if len(from_stripped) % 4 > 1:
                    padded_from = from_stripped + "=" * (4 - len(from_stripped) % 4)
                if padded_from != from_value:
                    from_value = padded_from
                    self.f_text.setText(from_value)
                from_value = base64.b64decode(from_value.encode("utf-8"))
            elif from_type in ("hex", "decimal", "binary"):
                if len(from_value) % 2:
                    from_value = "0" + from_value
                    if to_type not in ("hex", "decimal"):
                        self.f_text.setText(from_value)
                from_value = binascii.unhexlify(from_value.encode("utf-8"))

            to_value = from_value if isinstance(from_value, bytes) else from_value.encode("utf-8")
            if to_type == "base64":
                to_value = base64.b64encode(to_value).decode("utf-8")
            elif to_type == "hex":
                to_value = binascii.hexlify(to_value).decode("utf-8")
            elif to_type == "decimal":
                to_value = str(int(binascii.hexlify(to_value).decode("utf-8"), 16))
            elif to_type == "binary":
                to_value = "{:b}".format(int(binascii.hexlify(to_value).decode("utf-8"), 16))
            else:
                to_value = to_value.decode("utf-8") if isinstance(to_value, bytes) else to_value

            if to_type == "hex":
                to_value = " ".join((to_value[0 + i : 8 + i] for i in range(0, len(to_value), 8))).upper()

            self.t_text.setText(str(to_value))
        except Exception as e:
            self.t_text.setText("")
            QMessageBox.critical(self, "Conversion Error", str(e))

    def showEvent(self, event):
        super().showEvent(event)
        self.f_text.setFocus()
