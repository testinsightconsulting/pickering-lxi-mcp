# pickering-lxi-mcp

An MCP server that lets an LLM agent route signals through Pickering PXI/LXI switching — by logical endpoint name, with the interlocks that make that safe to point at a real fixture.

Switching is the routing layer of a test rack. Every other instrument an agent might drive is reached *through* it, which makes it the one server a multi-vendor agent cannot do without, and the one where a mistake is not a wrong reading but a short.

It ships with an in-process chassis simulator, so `git clone && pip install -e ".[dev]" && pytest` exercises every code path with no hardware, no Pickering driver and no lab.

```bash
pip install -e ".[dev]"
pytest -q                                    # 83 tests
pickering-lxi-mcp-walkthrough walkthroughs   # the CI gate
pickering-lxi-mcp                            # MCP server on stdio, simulated chassis
```

Against a real rack:

```bash
PICKERING_LXI_ADDRESS=192.168.1.50 pickering-lxi-mcp     # LXI chassis by IP
PICKERING_LXI_ADDRESS=PXI          pickering-lxi-mcp     # local PXI cards
PICKERING_LXI_TOPOLOGY=./my_bench.json pickering-lxi-mcp # your fixture map
```

Point any MCP client at it:

```json
{ "mcpServers": { "switching": { "command": "pickering-lxi-mcp" } } }
```

Or run it as a network service and let several agents share the rack:

```bash
pickering-lxi-mcp --transport streamable-http --host 0.0.0.0 --port 8000
```

```json
{ "mcpServers": { "switching": { "url": "http://lab-host:8000/mcp" } } }
```

## The problem this is actually solving

On a programmable supply, the dangerous mistake is a number: 400 V where 4 V was meant. On a switching matrix, the dangerous mistake is a **graph**.

Nobody ever asks to short the supply to ground. They route the supply to a DUT pin — reasonable. Then they route that pin to ground for a continuity check — also reasonable. The short is the *composition* of two individually correct requests, and neither one looks wrong at the moment it is made. An agent that reasons one call at a time will make this mistake, and so will a tired engineer at 2am.

So this server does not ask "is this route forbidden". It asks: given every crosspoint closed right now, plus every crosspoint this route would close, plus the hard-wired patch leads, **does any forbidden pair of endpoints end up in the same connected component?** That question is answered before a relay moves, and a route that fails it is refused whole.

```
> route_signal  psu_pos -> dut_pin_a1        ok   matrix_a/sub1(1,1)
> route_signal  dmm_hi  -> dut_pin_a1        ok   matrix_a/sub1(6,1)     measuring under power is fine
> route_signal  gnd     -> dut_pin_a1        REFUSED
    this route would make 'psu_pos' and 'gnd' electrically common,
    which the topology forbids. Nothing was switched.
> route_signal  gnd     -> dut_pin_a5        ok   matrix_a/sub1(3,5)     same route, different pin
```

## Logical endpoints, not crosspoints

A test engineer does not think in crosspoints; they think *connect the DMM to thermocouple 1*. The topology file is the map from those names to physical lines, plus the patch leads between cards. Routing is then a shortest-path search over that graph, and the answer is an ordered list of switch operations.

```jsonc
"endpoints": {
  "dmm_hi": { "card": "matrix_a", "subunit": 1, "line": "row",    "index": 6 },
  "tc_1":   { "card": "mux_b",    "subunit": 1, "line": "column", "index": 1 }
},
"links": [                          // a patch lead: known about, never switched
  [ { "card": "matrix_a", "subunit": 1, "line": "column", "index": 13 },
    { "card": "mux_b",    "subunit": 1, "line": "row",    "index": 1  } ]
]
```

`plan_route dmm_hi -> tc_1` returns two closures across two cards, and says whether the interlocks would allow it — without switching anything, and without taking the chassis. It is the first tool an agent should reach for.

Three consequences worth naming:

**Routes are reference counted.** Two routes through the same matrix will legitimately share a crosspoint. Tearing one down must not open a crosspoint the other is still holding up, so `unroute_signal` reports what it opened *and* what it retained.

**The plan is computed before anything is switched.** A router that closes crosspoints as it discovers them cannot be refused half way. This one can be refused whole, and a route that fails mid-flight is rolled back.

**A topology is a claim about the rack.** `verify_topology` checks it against what the chassis actually reports — which is trivially true on the simulator, and is exactly what catches a topology written for last quarter's rack.

## The two patterns

Both are argued at length in **[PATTERNS.md](PATTERNS.md)**.

**1. Read/observe and mutating tools are separate tiers, structurally.** Every tool declares a tier. `tools.call` is the single dispatch point and refuses a `MUTATE` tool without a live reservation token. Observation is never gated — you can always read a chassis someone else is using. There is no passthrough onto the vendor driver, and a test asserts there never will be:

```python
FORBIDDEN = {"send", "write", "raw", "exec", "command", "opbit", "opcrosspoint", "driver", ...}

def test_no_raw_driver_passthrough_is_exposed():
    for name in tools.REGISTRY:
        assert not (set(name.lower().split("_")) & FORBIDDEN), name
```

**2. Deterministic tool walkthroughs are the hard CI gate.** A walkthrough is an ordered list of tool calls and expected results, expressed as data, run against the simulator. `expect_error` is the half that matters most: a switching server's job is as much refusing as connecting.

```
PASS  interlocks: the short is refused as a graph, not as a request, and the fixture is left untouched
  ok  unarmed    route before arming             -> InterlockError
  ok  clean1     nothing closed after refusal    -> 0 crosspoints
  ok  badarm     arm with confirm="yes"          -> InterlockError
  ok  psu        psu_pos -> dut_pin_a1           -> open
  ok  measure    dmm_hi  -> dut_pin_a1           -> open      (measuring under power)
  ok  short      gnd     -> dut_pin_a1           -> InterlockError
  ok  intact     still exactly 2 crosspoints closed
  ok  excl       psu_pos -> dut_pin_a2           -> InterlockError  (exclusive endpoint)
  ok  tc2        second mux channel              -> InterlockError  (closure limit of 1)
  ok  held       opening a crosspoint a route needs -> InterlockError
```

## Tool surface

| Tool | Tier | Purpose |
|---|---|---|
| `chassis_identify` | observe | Backend, driver, topology, current status |
| `list_cards` | observe | Cards, subunits, matrix sizes, closure limits |
| `list_endpoints` | observe | The logical names this topology can route between |
| `list_routes` | observe | Connections currently held open |
| `plan_route` | observe | **Dry run**: crosspoints a route would close, and whether it is permitted |
| `subunit_state` | observe | Every closed crosspoint on one subunit |
| `crosspoint_state` | observe | One crosspoint, and which routes are holding it |
| `interlock_status` | observe | Armed or not, and the policy in force |
| `verify_topology` | observe | The topology's claims vs what the chassis reports |
| `reserve_chassis` | observe | Take a time-boxed reservation; returns the token |
| `list_tool_tiers` | observe | Let an agent plan before it reserves |
| `arm_interlock` | **mutate** | Explicit acknowledgement before any relay moves |
| `disarm_interlock` | **mutate** | Stop new routing; leave existing routes up |
| `route_signal` | **mutate** | Connect two endpoints by the shortest switch path |
| `unroute_signal` | **mutate** | Tear one route down, reference counted |
| `clear_all_routes` | **mutate** | Open everything, forget everything |
| `set_crosspoint` | **mutate** | Direct control, still bounds- and interlock-checked |
| `release_chassis` | **mutate** | Clear routes, disarm, release the reservation |

Chassis lifecycle: `connect → discover → reserve → arm → route → observe → unroute → release`. Releasing tears the fixture down, because an agent that crashes mid-run must not leave a bench live.

Arming takes a literal acknowledgement — `confirm="the fixture is safe to energise"` — rather than a boolean, because a boolean is something a model fills in from context and a fixed string is something it has to mean.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `PICKERING_LXI_ADDRESS` | *(unset)* | LXI unit IP, or `PXI` for local cards. Unset means the in-process simulator. |
| `PICKERING_LXI_TOPOLOGY` | bundled `dut_bench.json` | Path to your fixture map |
| `PICKERING_LXI_SIM_CARD` | `0` | Ask the **vendor driver** for simulated cards (`DriverModes.SIM_CARD`) |
| `PICKERING_LXI_PORT` | `1024` | ClientBridge port |
| `PICKERING_LXI_TIMEOUT_MS` | `5000` | Session timeout |

The default is the simulator on purpose: the interesting failure mode is a server that silently reaches for a rack, not one that refuses to.

## Where the pieces run

| Flag / variable | Default | Meaning |
|---|---|---|
| `--transport` / `PICKERING_LXI_TRANSPORT` | `stdio` | `stdio`, `streamable-http` or `sse` |
| `--host` / `PICKERING_LXI_HTTP_HOST` | `127.0.0.1` | HTTP bind address |
| `--port` / `PICKERING_LXI_HTTP_PORT` | `8000` | HTTP port |
| `--path` / `PICKERING_LXI_HTTP_PATH` | `/mcp` | HTTP endpoint path |
| `--stateless-http` / `PICKERING_LXI_STATELESS_HTTP` | off | Each HTTP request stands alone at the MCP protocol level |

Three deployments, and the only thing that actually constrains them is where the switching driver has to live:

**One workstation, stdio.** The MCP client launches this server as a subprocess, so agent, client and server share a host. The *chassis* need not: an LXI unit is reached over IP, so `PICKERING_LXI_ADDRESS=192.168.1.50` works from any host on that network. This is the right shape for one engineer at one bench.

**Lab-side service, streamable HTTP.** The server runs near the rack and agents connect over the network from wherever they are. This is the shape that matters once more than one agent, or more than one person, needs the same fixture.

**Local PXI cards.** `PICKERING_LXI_ADDRESS=PXI` means the ClientBridge driver is talking to cards in the chassis this process is running in, so the server must run on the PXI controller itself. Everything above it can still be remote — run it there with `--transport streamable-http` and the agents stay wherever they are.

One process serves one chassis. There is a single chassis session shared by every client of the process, because there is a single set of physical relays, and the reservation is what arbitrates between callers. Over stdio that is mostly bookkeeping; over HTTP it is doing the job it was built for:

```
agent-a  reserve_chassis                    -> token 8fa0a571
agent-b  reserve_chassis                    -> ReservationError: chassis is reserved by 'agent-a'
agent-b  list_routes                        -> ok            (observation is never gated)
agent-a  route_signal psu_pos -> dut_pin_a1 -> open
agent-b  route_signal gnd     -> dut_pin_a1 -> InterlockError: would make 'psu_pos' and 'gnd'
                                                electrically common
agent-b  subunit_state matrix_a/1           -> closed_count = 1   (one rack, one truth)
```

A second chassis is a second process on a second port, not a second session in this one.

There are two distinct kinds of simulation here, and they answer different questions. `SimBackend` (the default) is an in-process state machine — no vendor software required, runs in CI, answers *is the routing logic right*. `PICKERING_LXI_SIM_CARD=1` runs the **real** ClientBridge driver against cards that are not in the rack — answers *is the driver integration right*. Use both, in that order.

Hardware support needs the vendor wrapper and the Pickering software suite installed:

```bash
pip install "pickering-lxi-mcp[hardware]"     # adds pilxi
```

`pilxi` imports fine without the driver; only opening a session needs it. That is deliberate — the package installs, imports, tests and runs on a laptop with no Pickering software on it at all.

## Layout

```
src/pickering_lxi_mcp/
  driver.py        Backend protocol; SimBackend (state machine) + PilxiBackend (ClientBridge)
  topology.py      endpoints, patch leads, the switch graph, shortest-path routing
  interlocks.py    the connectivity check, closure ceilings, exclusive endpoints
  session.py       reservations, the mutation gate, reference-counted routes, a journal
  tools.py         typed tool registry with tiers; the single dispatch point
  walkthrough.py   the deterministic runner
  server.py        thin MCP binding — every tool body is one call into tools.call
  topologies/      dut_bench.json, the worked example
walkthroughs/      the gate, as data
```

The MCP tool bodies are deliberately one line each. The server, the tests and the walkthroughs all go through `tools.call`, so a green walkthrough is evidence about the server rather than about a parallel test-only implementation.

## Scope

Written from scratch against the public `pilxi` wrapper and the ClientBridge API surface it documents. The simulator, the example topology and the endpoint names are invented for this repository — no employer or client code, configuration, rack inventory, fixture map or customer name appears anywhere in it. The example bench is a generic matrix-plus-multiplexer arrangement, sized to make the patterns concrete without modelling any particular product.

Where the simulator and a real card disagree, the simulator is wrong and gets fixed.

MIT licensed.
