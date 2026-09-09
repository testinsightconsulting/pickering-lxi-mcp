import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.lines import Line2D

BG, INK, MUTED, LINE = "#FAF9F6", "#17171A", "#6E6E73", "#C9C7C0"
ACCENT, ACCENTF = "#A84A17", "#FBEEE4"
BLUE,  BLUEF    = "#2B5C86", "#EAF1F7"
GREEN, GREENF   = "#3A6647", "#E9F1EB"
RED             = "#9A2F2F"
WHITE, PANEL    = "#FFFFFF", "#F1F0EB"

fig, ax = plt.subplots(figsize=(18.0, 13.5))
fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
ax.set_xlim(0, 18.0); ax.set_ylim(-0.4, 13.3); ax.axis("off")
P = 0.05

def panel(cx, cy, w, h, edge=LINE, fill=WHITE, lw=1.3, z=3):
    ax.add_patch(FancyBboxPatch((cx-w/2, cy-h/2), w, h,
        boxstyle=f"round,pad={P},rounding_size=0.10",
        linewidth=lw, edgecolor=edge, facecolor=fill, zorder=z))

def zone(x0, y0, x1, y1, fill=PANEL, edge="none", ls="-", lw=0):
    ax.add_patch(FancyBboxPatch((x0, y0), x1-x0, y1-y0,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=lw, edgecolor=edge, facecolor=fill, linestyle=ls, zorder=0))

def box(cx, cy, w, h, title, sub=None, edge=LINE, fill=WHITE, tcol=INK,
        ts=12, ss=8.8, bold=True, lw=1.3):
    panel(cx, cy, w, h, edge, fill, lw)
    if sub:
        ax.text(cx, cy+h*0.19, title, ha="center", va="center", fontsize=ts,
                color=tcol, fontweight="bold" if bold else "normal", zorder=4)
        ax.text(cx, cy-h*0.25, sub, ha="center", va="center", fontsize=ss,
                color=MUTED, zorder=4, linespacing=1.5)
    else:
        ax.text(cx, cy, title, ha="center", va="center", fontsize=ts,
                color=tcol, fontweight="bold" if bold else "normal", zorder=4)

def listbox(cx, cy, w, h, title, lines, edge=LINE, fill=WHITE, tcol=INK, ts=12, ss=9.0):
    panel(cx, cy, w, h, edge, fill)
    top = cy + h/2
    ax.text(cx, top-0.28, title, ha="center", va="center", fontsize=ts,
            color=tcol, fontweight="bold", zorder=4)
    ax.text(cx-w/2+0.26, top-0.58, "\n".join(lines), ha="left", va="top",
            fontsize=ss, color=MUTED, zorder=4, linespacing=1.72)

def arr(x1, y1, x2, y2, color=LINE, lw=1.15, ls="-", head=True, z=2, rad=None):
    kw = dict(arrowstyle="-|>" if head else "-", mutation_scale=12,
              linewidth=lw, color=color, linestyle=ls, shrinkA=1, shrinkB=1, zorder=z)
    if rad is not None:
        kw["connectionstyle"] = f"arc3,rad={rad}"
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), **kw))

def ztitle(x, y, t, s, color=MUTED, ha="left"):
    ax.text(x, y, t, fontsize=10, fontweight="bold", color=color, ha=ha)
    ax.text(x, y-0.27, s, fontsize=9.2, color=MUTED, ha=ha, style="italic")

# ── heading ──────────────────────────────────────────────────────────────
ax.text(0.15, 12.98, "Where each piece runs, and what it speaks", fontsize=23.5,
        fontweight="bold", color=INK)
ax.text(0.15, 12.53, "The same fleet as the previous figure, drawn by host and transport instead of by layer",
        fontsize=12.2, color=MUTED)

# ══ ZONE A — anywhere ════════════════════════════════════════════════════
zone(0.30, 10.16, 11.70, 12.34)
ztitle(0.58, 12.08, "A N Y W H E R E   ·   many instances", "laptops, CI runners, cloud — the only tier you scale out")

for cx, name in ((2.15, "Engineer A"), (4.85, "Engineer B"), (7.55, "CI pipeline")):
    box(cx, 11.45, 2.25, 0.48, name, ts=10.5, fill=BG, bold=False)
    arr(cx, 11.19, cx, 11.03)
box(4.85, 10.62, 7.60, 0.68, "Agent  /  orchestrator", edge=BLUE, fill=BLUEF, ts=13.5)

# ── trust boundary ───────────────────────────────────────────────────────
ax.add_line(Line2D([0.30, 17.85], [10.02, 10.02], color=RED, lw=1.3, ls=(0, (7, 4))))
ax.text(0.58, 9.80, "network boundary — authenticate, authorise and audit here.  Nothing below this line is reachable from a laptop except the gateway.",
        fontsize=9.4, color=RED, style="italic")

# ══ ZONE C — lab host ════════════════════════════════════════════════════
zone(0.30, 5.75, 11.70, 9.55, fill="#EFEEE9")
ztitle(0.58, 9.28, "L A B   H O S T   /   P X I   C O N T R O L L E R",
       "one machine beside the rack — the trust boundary you can actually enforce")

box(5.95, 8.22, 9.40, 0.92, "MCP gateway",
    "binds 0.0.0.0:8443 · namespaces the fleet · the only port open to the network",
    edge=BLUE, ts=13, ss=9.0)
arr(4.85, 10.26, 5.95, 8.70, color=BLUE, lw=1.5)
ax.text(6.20, 9.45, "streamable HTTP over TLS\none hop carries a whole plan", fontsize=9.2,
        color=BLUE, ha="left", va="center", style="italic", linespacing=1.45)

srv = [("pickering-lxi-mcp", ":8101", True), ("scope-mcp", ":8102", False),
       ("testcenter-mcp", ":8103", False), ("snexiq-mcp", ":8104", False),
       ("cyberfloodiq-mcp", ":8105", False)]
xs = [1.50, 3.72, 5.94, 8.16, 10.38]
for cx, (name, port, hot) in zip(xs, srv):
    box(cx, 6.78, 2.00, 0.86, name, f"127.0.0.1{port}",
        edge=ACCENT if hot else LINE, fill=ACCENTF if hot else WHITE,
        tcol=ACCENT if hot else INK, ts=9.4, ss=8.2, lw=1.8 if hot else 1.2)
    arr(5.95, 7.76, cx, 7.21)

ax.text(5.95, 6.10,
        "long-lived daemons bound to loopback — systemd units or containers, reached from the gateway over 127.0.0.1.",
        fontsize=9.4, color=MUTED, ha="center", style="italic")
ax.text(5.95, 5.86, "Never spawned per client. That is the whole point.",
        fontsize=9.4, color=RED, ha="center", style="italic", fontweight="bold")

# ══ ZONE R — the rack ════════════════════════════════════════════════════
zone(0.30, 1.15, 11.70, 5.28, fill="#F4F1ED")
ztitle(11.42, 5.01, "T H E   R A C K",
       "ClientBridge over IP for an LXI unit — or the PXI backplane, if the cards are in this controller",
       color=ACCENT, ha="right")

for cx, name in zip([2.40, 4.30, 6.20, 8.10, 10.00],
                    ("PSU", "AWG", "Scope", "DMM", "TestCenter")):
    box(cx, 4.10, 1.70, 0.50, name, ts=10, bold=False)
    arr(cx, 3.85, cx, 3.26, color=ACCENT, lw=1.0, head=False)
box(5.95, 2.95, 9.40, 0.62, "Pickering matrix  +  multiplexers",
    edge=ACCENT, fill=ACCENTF, tcol=ACCENT, ts=12)
arr(5.95, 2.64, 5.95, 1.86, color=ACCENT, lw=1.0, head=False)
box(5.95, 1.60, 2.60, 0.50, "DUT", ts=11)

dot = dict(color=ACCENT, lw=1.15, ls=(0, (1.6, 3)), zorder=1)
ax.add_line(Line2D([1.50, 0.90], [6.35, 6.35], **dot))
ax.add_line(Line2D([0.90, 0.90], [6.35, 2.95], **dot))
arr(0.90, 2.95, 1.28, 2.95, color=ACCENT, lw=1.15, ls=(0, (1.6, 3)), z=1)
ax.text(0.72, 4.55, "drives", fontsize=8.8, color=ACCENT, rotation=90,
        ha="center", va="center", style="italic")
ax.text(11.42, 1.42, "(each other server reaches its own instrument the same way)",
        fontsize=8.6, color=MUTED, ha="right", style="italic")

# ══ RIGHT COLUMN ═════════════════════════════════════════════════════════
listbox(14.98, 11.15, 5.60, 2.30, "Lease broker  —  its own host", [
    "fleet-wide, NOT per rack: it leases across",
    "resources that live on different machines.",
    "",
    "·  all-or-nothing lease over a resource SET",
    "·  one global acquire order — no deadlock",
    "·  small, stateless-ish, easy to keep up",
], edge=GREEN, fill=GREENF, ts=12.5, ss=8.9)
arr(8.67, 10.62, 12.13, 11.15, color=GREEN, lw=1.4, rad=-0.10)
ax.text(10.35, 11.30, "acquire / renew / release", fontsize=9.0, color=GREEN,
        ha="center", style="italic")

listbox(14.98, 7.75, 5.60, 3.45, "Why stdio cannot be the fleet transport", [
    "stdio means the client SPAWNS the server.",
    "Spawning is per-client — so two agents that",
    "launch pickering-lxi-mcp get two processes,",
    "and two truths about one set of relays.",
    "The reservation cannot arbitrate between",
    "them, because each process has its own.",
    "",
    "A shared device needs a daemon that clients",
    "connect TO, not a subprocess they start.",
    "That is the entire reason for HTTP here —",
    "not remoteness, singularity.",
], edge=RED, fill="#FBF0EF", tcol=RED, ts=12.5, ss=8.9)

listbox(14.98, 4.30, 5.60, 2.85, "Single-bench mode — where stdio IS right", [
    "One engineer, one bench, one process tree:",
    "",
    "    agent  +  MCP client  +  server",
    "    all on the laptop, stdio between them;",
    "    the LXI chassis still reached over IP",
    "",
    "No network hop, no auth, no broker. Correct",
    "until a second caller exists — then it is the",
    "wrong shape, not a smaller right one.",
], edge=LINE, fill=BG, ts=12.5, ss=8.9)

listbox(14.98, 1.60, 5.60, 1.90, "Scaling to N racks", [
    "One gateway per rack — it follows the host",
    "boundary, so it cannot be shared across racks.",
    "The broker stays fleet-wide. A thin router",
    "above the gateways is the next piece to build,",
    "not a bigger gateway.",
], edge=LINE, fill=BG, ts=12.5, ss=8.9)

plt.savefig(
    "deployment-and-transports.png",
            dpi=160, facecolor=BG, bbox_inches="tight", pad_inches=0.36)
print("ok")
