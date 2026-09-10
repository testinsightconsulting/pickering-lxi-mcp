"""Check a topology file without a chassis anywhere near it.

``verify_topology`` compares a loaded topology against the chassis in front of
it. This is the other half: everything that can be decided from the file alone,
so a fixture map can be reviewed before the rack exists, in CI, or in a pull
request.

Three severities, and the middle one is the point:

* **problems** are wrong. A rule that can never fire, a closure limit larger
  than the subunit, an endpoint that is not on a routable subunit. Exit 1.
* **warnings** are things the interlock cannot protect you from, and the most
  useful of them is a destination with no power rating that a rated source can
  reach. The file is not malformed; it is just quietly not covering something.
* **notes** are what the file says about the world, including what it asserts
  that nothing can check.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .errors import PickeringError
from .interlocks import InterlockPolicy, connectivity
from .topology import Operation, Topology

# Endpoint roles that represent something a signal is delivered *to*, and which
# therefore ought to have a rating if anything can reach them at power.
SINK_ROLES = {"dut", "instrument", "sensor"}


def every_crosspoint(topology: Topology) -> list[Operation]:
    """The worst case: every crosspoint the topology could ever close."""
    return [
        Operation(card.alias, sub.subunit, row, column)
        for card in topology.cards
        for sub in card.subunits
        for row in range(1, sub.rows + 1)
        for column in range(1, sub.columns + 1)
    ]


def check(topology: Topology) -> tuple[list[str], list[str], list[str]]:
    problems: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []

    try:
        policy = InterlockPolicy.from_spec(topology.interlocks, topology)
    except PickeringError as exc:
        # A malformed policy is a finding, not a reason to stop looking. Carry on
        # with an empty one so the structural and power checks still report.
        problems.append(f"interlock policy is malformed: {exc}")
        policy = InterlockPolicy(require_arm=False)

    domains = topology.fabric_domains()
    home = {name: d.domain_id for d in domains for name in d.endpoints}
    reachable = connectivity(topology, every_crosspoint(topology))

    # -- structure ---------------------------------------------------------
    for card in topology.cards:
        for sub in card.subunits:
            ceiling = sub.rows * sub.columns
            if sub.closure_limit > ceiling:
                problems.append(
                    f"{card.alias}/sub{sub.subunit}: closure limit {sub.closure_limit} exceeds "
                    f"the {ceiling} crosspoints the subunit has"
                )
            if sub.closure_limit < 1:
                problems.append(f"{card.alias}/sub{sub.subunit}: closure limit must be at least 1")

    seen: dict[tuple, list[str]] = {}
    for name, endpoint in topology.endpoints.items():
        seen.setdefault(endpoint.node, []).append(name)
    for node, names in sorted(seen.items()):
        if len(names) > 1:
            warnings.append(
                f"{len(names)} endpoints share one line ({node[0]}/sub{node[1]} {node[2]} "
                f"{node[3]}): {', '.join(sorted(names))}. They are the same point electrically; "
                "routing between them is refused as already-common."
            )

    # -- safety rules that cannot fire -------------------------------------
    for a, b in policy.forbidden_pairs:
        if home.get(a) != home.get(b):
            problems.append(
                f"forbidden pair {a!r}/{b!r} can never fire: {a} is in {home.get(a)} and {b} is "
                f"in {home.get(b)}. Either the pair is wrong, or a link between those domains "
                "is missing from this file."
            )

    for name in sorted(policy.exclusive_endpoints):
        if name not in topology.endpoints:
            problems.append(f"exclusive endpoint {name!r} is not defined")

    # -- power -------------------------------------------------------------
    sources = [e for e in topology.endpoints.values() if e.max_output_dbm is not None]
    for source in sorted(sources, key=lambda e: e.name):
        unrated: list[str] = []
        for name, endpoint in sorted(topology.endpoints.items()):
            if name == source.name or not reachable.connected(source.node, endpoint.node):
                continue
            if endpoint.max_input_dbm is None:
                if endpoint.role in SINK_ROLES:
                    unrated.append(name)
                continue
            margin = source.max_output_dbm - endpoint.max_input_dbm
            if margin > 0:
                notes.append(
                    f"{source.name} ({source.max_output_dbm:+.1f} dBm) can reach {name} "
                    f"({endpoint.max_input_dbm:+.1f} dBm) — {margin:.1f} dB over. Any route "
                    "making them common will be refused."
                )
        if unrated:
            # One warning per source, not one per destination: the cause is the
            # missing ratings, and twenty identical lines bury the other findings.
            shown = ", ".join(unrated[:4])
            more = "" if len(unrated) <= 4 else f", +{len(unrated) - 4} more"
            warnings.append(
                f"{len(unrated)} destination(s) reachable from {source.name!r} declare no "
                f"max_input_dbm, and it can deliver up to {source.max_output_dbm:+.1f} dBm: "
                f"{shown}{more}. The interlock cannot protect them."
            )

    if policy.enforce_power_limits and not sources:
        warnings.append(
            "enforce_power_limits is on and no endpoint declares max_output_dbm, so the power "
            "check can never fire."
        )

    # -- what the file says ------------------------------------------------
    notes.append(f"{len(domains)} fabric domain(s): " + ", ".join(d.domain_id for d in domains))
    for d in domains:
        lines_named = len(d.endpoints)
        notes.append(
            f"  {d.domain_id}: {lines_named} named endpoint(s) of {d.line_count} lines, "
            f"subunits {', '.join(f'{c}/sub{n}' for c, n in d.subunits)}"
        )
    notes.append(
        f"asserted, unverifiable: {len(topology.links)} link(s), "
        f"{len(policy.forbidden_pairs)} forbidden pair(s), "
        f"{sum(1 for e in topology.endpoints.values() if e.max_output_dbm is not None or e.max_input_dbm is not None)} "
        "power rating(s), and that every endpoint name matches what is physically on that line"
    )
    return problems, warnings, notes


def report(path: Path) -> int:
    print(f"\n\033[1m{path}\033[0m")
    try:
        topology = Topology.load(path)
    except PickeringError as exc:
        print(f"  PROBLEM  {exc}")
        return 1

    print(f"  {topology.name} — {len(topology.cards)} card(s), {len(topology.endpoints)} endpoint(s)")
    try:
        problems, warnings, notes = check(topology)
    except Exception as exc:
        print(f"  PROBLEM  the file could not be fully checked: {type(exc).__name__}: {exc}")
        return 1

    for line in problems:
        print(f"  PROBLEM  {line}")
    for line in warnings:
        print(f"  WARNING  {line}")
    for line in notes:
        print(f"  note     {line}")

    verdict = "FAIL" if problems else ("OK, with warnings" if warnings else "OK")
    print(f"  → {verdict}: {len(problems)} problem(s), {len(warnings)} warning(s)")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help"}:
        print(
            "usage: pickering-lxi-mcp-validate <topology.json> [...]\n\n"
            "Checks what can be decided from the file alone: structure, fabric domains,\n"
            "safety rules that can never fire, and destinations a rated source can reach\n"
            "that declare no rating of their own. No chassis required."
        )
        return 0 if args else 1

    targets: list[Path] = []
    for arg in args:
        path = Path(arg)
        targets.extend(sorted(path.glob("*.json")) if path.is_dir() else [path])

    if not targets:
        print("no topology files found")
        return 1
    return max(report(p) for p in targets)


if __name__ == "__main__":
    raise SystemExit(main())
