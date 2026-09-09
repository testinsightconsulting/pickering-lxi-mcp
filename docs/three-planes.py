import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle
from matplotlib.lines import Line2D

BG, INK, MUTED, LINE = "#FAF9F6", "#17171A", "#6E6E73", "#C6C4BD"
ACC, ACCF = "#A84A17", "#F8EDE4"      # fabric / signal
BLUE, BLUEF = "#2B5C86", "#E8F0F6"    # data plane
GREEN, GREENF = "#3A6647", "#E8F0EA"  # management plane
RED = "#9A2F2F"
WHITE = "#FFFFFF"

fig, ax = plt.subplots(figsize=(19.2, 13.6))
fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
ax.set_xlim(0, 19.2); ax.set_ylim(0, 13.6); ax.axis("off")

def rbox(x0, y0, x1, y1, edge=LINE, fill=WHITE, lw=1.3, r=0.10, z=2, ls="-"):
    ax.add_patch(FancyBboxPatch((x0, y0), x1-x0, y1-y0,
        boxstyle=f"round,pad=0.02,rounding_size={r}", linewidth=lw,
        edgecolor=edge, facecolor=fill, zorder=z, linestyle=ls))

def txt(x, y, s, size=9.2, color=INK, ha="left", va="center", weight=None,
        style=None, rot=0, z=6, ls=1.55):
    ax.text(x, y, s, fontsize=size, color=color, ha=ha, va=va, fontweight=weight,
            style=style, rotation=rot, zorder=z, linespacing=ls)

def wire(x1, y1, x2, y2, color=MUTED, lw=1.0, ls="-", z=3):
    ax.add_line(Line2D([x1, x2], [y1, y2], color=color, lw=lw, linestyle=ls, zorder=z))

def node(cx, cy, w, h, label, sub=None, edge=LINE, fill=WHITE, tcol=INK, ts=9.4, lw=1.2):
    rbox(cx-w/2, cy-h/2, cx+w/2, cy+h/2, edge=edge, fill=fill, lw=lw, r=0.07, z=4)
    if sub:
        txt(cx, cy+h*0.17, label, ts, tcol, ha="center", weight="bold")
        txt(cx, cy-h*0.23, sub, 7.8, MUTED, ha="center")
    else:
        txt(cx, cy, label, ts, tcol, ha="center")

txt(0.3, 13.15, "Three planes, one topology", 24, INK, weight="bold")
txt(0.3, 12.70, "The same devices, three different meanings of “connected”. A fabric domain is one of them, not the whole picture.",
    12.2, MUTED)

BAND_X0, BAND_X1 = 0.35, 13.15
DUT_X0, DUT_X1 = 11.15, 12.95

# ══ MANAGEMENT PLANE ═════════════════════════════════════════════════════
rbox(BAND_X0, 9.15, BAND_X1, 12.10, edge=GREEN, fill=GREENF, lw=1.4, r=0.12, z=1)
txt(0.62, 11.86, "M A N A G E M E N T   P L A N E", 10, GREEN, weight="bold")
txt(0.62, 11.58, "how every server reaches its equipment  ·  out-of-band, its own network domain",
    8.9, MUTED, style="italic")

node(1.65, 10.45, 2.0, 0.85, "gateway", "+ agent", edge=GREEN, fill=WHITE)
node(4.30, 10.45, 1.9, 0.85, "mgmt switch", "VLAN 99", edge=GREEN, fill=WHITE)
wire(2.65, 10.45, 3.35, 10.45, GREEN, 1.3)
for cy, label in ((11.15, "chassis  ·  192.168.1.50"), (10.45, "scope  ·  .51"), (9.75, "TestCenter  ·  .52")):
    node(7.65, cy, 3.4, 0.52, label, edge=GREEN, fill=WHITE, ts=8.6)
    wire(5.25, 10.45, 5.95, cy, GREEN, 1.0)
for a, b in (((4.30, 10.03), (4.30, 9.42)), ((4.30, 9.42), (10.50, 9.42)),
             ((10.50, 9.42), (11.15, 9.88))):
    wire(a[0], a[1], b[0], b[1], GREEN, 1.0)
txt(10.72, 9.60, "eth0", 7.6, GREEN, ha="center")

# ══ DATA PLANE ═══════════════════════════════════════════════════════════
rbox(BAND_X0, 5.80, BAND_X1, 8.75, edge=BLUE, fill=BLUEF, lw=1.4, r=0.12, z=1)
txt(0.62, 8.51, "D A T A   P L A N E", 10, BLUE, weight="bold")
txt(0.62, 8.23, "the network under test  ·  its own domains — VLANs, subnets, segments", 8.9, MUTED, style="italic")

node(2.30, 7.30, 2.6, 0.85, "TestCenter", "traffic ports", edge=BLUE, fill=WHITE)
node(2.30, 6.35, 2.6, 0.62, "CyberFlood", edge=BLUE, fill=WHITE, ts=8.8)
for y, name, col in ((7.30, "segment A  ·  VLAN 10", BLUE), (6.35, "segment B  ·  VLAN 20", BLUE)):
    wire(3.60, y, 11.15, y, col, 1.4)
    txt(7.20, y + 0.20, name, 8.4, col, ha="center", style="italic")

# ══ SIGNAL / FABRIC PLANE ════════════════════════════════════════════════
rbox(BAND_X0, 2.45, BAND_X1, 5.40, edge=ACC, fill="#F5EFE8", lw=1.4, r=0.12, z=1)
txt(0.62, 5.16, "S I G N A L   P L A N E", 10, ACC, weight="bold")
txt(0.62, 4.88, "what can become electrically common  ·  fabric domains live here, and only here",
    8.9, MUTED, style="italic")

for x0, x1, y0, y1, name, rack, pins in (
        (1.35, 5.35, 3.88, 4.76, "matrix_a/sub1", "rack 1", "pins a1–a12"),
        (5.95, 9.95, 2.72, 3.60, "matrix_c/sub1", "rack 2", "pins a13–a24")):
    rbox(x0, y0, x1, y1, edge=ACC, fill=ACCF, lw=1.5, r=0.09, z=3, ls=(0, (5, 3)))
    txt((x0+x1)/2, y1 - 0.21, f"fabric domain  ·  {name}", 8.8, ACC, ha="center", weight="bold")
    txt((x0+x1)/2, y1 - 0.47, f"{rack}  ·  its own chassis, its own server", 7.9, MUTED, ha="center")
    txt((x0+x1)/2, y0 + 0.19, "PSU · AWG · scope · DMM  →  matrix", 8.0, MUTED, ha="center", style="italic")
    mid = (y0 + y1) / 2
    wire(x1, mid, 11.15, mid, ACC, 1.4)
    txt((x1 + 11.15) / 2, mid + 0.16, pins, 7.8, ACC, ha="center")

txt(1.45, 3.15, "Two servers, two fabric domains,\none DUT with pins in both.\nThey stay separate only because\nnothing bridges them — a DUT\njoining rack 1 to rack 2 merges them.",
    8.5, ACC, va="center", style="italic", ls=1.65)

# ══ the DUT, spanning all three ══════════════════════════════════════════
rbox(DUT_X0, 2.60, DUT_X1, 11.95, edge=INK, fill=WHITE, lw=1.8, r=0.10, z=5)
txt((DUT_X0+DUT_X1)/2, 11.68, "DUT", 13, INK, ha="center", weight="bold", z=7)
txt((DUT_X0+DUT_X1)/2, 11.35, "one device", 8.0, MUTED, ha="center", style="italic", z=7)
for cy, label, col in ((10.10, "mgmt port\neth0", GREEN),
                       (6.85, "data ports\n1 – 48", BLUE),
                       (3.70, "analog pins\na1 – a24", ACC)):
    rbox(DUT_X0 + 0.18, cy - 0.42, DUT_X1 - 0.18, cy + 0.42, edge=col, fill=WHITE, lw=1.2, r=0.06, z=6)
    txt((DUT_X0+DUT_X1)/2, cy, label, 8.2, col, ha="center", z=7)

# ══ notes ════════════════════════════════════════════════════════════════
NX = 13.55
rbox(NX, 2.45, 18.95, 12.10, lw=1.2, r=0.10, z=2)
y = 11.78
def note(title, body, color=INK):
    global y
    txt(NX + 0.34, y, title, 9.9, color, weight="bold")
    txt(NX + 0.34, y - 0.32, body, 8.6, MUTED, va="top", ls=1.6)
    y -= 0.42 + 0.185 * (body.count("\n") + 1) + 0.30

note("Domains are a family, not one thing",
     "Each kind has elements, a rule for what makes two of\n"
     "them common, and pairs that must never be:\n\n"
     "  fabric        lines  ·  electrically continuous\n"
     "  data          ports, VLANs, subnets  ·  reachable\n"
     "  management    interfaces  ·  reachable")

note("A device is not in a domain",
     "Domains partition lines and segments, never boxes. This\n"
     "DUT sits in two fabric domains, two data segments and\n"
     "one management domain, all at once. So do instruments:\n"
     "a scope with channels in two racks touches two.")

note("The interlock argument generalises",
     "“Is any forbidden pair in the same connected component,\n"
     "given what is closed plus what is proposed?” holds in\n"
     "every plane. Same shape, different substrate: shorts in\n"
     "the fabric, bridged VLANs in the data plane, management\n"
     "reachable from the network under test.")

note("In-band management: the cross-plane hazard",
     "If the control path rides the data plane, a test that\n"
     "disrupts the network under test cuts the path you are\n"
     "testing it with — and the abort cannot be delivered.\n"
     "Out-of-band keeps the control path outside the\n"
     "experiment. That is a topology decision, not a\n"
     "networking preference.", RED)

note("What this repository implements",
     "The signal plane, and only it. pickering-lxi-mcp computes\n"
     "its fabric domains from its own file. The data and\n"
     "management planes belong to other servers and to the\n"
     "contract above them — which is why a fabric domain is\n"
     "computed and a network domain is configured.")

# ══ footer ═══════════════════════════════════════════════════════════════
rbox(0.35, 0.40, 18.95, 2.15, edge=GREEN, fill=GREENF, lw=1.4, r=0.12, z=1)
txt(0.68, 1.86, "O N E   R E S E R V A T I O N   C O V E R S   A L L   T H R E E", 10.2, GREEN, weight="bold")
txt(0.68, 1.44,
    "The contract names resources in every plane — switching, traffic, the DUT's management interface — and is held whole or not at all.",
    9.2, MUTED, style="italic")
txt(0.68, 1.06,
    "The owner is a principal, which may be one engineer or a group. A group does not weaken the model: it admits several writers at once, and inside the reservation the lock is what orders them —",
    9.2, MUTED, style="italic")
txt(0.68, 0.74,
    "the same mechanism that already makes one agent's several threads safe. Admission is the reservation's job; ordering is the lock's; neither substitutes for the other.",
    9.2, MUTED, style="italic")

plt.savefig("three-planes.png", dpi=150, facecolor=BG, bbox_inches="tight", pad_inches=0.32)
print("ok")
