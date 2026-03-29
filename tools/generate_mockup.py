"""Generate a dashboard mockup image using the Autobiographer design system.

Run with:  venv/Scripts/python tools/generate_mockup.py
Output:    assets/dashboard_mockup.png
"""

from __future__ import annotations

import math
import random

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import numpy as np
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.colors import LinearSegmentedColormap

# ── Palette ────────────────────────────────────────────────────────────────────
BG          = "#0c1120"
CARD        = "#141c2f"
SIDEBAR     = "#090e1a"
LIFTED      = "#1e293b"
BORDER      = "#2d3a52"
TEXT        = "#f0f4ff"
TEXT_DIM    = "#8895a7"
TEXT_MUTED  = "#4b5a72"
INDIGO      = "#6366f1"
CYAN        = "#22d3ee"
PINK        = "#f472b6"
PURPLE      = "#a855f7"
GREEN       = "#22c55e"
ORANGE      = "#f97316"
YELLOW      = "#facc15"

CHART_PALETTE = [INDIGO, CYAN, PINK, PURPLE, GREEN, ORANGE, YELLOW]

random.seed(42)
rng = np.random.default_rng(42)

# ── Canvas ─────────────────────────────────────────────────────────────────────
FIG_W, FIG_H = 24, 16
fig = plt.figure(figsize=(FIG_W, FIG_H), facecolor=BG)
fig.patch.set_facecolor(BG)


def card(ax: plt.Axes, x: float, y: float, w: float, h: float,
         accent_left: str | None = None, radius: float = 0.015) -> None:
    """Draw a rounded card background on the given axes."""
    rx = radius * (FIG_H / FIG_W)
    ry = radius
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0,rounding_size={rx}",
        facecolor=CARD, edgecolor=BORDER, linewidth=0.6,
        transform=fig.transFigure, clip_on=False,
    )
    fig.add_artist(patch)
    if accent_left:
        accent = plt.Rectangle(
            (x, y), 0.003, h,
            facecolor=accent_left, transform=fig.transFigure, clip_on=False,
        )
        fig.add_artist(accent)


def label(x: float, y: float, text: str, size: float = 7,
          color: str = TEXT_DIM, weight: str = "normal",
          ha: str = "left", va: str = "center") -> None:
    fig.text(x, y, text, color=color, fontsize=size,
             fontweight=weight, ha=ha, va=va)


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
SB_W = 0.13
sidebar_bg = plt.Rectangle((0, 0), SB_W, 1, facecolor=SIDEBAR,
                             transform=fig.transFigure, clip_on=False)
fig.add_artist(sidebar_bg)
sidebar_border = plt.Rectangle((SB_W - 0.001, 0), 0.001, 1,
                                facecolor=BORDER, transform=fig.transFigure, clip_on=False)
fig.add_artist(sidebar_border)

# App name
fig.text(0.065, 0.94, "autobiographer", color=TEXT, fontsize=11,
         fontweight="bold", ha="center", va="center")
fig.text(0.065, 0.905, "personal data explorer", color=TEXT_MUTED,
         fontsize=6.5, ha="center", va="center")

# Nav items
nav_items = [
    ("dashboard",       INDIGO, True),
    ("headphones",      TEXT_DIM, False),
    ("location_on",     TEXT_DIM, False),
    ("fitness_center",  TEXT_DIM, False),
    ("local_library",   TEXT_DIM, False),
    ("sports_bar",      TEXT_DIM, False),
]
nav_labels = ["Overview", "Music", "Places", "Fitness", "Culture", "Beer"]
for i, ((icon, col, active), nav_label) in enumerate(zip(nav_items, nav_labels)):
    y = 0.845 - i * 0.065
    if active:
        highlight = FancyBboxPatch(
            (0.008, y - 0.022), SB_W - 0.016, 0.044,
            boxstyle="round,pad=0,rounding_size=0.008",
            facecolor=LIFTED, edgecolor="none",
            transform=fig.transFigure, clip_on=False,
        )
        fig.add_artist(highlight)
        left_bar = plt.Rectangle((0.008, y - 0.022), 0.003, 0.044,
                                  facecolor=INDIGO, transform=fig.transFigure, clip_on=False)
        fig.add_artist(left_bar)
    dot = plt.Circle((0.038, y), 0.007,
                     color=col, transform=fig.transFigure, clip_on=False)
    fig.add_artist(dot)
    fig.text(0.052, y, nav_label, color=col if active else TEXT_DIM,
             fontsize=7.5, fontweight="semibold" if active else "normal",
             va="center")

# Config fields
fig.text(0.016, 0.38, "DATA SOURCES", color=TEXT_MUTED, fontsize=5.5,
         fontweight="bold", va="center")
config_fields = ["Last.fm CSV", "Swarm directory", "Assumptions JSON"]
for i, cf in enumerate(config_fields):
    y = 0.345 - i * 0.048
    field_bg = FancyBboxPatch(
        (0.01, y - 0.016), SB_W - 0.02, 0.032,
        boxstyle="round,pad=0,rounding_size=0.005",
        facecolor=LIFTED, edgecolor=BORDER, linewidth=0.5,
        transform=fig.transFigure, clip_on=False,
    )
    fig.add_artist(field_bg)
    fig.text(0.02, y, cf, color=TEXT_DIM, fontsize=6, va="center")

# Load button
btn = FancyBboxPatch(
    (0.01, 0.17), SB_W - 0.02, 0.038,
    boxstyle="round,pad=0,rounding_size=0.008",
    facecolor=INDIGO, edgecolor="none",
    transform=fig.transFigure, clip_on=False,
)
fig.add_artist(btn)
fig.text(0.065, 0.189, "Load Data", color=TEXT, fontsize=7.5,
         fontweight="bold", ha="center", va="center")

# ══════════════════════════════════════════════════════════════════════════════
# MAIN CONTENT AREA  (x: SB_W+pad … 1-pad,  y: 0.02 … 0.96)
# ══════════════════════════════════════════════════════════════════════════════
PAD  = 0.015
MX   = SB_W + PAD          # main area left
MW   = 1.0 - MX - PAD      # main area width
GAP  = 0.012               # inter-card gap

# ── Page title ─────────────────────────────────────────────────────────────
fig.text(MX, 0.955, "Overview", color=TEXT, fontsize=16,
         fontweight="bold", va="center")
fig.text(MX, 0.928, "Your complete personal data snapshot  ·  2024", color=TEXT_DIM,
         fontsize=8, va="center")

# ══════════════════════════════════════════════════════════════════════════════
# HERO CARD
# ══════════════════════════════════════════════════════════════════════════════
HX, HY, HW, HH = MX, 0.855, MW, 0.06
ax_hero = fig.add_axes([HX, HY, HW, HH])
ax_hero.set_facecolor(BG)
ax_hero.axis("off")
grad_data = np.linspace(0, 1, 256).reshape(1, -1)
hero_cmap = LinearSegmentedColormap.from_list("hero", ["#1e1b4b", "#0c1120"])
ax_hero.imshow(grad_data, aspect="auto", cmap=hero_cmap,
               extent=[0, 1, 0, 1], origin="lower", zorder=0)
hero_border = FancyBboxPatch(
    (HX, HY), HW, HH,
    boxstyle="round,pad=0,rounding_size=0.012",
    facecolor="none", edgecolor=INDIGO, linewidth=1.0,
    transform=fig.transFigure, clip_on=False,
)
fig.add_artist(hero_border)

fig.text(HX + 0.018, HY + HH * 0.62, "87,432", color=TEXT, fontsize=28,
         fontweight="bold", va="center",
         path_effects=[pe.withStroke(linewidth=6, foreground=BG)])
fig.text(HX + 0.018, HY + HH * 0.22, "scrobbles in 2024", color=TEXT_DIM,
         fontsize=8, va="center")

stats = [
    ("3,841", "check-ins"),
    ("312",   "films watched"),
    ("44",    "books read"),
    ("218",   "workouts"),
]
for i, (val, lbl) in enumerate(stats):
    sx = HX + HW * 0.38 + i * (HW * 0.155)
    fig.text(sx, HY + HH * 0.62, val, color=CHART_PALETTE[i + 1],
             fontsize=16, fontweight="bold", va="center")
    fig.text(sx, HY + HH * 0.22, lbl, color=TEXT_DIM, fontsize=6.5, va="center")

# ══════════════════════════════════════════════════════════════════════════════
# KPI ROW  (4 metric cards)
# ══════════════════════════════════════════════════════════════════════════════
KY, KH = 0.775, 0.068
kpi_data = [
    ("87,432",  "+1,204 this month",  "Scrobbles",        INDIGO),
    ("3,841",   "+47 this month",     "Check-ins",        CYAN),
    ("312",     "↑ 28 from last yr",  "Films Watched",    PINK),
    ("44",      "↑ 6 from last yr",   "Books Read",       PURPLE),
]
KW = (MW - 3 * GAP) / 4
for i, (val, delta, lbl, accent) in enumerate(kpi_data):
    kx = MX + i * (KW + GAP)
    card(fig, kx, KY, KW, KH, accent_left=accent)
    fig.text(kx + 0.016, KY + KH * 0.72, val, color=TEXT, fontsize=14,
             fontweight="bold", va="center")
    fig.text(kx + 0.016, KY + KH * 0.42, delta, color=GREEN, fontsize=6.5, va="center")
    fig.text(kx + 0.016, KY + KH * 0.18, lbl.upper(), color=TEXT_MUTED,
             fontsize=5.5, fontweight="bold", va="center")

# ══════════════════════════════════════════════════════════════════════════════
# ROW 2:  Streamgraph (left 60%)  +  Top Artists bar chart (right 40%)
# ══════════════════════════════════════════════════════════════════════════════
R2Y, R2H = 0.47, 0.285

# ── Streamgraph ────────────────────────────────────────────────────────────
SG_W = MW * 0.585
card(fig, MX, R2Y, SG_W - GAP / 2, R2H)
ax_sg = fig.add_axes([MX + 0.012, R2Y + 0.045, SG_W - GAP / 2 - 0.024, R2H - 0.065])
ax_sg.set_facecolor(CARD)

weeks = 52
x = np.linspace(0, weeks, weeks)
genres = ["Rock", "Electronic", "Jazz", "Hip-Hop", "Classical"]
genre_colors = [INDIGO, CYAN, PINK, PURPLE, GREEN]
ys = []
for seed in [7, 13, 21, 5, 17]:
    rng2 = np.random.default_rng(seed)
    base = rng2.uniform(3, 15, weeks)
    smooth = np.convolve(base, np.ones(8) / 8, mode="same")
    ys.append(smooth)
total = np.array(ys).sum(axis=0)
normalized = [y / total for y in ys]
bottoms = np.zeros(weeks)
center_offset = -0.5 * np.ones(weeks)
for y in normalized:
    center_offset += y
center_offset *= 0.5
bottoms = -center_offset.copy()
for i, (y, c) in enumerate(zip(normalized, genre_colors)):
    ax_sg.fill_between(x, bottoms, bottoms + y, color=c, alpha=0.85, linewidth=0)
    bottoms += y

ax_sg.set_xlim(0, weeks)
ax_sg.set_facecolor(CARD)
ax_sg.tick_params(colors=TEXT_DIM, labelsize=6)
ax_sg.set_xticks([0, 13, 26, 39, 52])
ax_sg.set_xticklabels(["Jan", "Apr", "Jul", "Oct", "Dec"], color=TEXT_DIM, fontsize=6)
ax_sg.set_yticks([])
for spine in ax_sg.spines.values():
    spine.set_visible(False)
ax_sg.grid(axis="x", color=BORDER, linewidth=0.4, alpha=0.5)

fig.text(MX + 0.012, R2Y + R2H - 0.012, "Listening by Genre  ·  2024",
         color=TEXT, fontsize=8, fontweight="semibold", va="center")

legend_x = MX + 0.012
for i, (g, c) in enumerate(zip(genres, genre_colors)):
    dot = plt.Circle((legend_x + i * 0.072 + 0.005, R2Y + 0.022), 0.003,
                     color=c, transform=fig.transFigure, clip_on=False)
    fig.add_artist(dot)
    fig.text(legend_x + i * 0.072 + 0.011, R2Y + 0.022, g,
             color=TEXT_DIM, fontsize=5.5, va="center")

# ── Top Artists horizontal bar ──────────────────────────────────────────────
BA_X = MX + SG_W + GAP / 2
BA_W = MW - SG_W - GAP / 2
card(fig, BA_X, R2Y, BA_W, R2H)
ax_bar = fig.add_axes([BA_X + 0.01, R2Y + 0.045, BA_W - 0.018, R2H - 0.065])
ax_bar.set_facecolor(CARD)

artists = ["Radiohead", "Portishead", "Massive Attack",
           "Aphex Twin", "The National", "Sigur Rós", "Bjork"]
counts  = [3241, 2108, 1876, 1654, 1432, 1287, 1104]
max_c   = counts[0]
bar_colors = [INDIGO if i == 0 else LIFTED for i in range(len(artists))]
bars = ax_bar.barh(range(len(artists)), counts, color=bar_colors,
                   height=0.65, zorder=2)
bars[0].set_color(INDIGO)
ax_bar.set_xlim(0, max_c * 1.18)
ax_bar.set_yticks(range(len(artists)))
ax_bar.set_yticklabels(artists, color=TEXT, fontsize=6.5)
ax_bar.set_xticks([])
ax_bar.invert_yaxis()
ax_bar.set_facecolor(CARD)
for spine in ax_bar.spines.values():
    spine.set_visible(False)
ax_bar.tick_params(left=False, colors=TEXT_DIM)
for i, (bar, count) in enumerate(zip(bars, counts)):
    ax_bar.text(count + max_c * 0.02, i, f"{count:,}",
                va="center", color=TEXT_DIM, fontsize=5.5)

fig.text(BA_X + 0.01, R2Y + R2H - 0.012, "Top Artists",
         color=TEXT, fontsize=8, fontweight="semibold", va="center")

# ══════════════════════════════════════════════════════════════════════════════
# ROW 3:  Map (left 55%)  +  Calendar heatmap (right 45%)
# ══════════════════════════════════════════════════════════════════════════════
R3Y, R3H = 0.06, 0.39

# ── Map ────────────────────────────────────────────────────────────────────
MAP_W = MW * 0.54
card(fig, MX, R3Y, MAP_W - GAP / 2, R3H)
ax_map = fig.add_axes([MX + 0.008, R3Y + 0.042, MAP_W - GAP / 2 - 0.016, R3H - 0.058])
ax_map.set_facecolor("#060d1a")

# Faint city grid lines
for gx in np.linspace(-0.2, 1.2, 18):
    ax_map.axvline(gx, color="#0e1d33", linewidth=0.3, alpha=0.6)
for gy in np.linspace(-0.2, 1.2, 12):
    ax_map.axhline(gy, color="#0e1d33", linewidth=0.3, alpha=0.6)

# Heatmap blobs (clusters of check-ins)
cluster_centers = [
    (0.35, 0.55, 0.12, INDIGO),   # main city
    (0.62, 0.48, 0.07, CYAN),
    (0.20, 0.38, 0.05, PURPLE),
    (0.75, 0.68, 0.06, PINK),
    (0.50, 0.28, 0.04, GREEN),
]
for cx, cy, radius, color in cluster_centers:
    for r in np.linspace(radius, 0, 12):
        alpha = (1 - r / radius) ** 2 * 0.25
        circle = plt.Circle((cx, cy), r, color=color, alpha=alpha,
                             transform=ax_map.transData, zorder=2)
        ax_map.add_patch(circle)

# Individual check-in dots
n_dots = 180
dot_x = np.concatenate([
    rng.normal(cx, radius * 0.4, int(40 * radius / 0.06))
    for cx, cy, radius, _ in cluster_centers
    for _ in [cy]
])
dot_y = np.concatenate([
    rng.normal(cy, radius * 0.4, int(40 * radius / 0.06))
    for cx, cy, radius, _ in cluster_centers
    for cy in [cy]
])
dot_colors = [CHART_PALETTE[i % len(CHART_PALETTE)]
              for i, (cx, cy, radius, _) in enumerate(cluster_centers)
              for _ in range(int(40 * radius / 0.06))]
ax_map.scatter(dot_x[:n_dots], dot_y[:n_dots], s=4, c=dot_colors[:n_dots],
               alpha=0.7, zorder=3, linewidths=0)

ax_map.set_xlim(0, 1)
ax_map.set_ylim(0, 1)
ax_map.set_xticks([])
ax_map.set_yticks([])
for spine in ax_map.spines.values():
    spine.set_edgecolor(BORDER)
    spine.set_linewidth(0.5)

fig.text(MX + 0.008, R3Y + R3H - 0.01, "Check-in Heatmap",
         color=TEXT, fontsize=8, fontweight="semibold", va="center")
fig.text(MX + 0.008, R3Y + 0.024, "pydeck  ·  HeatmapLayer + ScatterplotLayer  ·  CARTO dark-matter",
         color=TEXT_MUTED, fontsize=5.5, va="center")

# ── Calendar Heatmap ────────────────────────────────────────────────────────
CAL_X = MX + MAP_W + GAP / 2
CAL_W = MW - MAP_W - GAP / 2
card(fig, CAL_X, R3Y, CAL_W, R3H)
ax_cal = fig.add_axes([CAL_X + 0.01, R3Y + 0.065, CAL_W - 0.018, R3H - 0.09])
ax_cal.set_facecolor(CARD)

days = 365
cal_vals = rng.integers(0, 15, days).astype(float)
# Add some peaks
for peak in [45, 120, 200, 280, 340]:
    cal_vals[peak:peak + 7] += rng.integers(10, 25, 7)
cal_vals = np.clip(cal_vals, 0, 35)

cols = math.ceil(days / 7)
grid = np.zeros((7, cols))
for d in range(days):
    grid[d % 7, d // 7] = cal_vals[d]

cmap_cal = LinearSegmentedColormap.from_list("cal", [CARD, INDIGO, CYAN])
ax_cal.imshow(grid, aspect="auto", cmap=cmap_cal,
              vmin=0, vmax=35, origin="upper", interpolation="nearest")
ax_cal.set_xticks(np.linspace(0, cols - 1, 12))
ax_cal.set_xticklabels(["J","F","M","A","M","J","J","A","S","O","N","D"],
                        color=TEXT_DIM, fontsize=5.5)
ax_cal.set_yticks(range(7))
ax_cal.set_yticklabels(["S","M","T","W","T","F","S"], color=TEXT_DIM, fontsize=5)
ax_cal.tick_params(length=0)
for spine in ax_cal.spines.values():
    spine.set_visible(False)

fig.text(CAL_X + 0.01, R3Y + R3H - 0.01, "Activity Calendar  ·  2024",
         color=TEXT, fontsize=8, fontweight="semibold", va="center")

month_labels = ["Jan", "Apr", "Jul", "Oct"]
for i, ml in enumerate(month_labels):
    fig.text(CAL_X + 0.01 + i * (CAL_W - 0.02) / 3.5,
             R3Y + 0.024, ml, color=TEXT_MUTED, fontsize=5.5, va="center")

# ── Footer watermark ────────────────────────────────────────────────────────
fig.text(0.5, 0.015, "autobiographer  ·  design mockup  ·  deep space indigo palette",
         color=TEXT_MUTED, fontsize=6, ha="center", va="center")

# ── Save ────────────────────────────────────────────────────────────────────
out_path = "assets/dashboard_mockup.png"
plt.savefig(out_path, dpi=180, bbox_inches="tight",
            facecolor=BG, edgecolor="none")
print(f"Saved: {out_path}")
