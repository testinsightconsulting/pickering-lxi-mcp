"""The gate itself: the walkthroughs must pass, and the runner must be able to fail."""

from __future__ import annotations

from pathlib import Path

import pytest

from pickering_lxi_mcp import walkthrough

WALKTHROUGHS = Path(__file__).resolve().parents[1] / "walkthroughs"


def paths() -> list[Path]:
    return sorted(WALKTHROUGHS.glob("*.json"))


def test_there_are_walkthroughs_to_run():
    assert paths(), "the CI gate needs something to gate on"


@pytest.mark.parametrize("path", paths(), ids=lambda p: p.stem)
def test_walkthrough_passes(path):
    result = walkthrough.run(walkthrough.load(path))
    assert result.ok, "\n" + result.report()


def test_run_all_matches_the_directory():
    assert len(walkthrough.run_all(WALKTHROUGHS)) == len(paths())
    assert all(r.ok for r in walkthrough.run_all(WALKTHROUGHS))


def test_the_runner_reports_a_divergence_rather_than_swallowing_it():
    result = walkthrough.run(
        {
            "name": "deliberately wrong",
            "steps": [{"id": "x", "tool": "interlock_status", "expect": {"armed": True}}],
        }
    )
    assert not result.ok
    assert "FAIL" in result.report()


def test_an_expected_refusal_that_does_not_happen_is_a_failure():
    result = walkthrough.run(
        {
            "name": "refusal that never came",
            "steps": [{"id": "x", "tool": "list_routes", "expect_error": "InterlockError"}],
        }
    )
    assert not result.ok
    assert "to be raised" in result.report()


def test_the_wrong_refusal_is_also_a_failure():
    result = walkthrough.run(
        {
            "name": "wrong refusal",
            "steps": [
                {
                    "id": "x",
                    "tool": "route_signal",
                    "args": {"token": "", "from_endpoint": "scope_ch1", "to_endpoint": "gnd"},
                    "expect_error": "InterlockError",
                }
            ],
        }
    )
    assert not result.ok, "PermissionError must not satisfy expect_error: InterlockError"


def test_steps_can_consume_earlier_results():
    result = walkthrough.run(
        {
            "name": "placeholder",
            "steps": [
                {"id": "res", "tool": "reserve_chassis", "args": {"owner": "t"}},
                {
                    "id": "arm",
                    "tool": "arm_interlock",
                    "args": {
                        "token": "{{res.token}}",
                        "confirm": "the fixture is safe to energise",
                    },
                    "expect": {"armed": True},
                },
            ],
        }
    )
    assert result.ok, "\n" + result.report()


def test_the_cli_entry_point_returns_zero_on_a_clean_run(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["pickering-lxi-mcp-walkthrough", str(WALKTHROUGHS)])
    assert walkthrough.main() == 0
    assert "walkthroughs passed" in capsys.readouterr().out


def test_the_cli_entry_point_complains_about_an_empty_directory(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.argv", ["pickering-lxi-mcp-walkthrough", str(tmp_path)])
    assert walkthrough.main() == 1
