# A worked bench: RF, DC and LAN under one contract

Everything here is real except the DUT. Model numbers are current products, the two figures that
matter most are quoted from vendor datasheets with links, and the topology file is shipped and
validated in CI. Where a number is *asserted* rather than looked up, it says so — that distinction
runs through the whole design and it would be dishonest to blur it in the example.

Validate it yourself:

```bash
pickering-lxi-mcp-validate src/pickering_lxi_mcp/topologies/rf_bench.json
PICKERING_LXI_TOPOLOGY=rf_bench pickering-lxi-mcp
```

---

## 1  Equipment

| Role | Model | What the topology takes from it |
|---|---|---|
| Switching chassis | **Pickering 60-103-001**, 18-slot LXI modular chassis | one server, one management address |
| RF mux — source side | **Pickering 40-785B-521**, single SP6T, 18 GHz, 50 Ω SMA | `rf_src`, 1×6 MUX, one channel at a time |
| RF mux — receive side | **Pickering 40-785B-521** | `rf_rx`, 1×6 MUX |
| GP matrix — DC and control | 40-series general-purpose matrix, model to suit pin count | `gp_matrix`, 6×12 |
| Signal generator | **Keysight N5182B MXG**, Opt 1EA | `sig_gen_out`, **+26 dBm** max output |
| Signal analyser | **Keysight N9020B MXA** | `analyser_in`, **+30 dBm** max input |
| Power sensor | average power sensor | `power_sensor`, +20 dBm *(asserted)* |
| Traffic generator | **Spirent TestCenter SPT-N4U** | not switched — see §4 |
| DUT | a radio with an Ethernet management port | every `dut_*` endpoint *(asserted)* |

**The two numbers the interlock actually turns on:**

- N5182B with Option 1EA: **+26 dBm typical**, 10 MHz–3 GHz (+24 dBm specified). Datasheet maximum,
  *not* the level currently programmed — the interlock has to reason about what the instrument
  *can* do, because the setting is one SCPI command away from changing.
- N9020B: **+30 dBm** average total power, and ±0.2 Vdc DC-coupled. That DC limit is worth noting
  separately: this model has no predicate for volts, only dBm. See §7.

Everything else marked *(asserted)* comes from a datasheet by way of whoever wrote the file, and
`verify_topology` lists it as unverifiable for exactly that reason.

---

## 2  Rack layout

Two racks, because the fabric domains follow the wiring and it is easier to keep them separate if
the hardware is.

```
RACK A — signal                          RACK B — control and traffic
┌────────────────────────────────┐       ┌────────────────────────────────┐
│ 42U                            │       │                                │
│  ── N5182B MXG                 │       │  ── OOBM switch  (isolated)    │
│  ── N9020B MXA                 │       │  ── console server             │
│  ── power sensor / meter       │       │  ── switched PDU (A feed)      │
│  ──                            │       │  ── switched PDU (B feed)      │
│  ── 60-103-001 LXI chassis     │       │  ──                            │
│       slot 1  40-785B-521 src  │       │  ── mgmt switch — instruments  │
│       slot 2  40-785B-521 rx   │       │  ── mgmt switch — DUT + data   │
│       slot 3  GP matrix        │       │  ──                            │
│  ──                            │       │  ── SPT-N4U TestCenter         │
│  ── DUT                        │       │  ── jump host (only multi-homed│
│  ── patch panel, SMA           │       │       device in either rack)   │
└────────────────────────────────┘       └────────────────────────────────┘
```

Two things in that layout are deliberate. The **OOBM switch is its own box**, not a VLAN on the
management switch — its independence is the entire product, and a VLAN on shared silicon is
in-band with extra steps. And **instrument management and DUT management are separate switches**,
for the reason in §4.

---

## 3  Cabling

### RF — source side, `rf_src` (SP6T, one channel at a time)

| From | To | Cable | Endpoint |
|---|---|---|---|
| N5182B RF OUT | rf_src COM | SMA, phase-stable | `sig_gen_out` |
| rf_src ch 1 | DUT RX (direct) | SMA | `dut_rx_direct` |
| rf_src ch 2 | 20 dB pad → DUT RX | SMA | `dut_rx_padded` |
| rf_src ch 3 | patch panel → `rf_rx` ch 3 | SMA jumper | `loop_src` |
| rf_src ch 4 | power sensor | SMA | `power_sensor` |
| rf_src ch 5–6 | spare, terminated | 50 Ω loads | — |

### RF — receive side, `rf_rx`

| From | To | Cable | Endpoint |
|---|---|---|---|
| N9020B RF IN | rf_rx COM | SMA | `analyser_in` |
| rf_rx ch 1 | DUT TX | SMA | `dut_tx` |
| rf_rx ch 2 | DUT 10 MHz REF OUT | SMA | `dut_ref_clk` |
| rf_rx ch 3 | patch panel → `rf_src` ch 3 | SMA jumper | `loop_rx` |
| rf_rx ch 4 | noise source | SMA | `noise_source` |

**That jumper between `rf_src` ch 3 and `rf_rx` ch 3 is the calibration loop, and it is the single
most important line in this document.** It is a *link* in the topology file — traversable when
routing, never switched, and always counted in safety. It is also why the two multiplexers are one
fabric domain rather than two. Pull it and they separate; forget to declare it and every safety
rule spanning the two cards silently stops working. `pickering-lxi-mcp-validate` catches that
specific mistake, because the rule it disarms becomes a forbidden pair spanning two domains.

### DC and control — `gp_matrix` (6 × 12)

Rows are instruments and supplies (`psu_pos`, `psu_neg`, `gnd`, `dmm_hi`, `dmm_lo`, `dio_enable`);
columns are DUT pins (`dut_vcc`, `dut_gnd`, `dut_enable`, `dut_reset`, `dut_testpt1`,
`dut_testpt2`). Nothing here is patched to the RF cards, which is why it is a second, independent
fabric domain.

---

## 4  The four planes

| Plane | Carries | Subnet | Switch |
|---|---|---|---|
| **OOBM** | console server, both PDUs, chassis BMC | `10.10.0.0/24` | its own, isolated |
| **Instrument management** | 60-103-001, MXG, MXA, power meter | `10.10.1.0/24` | mgmt switch A |
| **DUT management** | the DUT's mgmt port | `10.10.2.0/24` | mgmt switch B |
| **Data** | SPT-N4U test ports ↔ DUT data ports | under test | direct cabling |

**Instrument management and DUT management are separate on purpose, and this is the one
recommendation here that is inference rather than received doctrine.** LXI Security — TLS, HiSLIP
SASL authentication, 802.1AR device certificates — is an *optional* extended function, not part of
base LXI conformance. Its own definition of "Unsecure Mode" is a client being able to change a
device's *"measurement/stimulus/**routing** configuration"* over Ethernet without authentication.
That is their word for switching, and it describes most deployed LXI. Pickering's client API is
consistent with it: `PICMLX_Connect(board, address, port, timeout, session)` takes no credentials.

So anything that can route to port 1024 on that chassis can operate the relays. Put the DUT's
management interface in the same L3 domain and a DUT you are deliberately stressing is one hop from
your switching. Keep them apart, and **test that they are apart**: from the DUT's management
interface, opening port 1024 on the chassis should fail. That check is the management plane's
nearest equivalent to `verify_topology`, and it is worth a cron job.

The **jump host is the only multi-homed device**, and it does not route between instrument
management and DUT management.

The TestCenter ↔ DUT data links are cabled directly and appear nowhere in the topology file. That
is correct and worth saying out loud: **a switch topology contains only what the matrix can
switch.** Those links belong to the test topology — the contract — one level up.

---

## 5  What the validator says

`pickering-lxi-mcp-validate src/pickering_lxi_mcp/topologies` reads the file and nothing else —
no chassis, no driver, no simulation. It runs in CI on every commit. Abridged output for this
bench:

```
rf-bench — 3 card(s), 22 endpoint(s)
  note  dut_tx (+23.0 dBm) can reach dut_ref_clk (+10.0 dBm) — 13.0 dB over.
        Any route making them common will be refused.
  note  sig_gen_out (+26.0 dBm) can reach dut_rx_direct (+10.0 dBm) — 16.0 dB over. …
  …9 such pairs in total…
  note  2 fabric domain(s): gp_matrix/sub1, rf_rx/sub1
  note    gp_matrix/sub1: 12 named endpoint(s) of 18 lines, subunits gp_matrix/sub1
  note    rf_rx/sub1: 10 named endpoint(s) of 14 lines, subunits rf_rx/sub1, rf_src/sub1
  note  asserted, unverifiable: 1 link(s), 3 forbidden pair(s), 8 power rating(s), and that
        every endpoint name matches what is physically on that line
  → OK: 0 problem(s), 0 warning(s)
```

Two domains, as the cabling implies: the RF side is one domain because the calibration loop
patches `rf_src` column 3 to `rf_rx` column 3, and the DC matrix is another because nothing
bridges it. Nine overload pairs the interlock will refuse, enumerated before anyone has plugged
anything in. And an explicit statement of what the check could *not* verify.

The shipped `dut_bench.json` deliberately validates with one warning — a rated source that can
reach twenty-two unrated destinations — because that is the finding this tool exists to produce,
and an example that only ever prints OK teaches nothing.

---

## 6  What an agent does on this bench

Every line below is actual behaviour of `rf_bench.json` on the simulation backend, not a
sketch. It is pinned as `walkthroughs/08_rf_bench.json` and runs in CI, so if the server's
answers change, this section fails the build rather than quietly going stale:

```
plan_route      sig_gen_out  → dut_rx_direct   permitted: false — +26 dBm into a +10 dBm input,
                                               16.0 dB over
plan_route      sig_gen_out  → dut_rx_padded   permitted: true, 1 closure   ← the pad is the answer

reserve_chassis owner=engineer-a               token
arm_interlock   confirm="the fixture is safe to energise"

route_signal    sig_gen_out  → dut_rx_padded   open
route_signal    sig_gen_out  → power_sensor    refused: 'sig_gen_out' is exclusive and is already
                                               part of route 'dut_rx_padded<->sig_gen_out'
route_signal    dut_tx       → analyser_in     open
route_signal    noise_source → analyser_in     refused: would leave 2 crosspoints closed on
                                               rf_rx subunit 1, over the limit of 1
route_signal    psu_pos      → dut_vcc         open
route_signal    gnd          → dut_vcc         refused: would make 'psu_pos' and 'gnd'
                                               electrically common, which the topology forbids

release_chassis                                clears every route, disarms
```

Four refusals, four different causes: a power limit, an exclusive endpoint, the SP6T's physical
one-channel-at-a-time closure limit, and a connectivity interlock. None depends on the agent
being careful, and none of them switched anything before refusing.

Note that the two `plan_route` calls come *before* `arm_interlock`. The plan answers the
substantive question — is this route permitted — separately from the session question — is the
interlock armed. It reports `permitted: false` with the power refusal *and* `requires_arming:
true`, as two different facts. So an agent can survey the bench and be told exactly why a path is
refused without ever energising it, and "you haven't armed yet" never masks "this would destroy
the DUT".

---

## 7  What this bench does not protect you from

- **Frequency.** Isolation is a curve; this model has a boolean. Two lines isolated at DC can be
  coupled at 6 GHz and nothing here will say so.
- **Insertion loss.** Paths are treated as lossless, so the pad in `dut_rx_padded` is handled by
  *naming the pad input as the endpoint* rather than by arithmetic. That is deliberate: a computed
  budget would be asserted from datasheets anyway, and a damage limit is a bad place for a number
  nobody measured.
- **Volts.** The N9020B's ±0.2 Vdc limit has no predicate here. dBm is the only magnitude modelled,
  and a DC fault into an RF input is a real way to destroy a front end.
- **The wiring itself.** Every link, rating and endpoint name is asserted. `verify_topology` checks
  what the driver reports; nothing checks what is actually on the other end of a cable.

---

## Sources

- [Pickering 60-103-001 — 18-slot LXI modular chassis](https://www.pickeringtest.com/en-us/product/lxi-modular-switching-chassis--18-slot)
- [Pickering 40-785B-521 — PXI single SP6T RF MUX, 18 GHz, 50 Ω SMA](https://www.pickeringtest.com/en-us/product/40-785b-single-6-ch-rf-mux-18ghz-50ohm-sma)
- [Keysight N5182B MXG datasheet](https://www.cmc.ca/wp-content/uploads/2019/08/Agilent_N5182B_Datasheet.pdf) — max output power by band and option
- [Keysight N9020B MXA specifications guide](https://www.keysight.com/us/en/assets/9018-04846/technical-specifications/9018-04846.pdf) — +30 dBm average total power, ±0.2 Vdc DC coupled
- [Spirent TestCenter SPT-N4U chassis](https://www.spirent.com/Products/TestCenter/Platforms/Appliances)
- [LXI Security Extended Function 1.1](https://public.lxistandard.org/specifications/LXI_1.6_Specifications/LXI_Security_Extended_Function_1.1_2023-01-26.pdf) — optional; defines "Unsecure Mode"
- [Cisco — Out-of-band management best practices](https://www.cisco.com/c/en/us/solutions/collateral/service-provider/out-of-band-best-practices-wp.html)
