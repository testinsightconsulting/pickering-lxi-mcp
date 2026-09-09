# Nomenclature

Words this project uses in a specific way, with the bench in
`src/pickering_lxi_mcp/topologies/dut_bench.json` as the worked example throughout.

Three of these terms are coined here — **fabric domain**, **unowned crosspoint**, and the
**reservation / lease** split. They are marked. Everything else is either the vendor's
vocabulary or ordinary MCP vocabulary, and where this project's usage is narrower than the
common one, that is called out.

---

## 1  The hardware, as the driver describes it

These are Pickering's words, not ours. They appear in `driver.py` and in the topology file.

| Term | Definition | On the example bench |
|---|---|---|
| **Chassis** | The physical enclosure the cards sit in. Reached over IP as an LXI unit, or through the backplane as local PXI. | One simulated chassis |
| **Card** | One switching module in the chassis, addressed by `(bus, device)`. Given a short **alias** in the topology so nothing downstream has to know the slot. | `matrix_a` at bus 4 device 14, `mux_b` at bus 4 device 15 |
| **Subunit** | An independently addressed switching block on a card. One card can have several of different shapes. | `matrix_a` has one; `mux_b` has two |
| **Row**, **Column** | The two axes of a subunit. Collectively, **lines**. | `matrix_a/sub1` is 8 rows × 16 columns |
| **Crosspoint** | The relay at one (row, column). Closing it makes that row and that column electrically common. The atom of everything here. | `matrix_a/sub1(4,1)` connects `scope_ch1` to `dut_pin_a1` |
| **MUX / MUXM** | A subunit with one row. A `MUX` allows one channel closed at a time; a `MUXM` allows several. Both are matrices in the model, so the routing code has no special case for either. | `mux_b/sub1` is a 1×16 MUX (limit 1); `mux_b/sub2` a 1×8 MUXM (limit 4) |
| **Closure limit** | How many crosspoints a subunit may hold closed at once — a real electrical and thermal constraint, not a policy. | 12 on the matrix, 1 on the MUX |
| **Settle time** | How long a relay takes to reach its new state, in microseconds. Reported per subunit. | 3000 µs on the matrix |
| **Mask** | A crosspoint marked unusable in hardware, which will not close. Modelled in the simulator; not yet exposed as a tool. | — |

**Note on "port".** Deliberately avoided. On a matrix it is ambiguous — a row and a column are
both things people call ports, and they behave completely differently. Say *row*, *column*, or
*endpoint*.

---

## 2  The map, and routing over it

The layer that turns names a person uses into crosspoints. `topology.py`.

**Endpoint** — a name bound to exactly one line. `psu_pos` is `matrix_a/sub1 row 1`. Endpoints
are what every tool in the server takes and returns; crosspoints are an implementation detail
that leaks out only in `set_crosspoint` and in observation. An endpoint carries a **role**
(`source`, `ground`, `instrument`, `dut`, `sensor`) which is documentation — the interlocks read
the explicit rules, not the roles.

**Link (patch lead)** — a hard-wired connection between two lines, declared in the topology.
Traversable when routing, invisible to switching, and fully present in every safety check. The
example bench has two: matrix column 13 to the MUX common, and column 14 to the MUXM common.
*A link is the part of the fixture that exists in a document rather than in a driver, which is
why it is the most dangerous thing to get wrong.*

**Switch graph** — lines as nodes; a switchable edge per crosspoint, a zero-cost edge per link.
Built once at load.

**Operation** — one crosspoint to operate, as `(card, subunit, row, column)`. Hashable, so two
routes that share a crosspoint are *seen* to share it. Printed as `matrix_a/sub1(6,13)`.

**SwitchPath** — a computed, not-yet-applied sequence of operations between two endpoints.
Shortest path by number of closures, because relay closures are the wear item.

**Route** — a SwitchPath that has been applied and is being held open, with an owner and an id.
Route ids are undirected: `route_id("a","b") == route_id("b","a")`, rendered `a<->b`.

**Fabric domain** *(coined here)* — a set of lines that can become electrically common with each
other. Formally: a connected component of the switch graph with *every* crosspoint treated as
closable, not merely the ones closed now. This is the unit that must be leased, locked and
owned as a whole, because a safety question about any line in it can only be answered by reading
every other line in it.

> The example bench is **28 endpoints in 1 fabric domain** — both patch leads tie the matrix and
> both multiplexers together. Remove the leads and it becomes three. The number is computed from
> the topology, never declared.

---

## 3  Safety

`interlocks.py`. All of it reasons about connectivity, never about intent.

**Interlock** — the whole check, run before any relay moves. Narrower than the industrial sense
of a physical safety switch; here it is entirely in software.

**Connectivity** — union-find over the switch graph given a set of closed crosspoints, answering
"are these two lines currently common".

**Forbidden pair** — two endpoints that must never end up in the same connected component.
`["psu_pos", "gnd"]`. The check is on the *composition* of everything closed plus everything
proposed, which is why a route can be refused for a reason that has nothing to do with the route
itself.

**Exclusive endpoint** — may take part in at most one open route. `psu_pos` on the example bench.

**Arm** — a chassis-wide acknowledgement that must be given before anything switches, taking the
literal string `the fixture is safe to energise` rather than a boolean. A boolean is something a
model fills in from context; a fixed string is something it has to mean.

**Plan** — a dry run. Computes the path and runs the interlocks against it, switches nothing,
needs no reservation. The tool an agent should reach for first.

**Violation** vs **refusal** — a *violation* is a rule broken by a state (`describe_violations`
lists all of them, for a state someone else produced). A *refusal* is a rule that stopped an
action (`check_route` raises on the first, for an action being proposed). Different questions,
different functions.

---

## 4  Access

**Tier** — every tool is `OBSERVE` or `MUTATE`, declared structurally and enforced at one
dispatch point. Observation is never gated, including on a chassis someone else holds.

**Reservation** — single-writer access to **one fabric domain, in one server**. Time-boxed,
held by an `owner` string, identified by a `token` every mutating call must present. This exists
and works today.

**Lease** *(coined here; not built)* — all-or-nothing access to a **set of resources across
several servers**, granted by the broker. Matrix + scope + supply as one grant, acquired in a
fixed global order so two agents cannot deadlock half-held.

> Keep these two apart. A reservation is what one server enforces about itself; a lease is what
> a broker asserts across many. The current code has only reservations, and calling them leases
> would imply a coordination guarantee nothing provides. When the broker exists, a reservation
> becomes the thing a server grants *because* a valid lease was presented.

**Owner** — who holds the reservation. Today a self-declared string: a courtesy label, not an
authenticated identity. It becomes real when the gateway authenticates and the broker signs.

**Token** — proves the caller went through `reserve_chassis`. Not an authentication mechanism.

**The lock** — a process-local mutex held across check-and-apply, so those two steps cannot be
separated by another thread. **The lease answers *who*, the reservation answers *who, here*, and
the lock answers *when*.** All three are needed and none substitutes for another.

---

## 5  Startup state

**Reconciliation** — reading every subunit at startup and comparing it against what this process
believes. A chassis is not a blank sheet: a previous run may have died holding a fixture live.

**Unowned crosspoint** *(coined here)* — a crosspoint found closed that no route in this process
holds. "Unowned" says nothing about legitimacy; it says only that nothing here can tell you what
depends on it. One word on the wire, in the code and in the refusal text.

**Unreconciled** — the session state when unowned crosspoints exist. Everything that could
energise the fixture is refused; observation is untouched, because deciding requires looking.

**Adopt** — keep what was found and fold it into every later interlock check. Switches nothing.
Refused when the found state already breaks the policy, because making a violation the baseline
is worse than refusing to serve.

**Clear** — open everything and start from a chassis whose state is known. Always available,
including from the state adoption refuses.

---

## 6  Deployment

**Vendor MCP server** — one process, one fabric domain, one truth about the relays in it. A
long-lived daemon clients connect *to*, never a subprocess a client spawns.

**Gateway** — one authenticated endpoint per lab host, in front of the vendor servers that bind
loopback. Namespaces the fleet, carries the audit log.

**Broker** — one fleet-wide service issuing leases across racks. Not built.

**Control plane / signal plane** — the control plane is a star: agents talk to servers. The
signal plane is a fabric: instruments reach the DUT through the matrix. Same boxes, different
topology, and confusing them is how the switching server gets mistaken for one instrument among
several rather than the layer the others are reached through.

---

## 7  What "one process per fabric domain" does *not* mean

It is a statement about **devices**, not about **users**.

The rule is that one fabric domain has exactly one process speaking to it, because one set of
relays can only have one truth about its state. How many people or agents use that process is
unrelated and unbounded — they multiplex through it, and what separates them is the reservation,
the lock and (eventually) the lease, not process isolation.

Giving each engineer their own process would reintroduce the exact bug the rule exists to prevent:
N processes, N route tables, N interlocks each reasoning from its own partial picture, and a
short that every one of them would have refused individually.

| | Determined by | Count |
|---|---|---|
| Processes | the wiring — one per fabric domain | fixed by the rack |
| Users / agents | who is working | unbounded, orthogonal |

The two axes only meet at the reservation: many users, one at a time, per fabric domain.
