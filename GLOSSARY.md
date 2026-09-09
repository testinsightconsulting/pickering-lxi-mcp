# Nomenclature

Words this project uses in a specific way, with the bench in
`src/pickering_lxi_mcp/topologies/dut_bench.json` as the worked example throughout.

Four of these terms are coined here — **fabric domain**, **unowned crosspoint**, the
**reservation / lease** split, and the **switch topology / test topology** split. They are marked. Everything else is either the vendor's
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
> the topology, never declared: `list_fabric_domains`, or `Topology.fabric_domains()`.

### What a fabric domain does not respect

The chassis → card → subunit hierarchy. The domain partition cuts across it in *both*
directions, and assuming otherwise is the most likely modelling error:

| | | |
|---|---|---|
| **Below** | A subunit is the floor and is never split | Every row of a matrix reaches every column, so all 8×16 of `matrix_a/sub1` is one domain. A caller who wants four columns gets all twenty-four lines. |
| **Sideways** | One card can host several domains | With the patch leads removed, `mux_b` hosts `mux_b/sub1` and `mux_b/sub2` as two independently leasable domains. |
| **Above** | One patch lead merges chassis | A single lead from a column in chassis 1 to a row in chassis 2 makes both matrices one domain, routable end to end in two closures. |

So "this card belongs to that fabric" is not a well-formed statement — cards do not belong to
domains, *subunits* do, and which subunits share a domain is a fact about the wiring rather than
about the enclosure.

**Lease scope** — the consequence for a broker. You do not lease the endpoints you asked for; you
lease every domain they touch, whole. `domains_for(["dut_pin_a1"])` on the example bench returns
one domain containing all 28 endpoints. Expand the request to whole domains *before* acquiring,
or the all-or-nothing guarantee is over a set that does not match what actually gets used.

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

**Vendor MCP server** — one process, one switch topology, one truth about the relays in it. A long-lived
daemon clients connect *to*, never a subprocess a client spawns. It is also the broker's unit of
resource: one server, one reservation, one thing to lease.

**Gateway** — one authenticated endpoint per lab host, in front of the vendor servers that bind
loopback. Namespaces the fleet, carries the audit log.

**Broker** — one fleet-wide service issuing leases across racks, over the set of resources a test
topology names. Not built.

**Control plane / signal plane** — the control plane is a star: agents talk to servers. The
signal plane is a fabric: instruments reach the DUT through the matrix. Same boxes, different
topology, and confusing them is how the switching server gets mistaken for one instrument among
several rather than the layer the others are reached through.

---

## 7  Two things called "topology"

This word was doing double duty, and the two objects it named are not the same size.

**Switch topology** — what this server loads: one file describing one switching fabric. Cards,
subunits, endpoints, patch leads, interlock policy. One per process. `Topology` in the code is
always this one.

**Test topology** — the lab-level contract: everything a workflow needs, across every vendor.
Switching, scope, traffic generator, emulator, the DUT. It names resources on several servers and
declares the connections between them. Nothing in this repository implements it, and it needs
nothing from this repository to exist — it sits entirely above the server.

> When these pages say "topology" unqualified they mean the switch topology, because that is what
> the code loads. Talking to a lab, "topology" almost always means the test topology. Say which.

Two things called **endpoint**, too. Here an endpoint is a named line on a switch (`psu_pos`). In
deployment writing it usually means a URL. This document says **address** for the second, and
"endpoint" only ever means the first.

---

## 8  Containment, and what owns what

**domain ⊆ switch topology = process ∈ test topology.** Each link earns its place differently.

**A domain never spans two switch topologies.** Forced, by the interlock: a safety question about
any line in a domain can only be answered by reading every other line in it, so splitting one
across two processes leaves both reasoning from a partial picture. If a patch lead ties two chassis
together, those chassis are one switch topology in one process — there is no configuration in which
they are two servers.

**A switch topology may contain many domains.** A free choice, made when the file is authored.
Nothing stops you describing four unrelated benches in one file; nothing requires you to.

**One process serves one switch topology.** One route table, one interlock, one lock, one
reservation, one address.

**A test topology contains many processes.** It is the contract, and it is atomic: held whole by
one user under one reservation, or not held at all. A resource in it that cannot be acquired, or
that is lost mid-run, does not degrade the contract — it voids the reservation and the workflow
aborts. Which is why a lease is renewable rather than merely time-boxed: the renewal is how a
broken contract gets noticed before the workflow acts on a fixture it no longer owns.

> An earlier phrasing — "one process per fabric domain" — was too strong, and survives in `docs/`
> and in the commit history. The domain is the *minimum* a process must contain, not the maximum.

### Connections that cross a domain, and why the server is right to refuse them

A **switch path** never crosses a fabric domain boundary — that is what a domain means. A
**connection in a test topology** crosses them routinely, because it is a composition, and not
everything it composes is a relay.

```
awg_out ──[ domain A ]──▶ DUT in  ···  DUT  ···  DUT out ──[ domain B ]──▶ scope_ch1
```

Asked to route `awg_out` to `scope_ch1`, the switching server correctly raises `PathError`: there
is no path through relays, and inventing one would be a lie about the fixture. The connection is
real; it lives in the test topology, which knows about the DUT. Segment ownership stays with each
server, end-to-end ownership belongs to the contract.

**The safety consequence is a real limit, not a gap in the implementation.** If the DUT connects
its input to its output internally, domains A and B are electrically common *through the DUT*, and
no switching server can know — connectivity through a bridge element is a property of the bridge,
not of anybody's driver. A forbidden pair spanning that bridge cannot be enforced by any single
server, and the interlock here does not claim to. Only the test topology is positioned to declare
such a rule, and even then it is asserting something about the DUT that nothing verifies.

### The unit of ownership

A reservation on this server covers its whole switch topology, and therefore every domain in it.
One owner at a time; anyone else waits, or is scheduled.

Domain-level ownership would also be *safe* — routes never cross a domain boundary, and a forbidden
pair whose endpoints sit in different domains cannot fire even with every crosspoint on the chassis
closed, so an interlock is domain-local by construction. Safety does not force the coarser choice.
Three other things do:

* a switch topology is authored for a purpose — the patch leads *are* the experiment;
* two users on one fixture share more than switching: the DUT, the ground reference, the bench;
* it keeps each server's resource flat — one switch topology, one server, one address, one resource
  id, no hierarchical addressing and no partial acquisition *inside* a server. Naming several such
  resources together is the test topology's job. The flatness is per-server, not fleet-wide.

Which moves the decision to authoring time, where it belongs: **write switch topologies at the
granularity you intend to share.** Four independent benches used independently should be four files
and four servers, not one file leased whole. `list_fabric_domains` is how you check — a switch
topology reporting several disjoint domains is telling you it *could* be split, and asking whether
it should be.

### And none of this is about users

How many people or agents use a process is unrelated and unbounded. They multiplex through it, and
what separates them is the reservation, the lock and the lease — never process isolation. Giving
each engineer their own process would reintroduce the bug the rule exists to prevent: N route
tables, N interlocks each reasoning from its own partial picture, and a short every one of them
would have refused individually.

| | Determined by | Count |
|---|---|---|
| Domains | the wiring | computed, never declared |
| Processes | the switch topology files you authored | one per switch topology |
| Test topologies | the workflows you run | one per contract, spanning many processes |
| Users / agents | who is working | unbounded, orthogonal |

The axes meet at one place: many users, one at a time, per test topology — and therefore per switch
topology inside it.

### Vacuous rules

Because an interlock is domain-local, a forbidden pair naming two endpoints in different domains is
unreachable: it looks like protection and provides none. `verify_topology` reports it, and the
usual cause is worth knowing — a patch lead that exists in the rack and not in the file. The
interlock then reasons over a fixture less connected than the real one, which is the failure with
no runtime symptom. This does not find missing leads in general; it finds the ones that have
silently disarmed a rule somebody thought they had.
