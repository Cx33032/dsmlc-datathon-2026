"""Printable parts for the Idea 4 tabletop "well" rig.

Run:  python data/ideas/4/cad/make_parts.py
Writes: docs/ideas/4/cad/*.stl          (binary STL, millimetres, Z up = print orientation)
        docs/ideas/4/assets/4f_printed_parts.png   (render of every part)
        docs/ideas/4/assets/4g_rig_assembly.png    (render of the assembled rig)

No CAD program is needed: every part is built from simple closed shapes with numpy.
Each part is one STL that may contain several overlapping closed shells
(slicers such as PrusaSlicer, Bambu Studio and Cura merge overlapping shells).
The script checks that EVERY shell is watertight (each edge used exactly twice,
in opposite directions) and stops with an error if one is not.

MEASURE YOUR PARTS FIRST. The default sizes below are common values for the
Elegoo kit DC motor (130-size), the SG90 servo, a 4 mm wooden dowel and a
regular-mouth glass jar. Change the numbers in PARAMS, then run again.
An editable OpenSCAD version of the same parts is in docs/ideas/4/cad/rig_parts.scad.
"""
from pathlib import Path
import struct
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import common as cm  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

OUT = cm.DOCS_IDEAS / "4" / "cad"
OUT.mkdir(parents=True, exist_ok=True)

PARAMS = dict(
    rod_d=4.0,            # wooden dowel or steel rod diameter ("rod string")
    rod_clear=0.6,        # extra diameter for holes the rod must turn in
    rod_press=0.2,        # extra diameter for holes the rod is glued / pressed into
    jar_inner_d=58.0,     # inside diameter of the jar mouth ("wellbore")
    lid_d=90.0,           # lid outer diameter (must be wider than the jar rim)
    motor_w=20.4,         # DC motor can, wide side (flat to flat across the long side)
    motor_t=15.2,         # DC motor can, thin side (flat to flat)
    motor_boss_d=6.6,     # round boss around the motor shaft
    motor_shaft_d=2.0,    # motor shaft diameter
    servo_l=22.8,         # SG90 body length
    servo_w=12.4,         # SG90 body width
    magnet_d=6.0,         # optional disc magnets in the coupling (6 x 3 mm)
    magnet_t=3.0,
    pcp_r=6.0,            # PCP rotor section radius
    pcp_e=2.0,            # PCP eccentricity
    pcp_pitch=40.0,       # rotor pitch (stator pitch is 2x)
    pcp_len=120.0,        # rotor / stator length
    pcp_clear=0.45,       # radial clearance between rotor and stator
)
P = PARAMS
N = 96  # facets around a circle


# ------------------------------------------------------------------ mesh primitives (all return closed shells)
def _ring(r, z, n=N, cx=0.0, cy=0.0):
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.c_[cx + r * np.cos(a), cy + r * np.sin(a), np.full(n, z)]


def _side(lo, hi, outward=True):
    """Quads between two loops with the same vertex count. Loops are CCW seen from +Z."""
    t = []
    n = len(lo)
    for i in range(n):
        j = (i + 1) % n
        a, b, c, d = lo[i], lo[j], hi[j], hi[i]
        if outward:
            t += [(a, b, c), (a, c, d)]
        else:
            t += [(a, c, b), (a, d, c)]
    return t


def _cap(loop, up):
    c = loop.mean(axis=0)
    n = len(loop)
    return [(c, loop[i], loop[(i + 1) % n]) if up else (c, loop[(i + 1) % n], loop[i]) for i in range(n)]


def _annulus(inner, outer, up):
    """Flat ring between two loops with the same vertex count (both CCW)."""
    t = []
    n = len(inner)
    for i in range(n):
        j = (i + 1) % n
        a, b, c, d = inner[i], inner[j], outer[j], outer[i]
        if up:
            t += [(a, d, c), (a, c, b)]
        else:
            t += [(a, b, c), (a, c, d)]
    return t


def loft(loops, cap_bottom=True, cap_top=True):
    """Closed solid through a stack of loops (bottom to top)."""
    t = []
    for k in range(len(loops) - 1):
        t += _side(loops[k], loops[k + 1])
    if cap_bottom:
        t += _cap(loops[0], up=False)
    if cap_top:
        t += _cap(loops[-1], up=True)
    return np.array(t)


def cylinder(r, z0, z1, cx=0.0, cy=0.0):
    return loft([_ring(r, z0, cx=cx, cy=cy), _ring(r, z1, cx=cx, cy=cy)])


def tube(r_in, r_out, z0, z1, cx=0.0, cy=0.0):
    ib, it = _ring(r_in, z0, cx=cx, cy=cy), _ring(r_in, z1, cx=cx, cy=cy)
    ob, ot = _ring(r_out, z0, cx=cx, cy=cy), _ring(r_out, z1, cx=cx, cy=cy)
    t = _side(ob, ot) + _side(ib, it, outward=False) + _annulus(ib, ob, up=False) + _annulus(it, ot, up=True)
    return np.array(t)


def box(x0, x1, y0, y1, z0, z1):
    lo = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0]], float)
    hi = lo.copy()
    hi[:, 2] = z1
    return loft([lo, hi])


def hub(r, h, top_hole=None, bottom_hole=None):
    """Solid cylinder z 0..h with optional blind holes (radius, depth) from the top and the bottom."""
    t = []
    ob, ot = _ring(r, 0), _ring(r, h)
    t += _side(ob, ot)
    for hole, z_face, sgn in [(bottom_hole, 0.0, +1), (top_hole, h, -1)]:
        outer = ob if sgn > 0 else ot
        if hole is None:
            t += _cap(outer, up=(sgn < 0))
            continue
        hr, depth = hole
        mouth = _ring(hr, z_face)
        floor = _ring(hr, z_face + sgn * depth)
        t += _annulus(mouth, outer, up=(sgn < 0))
        if sgn > 0:      # hole from the bottom going up
            t += _side(mouth, floor, outward=False)
            t += _cap(floor, up=False)
        else:            # hole from the top going down
            t += _side(floor, mouth, outward=False)
            t += _cap(floor, up=True)
    return np.array(t)


def stadium_radius(alpha, half_len, r):
    """Distance from the origin to the edge of a stadium (segment +-half_len on x, radius r) along angle alpha."""
    u = np.c_[np.cos(alpha), np.sin(alpha)]
    lo, hi = np.zeros(len(alpha)), np.full(len(alpha), half_len + r + 1)
    for _ in range(60):
        mid = (lo + hi) / 2
        p = u * mid[:, None]
        qx = np.clip(p[:, 0], -half_len, half_len)
        d = np.hypot(p[:, 0] - qx, p[:, 1]) - r
        inside = d < 0
        lo = np.where(inside, mid, lo)
        hi = np.where(inside, hi, mid)
    return (lo + hi) / 2


def circle_radius(alpha, off, r):
    """Distance from the origin to the edge of a circle (centre (off, 0), radius r > off) along angle alpha."""
    c = off * np.cos(alpha)
    return c + np.sqrt(c ** 2 - (off ** 2 - r ** 2))


def pcp_rotor():
    """Single-lobe helical rotor: circle radius r, centre offset e, one turn per pitch. Socket in the top for the rod."""
    r, e, pitch, L = P["pcp_r"], P["pcp_e"], P["pcp_pitch"], P["pcp_len"]
    nz = int(L / 1.0) + 1
    a = np.linspace(0, 2 * np.pi, N, endpoint=False)
    loops = []
    for z in np.linspace(0, L, nz):
        phi = 2 * np.pi * z / pitch
        rr = circle_radius(a - phi, e, r)
        loops.append(np.c_[rr * np.cos(a), rr * np.sin(a), np.full(N, z)])
    t = []
    for k in range(nz - 1):
        t += _side(loops[k], loops[k + 1])
    t += _cap(loops[0], up=False)
    # top: annulus to a socket that goes 10 mm down for the rod
    sr = (P["rod_d"] + P["rod_press"]) / 2
    mouth, floor = _ring(sr, L), _ring(sr, L - 10)
    t += _annulus(mouth, loops[-1], up=True)
    t += _side(floor, mouth, outward=False)
    t += _cap(floor, up=True)
    return np.array(t)


def pcp_stator_cutaway(window_deg=90.0, R=14.0):
    """Two-lobe stator (stadium cavity, pitch 2x rotor) in a round tube, with a window cut open for display."""
    r, e, pitch, L = P["pcp_r"] + P["pcp_clear"], P["pcp_e"], 2 * P["pcp_pitch"], P["pcp_len"]
    nz, na = int(L / 1.0) + 1, 180
    a = np.linspace(np.radians(window_deg / 2), 2 * np.pi - np.radians(window_deg / 2), na)  # open C-shape
    inner, outer = [], []
    for z in np.linspace(0, L, nz):
        phi = 2 * np.pi * z / pitch
        ri = stadium_radius(a - phi, 2 * e, r)
        inner.append(np.c_[ri * np.cos(a), ri * np.sin(a), np.full(na, z)])
        outer.append(np.c_[R * np.cos(a), R * np.sin(a), np.full(na, z)])
    t = []
    for k in range(nz - 1):
        for i in range(na - 1):
            o0, o1, o2, o3 = outer[k][i], outer[k][i + 1], outer[k + 1][i + 1], outer[k + 1][i]
            t += [(o0, o1, o2), (o0, o2, o3)]
            i0, i1, i2, i3 = inner[k][i], inner[k][i + 1], inner[k + 1][i + 1], inner[k + 1][i]
            t += [(i0, i2, i1), (i0, i3, i2)]
        # the two flat faces of the window
        for i, s in [(0, -1), (na - 1, 1)]:
            p0, p1, p2, p3 = inner[k][i], outer[k][i], outer[k + 1][i], inner[k + 1][i]
            # start face (s<0) must face -theta, end face +theta
            t += [(p0, p1, p2), (p0, p2, p3)] if s < 0 else [(p0, p2, p1), (p0, p3, p2)]
    for loops_k, up in [(0, False), (nz - 1, True)]:
        for i in range(na - 1):
            a0, a1 = inner[loops_k][i], inner[loops_k][i + 1]
            b0, b1 = outer[loops_k][i], outer[loops_k][i + 1]
            t += [(a0, b0, b1), (a0, b1, a1)] if up else [(a0, b1, b0), (a0, a1, b1)]
    return np.array(t)


# ------------------------------------------------------------------ the parts
SERVO_Y = -31.0      # servo cradle centre (move closer, e.g. -28, if the horn + pad cannot reach the drum)
PILLAR_H = 69.0      # drive-head height: keeps the coupling ABOVE the servo horn / brake drum


def part_wellhead_plate():
    """Flat plate that sits on the jar rim. Print it as shown (flat side on the bed), then flip it:
    the centring lip and the guide boss go DOWN into the jar mouth. No supports needed."""
    rc = (P["rod_d"] + P["rod_clear"]) / 2
    return [
        tube(rc, P["lid_d"] / 2, 0, 4),                                        # plate with rod hole
        tube(P["jar_inner_d"] / 2 - 2.5, P["jar_inner_d"] / 2 - 0.4, 3.5, 10),  # centring lip
        tube(rc, 7, 3.5, 14),                                                  # guide boss ("stuffing box")
    ]


def part_drive_head():
    """Glue (or screw) onto the top of the plate. Two pillars carry the motor (the 'drive head');
    a cradle holds the SG90 servo standing shaft-up so its horn can press the brake drum."""
    sl, sw, y0, H = P["servo_l"], P["servo_w"], SERVO_Y, PILLAR_H
    shells = [
        box(-27, -13, -7, 7, 0, 3), box(13, 27, -7, 7, 0, 3),                 # pillar feet
        box(-27, 27, -11, -8, 0, 3),                                           # cross bar (stays clear of the rod)
        box(-6, 6, y0 + sw / 2, -8, 0, 3),                                     # spine to the servo cradle
        box(-sl / 2 - 2, sl / 2 + 2, y0 - sw / 2 - 2, y0 + sw / 2 + 2, 0, 3),  # cradle floor
        box(-24, -16, -5, 5, 0, H), box(16, 24, -5, 5, 0, H),                  # pillars
        box(-24, -9, -9, 9, H - 4, H), box(9, 24, -9, 9, H - 4, H),            # bridge
        tube(P["motor_boss_d"] / 2, 10, H - 4, H),                             # bridge centre, motor boss hole
    ]
    mw, mt, wall, z0, z1 = P["motor_w"], P["motor_t"], 2.0, H - 0.5, H + 12    # motor pocket
    shells += [box(-mw / 2 - wall, mw / 2 + wall, -mt / 2 - wall, -mt / 2, z0, z1),
               box(-mw / 2 - wall, mw / 2 + wall, mt / 2, mt / 2 + wall, z0, z1),
               box(-mw / 2 - wall, -mw / 2, -mt / 2 - 0.1, mt / 2 + 0.1, z0, z1),
               box(mw / 2, mw / 2 + wall, -mt / 2 - 0.1, mt / 2 + 0.1, z0, z1)]
    shells += [box(-sl / 2 - 2, sl / 2 + 2, y0 - sw / 2 - 2, y0 - sw / 2, 2.5, 18.5),   # cradle walls; servo tabs
               box(-sl / 2 - 2, sl / 2 + 2, y0 + sw / 2, y0 + sw / 2 + 2, 2.5, 18.5),   # rest on top (measure yours)
               box(-sl / 2 - 2, -sl / 2, y0 - sw / 2 - 0.1, y0 + sw / 2 + 0.1, 2.5, 18.5),
               box(sl / 2, sl / 2 + 2, y0 - sw / 2 - 0.1, y0 + sw / 2 + 0.1, 2.5, 18.5)]
    return shells


def part_coupling(motor_side):
    """Dog-clutch half, printed face-up (dogs up, no supports).
    Motor side: bore for the motor shaft. Rod side: bore for the dowel. Both: magnet pocket in the face."""
    r, h = 8.0, 10.0
    mag = ((P["magnet_d"] + 0.3) / 2, P["magnet_t"] + 0.2)
    bore = ((P["motor_shaft_d"] - 0.1) / 2, 6.0) if motor_side else ((P["rod_d"] + P["rod_press"]) / 2, 6.0)
    shells = [hub(r, h, top_hole=mag, bottom_hole=bore)]
    rot = 0.0 if motor_side else 60.0
    for k in range(3):
        ang = np.radians(rot + 120 * k)
        b = box(3.8, r, -1.9, 1.9, h - 0.2, h + 3.0)
        c, s = np.cos(ang), np.sin(ang)
        Rm = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
        shells.append(b @ Rm.T)
    return shells


def part_brake_drum():
    return [tube((P["rod_d"] + P["rod_press"]) / 2, 12, 0, 6)]


def part_brake_pad():
    return [box(-5, 5, 0, 4, 0, 7), box(-2, 2, -6, 0.5, 0, 3)]   # pad + flat tab to glue onto the servo horn


def part_paddle():
    hr = (P["rod_d"] + P["rod_press"]) / 2
    shells = [hub(5.5, 16, top_hole=(hr, 12))]
    for k in range(4):
        ang = np.radians(45 * k * 2)
        c, s = np.cos(ang), np.sin(ang)
        Rm = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
        shells.append(box(4.5, 21, -0.9, 0.9, 0, 13) @ Rm.T)
    return shells


PARTS = {
    "wellhead_plate": (part_wellhead_plate, "Wellhead plate (flip after printing)"),
    "drive_head": (part_drive_head, "Drive head + servo cradle"),
    "coupling_motor_side": (lambda: part_coupling(True), "Coupling, motor side"),
    "coupling_rod_side": (lambda: part_coupling(False), "Coupling, rod side ('parted rod')"),
    "brake_drum": (part_brake_drum, "Brake drum (on the rod)"),
    "brake_pad": (part_brake_pad, "Brake pad (glue to servo horn)"),
    "paddle_rotor": (part_paddle, "Paddle load (in syrup)"),
    "pcp_rotor": (lambda: [pcp_rotor()], "PCP rotor (helix)"),
    "pcp_stator_cutaway": (lambda: [pcp_stator_cutaway()], "PCP stator, cut-away"),
}


# ------------------------------------------------------------------ checks + output
def check_shell(t, name):
    """Every directed edge must appear once and its reverse once (closed, consistently oriented)."""
    key = lambda p: tuple(np.round(p, 5))
    edges = {}
    for tri in t:
        v = [key(p) for p in tri]
        if v[0] == v[1] or v[1] == v[2] or v[0] == v[2]:
            raise ValueError(f"{name}: degenerate triangle")
        for a, b in ((v[0], v[1]), (v[1], v[2]), (v[2], v[0])):
            edges[(a, b)] = edges.get((a, b), 0) + 1
    bad = [e for e, c in edges.items() if c != 1 or edges.get((e[1], e[0]), 0) != 1]
    if bad:
        raise ValueError(f"{name}: not watertight ({len(bad)} bad edges)")
    # outward orientation: signed volume must be positive
    v = np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6
    if v <= 0:
        raise ValueError(f"{name}: inward-facing shell (volume {v:.1f})")
    return v


def write_stl(tris, path):
    tris = np.asarray(tris, dtype=np.float32)
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    with open(path, "wb") as f:
        f.write(b"Idea4 rig part".ljust(80, b" "))
        f.write(struct.pack("<I", len(tris)))
        for nn, t in zip(n, tris):
            f.write(struct.pack("<12fH", *nn, *t[0], *t[1], *t[2], 0))


built = {}
for name, (fn, label) in PARTS.items():
    shells = fn()
    vol = sum(check_shell(np.asarray(s), f"{name}[{i}]") for i, s in enumerate(shells))
    tris = np.concatenate([np.asarray(s) for s in shells])
    tris[:, :, 2] -= tris[:, :, 2].min()          # sit on the print bed
    write_stl(tris, OUT / f"{name}.stl")
    ext = tris.reshape(-1, 3).max(axis=0) - tris.reshape(-1, 3).min(axis=0)
    built[name] = (tris, label)
    print(f"{name:22s} shells={len(shells):2d} triangles={len(tris):6d} "
          f"size={ext[0]:.1f} x {ext[1]:.1f} x {ext[2]:.1f} mm  volume~{vol / 1000:.1f} cm3")


# ------------------------------------------------------------------ renders (dark theme to match the diagrams)
BG, INK, MUTED, ACC = "#16181d", "#e8e6e1", "#9aa0a6", "#e0623a"


def draw(ax, tris, color, alpha=1.0, step=1):
    pc = Poly3DCollection(tris[::step], facecolor=color, edgecolor="none", alpha=alpha)
    # simple lambert shading so curved parts read as 3D
    nrm = np.cross(tris[::step, 1] - tris[::step, 0], tris[::step, 2] - tris[::step, 0])
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
    light = np.array([0.4, -0.5, 0.75])
    light /= np.linalg.norm(light)
    shade = 0.35 + 0.65 * np.clip(nrm @ light, 0, 1)
    base = np.array(plt.matplotlib.colors.to_rgb(color))
    pc.set_facecolor(np.c_[np.clip(base[None, :] * shade[:, None], 0, 1), np.full(len(shade), alpha)])
    ax.add_collection3d(pc)


def frame(ax, tris_list, pad=2):
    pts = np.concatenate([t.reshape(-1, 3) for t in tris_list])
    lo, hi = pts.min(axis=0) - pad, pts.max(axis=0) + pad
    c, s = (lo + hi) / 2, (hi - lo).max() / 2
    ax.set_xlim(c[0] - s, c[0] + s)
    ax.set_ylim(c[1] - s, c[1] + s)
    ax.set_zlim(c[2] - s, c[2] + s)
    ax.set_box_aspect((1, 1, 1))
    ax.set_axis_off()
    ax.set_facecolor(BG)


fig = plt.figure(figsize=(13, 12), facecolor=BG)
for i, (name, (tris, label)) in enumerate(built.items()):
    ax = fig.add_subplot(3, 3, i + 1, projection="3d")
    color = ACC if name.startswith("coupling") else ("#6aa9d8" if name.startswith("pcp") else "#c9c4b8")
    draw(ax, tris, color)
    frame(ax, [tris])
    ax.view_init(elev=24, azim=-58)
    ext = tris.reshape(-1, 3).max(axis=0) - tris.reshape(-1, 3).min(axis=0)
    ax.set_title(f"{label}\n{ext[0]:.0f} x {ext[1]:.0f} x {ext[2]:.0f} mm", color=INK, fontsize=10)
fig.suptitle("Idea 4 printable parts (STL files in docs/ideas/4/cad/, shown in print orientation)",
             color=INK, fontsize=13, fontweight="bold")
fig.tight_layout()
fig.savefig(cm.DOCS_IDEAS / "4" / "assets" / "4f_printed_parts.png", facecolor=BG, dpi=110)
plt.close(fig)

# assembly (jar rim at z = 0): plate flipped onto the rim, drive head glued on top, coupling under the motor,
# brake drum on the rod at servo-horn height, paddle in syrup at the bottom
fig = plt.figure(figsize=(9, 9), facecolor=BG)
ax = fig.add_subplot(111, projection="3d")
H = PILLAR_H
plate = built["wellhead_plate"][0].copy()
plate[:, :, 2] = 4 - plate[:, :, 2]                  # flip: lip and boss point down into the jar
plate = plate[:, ::-1, :]                             # keep faces outward after mirroring
head = built["drive_head"][0].copy()
head[:, :, 2] += 4
jar_h = 150.0
jar = tube(P["jar_inner_d"] / 2 - 2, P["jar_inner_d"] / 2 + 6, -jar_h, 0)
draw(ax, jar, "#5f7f8f", alpha=0.18)
syrup = cylinder(P["jar_inner_d"] / 2 - 2.2, -jar_h + 3, -60)
draw(ax, syrup, "#b8862e", alpha=0.35)
draw(ax, plate, "#c9c4b8")
draw(ax, head, "#b9b4a8")
motor = box(-P["motor_w"] / 2, P["motor_w"] / 2, -P["motor_t"] / 2, P["motor_t"] / 2, H + 4, H + 4 + 25)
draw(ax, motor, "#8a8f98")
cm_top = built["coupling_motor_side"][0].copy()
cm_top[:, :, 2] = H - cm_top[:, :, 2]                 # bore up to the motor shaft, dogs face down
cm_top = cm_top[:, ::-1, :]
draw(ax, cm_top, ACC)
cr = built["coupling_rod_side"][0].copy()
cr[:, :, 2] += H - 23                                  # dogs up, interleaved with the motor-side dogs
draw(ax, cr, ACC)
rod = cylinder(P["rod_d"] / 2, -jar_h + 12, H - 17)
draw(ax, rod, "#a07850")
drum = built["brake_drum"][0].copy()
drum[:, :, 2] += 30
draw(ax, drum, "#d8d2c4")
pad = built["brake_pad"][0].copy()
pad[:, :, 1] -= 16
pad[:, :, 2] += 30
draw(ax, pad, ACC)
servo = box(-P["servo_l"] / 2, P["servo_l"] / 2, SERVO_Y - P["servo_w"] / 2, SERVO_Y + P["servo_w"] / 2, 7, 30)
draw(ax, servo, "#3d6fb0")
padl = built["paddle_rotor"][0].copy()
padl[:, :, 2] = -padl[:, :, 2]
padl = padl[:, ::-1, :]
padl[:, :, 2] += -jar_h + 30
draw(ax, padl, "#c9c4b8")
lid = np.concatenate([plate, head])
frame(ax, [jar, lid, motor], pad=-28)
ax.view_init(elev=14, azim=-62)
ax.set_title("Assembled tabletop 'well' (not to scale with a real well)", color=INK, fontsize=13, fontweight="bold")
fig.tight_layout()
fig.canvas.draw()
from mpl_toolkits.mplot3d import proj3d  # noqa: E402

# (point on the part, label, label height in axes fraction); labels sit in a clear column on the right
pts = lid.reshape(-1, 3)
cradle = servo.reshape(-1, 3).mean(axis=0)    # anchor labels on the real geometry
labels = [(motor.reshape(-1, 3).mean(axis=0), "DC motor = surface drive head", 0.92),
          (cm_top.reshape(-1, 3).mean(axis=0), "magnetic coupling = top of the rod string", 0.80),
          (cradle, "servo + pad = brake", 0.70),
          (plate.reshape(-1, 3)[np.argmax(plate.reshape(-1, 3)[:, 0])], "plate = wellhead", 0.60),
          (np.array([P["jar_inner_d"] / 2 + 6, 0, -40]), "jar = wellbore", 0.45),
          (padl.reshape(-1, 3).mean(axis=0), "syrup + paddle = heavy-oil load", 0.20)]
for (x, y, z), txt, yf in labels:
    # project the 3D anchor to screen pixels, then draw the leader and label on the figure (always on top)
    x2, y2, _ = proj3d.proj_transform(x, y, z, ax.get_proj())
    px, py = ax.transData.transform((x2, y2))
    tx, ty = ax.transAxes.transform((0.66, yf))
    fx, fy = fig.transFigure.inverted().transform([(px, py), (tx - 4, ty)]).T
    fig.add_artist(plt.Line2D(fx, fy, color=MUTED, lw=0.8, transform=fig.transFigure))
    fig.add_artist(plt.Circle((fx[0], fy[0]), 0.003, color=INK, transform=fig.transFigure))
    fig.text(fx[1] + 0.004, fy[1], txt, color=INK, fontsize=10, va="center")
fig.savefig(cm.DOCS_IDEAS / "4" / "assets" / "4g_rig_assembly.png", facecolor=BG, dpi=110)
plt.close(fig)
print("renders written")
