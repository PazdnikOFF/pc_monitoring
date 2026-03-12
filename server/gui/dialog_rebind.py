"""
RebindDialog — confirmation dialog shown when binding a device
that is already claimed by another PC.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)


class RebindDialog(QDialog):
    """
    Ask the user whether they want to force-rebind a device.

    Usage::

        dlg = RebindDialog(device_id="ESP_001", pc_name="GAMING-PC", parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # user confirmed
    """

    def __init__(
        self,
        device_id: str,
        pc_name: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Перепривязка устройства")
        self.setModal(True)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        info_label = QLabel(
            f"Устройство <b>{device_id}</b> уже привязано к ПК:<br>"
            f"<b>{pc_name}</b>"
        )
        info_label.setTextFormat(Qt.TextFormat.RichText)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        question_label = QLabel("Подтвердить привязку к <b>этому ПК</b>?")
        question_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(question_label)

        buttons = QDialogButtonBox(parent=self)
        self._cancel_btn = buttons.addButton(
            "Отмена", QDialogButtonBox.ButtonRole.RejectRole
        )
        self._confirm_btn = buttons.addButton(
            "Подтвердить привязку", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self._confirm_btn.setDefault(True)

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
