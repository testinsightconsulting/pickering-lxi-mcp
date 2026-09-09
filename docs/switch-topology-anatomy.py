import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle
from matplotlib.lines import Line2D

BG, INK, MUTED, LINE = "#FAF9F6", "#17171A", "#6E6E73", "#C6C4BD"
ACC, ACCF = "#A84A17", "#FBEEE4"
GREEN, GREENF = "#3A6647", "#E9F1EB"
RED = "#9A2F2F"
DOM = "#EFE8DE"
WHITE = "#FFFFFF"

fig, ax = plt.subplots(figsize=(19.2, 14.4))
fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
ax.set_xlim(0, 19.2); ax.set_ylim(0, 14.4); ax.axis("off")

def rbox(x0, y0, x1, y1, edge=LINE, fill=WHITE, lw=1.3, r=0.10, z=2, ls="-"):
    ax.add_patch(FancyBboxPatch((x0, y0), x1-x0, y1-y0,
        boxstyle=f"round,pad=0.02,rounding_size={r}", linewidth=lw,
        edgecolor=edge, facecolor=fill, zorder=z, linestyle=ls))

def txt(x, y, s, size=9.2, color=INK, ha="left", va="center", weight=None,
        style=None, rot=0, z=6, ls=1.55):
    ax.text(x, y, s, fontsize=size, color=color, ha=ha, va=va, fontweight=weight,
            style=style, rotation=rot, zorder=z, linespacing=ls)

def tag(x, y, n, color=ACC):
    ax.add_patch(Circle((x, y), 0.15, facecolor=color, edgecolor=WHITE, lw=1.0, zorder=8))
    ax.text(x, y, str(n), fontsize=8.0, color=WHITE, ha="center", va="center",
            fontweight="bold", zorder=9)

txt(0.3, 14.02, "Anatomy of a switch topology", 24, INK, weight="bold")
txt(0.3, 13.56, "One bench, every term. Numbers key to the panel on the right.", 12.2, MUTED)

# ── fabric domain ────────────────────────────────────────────────────────
rbox(1.85, 3.90, 13.05, 13.05, edge=ACC, fill=DOM, lw=1.5, r=0.16, z=0, ls=(0, (7, 4)))
txt(2.15, 12.80, "F A B R I C   D O M A I N   ·   matrix_a/sub1", 10.2, ACC, weight="bold")
txt(2.15, 12.52, "every line that the crosspoints, the patch lead and the declared bridge can tie together",
    9, MUTED, style="italic")
tag(12.78, 12.80, 10)

# ── chassis ──────────────────────────────────────────────────────────────
rbox(2.15, 7.15, 12.95, 12.30, edge=INK, fill="#F7F5F1", lw=1.6, r=0.12, z=1)
txt(2.52, 12.08, "C H A S S I S   ·   LXI unit at 192.168.1.50", 9.6, INK, weight="bold")
tag(2.30, 12.08, 1)

ROWS = ["psu_pos", "psu_neg", "gnd", "scope_ch1", "scope_ch2", "dmm_hi", "dmm_lo", "awg_out"]
def row_y(j): return 11.05 - 0.45 * j
def col_x(i): return 4.45 + 0.40 * i

# ── instruments ──────────────────────────────────────────────────────────
for name, a, b in (("PSU", 0, 1), ("GND", 2, 2), ("Scope", 3, 4), ("DMM", 5, 6), ("AWG", 7, 7)):
    y0, y1 = row_y(b) - 0.19, row_y(a) + 0.19
    rbox(0.38, y0, 1.38, y1, lw=1.2, r=0.07, z=3)
    txt(0.88, (y0 + y1) / 2, name, 9.4, INK, ha="center")
    for j in range(a, b + 1):
        ax.add_line(Line2D([1.38, 2.58], [row_y(j), row_y(j)], color=MUTED, lw=0.9, zorder=3))
        txt(1.98, row_y(j) + 0.13, ROWS[j], 7.5, INK, ha="center")

# ── matrix card ──────────────────────────────────────────────────────────
rbox(2.55, 7.35, 11.05, 11.80, edge=ACC, fill=WHITE, lw=1.7, r=0.10, z=3)
txt(2.90, 11.58, "card  matrix_a", 10, ACC, weight="bold")
txt(4.42, 11.58, "·  8 × 16 matrix  ·  closure limit 12  ·  settle 3 ms", 8.8, MUTED)
tag(2.72, 11.58, 2)
rbox(3.52, 7.58, 10.92, 11.32, edge=ACC, fill="#FEFAF7", lw=1.0, r=0.06, z=3, ls=(0, (4, 3)))
txt(3.98, 11.18, "subunit 1", 8.6, ACC, style="italic")
tag(3.72, 11.18, 3)

for j in range(8):
    ax.add_line(Line2D([3.62, 10.82], [row_y(j), row_y(j)], color=LINE, lw=0.8, zorder=4))
for i in range(16):
    ax.add_line(Line2D([col_x(i), col_x(i)], [7.80, 11.18], color=LINE, lw=0.8, zorder=4))
    txt(col_x(i), 7.66, str(i + 1), 7.0, MUTED, ha="center")
txt(4.42, 11.44, "columns  1–12 → DUT pins a1–a12   ·   13, 14 → patch leads to mux_b   ·   15, 16 spare",
    7.6, MUTED, style="italic")

for j in range(8):
    for i in range(16):
        ax.add_patch(Circle((col_x(i), row_y(j)), 0.042, facecolor=WHITE,
                            edgecolor=MUTED, linewidth=0.7, zorder=5))
for j, i in ((0, 0), (5, 0), (3, 12)):
    ax.add_patch(Circle((col_x(i), row_y(j)), 0.078, facecolor=ACC, edgecolor=ACC, zorder=6))

rj, ri = 2, 0
ax.add_patch(Circle((col_x(ri), row_y(rj)), 0.115, facecolor=WHITE, edgecolor=RED, lw=1.6, zorder=6))
for d in (1, -1):
    ax.add_line(Line2D([col_x(ri)-0.07, col_x(ri)+0.07],
                       [row_y(rj)-0.07*d, row_y(rj)+0.07*d], color=RED, lw=1.5, zorder=7))

tag(col_x(0) - 0.34, row_y(0) - 0.22, 6)
tag(col_x(0) - 0.34, row_y(2) - 0.24, 12, RED)
tag(col_x(7), row_y(6) - 0.30, 5)
tag(2.50, row_y(3) + 0.13, 7)
tag(col_x(15) + 0.32, row_y(4), 4)
tag(col_x(12) + 0.30, row_y(3) + 0.26, 11)

# ── mux card ─────────────────────────────────────────────────────────────
rbox(11.22, 8.60, 12.88, 11.32, edge=ACC, fill=WHITE, lw=1.5, r=0.08, z=3)
txt(12.05, 11.10, "card  mux_b", 9.2, ACC, weight="bold", ha="center")
txt(12.05, 10.82, "subunit 1 · MUX 1×16\none channel at a time", 7.7, MUTED, ha="center")
ax.add_line(Line2D([11.36, 12.76], [10.35, 10.35], color=MUTED, lw=1.3, zorder=4))
txt(11.36, 10.50, "common", 7.5, MUTED)
for k in range(6):
    x = 11.46 + 0.26 * k
    ax.add_line(Line2D([x, x], [10.35, 9.35], color=LINE, lw=0.8, zorder=4))
    ax.add_patch(Circle((x, 10.35), 0.042, facecolor=WHITE, edgecolor=MUTED, lw=0.7, zorder=5))
    if k < 4:
        txt(x, 9.26, f"tc_{k+1}", 7.0, INK, ha="right", rot=90, va="top")

ax.add_patch(FancyArrowPatch((col_x(12), 7.35), (11.30, 10.35), arrowstyle="-",
    linewidth=2.4, color=ACC, alpha=0.85, connectionstyle="arc3,rad=-0.30", zorder=4))
txt(11.95, 8.18, "patch lead", 8.6, ACC, ha="center", style="italic", weight="bold")
tag(11.32, 8.02, 8)

# ── DUT ──────────────────────────────────────────────────────────────────
for i in range(6):
    ax.add_line(Line2D([col_x(i), col_x(i)], [7.35, 6.15], color=MUTED, lw=0.9, zorder=3))
rbox(3.95, 4.55, 8.25, 6.15, edge=INK, fill=WHITE, lw=1.5, r=0.08, z=4)
txt(8.05, 5.86, "DUT", 12.5, INK, weight="bold", ha="right")
txt(8.05, 5.46, "not an instrument, not a card,\nnot addressable by any driver", 8.3, MUTED,
    ha="right", style="italic")
for i in range(6):
    txt(col_x(i), 6.02, f"a{i+1}", 7.2, MUTED, ha="center")
ax.add_patch(FancyArrowPatch((col_x(0), 5.80), (col_x(3), 5.80), arrowstyle="-",
    linewidth=1.7, color=RED, linestyle=(0, (3, 2.5)),
    connectionstyle="arc3,rad=0.60", zorder=5))
txt(5.05, 4.90, "internal bridge", 8.4, RED, ha="center", style="italic")

ax.add_patch(FancyArrowPatch((col_x(0), 6.55), (col_x(3), 6.55), arrowstyle="-",
    linewidth=2.3, color=ACC, linestyle=(0, (4, 3)),
    connectionstyle="arc3,rad=-0.62", zorder=5))
txt(4.20, 6.80, "declared\nbridge", 8.4, ACC, ha="right", style="italic", weight="bold")
tag(4.02, 6.42, 9)

txt(8.62, 6.58, "The DUT joins a1 to a4 inside itself.", 9.4, INK, va="top", weight="bold")
txt(8.62, 6.24,
    "No driver can see that — connectivity through a\n"
    "bridge is a property of the bridge. But it is\n"
    "declarable, in exactly the shape of a patch lead:\n"
    "a link between the two lines those pins sit on.\n"
    "The file never describes the DUT's internals, only\n"
    "that these two ends come out common.\n\n"
    "Declared, it merges the halves into one domain and\n"
    "the interlock holds. Undeclared, gnd → a1 would\n"
    "have been allowed.",
    8.5, MUTED, va="top", ls=1.6)

# ── legend ───────────────────────────────────────────────────────────────
LX = 13.35
rbox(LX, 3.28, 18.95, 13.05, lw=1.2, r=0.10, z=2)
txt(LX + 0.32, 12.75, "What each part is called", 12.8, INK, weight="bold")

items = [
    (1, "Chassis", "The enclosure. Reached over IP as an LXI unit, or\nthrough the backplane as local PXI."),
    (2, "Card", "One switching module, addressed by (bus, device),\ngiven an alias so nothing downstream knows the slot."),
    (3, "Subunit", "An independently addressed block on a card. The floor\nof a fabric domain — never split across one."),
    (4, "Line", "A row or a column. Say row, column or endpoint —\nnever \"port\", which means both of them here."),
    (5, "Crosspoint", "The relay at one (row, column). Closing it makes that\nrow and that column common. The atom of everything."),
    (6, "Closed crosspoint", "Three here: psu_pos→a1, dmm_hi→a1 (measuring a\npowered pin is fine), scope_ch1→the patch lead."),
    (7, "Endpoint", "A name bound to exactly one line. What every tool\ntakes and returns; crosspoints are an internal detail."),
    (8, "Link — patch lead", "A hard-wired connection between two lines. Traversed\nwhen routing, never switched, always counted in safety."),
    (9, "Link — declared bridge", "The same mechanism for what is not a cable: the DUT\njoining two pins. Declaring it makes it enforceable."),
    (10, "Fabric domain", "Everything the above ties together. 28 endpoints, one\ndomain — computed from the file, never declared."),
    (11, "Route", "A path applied and held open, owned and reference-\ncounted. Never crosses a domain boundary."),
    (12, "Refusal", "gnd→a1 would make psu_pos and gnd common through the\nDUT bridge — checked before any relay moves."),
]
y = 12.42
for n, name, body in items:
    tag(LX + 0.44, y, n, RED if n == 12 else ACC)
    txt(LX + 0.76, y, name, 9.5, INK, weight="bold")
    txt(LX + 0.76, y - 0.23, body, 7.8, MUTED, va="top", ls=1.5)
    y -= 0.74

# ── bottom strip ─────────────────────────────────────────────────────────
rbox(0.3, 0.45, 18.95, 3.20, edge=GREEN, fill=GREENF, lw=1.4, r=0.12, z=1)
txt(0.65, 2.92, "T E S T   T O P O L O G Y   —   the contract, held whole under one reservation",
    10.8, GREEN, weight="bold")
txt(0.65, 2.60, "Everything above is ONE resource in it. The contract names several, and the connections between them. A resource lost mid-run voids the reservation rather than degrading it.",
    9.1, MUTED, style="italic")
for cx, w, name, sub, hot in (
    (3.55, 3.9, "pickering-lxi-mcp", "everything above\n= one switch topology", True),
    (8.30, 2.7, "scope-mcp", "Keysight", False),
    (12.55, 2.7, "testcenter-mcp", "Spirent", False),
    (16.65, 3.3, "DUT", "no server, no driver —\nonly what the contract asserts", False)):
    rbox(cx - w/2, 0.80, cx + w/2, 2.05, edge=ACC if hot else LINE,
         fill=ACCF if hot else WHITE, lw=1.6 if hot else 1.2, r=0.08, z=3)
    txt(cx, 1.70, name, 10, ACC if hot else INK, weight="bold", ha="center")
    txt(cx, 1.24, sub, 8.4, MUTED, ha="center")
for a, wa, b, wb in ((3.55, 3.9, 8.30, 2.7), (8.30, 2.7, 12.55, 2.7), (12.55, 2.7, 16.65, 3.3)):
    ax.add_line(Line2D([a + wa/2, b - wb/2], [1.42, 1.42], color=GREEN, lw=1.0,
                       linestyle=(0, (3, 3)), zorder=2))

plt.savefig(
    "switch-topology-anatomy.png",
            dpi=150, facecolor=BG, bbox_inches="tight", pad_inches=0.32)
print("ok")
