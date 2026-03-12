"""
Tab: Sensors (Мониторинг).

Displays a live table of sensor readings updated every second.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from server.core.mahm_reader import MAHMReader


class TabSensors(QWidget):
    def __init__(self, mahm_reader: MAHMReader, parent=None) -> None:
        super().__init__(parent)
        self._reader = mahm_reader
        self._setup_ui()
        self._start_timer()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        if self._reader.is_mock():
            mock_label = QLabel(
                "Режим разработки: данные mock (MAHM недоступен на этой платформе)"
            )
            mock_label.setStyleSheet("color: orange;")
            layout.addWidget(mock_label)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Датчик", "Значение", "Единица"])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table)

    # ------------------------------------------------------------------
    # Timer
    # ------------------------------------------------------------------

    def _start_timer(self) -> None:
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh()  # initial fill

    def _refresh(self) -> None:
        sensors = self._reader.read_all()
        self._table.setRowCount(len(sensors))

        for row, (key, entry) in enumerate(sensors.items()):
            label_item = QTableWidgetItem(entry.label or key)
            label_item.setData(Qt.ItemDataRole.UserRole, key)

            value_item = QTableWidgetItem(f"{entry.value:.1f}")
            value_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )

            unit_item = QTableWidgetItem(entry.unit)

            self._table.setItem(row, 0, label_item)
            self._table.setItem(row, 1, value_item)
            self._table.setItem(row, 2, unit_item)

    def stop(self) -> None:
        self._timer.stop()
