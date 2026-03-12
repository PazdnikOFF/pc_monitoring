"""
Tab: Templates (Шаблоны).

Allows creating, editing and deleting display templates.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from server.core.mahm_reader import MAHMReader
from server.paths import TEMPLATES_DIR

_TEMPLATES_DIR = TEMPLATES_DIR
_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------
# Page editor widget
# ------------------------------------------------------------------

class _PageWidget(QGroupBox):
    """Editor for a single template page."""

    def __init__(self, sensor_keys: List[str], page_data: Optional[Dict] = None, parent=None):
        super().__init__(parent)
        self._sensor_keys = sensor_keys
        self._setup_ui(page_data or {})

    def _setup_ui(self, page_data: Dict) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self._duration_spin = QSpinBox()
        self._duration_spin.setRange(1, 3600)
        self._duration_spin.setValue(page_data.get("duration_s", 5))
        form.addRow("Длительность (с):", self._duration_spin)
        layout.addLayout(form)

        layout.addWidget(QLabel("Датчики (по одному на строку):"))

        self._rows_edit = QListWidget()
        self._rows_edit.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        for key in self._sensor_keys:
            item = QListWidgetItem(key)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if key in page_data.get("rows", []):
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            self._rows_edit.addItem(item)

        self._rows_edit.setMaximumHeight(120)
        layout.addWidget(self._rows_edit)

    def get_data(self) -> Dict:
        rows = []
        for i in range(self._rows_edit.count()):
            item = self._rows_edit.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                rows.append(item.text())
        return {
            "duration_s": self._duration_spin.value(),
            "rows": rows,
        }


# ------------------------------------------------------------------
# Main tab widget
# ------------------------------------------------------------------

class TabTemplates(QWidget):
    def __init__(self, mahm_reader: MAHMReader, parent=None) -> None:
        super().__init__(parent)
        self._reader = mahm_reader
        self._current_name: Optional[str] = None
        self._page_widgets: List[_PageWidget] = []
        self._setup_ui()
        self._refresh_list()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(splitter)

        # --- Left panel: template list ---
        left = QWidget()
        left_layout = QVBoxLayout(left)

        self._list_widget = QListWidget()
        self._list_widget.currentTextChanged.connect(self._on_template_selected)
        left_layout.addWidget(self._list_widget)

        btn_row = QHBoxLayout()
        self._btn_new = QPushButton("Новый")
        self._btn_new.clicked.connect(self._on_new)
        self._btn_delete = QPushButton("Удалить")
        self._btn_delete.clicked.connect(self._on_delete)
        btn_row.addWidget(self._btn_new)
        btn_row.addWidget(self._btn_delete)
        left_layout.addLayout(btn_row)

        splitter.addWidget(left)

        # --- Right panel: editor ---
        right = QWidget()
        self._right_layout = QVBoxLayout(right)

        form = QFormLayout()
        self._name_edit = QLineEdit()
        form.addRow("Название:", self._name_edit)
        self._refresh_spin = QSpinBox()
        self._refresh_spin.setRange(100, 60000)
        self._refresh_spin.setSingleStep(100)
        self._refresh_spin.setValue(1000)
        self._refresh_spin.setSuffix(" мс")
        form.addRow("Обновление:", self._refresh_spin)
        self._right_layout.addLayout(form)

        self._right_layout.addWidget(QLabel("Страницы:"))

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        self._pages_container = QWidget()
        self._pages_layout = QVBoxLayout(self._pages_container)
        self._pages_layout.addStretch()
        scroll_area.setWidget(self._pages_container)
        self._right_layout.addWidget(scroll_area)

        pages_btn_row = QHBoxLayout()
        self._btn_add_page = QPushButton("+ Страница")
        self._btn_add_page.clicked.connect(self._add_page)
        self._btn_save = QPushButton("Сохранить")
        self._btn_save.clicked.connect(self._on_save)
        self._btn_save.setDefault(True)
        pages_btn_row.addWidget(self._btn_add_page)
        pages_btn_row.addStretch()
        pages_btn_row.addWidget(self._btn_save)
        self._right_layout.addLayout(pages_btn_row)

        splitter.addWidget(right)
        splitter.setSizes([200, 500])

    # ------------------------------------------------------------------
    # Template list
    # ------------------------------------------------------------------

    def _refresh_list(self) -> None:
        self._list_widget.blockSignals(True)
        self._list_widget.clear()
        for p in sorted(_TEMPLATES_DIR.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                self._list_widget.addItem(data.get("name", p.stem))
            except (json.JSONDecodeError, OSError):
                pass
        self._list_widget.blockSignals(False)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _sensor_keys(self) -> List[str]:
        return list(self._reader.read_all().keys())

    def _on_template_selected(self, name: str) -> None:
        if not name:
            return
        self._current_name = name
        safe = "".join(c for c in name if c.isalnum() or c in ("-", "_", " "))
        p = _TEMPLATES_DIR / f"{safe}.json"
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return

        self._name_edit.setText(data.get("name", ""))
        self._refresh_spin.setValue(data.get("refresh_ms", 1000))
        self._clear_pages()
        for page in data.get("pages", []):
            self._add_page(page)

    def _on_new(self) -> None:
        name, ok = QInputDialog.getText(self, "Новый шаблон", "Название:")
        if not ok or not name.strip():
            return
        self._current_name = None
        self._name_edit.setText(name.strip())
        self._refresh_spin.setValue(1000)
        self._clear_pages()
        self._add_page()

    def _on_delete(self) -> None:
        name = self._list_widget.currentItem()
        if not name:
            return
        template_name = name.text()
        reply = QMessageBox.question(
            self,
            "Удалить шаблон",
            f"Удалить шаблон '{template_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        safe = "".join(c for c in template_name if c.isalnum() or c in ("-", "_", " "))
        p = _TEMPLATES_DIR / f"{safe}.json"
        if p.exists():
            p.unlink()
        self._refresh_list()
        self._clear_pages()
        self._name_edit.clear()

    def _add_page(self, page_data: Optional[Dict] = None) -> None:
        pw = _PageWidget(self._sensor_keys(), page_data, self)
        pw.setTitle(f"Страница {len(self._page_widgets) + 1}")
        # Insert before stretch
        self._pages_layout.insertWidget(
            self._pages_layout.count() - 1, pw
        )
        self._page_widgets.append(pw)

    def _clear_pages(self) -> None:
        for pw in self._page_widgets:
            self._pages_layout.removeWidget(pw)
            pw.deleteLater()
        self._page_widgets.clear()

    def _on_save(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Ошибка", "Введите название шаблона.")
            return

        pages = [pw.get_data() for pw in self._page_widgets]
        data = {
            "name": name,
            "refresh_ms": self._refresh_spin.value(),
            "pages": pages,
        }
        safe = "".join(c for c in name if c.isalnum() or c in ("-", "_", " "))
        p = _TEMPLATES_DIR / f"{safe}.json"
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        self._refresh_list()

        # Select the saved template
        for i in range(self._list_widget.count()):
            if self._list_widget.item(i).text() == name:
                self._list_widget.setCurrentRow(i)
                break

        QMessageBox.information(self, "Сохранено", f"Шаблон '{name}' сохранён.")
