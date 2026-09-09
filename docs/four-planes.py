import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.lines import Line2D

BG, INK, MUTED, LINE = "#FAF9F6", "#17171A", "#6E6E73", "#C6C4BD"
ACC,   ACCF   = "#A84A17", "#F5EFE8"   # signal / fabric
BLUE,  BLUEF  = "#2B5C86", "#E8F0F6"   # data
GREEN, GREENF = "#3A6647", "#E8F0EA"   # management
PLUM,  PLUMF  = "#5B3A7E", "#EEE9F4"   # out-of-band management
RED = "#9A2F2F"
WHITE = "#FFFFFF"

# dpi is set here, not only at savefig: text is measured through the renderer
# below, and a bbox measured at one dpi does not describe a layout drawn at another.
fig, ax = plt.subplots(figsize=(19.2, 15.6), dpi=150)
fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
ax.set_xlim(0, 19.2); ax.set_ylim(0, 15.6); ax.axis("off")

def rbox(x0, y0, x1, y1, edge=LINE, fill=WHITE, lw=1.3, r=0.10, z=2, ls="-"):
    ax.add_patch(FancyBboxPatch((x0, y0), x1-x0, y1-y0,
        boxstyle=f"round,pad=0.02,rounding_size={r}", linewidth=lw,
        edgecolor=edge, facecolor=fill, zorder=z, linestyle=ls))

def txt(x, y, s, size=9.2, color=INK, ha="left", va="center", weight=None,
        style=None, z=6, ls=1.55):
    ax.text(x, y, s, fontsize=size, color=color, ha=ha, va=va, fontweight=weight,
            style=style, zorder=z, linespacing=ls)

def wire(x1, y1, x2, y2, color=MUTED, lw=1.0, z=3):
    ax.add_line(Line2D([x1, x2], [y1, y2], color=color, lw=lw, zorder=z))

def node(cx, cy, w, h, label, sub=None, edge=LINE, ts=9.2):
    rbox(cx-w/2, cy-h/2, cx+w/2, cy+h/2, edge=edge, fill=WHITE, lw=1.2, r=0.07, z=4)
    if sub:
        txt(cx, cy+h*0.17, label, ts, INK, ha="center", weight="bold")
        txt(cx, cy-h*0.24, sub, 7.7, MUTED, ha="center")
    else:
        txt(cx, cy, label, ts, INK, ha="center")

X0, X1 = 0.35, 13.15
DX0, DX1 = 11.15, 12.95

txt(0.3, 15.15, "Four planes, one topology", 24, INK, weight="bold")
txt(0.3, 14.70, "The same devices, four different meanings of “connected”. A fabric domain is one of them, and the relays are underneath two of the others.",
    12.0, MUTED)

def band(y0, y1, edge, fill, title, sub):
    rbox(X0, y0, X1, y1, edge=edge, fill=fill, lw=1.4, r=0.12, z=1)
    txt(0.62, y1 - 0.26, title, 10, edge, weight="bold")
    txt(0.62, y1 - 0.54, sub, 8.8, MUTED, style="italic")

# ══ OUT-OF-BAND MANAGEMENT ═══════════════════════════════════════════════
band(11.95, 14.30, PLUM, PLUMF, "O U T - O F - B A N D   M A N A G E M E N T",
     "console, BMC, power  ·  reaches the device when its OS, its config and its network do not")
node(1.75, 13.05, 2.2, 0.80, "console server", "serial / SSH", edge=PLUM)
node(4.55, 13.45, 2.2, 0.62, "PDU", edge=PLUM)
node(4.55, 12.60, 2.2, 0.62, "BMC / IPMI", edge=PLUM)
wire(2.85, 13.05, 3.45, 13.45, PLUM, 1.2)
wire(2.85, 13.05, 3.45, 12.60, PLUM, 1.2)
for y in (13.45, 12.60):
    wire(5.65, y, DX0, 13.05, PLUM, 1.2)
txt(8.40, 12.30, "an outlet and a console port are leasable resources too", 8.2, PLUM,
    ha="center", style="italic")

# ══ MANAGEMENT ═══════════════════════════════════════════════════════════
band(9.25, 11.60, GREEN, GREENF, "M A N A G E M E N T",
     "how every server reaches its equipment over IP  ·  needs the device alive")
node(1.75, 10.35, 2.2, 0.78, "gateway", "+ agent", edge=GREEN)
node(4.55, 10.35, 2.0, 0.78, "mgmt switch", "VLAN 99", edge=GREEN)
wire(2.85, 10.35, 3.55, 10.35, GREEN, 1.3)
for cy, label in ((10.95, "chassis · 192.168.1.50"), (10.35, "scope · .51"), (9.75, "TestCenter · .52")):
    node(7.85, cy, 3.3, 0.46, label, edge=GREEN, ts=8.4)
    wire(5.55, 10.35, 6.20, cy, GREEN, 1.0)
wire(4.55, 9.96, 4.55, 9.52, GREEN, 1.0)
wire(4.55, 9.52, 10.55, 9.52, GREEN, 1.0)
wire(10.55, 9.52, DX0, 9.90, GREEN, 1.0)
txt(10.70, 9.66, "eth0", 7.6, GREEN, ha="center")

# ══ DATA ═════════════════════════════════════════════════════════════════
band(6.55, 8.90, BLUE, BLUEF, "D A T A",
     "the network under test  ·  its own domains — VLANs, subnets, segments")
node(2.30, 7.95, 2.5, 0.70, "TestCenter", "traffic ports", edge=BLUE)
node(2.30, 7.28, 2.5, 0.52, "CyberFlood", edge=BLUE, ts=8.6)
for y, name in ((7.95, "segment A  ·  VLAN 10"), (7.30, "segment B  ·  VLAN 20")):
    wire(3.55, y, DX0, y, BLUE, 1.4)
    txt(7.40, y + 0.16, name, 8.3, BLUE, ha="center", style="italic")
rbox(3.55, 6.66, 10.95, 7.02, edge=RED, fill="#FBF0EF", lw=1.3, r=0.06, z=4)
txt(7.25, 6.84, "no control path may ride this plane — forbidden, not discouraged", 8.4, RED,
    ha="center", weight="bold")

# ══ SIGNAL ═══════════════════════════════════════════════════════════════
band(3.35, 6.20, ACC, ACCF, "S I G N A L",
     "what can become electrically common  ·  fabric domains live here, and only here")
for x0, x1, y0, y1, name, rack, pins in (
        (1.35, 5.35, 4.62, 5.42, "matrix_a/sub1", "rack 1", "pins a1–a12"),
        (5.95, 9.95, 3.62, 4.42, "matrix_c/sub1", "rack 2", "pins a13–a24")):
    rbox(x0, y0, x1, y1, edge=ACC, fill="#FBEEE4", lw=1.5, r=0.09, z=3, ls=(0, (5, 3)))
    txt((x0+x1)/2, y1 - 0.20, f"fabric domain  ·  {name}", 8.7, ACC, ha="center", weight="bold")
    txt((x0+x1)/2, y1 - 0.44, f"{rack}  ·  its own chassis, its own server", 7.8, MUTED, ha="center")
    txt((x0+x1)/2, y0 + 0.18, "PSU · AWG · scope · DMM  →  matrix", 7.9, MUTED, ha="center", style="italic")
    mid = (y0 + y1) / 2
    wire(x1, mid, DX0, mid, ACC, 1.4)
    txt((x1 + DX0) / 2, mid + 0.15, pins, 7.7, ACC, ha="center")
txt(1.45, 3.95, "Two servers, two fabric domains, one DUT with pins in both.\nThey stay separate only because nothing bridges them — a DUT\njoining rack 1 to rack 2 would make them one.",
    8.4, ACC, va="center", style="italic", ls=1.62)

# ── what each plane rests on ─────────────────────────────────────────────
for x in (3.30, 6.60, 9.40):
    ax.add_patch(FancyArrowPatch((x, 6.24), (x, 6.51), arrowstyle="-|>",
        mutation_scale=10, linewidth=1.2, color=ACC, zorder=5))
txt(0.62, 6.37, "every link above exists because a path down here is closed", 8.2, ACC, style="italic")
txt(10.05, 6.37, "open the crosspoint and the VLAN's link goes with it", 8.2, ACC, style="italic")
txt(0.62, 9.07, "management rides its own network, but still needs the device's control plane alive — which a test can take away",
    8.2, GREEN, style="italic")
txt(0.62, 11.77, "OOBM depends on none of the three below it. That is the entire point of it, and what makes an abort deliverable.",
    8.2, PLUM, style="italic")

# ══ the DUT, spanning all four ═══════════════════════════════════════════
rbox(DX0, 3.50, DX1, 14.15, edge=INK, fill=WHITE, lw=1.8, r=0.10, z=5)
txt((DX0+DX1)/2, 13.88, "DUT", 13, INK, ha="center", weight="bold", z=7)
txt((DX0+DX1)/2, 13.58, "one device", 7.9, MUTED, ha="center", style="italic", z=7)
for cy, label, col in ((13.05, "console · BMC\npower inlet", PLUM),
                       (9.90, "mgmt port\neth0", GREEN),
                       (7.35, "data ports\n1 – 48", BLUE),
                       (4.45, "analog pins\na1 – a24", ACC)):
    rbox(DX0 + 0.18, cy - 0.40, DX1 - 0.18, cy + 0.40, edge=col, fill=WHITE, lw=1.2, r=0.06, z=6)
    txt((DX0+DX1)/2, cy, label, 8.1, col, ha="center", z=7)

# ══ notes ════════════════════════════════════════════════════════════════
NX = 13.55
rbox(NX, 3.35, 18.95, 14.30, lw=1.2, r=0.10, z=2)
y = 14.02
_renderer = fig.canvas.get_renderer()
_inv = ax.transData.inverted()

def note(title, body, color=INK):
    """Place each note under the measured extent of the last one, not a guess."""
    global y
    txt(NX + 0.34, y, title, 9.9, color, weight="bold")
    handle = ax.text(NX + 0.34, y - 0.28, body, fontsize=7.8, color=MUTED,
                     va="top", zorder=6, linespacing=1.58)
    bbox = handle.get_window_extent(renderer=_renderer)
    (_, y0), (_, _) = _inv.transform(bbox)
    y = y0 - 0.42

note("Domains are a family, not one thing",
     "Each has elements, a rule for what makes two common, and pairs\n"
     "that must never be:\n"
     "  signal        lines  ·  electrically continuous\n"
     "  data          ports, VLANs, subnets  ·  reachable\n"
     "  management    interfaces  ·  reachable\n"
     "  OOBM          consoles, outlets  ·  reachable, powered")

note("A device is not in a domain",
     "Domains partition lines and segments, never boxes. This DUT is in\n"
     "two fabric domains, two data segments, one management domain and\n"
     "one OOBM domain, all at once.")

note("Generalises in shape, not in substrate",
     "“Is any forbidden pair in the same connected component, given what\n"
     "exists plus what is proposed?” has the same shape in every plane.\n"
     "But relays are not one instance among several — they are the layer\n"
     "two of the others land on:\n"
     "  underneath    a VLAN exists because a link exists because a\n"
     "                crosspoint is closed\n"
     "  decidable     fabric connectivity is a static graph; network\n"
     "                reachability is dynamic and only samplable\n"
     "  irreversible  a bridged VLAN is a bad result; a short is smoke\n"
     "So a fabric interlock can be synchronous and authoritative, and a\n"
     "data-plane one cannot.")

note("Control has two homes, and one forbidden",
     "Which plane a control path rides is decided by its role:\n"
     "  in-band mgmt   routine control — configure, measure, read\n"
     "  OOBM           recovery and abort — console, BMC, power\n"
     "  data plane     never. A test that disrupts the network under\n"
     "                 test would be cutting its own control path\n"
     "So the abort path is OOBM by construction: the contract must tear\n"
     "down even when the management plane is what the test broke. Which\n"
     "makes an outlet a dangerous resource of its own — cutting one held\n"
     "by a contract you do not own is this plane's version of the short.", PLUM)

note("What this repository implements",
     "The signal plane, and only it. The others belong to other servers\n"
     "and to the contract above them — which is why a fabric domain is\n"
     "computed and a network domain is configured.")

# ══ footer ═══════════════════════════════════════════════════════════════
rbox(0.35, 0.50, 18.95, 3.00, edge=GREEN, fill=GREENF, lw=1.4, r=0.12, z=1)
txt(0.68, 2.70, "O N E   R E S E R V A T I O N   C O V E R S   A L L   F O U R", 10.2, GREEN, weight="bold")
txt(0.68, 2.24,
    "The contract names resources in every plane — switching, traffic, the DUT's management interface, its console and its outlet — and is held whole or not at all.",
    9.1, MUTED, style="italic")
txt(0.68, 1.80,
    "The owner is a principal, which may be one engineer or a group. A group does not weaken the model: it admits several writers at once, and inside the reservation the lock is what orders",
    9.1, MUTED, style="italic")
txt(0.68, 1.46,
    "them — the same mechanism that already makes one agent's several threads safe. Admission is the reservation's job; ordering is the lock's; neither substitutes for the other.",
    9.1, MUTED, style="italic")
txt(0.68, 0.94,
    "Planes are how a lab is wired. Domains are how each plane partitions. A reservation spans planes; a lock lives inside one process; an interlock answers one plane's question about one domain.",
    9.1, INK, style="italic")

plt.savefig("three-planes.png", dpi=150, facecolor=BG, bbox_inches="tight", pad_inches=0.32)
print("ok")
