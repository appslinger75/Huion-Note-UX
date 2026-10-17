from __future__ import annotations

import asyncio
import hashlib
import csv
import json
import math
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unicodedata
from string import Template
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from PySide6.QtCore import (
    QBuffer, QByteArray, QIODevice, QLocale, QPointF, QRectF, QSize, Qt, QSettings, QTimer, QUrl, Signal,
)
from PySide6.QtGui import (
    QAction, QColor, QCloseEvent, QDesktopServices, QFontDatabase, QIcon, QImage, QKeySequence, QPainter,
    QPainterPath, QPalette, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QProgressBar,
    QPushButton, QScrollArea, QSpinBox, QSplitter, QStackedWidget, QTabWidget, QTableWidget,
    QTableWidgetItem, QTextEdit, QToolButton, QVBoxLayout, QWidget,
)
try:  # Los iconos vectoriales son opcionales: sin QtSvg la aplicación funciona igual, solo con texto.
    from PySide6.QtSvg import QSvgRenderer
except ImportError:  # pragma: no cover
    QSvgRenderer = None
from qasync import QEventLoop

APP_NAME = "Huion Note Sync"
APP_VERSION = "3.0.0"
ORG_NAME = "HuionNoteTools"

SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
COMMAND_UUID = "0000ffe2-0000-1000-8000-00805f9b34fb"

OP_HEARTBEAT = 0x80
OP_VERIFY_CONNECT = 0x81
OP_VERIFY_RESULT = 0x82
OP_MODE = 0x84
OP_CURRENT_PAGE = 0x85
OP_REQUEST_OFFLINE_DATA = 0x86
OP_RETURN_OFFLINE_DATA = 0x87
OP_GET_PAGE_PACKAGE = 0x88
OP_NEXT_PAGE = 0x8A
OP_ONLINE_DATA = 0x8D
OP_BATTERY = 0x8E
OP_MAX_DATA = 0x95
OP_VERSION = 0xC9

DEFAULT_MAX_X = 28200
DEFAULT_MAX_Y = 37400
DEFAULT_MAX_PRESSURE = 8191
PAGE_WIDTH = 794
PAGE_HEIGHT = 1123
LIVE_PAGE_BASE = 10000  # las páginas guardadas desde la escucha pasiva se numeran a partir de aquí



def page_dimensions(max_x: int, max_y: int, width: int = PAGE_WIDTH) -> tuple[int, int]:
    """Tamaño de exportación que conserva la proporción real del área activa del dispositivo."""
    return width, max(1, round(width * max(1, max_y) / max(1, max_x)))

# --------------------------------------------------------------------------------------------------
# Temas (claro / oscuro) definidos con «tokens» de diseño en un solo sitio
# --------------------------------------------------------------------------------------------------
THEMES = {
    "oscuro": dict(
        bg="#0b0d10", surface="#141820", surface2="#1e2530", surface3="#263040", border="#283548",
        border_soft="#1e2530", text="#e2e8f0", strong="#ffffff", muted="#8c9bae", faint="#4a5568",
        accent="#2563eb", accent_hover="#1d4ed8", accent_border="#3b82f6", on_accent="#ffffff",
        danger="#dc2626", danger_hover="#b91c1c", danger_border="#ef4444",
        input="#07090c", canvas_bg="#07090c", selection="#1d3a6e", scroll="#324055",
        nav_hover="#171c25", nav_checked="#1b2a47", chip_bg="#1a2230",
        ok_bg="#064e3b", ok_fg="#34d399", ok_bd="#059669",
        warn_bg="#78350f", warn_fg="#fbbf24", warn_bd="#d97706",
        bad_bg="#7f1d1d", bad_fg="#f87171", bad_bd="#dc2626",
        crit_bg="#991b1b", crit_fg="#fca5a5", crit_bd="#ef4444",
        toast_bg="#1e2530", toast_fg="#f1f5f9",
    ),
    "claro": dict(
        bg="#f3f5f8", surface="#ffffff", surface2="#eef1f5", surface3="#e3e8ee", border="#cfd6df",
        border_soft="#e1e6ec", text="#1c2533", strong="#0b1220", muted="#5b6b7e", faint="#a3afbd",
        accent="#2563eb", accent_hover="#1d4ed8", accent_border="#2563eb", on_accent="#ffffff",
        danger="#dc2626", danger_hover="#b91c1c", danger_border="#dc2626",
        input="#ffffff", canvas_bg="#e6eaf0", selection="#cfe0ff", scroll="#c3ccd8",
        nav_hover="#e8edf3", nav_checked="#dbe7ff", chip_bg="#eef1f5",
        ok_bg="#dcfce7", ok_fg="#166534", ok_bd="#86efac",
        warn_bg="#fef3c7", warn_fg="#92400e", warn_bd="#fcd34d",
        bad_bg="#fee2e2", bad_fg="#991b1b", bad_bd="#fca5a5",
        crit_bg="#fecaca", crit_fg="#7f1d1d", crit_bd="#f87171",
        toast_bg="#1e2530", toast_fg="#f1f5f9",
    ),
}

STYLE_TEMPLATE = Template("""
QMainWindow, QWidget { background: $bg; color: $text; font-size: 13px; }
QLabel, QCheckBox, QRadioButton { background: transparent; }
QToolTip { background: $surface2; color: $text; border: 1px solid $border; padding: 4px 8px; }

QFrame#card { background: $surface; border: 1px solid $border_soft; border-radius: 14px; }
QFrame#sidebar { background: $surface; border: none; border-right: 1px solid $border_soft; border-radius: 0; }
QFrame#footer { background: $surface; border: 1px solid $border_soft; border-radius: 10px; }
QFrame#banner { background: $warn_bg; border: 1px solid $warn_bd; border-radius: 10px; }
QFrame#banner QLabel { color: $warn_fg; font-weight: 500; }

QLabel#brand { font-size: 16px; font-weight: 700; color: $strong; }
QLabel#title { font-size: 20px; font-weight: 700; color: $strong; }
QLabel#subtitle { color: $muted; font-size: 12px; }
QLabel#section { font-size: 14px; font-weight: 600; color: $strong; }
QLabel#toast { background: $toast_bg; color: $toast_fg; border: 1px solid $border; border-radius: 10px; font-weight: 500; }
QLabel#toast[kind="error"] { border: 1px solid $bad_bd; background: $bad_bg; color: $bad_fg; }
QLabel#toast[kind="warn"] { border: 1px solid $warn_bd; background: $warn_bg; color: $warn_fg; }
QLabel#toast[kind="ok"] { border: 1px solid $ok_bd; background: $ok_bg; color: $ok_fg; }

QLabel#connected { background: $ok_bg; color: $ok_fg; border: 1px solid $ok_bd; border-radius: 10px; padding: 5px 12px; font-weight: 600; }
QLabel#busy { background: $warn_bg; color: $warn_fg; border: 1px solid $warn_bd; border-radius: 10px; padding: 5px 12px; font-weight: 600; }
QLabel#disconnected { background: $bad_bg; color: $bad_fg; border: 1px solid $bad_bd; border-radius: 10px; padding: 5px 12px; font-weight: 600; }
QLabel#battery_normal { background: $chip_bg; color: $ok_fg; border: 1px solid $border; border-radius: 10px; padding: 5px 10px; font-weight: 600; }
QLabel#battery_warning { background: $warn_bg; color: $warn_fg; border: 1px solid $warn_bd; border-radius: 10px; padding: 5px 10px; font-weight: 600; }
QLabel#battery_critical { background: $crit_bg; color: $crit_fg; border: 1px solid $crit_bd; border-radius: 10px; padding: 5px 10px; font-weight: 700; }

QPushButton { background: $surface2; border: 1px solid $border; border-radius: 8px; padding: 7px 14px; color: $text; font-weight: 500; }
QPushButton:hover { background: $surface3; }
QPushButton:pressed { background: $border_soft; }
QPushButton:disabled { color: $faint; background: $surface; border-color: $border_soft; }
QPushButton#primary { background: $accent; border-color: $accent_border; color: $on_accent; font-weight: 600; }
QPushButton#primary:hover { background: $accent_hover; }
QPushButton#primary:disabled { background: $surface2; color: $faint; border-color: $border_soft; }
QPushButton#danger { background: $danger; border-color: $danger_border; color: #ffffff; font-weight: 600; }
QPushButton#danger:hover { background: $danger_hover; }
QPushButton#toggle:checked { background: $ok_bg; color: $ok_fg; border-color: $ok_bd; font-weight: 600; }
QPushButton#icon { padding: 5px 0; min-width: 32px; max-width: 32px; font-size: 16px; font-weight: 600; }
QPushButton#nav { background: transparent; border: none; border-radius: 8px; padding: 9px 12px; text-align: left; color: $muted; font-weight: 500; }
QPushButton#nav:hover { background: $nav_hover; color: $text; }
QPushButton#nav:checked { background: $nav_checked; color: $strong; font-weight: 600; }
QToolButton#more { background: $surface2; border: 1px solid $border; border-radius: 8px; padding: 7px 12px; color: $text; font-weight: 500; }
QToolButton#more:hover { background: $surface3; }
QToolButton#more::menu-indicator { subcontrol-position: right center; subcontrol-origin: padding; right: 4px; }

QLineEdit, QSpinBox, QComboBox { background: $input; border: 1px solid $border; border-radius: 8px; padding: 6px 10px; color: $text; selection-background-color: $selection; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus { border: 1px solid $accent_border; }
QComboBox QAbstractItemView { background: $surface; color: $text; border: 1px solid $border; selection-background-color: $nav_checked; selection-color: $strong; }
QTextEdit { background: $input; border: 1px solid $border_soft; border-radius: 10px; color: $text; padding: 8px; selection-background-color: $selection; }

QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid $border; background: $input; }
QCheckBox::indicator:checked { background: $accent; border-color: $accent_border; }

QListWidget { background: $input; border: 1px solid $border_soft; border-radius: 10px; padding: 4px; outline: none; }
QListWidget::item { border-radius: 8px; padding: 6px; color: $muted; }
QListWidget::item:hover { background: $nav_hover; }
QListWidget::item:selected { background: $nav_checked; color: $strong; }

QTableWidget { background: $input; border: 1px solid $border_soft; border-radius: 10px; gridline-color: $border_soft; alternate-background-color: $surface; selection-background-color: $nav_checked; selection-color: $strong; }
QHeaderView::section { background: $surface2; color: $muted; border: none; border-bottom: 1px solid $border_soft; padding: 7px 8px; font-weight: 600; }

QTabWidget::pane { border: 1px solid $border_soft; border-radius: 10px; background: $surface; top: -1px; }
QTabBar::tab { background: transparent; border: none; padding: 9px 16px; color: $muted; font-weight: 500; }
QTabBar::tab:selected { color: $strong; border-bottom: 2px solid $accent_border; font-weight: 600; }
QTabBar::tab:hover { color: $text; }

QProgressBar { background: $input; border: 1px solid $border_soft; border-radius: 7px; text-align: center; height: 16px; color: $text; font-weight: 600; font-size: 11px; }
QProgressBar::chunk { background: $accent; border-radius: 6px; }

QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: $scroll; border-radius: 5px; min-height: 30px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: $scroll; border-radius: 5px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QSplitter::handle { background: transparent; }

QMenu { background: $surface; border: 1px solid $border; border-radius: 8px; padding: 6px; }
QMenu::item { padding: 7px 24px; border-radius: 6px; color: $text; }
QMenu::item:selected { background: $nav_checked; color: $strong; }
QMenu::item:disabled { color: $faint; }
QMenu::separator { height: 1px; background: $border_soft; margin: 6px 4px; }
QMenuBar { background: $bg; color: $text; }
QMenuBar::item { padding: 5px 10px; background: transparent; }
QMenuBar::item:selected { background: $nav_checked; border-radius: 6px; }
""")


def build_stylesheet(name: str) -> str:
    return STYLE_TEMPLATE.substitute(THEMES[name])


_SYSTEM_THEME_AT_START = "oscuro"


def detect_system_theme() -> str:
    """Tema del sistema operativo (claro u oscuro), igual en Windows y macOS."""
    app = QApplication.instance()
    try:
        scheme = app.styleHints().colorScheme()  # Qt >= 6.5
        if scheme == Qt.ColorScheme.Dark:
            return "oscuro"
        if scheme == Qt.ColorScheme.Light:
            return "claro"
    except Exception:
        pass
    return _SYSTEM_THEME_AT_START


# --------------------------------------------------------------------------------------------------
# Iconos vectoriales (SVG propio, mismos en Windows y macOS)
# --------------------------------------------------------------------------------------------------
ICON_PATHS = {
    "notes": '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5"/><path d="M10 13h6M10 17h6"/>',
    "measure": '<path d="M4 20V11M10 20V5M16 20v-6M22 20H2"/>',
    "history": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "settings": '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
    "advanced": '<path d="M4 6l6 6-6 6"/><path d="M12 18h8"/>',
}


def _icon_pixmap(name: str, color: str, size: int) -> Optional[QPixmap]:
    if QSvgRenderer is None or name not in ICON_PATHS:
        return None
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="%s" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">%s</svg>' % (color, ICON_PATHS[name])
    )
    ratio = 2  # el doble de resolución para que se vea nítido en pantallas HiDPI/Retina
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(size * ratio, size * ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def make_nav_icon(name: str, off_color: str, on_color: str, size: int = 20) -> QIcon:
    icon = QIcon()
    try:
        off = _icon_pixmap(name, off_color, size)
        on = _icon_pixmap(name, on_color, size)
        if off is not None and on is not None:
            icon.addPixmap(off, QIcon.Mode.Normal, QIcon.State.Off)
            icon.addPixmap(on, QIcon.Mode.Normal, QIcon.State.On)
    except Exception:
        return QIcon()
    return icon


def make_thumbnail(points: list, max_x: int, max_y: int, width: int = 84) -> QIcon:
    """Miniatura de una página para la lista lateral."""
    max_x, max_y = max(1, max_x), max(1, max_y)
    height = max(1, round(width * max_y / max_x))
    ratio = 2
    image = QImage(width * ratio, height * ratio, QImage.Format.Format_ARGB32)
    image.fill(QColor("#f7f7f4"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#111318"), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    scale = width * ratio / max_x
    for stroke in Protocol.strokes(points, max_x, max_y):
        path = QPainterPath()
        path.moveTo(QPointF(stroke[0].x * scale, stroke[0].y * scale))
        if len(stroke) == 1:
            path.lineTo(QPointF(stroke[0].x * scale + 0.1, stroke[0].y * scale + 0.1))
        for point in stroke[1:]:
            path.lineTo(QPointF(point.x * scale, point.y * scale))
        painter.drawPath(path)
    painter.end()
    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(ratio)
    return QIcon(pixmap)


class Toast(QLabel):
    """Aviso flotante no intrusivo (sustituye a las ventanas emergentes)."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setWordWrap(True)
        self.setContentsMargins(14, 10, 14, 10)
        self.hide()
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)

    def show_message(self, text: str, kind: str = "info", duration: int = 4500):
        self.setProperty("kind", kind)
        self.style().unpolish(self)
        self.style().polish(self)
        self.setText(text)
        self.reposition()
        self.show()
        self.raise_()
        self.timer.start(duration)

    def reposition(self):
        parent = self.parentWidget()
        if parent is None:
            return
        width = max(260, min(440, parent.width() // 3))
        self.setFixedWidth(width)
        self.setFixedHeight(max(40, self.heightForWidth(width)))
        self.move(max(0, parent.width() - width - 28), max(0, parent.height() - self.height() - 70))

    def mousePressEvent(self, event):
        self.hide()


@dataclass
class PenPoint:
    x: int
    y: int
    pressure: int
    down: bool
    timestamp: float
    status: int = 0


@dataclass
class InputDeviceInfo:
    name: str
    vendor_id: str = ""
    product_id: str = ""
    transport: str = ""
    usage_page: str = ""
    usage: str = ""
    registry_id: str = ""
    source: str = ""
    is_huion_note: bool = False


class InputDeviceScanner:
    @staticmethod
    def _is_huion(text: str) -> bool:
        normalized = text.lower().replace("_", " ").replace("-", " ")
        return "huion" in normalized and ("note" in normalized or "t218" in normalized)

    @classmethod
    def scan(cls) -> list[InputDeviceInfo]:
        if platform.system() == "Darwin":
            return cls._scan_macos()
        if platform.system() == "Windows":
            return cls._scan_windows()
        return []

    @staticmethod
    def _format_id(value) -> str:
        if value in (None, ""):
            return ""
        try:
            number = int(value)
            return f"0x{number:04X} ({number})"
        except (TypeError, ValueError):
            return str(value)

    @classmethod
    def _scan_macos(cls) -> list[InputDeviceInfo]:
        import plistlib

        result = subprocess.run(
            ["ioreg", "-a", "-r", "-c", "IOHIDDevice"],
            capture_output=True,
            timeout=8,
            check=False,
        )
        if result.returncode != 0 or not result.stdout:
            return []

        entries = plistlib.loads(result.stdout)
        devices: list[InputDeviceInfo] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = str(
                entry.get("Product")
                or entry.get("Product Name")
                or entry.get("IOHIDProduct")
                or entry.get("USB Product Name")
                or entry.get("IORegistryEntryName")
                or "Dispositivo HID sin nombre"
            )
            searchable = " ".join(str(value) for value in entry.values())
            devices.append(InputDeviceInfo(
                name=name,
                vendor_id=cls._format_id(entry.get("VendorID", entry.get("idVendor", ""))),
                product_id=cls._format_id(entry.get("ProductID", entry.get("idProduct", ""))),
                transport=str(entry.get("Transport", entry.get("IOHIDTransport", ""))),
                usage_page=cls._format_id(entry.get("PrimaryUsagePage", entry.get("DeviceUsagePage", ""))),
                usage=cls._format_id(entry.get("PrimaryUsage", entry.get("DeviceUsage", ""))),
                registry_id=str(entry.get("LocationID", entry.get("RegistryID", ""))),
                source="IORegistry, solo lectura",
                is_huion_note=cls._is_huion(name + " " + searchable),
            ))
        return cls._deduplicate(devices)

    @classmethod
    def _scan_windows(cls) -> list[InputDeviceInfo]:
        import re

        powershell = (
            "$items=Get-PnpDevice -PresentOnly | Where-Object {"
            "$_.Class -in @('HIDClass','Mouse','Keyboard','Bluetooth')};"
            "$items | Select-Object FriendlyName,InstanceId,Class,Status,Manufacturer | "
            "ConvertTo-Json -Depth 3 -Compress"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", powershell],
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
        if not result.stdout.strip():
            return []
        parsed = json.loads(result.stdout)
        entries = parsed if isinstance(parsed, list) else [parsed]
        devices: list[InputDeviceInfo] = []
        for entry in entries:
            name = str(entry.get("FriendlyName") or "Dispositivo PnP sin nombre")
            instance = str(entry.get("InstanceId") or "")
            vendor_match = re.search(r"VID[_&]([0-9A-F]{4})", instance, re.I)
            product_match = re.search(r"PID[_&]([0-9A-F]{4})", instance, re.I)
            searchable = " ".join(str(value) for value in entry.values())
            devices.append(InputDeviceInfo(
                name=name,
                vendor_id=f"0x{vendor_match.group(1).upper()}" if vendor_match else "",
                product_id=f"0x{product_match.group(1).upper()}" if product_match else "",
                transport="Bluetooth" if "BTH" in instance.upper() else str(entry.get("Class") or ""),
                registry_id=instance,
                source="Windows PnP, solo lectura",
                is_huion_note=cls._is_huion(name + " " + searchable),
            ))
        return cls._deduplicate(devices)

    @staticmethod
    def _deduplicate(devices: list[InputDeviceInfo]) -> list[InputDeviceInfo]:
        unique: dict[tuple, InputDeviceInfo] = {}
        for device in devices:
            key = (
                device.name.lower(), device.vendor_id, device.product_id,
                device.transport, device.usage_page, device.usage,
            )
            if key not in unique or device.is_huion_note:
                unique[key] = device
        return sorted(unique.values(), key=lambda item: (not item.is_huion_note, item.name.lower()))


class PageStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS pages(
                device_id TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                logical_page INTEGER NOT NULL,
                saved_at TEXT NOT NULL,
                json_path TEXT NOT NULL,
                svg_path TEXT NOT NULL,
                png_path TEXT NOT NULL,
                PRIMARY KEY(device_id, content_hash)
            )
        """)
        # Los puntos de cada página se guardan en la base de datos (no en un archivo JSON exportado),
        # para poder mostrar las páginas en la vista previa al reiniciar la aplicación.
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(pages)")}
        if "points_json" not in columns:
            self.db.execute("ALTER TABLE pages ADD COLUMN points_json TEXT NOT NULL DEFAULT ''")
        self.db.commit()

    def exists(self, device_id: str, digest: str) -> bool:
        return self.db.execute(
            "SELECT 1 FROM pages WHERE device_id=? AND content_hash=?",
            (device_id, digest),
        ).fetchone() is not None

    def page_exists(self, device_id: str, logical_page: int) -> bool:
        return self.db.execute(
            "SELECT 1 FROM pages WHERE device_id=? AND logical_page=?",
            (device_id, logical_page),
        ).fetchone() is not None

    def add(self, device_id: str, digest: str, page: int, png_path: Path, points_json: str) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO pages(device_id, content_hash, logical_page, saved_at, json_path, svg_path, "
            "png_path, points_json) VALUES(?,?,?,?,?,?,?,?)",
            (device_id, digest, page, datetime.now().isoformat(), "", "", str(png_path), points_json),
        )
        self.db.commit()

    def png_path_for(self, digest: str) -> Optional[str]:
        row = self.db.execute(
            "SELECT png_path FROM pages WHERE content_hash=? AND png_path<>'' ORDER BY saved_at DESC LIMIT 1",
            (digest,),
        ).fetchone()
        return row[0] if row else None

    def count(self) -> int:
        return int(self.db.execute("SELECT COUNT(*) FROM pages").fetchone()[0])

    def history(self) -> list[tuple]:
        return self.db.execute(
            "SELECT logical_page,saved_at,png_path,content_hash FROM pages ORDER BY logical_page ASC LIMIT 200"
        ).fetchall()

    def clear(self) -> None:
        self.db.execute("DELETE FROM pages")
        self.db.commit()

    def close(self) -> None:
        self.db.close()


class Protocol:
    def __init__(self):
        self.max_x = DEFAULT_MAX_X
        self.max_y = DEFAULT_MAX_Y
        self.max_pressure = DEFAULT_MAX_PRESSURE

    @staticmethod
    def command(opcode: int, *args: int) -> bytes:
        values = list(args[:4]) + [0] * (4 - len(args[:4]))
        return bytes([0xCD, opcode & 0xFF, 0x08, *[v & 0xFF for v in values], 0xED])

    @staticmethod
    def frame(data: bytes) -> Optional[tuple[int, bytes]]:
        if len(data) < 3 or data[0] != 0xCD:
            return None
        length = data[2]
        if length > len(data):
            return None
        return data[1], data[:length]

    @staticmethod
    def verify_reply(challenge: bytes) -> bytes:
        if len(challenge) < 6:
            raise RuntimeError("Reto de autenticación incompleto")
        a, b, c = challenge[3], challenge[4], challenge[5]
        return Protocol.command(
            OP_VERIFY_RESULT,
            ((a + b) << 2) % 255,
            ((b + c) << 2) % 255,
            ((c + 10) << 2) % 255,
            0,
        )

    def parse_limits(self, frame: bytes) -> None:
        if len(frame) < 11:
            return
        x = frame[3] | (frame[4] << 8) | (frame[5] << 16)
        y = frame[6] | (frame[7] << 8) | (frame[8] << 16)
        pressure = frame[9] | (frame[10] << 8)
        if 1000 <= x <= 100000:
            self.max_x = x
        if 1000 <= y <= 100000:
            self.max_y = y
        if 255 <= pressure <= 65535:
            self.max_pressure = pressure

    @staticmethod
    def u16(frame: bytes, offset: int = 3) -> int:
        return frame[offset] | (frame[offset + 1] << 8) if len(frame) > offset + 1 else 0

    def points(self, frame: bytes) -> list[PenPoint]:
        if len(frame) < 11:
            return []
        payload = frame[5:]
        # Cada punto ocupa 6 bytes; el resto (normalmente el byte final 0xED) se descarta.
        payload = payload[:len(payload) - (len(payload) % 6)]
        # Se usan los límites reales del dispositivo (con un pequeño margen), no los valores por defecto.
        limit_x = int(max(self.max_x, DEFAULT_MAX_X) * 1.05)
        limit_y = int(max(self.max_y, DEFAULT_MAX_Y) * 1.05)
        result: list[PenPoint] = []
        now = time.time()
        for index in range(0, len(payload), 6):
            chunk = payload[index:index + 6]
            if chunk == b"\x00\x00\x00\x00\x00\x00":
                continue
            x = chunk[0] | (chunk[1] << 8)
            y = chunk[2] | (chunk[3] << 8)
            pressure = chunk[4] | ((chunk[5] & 0x1F) << 8)
            status = (chunk[5] >> 5) & 0x07
            if x == 0 and y == 0 and pressure == 0:
                continue
            if not (0 <= x <= limit_x and 0 <= y <= limit_y):
                continue
            result.append(PenPoint(x, y, pressure, status == 1 and pressure > 0, now, status))
        return result

    @staticmethod
    def strokes(points: list[PenPoint], max_x: int = DEFAULT_MAX_X, max_y: int = DEFAULT_MAX_Y) -> list[list[PenPoint]]:
        """Agrupa los puntos en trazos. Debe recibir SIEMPRE los puntos originales (con su estado de
        lápiz), nunca trazos ya normalizados, o se pierden las separaciones entre trazos."""
        limit_x = int(max(max_x, DEFAULT_MAX_X) * 1.05)
        limit_y = int(max(max_y, DEFAULT_MAX_Y) * 1.05)
        useful = [
            point for point in points
            if not (point.x == 0 and point.y == 0 and point.pressure == 0)
            and 0 <= point.x <= limit_x
            and 0 <= point.y <= limit_y
        ]
        # Si el dispositivo informa del estado "lápiz apoyado", se usa para separar trazos.
        # Si ningún punto lo trae, se recurre únicamente a la presión.
        use_status = any(point.down for point in useful)
        result: list[list[PenPoint]] = []
        current: list[PenPoint] = []
        jump_limit = max(max_x, DEFAULT_MAX_X) * 0.06
        for point in useful:
            touching = point.down if use_status else point.pressure > 0
            if not touching:
                if current:
                    result.append(current)
                    current = []
                continue
            normalized = PenPoint(point.x, point.y, max(1, point.pressure), True, point.timestamp, point.status)
            if current:
                previous = current[-1]
                distance = ((normalized.x - previous.x) ** 2 + (normalized.y - previous.y) ** 2) ** 0.5
                if distance > jump_limit:
                    result.append(current)
                    current = []
                elif normalized.x == previous.x and normalized.y == previous.y:
                    continue
            current.append(normalized)
        if current:
            result.append(current)
        return result


class BleManager:
    def __init__(self, log, state, live, battery):
        self.log = log
        self.state = state
        self.live = live
        self.battery_cb = battery
        self.protocol = Protocol()
        self.device: Optional[BLEDevice] = None
        self.client: Optional[BleakClient] = None
        self.device_id = ""
        self.device_name = ""
        self.firmware = ""
        self.queues: dict[int, asyncio.Queue[bytes]] = {}
        self.write_lock = asyncio.Lock()
        self.sync_lock = asyncio.Lock()
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.command_response = False
        self.io_paused = False
        self.online_enabled = False
        self.cancel_sync = False
        self.debug_frames = False
        self.debug_left = 0

    @property
    def connected(self) -> bool:
        return bool(self.client and self.client.is_connected)

    def queue(self, opcode: int) -> asyncio.Queue[bytes]:
        return self.queues.setdefault(opcode, asyncio.Queue())

    def clear_queue(self, opcode: int) -> None:
        queue = self.queue(opcode)
        while not queue.empty():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def wait(self, opcode: int, timeout: float = 8.0) -> bytes:
        return await asyncio.wait_for(self.queue(opcode).get(), timeout)

    async def scan(self) -> None:
        self.state("Buscando")
        self.log("Buscando Huion Note...")
        found = await BleakScanner.discover(timeout=8.0, return_adv=True)
        candidates: list[tuple[int, BLEDevice]] = []
        for device, advertisement in found.values():
            name = f"{device.name or ''} {advertisement.local_name or ''}".lower()
            services = [item.lower() for item in (advertisement.service_uuids or [])]
            score = 100 if "huion note" in name else 70 if "huion" in name else 50 if "t218" in name else 0
            if SERVICE_UUID in services or any("ffe0" in item for item in services):
                score += 40
            if score:
                candidates.append((score, device))
        if not candidates:
            self.state("Desconectado")
            raise RuntimeError("No se encontró el Huion Note. Enciéndelo y cierra la aplicación oficial.")
        candidates.sort(key=lambda item: item[0], reverse=True)
        self.device = candidates[0][1]
        self.device_id = self.device.address
        self.device_name = self.device.name or "Huion Note"
        self.log(f"Encontrado: {self.device_name} ({self.device_id})")

    async def connect(self) -> None:
        if self.connected:
            return
        if not self.device:
            await self.scan()
        self.state("Conectando")
        self.client = BleakClient(self.device, disconnected_callback=self._disconnected, timeout=20)
        await self.client.connect()
        available = {
            char.uuid.lower(): char
            for service in self.client.services
            for char in service.characteristics
        }
        if COMMAND_UUID not in available or NOTIFY_UUID not in available:
            raise RuntimeError("El dispositivo no expone FFE1/FFE2")
        await self.client.start_notify(NOTIFY_UUID, self._notify)
        command_props = {p.lower() for p in available[COMMAND_UUID].properties}
        if {"notify", "indicate"} & command_props:
            await self.client.start_notify(COMMAND_UUID, self._notify)
        self.command_response = "write" in command_props and "write-without-response" not in command_props
        await asyncio.sleep(0.8)
        await self._authenticate()
        await self._read_info()
        self.online_enabled = False
        self.state("Conectado")
        self.log("Conectado correctamente")
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _authenticate(self) -> None:
        challenge: Optional[bytes] = None
        command = Protocol.command(OP_VERIFY_CONNECT)
        for attempt in range(1, 4):
            self.clear_queue(OP_VERIFY_CONNECT)
            await self.send(command)
            try:
                challenge = await self.wait(OP_VERIFY_CONNECT, 4)
                break
            except asyncio.TimeoutError:
                await asyncio.sleep(0.6)
        if challenge is None:
            raise asyncio.TimeoutError("No se recibió VERIFY_CONNECT 0x81")
        self.clear_queue(OP_VERIFY_RESULT)
        await self.send(Protocol.verify_reply(challenge))
        result = await self.wait(OP_VERIFY_RESULT, 8)
        if len(result) < 4 or result[3] == 0:
            raise RuntimeError("Autenticación rechazada")

    async def _read_info(self) -> None:
        try:
            self.clear_queue(OP_MAX_DATA)
            await self.send(Protocol.command(OP_MAX_DATA))
            frame = await self.wait(OP_MAX_DATA, 4)
            self.protocol.parse_limits(frame)
        except Exception:
            pass
        try:
            self.clear_queue(OP_VERSION)
            await self.send(Protocol.command(OP_VERSION))
            frame = await self.wait(OP_VERSION, 4)
            self.firmware = frame[3:].rstrip(b"\xed\x00").decode(errors="ignore")
        except Exception:
            self.firmware = "No disponible"
        try:
            await self.send(Protocol.command(OP_BATTERY))
        except Exception:
            pass

    async def send(self, data: bytes) -> None:
        if not self.connected:
            raise RuntimeError("Dispositivo desconectado")
        async with self.write_lock:
            await self.client.write_gatt_char(COMMAND_UUID, data, response=self.command_response)
            await asyncio.sleep(0.08)

    def _notify(self, characteristic, data: bytearray) -> None:
        raw = bytes(data)
        parsed = Protocol.frame(raw)

        if self.debug_frames and self.debug_left > 0:
            self.debug_left -= 1
            note = "" if parsed else "  (descartada: cabecera/longitud no válida)"
            self.log(f"RX [{len(raw)}] {raw.hex(' ')}{note}")

        if not parsed:
            return
        opcode, frame = parsed

        # IMPORTANTE: las respuestas a los comandos (página actual, cabecera y paquetes de datos
        # offline...) deben llegar SIEMPRE a su cola, también mientras se sincroniza. Antes se
        # descartaban todas las notificaciones durante la sincronización y por eso nunca llegaban datos.
        if opcode == OP_ONLINE_DATA:
            # Datos en directo: solo se procesan si la escucha está activa y no hay sincronización.
            if self.online_enabled and not self.io_paused and not self.sync_lock.locked():
                points = self.protocol.points(frame)
                if points:
                    self.live(points)
            return
        if opcode == OP_NEXT_PAGE:
            if not self.sync_lock.locked():
                self.live(None)
            return
        if opcode == OP_BATTERY:
            if len(frame) > 3 and frame[3] <= 100:
                self.battery_cb(frame[3])
            return
        if opcode == OP_HEARTBEAT:
            return
        self.queue(opcode).put_nowait(frame)

    async def enable_online_mode(self) -> None:
        self.online_enabled = True
        if self.debug_frames:
            self.debug_left = 150

    async def disable_online_mode(self) -> None:
        self.online_enabled = False

    async def _heartbeat_loop(self) -> None:
        try:
            while self.connected:
                await asyncio.sleep(8)
                if self.io_paused or self.sync_lock.locked():
                    continue
                await self.send(Protocol.command(OP_HEARTBEAT))
        except asyncio.CancelledError:
            return
        except Exception:
            pass

    def _disconnected(self, _client) -> None:
        self.client = None
        self.online_enabled = False
        self.state("Desconectado")

    async def disconnect(self) -> None:
        self.online_enabled = False
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        self.heartbeat_task = None
        if self.client and self.client.is_connected:
            try:
                await self.client.disconnect()
            except Exception:
                pass
        self.client = None
        self.state("Desconectado")

    async def page_count(self) -> int:
        command = Protocol.command(OP_CURRENT_PAGE)
        for attempt in range(1, 4):
            self.clear_queue(OP_CURRENT_PAGE)
            await self.send(command)
            try:
                return Protocol.u16(await self.wait(OP_CURRENT_PAGE, 5))
            except asyncio.TimeoutError:
                pass
        return 20

    async def _download_page_once(self, page: int, progress) -> tuple[list[PenPoint], bool]:
        """Descarga una página. Devuelve (puntos, completa)."""
        self.clear_queue(OP_REQUEST_OFFLINE_DATA)
        self.clear_queue(OP_RETURN_OFFLINE_DATA)
        low, high = page & 255, (page >> 8) & 255
        await self.send(Protocol.command(OP_REQUEST_OFFLINE_DATA, low, high))
        try:
            header = await self.wait(OP_REQUEST_OFFLINE_DATA, 4.0)
        except asyncio.TimeoutError:
            return [], True  # sin respuesta: página vacía
        expected = Protocol.u16(header)
        if expected <= 0:
            return [], True

        packets: dict[int, bytes] = {}
        deadline = time.monotonic() + max(25, expected * 0.3)
        while len(packets) < expected and time.monotonic() < deadline:
            if self.cancel_sync:
                break
            try:
                frame = await self.wait(OP_RETURN_OFFLINE_DATA, 5)
            except asyncio.TimeoutError:
                break
            sequence = Protocol.u16(frame)
            # Se acepta numeración que empiece en 0 o en 1 para no perder el primer paquete.
            if 0 <= sequence <= expected and sequence not in packets:
                packets[sequence] = frame
            progress(len(packets), expected)

        points: list[PenPoint] = []
        for sequence in sorted(packets):
            points.extend(self.protocol.points(packets[sequence]))
        return points, len(packets) >= expected

    async def download_page(self, page: int, progress, attempts: int = 3) -> list[PenPoint]:
        """Descarga una página reintentando si faltan paquetes (pérdidas típicas de BLE)."""
        best: list[PenPoint] = []
        for attempt in range(1, attempts + 1):
            if self.cancel_sync or not self.connected:
                break
            points, complete = await self._download_page_once(page, progress)
            if complete:
                return points
            if len(points) > len(best):
                best = points
            if attempt < attempts:
                self.log(f"Página {page}: transferencia incompleta, reintentando ({attempt}/{attempts - 1})...")
                await asyncio.sleep(0.5)
        if best:
            self.log(f"Página {page}: se guarda el contenido parcial recibido ({len(best)} puntos).")
        return best

    async def synchronize(self, max_pages: int, page_callback, progress_callback, page_store: PageStore,
                          device_id: str, skip_saved: bool = False) -> tuple[int, int]:
        async with self.sync_lock:
            was_online = self.online_enabled
            self.io_paused = True
            self.online_enabled = False
            self.cancel_sync = False
            if self.debug_frames:
                self.debug_left = 150
            try:
                await asyncio.sleep(0.15)
                current_page = await self.page_count()
                self.log(f"Páginas informadas por el dispositivo: {current_page}")
                scan_limit = max_pages
                # Estimación del total para el progreso: el dispositivo informa de su página actual.
                estimate = scan_limit if current_page <= 0 else min(scan_limit, current_page + 1)
                checked = 0
                nonempty = 0
                consecutive_empty = 0

                for page in range(scan_limit):
                    if self.cancel_sync:
                        self.log("Sincronización detenida de forma segura por el usuario.")
                        break
                    if not self.connected:
                        raise RuntimeError("Se perdió la conexión con el Huion Note durante la sincronización")

                    if page + 1 > estimate:
                        estimate = min(scan_limit, page + 2)
                    progress_callback(page, estimate, 0, 0)

                    # Por defecto se vuelve a descargar todo: una página puede haber cambiado desde la
                    # última vez, y los duplicados ya se descartan por hash de contenido.
                    if skip_saved and page_store.page_exists(device_id, page):
                        checked += 1
                        nonempty += 1
                        consecutive_empty = 0
                        progress_callback(page + 1, estimate, 0, 0)
                        continue

                    try:
                        points = await self.download_page(
                            page,
                            lambda received, total, current=page: progress_callback(
                                current, estimate, received, total
                            ),
                        )
                    except Exception as error:
                        self.log(f"Página {page}: error al descargar ({type(error).__name__}: {error})")
                        points = []

                    if self.cancel_sync:
                        break

                    checked += 1
                    if points:
                        consecutive_empty = 0
                        nonempty += 1
                        page_callback(page, points)
                    else:
                        consecutive_empty += 1

                    progress_callback(page + 1, estimate, 0, 0)

                    # Fin de la libreta: varias páginas vacías seguidas pasada la última página con datos.
                    if consecutive_empty >= 8 and page >= current_page:
                        break

                return checked, nonempty
            finally:
                self.io_paused = False
                self.online_enabled = was_online


class OcrUnavailable(RuntimeError):
    """El OCR local no se puede usar en este equipo (falta una librería o un idioma)."""


# Script de Windows PowerShell 5.1 que usa el OCR integrado de Windows (Windows.Media.Ocr).
# Se mantiene en ASCII a propósito para evitar problemas de codificación al ejecutarlo.
WINDOWS_OCR_SCRIPT = r"""
param([string]$Folder, [string]$OutPath, [string]$Languages)
$ErrorActionPreference = 'Stop'

function Write-Result($ok, $texts, $err) {
    $json = @{ ok = $ok; texts = $texts; error = $err } | ConvertTo-Json -Compress -Depth 4
    [System.IO.File]::WriteAllText($OutPath, $json, (New-Object System.Text.UTF8Encoding($false)))
}

try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
    $null = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
    $null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
    $null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
    $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
    $null = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType = WindowsRuntime]
    $null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]

    $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
    function Await($operation, $resultType) {
        $task = $asTaskGeneric.MakeGenericMethod($resultType).Invoke($null, @($operation))
        $null = $task.Wait(-1)
        $task.Result
    }

    $engine = $null
    foreach ($tag in $Languages.Split(',')) {
        if ($tag.Trim()) {
            try {
                $language = New-Object Windows.Globalization.Language($tag.Trim())
                $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
            } catch { $engine = $null }
            if ($engine) { break }
        }
    }
    if (-not $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
    if (-not $engine) { throw 'NO_OCR_LANGUAGE' }
    $maxDim = [Windows.Media.Ocr.OcrEngine]::MaxImageDimension

    $texts = New-Object System.Collections.ArrayList
    $files = Get-ChildItem -Path $Folder -Filter 'page_*.png' | Sort-Object Name
    foreach ($item in $files) {
        $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($item.FullName)) ([Windows.Storage.StorageFile])
        $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        if ($bitmap.PixelWidth -gt $maxDim -or $bitmap.PixelHeight -gt $maxDim) {
            throw ('IMAGE_TOO_LARGE ' + $bitmap.PixelWidth + 'x' + $bitmap.PixelHeight + ' max ' + $maxDim)
        }
        $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
        $lines = @($result.Lines | ForEach-Object { $_.Text })
        [void]$texts.Add(($lines -join [Environment]::NewLine))
    }
    Write-Result $true $texts ''
} catch {
    Write-Result $false @() ($_.Exception.Message)
}
"""


class LocalOcr:
    """OCR local y gratuito: Windows.Media.Ocr en Windows y Vision (VNRecognizeTextRequest) en macOS."""

    @staticmethod
    def engine_name() -> str:
        system = platform.system()
        if system == "Windows":
            return "OCR de Windows"
        if system == "Darwin":
            return "Vision de macOS"
        return "no disponible"

    @staticmethod
    def recognize(png: bytes, languages: list[str]) -> str:
        return LocalOcr.recognize_many([png], languages)[0]

    @staticmethod
    def recognize_many(pngs: list[bytes], languages: list[str]) -> list[str]:
        """Reconoce varias imágenes en una sola llamada (en Windows, un único proceso de PowerShell)."""
        if not pngs:
            return []
        system = platform.system()
        if system == "Windows":
            return LocalOcr._recognize_windows(pngs, languages)
        if system == "Darwin":
            return LocalOcr._recognize_macos(pngs, languages)
        raise OcrUnavailable("El OCR local solo está disponible en Windows y macOS.")

    @staticmethod
    def _recognize_windows(pngs: list[bytes], languages: list[str]) -> list[str]:
        folder = tempfile.mkdtemp(prefix="huion_ocr_")
        try:
            for index, png in enumerate(pngs):
                (Path(folder) / f"page_{index:03d}.png").write_bytes(png)
            script_path = Path(folder) / "ocr.ps1"
            out_path = Path(folder) / "result.json"
            script_path.write_text(WINDOWS_OCR_SCRIPT, encoding="utf-8")
            try:
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                     "-File", str(script_path), "-Folder", folder,
                     "-OutPath", str(out_path), "-Languages", ",".join(languages)],
                    capture_output=True, text=True, timeout=60 + 40 * len(pngs), check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except FileNotFoundError as error:
                raise OcrUnavailable("No se encontró Windows PowerShell, necesario para el OCR de Windows.") from error
            except subprocess.TimeoutExpired as error:
                raise RuntimeError("El OCR de Windows tardó demasiado en responder.") from error
            if not out_path.exists():
                detail = (result.stderr or result.stdout or "").strip()[:300]
                raise RuntimeError(f"El OCR de Windows no devolvió ningún resultado. {detail}")
            data = json.loads(out_path.read_text(encoding="utf-8-sig"))
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        if not data.get("ok"):
            error = str(data.get("error", "error desconocido"))
            if "NO_OCR_LANGUAGE" in error:
                raise OcrUnavailable(
                    "Windows no tiene ningún idioma con OCR instalado. Ve a Configuración > Hora e idioma > "
                    "Idioma y región, añade Español (o tu idioma) e instala sus funciones de idioma, incluido "
                    "el reconocimiento óptico de caracteres."
                )
            raise RuntimeError(f"Error del OCR de Windows: {error}")
        texts = data.get("texts", [])
        if isinstance(texts, str):
            texts = [texts]
        texts = [str(item).replace("\r\n", "\n").strip() for item in texts]
        if len(texts) != len(pngs):
            raise RuntimeError("El OCR de Windows devolvió un número de resultados inesperado.")
        return texts

    @staticmethod
    def _recognize_macos(pngs: list[bytes], languages: list[str]) -> list[str]:
        try:
            import Foundation
            import Vision
        except ImportError as error:
            raise OcrUnavailable(
                "Falta la librería de Vision para Python. Instálala con:  pip install pyobjc-framework-Vision"
            ) from error
        try:
            import objc
            pool = objc.autorelease_pool()
        except Exception:
            pool = None

        def recognize_one(png: bytes) -> str:
            data = Foundation.NSData.dataWithBytes_length_(png, len(png))
            handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(data, {})
            request = Vision.VNRecognizeTextRequest.alloc().init()
            request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
            request.setUsesLanguageCorrection_(True)
            try:
                # Por defecto Vision ignora texto más bajo que 1/32 de la altura de la imagen; con varias
                # líneas apiladas eso descartaría texto válido.
                request.setMinimumTextHeight_(0.008)
            except Exception:
                pass
            chosen: list[str] = []
            try:
                supported, _error = request.supportedRecognitionLanguagesAndReturnError_(None)
                chosen = [tag for tag in languages if tag in (supported or [])]
            except Exception:
                chosen = []
            if chosen:
                request.setRecognitionLanguages_(chosen)
            else:
                try:
                    request.setAutomaticallyDetectsLanguage_(True)
                except Exception:
                    pass
            success, error = handler.performRequests_error_([request], None)
            if not success:
                raise RuntimeError(f"Vision no pudo procesar la imagen: {error}")
            found = []
            for observation in request.results() or []:
                candidates = observation.topCandidates_(1)
                if not candidates:
                    continue
                box = observation.boundingBox()
                found.append((box.origin.y + box.size.height, box.origin.x, str(candidates[0].string())))
            # Vision usa el origen abajo a la izquierda: se ordena de arriba a abajo y de izquierda a derecha.
            found.sort(key=lambda item: (-round(item[0], 2), item[1]))
            return "\n".join(item[2] for item in found).strip()

        def run() -> list[str]:
            return [recognize_one(png) for png in pngs]

        if pool is not None:
            with pool:
                return run()
        return run()


OCR_MAX_DIM = 2400           # lado máximo de cada imagen enviada al OCR (el de Windows admite ~2600 px)
OCR_TARGET_LETTER_PX = 64    # altura de letra a la que se normaliza el texto preprocesado
OCR_MARGIN_PX = 48


def paint_png(width: int, height: int, strokes_px: list[list[tuple[float, float]]], pen_width: float) -> bytes:
    """Dibuja trazos (ya en píxeles) en negro sobre blanco y devuelve un PNG. Idéntico en Windows y macOS."""
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#ffffff"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#000000"), pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    for stroke in strokes_px:
        if not stroke:
            continue
        path = QPainterPath()
        path.moveTo(QPointF(stroke[0][0], stroke[0][1]))
        if len(stroke) == 1:
            path.lineTo(QPointF(stroke[0][0] + 0.1, stroke[0][1] + 0.1))
        for x, y in stroke[1:]:
            path.lineTo(QPointF(x, y))
        painter.drawPath(path)
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    data = bytes(buffer.data())
    buffer.close()
    return data


def render_ocr_png(strokes: list[list[PenPoint]], max_x: int, max_y: int) -> bytes:
    """Método «directo»: trazos tal cual, recortados al contenido y con margen."""
    xs = [point.x for stroke in strokes for point in stroke]
    ys = [point.y for stroke in strokes for point in stroke]
    low_x, high_x, low_y, high_y = min(xs), max(xs), min(ys), max(ys)
    box_w, box_h = max(1, high_x - low_x), max(1, high_y - low_y)
    base_scale = 1560 / max(1, max(max_x, max_y))
    scale = min(OCR_MAX_DIM / max(box_w, box_h), base_scale * 2.5)
    margin = 60
    width = int(box_w * scale) + margin * 2
    height = int(box_h * scale) + margin * 2
    strokes_px = [
        [((point.x - low_x) * scale + margin, (point.y - low_y) * scale + margin) for point in stroke]
        for stroke in strokes
    ]
    return paint_png(width, height, strokes_px, 4.0)


# --------------------------------------------------------------------------------------------------
# Preprocesado de trazos para el OCR (geometría pura, sin Qt: idéntico en Windows y macOS)
#   1. suavizado ligero · 2. corrección de la inclinación global de la página · 3. separación por líneas
#   4. por línea: corrección de la inclinación del renglón y de la cursiva (slant)
#   5. normalización del tamaño de letra · 6. grosor de trazo uniforme · 7. líneas apiladas y ordenadas
# --------------------------------------------------------------------------------------------------
@dataclass
class OcrChunk:
    width: int
    height: int
    strokes: list      # trazos [(x, y), ...] ya en píxeles
    pen_width: float


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def _smooth_stroke(stroke: list[tuple[float, float]], unit: float) -> list[tuple[float, float]]:
    """Suavizado ligero. Solo se aplica si el trazo está muestreado con densidad (lo normal en el lápiz);
    con muestreo escaso redondearía las esquinas de las letras."""
    if len(stroke) < 4:
        return stroke
    length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(stroke, stroke[1:]))
    if length / (len(stroke) - 1) > unit / 20.0:
        return stroke
    result = [stroke[0]]
    for index in range(1, len(stroke) - 1):
        result.append((
            (stroke[index - 1][0] + 2 * stroke[index][0] + stroke[index + 1][0]) / 4,
            (stroke[index - 1][1] + 2 * stroke[index][1] + stroke[index + 1][1]) / 4,
        ))
    result.append(stroke[-1])
    return result


def _letter_unit(strokes: list[list[tuple[float, float]]]) -> float:
    """Altura típica de una letra/palabra: mediana de las alturas de los trazos, sin puntos ni rayitas."""
    heights = [max(y for _, y in stroke) - min(y for _, y in stroke) for stroke in strokes if stroke]
    if not heights:
        return 1.0
    top = _percentile(heights, 0.9)
    letterish = [value for value in heights if value >= 0.25 * top] or heights
    return max(_median(letterish), 1.0)


def _densify(strokes: list[list[tuple[float, float]]], step: float, limit: int = 14000) -> list[tuple[float, float]]:
    """Remuestrea los trazos a intervalos regulares: la densidad de puntos pasa a representar la tinta."""
    step = max(step, 0.5)
    total = sum(
        math.hypot(b[0] - a[0], b[1] - a[1]) for stroke in strokes for a, b in zip(stroke, stroke[1:])
    )
    if total / step > limit:
        step = total / limit
    dense: list[tuple[float, float]] = []
    for stroke in strokes:
        if not stroke:
            continue
        dense.append(stroke[0])
        carry = 0.0
        for a, b in zip(stroke, stroke[1:]):
            segment = math.hypot(b[0] - a[0], b[1] - a[1])
            if segment <= 0:
                continue
            position = step - carry
            while position <= segment:
                t = position / segment
                dense.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
                position += step
            carry = (carry + segment) % step
    return dense


def _peakiness(values: list[float], bin_size: float) -> float:
    if not values:
        return 0.0
    low = min(values)
    counts: dict[int, int] = {}
    for value in values:
        key = int((value - low) / bin_size)
        counts[key] = counts.get(key, 0) + 1
    return sum(count * count for count in counts.values()) / (len(values) ** 2)


def _best_rotation(points: list[tuple[float, float]], bin_size: float, max_deg: float, step_deg: float) -> float:
    """Ángulo (rad) que hace más «afilado» el perfil horizontal de tinta; 0 si no mejora claramente."""
    if len(points) < 12:
        return 0.0
    cx = sum(x for x, _ in points) / len(points)
    cy = sum(y for _, y in points) / len(points)

    def score(angle: float) -> float:
        c, s = math.cos(angle), math.sin(angle)
        return _peakiness([cy + (x - cx) * s + (y - cy) * c for x, y in points], bin_size)

    base = score(0.0)
    best_angle, best_score = 0.0, base
    degrees = -max_deg
    while degrees <= max_deg + 1e-9:
        angle = math.radians(degrees)
        value = score(angle)
        if value > best_score:
            best_angle, best_score = angle, value
        degrees += step_deg
    for k in range(-4, 5):  # refinamiento fino
        angle = best_angle + math.radians(k * step_deg / 4)
        value = score(angle)
        if value > best_score:
            best_angle, best_score = angle, value
    return best_angle if best_score >= base * 1.04 else 0.0


def _rotate_strokes(strokes, angle: float, cx: float, cy: float):
    c, s = math.cos(angle), math.sin(angle)
    return [[(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c) for x, y in stroke] for stroke in strokes]


def _best_shear(points: list[tuple[float, float]], bin_size: float, max_k: float = 0.6, step: float = 0.05) -> float:
    """Cizallamiento horizontal k que verticaliza los trazos (corrige la cursiva); 0 si no mejora claramente."""
    if len(points) < 12:
        return 0.0
    cy = sum(y for _, y in points) / len(points)

    def score(k: float) -> float:
        return _peakiness([x + k * (y - cy) for x, y in points], bin_size)

    base = score(0.0)
    best_k, best_score = 0.0, base
    index = -int(round(max_k / step))
    while index <= int(round(max_k / step)):
        k = index * step
        value = score(k)
        if value > best_score:
            best_k, best_score = k, value
        index += 1
    return best_k if best_score >= base * 1.03 else 0.0


def _shear_strokes(strokes, k: float, cy: float):
    return [[(x + k * (y - cy), y) for x, y in stroke] for stroke in strokes]


def _segment_lines(strokes: list[list[tuple[float, float]]], unit: float) -> list[list[list[tuple[float, float]]]]:
    """Agrupa los trazos en líneas de texto mediante los huecos verticales de la cobertura de tinta."""
    ranges = [(min(y for _, y in st), max(y for _, y in st)) for st in strokes]
    top = min(r[0] for r in ranges)
    bottom = max(r[1] for r in ranges)
    bin_size = max(unit / 10.0, 1.0)
    count = int((bottom - top) / bin_size) + 2
    cover = [0] * count
    for y0, y1 in ranges:
        for index in range(int((y0 - top) / bin_size), int((y1 - top) / bin_size) + 1):
            cover[index] += 1
    threshold = int(0.05 * max(cover))
    min_gap = max(3, int(0.35 * unit / bin_size))

    bands: list[list[int]] = []
    start = None
    gap = 0
    for index, value in enumerate(cover):
        if value > threshold:
            if start is None:
                start = index
            gap = 0
            end = index
        elif start is not None:
            gap += 1
            if gap >= min_gap:
                bands.append([start, end])
                start = None
    if start is not None:
        bands.append([start, end])

    def band_for(stroke_range) -> int:
        center = ((stroke_range[0] + stroke_range[1]) / 2 - top) / bin_size
        best, best_distance = 0, float("inf")
        for number, (low, high) in enumerate(bands):
            distance = 0.0 if low <= center <= high else min(abs(center - low), abs(center - high))
            if distance < best_distance:
                best, best_distance = number, distance
        return best

    groups: dict[int, list] = {}
    for stroke, stroke_range in zip(strokes, ranges):
        groups.setdefault(band_for(stroke_range), []).append(stroke)
    lines = [groups[number] for number in sorted(groups)]

    # Una «línea» minúscula (un punto de la i, una tilde, un signo) se une a la línea vecina más cercana.
    def extent(line):
        ys = [y for st in line for _, y in st]
        return min(ys), max(ys)

    merged = True
    while merged and len(lines) > 1:
        merged = False
        for number, line in enumerate(lines):
            low, high = extent(line)
            if high - low < 0.45 * unit and len(line) <= 2:
                centers = [((extent(other)[0] + extent(other)[1]) / 2, index)
                           for index, other in enumerate(lines) if index != number]
                _, target = min(centers, key=lambda item: abs(item[0] - (low + high) / 2))
                lines[target] = lines[target] + line
                del lines[number]
                merged = True
                break
    return lines


def _prepare_line(strokes, unit: float):
    """Corrige la inclinación del renglón y la cursiva de una línea de texto."""
    dense = _densify(strokes, unit / 6.0)
    if len(dense) < 12:
        return strokes
    cx = sum(x for x, _ in dense) / len(dense)
    cy = sum(y for _, y in dense) / len(dense)
    angle = _best_rotation(dense, unit / 8.0, max_deg=6.0, step_deg=1.0)
    if angle:
        strokes = _rotate_strokes(strokes, angle, cx, cy)
        dense = _densify(strokes, unit / 6.0)
        cy = sum(y for _, y in dense) / len(dense)
    k = _best_shear(dense, unit / 10.0)
    if k:
        strokes = _shear_strokes(strokes, k, cy)
    return strokes


def preprocess_for_ocr(strokes_in: list[list[PenPoint]]) -> list[OcrChunk]:
    """Convierte los trazos manuscritos en imágenes (trozos) limpias y homogéneas para el OCR."""
    strokes = [[(float(p.x), float(p.y)) for p in stroke] for stroke in strokes_in if stroke]
    if not strokes:
        return []
    unit = _letter_unit(strokes)
    strokes = [_smooth_stroke(stroke, unit) for stroke in strokes]

    # Inclinación global de la página (la libreta puede estar girada respecto a la escritura).
    dense = _densify(strokes, unit / 6.0)
    if len(dense) >= 40:
        angle = _best_rotation(dense, unit / 4.0, max_deg=10.0, step_deg=1.0)
        if angle:
            cx = sum(x for x, _ in dense) / len(dense)
            cy = sum(y for _, y in dense) / len(dense)
            strokes = _rotate_strokes(strokes, angle, cx, cy)

    lines = [_prepare_line(line, unit) for line in _segment_lines(strokes, unit)]

    base_scale = OCR_TARGET_LETTER_PX / unit
    prepared = []
    for line in lines:
        line_unit = _letter_unit(line) if len(line) >= 3 else unit
        scale = min(max(OCR_TARGET_LETTER_PX / line_unit, 0.5 * base_scale), 2.5 * base_scale)
        xs = [x for st in line for x, _ in st]
        ys = [y for st in line for _, y in st]
        prepared.append((line, scale, min(xs), min(ys), (max(xs) - min(xs)) * scale, (max(ys) - min(ys)) * scale))

    widest = max(item[4] for item in prepared)
    shrink = min(1.0, (OCR_MAX_DIM - 2 * OCR_MARGIN_PX) / max(widest, 1.0))
    gap = max(18.0, 0.6 * OCR_TARGET_LETTER_PX * shrink)
    pen_width = max(2.5, 0.07 * OCR_TARGET_LETTER_PX * shrink)
    limit = OCR_MAX_DIM - 2 * OCR_MARGIN_PX

    chunks: list[OcrChunk] = []
    current: list[list[tuple[float, float]]] = []
    cursor, chunk_width = 0.0, 0.0

    def flush():
        nonlocal current, cursor, chunk_width
        if current:
            width = max(200, int(chunk_width) + 2 * OCR_MARGIN_PX)
            height = max(120, int(cursor - gap) + 2 * OCR_MARGIN_PX)
            chunks.append(OcrChunk(width, height, current, pen_width))
        current, cursor, chunk_width = [], 0.0, 0.0

    for line, scale, x0, y0, width, height in prepared:
        s = scale * shrink
        line_height = height * shrink
        if current and cursor + line_height > limit:
            flush()
        for stroke in line:
            current.append([((x - x0) * s + OCR_MARGIN_PX, (y - y0) * s + cursor + OCR_MARGIN_PX) for x, y in stroke])
        chunk_width = max(chunk_width, width * shrink)
        cursor += line_height + gap
    flush()
    return chunks


def render_chunk_png(chunk: OcrChunk) -> bytes:
    return paint_png(chunk.width, chunk.height, chunk.strokes, chunk.pen_width)


# --------------------------------------------------------------------------------------------------
# Métricas de precisión (para la pantalla de medición)
# --------------------------------------------------------------------------------------------------
def levenshtein(a, b) -> int:
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, item_a in enumerate(a, 1):
        current = [i]
        for j, item_b in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (item_a != item_b)))
        previous = current
    return previous[-1]


def normalize_for_score(text: str, loose: bool) -> str:
    text = unicodedata.normalize("NFC", text)
    if loose:  # ignora mayúsculas y tildes
        text = "".join(ch for ch in unicodedata.normalize("NFD", text.casefold()) if unicodedata.category(ch) != "Mn")
    return " ".join(text.split())


def accuracy_scores(reference: str, recognized: str, loose: bool) -> tuple[float, float]:
    """Devuelve (precisión de caracteres, precisión de palabras) entre 0 y 1."""
    ref = normalize_for_score(reference, loose)
    hyp = normalize_for_score(recognized, loose)
    char_acc = max(0.0, 1.0 - levenshtein(ref, hyp) / max(1, len(ref)))
    ref_words, hyp_words = ref.split(), hyp.split()
    word_acc = max(0.0, 1.0 - levenshtein(ref_words, hyp_words) / max(1, len(ref_words)))
    return char_acc, word_acc


class Canvas(QWidget):
    count_changed = Signal(int)

    def __init__(self):
        super().__init__()
        self.max_x = DEFAULT_MAX_X
        self.max_y = DEFAULT_MAX_Y
        self.max_pressure = DEFAULT_MAX_PRESSURE
        self.raw_points: list[PenPoint] = []
        self.strokes: list[list[PenPoint]] = []
        self.current: list[PenPoint] = []
        self.total = 0
        self.bg_color = "#07090c"
        self.border_color = "#1e2530"
        self.muted_color = "#64748b"
        self.empty_text = "No hay contenido para mostrar."
        self.setMinimumSize(360, 480)

    def set_theme(self, background: str, border: str, muted: str):
        self.bg_color, self.border_color, self.muted_color = background, border, muted
        self.update()

    def set_empty_text(self, text: str):
        self.empty_text = text
        self.update()

    def set_limits(self, x, y, pressure):
        self.max_x, self.max_y, self.max_pressure = max(1, x), max(1, y), max(1, pressure)

    def clear(self):
        self.raw_points, self.strokes, self.current, self.total = [], [], [], 0
        self.count_changed.emit(0)
        self.update()

    def rebuild(self):
        self.strokes = Protocol.strokes(self.raw_points, self.max_x, self.max_y)
        self.current = []
        self.total = sum(len(stroke) for stroke in self.strokes)
        self.count_changed.emit(self.total)
        self.update()

    def add_points(self, points: Optional[list[PenPoint]]):
        if points is None:
            self.clear()
            return
        useful = [
            point for point in points
            if not (point.x == 0 and point.y == 0 and point.pressure == 0)
        ]
        if not useful:
            return
        # Se acumulan los puntos ORIGINALES y se recalculan los trazos desde cero. Antes se volvían a
        # agrupar trazos ya aplanados, lo que unía letras sueltas en una única línea continua.
        self.raw_points.extend(useful)
        self.rebuild()

    def set_points(self, points):
        self.clear()
        self.raw_points = list(points)
        self.rebuild()

    def page_rect(self):
        margin = 20
        aw, ah = max(1, self.width() - margin * 2), max(1, self.height() - margin * 2)
        ratio = self.max_x / self.max_y  # misma proporción que el área activa del dispositivo
        if aw / ah > ratio:
            height, width = ah, ah * ratio
        else:
            width, height = aw, aw / ratio
        return QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height)

    def mapped(self, point, rect):
        return QPointF(
            rect.left() + point.x / self.max_x * rect.width(),
            rect.top() + point.y / self.max_y * rect.height(),
        )

    def draw_stroke(self, painter, stroke, rect):
        if not stroke:
            return
        points = [self.mapped(point, rect) for point in stroke]
        width = max(1.2, 1.2 + sum(p.pressure for p in stroke) / len(stroke) / self.max_pressure * 3)
        if len(points) == 1:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#111318"))
            painter.drawEllipse(points[0], width, width)
            return
        path = QPainterPath()
        path.moveTo(points[0])
        for index in range(1, len(points)):
            previous, current = points[index - 1], points[index]
            midpoint = QPointF((previous.x() + current.x()) / 2, (previous.y() + current.y()) / 2)
            path.quadTo(previous, midpoint)
        path.lineTo(points[-1])
        painter.setPen(QPen(QColor("#111318"), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(self.bg_color))
        rect = self.page_rect()
        painter.setPen(QPen(QColor(self.border_color)))
        painter.setBrush(QColor("#f7f7f4"))  # el «papel» es siempre claro, en cualquier tema
        painter.drawRoundedRect(rect, 8, 8)

        # Estado vacío con instrucciones según la situación
        if not self.strokes and not self.current:
            painter.setPen(QColor("#6b7280"))
            painter.setFont(self.font())
            painter.drawText(
                rect.adjusted(24, 24, -24, -24),
                int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap),
                self.empty_text,
            )
            return

        for stroke in self.strokes:
            self.draw_stroke(painter, stroke, rect)
        self.draw_stroke(painter, self.current, rect)


class MeasurePage(QWidget):
    """Pantalla de medición: compara el acierto del OCR directo frente al OCR con preprocesado."""

    PHRASES = (
        "El veloz murciélago hindú comía feliz cardillo y kiwi.",
        "Mañana por la tarde iremos a la biblioteca de la ciudad.",
        "La reunión del jueves empieza a las 10:30 en la sala dos.",
        "Compra pan, leche, huevos y dos kilos de naranjas.",
    )
    METHODS = (("directo", "OCR directo"), ("preprocesado", "OCR con preprocesado"))

    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.samples: list[dict] = []
        self.phrase_index = 0
        self.busy = False
        self.build_ui()

    @staticmethod
    def pct(value: float) -> str:
        return f"{value * 100:.1f} %".replace(".", ",")

    def build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        intro = QLabel(
            "Escribe en el Huion Note una frase conocida y comprueba qué porcentaje de acierto consigue "
            "cada método con tu letra. Con varias muestras la media es más fiable."
        )
        intro.setObjectName("subtitle")
        intro.setWordWrap(True)
        root.addWidget(intro)

        columns = QHBoxLayout()
        columns.setSpacing(14)

        # --- Tarjeta 1: referencia y captura
        left = self.owner.card()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(8)
        title_1 = QLabel("1 · Frase de referencia")
        title_1.setObjectName("section")
        self.reference_edit = QTextEdit()
        self.reference_edit.setMaximumHeight(84)
        self.reference_edit.setPlaceholderText("Escribe aquí exactamente la frase que vas a escribir a mano.")
        self.sample_button = QPushButton("Sugerir frase")
        title_2 = QLabel("2 · Escritura capturada")
        title_2.setObjectName("section")
        self.capture_status = QLabel("")
        self.capture_status.setObjectName("subtitle")
        self.capture_status.setWordWrap(True)
        self.canvas = Canvas()
        self.canvas.setMinimumSize(300, 220)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.canvas)
        capture_row = QHBoxLayout()
        self.clear_capture_button = QPushButton("Limpiar captura")
        self.page_combo = QComboBox()
        self.load_page_button = QPushButton("Cargar página")
        capture_row.addWidget(self.clear_capture_button)
        capture_row.addStretch()
        capture_row.addWidget(self.page_combo)
        capture_row.addWidget(self.load_page_button)
        for widget in (title_1, self.reference_edit):
            left_layout.addWidget(widget)
        left_layout.addWidget(self.sample_button, 0, Qt.AlignmentFlag.AlignLeft)
        left_layout.addSpacing(6)
        left_layout.addWidget(title_2)
        left_layout.addWidget(self.capture_status)
        left_layout.addWidget(scroll, 1)
        left_layout.addLayout(capture_row)

        # --- Tarjeta 2: resultados
        right = self.owner.card()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(8)
        title_3 = QLabel("3 · Resultados")
        title_3.setObjectName("section")
        options = QHBoxLayout()
        self.loose_check = QCheckBox("Ignorar mayúsculas y tildes")
        self.loose_check.setChecked(True)
        self.target_spin = QSpinBox()
        self.target_spin.setRange(1, 100)
        self.target_spin.setSuffix(" %")
        self.target_spin.setValue(self.owner.settings.value("ocr_target", 88, type=int))
        options.addWidget(self.loose_check)
        options.addStretch()
        options.addWidget(QLabel("Objetivo:"))
        options.addWidget(self.target_spin)
        self.measure_button = QPushButton("Medir precisión")
        self.measure_button.setObjectName("primary")
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Método", "Caracteres (última)", "Caracteres (media)", "Palabras (media)", "Texto reconocido (última)"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setWordWrap(True)
        header = self.table.horizontalHeader()
        for column in range(4):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.verdict_label = QLabel("Todavía no hay mediciones.")
        self.verdict_label.setWordWrap(True)
        self.samples_label = QLabel("")
        self.samples_label.setObjectName("subtitle")
        buttons = QHBoxLayout()
        self.apply_button = QPushButton("Usar el mejor método")
        self.reset_button = QPushButton("Reiniciar promedios")
        self.export_button = QPushButton("Exportar CSV")
        for button in (self.apply_button, self.reset_button, self.export_button):
            buttons.addWidget(button)
        buttons.addStretch()
        right_layout.addWidget(title_3)
        right_layout.addLayout(options)
        right_layout.addWidget(self.measure_button)
        right_layout.addWidget(self.table, 1)
        right_layout.addWidget(self.verdict_label)
        right_layout.addWidget(self.samples_label)
        right_layout.addLayout(buttons)

        columns.addWidget(left, 1)
        columns.addWidget(right, 1)
        root.addLayout(columns, 1)

        self.sample_button.clicked.connect(self.suggest_phrase)
        self.clear_capture_button.clicked.connect(self.clear_capture)
        self.load_page_button.clicked.connect(self.load_page)
        self.measure_button.clicked.connect(self.start_measure)
        self.loose_check.toggled.connect(lambda _v: self.refresh_results())
        self.target_spin.valueChanged.connect(self.on_target_changed)
        self.apply_button.clicked.connect(self.apply_best)
        self.reset_button.clicked.connect(self.reset_samples)
        self.export_button.clicked.connect(self.export_csv)
        self.update_capture_status()
        self.update_buttons()

    # ------------------------------------------------------------------ captura
    def showEvent(self, event):
        super().showEvent(event)
        protocol = self.owner.manager.protocol
        self.canvas.set_limits(protocol.max_x, protocol.max_y, protocol.max_pressure)
        self.refresh_pages()
        self.update_capture_status()

    def on_live(self, points):
        """Recibe los trazos en directo mientras la escucha pasiva está activa."""
        if points is None or not self.owner.manager.online_enabled:
            return
        self.canvas.add_points(points)
        self.update_capture_status()
        self.update_buttons()

    def update_capture_status(self):
        if self.owner.manager.online_enabled:
            text = "Escucha pasiva activa: escribe la frase en el Huion Note."
        elif self.canvas.raw_points:
            text = f"Captura lista ({len(self.canvas.raw_points)} puntos)."
        else:
            text = ("Activa la escucha pasiva (Dispositivo › Escucha pasiva) y escribe la frase, "
                    "o carga una página ya sincronizada.")
        self.capture_status.setText(text)

    def refresh_pages(self):
        current = self.page_combo.currentData()
        self.page_combo.clear()
        for page in sorted(self.owner.synced_pages):
            self.page_combo.addItem(self.owner.page_label(page), page)
        if current is not None:
            index = self.page_combo.findData(current)
            if index >= 0:
                self.page_combo.setCurrentIndex(index)
        self.update_buttons()

    def clear_capture(self):
        self.canvas.clear()
        self.update_capture_status()
        self.update_buttons()

    def load_page(self):
        page = self.page_combo.currentData()
        points = self.owner.synced_pages.get(page) if page is not None else None
        if not points:
            return
        self.canvas.set_points(points)
        self.update_capture_status()
        self.update_buttons()

    def suggest_phrase(self):
        self.reference_edit.setPlainText(self.PHRASES[self.phrase_index % len(self.PHRASES)])
        self.phrase_index += 1

    def update_buttons(self):
        has_pages = self.page_combo.count() > 0
        self.load_page_button.setEnabled(has_pages)
        self.page_combo.setEnabled(has_pages)
        self.measure_button.setEnabled(not self.busy)
        self.apply_button.setEnabled(bool(self.samples))
        self.reset_button.setEnabled(bool(self.samples))
        self.export_button.setEnabled(bool(self.samples))

    # ------------------------------------------------------------------ medición
    def start_measure(self):
        reference = self.reference_edit.toPlainText().strip()
        if not reference:
            self.owner.show_toast("Escribe primero la frase de referencia.", "warn")
            return
        if not self.canvas.raw_points:
            self.owner.show_toast("No hay escritura capturada. Escribe la frase o carga una página.", "warn")
            return
        if self.busy:
            return
        self.owner.schedule(self.measure(reference, list(self.canvas.raw_points)))

    async def measure(self, reference: str, points: list):
        self.busy = True
        self.measure_button.setText("Midiendo…")
        self.update_buttons()
        try:
            self.owner.ocr_disabled_reason = ""
            texts: dict[str, str] = {}
            for key, label in self.METHODS:
                self.capture_status.setText(f"Reconociendo con «{label}»…")
                text = await self.owner.recognize_points(points, quiet=False, method=key)
                if text is None:
                    self.capture_status.setText("No se pudo completar la medición (revisa el aviso del OCR).")
                    return
                texts[key] = text
            self.samples.append({"reference": reference, "texts": texts, "when": datetime.now()})
            self.refresh_results()
            self.owner.show_toast("Medición completada.", "ok")
        finally:
            self.busy = False
            self.measure_button.setText("Medir precisión")
            self.update_capture_status()
            self.update_buttons()

    def scores(self) -> dict[str, list[tuple[float, float]]]:
        loose = self.loose_check.isChecked()
        return {
            key: [accuracy_scores(sample["reference"], sample["texts"][key], loose) for sample in self.samples]
            for key, _label in self.METHODS
        }

    def best_method(self) -> Optional[str]:
        if not self.samples:
            return None
        scores = self.scores()
        return max(scores, key=lambda key: sum(item[0] for item in scores[key]) / len(scores[key]))

    def on_target_changed(self, value: int):
        self.owner.settings.setValue("ocr_target", value)
        self.refresh_results()

    def refresh_results(self):
        self.table.setRowCount(0)
        if not self.samples:
            self.verdict_label.setText("Todavía no hay mediciones.")
            self.samples_label.setText("")
            self.update_buttons()
            return
        scores = self.scores()
        last = self.samples[-1]
        averages = {}
        self.table.setRowCount(len(self.METHODS))
        for row, (key, label) in enumerate(self.METHODS):
            char_last = scores[key][-1][0]
            char_avg = sum(item[0] for item in scores[key]) / len(scores[key])
            word_avg = sum(item[1] for item in scores[key]) / len(scores[key])
            averages[key] = char_avg
            values = [label, self.pct(char_last), self.pct(char_avg), self.pct(word_avg), last["texts"][key] or "(sin texto)"]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.table.resizeRowsToContents()
        best = max(averages, key=averages.get)
        best_label = dict(self.METHODS)[best]
        target = self.target_spin.value() / 100
        if averages[best] >= target:
            verdict = f"Mejor método: {best_label} — {self.pct(averages[best])} de media. Alcanza el objetivo del {self.target_spin.value()} %."
        else:
            verdict = (f"Mejor método: {best_label} — {self.pct(averages[best])} de media, por debajo del objetivo del "
                       f"{self.target_spin.value()} %. Prueba con letra de imprenta, más separación entre palabras o más muestras.")
        self.verdict_label.setText(verdict)
        self.samples_label.setText(f"Muestras: {len(self.samples)}")
        self.update_buttons()

    def apply_best(self):
        best = self.best_method()
        if best is None:
            return
        self.owner.preprocess.setChecked(best == "preprocesado")
        self.owner.show_toast(f"Método aplicado en todo el programa: {dict(self.METHODS)[best]}.", "ok")

    def reset_samples(self):
        self.samples.clear()
        self.refresh_results()

    def export_csv(self):
        if not self.samples:
            return
        path = self.owner.output / f"mediciones_ocr_{datetime.now():%Y%m%d_%H%M%S}.csv"
        loose = self.loose_check.isChecked()
        with path.open("w", newline="", encoding="utf-8-sig") as handle:  # utf-8-sig: Excel lo abre bien en Windows y Mac
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(["fecha", "metodo", "referencia", "reconocido", "precision_caracteres", "precision_palabras", "ignora_mayusculas_y_tildes"])
            for sample in self.samples:
                for key, label in self.METHODS:
                    char_acc, word_acc = accuracy_scores(sample["reference"], sample["texts"][key], loose)
                    writer.writerow([
                        sample["when"].isoformat(timespec="seconds"), label, sample["reference"],
                        sample["texts"][key].replace("\n", " "), f"{char_acc:.4f}", f"{word_acc:.4f}", "si" if loose else "no",
                    ])
        self.owner.add_log(f"Mediciones exportadas en {path}")
        self.owner.show_toast(f"CSV guardado: {path.name}", "ok")


class MainWindow(QMainWindow):
    log_signal = Signal(str)
    state_signal = Signal(str)
    live_signal = Signal(object)
    battery_signal = Signal(int)
    page_signal = Signal(int, object)
    progress_signal = Signal(int, int, int, int)
    devices_signal = Signal(object)

    SECTIONS = (
        ("Notas", "notes"),
        ("Medición", "measure"),
        ("Historial", "history"),
        ("Ajustes", "settings"),
        ("Avanzado", "advanced"),
    )

    def __init__(self):
        super().__init__()
        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.store = PageStore(Path.home() / ".huion_note_sync" / "pages.sqlite3")
        self.output = Path(self.settings.value("output", str(Path.home() / "Documents" / "Huion Note")))
        self.output.mkdir(parents=True, exist_ok=True)
        self.manager = BleManager(self.log_signal.emit, self.state_signal.emit, self.live_signal.emit, self.battery_signal.emit)

        self.synced_pages: dict[int, list[PenPoint]] = {}
        self.current_preview_page: Optional[int] = None
        self.low_battery_warned = False
        self.shown_digest = ""                       # hash de la página mostrada en el lienzo (vacío si es directo)
        self.live_snapshot: list[PenPoint] = []      # lo escrito en directo y aún sin guardar
        self.live_key_counter = LIVE_PAGE_BASE
        self.digest_cache: dict[int, tuple] = {}
        self.thumb_cache: dict[str, QIcon] = {}
        self.zoom = 1.0
        self.sync_started = 0.0
        self.theme_mode = str(self.settings.value("theme", "auto"))
        self._banner_action = None

        # Estado del OCR local: texto reconocido por contenido (hash), idiomas y control de errores.
        self.ocr_texts: dict[str, str] = {}
        self.ocr_languages = self.system_ocr_languages()
        self.ocr_disabled_reason = ""
        self.live_ocr_digest = ""

        # Carga automática de páginas almacenadas previamente en memoria
        self.load_stored_pages_into_memory()

        self.syncing = False
        self.ocr_lock = asyncio.Lock()
        self.ocr_timer = QTimer(self)
        self.ocr_timer.setSingleShot(True)
        self.ocr_timer.setInterval(1500)  # espera a que el lápiz deje de escribir antes de reconocer
        self.tasks: set[asyncio.Task] = set()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1280, 860)
        self.setMinimumSize(1040, 700)
        self.build_ui()
        self.connect_signals()
        self.apply_theme()
        self.restore_window_state()
        self.set_state("Desconectado")
        self.refresh_history()
        self.refresh_page_list()
        if self.synced_pages:
            self.update_canvas_display()
        QTimer.singleShot(700, self.auto_start)

    def load_stored_pages_into_memory(self):
        """Carga en memoria las páginas guardadas previamente (y su texto) para mostrarlas al iniciar."""
        try:
            rows = self.store.db.execute(
                "SELECT logical_page, content_hash, points_json, json_path, png_path "
                "FROM pages ORDER BY saved_at ASC"
            ).fetchall()
            for page, digest, points_json, json_path, png_path in rows:
                points = None
                if points_json:
                    points = [
                        PenPoint(x, y, pressure, bool(down), 0, status)
                        for x, y, pressure, down, status in json.loads(points_json)
                    ]
                elif json_path and Path(json_path).exists():
                    # Páginas guardadas con versiones anteriores, que sí exportaban un JSON.
                    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
                    points = [
                        PenPoint(p["x"], p["y"], p["pressure"], p["down"], p.get("timestamp", 0), p.get("status", 0))
                        for p in data.get("points", [])
                    ]
                if points is None:
                    continue
                self.synced_pages[page] = points
                txt_path = Path(png_path).with_suffix(".txt") if png_path else None
                if txt_path and txt_path.exists():
                    self.ocr_texts[digest] = txt_path.read_text(encoding="utf-8")

            if self.synced_pages:
                self.current_preview_page = min(self.synced_pages.keys())
            live_keys = [key for key in self.synced_pages if key >= LIVE_PAGE_BASE]
            self.live_key_counter = max(live_keys) if live_keys else LIVE_PAGE_BASE
        except Exception as error:
            print(f"Error al cargar páginas previas: {error}")

    @staticmethod
    def system_ocr_languages() -> list[str]:
        tag = QLocale.system().name().replace("_", "-")  # p. ej. "es-ES"
        candidates = [tag, tag.split("-")[0], "es-ES", "en-US"]
        return list(dict.fromkeys(item for item in candidates if item and item != "C"))

    def schedule(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    @staticmethod
    def card():
        frame = QFrame()
        frame.setObjectName("card")
        return frame

    @staticmethod
    def page_label(page: int) -> str:
        return f"En vivo {page - LIVE_PAGE_BASE}" if page >= LIVE_PAGE_BASE else f"Pág. {page}"

    def page_digest(self, page: int) -> str:
        points = self.synced_pages[page]
        cached = self.digest_cache.get(page)
        if cached is not None and cached[0] is points:
            return cached[1]
        digest = self.digest(points)
        self.digest_cache[page] = (points, digest)
        return digest

    # ------------------------------------------------------------------ Construcción de la interfaz
    def build_ui(self):
        root_widget = QWidget()
        self.setCentralWidget(root_widget)
        outer = QHBoxLayout(root_widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- Barra lateral de navegación
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 20, 14, 14)
        side.setSpacing(4)
        brand = QLabel(APP_NAME)
        brand.setObjectName("brand")
        tagline = QLabel("Tus notas manuscritas, digitalizadas")
        tagline.setObjectName("subtitle")
        tagline.setWordWrap(True)
        side.addWidget(brand)
        side.addWidget(tagline)
        side.addSpacing(16)
        self.nav_buttons: list[QPushButton] = []
        for index, (label, _icon) in enumerate(self.SECTIONS):
            button = QPushButton(label)
            button.setObjectName("nav")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIconSize(QSize(20, 20))
            button.clicked.connect(lambda _checked=False, i=index: self.show_section(i))
            side.addWidget(button)
            self.nav_buttons.append(button)
        side.addStretch()
        version = QLabel(f"Versión {APP_VERSION}")
        version.setObjectName("subtitle")
        side.addWidget(version)
        outer.addWidget(sidebar)

        # ---- Contenido
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(22, 16, 22, 12)
        content_layout.setSpacing(12)

        topbar = QHBoxLayout()
        topbar.setSpacing(8)
        self.section_title = QLabel("Notas")
        self.section_title.setObjectName("title")
        self.header_device = QLabel("")
        self.header_device.setObjectName("subtitle")
        self.status = QLabel("Desconectado")
        self.battery = QLabel("—")
        self.battery.setObjectName("battery_normal")
        self.connect_button = QPushButton("Buscar y conectar")
        self.connect_button.setObjectName("primary")
        self.sync_button = QPushButton("Sincronizar")
        self.sync_button.setObjectName("primary")
        self.stop_sync_button = QPushButton("Parar sincronización")
        self.stop_sync_button.setObjectName("danger")
        self.live_button = QPushButton("Escucha pasiva")
        self.live_button.setObjectName("toggle")
        self.live_button.setCheckable(True)
        self.more_button = QToolButton()
        self.more_button.setObjectName("more")
        self.more_button.setText("Más")
        self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        topbar.addWidget(self.section_title)
        topbar.addStretch()
        for widget in (self.header_device, self.status, self.battery, self.connect_button, self.sync_button,
                       self.stop_sync_button, self.live_button, self.more_button):
            topbar.addWidget(widget)
        content_layout.addLayout(topbar)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.build_notes_page())
        self.measure_page = MeasurePage(self)
        self.stack.addWidget(self.measure_page)
        self.stack.addWidget(self.build_history_page())
        self.stack.addWidget(self.build_settings_page())
        self.stack.addWidget(self.build_advanced_page())
        content_layout.addWidget(self.stack, 1)

        # ---- Pie con el progreso, siempre visible
        footer = QFrame()
        footer.setObjectName("footer")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(14, 8, 14, 8)
        footer_layout.setSpacing(12)
        self.footer_label = QLabel("Listo")
        self.footer_label.setObjectName("subtitle")
        self.page_progress = QProgressBar()
        self.page_progress.setFixedWidth(280)
        self.packet_progress = QProgressBar()
        self.packet_progress.setFixedWidth(170)
        self.page_progress.hide()
        self.packet_progress.hide()
        footer_layout.addWidget(self.footer_label, 1)
        footer_layout.addWidget(self.page_progress)
        footer_layout.addWidget(self.packet_progress)
        content_layout.addWidget(footer)
        outer.addWidget(content, 1)

        self.toast = Toast(root_widget)
        self.build_menu()

    def build_notes_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Aviso accionable cuando el OCR no está disponible
        self.ocr_banner = QFrame()
        self.ocr_banner.setObjectName("banner")
        banner_layout = QHBoxLayout(self.ocr_banner)
        banner_layout.setContentsMargins(14, 10, 14, 10)
        self.ocr_banner_label = QLabel("")
        self.ocr_banner_label.setWordWrap(True)
        self.ocr_banner_button = QPushButton("")
        banner_layout.addWidget(self.ocr_banner_label, 1)
        banner_layout.addWidget(self.ocr_banner_button)
        self.ocr_banner.hide()
        layout.addWidget(self.ocr_banner)

        self.notes_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.notes_splitter.setChildrenCollapsible(False)

        # ---- Columna 1: páginas con miniaturas y búsqueda
        pages_card = self.card()
        pages_card.setMinimumWidth(150)
        pages_layout = QVBoxLayout(pages_card)
        pages_layout.setContentsMargins(12, 12, 12, 12)
        pages_layout.setSpacing(8)
        pages_title = QLabel("Páginas")
        pages_title.setObjectName("section")
        self.page_search = QLineEdit()
        self.page_search.setPlaceholderText("Buscar en el texto…")
        self.page_search.setClearButtonEnabled(True)
        self.page_list = QListWidget()
        self.page_list.setIconSize(QSize(84, 112))
        self.page_list.setSpacing(4)
        self.page_count_label = QLabel("Sin páginas todavía")
        self.page_count_label.setObjectName("subtitle")
        pages_layout.addWidget(pages_title)
        pages_layout.addWidget(self.page_search)
        pages_layout.addWidget(self.page_list, 1)
        pages_layout.addWidget(self.page_count_label)

        # ---- Columna 2: vista previa con zoom
        preview_card = self.card()
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(14, 12, 14, 14)
        preview_layout.setSpacing(8)
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.prev_page_btn = QPushButton("‹")
        self.prev_page_btn.setObjectName("icon")
        self.page_indicator = QLabel("Página —")
        self.page_indicator.setObjectName("section")
        self.next_page_btn = QPushButton("›")
        self.next_page_btn.setObjectName("icon")
        self.zoom_out_btn = QPushButton("−")
        self.zoom_out_btn.setObjectName("icon")
        self.zoom_label = QLabel("100 %")
        self.zoom_label.setObjectName("subtitle")
        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.setObjectName("icon")
        self.points_label = QLabel("0 puntos")
        self.points_label.setObjectName("subtitle")
        self.clear_button = QPushButton("Limpiar vista")
        bar.addWidget(self.prev_page_btn)
        bar.addWidget(self.page_indicator)
        bar.addWidget(self.next_page_btn)
        bar.addStretch()
        bar.addWidget(self.points_label)
        bar.addWidget(self.zoom_out_btn)
        bar.addWidget(self.zoom_label)
        bar.addWidget(self.zoom_in_btn)
        bar.addWidget(self.clear_button)
        preview_layout.addLayout(bar)
        self.canvas = Canvas()
        self.canvas_base_size = (360, 480)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.canvas)
        preview_layout.addWidget(scroll, 1)

        # ---- Columna 3: texto reconocido (editable)
        text_card = self.card()
        text_card.setMinimumWidth(280)
        text_layout = QVBoxLayout(text_card)
        text_layout.setContentsMargins(14, 12, 14, 14)
        text_layout.setSpacing(8)
        text_header = QHBoxLayout()
        text_title = QLabel("Texto reconocido")
        text_title.setObjectName("section")
        self.ocr_status = QLabel(f"Motor: {LocalOcr.engine_name()}")
        self.ocr_status.setObjectName("subtitle")
        text_header.addWidget(text_title)
        text_header.addStretch()
        text_header.addWidget(self.ocr_status)
        self.ocr_view = QTextEdit()
        self.ocr_view.setPlaceholderText(
            "Aquí aparecerá el texto de la página mostrada. Puedes corregirlo a mano y pulsar «Guardar cambios»."
        )
        self.ocr_now_button = QPushButton("Reconocer")
        self.ocr_copy_button = QPushButton("Copiar")
        self.ocr_save_button = QPushButton("Guardar cambios")
        self.export_md_button = QPushButton("Exportar todo (.md)")
        row_one = QHBoxLayout()
        row_one.addWidget(self.ocr_now_button)
        row_one.addWidget(self.ocr_copy_button)
        row_two = QHBoxLayout()
        row_two.addWidget(self.ocr_save_button)
        row_two.addWidget(self.export_md_button)
        text_layout.addLayout(text_header)
        text_layout.addWidget(self.ocr_view, 1)
        text_layout.addLayout(row_one)
        text_layout.addLayout(row_two)

        self.notes_splitter.addWidget(pages_card)
        self.notes_splitter.addWidget(preview_card)
        self.notes_splitter.addWidget(text_card)
        self.notes_splitter.setStretchFactor(0, 0)
        self.notes_splitter.setStretchFactor(1, 3)
        self.notes_splitter.setStretchFactor(2, 2)
        self.notes_splitter.setSizes([190, 640, 380])
        layout.addWidget(self.notes_splitter, 1)
        return page

    def build_history_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        card = self.card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(8)
        top = QHBoxLayout()
        title = QLabel("Páginas guardadas")
        title.setObjectName("section")
        self.summary = QLabel("")
        self.summary.setObjectName("subtitle")
        top.addWidget(title)
        top.addStretch()
        top.addWidget(self.summary)
        self.history_table = QTableWidget(0, 4)
        self.history_table.setHorizontalHeaderLabels(["Página", "Guardado", "Archivo", "Huella"])
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setAlternatingRowColors(True)
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hint = QLabel("Haz doble clic en una fila para abrir el PNG.")
        hint.setObjectName("subtitle")
        card_layout.addLayout(top)
        card_layout.addWidget(self.history_table, 1)
        card_layout.addWidget(hint)
        layout.addWidget(card, 1)
        self.history_paths: list[str] = []
        return page

    def settings_card(self, title: str):
        card = self.card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("section")
        layout.addWidget(heading)
        return card, layout

    def build_settings_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 10, 0)
        layout.setSpacing(14)

        # Dispositivo
        device_card, device_layout = self.settings_card("Dispositivo")
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(8)
        self.name = QLabel("No detectado")
        self.identifier = QLabel("—")
        self.firmware = QLabel("—")
        self.area = QLabel("—")
        for row, (label, widget) in enumerate((("Nombre", self.name), ("Identificador", self.identifier),
                                               ("Firmware", self.firmware), ("Área activa", self.area))):
            caption = QLabel(label)
            caption.setObjectName("subtitle")
            grid.addWidget(caption, row, 0)
            grid.addWidget(widget, row, 1)
        grid.setColumnStretch(1, 1)
        device_layout.addLayout(grid)

        # Carpeta
        folder_card, folder_layout = self.settings_card("Carpeta de destino")
        self.output_label = QLabel(str(self.output))
        self.output_label.setObjectName("subtitle")
        self.output_label.setWordWrap(True)
        folder_buttons = QHBoxLayout()
        self.folder_button = QPushButton("Cambiar carpeta…")
        self.open_button = QPushButton("Abrir carpeta")
        folder_buttons.addWidget(self.folder_button)
        folder_buttons.addWidget(self.open_button)
        folder_buttons.addStretch()
        folder_layout.addWidget(self.output_label)
        folder_layout.addLayout(folder_buttons)

        # Sincronización
        sync_card, sync_layout = self.settings_card("Sincronización")
        self.auto_connect = QCheckBox("Buscar y conectar al iniciar")
        self.auto_connect.setChecked(self.settings.value("autoconnect", True, type=bool))
        self.save_local = QCheckBox("Guardar PNG y TXT en local")
        self.save_local.setChecked(True)
        self.show_page = QCheckBox("Mostrar cada página al sincronizarla")
        self.show_page.setChecked(True)
        self.skip_saved = QCheckBox("Omitir páginas ya guardadas (más rápido, no detecta cambios)")
        self.skip_saved.setChecked(False)
        pages_row = QHBoxLayout()
        pages_row.addWidget(QLabel("Máximo de páginas a revisar:"))
        self.max_pages = QSpinBox()
        self.max_pages.setRange(1, 999)
        self.max_pages.setValue(self.settings.value("maxpages", 200, type=int))
        pages_row.addWidget(self.max_pages)
        pages_row.addStretch()
        for widget in (self.auto_connect, self.save_local, self.show_page, self.skip_saved):
            sync_layout.addWidget(widget)
        sync_layout.addLayout(pages_row)

        # Reconocimiento de texto
        ocr_card, ocr_layout = self.settings_card("Reconocimiento de texto")
        self.preprocess = QCheckBox("Preprocesar los trazos antes del OCR (recomendado para letra a mano)")
        self.preprocess.setChecked(self.settings.value("ocr_preprocess", True, type=bool))
        ocr_info = QLabel(
            f"Motor: {LocalOcr.engine_name()} (local y gratuito). El preprocesado separa por líneas, corrige la "
            "inclinación y homogeneiza tamaño y grosor. Compruébalo con tu letra en la sección Medición."
        )
        ocr_info.setObjectName("subtitle")
        ocr_info.setWordWrap(True)
        ocr_layout.addWidget(self.preprocess)
        ocr_layout.addWidget(ocr_info)

        # Apariencia
        look_card, look_layout = self.settings_card("Apariencia")
        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Tema:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Automático (según el sistema)", "auto")
        self.theme_combo.addItem("Claro", "claro")
        self.theme_combo.addItem("Oscuro", "oscuro")
        index = self.theme_combo.findData(self.theme_mode)
        self.theme_combo.setCurrentIndex(index if index >= 0 else 0)
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch()
        look_layout.addLayout(theme_row)

        # Diagnóstico
        debug_card, debug_layout = self.settings_card("Diagnóstico")
        self.debug_frames = QCheckBox("Registrar tramas crudas en el Registro (solo para resolver problemas)")
        debug_layout.addWidget(self.debug_frames)

        for card in (device_card, folder_card, sync_card, ocr_card, look_card, debug_card):
            layout.addWidget(card)
        layout.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        return page

    def build_advanced_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget()
        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.log_view.document().setMaximumBlockCount(2000)
        log_layout.addWidget(self.log_view)

        devices_tab = QWidget()
        devices_layout = QVBoxLayout(devices_tab)
        devices_info = QLabel("Detección informativa de solo lectura. No afecta al ratón ni al teclado.")
        devices_info.setWordWrap(True)
        devices_info.setObjectName("subtitle")
        self.devices_button = QPushButton("Detectar dispositivos")
        self.devices_view = QTextEdit()
        self.devices_view.setReadOnly(True)
        self.devices_view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.devices_view.setPlainText("Pulsa «Detectar dispositivos» para comenzar.")
        devices_layout.addWidget(devices_info)
        devices_layout.addWidget(self.devices_button, 0, Qt.AlignmentFlag.AlignLeft)
        devices_layout.addWidget(self.devices_view, 1)
        tabs.addTab(log_tab, "Registro")
        tabs.addTab(devices_tab, "Hardware")
        layout.addWidget(tabs)
        return page

    def build_menu(self):
        """Menús y atajos de teclado nativos (Ctrl en Windows, Cmd en macOS)."""
        def action(text, handler, shortcut=None, checkable=False):
            act = QAction(text, self)
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
            act.setCheckable(checkable)
            act.triggered.connect(handler)
            return act

        self.act_connect = action("Buscar y conectar", lambda: self.schedule(self.do_connect()), "Ctrl+K")
        self.act_sync = action("Sincronizar contenido", lambda: self.schedule(self.do_sync()), "Ctrl+R")
        self.act_live = action("Escucha pasiva", lambda: self.schedule(self.toggle_live()), "Ctrl+L", True)
        self.act_disconnect = action("Desconectar", lambda: self.schedule(self.manager.disconnect()))
        self.act_open_folder = action("Abrir carpeta de destino", self.open_output_folder, "Ctrl+O")
        self.act_choose_folder = action("Cambiar carpeta de destino…", self.choose_folder)
        self.act_export = action("Exportar transcripciones (.md)…", self.export_markdown, "Ctrl+E")
        self.act_quit = action("Salir", self.close, "Ctrl+Q")
        self.act_quit.setMenuRole(QAction.MenuRole.QuitRole)
        self.act_zoom_in = action("Acercar", lambda: self.set_zoom(self.zoom + 0.25))
        self.act_zoom_in.setShortcut(QKeySequence(QKeySequence.StandardKey.ZoomIn))
        self.act_zoom_out = action("Alejar", lambda: self.set_zoom(self.zoom - 0.25))
        self.act_zoom_out.setShortcut(QKeySequence(QKeySequence.StandardKey.ZoomOut))

        file_menu = self.menuBar().addMenu("Archivo")
        for act in (self.act_open_folder, self.act_choose_folder, self.act_export):
            file_menu.addAction(act)
        file_menu.addSeparator()
        file_menu.addAction(self.act_quit)

        device_menu = self.menuBar().addMenu("Dispositivo")
        for act in (self.act_connect, self.act_sync, self.act_live, self.act_disconnect):
            device_menu.addAction(act)

        view_menu = self.menuBar().addMenu("Ver")
        for index, (label, _icon) in enumerate(self.SECTIONS):
            section_action = action(label, lambda _checked=False, i=index: self.show_section(i), f"Ctrl+{index + 1}")
            view_menu.addAction(section_action)
        view_menu.addSeparator()
        view_menu.addAction(self.act_zoom_in)
        view_menu.addAction(self.act_zoom_out)

        more_menu = QMenu(self)
        for act in (self.act_disconnect, self.act_open_folder, self.act_choose_folder, self.act_export):
            more_menu.addAction(act)
        self.more_button.setMenu(more_menu)

    def connect_signals(self):
        self.log_signal.connect(self.add_log)
        self.state_signal.connect(self.set_state)
        self.live_signal.connect(self.route_live_to_canvas)
        self.battery_signal.connect(self.update_battery_display)
        self.page_signal.connect(self.save_page)
        self.progress_signal.connect(self.update_progress)
        self.devices_signal.connect(self.show_devices)

        self.connect_button.clicked.connect(lambda: self.schedule(self.do_connect()))
        self.sync_button.clicked.connect(lambda: self.schedule(self.do_sync()))
        self.stop_sync_button.clicked.connect(self.do_stop_sync)
        self.live_button.clicked.connect(lambda: self.schedule(self.toggle_live()))
        self.devices_button.clicked.connect(self.scan_input_devices)
        self.folder_button.clicked.connect(self.choose_folder)
        self.open_button.clicked.connect(self.open_output_folder)

        self.canvas.count_changed.connect(lambda value: self.points_label.setText(f"{value} puntos"))
        self.auto_connect.toggled.connect(lambda value: self.settings.setValue("autoconnect", value))
        self.max_pages.valueChanged.connect(lambda value: self.settings.setValue("maxpages", value))
        self.preprocess.toggled.connect(lambda value: self.settings.setValue("ocr_preprocess", value))
        self.theme_combo.currentIndexChanged.connect(lambda _i: self.on_theme_changed())
        self.debug_frames.toggled.connect(self.set_debug_frames)

        self.live_signal.connect(self.on_live_points)
        self.live_signal.connect(self.measure_page.on_live)
        self.ocr_timer.timeout.connect(self.run_live_ocr)
        self.ocr_now_button.clicked.connect(lambda: self.schedule(self.ocr_now()))
        self.ocr_copy_button.clicked.connect(lambda: QApplication.clipboard().setText(self.ocr_view.toPlainText()))
        self.ocr_save_button.clicked.connect(self.save_text_edits)
        self.export_md_button.clicked.connect(self.export_markdown)
        self.ocr_banner_button.clicked.connect(self.on_banner_action)

        self.prev_page_btn.clicked.connect(lambda: self.change_preview_page(-1))
        self.next_page_btn.clicked.connect(lambda: self.change_preview_page(1))
        self.zoom_in_btn.clicked.connect(lambda: self.set_zoom(self.zoom + 0.25))
        self.zoom_out_btn.clicked.connect(lambda: self.set_zoom(self.zoom - 0.25))
        self.clear_button.clicked.connect(self.clear_preview)
        self.page_list.currentItemChanged.connect(self.on_page_selected)
        self.page_search.textChanged.connect(lambda _t: self.filter_pages())
        self.history_table.cellDoubleClicked.connect(self.open_history_file)

        hints = QApplication.instance().styleHints()
        if hasattr(hints, "colorSchemeChanged"):  # Qt >= 6.5: seguir el cambio de tema del sistema en caliente
            hints.colorSchemeChanged.connect(lambda *_args: self.on_system_theme_changed())

    # ------------------------------------------------------------------ Tema, navegación y estado de la ventana
    def apply_theme(self):
        name = detect_system_theme() if self.theme_mode == "auto" else self.theme_mode
        if name not in THEMES:
            name = "oscuro"
        tokens = THEMES[name]
        QApplication.instance().setStyleSheet(build_stylesheet(name))
        for canvas in (self.canvas, self.measure_page.canvas):
            canvas.set_theme(tokens["canvas_bg"], tokens["border"], tokens["muted"])
        for button, (_label, icon_name) in zip(self.nav_buttons, self.SECTIONS):
            button.setIcon(make_nav_icon(icon_name, tokens["muted"], tokens["accent_border"]))

    def on_theme_changed(self):
        self.theme_mode = str(self.theme_combo.currentData())
        self.settings.setValue("theme", self.theme_mode)
        self.apply_theme()

    def on_system_theme_changed(self):
        if self.theme_mode == "auto":
            self.apply_theme()

    def show_section(self, index: int):
        self.commit_text_edits()
        self.stack.setCurrentIndex(index)
        for number, button in enumerate(self.nav_buttons):
            button.setChecked(number == index)
        self.section_title.setText(self.SECTIONS[index][0])
        self.settings.setValue("section", index)

    def restore_window_state(self):
        try:
            geometry = self.settings.value("geometry")
            if geometry:
                self.restoreGeometry(geometry)
            splitter = self.settings.value("notes_splitter")
            if splitter:
                self.notes_splitter.restoreState(splitter)
        except Exception as error:
            print(f"No se pudo restaurar la posición de la ventana: {error}")
        section = self.settings.value("section", 0, type=int)
        self.show_section(section if 0 <= section < len(self.SECTIONS) else 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "toast"):
            QTimer.singleShot(0, self.toast.reposition)

    def show_toast(self, text: str, kind: str = "info", duration: int = 4500):
        self.toast.show_message(text, kind, duration)

    def set_zoom(self, value: float):
        self.zoom = max(1.0, min(3.0, round(value * 4) / 4))
        base_w, base_h = self.canvas_base_size
        if self.zoom <= 1.0:
            self.canvas.setMinimumSize(base_w, base_h)
        else:
            viewport = self.canvas.parentWidget().size()
            self.canvas.setMinimumSize(int(max(base_w, viewport.width()) * self.zoom),
                                       int(max(base_h, viewport.height()) * self.zoom))
        self.zoom_label.setText(f"{int(self.zoom * 100)} %")

    def open_output_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output)))

    # ------------------------------------------------------------------ Lista de páginas (miniaturas y búsqueda)
    def refresh_page_list(self):
        selected = self.current_preview_page
        max_x, max_y = self.manager.protocol.max_x, self.manager.protocol.max_y
        self.page_list.blockSignals(True)
        self.page_list.clear()
        for page in sorted(self.synced_pages):
            digest = self.page_digest(page)
            icon = self.thumb_cache.get(digest)
            if icon is None:
                icon = make_thumbnail(self.synced_pages[page], max_x, max_y)
                self.thumb_cache[digest] = icon
            item = QListWidgetItem(icon, self.page_label(page))
            item.setData(Qt.ItemDataRole.UserRole, page)
            self.page_list.addItem(item)
            if page == selected:
                self.page_list.setCurrentItem(item)
        self.page_list.blockSignals(False)
        total = len(self.synced_pages)
        self.page_count_label.setText(
            "Sin páginas todavía" if not total else f"{total} página" + ("s" if total != 1 else "")
        )
        self.filter_pages()
        if hasattr(self, "measure_page"):
            self.measure_page.refresh_pages()

    def filter_pages(self):
        query = normalize_for_score(self.page_search.text(), True)
        for number in range(self.page_list.count()):
            item = self.page_list.item(number)
            page = item.data(Qt.ItemDataRole.UserRole)
            text = normalize_for_score(self.ocr_texts.get(self.page_digest(page), ""), True)
            item.setHidden(bool(query) and query not in text)

    def select_page_in_list(self, page: int):
        self.page_list.blockSignals(True)
        for number in range(self.page_list.count()):
            item = self.page_list.item(number)
            if item.data(Qt.ItemDataRole.UserRole) == page:
                self.page_list.setCurrentItem(item)
                break
        self.page_list.blockSignals(False)

    def on_page_selected(self, current, _previous):
        if current is None or self.manager.online_enabled:
            return
        page = current.data(Qt.ItemDataRole.UserRole)
        if page == self.current_preview_page and self.shown_digest:
            return
        self.current_preview_page = page
        self.update_canvas_display()

    def register_page(self, page: int, points: list, show: bool, select: bool):
        self.synced_pages[page] = points
        if select:
            self.current_preview_page = page
        self.refresh_page_list()
        if show:
            self.update_canvas_display()

    # ------------------------------------------------------------------ Batería, navegación y vista previa
    def update_battery_display(self, value: int):
        self.battery.setText(f"Batería {value} %")
        if value <= 10:
            self.battery.setObjectName("battery_critical")
            if not self.low_battery_warned:
                self.low_battery_warned = True
                self.show_error("Batería crítica", f"El nivel de batería del Huion Note es del {value} %. Conéctalo al cargador.")
        elif value <= 20:
            self.battery.setObjectName("battery_warning")
        else:
            self.battery.setObjectName("battery_normal")
            self.low_battery_warned = False

        self.battery.style().unpolish(self.battery)
        self.battery.style().polish(self.battery)

    def change_preview_page(self, delta: int):
        if not self.synced_pages or self.manager.online_enabled:
            return
        pages = sorted(self.synced_pages.keys())
        if self.current_preview_page in pages:
            idx = pages.index(self.current_preview_page)
            new_idx = max(0, min(len(pages) - 1, idx + delta))
            self.current_preview_page = pages[new_idx]
        else:
            self.current_preview_page = pages[0]
        self.update_canvas_display()

    def update_canvas_display(self):
        self.commit_text_edits()  # guarda las correcciones manuales de la página que se abandona
        page = self.current_preview_page
        if page is not None and page in self.synced_pages:
            digest = self.page_digest(page)
            self.canvas.set_points(self.synced_pages[page])
            self.shown_digest = digest
            pages = sorted(self.synced_pages.keys())
            self.page_indicator.setText(f"{self.page_label(page)} · {pages.index(page) + 1}/{len(pages)}")
            text = self.ocr_texts.get(digest, "")
            self.set_ocr_text(text, None if text else "Sin transcripción: pulsa «Reconocer»")
            self.select_page_in_list(page)
        else:
            self.canvas.clear()
            self.shown_digest = ""
            self.page_indicator.setText("Página —")
            self.set_ocr_text("")

    def update_nav_enabled(self):
        live = self.manager.online_enabled
        for widget in (self.prev_page_btn, self.next_page_btn, self.page_list):
            widget.setEnabled(not live)
        if live:
            self.page_indicator.setText("En directo")

    def scan_input_devices(self):
        self.devices_button.setEnabled(False)
        self.devices_view.setPlainText("Detectando dispositivos de entrada...")

        async def worker():
            try:
                result = await asyncio.to_thread(InputDeviceScanner.scan)
                self.devices_signal.emit(result)
            except Exception as error:
                self.devices_signal.emit(error)

        self.schedule(worker())

    def show_devices(self, result):
        self.devices_button.setEnabled(True)
        if isinstance(result, Exception):
            self.devices_view.setPlainText(f"Error: {type(result).__name__}: {result}")
            return
        devices = result
        if not devices:
            self.devices_view.setPlainText("No se encontraron dispositivos de entrada.")
            return
        huion = [device for device in devices if device.is_huion_note]
        lines = [f"Dispositivos detectados: {len(devices)}", f"Huion Note identificados: {len(huion)}", ""]
        for index, device in enumerate(devices, 1):
            kind = "HUION NOTE IDENTIFICADO" if device.is_huion_note else "dispositivo"
            lines.extend([
                f"[{index}] {kind}", f"Nombre: {device.name}",
                f"Vendor ID: {device.vendor_id or 'no disponible'}",
                f"Product ID: {device.product_id or 'no disponible'}",
                f"Transporte: {device.transport or 'no disponible'}",
                f"Identificador: {device.registry_id or 'no disponible'}",
                f"Fuente: {device.source}", "",
            ])
        self.devices_view.setPlainText("\n".join(lines))

    def auto_start(self):
        if self.auto_connect.isChecked():
            self.schedule(self.do_connect())

    def add_log(self, text):
        self.log_view.append(f"[{datetime.now():%H:%M:%S}] {text}")

    # ------------------------------------------------------------------ Estado, conexión y sincronización
    def set_state(self, state):
        self.status.setText(state)
        self.status.setObjectName("connected" if state == "Conectado" else "busy" if state in ("Buscando", "Conectando", "Sincronizando") else "disconnected")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

        connected = state in ("Conectado", "Sincronizando")
        connecting = state in ("Buscando", "Conectando")
        can_sync = connected and not self.syncing

        # Un único botón principal según el momento: conectar -> sincronizar -> parar
        self.connect_button.setVisible(not connected)
        self.connect_button.setEnabled(not connecting)
        self.sync_button.setVisible(connected and not self.syncing)
        self.stop_sync_button.setVisible(self.syncing)
        self.live_button.setVisible(connected)
        self.live_button.setEnabled(can_sync)
        self.battery.setVisible(connected)
        self.header_device.setVisible(connected)
        self.page_progress.setVisible(self.syncing)
        self.packet_progress.setVisible(self.syncing)
        self.act_connect.setEnabled(not connected and not connecting)
        self.act_sync.setEnabled(can_sync)
        self.act_live.setEnabled(can_sync)
        self.act_disconnect.setEnabled(connected)

        if connected:
            m = self.manager
            self.header_device.setText(m.device_name)
            self.name.setText(m.device_name)
            self.identifier.setText(m.device_id)
            self.firmware.setText(m.firmware or "No disponible")
            self.area.setText(f"{m.protocol.max_x} × {m.protocol.max_y} · {m.protocol.max_pressure} niveles")
            self.canvas.set_limits(m.protocol.max_x, m.protocol.max_y, m.protocol.max_pressure)
            self.canvas.set_empty_text("Pulsa «Sincronizar» para traer tus notas o activa la escucha pasiva para verlas mientras escribes.")
            if not self.syncing:
                self.footer_label.setText("Listo")
        else:
            self.canvas.set_empty_text("Conecta tu Huion Note para empezar: pulsa «Buscar y conectar».")
            self.footer_label.setText("Sin conexión con el dispositivo")
            self.flush_live_snapshot()
        self.sync_live_controls()

    def sync_live_controls(self):
        live = self.manager.online_enabled
        self.live_button.setChecked(live)
        self.live_button.setText("Escucha pasiva · activa" if live else "Escucha pasiva")
        self.act_live.setChecked(live)
        self.update_nav_enabled()
        if not live:
            self.ocr_status.setText(f"Motor: {LocalOcr.engine_name()}")

    def show_error(self, title, message):
        self.add_log(f"{title}: {message}")
        self.show_toast(f"{title}: {message}", "error", 9000)

    async def do_connect(self):
        try:
            await self.manager.disconnect()
            self.manager.device = None
            await self.manager.scan()
            await self.manager.connect()
            self.set_state("Conectado")
            self.show_toast(f"Conectado a {self.manager.device_name}.", "ok")
        except Exception as error:
            self.set_state("Desconectado")
            detail = f"{type(error).__name__}: {error}"
            self.add_log(f"Error: {detail}")
            self.show_error("Error de conexión", detail)

    async def toggle_live(self):
        try:
            if self.manager.online_enabled:
                await self.manager.disable_online_mode()
                self.ocr_timer.stop()
                self.flush_live_snapshot()
            else:
                await self.manager.enable_online_mode()
                self.ocr_disabled_reason = ""
                self.live_ocr_digest = ""
                self.live_snapshot = []
                self.commit_text_edits()
                self.shown_digest = ""
                self.canvas.clear()
                self.set_ocr_text("", "Escucha activa: escribe en el Huion Note…")
        except Exception as error:
            self.show_error("Error de tiempo real", f"{type(error).__name__}: {error}")
        finally:
            self.sync_live_controls()

    async def do_sync(self):
        if not self.manager.connected:
            return
        self.syncing = True
        self.sync_started = time.monotonic()
        self.ocr_disabled_reason = ""
        self.footer_label.setText("Sincronizando…")
        self.set_state("Sincronizando")
        try:
            checked, nonempty = await self.manager.synchronize(
                self.max_pages.value(),
                lambda page, points: self.page_signal.emit(page, points),
                lambda page, total, received, packets: self.progress_signal.emit(page, total, received, packets),
                self.store,
                self.manager.device_id,
                self.skip_saved.isChecked(),
            )
            self.add_log(f"Sincronización finalizada: {checked} páginas revisadas, {nonempty} con contenido.")
            self.page_progress.setValue(100)
            self.refresh_history()
            message = f"Sincronización terminada: {nonempty} página" + ("s" if nonempty != 1 else "") + " con contenido."
            self.show_toast(message, "ok")
            self.footer_label.setText(message)
            if not self.isActiveWindow():
                QApplication.alert(self, 0)  # avisa en la barra de tareas (Windows) o en el Dock (macOS)
        except Exception as error:
            detail = f"{type(error).__name__}: {error}"
            self.add_log(f"Error de sincronización: {detail}")
            self.show_error("Error de sincronización", detail)
        finally:
            self.syncing = False
            self.set_state("Conectado" if self.manager.connected else "Desconectado")

    def do_stop_sync(self):
        if self.syncing:
            self.manager.cancel_sync = True
            self.add_log("Solicitud de interrupción de sincronización enviada...")
            self.footer_label.setText("Deteniendo la sincronización…")

    @staticmethod
    def format_seconds(seconds: float) -> str:
        seconds = int(seconds)
        return f"{seconds} s" if seconds < 60 else f"{seconds // 60} min {seconds % 60} s"

    def update_progress(self, page, total, received, packets):
        total = max(1, total)
        self.page_progress.setValue(min(100, int(page / total * 100)))
        self.page_progress.setFormat(f"{page} / ~{total} páginas")
        eta = ""
        if page >= 2 and self.sync_started:
            elapsed = time.monotonic() - self.sync_started
            eta = f" · unos {self.format_seconds(max(0.0, elapsed / page * (total - page)))} restantes"
        self.footer_label.setText(f"Sincronizando… {page} de ~{total} páginas{eta}")
        self.packet_progress.setValue(int(received / max(1, packets) * 100) if packets else 0)
        self.packet_progress.setFormat(f"Paquetes {received}/{packets}" if packets else "Consultando…")

    # ------------------------------------------------------------------ Guardado de páginas (PNG + TXT)
    @staticmethod
    def digest(points):
        return hashlib.sha256(";".join(f"{p.x},{p.y},{p.pressure},{int(p.down)}" for p in points).encode()).hexdigest()

    def export_xy(self, point, width: int = PAGE_WIDTH, height: int = PAGE_HEIGHT):
        return (
            point.x / max(1, self.manager.protocol.max_x) * width,
            point.y / max(1, self.manager.protocol.max_y) * height,
        )

    @staticmethod
    def clean_points(points):
        return [point for point in points if not (point.x == 0 and point.y == 0 and point.pressure == 0)]

    def persist_page(self, page, points, text: Optional[str] = None):
        """Escribe el PNG (y el TXT si ya hay texto) de una página nueva y la registra en la base de datos.
        Devuelve (hash, ruta del TXT o None, si se creó una página nueva)."""
        digest = self.digest(points)
        device = self.manager.device_id or "unknown"
        if self.store.exists(device, digest):
            png_known = self.store.png_path_for(digest)
            txt_path = Path(png_known).with_suffix(".txt") if png_known else None
            if txt_path is not None and txt_path.exists():
                self.ocr_texts[digest] = txt_path.read_text(encoding="utf-8")
            return digest, txt_path, False
        if not self.save_local.isChecked():
            return digest, None, False

        folder = self.output / datetime.now().strftime("%Y-%m-%d")
        folder.mkdir(parents=True, exist_ok=True)
        base = f"huion_{page:03d}_{datetime.now():%Y%m%d_%H%M%S}_{digest[:8]}"
        png_path, txt_path = folder / f"{base}.png", folder / f"{base}.txt"
        max_x, max_y = self.manager.protocol.max_x, self.manager.protocol.max_y
        strokes = Protocol.strokes(points, max_x, max_y)
        width, height = page_dimensions(max_x, max_y)

        image = QImage(width, height, QImage.Format.Format_ARGB32)
        image.fill(QColor("#f7f7f4"))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#111318"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        for stroke in strokes:
            xy = [QPointF(*self.export_xy(p, width, height)) for p in stroke]
            for index in range(1, len(xy)):
                painter.drawLine(xy[index - 1], xy[index])
        painter.end()
        image.save(str(png_path), "PNG")

        points_json = json.dumps(
            [[p.x, p.y, p.pressure, int(p.down), p.status] for p in points], separators=(",", ":")
        )
        self.store.add(device, digest, page, png_path, points_json)
        if text is not None:
            self.ocr_texts[digest] = text
            if text:
                txt_path.write_text(text, encoding="utf-8")
        return digest, txt_path, True

    def save_page(self, page, points):
        """Página recibida por sincronización: se guarda, se muestra y se lanza su OCR."""
        points = self.clean_points(points)
        digest, txt_path, created = self.persist_page(page, points)
        self.register_page(page, points, show=self.show_page.isChecked(), select=True)
        if created:
            self.refresh_history()
            self.add_log(f"Página {page} sincronizada y guardada (PNG).")
        if digest not in self.ocr_texts:
            self.schedule(self.ocr_saved_page(page, points, digest, txt_path))

    # ------------------------------------------------------------------ Escritura en directo: guardado automático por página
    def next_live_key(self) -> int:
        self.live_key_counter += 1
        return self.live_key_counter

    def flush_live_snapshot(self, wait: bool = False):
        """Guarda lo escrito en directo como una página (al cambiar de página, parar la escucha o desconectar)."""
        snapshot, self.live_snapshot = self.live_snapshot, []
        if not snapshot or not self.save_local.isChecked():
            return
        key = self.next_live_key()
        if wait:  # al cerrar la aplicación no hay tiempo para tareas asíncronas: se guarda ya, sin OCR nuevo
            points = self.clean_points(snapshot)
            if Protocol.strokes(points, self.manager.protocol.max_x, self.manager.protocol.max_y):
                self.persist_page(key, points, self.ocr_texts.get(self.digest(points)))
            return
        self.schedule(self.autosave_live(snapshot, key))

    async def autosave_live(self, snapshot, key: int):
        points = self.clean_points(snapshot)
        if not Protocol.strokes(points, self.manager.protocol.max_x, self.manager.protocol.max_y):
            return
        digest = self.digest(points)
        text = self.ocr_texts.get(digest)
        if text is None and not self.ocr_disabled_reason:
            text = await self.recognize_points(points, quiet=True)
        _digest, _txt_path, created = self.persist_page(key, points, text)
        if created:
            self.register_page(key, points, show=False, select=False)
            self.refresh_history()
            self.add_log(f"Escritura en directo guardada como «{self.page_label(key)}».")
            self.show_toast(f"Escritura en directo guardada como «{self.page_label(key)}».", "ok")

    # ------------------------------------------------------------------ OCR local
    def set_ocr_text(self, text: str, status: Optional[str] = None):
        self.ocr_view.setPlainText(text)
        self.ocr_status.setText(status if status is not None else f"Motor: {LocalOcr.engine_name()}")

    def clear_preview(self):
        self.canvas.clear()
        self.ocr_timer.stop()
        self.live_ocr_digest = ""
        self.live_snapshot = []
        self.shown_digest = ""
        self.set_ocr_text("")

    def route_live_to_canvas(self, points):
        """El lienzo solo reacciona a los datos en directo mientras la escucha pasiva está activa."""
        if self.manager.online_enabled:
            self.canvas.add_points(points)

    def on_live_points(self, points):
        """Cada vez que llegan trazos en directo, se reinicia la espera para lanzar el OCR."""
        if not self.manager.online_enabled:
            return
        if points is None:  # el dispositivo cambió de página: se guarda la anterior y se empieza de cero
            self.ocr_timer.stop()
            self.live_ocr_digest = ""
            self.flush_live_snapshot()
            self.set_ocr_text("", "Escucha activa: página nueva")
            return
        self.live_snapshot = list(self.canvas.raw_points)
        if not self.ocr_disabled_reason:
            self.ocr_timer.start()

    def run_live_ocr(self):
        if not self.manager.online_enabled or self.ocr_disabled_reason or not self.canvas.raw_points:
            return
        if self.ocr_lock.locked():
            self.ocr_timer.start()  # hay un OCR en curso: se vuelve a intentar al terminar
            return
        self.schedule(self.ocr_live())

    async def ocr_live(self):
        points = list(self.canvas.raw_points)
        digest = self.digest(points)
        if digest == self.live_ocr_digest:
            return
        text = await self.recognize_points(points, quiet=True)
        if text is None:
            return
        self.live_ocr_digest = digest
        self.ocr_texts[digest] = text  # se reutiliza al guardar la página en directo
        if self.manager.online_enabled and self.canvas.raw_points:  # la vista no se limpió mientras tanto
            self.set_ocr_text(text, None if text else "Sin texto reconocido")

    async def ocr_now(self):
        """Botón «Reconocer»: reconoce lo que muestra la vista previa y, si es una página guardada, escribe su TXT."""
        self.ocr_disabled_reason = ""
        points = list(self.canvas.raw_points)
        if not points:
            self.ocr_status.setText("No hay trazos en la vista previa")
            return
        text = await self.recognize_points(points, quiet=False)
        if text is None:
            return
        digest = self.digest(points)
        self.ocr_texts[digest] = text
        self.set_ocr_text(text, None if text else "Sin texto reconocido")
        path = self.write_txt_for(digest, text)
        if path is not None:
            self.add_log(f"Texto guardado en {path.name}")
        if self.page_search.text():
            self.filter_pages()

    def write_txt_for(self, digest: str, text: str) -> Optional[Path]:
        png = self.store.png_path_for(digest)
        if not png or not text:
            return None
        txt_path = Path(png).with_suffix(".txt")
        txt_path.parent.mkdir(parents=True, exist_ok=True)
        txt_path.write_text(text, encoding="utf-8")
        return txt_path

    async def recognize_points(self, points, quiet: bool, method: Optional[str] = None) -> Optional[str]:
        """Ejecuta el OCR local. Devuelve el texto, o None si no se pudo (sin molestar con avisos si quiet)."""
        method = method or ("preprocesado" if self.preprocess.isChecked() else "directo")
        max_x, max_y = self.manager.protocol.max_x, self.manager.protocol.max_y
        strokes = Protocol.strokes(points, max_x, max_y)
        if not strokes:
            return ""
        async with self.ocr_lock:
            if quiet and self.ocr_disabled_reason:
                return None
            self.ocr_status.setText("Reconociendo…")
            try:
                if method == "preprocesado":
                    chunks = await asyncio.to_thread(preprocess_for_ocr, strokes)  # geometría pura, fuera del hilo de la interfaz
                    pngs = [render_chunk_png(chunk) for chunk in chunks]
                else:
                    pngs = [render_ocr_png(strokes, max_x, max_y)]
                texts = await asyncio.to_thread(LocalOcr.recognize_many, pngs, self.ocr_languages) if pngs else []
                text = "\n".join(item for item in texts if item).strip()
            except OcrUnavailable as error:
                self.ocr_disabled_reason = str(error)
                self.ocr_status.setText("OCR no disponible")
                self.add_log(f"OCR no disponible: {error}")
                self.show_ocr_banner(str(error))
                if not quiet:
                    self.show_error("OCR local", str(error))
                return None
            except Exception as error:
                detail = f"{type(error).__name__}: {error}"
                self.ocr_status.setText("Error de OCR (ver Avanzado › Registro)")
                self.add_log(f"Error de OCR: {detail}")
                if not quiet:
                    self.show_error("Error de OCR", detail)
                return None
            self.hide_ocr_banner()
            self.ocr_status.setText(f"Motor: {LocalOcr.engine_name()}")
            return text

    async def ocr_saved_page(self, page, points, digest, txt_path: Optional[Path]):
        """OCR de una página sincronizada y guardado de su TXT junto al PNG."""
        if self.ocr_disabled_reason:
            return
        text = await self.recognize_points(points, quiet=True)
        if text is None:
            return
        self.ocr_texts[digest] = text
        if text and txt_path is not None:
            txt_path.parent.mkdir(parents=True, exist_ok=True)
            txt_path.write_text(text, encoding="utf-8")
            self.add_log(f"Página {page}: texto reconocido y guardado en {txt_path.name}")
        elif not text:
            self.add_log(f"Página {page}: el OCR no reconoció texto.")
        if self.shown_digest == digest and not self.manager.online_enabled:
            self.set_ocr_text(text, None if text else "Sin texto reconocido")
        if self.page_search.text():
            self.filter_pages()

    # ------------------------------------------------------------------ Aviso accionable del OCR
    def show_ocr_banner(self, message: str):
        system = platform.system()
        lowered = message.lower()
        label, self._banner_action = "", None
        if system == "Windows" and "idioma" in lowered:
            label, self._banner_action = "Abrir ajustes de idioma", self.open_language_settings
        elif system == "Darwin" and "pyobjc" in lowered:
            label, self._banner_action = "Copiar comando de instalación", self.copy_install_command
        self.ocr_banner_label.setText(message)
        self.ocr_banner_button.setText(label)
        self.ocr_banner_button.setVisible(self._banner_action is not None)
        self.ocr_banner.show()

    def hide_ocr_banner(self):
        self.ocr_banner.hide()

    def on_banner_action(self):
        if self._banner_action is not None:
            self._banner_action()

    def open_language_settings(self):
        QDesktopServices.openUrl(QUrl("ms-settings:regionlanguage"))

    def copy_install_command(self):
        QApplication.clipboard().setText("pip install pyobjc-framework-Vision")
        self.show_toast("Comando copiado. Pégalo en la Terminal y vuelve a pulsar «Reconocer».", "ok", 7000)

    # ------------------------------------------------------------------ Edición y exportación del texto
    def commit_text_edits(self):
        """Guarda las correcciones manuales de la página mostrada antes de cambiar de página o de sección."""
        digest = self.shown_digest
        if not digest or self.manager.online_enabled:
            return
        text = self.ocr_view.toPlainText().strip()
        previous = self.ocr_texts.get(digest, "").strip()
        if text == previous or (not text and digest not in self.ocr_texts):
            return
        self.ocr_texts[digest] = text
        self.write_txt_for(digest, text)
        if self.page_search.text():
            self.filter_pages()

    def save_text_edits(self):
        if not self.shown_digest:
            self.show_toast("Abre una página guardada para poder guardar su texto.", "warn")
            return
        self.commit_text_edits()
        self.show_toast("Cambios guardados.", "ok")

    def export_markdown(self):
        self.commit_text_edits()
        parts = []
        for page in sorted(self.synced_pages):
            text = self.ocr_texts.get(self.page_digest(page), "").strip()
            if text:
                parts.append(f"## {self.page_label(page)}\n\n{text}")
        if not parts:
            self.show_toast("Todavía no hay texto reconocido que exportar.", "warn")
            return
        path = self.output / f"transcripciones_{datetime.now():%Y%m%d_%H%M%S}.md"
        path.write_text("# Notas del Huion Note\n\n" + "\n\n---\n\n".join(parts) + "\n", encoding="utf-8")
        self.add_log(f"Transcripciones exportadas en {path}")
        self.show_toast(f"Exportado: {path.name}", "ok")

    # ------------------------------------------------------------------ Diagnóstico, carpeta e historial
    def set_debug_frames(self, value: bool):
        self.manager.debug_frames = value
        self.manager.debug_left = 150 if value else 0
        if value:
            self.add_log("Registro de tramas crudas activado (se muestran las primeras 150 de cada operación).")

    def choose_folder(self):
        selected = QFileDialog.getExistingDirectory(self, "Carpeta de destino", str(self.output))
        if selected:
            self.output = Path(selected)
            self.settings.setValue("output", selected)
            self.output_label.setText(selected)
            self.show_toast("Carpeta de destino actualizada.", "ok")

    def refresh_history(self):
        rows = self.store.history()
        self.history_table.setRowCount(len(rows))
        self.history_paths = []
        for row, (page, saved_at, png_path, digest) in enumerate(rows):
            values = [self.page_label(page), str(saved_at)[:16].replace("T", " "), png_path, digest[:12]]
            for column, value in enumerate(values):
                self.history_table.setItem(row, column, QTableWidgetItem(value))
            self.history_paths.append(png_path)
        self.summary.setText(f"{self.store.count()} guardadas")

    def open_history_file(self, row: int, _column: int):
        if 0 <= row < len(self.history_paths):
            path = Path(self.history_paths[row])
            if path.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
            else:
                self.show_toast("El archivo ya no existe en esa ubicación.", "warn")

    def closeEvent(self, event: QCloseEvent):
        self.commit_text_edits()
        self.flush_live_snapshot(wait=True)
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("notes_splitter", self.notes_splitter.saveState())
        for task in list(self.tasks):
            task.cancel()
        self.settings.sync()
        self.store.close()
        event.accept()


def main():
    global _SYSTEM_THEME_AT_START
    if platform.system() not in ("Darwin", "Windows"):
        raise SystemExit("Solo compatible con macOS y Windows")
    app = QApplication(sys.argv)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationName(APP_NAME)
    # Tema del sistema leído ANTES de cambiar el estilo (en Qt < 6.5 es la única forma de conocerlo).
    palette = app.palette()
    _SYSTEM_THEME_AT_START = "oscuro" if palette.color(QPalette.ColorRole.Window).lightness() < 128 else "claro"
    app.setStyle("Fusion")
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    window = MainWindow()
    window.show()
    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
