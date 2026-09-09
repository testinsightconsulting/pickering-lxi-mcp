"""The simulator is a claim about the card. These are the claims."""

from __future__ import annotations

import pytest

from pickering_lxi_mcp.driver import CardInfo, SimBackend, SubunitInfo, build_backend
from pickering_lxi_mcp.errors import DriverError


def small_card(closure_limit: int = 2) -> CardInfo:
    return CardInfo(
        alias="c",
        bus=1,
        device=2,
        card_id="SIM-2x3",
        subunits=(
            SubunitInfo(
                subunit=1,
                type="MATRIX",
                rows=2,
                columns=3,
                closure_limit=closure_limit,
                settle_time_us=1000,
            ),
        ),
    )


@pytest.fixture
def backend() -> SimBackend:
    return SimBackend((small_card(),))


def test_a_fresh_card_has_nothing_closed(backend):
    assert backend.closed_count("c", 1) == 0
    assert backend.view_subunit("c", 1) == [[False] * 3, [False] * 3]
    assert backend.describe()["hardware"] is False


def test_closing_and_opening_a_crosspoint(backend):
    backend.close_crosspoint("c", 1, 2, 3)
    assert backend.view_crosspoint("c", 1, 2, 3) is True
    assert backend.closed_count("c", 1) == 1
    backend.open_crosspoint("c", 1, 2, 3)
    assert backend.view_crosspoint("c", 1, 2, 3) is False


def test_closing_the_same_crosspoint_twice_is_idempotent(backend):
    backend.close_crosspoint("c", 1, 1, 1)
    backend.close_crosspoint("c", 1, 1, 1)
    assert backend.closed_count("c", 1) == 1


@pytest.mark.parametrize(("row", "column"), [(0, 1), (3, 1), (1, 0), (1, 4)])
def test_out_of_range_crosspoints_are_refused(backend, row, column):
    with pytest.raises(DriverError, match="out of range"):
        backend.close_crosspoint("c", 1, row, column)


def test_the_closure_limit_is_enforced(backend):
    backend.close_crosspoint("c", 1, 1, 1)
    backend.close_crosspoint("c", 1, 1, 2)
    with pytest.raises(DriverError, match="closure limit"):
        backend.close_crosspoint("c", 1, 1, 3)
    # ...and re-closing one that is already closed does not count again.
    backend.close_crosspoint("c", 1, 1, 1)


def test_a_masked_crosspoint_will_not_close(backend):
    backend.mask_crosspoint("c", 1, 1, 2)
    with pytest.raises(DriverError, match="masked"):
        backend.close_crosspoint("c", 1, 1, 2)
    assert backend.closed_count("c", 1) == 0


def test_clearing(backend):
    backend.close_crosspoint("c", 1, 1, 1)
    backend.clear_subunit("c", 1)
    assert backend.closed_count("c", 1) == 0
    backend.close_crosspoint("c", 1, 1, 1)
    backend.clear_all()
    assert backend.closed_count("c", 1) == 0


def test_unknown_cards_and_subunits_say_what_exists(backend):
    with pytest.raises(DriverError, match=r"no card aliased 'ghost'"):
        backend.close_crosspoint("ghost", 1, 1, 1)
    with pytest.raises(DriverError, match="no subunit 7"):
        backend.close_crosspoint("c", 7, 1, 1)


def test_card_info_names_the_subunits_it_has():
    card = small_card()
    assert card.subunit(1).rows == 2
    with pytest.raises(DriverError, match=r"has no subunit 2"):
        card.subunit(2)


def test_no_address_in_the_environment_means_the_simulator():
    backend = build_backend((small_card(),), env={})
    assert isinstance(backend, SimBackend)
    assert backend.describe()["backend"] == "simulator"


def test_an_address_without_the_vendor_driver_fails_loudly():
    # The point of the assertion is the message: a missing vendor driver must
    # not look like a chassis that is merely offline.
    with pytest.raises(DriverError) as exc:
        build_backend((small_card(),), env={"PICKERING_LXI_ADDRESS": "203.0.113.1"})
    assert "pilxi" in str(exc.value) or "ClientBridge" in str(exc.value)
