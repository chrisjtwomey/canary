"""The MQTT broker the boards get when config.yaml names none for them."""
from __future__ import annotations

import ipaddress


def board_broker(server_broker: str) -> str:
    """The server's own broker, which the boards most often reach by the same
    name, or "" when it names the server's machine: no board can reach that."""
    host = str(server_broker).strip()
    if host.lower() == "localhost":
        return ""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    return "" if address.is_loopback or address.is_unspecified else host
