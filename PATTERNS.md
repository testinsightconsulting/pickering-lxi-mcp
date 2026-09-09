# Three patterns for agents that operate switching

Notes on the design decisions in this repository. Two of them are the same patterns as in the SCPI server that preceded it — tiered tools, deterministic walkthroughs — and are restated here only as far as switching changes them. The third is specific to switching, and is the reason this server exists as its own thing rather than as a card type in a generic instrument server.

---

## 1. The dangerous mistake is a graph, not a value

### The failure mode

Safety checks on instrument control are almost always *value* checks. Is 400 V in range for this supply. Is this frequency inside the generator's band. Is this current limit positive. They work because the dangerous state is visible in the arguments of the call that causes it.

Switching does not work like that. Consider three calls, each of which is obviously fine:

```
route_signal  psu_pos  -> dut_pin_a1     # power the pin
route_signal  dmm_hi   -> dut_pin_a1     # measure it under load
route_signal  gnd      -> dut_pin_a1     # continuity check
```

The third one shorts the supply. Nothing about `("gnd", "dut_pin_a1")` says so — the same call on `dut_pin_a5` is correct and useful. The hazard is not in the request; it is in the state the request *composes with*. An agent reasoning one tool call at a time cannot see it, and neither can an argument validator, because by the time you are validating arguments the relevant information has already been left behind.

It gets worse with patch leads. A fixture with a multiplexer patched onto matrix column 13 has electrical paths that appear in no card's state and in no call's arguments. They are in the wiring, and the wiring is in a document.

### The pattern

Make connectivity a first-class object and check *that*.

Every crosspoint closure is an edge between two line nodes. Every patch lead is an edge between two line nodes, permanently. A forbidden pair is a pair of endpoints that must never end up in the same connected component. Then a route check is:

```python
prospective = closed_now | proposed_by_this_route
components  = connectivity(topology, prospective)      # union-find over line nodes
for a, b in policy.forbidden_pairs:
    if components.connected(endpoint(a).node, endpoint(b).node):
        raise InterlockError(...)                       # nothing has been switched yet
```

Four properties follow, and they are the whole argument for the pattern.

**It catches the composition, not the request.** The third route above is refused because of the first, which is the only place the information lives.

**It is not a blanket refusal.** `dmm_hi -> dut_pin_a1` while the supply is on that pin is *allowed*, because measuring a powered pin is the entire point of the fixture. A rule that forbade switching near a live supply would be safe and useless. This one forbids exactly the pairs the fixture says are forbidden.

**Patch leads participate.** They are edges with no operation attached: traversable by the router, invisible to the switch layer, fully present in the connectivity check. A hazard that only exists because of a wire is caught by the same code as one that exists because of a relay.

**The check runs before the first relay moves.** The plan is computed, the union is taken, the answer is known — and only then does anything close. This is why `route_signal` can be atomic, and why `plan_route` can answer "would this be allowed" without taking the chassis.

### The corollary nobody expects: an empty model is worse than no model

The check above is only as good as its idea of what is closed. Which raises the
question of where that idea comes from when the process has just started.

A chassis is not a blank sheet at boot. A previous run may have died holding a
fixture live; another program may be using the rack. If the server starts with
an empty route table and starts answering questions, every interlock decision is
computed against a fiction — and the fiction is optimistic, so the first thing it
will do is authorise a short. Note the shape of that: *no* safety check would
have been safer than this one, because a server with no interlock at least does
not tell you a route is fine.

So the server reads every subunit before it believes anything, and if it finds
crosspoints no route owns it refuses to switch until a caller resolves it —
adopt the state, which switches nothing but folds those crosspoints into every
later check, or clear it and start from a chassis whose state is known.
Observation stays open throughout, because deciding requires looking.

Two details that are easy to get wrong. Adoption is refused when the found state
already breaks the policy: making a violation the baseline is worse than
refusing to serve, and clearing is the way out. And an adopted crosspoint belongs
to no route, so no `unroute` will open it — nothing in this process knows what
depends on it. Only clearing everything, deliberately, removes it.

### What it costs

The topology file is now load-bearing safety infrastructure. A forbidden pair that nobody declared is not checked, and a patch lead that nobody wrote down makes the connectivity model wrong in the direction that matters. `verify_topology` closes half of that gap by checking the card claims against the chassis; nothing closes the other half, because no driver can tell you what someone plugged into the front panel. The honest statement is that this pattern converts a class of runtime hazard into a class of documentation hazard, and documentation hazards are the ones a review can catch.

The union-find is also rebuilt per check rather than maintained incrementally. At the scale of a rack — hundreds of crosspoints — that is free, and an incremental structure would be a second source of truth about state. When it stops being free, the fix is a cache with the route table as its key, not a smarter data structure.

---

## 2. Read/observe and mutating tools are separate tiers

The argument is the same as for any instrument server, so here is only what switching adds.

The obvious way to expose a switching card is one tool that mirrors the driver:

```python
@mcp.tool()
def op_crosspoint(card: str, subunit: int, row: int, column: int, state: bool) -> str:
    return card.OpCrosspoint(subunit, row, column, state)
```

This is a great demo and it is unshippable, for the usual reason — the system cannot distinguish a read from a write, so there is nowhere to put a permission check — and for one specific to switching: **crosspoint coordinates carry no meaning that a safety check can use.** `(3, 1)` is not "ground to pin A1" to anything except the person who wrote the fixture map. A server whose vocabulary is coordinates can range-check them and nothing else.

So the tier split here does double duty. It gates mutation behind a reservation, as it would anywhere. It also forces the tool vocabulary to be *endpoints*, because that is the only vocabulary in which the interesting refusals are expressible.

`set_crosspoint` still exists, because commissioning a fixture genuinely needs it. Note what it is not:

* it cannot name a card or subunit that is not in the topology;
* it cannot exceed the matrix size the card itself reports;
* it cannot open a crosspoint that a live route is holding up;
* and closing one goes through the same connectivity check as a named route.

That is the difference between a low-level tool and a passthrough. The test that keeps it that way is a name check, and it is aimed at a pull request that does not exist yet:

```python
FORBIDDEN = {"send", "write", "raw", "exec", "command", "opbit", "opcrosspoint", "driver", "eval"}

def test_no_raw_driver_passthrough_is_exposed():
    for name in tools.REGISTRY:
        assert not (set(name.lower().split("_")) & FORBIDDEN), name
```

Two smaller decisions in the same spirit.

**Arming takes a sentence, not a boolean.** `arm_interlock(token, confirm="the fixture is safe to energise")`. A boolean argument is something a model fills in from context; a fixed string is something it has to mean. This is a small amount of friction placed exactly where friction is worth having.

**Releasing tears the fixture down.** `release_chassis` clears every route and disarms before it drops the reservation. An agent that crashes mid-run must not leave a bench live, and the reservation expiry that eventually frees the chassis for someone else must not be the thing that decides how long the DUT stays powered.

### What it costs

An agent must plan before it acts: `plan_route`, `reserve_chassis`, `arm_interlock`, then `route_signal`. That is three round trips before anything happens and a genuinely worse demo. It is also the difference between a prototype and something you will let near a fixture.

And the tier split has to be *maintained*. A tool that reads a value but resets a latch on the way is a mutating tool whatever its name suggests. On switching hardware the realistic version of this is a diagnostic read that pulses a relay — a judgement call per card, and the way this pattern actually fails.

---

## 3. Deterministic tool walkthroughs are the hard CI gate

Agent systems are usually evaluated by asking a model to do a task and having another model score the transcript. LLM-as-judge is genuinely useful — it catches vagueness, missing caveats, answers that are correct but useless. It is also a sampled, non-deterministic signal, which makes it a bad thing to block a merge on. Judges disagree with themselves across runs; teams respond by loosening the threshold until it stops firing, at which point the gate is decorative.

The failures that actually break a fixture are boring and completely deterministic: a return shape changed, an argument got renamed, the interlock check got skipped on one branch, a teardown stopped reference counting and started opening crosspoints another route was using.

So: express a walkthrough as data — an ordered list of tool calls with expected results — and run it against the simulator, in CI, as a blocking step.

```json
{ "id": "psu",    "tool": "route_signal", "args": { "token": "{{res.token}}", "from_endpoint": "psu_pos", "to_endpoint": "dut_pin_a1" }, "expect": { "status": "open" } },
{ "id": "short",  "tool": "route_signal", "args": { "token": "{{res.token}}", "from_endpoint": "gnd",     "to_endpoint": "dut_pin_a1" }, "expect_error": "InterlockError" },
{ "id": "intact", "tool": "subunit_state", "args": { "card": "matrix_a", "subunit": 1 }, "expect": { "closed_count": 2 } }
```

**Refusals are assertions.** `expect_error` means a walkthrough can prove the interlock *fires*, not merely that the happy path works. For a switching server this is more than half the value — of the twenty steps in the interlock walkthrough, seven assert that something was refused and four that the fixture was left exactly as it was.

**"Nothing was switched" is itself assertable.** The step after every refusal is a state read. A refusal that leaves three crosspoints closed is not a refusal, and only an explicit assertion catches that.

**Steps consume earlier results.** `{{res.token}}` is what makes a reservation-gated sequence expressible as data instead of code. Without it every walkthrough becomes a Python function and drifts away from being a specification.

**The simulator is a state machine, not a mock.** `SimBackend` enforces crosspoint bounds, per-subunit closure limits, masked crosspoints and cleared-on-open semantics. A mock returning canned values would let a walkthrough pass while the closure-limit path was broken; a state machine that refuses the ninth closure on an eight-closure subunit will not.

**Same dispatch path as production.** The MCP tool bodies are one-liners into `tools.call`, and the walkthrough runner calls `tools.call` too. If those were two implementations, a green walkthrough would be evidence about the test harness.

### Where the judge still belongs

Deterministic walkthroughs cannot tell you whether an agent *chose* to call `plan_route` before reserving, explained a refusal in terms an engineer could act on, or gave up when it should have tried a different pin. That is exactly what a judge is good at.

| | Deterministic walkthrough | LLM-as-judge |
|---|---|---|
| Question | did the tool contract hold? | did the agent behave sensibly? |
| Signal | binary, reproducible | graded, sampled |
| In CI | **blocking** | advisory; routes to human review |

Run both. Block on one.

### What it costs

Walkthroughs are a second artifact to maintain, and they go stale in the specific way that hurts: a tool's contract changes, someone updates the walkthrough to match, and the gate silently ratifies a regression. The mitigation is that a walkthrough edit should be as reviewable as a source edit — an argument for keeping them small, few and readable, not for generating hundreds.

And the simulator is a claim about the card. It is worth exactly as much as its fidelity. When a real 40-series matrix disagrees with it, the simulator is wrong and gets fixed; the temptation to fix the walkthrough instead is the thing to watch for.
