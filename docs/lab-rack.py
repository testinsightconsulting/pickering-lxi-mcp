"""Draw the worked bench (docs/EXAMPLE-BENCH.md) as the two racks it lives in.

    python docs/lab-rack.py          # writes docs/lab-rack.svg
    python docs/lab-rack.py --png    # also docs/lab-rack.png (needs playwright + chromium)

This is an original illustration, not a photograph: instruments are drawn generically at
their real rack heights and labelled with their real model numbers. Relay state is the
middle of walkthroughs/08_rf_bench.json -- three routes open, blue LEDs on the closed
RF paths, exactly as the 40-785C lights them.
"""
from __future__ import annotations

import html
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ── palette: the same one the other docs/ figures use ────────────────────────────
BG, INK, MUTED, LINE = "#FAF9F6", "#17171A", "#6E6E73", "#C6C4BD"
ACC, ACCF = "#A84A17", "#F5EFE8"        # signal / RF
BLUE = "#2B5C86"                         # data plane
GREEN = "#3A6647"                        # instrument management
TEAL = "#2F7373"                         # DUT management
PLUM = "#5B3A7E"                         # out-of-band
DC = "#5C6168"                           # DC / control harness
LED_ON, LED_OFF = "#4FB6FF", "#394553"

SANS = "Inter, 'Inter Variable', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif"
MONO = "'JetBrains Mono', 'SFMono-Regular', Menlo, Consolas, monospace"

W, H = 1880, 1400
U = 38                     # one rack unit
PW = 412                   # 19-inch panel width at that scale (1U/19in = 0.0921)
RAIL = 22
POST = 14
TOP = 196                  # first U row, both racks

RACK_A_X = 430
RACK_B_X = 1080

out: list[str] = []
PORTS: dict[str, tuple[float, float]] = {}


# ── primitives ───────────────────────────────────────────────────────────────────
def a(**kw) -> str:
    return " ".join(f'{k.rstrip("_").replace("_", "-")}="{v}"' for k, v in kw.items() if v is not None)


def rect(x, y, w, h, fill, stroke=None, sw=1, rx=0, **kw):
    out.append(f'<rect {a(x=f"{x:.1f}", y=f"{y:.1f}", width=f"{w:.1f}", height=f"{h:.1f}", rx=rx, fill=fill, stroke=stroke, stroke_width=sw if stroke else None, **kw)}/>')


def circle(cx, cy, r, fill, stroke=None, sw=1, **kw):
    out.append(f'<circle {a(cx=f"{cx:.1f}", cy=f"{cy:.1f}", r=r, fill=fill, stroke=stroke, stroke_width=sw if stroke else None, **kw)}/>')


def line(x1, y1, x2, y2, stroke, sw=1, **kw):
    out.append(f'<line {a(x1=f"{x1:.1f}", y1=f"{y1:.1f}", x2=f"{x2:.1f}", y2=f"{y2:.1f}", stroke=stroke, stroke_width=sw, **kw)}/>')


def path(d, stroke="none", sw=1, fill="none", **kw):
    out.append(f'<path {a(d=d, stroke=stroke, stroke_width=sw, fill=fill, **kw)}/>')


def text(x, y, s, size=12, fill=INK, anchor="start", weight=400, family=SANS, **kw):
    out.append(f'<text {a(x=f"{x:.1f}", y=f"{y:.1f}", font_size=size, fill=fill, text_anchor=anchor, font_weight=weight, font_family=family, **kw)}>{html.escape(s)}</text>')


def smooth(points, tension=0.5):
    """Catmull-Rom through the waypoints -> one cubic bezier path. Cables drape; they
    do not turn corners."""
    p = [points[0], *points, points[-1]]
    d = f"M{p[1][0]:.1f},{p[1][1]:.1f}"
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        c1 = (p1[0] + (p2[0] - p0[0]) * tension / 3, p1[1] + (p2[1] - p0[1]) * tension / 3)
        c2 = (p2[0] - (p3[0] - p1[0]) * tension / 3, p2[1] - (p3[1] - p1[1]) * tension / 3)
        d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    return d


def cable(points, color, sw=3.2, active=False, dash=None, boots=True):
    d = smooth(points)
    if active:
        path(d, stroke=color, sw=sw + 9, opacity="0.20", stroke_linecap="round")
    path(d, stroke="#00000030", sw=sw + 1.6, stroke_linecap="round", transform="translate(1.2,1.6)")
    path(d, stroke=color, sw=sw, stroke_linecap="round", stroke_dasharray=dash,
         opacity=None if active else "0.9")
    if boots:
        for (x, y) in (points[0], points[-1]):
            circle(x, y, sw * 0.9 + 1.2, "#2A2B2E")


def sma(x, y, r=5.2, name=None, term=False):
    circle(x, y, r + 1.4, "#8C7A52")
    circle(x, y, r, "#D9B25A", stroke="#9A7A33", sw=0.8)
    circle(x, y, r * 0.42, "#6B5424")
    if term:                                    # 50-ohm load screwed on
        circle(x, y, r + 0.6, "#2C2E31")
        circle(x - 1, y - 1, r * 0.35, "#5A5E64")
    if name:
        PORTS[name] = (x, y)


def ntype(x, y, name=None):
    circle(x, y, 9.5, "#A9ADB2", stroke="#6F7479", sw=1)
    circle(x, y, 6, "#D5D8DB", stroke="#8A8F94", sw=0.8)
    circle(x, y, 2.4, "#55595E")
    if name:
        PORTS[name] = (x, y)


def rj45(x, y, accent=None, name=None, w=9, h=7.5):
    rect(x - w / 2, y - h / 2, w, h, "#0E0F11", stroke="#44474C", sw=0.6, rx=0.8)
    if accent:
        rect(x - w / 2 + 1, y + h / 2 - 2, 2.4, 1.6, accent)
        rect(x + w / 2 - 3.4, y + h / 2 - 2, 2.4, 1.6, "#D9A441")
    if name:
        PORTS[name] = (x, y)


def led(x, y, on, color=LED_ON, r=2.1):
    if on:
        circle(x, y, r + 3.2, color, opacity="0.28")
    circle(x, y, r, color if on else LED_OFF)


def screws(x, y, h):
    for yy in (y + 7, y + h - 7) if h > 30 else (y + h / 2,):
        circle(x, yy, 2.6, "#7B7F85", stroke="#4E5157", sw=0.6)


def ears(px, y, h, color="#B7BAB8"):
    rect(px - RAIL + 3, y + 1, RAIL - 1, h - 2, color, rx=1.5)
    rect(px + PW - 2, y + 1, RAIL - 1, h - 2, color, rx=1.5)
    screws(px - RAIL / 2 + 3, y, h)
    screws(px + PW + RAIL / 2 - 2, y, h)


def uy(u):
    return TOP + (u - 1) * U


# ── rack frame ───────────────────────────────────────────────────────────────────
def rack(x, units, label):
    px = x + POST + RAIL
    outer_w = PW + 2 * RAIL + 2 * POST
    y0, y1 = TOP - 30, TOP + units * U + 26
    rect(x - 4, y0 - 4, outer_w + 8, y1 - y0 + 8, "#00000014", rx=8)
    rect(x, y0, outer_w, y1 - y0, "#1F2124", rx=6)
    rect(x + POST, TOP - 4, PW + 2 * RAIL, units * U + 8, "#131417")
    for rx_ in (x + POST, x + POST + RAIL + PW):
        rect(rx_, TOP - 4, RAIL, units * U + 8, "#3B3E43")
        for u in range(units):
            for k in (0.22, 0.5, 0.78):
                rect(rx_ + RAIL / 2 - 2.6, TOP + u * U + U * k - 2.6, 5.2, 5.2, "#17181B", rx=0.8)
        for u in range(units + 1):
            line(rx_ + 3, TOP + u * U, rx_ + 7, TOP + u * U, "#6A6E74", 0.8)
    # top cap and plinth
    rect(x, y0, outer_w, 26, "#2A2C30", rx=6)
    text(x + outer_w / 2, y0 + 17.5, label, 11.5, "#C9CCD1", "middle", 600,
         letter_spacing="2.2")
    rect(x + 18, y1, 26, 12, "#2A2C30", rx=2)
    rect(x + outer_w - 44, y1, 26, 12, "#2A2C30", rx=2)
    for u in range(units):
        text(x + POST + 4, TOP + u * U + U / 2 + 3, str(units - u), 7.5, "#8B9096",
             family=MONO)
    return px


def blank(px, y, u=1, vent=False):
    h = u * U
    rect(px - RAIL + 3, y + 1, PW + 2 * RAIL - 5, h - 2, "#2A2C30", stroke="#35373C", sw=0.8, rx=1.5)
    screws(px - RAIL / 2 + 3, y, h)
    screws(px + PW + RAIL / 2 - 2, y, h)
    if vent:
        for row in range(3):
            for col in range(46):
                circle(px + 16 + col * 8.5 + (4 if row % 2 else 0), y + 11 + row * 8, 1.7, "#141518")


def brush(px, y):
    blank(px, y)
    rect(px + 20, y + 14, PW - 40, 10, "#141518", rx=5)
    for i in range(70):
        line(px + 24 + i * 5.3, y + 15, px + 24 + i * 5.3 + 1, y + 23, "#3A3D42", 0.9)


# ── Rack A: signal ───────────────────────────────────────────────────────────────
def screen(x, y, w, h):
    rect(x - 3, y - 3, w + 6, h + 6, "#2B2D31", rx=3)
    rect(x, y, w, h, "#0F1D28", rx=1.5)


def keypad(x, y, cols, rows, s=9, g=3.4, fill="#F3F3F1"):
    for r in range(rows):
        for c in range(cols):
            rect(x + c * (s + g), y + r * (s * 0.8 + g), s, s * 0.8, fill, stroke="#9EA19E", sw=0.5, rx=1.4)


def knob(x, y, r):
    circle(x, y, r + 2, "#9A9D9A")
    circle(x, y, r, "#3A3C40")
    circle(x, y, r * 0.72, "#505358")
    circle(x + r * 0.35, y - r * 0.35, r * 0.12, "#8C9095")


def siggen(px, y):
    h = 2 * U
    ears(px, y, h)
    rect(px, y + 1, PW, h - 2, "#E3E4E1", stroke="#B3B5B2", sw=0.8, rx=2.5)
    rect(px, y + 1, PW, 7, "#D1D3D0", rx=2.5)
    circle(px + 14, y + h - 14, 4.5, "#3C3E42")
    circle(px + 14, y + h - 14, 2, "#6BCB6B")
    screen(px + 30, y + 14, 118, 50)
    text(px + 36, y + 30, "1.000 000 000 GHz", 8.2, "#9AD6FF", family=MONO)
    text(px + 36, y + 45, "  -10.00 dBm", 10.5, "#E7F4FF", family=MONO, weight=600)
    text(px + 36, y + 58, "RF ON   MOD OFF", 6.5, "#6FB7E0", family=MONO)
    for i in range(5):
        rect(px + 154, y + 14 + i * 10, 13, 7, "#F3F3F1", stroke="#9EA19E", sw=0.5, rx=1.2)
    keypad(px + 182, y + 14, 4, 4)
    knob(px + 262, y + 38, 15)
    keypad(px + 292, y + 22, 2, 3, s=11)
    text(px + 360, y + 22, "N5182B", 8.5, "#55585C", weight=700, family=SANS)
    text(px + 375, y + 64, "RF OUT", 6.5, "#55585C", "middle", 600)
    sma(px + 375, y + 50, r=5.8, name="mxg_out")


def analyser(px, y):
    h = 4 * U
    ears(px, y, h)
    rect(px, y + 1, PW, h - 2, "#E3E4E1", stroke="#B3B5B2", sw=0.8, rx=2.5)
    rect(px, y + 1, PW, 8, "#D1D3D0", rx=2.5)
    sx, sy, sw_, sh = px + 30, y + 18, 196, 116
    screen(sx, sy, sw_, sh)
    for i in range(1, 10):
        line(sx + sw_ * i / 10, sy + 4, sx + sw_ * i / 10, sy + sh - 4, "#1E3446", 0.6)
    for i in range(1, 8):
        line(sx + 4, sy + sh * i / 8, sx + sw_ - 4, sy + sh * i / 8, "#1E3446", 0.6)
    pts = []
    for i in range(0, 97):
        t = i / 96
        xx = sx + 6 + t * (sw_ - 12)
        peak = 70 * math.exp(-((t - 0.5) ** 2) / 0.0009)
        side = 16 * math.exp(-((t - 0.44) ** 2) / 0.0006) + 16 * math.exp(-((t - 0.56) ** 2) / 0.0006)
        noise = 5 * math.sin(i * 2.3) * math.sin(i * 0.7) + 3 * math.sin(i * 5.1)
        pts.append((xx, sy + sh - 16 - peak - side - noise))
    path("M" + " L".join(f"{x:.1f},{y_:.1f}" for x, y_ in pts), stroke="#FFD34D", sw=1.3)
    text(sx + 6, sy + 12, "Ref 0.00 dBm   Center 1.000 GHz", 6.4, "#9AD6FF", family=MONO)
    text(sx + sw_ - 6, sy + sh - 5, "Span 20 MHz", 6.4, "#9AD6FF", "end", family=MONO)
    for i in range(8):
        rect(px + 234, y + 20 + i * 14, 15, 9, "#F3F3F1", stroke="#9EA19E", sw=0.5, rx=1.2)
    keypad(px + 262, y + 24, 4, 5)
    knob(px + 285, y + 110, 17)
    keypad(px + 318, y + 24, 3, 3, s=11)
    text(px + 392, y + 26, "N9020B", 8.5, "#55585C", "end", 700)
    circle(px + 14, y + h - 14, 4.5, "#3C3E42")
    circle(px + 14, y + h - 14, 2, "#6BCB6B")
    text(px + 372, y + 144, "RF INPUT", 6.5, "#55585C", "middle", 600)
    ntype(px + 372, y + 124, name="mxa_in")


def sensor_shelf(px, y):
    h = U
    rect(px - RAIL + 3, y + h - 7, PW + 2 * RAIL - 5, 6, "#3E4146", rx=1)
    screws(px - RAIL / 2 + 3, y + h - 12, 14)
    screws(px + PW + RAIL / 2 - 2, y + h - 12, 14)
    # USB average power sensor, lying on the shelf
    rect(px + 26, y + 12, 86, 18, "#50545A", rx=8)
    rect(px + 26, y + 12, 86, 5, "#62666C", rx=4)
    rect(px + 112, y + 16, 16, 10, "#8C9096", rx=2)
    line(px + 26, y + 21, px + 6, y + 30, "#2A2B2E", 2.2)
    text(px + 69, y + 25, "power sensor", 6.5, "#DADDE0", "middle", 600)
    sma(px + 134, y + 21, r=4.6, name="sensor_in")
    # noise source
    rect(px + 262, y + 11, 74, 20, "#5A4A3A", rx=3)
    text(px + 299, y + 24, "noise source", 6.5, "#F0E3D2", "middle", 600)
    rect(px + 336, y + 15, 10, 12, "#8C9096", rx=1.5)
    sma(px + 352, y + 21, r=4.6, name="noise_out")


CH_DY = 15.5


def sp6t(x, y, w, name, closed_ch, mirror=False):
    rect(x + 0.6, y, w - 1.2, 120, "#CDD1D5", stroke="#9CA2A8", sw=0.7, rx=1)
    rect(x + 4, y - 7, w - 8, 7, "#2E3034", rx=1.5)           # ejector
    rect(x + 4, y + 120, w - 8, 7, "#2E3034", rx=1.5)
    cx = x + w / 2 + (6 if mirror else -6)
    lx = x + 9 if mirror else x + w - 9
    sma(cx, y + 13, r=4.6, name=f"{name}_com")
    for k in range(1, 7):
        cy = y + 13 + k * CH_DY
        led(lx, cy, k == closed_ch, r=1.9)
        sma(cx, cy, r=4.6, name=f"{name}_{k}", term=k >= 5)
    text(x + w / 2, y + 116, "40-785C", 5.6, "#44484D", "middle", 700)


def gp_matrix_mod(x, y, w):
    rect(x + 0.6, y, w - 1.2, 120, "#CDD1D5", stroke="#9CA2A8", sw=0.7, rx=1)
    rect(x + 3, y - 7, w - 6, 7, "#2E3034", rx=1.5)
    rect(x + 3, y + 120, w - 6, 7, "#2E3034", rx=1.5)
    rect(x + w / 2 - 5, y + 18, 10, 76, "#3A3D42", rx=3)
    for i in range(12):
        circle(x + w / 2 - 1.8, y + 24 + i * 5.6, 0.9, "#A2A7AD")
        circle(x + w / 2 + 1.8, y + 26.8 + i * 5.6, 0.9, "#A2A7AD")
    led(x + w / 2, y + 104, True, color="#6BCB6B", r=1.6)
    PORTS["gp_conn"] = (x + w / 2, y + 60)


def filler(x, y, w):
    rect(x + 0.6, y, w - 1.2, 120, "#8E949A", stroke="#747A80", sw=0.6, rx=1)
    circle(x + w / 2, y + 5, 1.6, "#5C6167")
    circle(x + w / 2, y + 115, 1.6, "#5C6167")


CHASSIS = {}


def pickering(px, y):
    h = 4 * U
    ears(px, y, h, color="#5B6066")
    rect(px, y + 1, PW, h - 2, "#474B51", stroke="#2E3135", sw=0.8, rx=2.5)
    for i in range(52):                                   # top / bottom vents
        rect(px + 70 + i * 6.4, y + 5, 3.4, 5, "#2B2E32", rx=1)
        rect(px + 70 + i * 6.4, y + h - 10, 3.4, 5, "#2B2E32", rx=1)
    # control strip: IP display and LXI status LEDs
    rect(px + 8, y + 12, 54, h - 24, "#3B3F44", rx=2)
    rect(px + 12, y + 20, 46, 16, "#0D1A12", rx=1.5)
    text(px + 35, y + 31.5, "10.10.1.50", 6.9, "#7CF09A", "middle", family=MONO, weight=600)
    for i, (lab, on, col) in enumerate([("PWR", True, "#6BCB6B"), ("RDY", True, "#6BCB6B"),
                                        ("ERR", False, "#E0564A"), ("LAN", True, "#6BCB6B"),
                                        ("1G", True, "#E7B343")]):
        led(px + 18, y + 50 + i * 13, on, color=col, r=2)
        text(px + 25, y + 52.5 + i * 13, lab, 6, "#C3C7CC", weight=600)
    text(px + 35, y + h - 18, "LXI", 9, "#DADDE0", "middle", 800)
    rect(px + 28, y + h - 40, 14, 8, "#1D1F22", rx=1)          # front USB aux
    # 18 slots
    x0, slot = px + 68, (PW - 76) / 18
    my = y + 18
    CHASSIS.update(x0=x0, slot=slot, y=my)
    sp6t(x0, my, slot * 3, "src", closed_ch=2)
    sp6t(x0 + slot * 3, my, slot * 3, "rx", closed_ch=1, mirror=True)
    gp_matrix_mod(x0 + slot * 6, my, slot)
    for s in range(7, 18):
        filler(x0 + slot * s, my, slot)
    text(px + PW - 8, y + h - 3, "60-103D-001", 6.2, "#C3C7CC", "end", 700)


def patch_panel(px, y):
    h = U
    ears(px, y, h, color="#4A4D52")
    rect(px, y + 1, PW, h - 2, "#303338", rx=2)
    for i in range(12):
        x = px + 48 + i * 28
        sma(x, y + 17, r=4.6, name=f"patch_{i + 1}")
        text(x, y + 33, str(i + 1), 6, "#9CA1A7", "middle", family=MONO)
    text(px + 12, y + 22, "SMA", 7, "#9CA1A7", weight=700)
    text(px + PW - 12, y + 22, "PATCH", 7, "#9CA1A7", "end", 700)


def dut(px, y):
    h = 2 * U
    rect(px - RAIL + 3, y + h - 6, PW + 2 * RAIL - 5, 5, "#3E4146", rx=1)
    screws(px - RAIL / 2 + 3, y + h - 12, 14)
    screws(px + PW + RAIL / 2 - 2, y + h - 12, 14)
    bx = px + 8
    rect(bx, y + 4, PW - 16, h - 12, "#3A4556", stroke="#232A35", sw=0.8, rx=3)
    for i in range(11):                                   # heat-sink fins
        rect(bx + 8 + i * 5.5, y + 30, 3, h - 43, "#2C3441", rx=1)
    text(bx + 8, y + 19, "DUT", 9.5, "#E6EBF2", weight=800)
    text(bx + 32, y + 19, "radio under test", 6.3, "#AEB8C6")
    # RF
    sma(px + 118, y + 48, r=5, name="dut_rx_d")
    sma(px + 144, y + 48, r=5, name="dut_rx_p")
    path(f"M{px + 112},{y + 60} L{px + 112},{y + 64} L{px + 150},{y + 64} L{px + 150},{y + 60}",
         stroke="#AEB8C6", sw=0.8)
    text(px + 131, y + 71, "RX", 6.3, "#E6EBF2", "middle", 700)
    sma(px + 214, y + 48, r=5, name="dut_tx")
    text(px + 214, y + 64, "TX", 6.3, "#E6EBF2", "middle", 700)
    sma(px + 242, y + 48, r=5, name="dut_ref")
    text(px + 242, y + 64, "REF", 6.3, "#E6EBF2", "middle", 700)
    # DC header
    rect(px + 268, y + 40, 26, 14, "#3F8B4E", rx=1.5)
    for i in range(4):
        circle(px + 272 + i * 6, y + 47, 1.6, "#1E3A24")
    PORTS["dut_dc"] = (px + 281, y + 47)
    text(px + 281, y + 64, "DC", 6.3, "#E6EBF2", "middle", 700)
    # management, console, data
    rj45(px + 310, y + 47, accent=TEAL, name="dut_mgmt", w=11, h=9)
    text(px + 310, y + 64, "MGMT", 5.8, "#E6EBF2", "middle", 700)
    rj45(px + 330, y + 47, accent=PLUM, name="dut_console", w=11, h=9)
    text(px + 330, y + 64, "CON", 5.8, "#E6EBF2", "middle", 700)
    for i in range(4):
        x = px + 350 + i * 12
        rect(x - 4.5, y + 42, 9, 11, "#15181D", stroke="#6D7580", sw=0.6, rx=1)
        led(x, y + 36, i < 2, color="#6BCB6B", r=1.3)
        PORTS[f"dut_data_{i + 1}"] = (x, y + 47.5)
    text(px + 368, y + 64, "DATA", 5.8, "#E6EBF2", "middle", 700)


def bench_dc(px, y):
    h = 2 * U
    ears(px, y, h)
    half = PW / 2
    for i, (lab, l1, l2) in enumerate([("DC SUPPLY", "12.000 V", "0.250 A"), ("DMM", "11.998", "VDC")]):
        x = px + i * half
        rect(x + 1, y + 1, half - 2, h - 2, "#E3E4E1", stroke="#B3B5B2", sw=0.8, rx=2.5)
        screen(x + 14, y + 14, 92, 34)
        text(x + 20, y + 30, l1, 11, "#E7F4FF", family=MONO, weight=600)
        text(x + 20, y + 43, l2, 7.5, "#9AD6FF", family=MONO)
        text(x + 14, y + 66, lab, 6.8, "#55585C", weight=700)
        keypad(x + 114, y + 14, 3, 3, s=9)
        for j, col in enumerate(("#C8372D", "#1E1F22", "#1E1F22" if i else "#3C7A44")):
            circle(x + 162 + j * 14, y + 56, 5, col, stroke="#8C8F92", sw=0.8)
            circle(x + 162 + j * 14, y + 56, 2, "#B9BCBF")
        PORTS["psu" if i == 0 else "dmm"] = (x + 169, y + 56)


# ── Rack B: control and traffic ──────────────────────────────────────────────────
def switch(px, y, accent, label, ports=24, name=None, used=()):
    h = U
    ears(px, y, h, color="#4A4D52")
    rect(px, y + 1, PW, h - 2, "#2C2F34", stroke="#1C1E21", sw=0.8, rx=2)
    rect(px + 6, y + 6, 4, h - 12, accent, rx=1)
    text(px + 16, y + 16, label, 7.2, "#E3E6EA", weight=700)
    text(px + 16, y + 27, "1U", 6, "#8D939A", family=MONO)
    for i in range(ports):
        col, row = i // 2, i % 2
        x = px + 150 + col * 16.5
        rj45(x, y + 12 + row * 13, accent="#6BCB6B" if (i in used or i < 6) else None)
        if name and i == 0:
            PORTS[name] = (x, y + 12)
    for i in range(2):
        rect(px + 360 + i * 20, y + 10, 14, 17, "#15181D", stroke="#6D7580", sw=0.6, rx=1)


def console_server(px, y):
    h = U
    ears(px, y, h, color="#4A4D52")
    rect(px, y + 1, PW, h - 2, "#2E2C33", stroke="#1C1E21", sw=0.8, rx=2)
    rect(px + 6, y + 6, 4, h - 12, PLUM, rx=1)
    text(px + 16, y + 16, "CONSOLE", 7.2, "#E3E6EA", weight=700)
    text(px + 16, y + 27, "serial · RS-232", 6, "#8D939A")
    for i in range(16):
        x = px + 150 + i * 14.5
        rj45(x, y + 19, accent=PLUM if i < 3 else None)
        if i == 0:
            PORTS["con_1"] = (x, y + 19)
    rect(px + 390, y + 12, 12, 14, "#0E0F11", rx=1.5)


def testcenter(px, y):
    h = 4 * U
    ears(px, y, h, color="#4A4D52")
    rect(px, y + 1, PW, h - 2, "#303338", stroke="#1C1E21", sw=0.8, rx=2.5)
    # controller strip
    rect(px + 8, y + 10, 76, h - 20, "#262829", rx=2)
    text(px + 16, y + 26, "TestCenter", 8.4, "#E9ECEF", weight=800)
    text(px + 16, y + 37, "SPT-N4U", 7.4, "#AEB3B9", family=MONO)
    for i, lab in enumerate(("PWR", "SYS", "FAN")):
        led(px + 18, y + 56 + i * 12, True, color="#6BCB6B", r=2)
        text(px + 25, y + 58.5 + i * 12, lab, 6, "#C3C7CC", weight=600)
    rj45(px + 30, y + 108, accent=GREEN)
    rj45(px + 50, y + 108)
    text(px + 40, y + 124, "MGMT", 5.8, "#AEB3B9", "middle", 700)
    # two test-module slots
    for m in range(2):
        my = y + 14 + m * 64
        rect(px + 92, my, PW - 102, 58, "#3B3E43", stroke="#23262A", sw=0.8, rx=2)
        rect(px + 96, my + 4, 8, 50, "#26282C", rx=1.5)
        text(px + 112, my + 14, f"test module {m + 1}", 6.6, "#C9CDD2", weight=700)
        for p in range(8):
            x = px + 124 + p * 33
            rect(x - 8, my + 24, 16, 14, "#131518", stroke="#7B828A", sw=0.7, rx=1)
            rect(x - 5, my + 27, 10, 8, "#1F2226", rx=0.6)
            live = m == 0 and p < 2
            led(x - 5, my + 45, live, color="#6BCB6B", r=1.7)
            led(x + 5, my + 45, live, color="#E7B343", r=1.7)
            text(x, my + 54, f"{p + 1}", 5.6, "#8D939A", "middle", family=MONO)
            if m == 0 and p < 2:
                PORTS[f"stc_{p + 1}"] = (x, y + 14 + 31)


def jump_host(px, y):
    h = U
    ears(px, y, h, color="#4A4D52")
    rect(px, y + 1, PW, h - 2, "#34373C", stroke="#1C1E21", sw=0.8, rx=2)
    for i in range(4):
        rect(px + 14 + i * 58, y + 7, 52, 24, "#23252A", stroke="#4A4E54", sw=0.6, rx=1.5)
        line(px + 20 + i * 58, y + 19, px + 58 + i * 58, y + 19, "#4A4E54", 1)
        led(px + 60 + i * 58, y + 12, True, color="#6BCB6B", r=1.3)
    text(px + 262, y + 16, "JUMP HOST", 7.2, "#E3E6EA", weight=700)
    text(px + 262, y + 27, "the only multi-homed box", 6, "#8D939A")
    rj45(px + 372, y + 19, accent=GREEN)
    rj45(px + 388, y + 19, accent=TEAL)


def pdu(px, y, feed):
    h = U
    ears(px, y, h, color="#4A4D52")
    rect(px, y + 1, PW, h - 2, "#1E1F22", stroke="#0F1012", sw=0.8, rx=2)
    rect(px + 6, y + 6, 4, h - 12, PLUM, rx=1)
    text(px + 16, y + 16, f"PDU {feed}", 7.2, "#E3E6EA", weight=700)
    rect(px + 16, y + 21, 34, 11, "#0D1A12", rx=1)
    text(px + 33, y + 29.5, "3.4 A", 6.8, "#7CF09A", "middle", family=MONO)
    for i in range(10):
        x = px + 80 + i * 32
        path(f"M{x - 9},{y + 11} L{x + 9},{y + 11} L{x + 9},{y + 24} L{x + 5},{y + 28} L{x - 5},{y + 28} L{x - 9},{y + 24} Z",
             fill="#0C0D0F", stroke="#45484D", sw=0.7)
        rect(x - 5, y + 16, 2, 5, "#3E4146")
        rect(x + 3, y + 16, 2, 5, "#3E4146")
        led(x + 13, y + 12, i < 7, color="#6BCB6B", r=1.3)


# ── callouts ─────────────────────────────────────────────────────────────────────
def callout_left(y, target_x, target_y, title, sub=(), mono=None, color=INK):
    tx = 400
    text(tx, y, title, 14, color, "end", 700)
    yy = y
    for s in sub:
        yy += 17
        text(tx, yy, s, 11.5, MUTED, "end")
    if mono:
        yy += 17
        text(tx, yy, mono, 11, ACC, "end", 500, MONO)
    path(f"M{tx + 8},{y - 4.5} L{tx + 30},{y - 4.5} L{target_x},{target_y}", stroke="#9A9891", sw=1)
    circle(target_x, target_y, 3.2, BG, stroke=INK, sw=1.4)


def callout_right(y, target_x, target_y, title, sub=(), accent=None):
    tx = 1592
    if accent:
        rect(tx, y - 11, 4, 14, accent, rx=1)
    text(tx + (11 if accent else 0), y, title, 14, INK, "start", 700)
    yy = y
    for s in sub:
        yy += 17
        text(tx + (11 if accent else 0), yy, s, 11.5, MUTED)
    path(f"M{tx - 8},{y - 4.5} L{tx - 26},{y - 4.5} L{target_x},{target_y}", stroke="#9A9891", sw=1)
    circle(target_x, target_y, 3.2, BG, stroke=INK, sw=1.4)


# ── the drawing ──────────────────────────────────────────────────────────────────
def draw():
    out.append(f'<rect width="{W}" height="{H}" fill="{BG}"/>')
    text(40, 62, "The worked bench, racked", 34, INK, weight=800, letter_spacing="-0.6")
    text(40, 94, "docs/EXAMPLE-BENCH.md on real hardware: Pickering LXI switching between Keysight RF instruments, "
         "a VIAVI TestCenter and the DUT.", 15.5, MUTED)
    text(40, 116, "Real model numbers at their real rack heights; only the DUT is invented. Relay state: "
         "walkthrough 08, three routes open.", 15.5, MUTED)

    pa = rack(RACK_A_X, 18, "RACK A · SIGNAL")
    pb = rack(RACK_B_X, 18, "RACK B · CONTROL AND TRAFFIC")

    # Rack A, top to bottom
    brush(pa, uy(1))
    siggen(pa, uy(2))
    analyser(pa, uy(4))
    sensor_shelf(pa, uy(8))
    pickering(pa, uy(9))
    blank(pa, uy(13), vent=True)
    patch_panel(pa, uy(14))
    dut(pa, uy(15))
    bench_dc(pa, uy(17))

    # Rack B
    switch(pb, uy(1), PLUM, "OOBM", name="oobm_1")
    console_server(pb, uy(2))
    blank(pb, uy(3))
    switch(pb, uy(4), GREEN, "MGMT A", name="mgmt_a_1")
    switch(pb, uy(5), TEAL, "MGMT B", name="mgmt_b_1")
    brush(pb, uy(6))
    testcenter(pb, uy(7))
    blank(pb, uy(11))
    jump_host(pb, uy(12))
    for u in (13, 14, 15):
        blank(pb, uy(u))
    pdu(pb, uy(16), "A")
    pdu(pb, uy(17), "B")
    blank(pb, uy(18))

    P = PORTS
    top9 = uy(9)
    # ── RF cabling: instruments down the right-hand side into the two COMs ──
    (sx, sy), (rx_, ry) = P["src_com"], P["rx_com"]
    mo = P["mxg_out"]
    cable([mo, (mo[0] + 14, mo[1] + 16), (pa + PW + 7, uy(4) + 20), (pa + PW + 7, uy(7) + 30),
           (pa + PW - 24, uy(8) + 6), (pa + 200, uy(8) + 4), (sx + 12, top9 + 2), (sx, sy)],
          ACC, 3.4, active=True)
    mi = P["mxa_in"]
    cable([mi, (mi[0] + 2, mi[1] + 22), (pa + 300, uy(8) + 34), (rx_ + 30, top9 + 8), (rx_, ry)],
          ACC, 3.4, active=True)
    # source side leaves to the left, receive side to the right, then everything drops
    def ch(k, side):
        x, y = P[f"{side}_{k}"]
        return x, y

    x, y = ch(1, "src")

    q = P["dut_rx_d"]
    cable([(x, y), (x - 10, y + 5), (pa + 80, uy(12) + 30), (pa + 96, uy(14) + 8), (q[0], q[1] - 30), q], ACC, 2.8)
    x, y = ch(2, "src")
    q = P["dut_rx_p"]
    cable([(x, y), (x - 13, y + 5), (pa + 74, uy(12) + 34), (pa + 110, uy(14) + 4), (q[0], q[1] - 44), q],
          ACC, 2.8, active=True)
    x, y = ch(3, "src")
    q = P["patch_3"]
    cable([(x, y), (x - 16, y + 6), (pa + 70, uy(12) + 36), (q[0] - 4, q[1] - 20), q], ACC, 2.8)
    x, y = ch(4, "src")
    q = P["sensor_in"]
    cable([(x, y), (x - 19, y - 2), (pa + 66, top9 + 20), (pa + 110, uy(8) + 32), (q[0] - 12, q[1] + 2), q],
          ACC, 2.8)

    x, y = ch(1, "rx")

    q = P["dut_tx"]
    cable([(x, y), (x + 12, y + 5), (pa + 206, uy(12) + 30), (q[0] - 4, uy(14) + 4), (q[0], q[1] - 26), q],
          ACC, 2.8, active=True)
    x, y = ch(2, "rx")
    q = P["dut_ref"]
    cable([(x, y), (x + 14, y + 5), (pa + 232, uy(12) + 26), (q[0] - 2, uy(14) + 2), (q[0], q[1] - 26), q],
          ACC, 2.8)
    x, y = ch(3, "rx")
    q = P["patch_4"]
    cable([(x, y), (x - 7, y + 8), (x - 14, uy(12) + 34), (q[0] + 6, q[1] - 20), q], ACC, 2.8)
    x, y = ch(4, "rx")
    q = P["noise_out"]
    cable([(x, y), (x + 16, y - 3), (pa + 300, top9 + 44), (q[0] + 16, top9 + 14), (q[0] + 8, q[1] + 12), q],
          ACC, 2.8)
    # the calibration loop: patch 3 <-> patch 4, a link the matrix never switches
    x3, y3 = P["patch_3"]
    x4, _ = P["patch_4"]
    path(f"M{x3},{y3 + 6} C{x3},{y3 + 17} {x4},{y3 + 17} {x4},{y3 + 6}", stroke=ACC, sw=3)
    # 20 dB pad, inline just ahead of the padded RX
    qx, qy = P["dut_rx_p"]
    rect(qx - 5.5, qy - 34, 11, 19, "#B9BDC2", stroke="#6F747A", sw=0.8, rx=2)
    line(qx - 5.5, qy - 29, qx + 5.5, qy - 29, "#6F747A", 0.8)
    text(qx + 9, qy - 22, "20 dB", 7, "#E6EBF2", "start", 700)

    # DC harness: matrix connector -> DUT DC header, and down to the supply and DMM
    gx, gy = P["gp_conn"]
    hub = (pa + 262, uy(14) + 4)
    cable([P["gp_conn"], (gx + 3, gy + 22), (gx + 20, uy(12) + 34), (pa + 244, uy(13) + 20), hub], DC, 6.5,
          active=True, boots=False)
    cable([hub, (P["dut_dc"][0] - 2, P["dut_dc"][1] - 22), P["dut_dc"]], DC, 4.2)
    cable([hub, (pa + 296, uy(14) + 14), (pa + PW - 6, uy(15) + 20), (pa + PW - 10, uy(17) + 18),
           (P["dmm"][0] + 16, P["dmm"][1] - 16), P["dmm"]], DC, 3)
    cable([hub, (pa + 240, uy(15) + 6), (pa + 196, uy(16) + 28), (P["psu"][0] + 8, P["psu"][1] - 22),
           P["psu"]], DC, 3)

    # detail marker on the chassis
    rect(pa + 290, uy(13) + 10, 112, 18, "#FAF9F6", rx=9)
    text(pa + 346, uy(13) + 22.5, "slots 1–7: detail below", 7.4, INK, "middle", 700)

    # ── between the racks: data plane, DUT management, DUT console ──
    gap = (RACK_A_X + PW + 2 * RAIL + 2 * POST + RACK_B_X) / 2
    for i, stc in enumerate(("stc_1", "stc_2")):
        sxp, syp = P[stc]
        dx, dy = P[f"dut_data_{i + 1}"]
        yb = uy(11) + 14 + i * 9
        cable([(sxp, syp), (sxp - 2, syp + 40), (sxp - 14, yb), (pb - 20, yb + 2), (gap + 10 - i * 10, uy(13) + i * 8),
               (pa + PW + 30, uy(15) + 2 + i * 6), (dx + 4, dy - 26), (dx, dy)], BLUE, 3.6, active=True)
    mx, my = P["dut_mgmt"]
    mb = P["mgmt_b_1"]
    cable([(mx, my), (mx + 2, my - 24), (pa + PW + 18, uy(14) + 8), (gap - 22, uy(11)),
           (gap - 8, uy(6) + 20), (pb - 12, uy(5) + 34), (mb[0] - 16, mb[1] + 16), mb], TEAL, 2.6)
    cx_, cy_ = P["dut_console"]
    cb = P["con_1"]
    cable([(cx_, cy_), (cx_ + 2, cy_ - 28), (pa + PW + 28, uy(14) + 2), (gap - 36, uy(10)),
           (gap - 24, uy(4)), (pb - 14, uy(2) + 34), (cb[0] - 14, cb[1] + 14), cb], PLUM, 2.4)

    # ── callouts ──
    callout_left(uy(2) + 30, pa + 6, uy(2) + 38, "Keysight N5182B MXG",
                 ["vector signal generator · Opt 1EA", "+26 dBm max out · 10.10.1.21"], "sig_gen_out")
    callout_left(uy(4) + 58, pa + 6, uy(4) + 76, "Keysight N9020B MXA",
                 ["signal analyser · +30 dBm, ±0.2 Vdc in", "10.10.1.22"], "analyser_in")
    callout_left(uy(8) + 16, pa + 6, uy(8) + 20, "Power sensor · noise source",
                 ["ratings asserted, not looked up"], "power_sensor · noise_source")
    callout_left(uy(9) + 34, pa + 6, uy(9) + 60, "Pickering 60-103D-001",
                 ["18-slot LXI/USB modular chassis · 10.10.1.50",
                  "slots 1–3 · 40-785C-521 SP6T 18 GHz → rf_src",
                  "slots 4–6 · 40-785C-521 SP6T 18 GHz → rf_rx",
                  "slot 7 · 40-series GP matrix, 6×12 → gp_matrix"], color=ACC)
    callout_left(uy(14) + 18, pa + 6, uy(14) + 18, "SMA patch panel",
                 ["ports 3↔4: the calibration loop — a link, never switched"])
    callout_left(uy(15) + 34, pa + 6, uy(15) + 40, "DUT",
                 ["a radio with an Ethernet management port", "10.10.2.10 — a different subnet on purpose"], "dut_*")
    callout_left(uy(17) + 44, pa + 6, uy(17) + 40, "DC supply · DMM",
                 ["model to suit — rows of the GP matrix"], "psu_* · gnd · dmm_*")

    pr = pb + PW + 16
    callout_right(uy(1) + 16, pr, uy(1) + 19, "OOBM switch", ["10.10.0.0/24 · its own box, not a VLAN"], PLUM)
    callout_right(uy(2) + 26, pr, uy(2) + 19, "Console server", ["serial to the DUT and the chassis"], PLUM)
    callout_right(uy(4) + 16, pr, uy(4) + 19, "Mgmt switch A", ["instruments · 10.10.1.0/24"], GREEN)
    callout_right(uy(5) + 28, pr, uy(5) + 19, "Mgmt switch B", ["DUT management · 10.10.2.0/24"], TEAL)
    callout_right(uy(7) + 56, pr, uy(7) + 60, "VIAVI TestCenter SPT-N4U",
                  ["2-slot traffic chassis (formerly Spirent)", "data plane: cabled straight to the DUT,",
                   "never through the matrix"], BLUE)
    callout_right(uy(12) + 16, pr, uy(12) + 19, "Jump host",
                  ["the only multi-homed device;", "does not route between A and B"])
    callout_right(uy(16) + 26, pr, uy(16) + 38, "Switched PDUs, A and B feeds", ["on the OOBM plane"], PLUM)

    inset()


def inset():
    y0, y1 = 950, H - 30
    x0, x1 = 40, W - 40
    # zoom frame on the chassis, and the leaders down to the inset
    c = CHASSIS
    zx0, zy0 = c["x0"] - 3, c["y"] - 10
    zx1, zy1 = c["x0"] + c["slot"] * 7 + 3, c["y"] + 130
    rect(zx0, zy0, zx1 - zx0, zy1 - zy0, "none", stroke=INK, sw=1.4, rx=3, stroke_dasharray="4 3")
    rect(x0, y0, x1 - x0, y1 - y0, "#FFFFFF", stroke=LINE, sw=1.2, rx=10)

    text(x0 + 28, y0 + 38, "SLOTS 1–7, WITH THE NAMES THE TOPOLOGY GIVES EACH CONNECTOR", 12.5, ACC, weight=700,
         letter_spacing="1.6")
    text(x0 + 28, y0 + 60, "rf_bench.json maps every SMA to an endpoint. Blue LED = closed RF path; "
         "the filled crosspoint is psu_pos → dut_vcc.", 13, MUTED)

    def big_mux(x, y, title, card, names, closed):
        text(x, y - 12, title, 13, INK, weight=700)
        text(x + 112, y - 12, card, 11.5, MUTED, family=MONO)
        rect(x, y, 66, 7 * 34 + 8, "#CDD1D5", stroke="#9CA2A8", sw=1, rx=3)
        for k in range(7):
            cy = y + 22 + k * 34
            if k:
                led(x + 14, cy, k == closed, r=3.2)
            circle(x + 40, cy, 11, "#8C7A52")
            circle(x + 40, cy, 9, "#D9B25A", stroke="#9A7A33", sw=1)
            circle(x + 40, cy, 3.6, "#6B5424")
            if k >= 5:
                circle(x + 40, cy, 10, "#2C2E31")
            lab = "COM" if k == 0 else f"ch {k}"
            text(x + 78, cy + 4, lab, 11, MUTED, family=MONO)
            nm, note = names[k]
            text(x + 122, cy + 4, nm, 12.5, ACC if nm != "—" else MUTED, weight=600, family=MONO)
            if note:
                text(x + 122, cy + 20, note, 10.5, MUTED)

    top = y0 + 104
    big_mux(x0 + 28, top, "rf_src", "slots 1–3", [
        ("sig_gen_out", "N5182B RF OUT · exclusive"),
        ("dut_rx_direct", "+10 dBm max — refused"),
        ("dut_rx_padded", "via 20 dB pad · route open"),
        ("loop_src", "patch 3 → cal loop"),
        ("power_sensor", None),
        ("—", "50 Ω terminated"),
        ("—", None)], closed=2)
    big_mux(x0 + 370, top, "rf_rx", "slots 4–6", [
        ("analyser_in", "N9020B RF INPUT"),
        ("dut_tx", "+23 dBm · route open"),
        ("dut_ref_clk", None),
        ("loop_rx", "patch 4 → cal loop"),
        ("noise_source", "refused: closure limit 1"),
        ("—", "50 Ω terminated"),
        ("—", None)], closed=1)

    # GP matrix, 6 x 12
    gx, gy = x0 + 718, top
    text(gx, gy - 12, "gp_matrix", 13, INK, weight=700)
    text(gx + 88, gy - 12, "slot 7 · 6×12", 11.5, MUTED, family=MONO)
    rows = ["psu_pos", "psu_neg", "gnd", "dmm_hi", "dmm_lo", "dio_enable"]
    cols = ["dut_vcc", "dut_gnd", "dut_enable", "dut_reset", "dut_testpt1", "dut_testpt2"]
    cs = 22
    ox, oy = gx + 84, gy + 22
    for r_, nm in enumerate(rows):
        text(ox - 10, oy + r_ * cs + 4, nm, 11, ACC, "end", 600, MONO)
        line(ox, oy + r_ * cs, ox + 11 * cs, oy + r_ * cs, "#B9B6AE", 1.2)
    for c_ in range(12):
        line(ox + c_ * cs, oy - 8, ox + c_ * cs, oy + 5 * cs + 8, "#B9B6AE", 1.2)
    for c_, nm in enumerate(cols):
        text(ox + c_ * cs + 3, oy + 5 * cs + 16, nm, 10.5, ACC, "start", 600, MONO,
             transform=f"rotate(50 {ox + c_ * cs + 3} {oy + 5 * cs + 16})")
    for c_ in range(6, 12):
        text(ox + c_ * cs, oy + 5 * cs + 22, "·", 12, MUTED, "middle")
    for r_ in range(6):
        for c_ in range(12):
            circle(ox + c_ * cs, oy + r_ * cs, 3, "#FFFFFF", stroke="#9A9891", sw=1)
    circle(ox, oy, 6.5, ACC, opacity="0.25")
    circle(ox, oy, 4.6, ACC)
    circle(ox, oy + 2 * cs, 4.6, "#FFFFFF", stroke="#9A2F2F", sw=1.6)
    line(ox - 3.5, oy + 2 * cs - 3.5, ox + 3.5, oy + 2 * cs + 3.5, "#9A2F2F", 1.6)
    text(ox + 12 * cs + 2, oy + 2 * cs + 4, "gnd → dut_vcc: refused,", 11, "#9A2F2F", weight=600)
    text(ox + 12 * cs + 2, oy + 2 * cs + 19, "would short psu_pos to gnd", 11, "#9A2F2F")

    # legend
    lx = x0 + 1340
    text(lx, top - 12, "Key", 13, INK, weight=700)
    items = [(ACC, 3.4, None, "RF · SMA", True), (DC, 6, None, "DC / control harness", False),
             (BLUE, 3.6, None, "data plane · TestCenter ↔ DUT", False),
             (TEAL, 2.6, None, "DUT management", False), (PLUM, 2.4, None, "out-of-band · console, PDUs", False)]
    for i, (col, sw, _dash, lab, glow) in enumerate(items):
        yy = top + 14 + i * 28
        if glow:
            line(lx, yy, lx + 44, yy, col, sw + 9, opacity="0.2", stroke_linecap="round")
        line(lx, yy, lx + 44, yy, col, sw, stroke_linecap="round")
        text(lx + 58, yy + 4, lab, 12, INK)
    yy = top + 14 + 5 * 28
    line(lx, yy, lx + 44, yy, ACC, 12.4, opacity="0.2", stroke_linecap="round")
    line(lx, yy, lx + 44, yy, ACC, 3.4, stroke_linecap="round")
    text(lx + 58, yy + 4, "glow = part of an open route", 12, INK)
    yy += 28
    led(lx + 22, yy, True, r=3.2)
    text(lx + 58, yy + 4, "blue LED = closed RF path", 12, INK)
    yy += 28
    rect(lx + 16, yy - 6, 12, 12, "#7CF09A", rx=2)
    text(lx + 58, yy + 4, "instrument LAN is on the rear panels", 12, INK)
    text(lx, yy + 34, "Illustration, not a photograph. Instruments drawn", 11, MUTED)
    text(lx, yy + 50, "generically; model numbers and rack heights real.", 11, MUTED)


def main():
    draw()
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
           f'role="img" aria-label="Two equipment racks: Rack A holds a Keysight N5182B signal generator, '
           f'a Keysight N9020B signal analyser, a Pickering 60-103D-001 LXI chassis with two 40-785C-521 '
           f'SP6T RF multiplexers and a general-purpose matrix, an SMA patch panel, the DUT and a DC supply '
           f'and DMM. Rack B holds the out-of-band, instrument and DUT management switches, a console '
           f'server, a VIAVI TestCenter SPT-N4U, a jump host and two PDUs.">\n'
           + "\n".join(out) + "\n</svg>\n")
    (HERE / "lab-rack.svg").write_text(svg, encoding="utf-8")
    print("wrote docs/lab-rack.svg")
    if "--png" in sys.argv:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1.25)
            pg.set_content(f"<html><body style='margin:0'>{svg}</body></html>")
            pg.wait_for_timeout(300)
            pg.screenshot(path=str(HERE / "lab-rack.png"), full_page=False)
            b.close()
        print("wrote docs/lab-rack.png")


if __name__ == "__main__":
    main()
