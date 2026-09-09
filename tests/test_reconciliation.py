"""What the server does when the chassis was already switched before it started.

The failure this guards: the process restarts, the route table comes back empty
and the relays do not. An empty model of a chassis that is not empty is worse
than no model, because the interlock reasons from it confidently and will
authorise the short it exists to prevent.
"""

from __future__ import annotations

import pytest

from pickering_lxi_mcp.errors import InterlockError, ReconciliationError
from pickering_lxi_mcp.session import ChassisSession
from pickering_lxi_mcp.topology import Operation

CONFIRM_ARM = "the fixture is safe to energise"
CONFIRM_ADOPT = "adopt the state on the chassis"
CONFIRM_CLEAR = "open every crosspoint on the chassis"

# psu_pos -> dut_pin_a1 and dmm_hi -> dut_pin_a1: a plausible thing to die holding
LIVE = [(1, 1), (6, 1)]
# psu_pos -> dut_pin_a1 and gnd -> dut_pin_a1: a fixture that is already shorted
SHORTED = [(1, 1), (3, 1)]


def found(session: ChassisSession, crosspoints) -> ChassisSession:
    """Close crosspoints behind the server's back, then let it look."""
    for row, column in crosspoints:
        session.backend.close_crosspoint("matrix_a", 1, row, column)
    session.reconcile()
    return session


@pytest.fixture
def stale(session: ChassisSession) -> ChassisSession:
    return found(session, LIVE)


def test_a_clean_chassis_reconciles_itself(session):
    assert session.reconciled is True
    assert session.unowned == set()
    assert session.reconciliation_status()["resolve_with"] == []


def test_what_was_found_is_reported_precisely(stale):
    status = stale.reconciliation_status()
    assert status["reconciled"] is False
    assert status["violations"] == []
    assert [(c["row"], c["column"]) for c in status["unowned_crosspoints"]] == LIVE
    assert status["resolve_with"] == ["adopt_existing_state", "clear_existing_state"]


def test_observation_works_while_unreconciled(stale):
    """Deciding what to do requires looking first, so looking is never gated."""
    assert stale.subunit_state("matrix_a", 1)["closed_count"] == 2
    assert stale.list_cards()
    assert stale.plan("scope_ch1", "dut_pin_a2")["hops"] == 1
    assert stale.describe()["reconciled"] is False
    assert stale.crosspoint("matrix_a", 1, 1, 1)["closed"] is True


def test_nothing_that_could_energise_the_fixture_is_allowed(stale):
    token = stale.reserve(owner="ops").token
    with pytest.raises(ReconciliationError, match="already closed"):
        stale.arm(token, CONFIRM_ARM)
    with pytest.raises(ReconciliationError):
        stale.route(token, "scope_ch1", "dut_pin_a2")
    with pytest.raises(ReconciliationError):
        stale.set_crosspoint(token, "matrix_a", 1, 4, 2, True)
    assert stale.subunit_state("matrix_a", 1)["closed_count"] == 2, "nothing was switched"


def test_the_refusal_says_what_to_do_about_it(stale):
    token = stale.reserve(owner="ops").token
    with pytest.raises(ReconciliationError) as exc:
        stale.route(token, "scope_ch1", "dut_pin_a2")
    message = str(exc.value)
    assert "adopt_existing_state" in message
    assert "clear_existing_state" in message
    assert "matrix_a/sub1(1,1)" in message


def test_adoption_takes_the_words(stale):
    token = stale.reserve(owner="ops").token
    with pytest.raises(ReconciliationError, match="requires confirm"):
        stale.adopt_existing_state(token, "yes")
    assert stale.reconciled is False


def test_adoption_switches_nothing(stale):
    token = stale.reserve(owner="ops").token
    before = stale.subunit_state("matrix_a", 1)["closed"]
    stale.adopt_existing_state(token, CONFIRM_ADOPT)
    assert stale.reconciled is True
    assert stale.subunit_state("matrix_a", 1)["closed"] == before


def test_adopted_crosspoints_are_counted_by_the_interlock(stale):
    """The whole point: a short composed against state this process never made."""
    token = stale.reserve(owner="ops").token
    stale.adopt_existing_state(token, CONFIRM_ADOPT)
    stale.arm(token, CONFIRM_ARM)

    with pytest.raises(InterlockError, match="electrically common"):
        stale.route(token, "gnd", "dut_pin_a1")

    assert stale.route(token, "scope_ch1", "dut_pin_a2")["status"] == "open"


def test_a_fixture_already_shorted_cannot_become_the_baseline(session):
    stale = found(session, SHORTED)
    assert stale.reconciliation_status()["violations"] == [
        "'psu_pos' and 'gnd' are already electrically common"
    ]
    token = stale.reserve(owner="ops").token
    with pytest.raises(ReconciliationError, match="breaks the topology's own rules"):
        stale.adopt_existing_state(token, CONFIRM_ADOPT)
    assert stale.reconciled is False
    assert stale.subunit_state("matrix_a", 1)["closed_count"] == 2


def test_clearing_is_always_available_as_the_way_out(session):
    stale = found(session, SHORTED)
    token = stale.reserve(owner="ops").token
    with pytest.raises(ReconciliationError, match="requires confirm"):
        stale.clear_existing_state(token, "ok")

    result = stale.clear_existing_state(token, CONFIRM_CLEAR)
    assert result["crosspoints_opened"] == 2
    assert stale.reconciled is True
    assert stale.subunit_state("matrix_a", 1)["closed_count"] == 0

    stale.arm(token, CONFIRM_ARM)
    assert stale.route(token, "psu_pos", "dut_pin_a1")["status"] == "open"


def test_an_adopted_crosspoint_belongs_to_no_route(stale):
    token = stale.reserve(owner="ops").token
    stale.adopt_existing_state(token, CONFIRM_ADOPT)
    stale.arm(token, CONFIRM_ARM)

    assert stale.crosspoint("matrix_a", 1, 1, 1)["held_by_routes"] == []
    with pytest.raises(InterlockError, match="adopted"):
        stale.set_crosspoint(token, "matrix_a", 1, 1, 1, False)
    assert stale.backend.view_crosspoint("matrix_a", 1, 1, 1) is True


def test_clearing_everything_also_drops_what_was_adopted(stale):
    token = stale.reserve(owner="ops").token
    stale.adopt_existing_state(token, CONFIRM_ADOPT)
    stale.arm(token, CONFIRM_ARM)
    stale.route(token, "scope_ch1", "dut_pin_a2")

    result = stale.clear_all_routes(token)
    assert result["unowned_crosspoints_opened"] == 2
    assert stale.unowned == set()
    assert stale.subunit_state("matrix_a", 1)["closed_count"] == 0


def test_reconcile_does_not_disown_this_process_own_routes(armed):
    """Re-reading the chassis must not turn our own closures into strangers."""
    session, token = armed
    session.route(token, "scope_ch1", "dut_pin_a1")
    session.reconcile()
    assert session.unowned == set()
    assert session.reconciled is True
    assert session.route(token, "dmm_hi", "dut_pin_a3")["status"] == "open"


def test_reconcile_is_idempotent(stale):
    first = stale.reconciliation_status()
    stale.reconcile()
    assert stale.reconciliation_status() == first


def test_unowned_crosspoints_across_more_than_one_card_are_all_found(session):
    session.backend.close_crosspoint("matrix_a", 1, 2, 5)
    session.backend.close_crosspoint("mux_b", 1, 1, 3)
    session.reconcile()
    cards = {c["card"] for c in session.reconciliation_status()["unowned_crosspoints"]}
    assert cards == {"matrix_a", "mux_b"}
    assert session.unowned == {Operation("matrix_a", 1, 2, 5), Operation("mux_b", 1, 1, 3)}


def test_adoption_when_there_is_nothing_to_adopt_is_not_an_error(session):
    token = session.reserve(owner="ops").token
    assert session.adopt_existing_state(token, CONFIRM_ADOPT)["status"] == "nothing_to_adopt"


def test_reconciliation_needs_a_reservation_like_any_other_mutation(stale):
    from pickering_lxi_mcp.errors import ReservationError

    with pytest.raises(ReservationError):
        stale.adopt_existing_state("not-a-token", CONFIRM_ADOPT)
    with pytest.raises(ReservationError):
        stale.clear_existing_state("not-a-token", CONFIRM_CLEAR)
