import pytest

from broker import board_broker
from schedule import DEFAULT_PAGE_WEEK
from server import load_settings

BASE = {"display": {"pools": {"co2": ["breathe.png"]},
                    "schedule": {"type": "timeranges", "week": DEFAULT_PAGE_WEEK}}}


@pytest.mark.parametrize("server_broker, expected", [
    ("broker.lan", "broker.lan"),
    (" 192.168.1.2 ", "192.168.1.2"),
    ("localhost", ""),
    ("LocalHost", ""),
    ("127.0.0.1", ""),
    ("127.1.2.3", ""),
    ("::1", ""),
    ("0.0.0.0", ""),
])
def test_the_boards_get_the_servers_broker_unless_it_is_the_servers_own_machine(
        server_broker, expected):
    assert board_broker(server_broker) == expected


def _network(mqtt: dict, client: dict | None = None):
    config = {**BASE, "mqtt": {"enabled": True, **mqtt}}
    if client is not None:
        config["client"] = client
    core = load_settings(config).core
    return core.network, core.network.missing(core.mqtt)


def test_an_unset_board_broker_is_the_servers():
    network, missing = _network({"host": "broker.lan"})
    assert network.mqtt_host == "broker.lan"
    assert "client.mqtt_host" not in missing


def test_a_board_broker_that_is_set_stays():
    network, _ = _network({"host": "mosquitto"}, {"mqtt_host": "broker.lan"})
    assert network.mqtt_host == "broker.lan"


def test_a_server_broker_on_its_own_machine_leaves_the_board_broker_missing():
    network, missing = _network({"host": "localhost"})
    assert network.mqtt_host == ""
    assert "client.mqtt_host" in missing
