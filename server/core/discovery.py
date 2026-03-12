"""
UDP Discovery Service.

Listens on UDP port 45454 for beacon packets from ESP8266 devices and
provides methods to scan the local network and bind/unbind devices.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

log = logging.getLogger(__name__)

BEACON_PORT = 45454
DEVICE_TIMEOUT_S = 30.0


@dataclass
class DiscoveredDevice:
    device_id: str
    mac: str
    display: str
    firmware: str
    bound_to: str        # pc_name the device thinks it is bound to
    bound_pc_id: str     # pc_id the device thinks it is bound to
    ip: str
    last_seen: float = field(default_factory=time.time)


class DiscoveryService:
    """
    Background UDP discovery service.

    Start with :meth:`start`, stop with :meth:`stop`.
    """

    def __init__(
        self,
        udp_port: int = BEACON_PORT,
        on_device_found: Optional[Callable[[DiscoveredDevice], None]] = None,
        on_device_lost: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._port = udp_port
        self.on_device_found = on_device_found
        self.on_device_lost = on_device_lost

        self._devices: Dict[str, DiscoveredDevice] = {}
        self._lock = threading.Lock()

        self._sock: Optional[socket.socket] = None
        self._running = False
        self._rx_thread: Optional[threading.Thread] = None
        self._watchdog_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start listening and watchdog threads."""
        if self._running:
            return
        self._running = True
        self._sock = self._make_socket()
        self._rx_thread = threading.Thread(
            target=self._rx_loop, name="discovery-rx", daemon=True
        )
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, name="discovery-watchdog", daemon=True
        )
        self._rx_thread.start()
        self._watchdog_thread.start()
        log.info("DiscoveryService started on UDP port %d", self._port)

    def stop(self) -> None:
        """Stop all background threads."""
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        if self._rx_thread:
            self._rx_thread.join(timeout=2)
        if self._watchdog_thread:
            self._watchdog_thread.join(timeout=2)
        log.info("DiscoveryService stopped")

    def scan(self) -> None:
        """Broadcast a discover_request packet."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s.settimeout(1)
                payload = json.dumps({"type": "discover_request"}).encode()
                s.sendto(payload, ("255.255.255.255", self._port))
                log.debug("Sent discover_request broadcast")
        except OSError as exc:
            log.warning("scan() failed: %s", exc)

    def get_all_devices(self) -> List[DiscoveredDevice]:
        with self._lock:
            return list(self._devices.values())

    def get_device(self, device_id: str) -> Optional[DiscoveredDevice]:
        with self._lock:
            return self._devices.get(device_id)

    def send_bind_command(
        self,
        ip: str,
        device_id: str,
        pc_id: str,
        pc_name: str,
        force: bool = False,
    ) -> None:
        payload = json.dumps(
            {
                "type": "bind",
                "device_id": device_id,
                "pc_id": pc_id,
                "pc_name": pc_name,
                "force": force,
            }
        ).encode()
        self._udp_send(ip, payload)

    def send_unbind_command(self, ip: str, device_id: str) -> None:
        payload = json.dumps(
            {"type": "unbind", "device_id": device_id}
        ).encode()
        self._udp_send(ip, payload)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_socket(self) -> socket.socket:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)  # type: ignore[attr-defined]
        except AttributeError:
            pass  # Windows doesn't have SO_REUSEPORT
        s.settimeout(1.0)
        s.bind(("", self._port))
        return s

    def _rx_loop(self) -> None:
        while self._running:
            try:
                data, addr = self._sock.recvfrom(4096)  # type: ignore[union-attr]
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                pkt = json.loads(data.decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if pkt.get("type") == "pc_monitor_beacon":
                self._handle_beacon(pkt, addr[0])

    def _handle_beacon(self, pkt: dict, ip: str) -> None:
        device_id = pkt.get("device_id", "")
        if not device_id:
            return

        device = DiscoveredDevice(
            device_id=device_id,
            mac=pkt.get("mac", ""),
            display=pkt.get("display", ""),
            firmware=pkt.get("firmware", ""),
            bound_to=pkt.get("bound_to", ""),
            bound_pc_id=pkt.get("bound_pc_id", ""),
            ip=ip,
            last_seen=time.time(),
        )

        with self._lock:
            is_new = device_id not in self._devices
            self._devices[device_id] = device

        if is_new and self.on_device_found:
            try:
                self.on_device_found(device)
            except Exception:
                log.exception("on_device_found callback error")

    def _watchdog_loop(self) -> None:
        while self._running:
            time.sleep(5)
            now = time.time()
            lost: List[str] = []
            with self._lock:
                for did, dev in list(self._devices.items()):
                    if now - dev.last_seen > DEVICE_TIMEOUT_S:
                        lost.append(did)
                for did in lost:
                    del self._devices[did]

            for did in lost:
                log.info("Device lost: %s", did)
                if self.on_device_lost:
                    try:
                        self.on_device_lost(did)
                    except Exception:
                        log.exception("on_device_lost callback error")

    def _udp_send(self, ip: str, payload: bytes) -> None:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(2)
                s.sendto(payload, (ip, self._port))
        except OSError as exc:
            log.warning("UDP send to %s failed: %s", ip, exc)
