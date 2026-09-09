import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.lines import Line2D

BG, INK, MUTED, LINE = "#FAF9F6", "#17171A", "#6E6E73", "#C9C7C0"
ACCENT, ACCENTF = "#A84A17", "#FBEEE4"
BLUE,  BLUEF    = "#2B5C86", "#EAF1F7"
GREEN, GREENF   = "#3A6647", "#E9F1EB"
WHITE, PANEL    = "#FFFFFF", "#F1F0EB"

fig, ax = plt.subplots(figsize=(17.6, 13.4))
fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
ax.set_xlim(0, 17.6); ax.set_ylim(-2.5, 13.2); ax.axis("off")
P = 0.05

def panel(cx, cy, w, h, edge=LINE, fill=WHITE, lw=1.3):
    ax.add_patch(FancyBboxPatch((cx-w/2, cy-h/2), w, h,
        boxstyle=f"round,pad={P},rounding_size=0.10",
        linewidth=lw, edgecolor=edge, facecolor=fill, zorder=3))

def box(cx, cy, w, h, title, sub=None, edge=LINE, fill=WHITE, tcol=INK,
        ts=12.5, ss=9.3, bold=True, lw=1.3):
    panel(cx, cy, w, h, edge, fill, lw)
    if sub:
        ax.text(cx, cy+h*0.18, title, ha="center", va="center", fontsize=ts,
                color=tcol, fontweight="bold" if bold else "normal", zorder=4)
        ax.text(cx, cy-h*0.24, sub, ha="center", va="center", fontsize=ss,
                color=MUTED, zorder=4, linespacing=1.5)
    else:
        ax.text(cx, cy, title, ha="center", va="center", fontsize=ts,
                color=tcol, fontweight="bold" if bold else "normal", zorder=4)

def listbox(cx, cy, w, h, title, lines, edge=LINE, fill=WHITE, tcol=INK, ts=12.5, ss=9.2):
    panel(cx, cy, w, h, edge, fill)
    top = cy + h/2
    ax.text(cx, top-0.30, title, ha="center", va="center", fontsize=ts,
            color=tcol, fontweight="bold", zorder=4)
    ax.text(cx-w/2+0.28, top-0.62, "\n".join(lines), ha="left", va="top",
            fontsize=ss, color=MUTED, zorder=4, linespacing=1.72)

def arr(x1, y1, x2, y2, color=LINE, lw=1.15, ls="-", head=True, z=2):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2),
        arrowstyle="-|>" if head else "-", mutation_scale=12,
        linewidth=lw, color=color, linestyle=ls, shrinkA=1, shrinkB=1, zorder=z))

# ── heading ──────────────────────────────────────────────────────────────
ax.text(0.15, 12.80, "Multi-vendor lab, one agent", fontsize=24, fontweight="bold", color=INK)
ax.text(0.15, 12.33, "Where state lives — and what stands between two callers reaching for the same relay",
        fontsize=12.4, color=MUTED)

# ── control plane ────────────────────────────────────────────────────────
ax.add_patch(FancyBboxPatch((0.15, 4.45), 17.3, 7.60,
    boxstyle="round,pad=0.02,rounding_size=0.08", linewidth=0, facecolor=PANEL, zorder=0))
ax.text(0.45, 11.72, "C O N T R O L   P L A N E", fontsize=10, fontweight="bold", color=MUTED)
ax.text(0.45, 11.40, "a star — the agent talks to each server", fontsize=9.5, color=MUTED, style="italic")

for cx, name in ((2.6, "Engineer A"), (6.2, "Engineer B"), (9.8, "CI pipeline")):
    box(cx, 10.80, 2.30, 0.58, name, ts=11, fill=BG, bold=False)
    arr(cx, 10.80-0.34, cx, 9.40+0.55)

box(6.20, 9.40, 10.0, 1.00, "Agent  /  orchestrator",
    "one conversation, many vendors        plan → acquire → arm → act → release",
    edge=BLUE, fill=BLUEF, ts=14.5, ss=9.8)

box(6.20, 7.50, 7.6, 1.25, "MCP gateway   ·   one endpoint",
    "namespaces the fleet:  switching.route_signal,  scope.measure\none place for authentication, one audit log, tool-count control",
    edge=BLUE, ts=12.5)
arr(6.20, 9.40-0.55, 6.20, 7.50+0.68, color=BLUE, lw=1.4)
ax.text(6.42, 8.53, "tool calls", fontsize=9.2, color=BLUE, ha="left", style="italic")

listbox(14.60, 7.80, 4.70, 3.00, "Lease broker", [
    "the piece a single-instrument",
    "server does not need",
    "",
    "·  all-or-nothing lease over a",
    "    resource SET, not one device",
    "·  time-boxed and renewable",
    "·  one global acquire order, so two",
    "    agents cannot deadlock half-held",
], edge=GREEN, fill=GREENF, ts=13, ss=8.9)
arr(11.20, 9.15, 12.28, 8.85, color=GREEN, lw=1.4)
ax.text(11.80, 9.52, "acquire / renew / release", fontsize=9.2, color=GREEN,
        ha="center", style="italic")

listbox(14.60, 11.00, 4.70, 1.95, "What the agent actually does", [
    "1   plan_route            dry run, no lease",
    "2   acquire  [matrix, scope, psu]",
    "3   arm_interlock",
    "4   route_signal  ·  measure",
    "5   release        tears the fixture down",
], edge=LINE, fill=BG, ts=11, ss=8.8)

servers = [("pickering-lxi-mcp", "switching  ·  Pickering", True),
           ("scope-mcp", "Keysight", False),
           ("testcenter-mcp", "Spirent", False),
           ("snexiq-mcp", "Calnex", False),
           ("cyberfloodiq-mcp", "Spirent", False)]
xs = [1.60, 3.90, 6.20, 8.50, 10.80]
for cx, (name, vendor, hot) in zip(xs, servers):
    box(cx, 5.60, 2.10, 1.00, name, vendor,
        edge=ACCENT if hot else LINE, fill=ACCENTF if hot else WHITE,
        tcol=ACCENT if hot else INK, ts=9.8, ss=8.4, lw=1.8 if hot else 1.2)
    arr(6.20, 7.50-0.68, cx, 5.60+0.55)

arr(12.60, 6.28, 11.95, 5.90, color=GREEN, ls=(0, (3, 3)), lw=1.1)
ax.text(12.72, 5.72, "every mutate revalidates the lease", fontsize=8.8, color=GREEN,
        ha="left", va="center", style="italic")

ax.text(6.35, 4.70,
        "one process per switch topology        the device's truth lives here, not in the MCP session        observe ungated  /  mutate leased",
        fontsize=10, color=MUTED, ha="center", style="italic")

# ── divider ──────────────────────────────────────────────────────────────
ax.add_line(Line2D([0.15, 17.45], [4.22, 4.22], color=LINE, lw=1.1, ls=(0, (6, 4))))

# ── signal plane ─────────────────────────────────────────────────────────
ax.text(1.15, 3.88, "S I G N A L   P L A N E", fontsize=10, fontweight="bold", color=ACCENT)
ax.text(1.15, 3.56, "a fabric — every instrument reaches the DUT through the matrix",
        fontsize=9.5, color=MUTED, style="italic")

ipos = [2.55, 4.45, 6.35, 8.25, 10.15]
for cx, name in zip(ipos, ("PSU", "AWG", "Scope", "DMM", "TestCenter")):
    box(cx, 2.70, 1.72, 0.56, name, ts=10.5, bold=False)
    arr(cx, 2.70-0.33, cx, 1.70+0.41, color=ACCENT, lw=1.0, head=False)

box(6.20, 1.70, 10.6, 0.72, "Pickering matrix  +  multiplexers",
    edge=ACCENT, fill=ACCENTF, tcol=ACCENT, ts=13)
arr(6.20, 1.70-0.41, 6.20, 0.62+0.34, color=ACCENT, lw=1.0, head=False)
box(6.20, 0.62, 3.0, 0.56, "DUT", ts=12)

# pickering server drives the matrix — routed clear of everything
dot = dict(color=ACCENT, lw=1.15, ls=(0, (1.6, 3)), zorder=1)
ax.add_line(Line2D([1.05, 0.52], [5.60, 5.60], **dot))
ax.add_line(Line2D([0.52, 0.52], [5.60, 1.70], **dot))
arr(0.52, 1.70, 0.86, 1.70, color=ACCENT, lw=1.15, ls=(0, (1.6, 3)), z=1)
ax.text(0.34, 3.40, "drives", fontsize=9, color=ACCENT, rotation=90,
        ha="center", va="center", style="italic")

ax.text(12.05, 1.95,
        "The matrix is in the signal path of every\nother instrument. That is the whole argument:\nit is the one server a multi-vendor agent\ncannot do without — and the one where a\nmistake is a short, not a wrong reading.",
        fontsize=9.6, color=ACCENT, ha="left", va="center", linespacing=1.6)
ax.text(12.05, 0.66, "(each of the other servers drives its own instrument the same way)",
        fontsize=8.6, color=MUTED, ha="left", va="center", style="italic")

# ── rules ────────────────────────────────────────────────────────────────
ax.add_line(Line2D([0.15, 17.45], [-0.28, -0.28], color=LINE, lw=1.1))
rules = [
    ("Never per-session",
     "Relay positions, output on/off, who holds the\nbench. One physical thing, one truth. The MCP\nsession id may be per-connection; the state\nbehind it may not be."),
    ("Concurrency",
     "One process per switch topology, which must\ncontain whole fabric domains. Two agents are one\ntruth plus a lease — never two device objects,\nand never a replica."),
    ("Multi-user",
     "Everyone may observe, one may mutate — that\nis what makes sharing tolerable. A lease is\ntime-boxed and expiry tears down to a safe\nstate, so a crashed agent cannot hold a fixture."),
]
for i, (h, body) in enumerate(rules):
    x = 0.45 + i * 5.85
    ax.text(x, -0.70, h, fontsize=11.5, fontweight="bold", color=INK)
    ax.text(x, -1.05, body, fontsize=9.4, color=MUTED, va="top", linespacing=1.65)

plt.savefig(
    "multi-vendor-architecture.png",
            dpi=160, facecolor=BG, bbox_inches="tight", pad_inches=0.36)
print("ok")
