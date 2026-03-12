"""
Tab: Devices (Устройства).

Shows discovered and bound devices, handles binding / unbinding.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from server.core.binding import BindingManager
from server.core.discovery import DiscoveredDevice, DiscoveryService
from server.gui.dialog_rebind import RebindDialog


def _fmt_ts(ts: float) -> str:
    if ts == 0:
        return "—"
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


class TabDevices(QWidget):
    # Signals emitted from background threads — must be connected to Qt slots
    _sig_device_found = pyqtSignal(object)
    _sig_device_lost = pyqtSignal(str)

    def __init__(
        self,
        discovery: DiscoveryService,
        binding: BindingManager,
        config: dict,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._discovery = discovery
        self._binding = binding
        self._config = config

        # Wire signals for thread-safe GUI updates
        self._sig_device_found.connect(self._on_device_found)
        self._sig_device_lost.connect(self._on_device_lost)
        discovery.on_device_found = lambda d: self._sig_device_found.emit(d)
        discovery.on_device_lost = lambda did: self._sig_device_lost.emit(did)

        self._setup_ui()

        # Periodic refresh of bound devices table
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(5000)
        self._refresh_timer.timeout.connect(self._refresh_bound_table)
        self._refresh_timer.start()
        self._refresh_bound_table()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Discovered devices group
        disc_group = QGroupBox("Обнаруженные устройства в сети")
        disc_v = QVBoxLayout(disc_group)

        self._disc_table = QTableWidget(0, 5)
        self._disc_table.setHorizontalHeaderLabels(
            ["ID", "MAC", "Дисплей", "Статус", "Действие"]
        )
        self._disc_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self._disc_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._disc_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self._disc_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        self._disc_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents
        )
        self._disc_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._disc_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        disc_v.addWidget(self._disc_table)

        scan_btn = QPushButton("Найти устройства")
        scan_btn.clicked.connect(self._on_scan)
        disc_v.addWidget(scan_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(disc_group)

        # Bound devices group
        bound_group = QGroupBox("Привязанные устройства")
        bound_v = QVBoxLayout(bound_group)

        self._bound_table = QTableWidget(0, 5)
        self._bound_table.setHorizontalHeaderLabels(
            ["ID", "Псевдоним", "Шаблон", "Последний онлайн", "Действие"]
        )
        self._bound_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self._bound_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self._bound_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self._bound_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self._bound_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents
        )
        self._bound_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._bound_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        bound_v.addWidget(self._bound_table)

        layout.addWidget(bound_group)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_scan(self) -> None:
        self._discovery.scan()

    def _on_device_found(self, device: DiscoveredDevice) -> None:
        self._refresh_discovered_table()

    def _on_device_lost(self, device_id: str) -> None:
        self._refresh_discovered_table()

    def _refresh_discovered_table(self) -> None:
        devices = self._discovery.get_all_devices()
        self._disc_table.setRowCount(len(devices))

        my_pc_id = self._config.get("pc_id", "")

        for row, dev in enumerate(devices):
            bound_pc_id = dev.bound_pc_id

            if not bound_pc_id:
                status = "Свободно"
                btn_text = "Привязать"
                btn_style = ""
            elif bound_pc_id == my_pc_id:
                status = "Привязано (этот ПК)"
                btn_text = "Привязано"
                btn_style = "color: green;"
            else:
                status = f"Привязано ({dev.bound_to or bound_pc_id})"
                btn_text = "Перепривязать"
                btn_style = "color: orange;"

            self._disc_table.setItem(row, 0, QTableWidgetItem(dev.device_id))
            self._disc_table.setItem(row, 1, QTableWidgetItem(dev.mac))
            self._disc_table.setItem(row, 2, QTableWidgetItem(dev.display))
            self._disc_table.setItem(row, 3, QTableWidgetItem(status))

            action_btn = QPushButton(btn_text)
            action_btn.setStyleSheet(btn_style)

            # Capture variables for the lambda
            _dev = dev
            _is_rebind = bool(bound_pc_id and bound_pc_id != my_pc_id)
            action_btn.clicked.connect(
                lambda checked, d=_dev, rebind=_is_rebind: self._on_action(d, rebind)
            )
            self._disc_table.setCellWidget(row, 4, action_btn)

    def _refresh_bound_table(self) -> None:
        devices = self._binding.get_all_devices()
        self._bound_table.setRowCount(len(devices))

        for row, dev in enumerate(devices):
            self._bound_table.setItem(row, 0, QTableWidgetItem(dev.device_id))
            self._bound_table.setItem(row, 1, QTableWidgetItem(dev.alias or "—"))
            self._bound_table.setItem(row, 2, QTableWidgetItem(dev.active_template or "—"))
            self._bound_table.setItem(row, 3, QTableWidgetItem(_fmt_ts(dev.last_seen)))

            unbind_btn = QPushButton("Отвязать")
            _dev = dev
            unbind_btn.clicked.connect(
                lambda checked, d=_dev: self._on_unbind(d.device_id)
            )
            self._bound_table.setCellWidget(row, 4, unbind_btn)

    def _on_action(self, dev: DiscoveredDevice, is_rebind: bool) -> None:
        my_pc_id = self._config.get("pc_id", "")
        my_pc_name = self._config.get("pc_name", "этот ПК")

        if is_rebind:
            dlg = RebindDialog(
                device_id=dev.device_id,
                pc_name=dev.bound_to or dev.bound_pc_id,
                parent=self,
            )
            if dlg.exec() != dlg.DialogCode.Accepted:
                return
            self._discovery.send_bind_command(
                ip=dev.ip,
                device_id=dev.device_id,
                pc_id=my_pc_id,
                pc_name=my_pc_name,
                force=True,
            )
        else:
            self._discovery.send_bind_command(
                ip=dev.ip,
                device_id=dev.device_id,
                pc_id=my_pc_id,
                pc_name=my_pc_name,
            )

        self._binding.bind(
            device_id=dev.device_id,
            mac=dev.mac,
            display=dev.display,
        )
        self._refresh_bound_table()

    def _on_unbind(self, device_id: str) -> None:
        reply = QMessageBox.question(
            self,
            "Отвязать устройство",
            f"Отвязать устройство {device_id}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        discovered = self._discovery.get_device(device_id)
        if discovered:
            self._discovery.send_unbind_command(ip=discovered.ip, device_id=device_id)
        self._binding.unbind(device_id)
        self._refresh_bound_table()

    def stop(self) -> None:
        self._refresh_timer.stop()
