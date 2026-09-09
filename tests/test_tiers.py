"""The tier split, and the guard rails that keep it a split."""

from __future__ import annotations

import inspect

import pytest

from pickering_lxi_mcp import tools
from pickering_lxi_mcp.tools import Tier

# Words that would name a tool capable of pushing arbitrary operations at the
# vendor driver. This test is not about today's code; it is about the pull
# request in eight months that adds `op_crosspoint_raw` "just for debugging".
FORBIDDEN = {
    "send",
    "write",
    "raw",
    "exec",
    "command",
    "passthrough",
    "opbit",
    "opcrosspoint",
    "driver",
    "eval",
}


def test_no_raw_driver_passthrough_is_exposed():
    for name in tools.REGISTRY:
        assert not (set(name.lower().split("_")) & FORBIDDEN), name


def test_every_tool_declares_a_tier_and_a_summary():
    for spec in tools.REGISTRY.values():
        assert isinstance(spec.tier, Tier)
        assert spec.summary.endswith("."), f"{spec.name} summary should be a sentence"


def test_every_mutating_tool_takes_a_token_as_its_first_argument():
    for spec in tools.REGISTRY.values():
        if spec.tier is not Tier.MUTATE:
            continue
        params = list(inspect.signature(spec.handler).parameters)
        assert params[0] == "session"
        assert params[1] == "token", f"{spec.name} must be token-gated at the signature"


def test_no_observing_tool_takes_a_token():
    """An observe tool that wants a token has probably been mis-tiered."""
    for spec in tools.REGISTRY.values():
        if spec.tier is Tier.OBSERVE:
            assert "token" not in inspect.signature(spec.handler).parameters, spec.name


def test_the_dispatcher_refuses_a_mutating_tool_with_no_token(session):
    with pytest.raises(PermissionError, match="requires a reservation token"):
        tools.call(session, "route_signal", from_endpoint="a", to_endpoint="b")
    with pytest.raises(PermissionError):
        tools.call(session, "clear_all_routes", token="")


def test_unknown_tools_are_a_key_error(session):
    with pytest.raises(KeyError, match="unknown tool"):
        tools.call(session, "no_such_tool")


def test_observation_is_never_gated_even_while_someone_else_holds_the_chassis(session):
    session.reserve(owner="alice")
    assert tools.call(session, "interlock_status")["armed"] is False
    assert tools.call(session, "list_routes") == {"routes": []}
    assert tools.call(session, "chassis_identify")["reserved_by"] == "alice"


def test_the_manifest_lets_an_agent_plan_before_it_reserves():
    manifest = tools.manifest()
    names = {row["name"] for row in manifest}
    assert names == set(tools.REGISTRY)
    assert {row["tier"] for row in manifest} == {"observe", "mutate"}
    # mutate sorts before observe, so the gated half is what an agent reads first
    assert manifest[0]["tier"] == "mutate"


def test_the_mcp_server_exposes_the_same_tools_and_only_those():
    server = pytest.importorskip(
        "pickering_lxi_mcp.server", reason="the mcp package is not installed"
    )
    bound = {
        name
        for name, obj in vars(server).items()
        if callable(obj) and name in tools.REGISTRY
    }
    assert bound == set(tools.REGISTRY), "server bindings and the registry have drifted apart"
    assert hasattr(server, "list_tool_tiers")


def test_anticipated_refusals_reach_the_model_with_their_text():
    """The SDK hides the text of an unexpected exception; a refusal must not be one."""
    server = pytest.importorskip(
        "pickering_lxi_mcp.server", reason="the mcp package is not installed"
    )
    from pickering_lxi_mcp.errors import InterlockError, PickeringError

    assert issubclass(InterlockError, PickeringError)
    for kind in (PickeringError, PermissionError, ValueError, KeyError):
        assert issubclass(kind, Exception)
        assert kind in server.ANTICIPATED

    with pytest.raises(server.ToolError, match=r"PermissionError.*requires a reservation token"):
        server._call("route_signal", from_endpoint="scope_ch1", to_endpoint="dut_pin_a1")

    with pytest.raises(server.ToolError, match="TopologyError: unknown endpoint"):
        server._call("plan_route", from_endpoint="scope_ch1", to_endpoint="ghost_pin")


def test_a_genuine_bug_is_not_dressed_up_as_a_refusal():
    server = pytest.importorskip(
        "pickering_lxi_mcp.server", reason="the mcp package is not installed"
    )
    assert RuntimeError not in server.ANTICIPATED
    assert TypeError not in server.ANTICIPATED
