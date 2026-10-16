from __future__ import annotations

import asyncio
import hashlib
import json
import platform
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from PySide6.QtCore import QBuffer, QIODevice, QLocale, QPointF, QRectF, Qt, QSettings, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QCloseEvent, QDesktopServices, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea,
    QSpinBox, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)
from qasync import QEventLoop

APP_NAME = "Huion Note Sync"
APP_VERSION = "2.5.0"
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



def page_dimensions(max_x: int, max_y: int, width: int = PAGE_WIDTH) -> tuple[int, int]:
    """Tamaño de exportación que conserva la proporción real del área activa del dispositivo."""
    return width, max(1, round(width * max(1, max_y) / max(1, max_x)))

# Estilo UX/UI Avanzado - Material Design 3 (Dark Mode Refinado)
STYLE = """
QWidget { 
    background: #0b0d10; 
    color: #e2e8f0; 
    font-family: 'Segoe UI', 'Roboto', -apple-system, sans-serif; 
    font-size: 13px; 
}
QFrame#card { 
    background: #141820; 
    border: 1px solid #1e2530; 
    border-radius: 14px; 
}
QLabel#title { 
    font-size: 20px; 
    font-weight: 700; 
    color: #ffffff; 
}
QLabel#subtitle { 
    color: #8c9bae; 
    font-size: 12px; 
}
QLabel#section { 
    font-size: 14px; 
    font-weight: 600; 
    color: #f8fafc; 
}

/* Indicadores de Estado */
QLabel#connected { background: #064e3b; color: #34d399; border: 1px solid #059669; border-radius: 10px; padding: 5px 12px; font-weight: 600; }
QLabel#busy { background: #78350f; color: #fbbf24; border: 1px solid #d97706; border-radius: 10px; padding: 5px 12px; font-weight: 600; }
QLabel#disconnected { background: #7f1d1d; color: #f87171; border: 1px solid #dc2626; border-radius: 10px; padding: 5px 12px; font-weight: 600; }

/* Estados de Batería Dinámicos */
QLabel#battery_normal { background: #1a2230; color: #34d399; border: 1px solid #283548; border-radius: 6px; padding: 3px 8px; font-weight: 600; }
QLabel#battery_warning { background: #78350f; color: #fbbf24; border: 1px solid #d97706; border-radius: 6px; padding: 3px 8px; font-weight: 600; }
QLabel#battery_critical { background: #991b1b; color: #fca5a5; border: 1px solid #ef4444; border-radius: 6px; padding: 3px 8px; font-weight: 700; }

/* Botones Modernos */
QPushButton { 
    background: #1e2530; 
    border: 1px solid #283548; 
    border-radius: 8px; 
    padding: 7px 14px; 
    color: #f1f5f9; 
    font-weight: 500; 
}
QPushButton:hover { 
    background: #263040; 
    border-color: #3b4d66; 
}
QPushButton:pressed { 
    background: #171d26; 
}
QPushButton:disabled { 
    background: #11151c; 
    color: #4a5568; 
    border-color: #171d26; 
}

QPushButton#primary { 
    background: #2563eb; 
    border-color: #3b82f6; 
    color: #ffffff; 
    font-weight: 600; 
}
QPushButton#primary:hover { 
    background: #1d4ed8; 
}

QPushButton#danger { 
    background: #dc2626; 
    border-color: #ef4444; 
    color: #ffffff; 
    font-weight: 600; 
}
QPushButton#danger:hover { 
    background: #b91c1c; 
}

QTextEdit { 
    background: #07090c; 
    border: 1px solid #1e2530; 
    border-radius: 8px; 
    color: #cbd5e1; 
    font-family: 'JetBrains Mono', Consolas, monospace; 
    font-size: 12px; 
    padding: 8px; 
}
QTabWidget::pane { 
    border: 1px solid #1e2530; 
    border-radius: 10px; 
    background: #141820; 
}
QTabBar::tab { 
    background: #141820; 
    border: 1px solid #1e2530; 
    padding: 8px 14px; 
    color: #8c9bae; 
    border-top-left-radius: 6px; 
    border-top-right-radius: 6px; 
    margin-right: 2px; 
    font-weight: 500; 
}
QTabBar::tab:selected { 
    background: #1e2530; 
    color: #ffffff; 
    border-bottom: 2px solid #3b82f6; 
    font-weight: 600; 
}
QProgressBar { 
    background: #07090c; 
    border: 1px solid #1e2530; 
    border-radius: 6px; 
    text-align: center; 
    height: 16px; 
    color: #f1f5f9; 
    font-weight: 600; 
    font-size: 11px;
}
QProgressBar::chunk { 
    background: #2563eb; 
    border-radius: 5px; 
}
QSpinBox { 
    background: #07090c; 
    border: 1px solid #283548; 
    border-radius: 6px; 
    padding: 4px; 
    color: #f1f5f9; 
}
QScrollArea { 
    border: none; 
    background: transparent; 
}
"""


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
                checked = 0
                nonempty = 0
                consecutive_empty = 0

                for page in range(scan_limit):
                    if self.cancel_sync:
                        self.log("Sincronización detenida de forma segura por el usuario.")
                        break
                    if not self.connected:
                        raise RuntimeError("Se perdió la conexión con el Huion Note durante la sincronización")

                    progress_callback(page, scan_limit, 0, 0)

                    # Por defecto se vuelve a descargar todo: una página puede haber cambiado desde la
                    # última vez, y los duplicados ya se descartan por hash de contenido.
                    if skip_saved and page_store.page_exists(device_id, page):
                        checked += 1
                        nonempty += 1
                        consecutive_empty = 0
                        progress_callback(page + 1, scan_limit, 0, 0)
                        continue

                    try:
                        points = await self.download_page(
                            page,
                            lambda received, total, current=page: progress_callback(
                                current, scan_limit, received, total
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

                    progress_callback(page + 1, scan_limit, 0, 0)

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
param([string]$ImagePath, [string]$OutPath, [string]$Languages)
$ErrorActionPreference = 'Stop'

function Write-Result($ok, $text, $err) {
    $json = @{ ok = $ok; text = $text; error = $err } | ConvertTo-Json -Compress
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

    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($ImagePath)) ([Windows.Storage.StorageFile])
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

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

    $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    $lines = @($result.Lines | ForEach-Object { $_.Text })
    Write-Result $true ($lines -join [Environment]::NewLine) ''
} catch {
    Write-Result $false '' ($_.Exception.Message)
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
        system = platform.system()
        if system == "Windows":
            return LocalOcr._recognize_windows(png, languages)
        if system == "Darwin":
            return LocalOcr._recognize_macos(png, languages)
        raise OcrUnavailable("El OCR local solo está disponible en Windows y macOS.")

    @staticmethod
    def _recognize_windows(png: bytes, languages: list[str]) -> str:
        with tempfile.TemporaryDirectory(prefix="huion_ocr_") as folder:
            image_path = Path(folder) / "page.png"
            script_path = Path(folder) / "ocr.ps1"
            out_path = Path(folder) / "result.json"
            image_path.write_bytes(png)
            script_path.write_text(WINDOWS_OCR_SCRIPT, encoding="utf-8")
            try:
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                     "-File", str(script_path), "-ImagePath", str(image_path),
                     "-OutPath", str(out_path), "-Languages", ",".join(languages)],
                    capture_output=True, text=True, timeout=90, check=False,
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
        if not data.get("ok"):
            error = str(data.get("error", "error desconocido"))
            if "NO_OCR_LANGUAGE" in error:
                raise OcrUnavailable(
                    "Windows no tiene ningún idioma con OCR instalado. Ve a Configuración > Hora e idioma > "
                    "Idioma y región, añade Español (o tu idioma) e instala sus funciones de idioma, incluido "
                    "el reconocimiento óptico de caracteres."
                )
            raise RuntimeError(f"Error del OCR de Windows: {error}")
        return str(data.get("text", "")).replace("\r\n", "\n").strip()

    @staticmethod
    def _recognize_macos(png: bytes, languages: list[str]) -> str:
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

        def run() -> str:
            data = Foundation.NSData.dataWithBytes_length_(png, len(png))
            handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(data, {})
            request = Vision.VNRecognizeTextRequest.alloc().init()
            request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
            request.setUsesLanguageCorrection_(True)
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

        if pool is not None:
            with pool:
                return run()
        return run()


def render_ocr_png(strokes: list[list[PenPoint]], max_x: int, max_y: int) -> bytes:
    """PNG negro sobre blanco, recortado al contenido y con margen, pensado para el OCR."""
    xs = [point.x for stroke in strokes for point in stroke]
    ys = [point.y for stroke in strokes for point in stroke]
    low_x, high_x, low_y, high_y = min(xs), max(xs), min(ys), max(ys)
    box_w, box_h = max(1, high_x - low_x), max(1, high_y - low_y)
    base_scale = 1560 / max(1, max(max_x, max_y))
    scale = min(2400 / max(box_w, box_h), base_scale * 2.5)
    margin = 60
    width = int(box_w * scale) + margin * 2
    height = int(box_h * scale) + margin * 2
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#ffffff"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#000000"), 4.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    for stroke in strokes:
        if not stroke:
            continue
        path = QPainterPath()
        first = QPointF((stroke[0].x - low_x) * scale + margin, (stroke[0].y - low_y) * scale + margin)
        path.moveTo(first)
        if len(stroke) == 1:
            path.lineTo(QPointF(first.x() + 0.1, first.y() + 0.1))
        for point in stroke[1:]:
            path.lineTo(QPointF((point.x - low_x) * scale + margin, (point.y - low_y) * scale + margin))
        painter.drawPath(path)
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    data = bytes(buffer.data())
    buffer.close()
    return data


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
        self.setMinimumSize(500, 680)

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
        painter.fillRect(self.rect(), QColor("#07090c"))
        rect = self.page_rect()
        painter.setPen(QPen(QColor("#1e2530")))
        painter.setBrush(QColor("#f7f7f4"))
        painter.drawRoundedRect(rect, 8, 8)
        
        # UX Empty State cuando no hay trazos ni página activa
        if not self.strokes and not self.current:
            painter.setPen(QColor("#64748b"))
            painter.setFont(self.font())
            painter.drawText(
                rect, 
                Qt.AlignmentFlag.AlignCenter, 
                "No hay contenido para mostrar.\nConecta tu Huion Note y pulsa Sincronizar."
            )
            return

        for stroke in self.strokes:
            self.draw_stroke(painter, stroke, rect)
        self.draw_stroke(painter, self.current, rect)


class MainWindow(QMainWindow):
    log_signal = Signal(str)
    state_signal = Signal(str)
    live_signal = Signal(object)
    battery_signal = Signal(int)
    page_signal = Signal(int, object)
    progress_signal = Signal(int, int, int, int)
    devices_signal = Signal(object)

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
        self.resize(1220, 840)
        self.build_ui()
        self.connect_signals()
        self.set_state("Desconectado")
        self.refresh_history()
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

    def build_ui(self):
        root_widget = QWidget()
        self.setCentralWidget(root_widget)
        root = QVBoxLayout(root_widget)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)
        
        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        subtitle = QLabel("Panel de sincronización profesional y visor de notas manuscritas")
        subtitle.setObjectName("subtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch()
        self.status = QLabel("Desconectado")
        header.addWidget(self.status)
        root.addLayout(header)

        info = self.card()
        grid = QGridLayout(info)
        grid.setContentsMargins(20, 18, 20, 18)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(12)

        section = QLabel("Dispositivo Conectado")
        section.setObjectName("section")
        grid.addWidget(section, 0, 0, 1, 4)

        self.name = QLabel("No detectado")
        self.identifier = QLabel("—")
        self.firmware = QLabel("—")
        self.battery = QLabel("—")
        self.battery.setObjectName("battery_normal")
        self.area = QLabel("—")

        grid.addWidget(QLabel("<b>Nombre:</b>"), 1, 0)
        grid.addWidget(self.name, 1, 1)
        grid.addWidget(QLabel("<b>Identificador:</b>"), 1, 2)
        grid.addWidget(self.identifier, 1, 3)

        grid.addWidget(QLabel("<b>Firmware:</b>"), 2, 0)
        grid.addWidget(self.firmware, 2, 1)
        grid.addWidget(QLabel("<b>Batería:</b>"), 2, 2)
        grid.addWidget(self.battery, 2, 3)

        grid.addWidget(QLabel("<b>Área Activa:</b>"), 3, 0)
        grid.addWidget(self.area, 3, 1, 1, 3)

        buttons_layout = QVBoxLayout()
        buttons_layout.setSpacing(10)

        primary_row = QHBoxLayout()
        self.connect_button = QPushButton("Buscar y conectar")
        self.connect_button.setObjectName("primary")
        self.disconnect_button = QPushButton("Desconectar")
        self.sync_button = QPushButton("Sincronizar contenido")
        self.sync_button.setObjectName("primary")
        self.stop_sync_button = QPushButton("Parar sincronización")
        self.stop_sync_button.setObjectName("danger")
        self.stop_sync_button.setEnabled(False)

        for btn in (self.connect_button, self.disconnect_button, self.sync_button, self.stop_sync_button):
            primary_row.addWidget(btn)
        primary_row.addStretch()

        secondary_row = QHBoxLayout()
        self.live_button = QPushButton("Activar escucha pasiva")
        self.devices_button = QPushButton("Detectar dispositivos")
        self.folder_button = QPushButton("Cambiar carpeta")
        self.open_button = QPushButton("Abrir en explorador")

        for btn in (self.live_button, self.devices_button, self.folder_button, self.open_button):
            secondary_row.addWidget(btn)
        secondary_row.addStretch()

        buttons_layout.addLayout(primary_row)
        buttons_layout.addLayout(secondary_row)

        grid.addLayout(buttons_layout, 4, 0, 1, 4)

        self.output_label = QLabel(str(self.output))
        self.output_label.setObjectName("subtitle")
        grid.addWidget(QLabel("<b>Carpeta destino:</b>"), 5, 0)
        grid.addWidget(self.output_label, 5, 1, 1, 3)

        root.addWidget(info)

        body = QHBoxLayout()
        body.setSpacing(16)
        
        left = self.card()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(18, 18, 18, 18)
        
        canvas_header = QHBoxLayout()
        canvas_title = QLabel("Vista previa y navegación")
        canvas_title.setObjectName("section")
        
        self.prev_page_btn = QPushButton("◀ Anterior")
        self.page_indicator = QLabel("Página —")
        self.next_page_btn = QPushButton("Siguiente ▶")
        self.points_label = QLabel("0 puntos")
        clear_button = QPushButton("Limpiar vista")
        
        canvas_header.addWidget(canvas_title)
        canvas_header.addStretch()
        canvas_header.addWidget(self.prev_page_btn)
        canvas_header.addWidget(self.page_indicator)
        canvas_header.addWidget(self.next_page_btn)
        canvas_header.addWidget(self.points_label)
        canvas_header.addWidget(clear_button)
        
        left_layout.addLayout(canvas_header)
        self.canvas = Canvas()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.canvas)
        left_layout.addWidget(scroll, 1)

        ocr_header = QHBoxLayout()
        ocr_title = QLabel("Texto reconocido (OCR local)")
        ocr_title.setObjectName("section")
        self.ocr_status = QLabel(f"Motor: {LocalOcr.engine_name()}")
        self.ocr_status.setObjectName("subtitle")
        self.ocr_now_button = QPushButton("Reconocer ahora")
        self.ocr_copy_button = QPushButton("Copiar texto")
        ocr_header.addWidget(ocr_title)
        ocr_header.addStretch()
        ocr_header.addWidget(self.ocr_status)
        ocr_header.addWidget(self.ocr_now_button)
        ocr_header.addWidget(self.ocr_copy_button)
        self.ocr_view = QTextEdit()
        self.ocr_view.setReadOnly(True)
        self.ocr_view.setMaximumHeight(150)
        self.ocr_view.setPlaceholderText("Activa la escucha pasiva y escribe en el Huion Note: el texto reconocido aparecerá aquí.")
        self.ocr_view.setStyleSheet("font-family: 'Segoe UI', 'Roboto', sans-serif; font-size: 14px;")
        left_layout.addLayout(ocr_header)
        left_layout.addWidget(self.ocr_view)
        clear_button.clicked.connect(self.clear_preview)

        right = self.card()
        right.setMinimumWidth(380)
        right.setMaximumWidth(450)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(14, 14, 14, 14)
        
        tabs = QTabWidget()
        
        options = QWidget()
        options_layout = QVBoxLayout(options)
        options_layout.setSpacing(14)
        self.save_local = QCheckBox("Guardar PNG y TXT en local")
        self.save_local.setChecked(True)
        self.auto_connect = QCheckBox("Buscar y conectar al iniciar")
        self.auto_connect.setChecked(self.settings.value("autoconnect", True, type=bool))
        self.show_page = QCheckBox("Mostrar páginas sincronizadas")
        self.show_page.setChecked(True)
        self.skip_saved = QCheckBox("Omitir páginas ya guardadas (más rápido, no detecta cambios)")
        self.skip_saved.setChecked(False)
        self.debug_frames = QCheckBox("Registrar tramas crudas en el Registro (diagnóstico)")
        
        row = QHBoxLayout()
        row.addWidget(QLabel("Máximo de páginas:"))
        self.max_pages = QSpinBox()
        self.max_pages.setRange(1, 999)
        self.max_pages.setValue(self.settings.value("maxpages", 200, type=int))
        row.addWidget(self.max_pages)
        row.addStretch()
        
        self.page_progress = QProgressBar()
        self.page_progress.setFormat("Sin sincronización activa")
        self.packet_progress = QProgressBar()
        self.packet_progress.setFormat("Paquetes: 0/0")
        self.summary = QLabel()
        
        for widget in (self.save_local, self.auto_connect, self.show_page, self.skip_saved, self.debug_frames):
            options_layout.addWidget(widget)
        options_layout.addLayout(row)
        options_layout.addWidget(self.page_progress)
        options_layout.addWidget(self.packet_progress)
        options_layout.addWidget(self.summary)
        options_layout.addStretch()

        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.document().setMaximumBlockCount(2000)
        log_layout.addWidget(self.log_view)

        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)
        self.history_view = QTextEdit()
        self.history_view.setReadOnly(True)
        history_layout.addWidget(self.history_view)

        devices_tab = QWidget()
        devices_layout = QVBoxLayout(devices_tab)
        devices_info = QLabel("Detección informativa de solo lectura. No afecta al ratón ni al teclado.")
        devices_info.setWordWrap(True)
        devices_info.setObjectName("subtitle")
        self.devices_view = QTextEdit()
        self.devices_view.setReadOnly(True)
        self.devices_view.setPlainText("Pulsa Detectar dispositivos para comenzar.")
        devices_layout.addWidget(devices_info)
        devices_layout.addWidget(self.devices_view, 1)

        tabs.addTab(options, "Ajustes")
        tabs.addTab(log_tab, "Registro")
        tabs.addTab(history_tab, "Historial")
        tabs.addTab(devices_tab, "Hardware")
        
        right_layout.addWidget(tabs)
        body.addWidget(left, 1)
        body.addWidget(right)
        root.addLayout(body, 1)

        # Mostrar la primera página cargada en memoria si existe
        if self.synced_pages:
            self.update_canvas_display()

    def connect_signals(self):
        self.log_signal.connect(self.add_log)
        self.state_signal.connect(self.set_state)
        self.live_signal.connect(self.canvas.add_points)
        self.battery_signal.connect(self.update_battery_display)
        self.page_signal.connect(self.save_page)
        self.progress_signal.connect(self.update_progress)
        self.devices_signal.connect(self.show_devices)
        
        self.connect_button.clicked.connect(lambda: self.schedule(self.do_connect()))
        self.disconnect_button.clicked.connect(lambda: self.schedule(self.manager.disconnect()))
        self.sync_button.clicked.connect(lambda: self.schedule(self.do_sync()))
        self.stop_sync_button.clicked.connect(self.do_stop_sync)
        self.live_button.clicked.connect(lambda: self.schedule(self.toggle_live()))
        self.devices_button.clicked.connect(self.scan_input_devices)
        self.folder_button.clicked.connect(self.choose_folder)
        self.open_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output))))
        
        self.canvas.count_changed.connect(lambda value: self.points_label.setText(f"{value} puntos"))
        self.auto_connect.toggled.connect(lambda value: self.settings.setValue("autoconnect", value))
        self.max_pages.valueChanged.connect(lambda value: self.settings.setValue("maxpages", value))
        
        self.debug_frames.toggled.connect(self.set_debug_frames)
        self.live_signal.connect(self.on_live_points)
        self.ocr_timer.timeout.connect(self.run_live_ocr)
        self.ocr_now_button.clicked.connect(lambda: self.schedule(self.ocr_now()))
        self.ocr_copy_button.clicked.connect(lambda: QApplication.clipboard().setText(self.ocr_view.toPlainText()))

        self.prev_page_btn.clicked.connect(lambda: self.change_preview_page(-1))
        self.next_page_btn.clicked.connect(lambda: self.change_preview_page(1))

    def update_battery_display(self, value: int):
        self.battery.setText(f"{value}%")
        if value <= 10:
            self.battery.setObjectName("battery_critical")
            if not self.low_battery_warned:
                self.low_battery_warned = True
                self.show_error("¡Batería Crítica!", f"El nivel de batería del Huion Note es del {value}%. Por favor, conecta el dispositivo al cargador.")
        elif value <= 20:
            self.battery.setObjectName("battery_warning")
        else:
            self.battery.setObjectName("battery_normal")
            self.low_battery_warned = False
        
        self.battery.style().unpolish(self.battery)
        self.battery.style().polish(self.battery)

    def change_preview_page(self, delta: int):
        if not self.synced_pages:
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
        if self.current_preview_page is not None and self.current_preview_page in self.synced_pages:
            points = self.synced_pages[self.current_preview_page]
            self.canvas.set_points(points)
            pages = sorted(self.synced_pages.keys())
            idx = pages.index(self.current_preview_page) + 1
            self.page_indicator.setText(f"Pág. {self.current_preview_page} ({idx}/{len(pages)})")
            text = self.ocr_texts.get(self.digest(points), "")
            self.ocr_view.setPlainText(text)
            self.ocr_status.setText(
                f"Motor: {LocalOcr.engine_name()}" if text else "Sin transcripción (pulsa Reconocer ahora)"
            )
        else:
            self.canvas.clear()
            self.page_indicator.setText("Página —")
            self.ocr_view.clear()

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

    def set_state(self, state):
        self.status.setText(state)
        self.status.setObjectName("connected" if state == "Conectado" else "busy" if state in ("Buscando", "Conectando", "Sincronizando") else "disconnected")
        self.status.style().unpolish(self.status); self.status.style().polish(self.status)
        
        connected = state in ("Conectado", "Sincronizando")
        self.connect_button.setEnabled(not connected and state not in ("Buscando", "Conectando"))
        self.disconnect_button.setEnabled(connected)
        self.sync_button.setEnabled(connected and not self.syncing)
        self.stop_sync_button.setEnabled(self.syncing)
        self.live_button.setEnabled(connected and not self.syncing)
        
        if connected:
            m = self.manager
            self.name.setText(m.device_name)
            self.identifier.setText(m.device_id)
            self.firmware.setText(m.firmware or "No disponible")
            self.area.setText(f"{m.protocol.max_x} × {m.protocol.max_y} · {m.protocol.max_pressure} niveles")
            self.canvas.set_limits(m.protocol.max_x, m.protocol.max_y, m.protocol.max_pressure)

    def show_error(self, title, message):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle(title)
        box.setText(message)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        box.open()

    async def do_connect(self):
        try:
            await self.manager.disconnect()
            self.manager.device = None
            await self.manager.scan()
            await self.manager.connect()
            self.set_state("Conectado")
            self.live_button.setText("Activar escucha pasiva")
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
                self.ocr_status.setText(f"Motor: {LocalOcr.engine_name()}")
                self.live_button.setText("Activar escucha pasiva")
            else:
                await self.manager.enable_online_mode()
                self.ocr_disabled_reason = ""
                self.live_ocr_digest = ""
                self.ocr_status.setText(f"Escucha activa · Motor: {LocalOcr.engine_name()}")
                self.live_button.setText("Desactivar escucha pasiva")
        except Exception as error:
            self.show_error("Error de tiempo real", f"{type(error).__name__}: {error}")

    async def do_sync(self):
        if not self.manager.connected:
            return
        self.syncing = True
        self.ocr_disabled_reason = ""
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

    def update_progress(self, page, total, received, packets):
        self.page_progress.setValue(int(page / max(1, total) * 100))
        self.page_progress.setFormat(f"Páginas: {page}/{total}")
        self.packet_progress.setValue(int(received / max(1, packets) * 100) if packets else 0)
        self.packet_progress.setFormat(f"Paquetes: {received}/{packets}" if packets else "Consultando...")

    @staticmethod
    def digest(points):
        return hashlib.sha256(";".join(f"{p.x},{p.y},{p.pressure},{int(p.down)}" for p in points).encode()).hexdigest()

    def export_xy(self, point, width: int = PAGE_WIDTH, height: int = PAGE_HEIGHT):
        return (
            point.x / max(1, self.manager.protocol.max_x) * width,
            point.y / max(1, self.manager.protocol.max_y) * height,
        )

    def save_page(self, page, points):
        points = [
            point for point in points
            if not (point.x == 0 and point.y == 0 and point.pressure == 0)
        ]

        digest = self.digest(points)
        device = self.manager.device_id or "unknown"
        known = self.store.exists(device, digest)
        txt_known: Optional[Path] = None
        if known:
            png_known = self.store.png_path_for(digest)
            if png_known:
                txt_known = Path(png_known).with_suffix(".txt")
                if txt_known.exists():
                    self.ocr_texts[digest] = txt_known.read_text(encoding="utf-8")

        self.synced_pages[page] = points
        self.current_preview_page = page
        if self.show_page.isChecked():
            self.update_canvas_display()

        if known:
            # Página ya guardada: solo se completa el TXT si faltaba (por ejemplo, si el OCR falló antes).
            if txt_known is not None and not txt_known.exists():
                self.schedule(self.ocr_saved_page(page, points, digest, txt_known))
            return
        if not self.save_local.isChecked():
            return

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
            for index in range(1, len(xy)): painter.drawLine(xy[index - 1], xy[index])
        painter.end()
        image.save(str(png_path), "PNG")

        points_json = json.dumps(
            [[p.x, p.y, p.pressure, int(p.down), p.status] for p in points], separators=(",", ":")
        )
        self.store.add(device, digest, page, png_path, points_json)
        self.refresh_history()
        self.add_log(f"Página {page} sincronizada y guardada (PNG).")
        self.schedule(self.ocr_saved_page(page, points, digest, txt_path))

    # ------------------------------------------------------------------ OCR local
    def set_ocr_text(self, text: str, status: Optional[str] = None):
        self.ocr_view.setPlainText(text)
        self.ocr_status.setText(status if status is not None else f"Motor: {LocalOcr.engine_name()}")

    def clear_preview(self):
        self.canvas.clear()
        self.ocr_timer.stop()
        self.live_ocr_digest = ""
        self.set_ocr_text("")

    def on_live_points(self, points):
        """Cada vez que llegan trazos en directo, se reinicia la espera para lanzar el OCR."""
        if points is None:  # el dispositivo cambió de página y la vista se limpia
            self.ocr_timer.stop()
            self.live_ocr_digest = ""
            self.set_ocr_text("")
            return
        if self.manager.online_enabled and not self.ocr_disabled_reason:
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
        if self.manager.online_enabled and self.canvas.raw_points:  # la vista no se limpió mientras tanto
            self.set_ocr_text(text, None if text else "Sin texto reconocido")

    async def ocr_now(self):
        """Botón «Reconocer ahora»: reconoce lo que muestra la vista previa y, si es una página guardada, escribe su TXT."""
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
        png = self.store.png_path_for(digest)
        if png and text:
            txt_path = Path(png).with_suffix(".txt")
            txt_path.write_text(text, encoding="utf-8")
            self.add_log(f"Texto guardado en {txt_path.name}")

    async def recognize_points(self, points, quiet: bool) -> Optional[str]:
        """Ejecuta el OCR local. Devuelve el texto, o None si no se pudo (sin molestar con ventanas si quiet)."""
        max_x, max_y = self.manager.protocol.max_x, self.manager.protocol.max_y
        strokes = Protocol.strokes(points, max_x, max_y)
        if not strokes:
            return ""
        async with self.ocr_lock:
            if quiet and self.ocr_disabled_reason:
                return None
            self.ocr_status.setText("Reconociendo...")
            try:
                png = render_ocr_png(strokes, max_x, max_y)
                text = await asyncio.to_thread(LocalOcr.recognize, png, self.ocr_languages)
            except OcrUnavailable as error:
                self.ocr_disabled_reason = str(error)
                self.ocr_status.setText("OCR no disponible (ver Registro)")
                self.add_log(f"OCR no disponible: {error}")
                if not quiet:
                    self.show_error("OCR local", str(error))
                return None
            except Exception as error:
                detail = f"{type(error).__name__}: {error}"
                self.ocr_status.setText("Error de OCR (ver Registro)")
                self.add_log(f"Error de OCR: {detail}")
                if not quiet:
                    self.show_error("Error de OCR", detail)
                return None
            self.ocr_status.setText(f"Motor: {LocalOcr.engine_name()}")
            return text

    async def ocr_saved_page(self, page, points, digest, txt_path: Path):
        """OCR de una página sincronizada y guardado de su TXT junto al PNG."""
        if self.ocr_disabled_reason:
            return
        text = await self.recognize_points(points, quiet=True)
        if text is None:
            return
        self.ocr_texts[digest] = text
        if text:
            txt_path.write_text(text, encoding="utf-8")
            self.add_log(f"Página {page}: texto reconocido y guardado en {txt_path.name}")
        else:
            self.add_log(f"Página {page}: el OCR no reconoció texto.")
        current = self.synced_pages.get(self.current_preview_page) if self.current_preview_page is not None else None
        if current is not None and self.digest(current) == digest and not self.manager.online_enabled:
            self.set_ocr_text(text, None if text else "Sin texto reconocido")

    # ------------------------------------------------------------------ Diagnóstico
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

    def refresh_history(self):
        rows = self.store.history()
        self.history_view.setPlainText("\n\n".join(f"Página {p}\n{d}\n{path}\nHash: {h[:16]}" for p, d, path, h in rows) if rows else "Sin páginas guardadas")
        self.summary.setText(f"Páginas guardadas: {self.store.count()}")

    def closeEvent(self, event: QCloseEvent):
        for task in list(self.tasks): task.cancel()
        self.settings.sync()
        self.store.close()
        event.accept()


def main():
    if platform.system() not in ("Darwin", "Windows"):
        raise SystemExit("Solo compatible con macOS y Windows")
    app = QApplication(sys.argv)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    window = MainWindow()
    window.show()
    with loop: loop.run_forever()


if __name__ == "__main__":
    main()