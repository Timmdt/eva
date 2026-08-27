from __future__ import annotations

import re
import socket
import time
from typing import Any, Callable


def magic_packet(mac: str) -> bytes:
    compact = re.sub(r"[:-]", "", mac.strip())
    if not re.fullmatch(r"[0-9A-Fa-f]{12}", compact):
        raise ValueError("Ungültige MAC-Adresse.")
    return b"\xff" * 6 + bytes.fromhex(compact) * 16


def wake_server(mac: str, broadcast: str, *, socket_factory: Callable[..., Any] = socket.socket) -> None:
    packet = magic_packet(mac)
    sock = socket_factory(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast, 9))
    finally:
        sock.close()


class WakeOnLan:
    def __init__(self, mac: str, broadcast: str, cooldown: float = 120.0,
                 *, sender: Callable[[str, str], None] = wake_server,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.mac, self.broadcast, self.cooldown = mac, broadcast, cooldown
        self.sender, self.clock = sender, clock
        self.last_sent: float | None = None

    def wake(self) -> bool:
        now = self.clock()
        if self.last_sent is not None and now - self.last_sent < self.cooldown:
            return False
        self.sender(self.mac, self.broadcast)
        self.last_sent = now
        return True
