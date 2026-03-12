"""
Tab: Network (Сеть).

Shows server IP addresses, port, and connected WebSocket clients.
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path
from typing import Set

from PyQt6.QtCore import QProcess, QTimer
from PyQt6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from server.api.websocket import get_active_connections


def _get_local_ips() -> list[str]:
    """Return all non-loopback IPv4 addresses of this host."""
    ips = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            addr = info[4][0]
            if ":" not in addr and addr != "127.0.0.1":
                if addr not in ips:
                    ips.append(addr)
    except OSError:
        pass
    if not ips:
        ips.append("127.0.0.1")
    return ips


class TabNetwork(QWidget):
    def __init__(self, config: dict, on_port_change=None, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self._on_port_change = on_port_change
        self._setup_ui()
        self._start_timer()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Server info group
        info_group = QGroupBox("Адреса сервера")
        info_layout = QVBoxLayout(info_group)

        ips = _get_local_ips()
        port = self._config.get("port", 8080)

        for ip in ips:
            lbl = QLabel(f"http://{ip}:{port}")
            lbl.setTextInteractionFlags(lbl.textInteractionFlags() | lbl.textInteractionFlags().TextSelectableByMouse)
            info_layout.addWidget(lbl)

        layout.addWidget(info_group)

        # Port editor group
        port_group = QGroupBox("Настройки")
        port_layout = QHBoxLayout(port_group)

        port_layout.addWidget(QLabel("HTTP/WS порт:"))
        self._port_spin = QSpinBox()
        self._port_spin.setRange(1024, 65535)
        self._port_spin.setValue(port)
        port_layout.addWidget(self._port_spin)

        apply_btn = QPushButton("Применить")
        apply_btn.clicked.connect(self._on_apply_port)
        port_layout.addWidget(apply_btn)
        port_layout.addStretch()

        self._restart_hint = QLabel("")
        self._restart_hint.setStyleSheet("color: orange;")
        port_layout.addWidget(self._restart_hint)

        layout.addWidget(port_group)

        # WebSocket clients group
        ws_group = QGroupBox("Подключённые WebSocket клиенты")
        ws_layout = QVBoxLayout(ws_group)

        self._ws_list = QListWidget()
        ws_layout.addWidget(self._ws_list)

        self._ws_count_lbl = QLabel("Клиентов: 0")
        ws_layout.addWidget(self._ws_count_lbl)

        layout.addWidget(ws_group)

        # Build EXE group
        build_group = QGroupBox("Сборка EXE")
        build_layout = QVBoxLayout(build_group)

        btn_row = QHBoxLayout()
        self._build_btn = QPushButton("Собрать EXE (PyInstaller)")
        self._build_btn.clicked.connect(self._on_build_exe)
        btn_row.addWidget(self._build_btn)

        self._launch_btn = QPushButton("Запустить EXE")
        self._launch_btn.setEnabled(False)
        self._launch_btn.clicked.connect(self._on_launch_exe)
        btn_row.addWidget(self._launch_btn)
        build_layout.addLayout(btn_row)

        self._build_output = QTextEdit()
        self._build_output.setReadOnly(True)
        self._build_output.setFixedHeight(130)
        self._build_output.setFontFamily("Courier New")
        build_layout.addWidget(self._build_output)

        layout.addWidget(build_group)
        layout.addStretch()

    # ------------------------------------------------------------------
    # Timer
    # ------------------------------------------------------------------

    def _start_timer(self) -> None:
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._refresh_clients)
        self._timer.start()
        self._refresh_clients()

    def _refresh_clients(self) -> None:
        conns = get_active_connections()
        self._ws_list.clear()
        for ws in conns:
            client = ws.client
            if client:
                self._ws_list.addItem(f"{client.host}:{client.port}")
            else:
                self._ws_list.addItem("unknown")
        self._ws_count_lbl.setText(f"Клиентов: {len(conns)}")

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_apply_port(self) -> None:
        new_port = self._port_spin.value()
        if new_port != self._config.get("port"):
            self._config["port"] = new_port
            self._config["ws_port"] = new_port
            self._restart_hint.setText("Перезапустите сервер для применения порта")
            if self._on_port_change:
                self._on_port_change(new_port)

    # ------------------------------------------------------------------
    # Build / Launch EXE
    # ------------------------------------------------------------------

    def _on_build_exe(self) -> None:
        project_root = Path(__file__).resolve().parent.parent.parent
        main_script = project_root / "server" / "main.py"
        data_src = project_root / "server" / "data"
        sep = ";" if sys.platform == "win32" else ":"

        self._build_output.clear()
        self._build_btn.setEnabled(False)
        self._launch_btn.setEnabled(False)
        self._build_output.append(f"Сборка из {main_script} …\n")

        args = [
            "-m", "PyInstaller",
            "--onefile",
            "--windowed",
            "--name", "PCMonitoringServer",
            f"--add-data={data_src}{sep}server/data",
            str(main_script),
        ]

        self._build_proc = QProcess(self)
        self._build_proc.setWorkingDirectory(str(project_root))
        self._build_proc.readyReadStandardOutput.connect(self._on_build_stdout)
        self._build_proc.readyReadStandardError.connect(self._on_build_stderr)
        self._build_proc.finished.connect(self._on_build_finished)
        self._build_proc.start(sys.executable, args)

    def _on_build_stdout(self) -> None:
        text = self._build_proc.readAllStandardOutput().data().decode("utf-8", errors="replace")
        self._build_output.append(text.rstrip())

    def _on_build_stderr(self) -> None:
        text = self._build_proc.readAllStandardError().data().decode("utf-8", errors="replace")
        self._build_output.append(text.rstrip())

    def _on_build_finished(self, exit_code: int, _status) -> None:
        self._build_btn.setEnabled(True)
        if exit_code == 0:
            self._build_output.append("\n✓ Сборка завершена успешно")
            self._launch_btn.setEnabled(True)
        else:
            self._build_output.append(f"\n✗ Ошибка сборки (код {exit_code})")

    def _on_launch_exe(self) -> None:
        project_root = Path(__file__).resolve().parent.parent.parent
        exe = project_root / "dist" / "PCMonitoringServer.exe"
        if not exe.exists():
            self._build_output.append(f"EXE не найден: {exe}")
            return
        QProcess.startDetached(str(exe), [])

    def stop(self) -> None:
        self._timer.stop()
