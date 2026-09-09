"""Transport selection.

stdio and streamable-http are the same server on a different wire, so these
tests are about the wiring: what the flags parse to, what gets handed to the
SDK, and the fact that one process still means one chassis.
"""

from __future__ import annotations

import pytest

server = pytest.importorskip(
    "pickering_lxi_mcp.server", reason="the mcp package is not installed"
)


def test_stdio_is_the_default():
    args = server._parse_args([])
    assert args.transport == "stdio"
    assert args.host == "127.0.0.1", "never bind wider than loopback without being asked"
    assert args.stateless_http is False


def test_flags_are_parsed():
    args = server._parse_args(
        ["--transport", "streamable-http", "--host", "0.0.0.0", "--port", "9000",
         "--path", "/switching", "--stateless-http"]
    )
    assert (args.transport, args.host, args.port, args.path) == (
        "streamable-http",
        "0.0.0.0",
        9000,
        "/switching",
    )
    assert args.stateless_http is True


def test_the_environment_supplies_defaults(monkeypatch):
    monkeypatch.setenv("PICKERING_LXI_TRANSPORT", "streamable-http")
    monkeypatch.setenv("PICKERING_LXI_HTTP_PORT", "8123")
    monkeypatch.setenv("PICKERING_LXI_HTTP_PATH", "/rack")
    monkeypatch.setenv("PICKERING_LXI_STATELESS_HTTP", "1")
    args = server._parse_args([])
    assert (args.transport, args.port, args.path, args.stateless_http) == (
        "streamable-http",
        8123,
        "/rack",
        True,
    )


def test_a_flag_beats_the_environment(monkeypatch):
    monkeypatch.setenv("PICKERING_LXI_TRANSPORT", "streamable-http")
    assert server._parse_args(["--transport", "stdio"]).transport == "stdio"


def test_an_unknown_transport_is_refused():
    with pytest.raises(SystemExit):
        server._parse_args(["--transport", "carrier-pigeon"])


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple, dict]] = []

    def run(self, *args, **kwargs) -> None:
        self.calls.append((args, kwargs))


def test_stdio_asks_the_sdk_for_nothing_else(monkeypatch):
    recorder = _Recorder()
    monkeypatch.setattr(server, "server", recorder)
    server.run(transport="stdio", host="0.0.0.0", port=9000)
    assert recorder.calls == [((), {})], "HTTP options must not leak into a stdio run"


def test_streamable_http_options_reach_the_sdk(monkeypatch):
    recorder = _Recorder()
    monkeypatch.setattr(server, "server", recorder)
    server.run(transport="streamable-http", host="0.0.0.0", port=9000, path="/switching")
    (_, kwargs), = recorder.calls
    assert kwargs["transport"] == "streamable-http"
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["port"] == 9000
    assert kwargs["streamable_http_path"] == "/switching"


def test_an_sdk_that_does_not_take_the_options_still_starts(monkeypatch):
    """Older SDKs configure host and port on settings rather than on run()."""

    class Settings:
        host = "127.0.0.1"
        port = 8000

    class Old:
        def __init__(self) -> None:
            self.settings = Settings()
            self.started: list[str] = []

        def run(self, transport: str = "stdio", **kwargs):
            if kwargs:
                raise TypeError("run() got unexpected keyword arguments")
            self.started.append(transport)

    old = Old()
    monkeypatch.setattr(server, "server", old)
    server.run(transport="streamable-http", host="0.0.0.0", port=9000)
    assert old.started == ["streamable-http"]
    assert old.settings.host == "0.0.0.0"
    assert old.settings.port == 9000


def test_main_dispatches_what_it_parsed(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(server, "run", lambda **kwargs: seen.update(kwargs))
    server.main(["--transport", "streamable-http", "--port", "9100"])
    assert seen["transport"] == "streamable-http"
    assert seen["port"] == 9100


def test_one_process_serves_one_chassis():
    """The session is module level on purpose: there is one physical chassis.

    Over stdio the reservation is mostly bookkeeping. Over HTTP, where several
    agents share this process, it is the thing standing between them.
    """
    from pickering_lxi_mcp import tools

    first = tools.call(server.SESSION, "chassis_identify")
    second = tools.call(server.SESSION, "chassis_identify")
    assert first["topology"] == second["topology"]
    assert server.SESSION is server.SESSION
