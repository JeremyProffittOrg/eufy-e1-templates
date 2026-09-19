"""Eufy E1 UV-printer hold-down templates.

Draft 1. Sits on the OEM adhesive mat. Printed on a Bambu Lab H2D.
One source of numbers for OpenSCAD models and SVG drawings.
"""

from __future__ import annotations

import math
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DRAW = ROOT / "drawings"
STL = ROOT / "stl"
PNG = ROOT / "png"

# --- Bed / printer limits ---
# Mini printable 330 x 90; keep inside H2D single-nozzle 325 x 320.
MINI_PLATE = (318.0, 86.0)
# Standard printable 420 x 330 exceeds H2D. 308 x 308 is the 318 centre plate
# with 10 mm trimmed from X and Y so it fits the H2D bed.
STD_PLATE = (308.0, 308.0)
STD_MIN_OUTER = 1.5  # allow a thinner rim than WALL so the pocket grid still fits

WALL = 2.0  # outer frame (mini) and gap between pockets
CLEAR = 0.25  # per-side pocket clearance
BASE = 2.0
MAGNET_PROUD = 1.5
RAM_PROUD_TARGET = 2.0  # walls stay this far below a typical module
CORNER_R = 3.0
POCKET_R = 0.8
PICK_R = 4.5

# Item envelopes (face x, face y, thickness)
MAG_5070 = (50.0, 70.0, 7.5)
MAG_5757 = (57.0, 57.0, 7.5)
PC100 = (133.35, 38.10, 8.0)  # 8 mm envelope; real sticks 4-9 mm
SIMM72 = (107.95, 25.40, 5.08)


@dataclass
class Pocket:
    x: float
    y: float
    w: float
    h: float
    depth: float


@dataclass
class Jig:
    key: str
    title: str
    bed: str  # "mini" or "standard"
    item: str
    plate: tuple[float, float]
    item_size: tuple[float, float, float]
    pockets: list[Pocket]
    wall_z: float
    notes: list[str] = field(default_factory=list)

    @property
    def plate_z(self) -> float:
        return BASE + self.wall_z

    @property
    def cols_rows(self) -> tuple[int, int]:
        xs = sorted({round(p.x, 3) for p in self.pockets})
        ys = sorted({round(p.y, 3) for p in self.pockets})
        return len(xs), len(ys)


def pocket_xy(w: float, h: float) -> tuple[float, float]:
    return w + 2 * CLEAR, h + 2 * CLEAR


def pack(
    plate: tuple[float, float],
    item_w: float,
    item_h: float,
    min_outer: float = WALL,
) -> tuple[int, int, float, float, float, float]:
    """Return cols, rows, pocket_w, pocket_h, origin_x, origin_y. Try both orientations."""
    pw0, ph0 = pocket_xy(item_w, item_h)
    best = None
    for pw, ph, rotated in ((pw0, ph0, False), (ph0, pw0, True)):
        inner_w = plate[0] - 2 * min_outer
        inner_h = plate[1] - 2 * min_outer
        cols = max(1, int(math.floor((inner_w + WALL) / (pw + WALL))))
        rows = max(1, int(math.floor((inner_h + WALL) / (ph + WALL))))
        used_w = cols * pw + (cols - 1) * WALL
        used_h = rows * ph + (rows - 1) * WALL
        if used_w > inner_w + 0.05 or used_h > inner_h + 0.05:
            continue
        ox = min_outer + (inner_w - used_w) / 2
        oy = min_outer + (inner_h - used_h) / 2
        count = cols * rows
        score = (count, 0 if not rotated else -1)
        if best is None or score > best[0]:
            best = (score, cols, rows, pw, ph, ox, oy, rotated)
    if best is None:
        raise RuntimeError(f"cannot pack {item_w}x{item_h} on {plate}")
    _, cols, rows, pw, ph, ox, oy, _ = best
    return cols, rows, pw, ph, ox, oy


def build_jig(
    key: str,
    title: str,
    bed: str,
    item: str,
    plate: tuple[float, float],
    size: tuple[float, float, float],
    notes: list[str],
) -> Jig:
    w, h, z = size
    min_outer = STD_MIN_OUTER if bed == "standard" else WALL
    cols, rows, pw, ph, ox, oy = pack(plate, w, h, min_outer=min_outer)
    if item.startswith("mag"):
        wall_z = max(2.4, z - MAGNET_PROUD)  # 7.5 mm blank sits ~1.5 mm proud
        depth = wall_z
    else:
        # RAM thickness varies 4-9 mm. Keep walls at 2.4 mm so a thin stick still sits proud.
        wall_z = 2.4
        depth = wall_z
    pockets = []
    for r in range(rows):
        for c in range(cols):
            x = ox + c * (pw + WALL)
            y = oy + r * (ph + WALL)
            pockets.append(Pocket(x, y, pw, ph, depth))
    cols_n, rows_n = cols, rows
    notes = list(notes) + [
        f"{cols_n} x {rows_n} = {cols_n * rows_n} pockets",
        f"Pocket {pw:.2f} x {ph:.2f} mm (item {w} x {h} + {CLEAR * 2:.2f} mm clearance)",
        f"Walls {wall_z:.2f} mm; item sits proud of the walls",
        f"Plate {plate[0]:.0f} x {plate[1]:.0f} x {BASE + wall_z:.1f} mm",
        "Print on Bambu Lab H2D, PETG, 0.2 mm layers, 3 perimeters",
        "Sits on the OEM adhesive mat. Item print-face up. Walls stay below the print surface.",
    ]
    return Jig(key, title, bed, item, plate, size, pockets, wall_z, notes)


def all_jigs() -> list[Jig]:
    mini_note = "Mini E1 bed printable 330 x 90 mm. Plate leaves ~6 mm X and ~2 mm Y margin."
    std_note = (
        "Standard E1 bed printable 420 x 330 mm. This 308 x 308 mm plate is the camera-"
        "friendly centre trimmed 10 mm in X and Y to fit an H2D bed."
    )
    return [
        build_jig(
            "mini-mag-50x70",
            "Mini bed — 50 x 70 mm ceramic magnets",
            "mini",
            "mag50",
            MINI_PLATE,
            MAG_5070,
            [mini_note, "Official eufy blank V72W0022. Thickness 7.5 mm (3DJake). Measure one stick before a production run."],
        ),
        build_jig(
            "mini-mag-57x57",
            "Mini bed — 57 x 57 mm ceramic magnets",
            "mini",
            "mag57",
            MINI_PLATE,
            MAG_5757,
            [mini_note, "Official eufy blank V72W0023. Thickness 7.5 mm (3DJake). Measure one stick before a production run."],
        ),
        build_jig(
            "mini-pc100",
            "Mini bed — PC100 168-pin DIMM",
            "mini",
            "pc100",
            MINI_PLATE,
            PC100,
            [
                mini_note,
                "JEDEC MO-161, 133.35 x 38.10 mm face, 38 mm max height.",
                "Gold-finger edge along the 133 mm side. Seat fingers toward the labelled strip.",
            ],
        ),
        build_jig(
            "mini-simm72",
            "Mini bed — 72-pin SIMM",
            "mini",
            "simm72",
            MINI_PLATE,
            SIMM72,
            [
                mini_note,
                "JEDEC MO-116, 107.95 x 25.40 mm face, 5.08 mm max thickness.",
                "Polarizing notch at one end. Measure a real module; some stacked SIMMs are taller.",
            ],
        ),
        build_jig(
            "std-mag-50x70",
            "Standard bed centre — 50 x 70 mm ceramic magnets",
            "standard",
            "mag50",
            STD_PLATE,
            MAG_5070,
            [std_note, "Official eufy blank V72W0022. Thickness 7.5 mm (3DJake)."],
        ),
        build_jig(
            "std-mag-57x57",
            "Standard bed centre — 57 x 57 mm ceramic magnets",
            "standard",
            "mag57",
            STD_PLATE,
            MAG_5757,
            [std_note, "Official eufy blank V72W0023. Thickness 7.5 mm (3DJake)."],
        ),
        build_jig(
            "std-pc100",
            "Standard bed centre — PC100 168-pin DIMM",
            "standard",
            "pc100",
            STD_PLATE,
            PC100,
            [std_note, "JEDEC MO-161, 133.35 x 38.10 mm face, 38 mm max height."],
        ),
        build_jig(
            "std-simm72",
            "Standard bed centre — 72-pin SIMM",
            "standard",
            "simm72",
            STD_PLATE,
            SIMM72,
            [std_note, "JEDEC MO-116, 107.95 x 25.40 mm face."],
        ),
    ]


def scad_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def write_scad(jig: Jig) -> Path:
    pw, ph = jig.plate
    pz = jig.plate_z
    pockets = ",\n".join(
        f"    [{p.x:.3f}, {p.y:.3f}, {p.w:.3f}, {p.h:.3f}, {p.depth:.3f}]" for p in jig.pockets
    )
    label = scad_escape(jig.title)
    key = scad_escape(jig.key)
    scad = f"""// Auto-generated by generate.py — do not edit by hand.
// {jig.title}
// Draft 1  |  Eufy E1 UV jig  |  Bambu Lab H2D

$fn = 28;

plate = [{pw:.3f}, {ph:.3f}, {pz:.3f}];
base_z = {BASE:.3f};
wall = {WALL:.3f};
corner_r = {CORNER_R:.3f};
pocket_r = {POCKET_R:.3f};
pick_r = {PICK_R:.3f};
label = "{label}";
part_key = "{key}";

pockets = [
{pockets}
];

module rounded_plate(s, r) {{
    hull() {{
        for (x = [r, s[0] - r])
            for (y = [r, s[1] - r])
                translate([x, y, 0])
                    cylinder(h = s[2], r = r);
    }}
}}

module rounded_slot(w, h, d, r) {{
    rr = min(r, w / 2 - 0.05, h / 2 - 0.05);
    hull() {{
        for (x = [rr, w - rr])
            for (y = [rr, h - rr])
                translate([x, y, 0])
                    cylinder(h = d, r = rr);
    }}
}}

module pick_notches(w, h, d) {{
    // Vertical scoop from the top of the wall, stopping 1 mm above the pocket floor.
    if (w >= h) {{
        translate([w / 2, 0, 1.0]) cylinder(h = d + 0.4, r = pick_r);
        translate([w / 2, h, 1.0]) cylinder(h = d + 0.4, r = pick_r);
    }} else {{
        translate([0, h / 2, 1.0]) cylinder(h = d + 0.4, r = pick_r);
        translate([w, h / 2, 1.0]) cylinder(h = d + 0.4, r = pick_r);
    }}
}}

module jig() {{
    difference() {{
        rounded_plate(plate, corner_r);
        for (p = pockets) {{
            translate([p[0], p[1], base_z]) {{
                rounded_slot(p[2], p[3], p[4] + 0.3, pocket_r);
                pick_notches(p[2], p[3], p[4]);
            }}
        }}
        // Recessed label, top-left unused margin if any, else on the base rim.
        translate([6, plate[1] - 7, plate[2] - 0.6])
            linear_extrude(1)
                text(label, size = 4.2, font = "Arial:style=Bold", valign = "top");
        translate([6, 4.5, plate[2] - 0.6])
            linear_extrude(1)
                text(str(part_key, "  DRAFT 1  LOCK ->"), size = 3.2, font = "Arial", valign = "center");
    }}
}}

jig();
"""
    path = ROOT / f"{jig.key}.scad"
    path.write_text(scad, encoding="utf-8")
    return path


def openscad_bin() -> Path:
    for candidate in (
        Path(r"C:\Program Files\OpenSCAD\openscad.com"),
        Path(r"C:\Program Files\OpenSCAD\openscad.exe"),
        Path(r"C:\Program Files\OpenSCAD Nightly\openscad.com"),
    ):
        if candidate.exists():
            return candidate
    found = shutil.which("openscad")
    if found:
        return Path(found)
    raise FileNotFoundError("OpenSCAD not found; install it to export STL")


def write_stl(jig: Jig, scad_path: Path) -> Path:
    out = STL / f"{jig.key}.stl"
    cmd = [
        str(openscad_bin()),
        "--export-format",
        "binstl",
        "-o",
        str(out),
        str(scad_path),
    ]
    subprocess.run(cmd, check=True)
    if not out.is_file() or out.stat().st_size < 84:
        raise RuntimeError(f"OpenSCAD wrote no STL for {jig.key}")
    return out


def arrow(x1: float, y1: float, x2: float, y2: float) -> str:
    return (
        f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" />'
        f'<polygon points="{x2:.2f},{y2:.2f} {x2 - 1.6:.2f},{y2 - 0.7:.2f} {x2 - 1.6:.2f},{y2 + 0.7:.2f}" />'
        if abs(x2 - x1) > abs(y2 - y1)
        else f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" />'
    )


def dim_h(x1: float, x2: float, y: float, label: str, flip: bool = False) -> str:
    xa, xb = (x1, x2) if x1 < x2 else (x2, x1)
    mid = (xa + xb) / 2
    ty = y - 2.2 if flip else y + 3.4
    return f"""
    <g class="dim">
      <line x1="{xa:.2f}" y1="{y:.2f}" x2="{xb:.2f}" y2="{y:.2f}" />
      <line x1="{xa:.2f}" y1="{y - 1.5:.2f}" x2="{xa:.2f}" y2="{y + 1.5:.2f}" />
      <line x1="{xb:.2f}" y1="{y - 1.5:.2f}" x2="{xb:.2f}" y2="{y + 1.5:.2f}" />
      <text x="{mid:.2f}" y="{ty:.2f}" text-anchor="middle">{label}</text>
    </g>"""


def dim_v(y1: float, y2: float, x: float, label: str, flip: bool = False) -> str:
    ya, yb = (y1, y2) if y1 < y2 else (y2, y1)
    mid = (ya + yb) / 2
    tx = x - 2.4 if flip else x + 2.4
    anchor = "end" if flip else "start"
    return f"""
    <g class="dim">
      <line x1="{x:.2f}" y1="{ya:.2f}" x2="{x:.2f}" y2="{yb:.2f}" />
      <line x1="{x - 1.5:.2f}" y1="{ya:.2f}" x2="{x + 1.5:.2f}" y2="{ya:.2f}" />
      <line x1="{x - 1.5:.2f}" y1="{yb:.2f}" x2="{x + 1.5:.2f}" y2="{yb:.2f}" />
      <text x="{tx:.2f}" y="{mid:.2f}" text-anchor="{anchor}" dominant-baseline="middle">{label}</text>
    </g>"""


def write_svg(jig: Jig) -> Path:
    pw, ph = jig.plate
    p0 = jig.pockets[0]
    cols, rows = jig.cols_rows
    pad = 28
    title_h = 36
    note_h = 52
    vb_w = pw + pad * 2
    vb_h = ph + pad * 2 + title_h + note_h
    ox, oy = pad, pad + title_h
    # SVG Y-down: flip jig Y so origin matches CAD (Y up, label at top of plate)
    def jx(x: float) -> float:
        return ox + x

    def jy(y: float) -> float:
        return oy + (ph - y)

    pockets_svg = []
    for p in jig.pockets:
        x = jx(p.x)
        y = jy(p.y + p.h)
        pockets_svg.append(
            f'<rect class="pocket" x="{x:.2f}" y="{y:.2f}" width="{p.w:.2f}" height="{p.h:.2f}" rx="{POCKET_R}" />'
        )
        # pick marks
        if p.w >= p.h:
            pockets_svg.append(
                f'<circle class="pick" cx="{x + p.w / 2:.2f}" cy="{y:.2f}" r="2.2" />'
                f'<circle class="pick" cx="{x + p.w / 2:.2f}" cy="{y + p.h:.2f}" r="2.2" />'
            )
        else:
            pockets_svg.append(
                f'<circle class="pick" cx="{x:.2f}" cy="{y + p.h / 2:.2f}" r="2.2" />'
                f'<circle class="pick" cx="{x + p.w:.2f}" cy="{y + p.h / 2:.2f}" r="2.2" />'
            )

    notes = "  |  ".join(jig.notes[:4])
    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vb_w:.2f} {vb_h:.2f}"
     width="{vb_w * 3:.0f}" height="{vb_h * 3:.0f}">
  <style>
    text {{ font-family: Segoe UI, Arial, sans-serif; fill: #111; }}
    .title {{ font-size: 7px; font-weight: 700; }}
    .sub {{ font-size: 4px; fill: #333; }}
    .dim text {{ font-size: 3.2px; fill: #1a1a1a; }}
    .dim line {{ stroke: #222; stroke-width: 0.25; }}
    .plate {{ fill: #f4f1e8; stroke: #111; stroke-width: 0.6; }}
    .pocket {{ fill: #fff; stroke: #111; stroke-width: 0.35; }}
    .pick {{ fill: none; stroke: #666; stroke-width: 0.2; stroke-dasharray: 0.8 0.6; }}
    .note {{ font-size: 3.3px; fill: #222; }}
    .block {{ fill: #fff; stroke: #111; stroke-width: 0.4; }}
  </style>
  <rect class="block" x="0.4" y="0.4" width="{vb_w - 0.8:.2f}" height="{vb_h - 0.8:.2f}"/>
  <text class="title" x="{pad}" y="12">{jig.title}</text>
  <text class="sub" x="{pad}" y="19">Eufy E1 UV hold-down  ·  Draft 1  ·  {jig.key}.scad  ·  units mm  ·  scale 1:1 in viewBox</text>
  <text class="sub" x="{pad}" y="25">Bambu Lab H2D  ·  PETG  ·  sits on OEM adhesive mat  ·  LOCK edge →</text>

  <rect class="plate" x="{ox:.2f}" y="{oy:.2f}" width="{pw:.2f}" height="{ph:.2f}" rx="{CORNER_R}"/>
  {''.join(pockets_svg)}

  {dim_h(ox, ox + pw, oy + ph + 8, f"{pw:.0f}")}
  {dim_v(oy, oy + ph, ox - 8, f"{ph:.0f}", flip=True)}
  {dim_h(jx(p0.x), jx(p0.x + p0.w), jy(p0.y + p0.h) - 6, f"{p0.w:.2f}", flip=True)}
  {dim_v(jy(p0.y + p0.h), jy(p0.y), jx(p0.x + p0.w) + 6, f"{p0.h:.2f}")}

  <text class="note" x="{pad}" y="{oy + ph + pad + 8}">{notes}</text>
  <text class="note" x="{pad}" y="{oy + ph + pad + 14}">{jig.notes[4] if len(jig.notes) > 4 else ""}</text>
  <text class="note" x="{pad}" y="{oy + ph + pad + 20}">{jig.notes[5] if len(jig.notes) > 5 else ""}  ·  {cols} cols × {rows} rows  ·  plate Z {jig.plate_z:.1f} mm  ·  pocket depth {p0.depth:.1f} mm</text>
  <text class="note" x="{vb_w - pad}" y="{oy + ph + pad + 20}" text-anchor="end">LOCK →</text>
</svg>
"""
    path = DRAW / f"{jig.key}.svg"
    path.write_text(svg, encoding="utf-8")
    return path


def write_html(jigs: list[Jig], svgs: list[Path]) -> Path:
    cards = []
    for jig, svg in zip(jigs, svgs):
        rel = svg.name
        cols, rows = jig.cols_rows
        cards.append(
            f"""
<section>
  <h2>{jig.title}</h2>
  <p class="meta">{jig.key}.scad · {cols}×{rows} = {len(jig.pockets)} pockets ·
     plate {jig.plate[0]:.0f}×{jig.plate[1]:.0f}×{jig.plate_z:.1f} mm ·
     pocket {jig.pockets[0].w:.2f}×{jig.pockets[0].h:.2f}×{jig.pockets[0].depth:.1f} mm</p>
  <object type="image/svg+xml" data="{rel}" class="dwg"></object>
</section>"""
        )
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Eufy E1 hold-down templates — Draft 1</title>
<style>
  body {{ font-family: Segoe UI, Arial, sans-serif; margin: 24px; background: #ececec; color: #111; }}
  h1 {{ font-size: 22px; margin: 0 0 6px; }}
  .lead {{ color: #333; max-width: 900px; }}
  section {{ background: #fff; border: 1px solid #bbb; margin: 18px 0; padding: 12px 12px 4px; }}
  h2 {{ font-size: 16px; margin: 0 0 4px; }}
  .meta {{ font-size: 12px; color: #444; margin: 0 0 8px; }}
  .dwg {{ width: 100%; height: 520px; }}
  ul {{ max-width: 900px; }}
</style>
</head>
<body>
<h1>Eufy E1 UV hold-down templates — Draft 1</h1>
<p class="lead">Eight plates. Mini bed is 318×86 mm (fits the 330×90 printable area and an H2D).
Standard bed is a 308×308 mm centre plate (318 trimmed 10 mm in X and Y so it fits the H2D).
Sits on the OEM sticky mat. Item print-face up. Walls sit below the print surface.
Print PETG, 0.2 mm layers, 3 perimeters. Measure one real blank before a production run.</p>
<ul>
  <li>Magnets: 50×70×7.5 mm (V72W0022) and 57×57×7.5 mm (V72W0023)</li>
  <li>PC100 DIMM: 133.35×38.10 mm face, 38 mm max height, 168-pin</li>
  <li>72-pin SIMM: 107.95×25.40 mm face, 5.08 mm max thickness</li>
</ul>
{''.join(cards)}
</body>
</html>
"""
    path = DRAW / "index.html"
    path.write_text(html, encoding="utf-8")
    return path


def main() -> None:
    DRAW.mkdir(parents=True, exist_ok=True)
    STL.mkdir(parents=True, exist_ok=True)
    PNG.mkdir(parents=True, exist_ok=True)
    jigs = all_jigs()
    svgs = []
    scad_by_key = {}
    for jig in jigs:
        sp = write_scad(jig)
        vp = write_svg(jig)
        svgs.append(vp)
        scad_by_key[jig.key] = sp
        cols, rows = jig.cols_rows
        print(
            f"{jig.key:18}  {cols}x{rows}={len(jig.pockets):2}  "
            f"plate {jig.plate[0]:.0f}x{jig.plate[1]:.0f}x{jig.plate_z:.1f}  "
            f"pocket {jig.pockets[0].w:.2f}x{jig.pockets[0].h:.2f}x{jig.pockets[0].depth:.1f}  "
            f"{sp.name}  {vp.name}"
        )
    html = write_html(jigs, svgs)
    print(f"index {html}")
    with ThreadPoolExecutor(max_workers=3) as pool:
        futs = {pool.submit(write_stl, jig, scad_by_key[jig.key]): jig for jig in jigs}
        for fut in as_completed(futs):
            jig = futs[fut]
            stl = fut.result()
            print(f"stl {jig.key:18}  {stl}  {stl.stat().st_size}")


if __name__ == "__main__":
    main()
