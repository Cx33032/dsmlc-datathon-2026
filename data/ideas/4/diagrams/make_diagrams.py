"""Idea 4 diagrams (dark editorial style): system architecture, what Canary is, team plan.

Run:  python data/ideas/4/diagrams/make_diagrams.py
Writes docs/ideas/4/diagrams/<name>.html (page with fonts) and <name>.svg (for embedding in Markdown).
Rules followed: orthogonal connectors only, arrow labels on opaque masks 8 px from their line,
arrows drawn before boxes, at most 2 accent elements per diagram, legend as a bottom strip,
accessible <title>/<desc>. A geometry check at the end fails if two nodes overlap or anything
falls outside the viewBox.
"""
from pathlib import Path
import html

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "docs" / "ideas" / "4" / "diagrams"
OUT.mkdir(parents=True, exist_ok=True)

T = dict(paper="#16181d", paper2="#1e2128", ink="#e8e6e1", muted="#9aa0a6", soft="#6b7280",
         rule="#2e323b", accent="#e0623a", accent_tint="rgba(224,98,58,0.14)", link="#6aa9d8",
         link_tint="rgba(106,169,216,0.10)")
SANS = "Geist, 'Segoe UI', Arial, sans-serif"
MONO = "'Geist Mono', Consolas, 'Courier New', monospace"
SERIF = "'Instrument Serif', Georgia, serif"
esc = html.escape


class D:
    def __init__(self, slug, w, h, title, desc, top=0):
        self.slug, self.w, self.h, self.title, self.desc, self.top = slug, w, h, title, desc, top
        self.edges, self.nodes, self.extra, self.boxes = [], [], [], []

    # ---------------- connectors (drawn first)
    def _label_h(self, x_mid, y, text, color):
        w = 5.8 * len(text) + 12
        self.edges.append(f'<rect x="{x_mid - w / 2:.1f}" y="{y - 8 - 16}" width="{w:.1f}" height="16" fill="{T["paper"]}"/>'
                          f'<text x="{x_mid:.1f}" y="{y - 8 - 4.5}" text-anchor="middle" font-family="{MONO}" font-size="9.5" '
                          f'letter-spacing="0.6" fill="{color}">{esc(text)}</text>')

    def _label_v(self, x, y_mid, text, color):
        w = 5.8 * len(text) + 12
        self.edges.append(f'<rect x="{x + 8}" y="{y_mid - 8}" width="{w:.1f}" height="16" fill="{T["paper"]}"/>'
                          f'<text x="{x + 8 + 6}" y="{y_mid + 3.5}" font-family="{MONO}" font-size="9.5" '
                          f'letter-spacing="0.6" fill="{color}">{esc(text)}</text>')

    def hline(self, x0, x1, y, label=None, kind="muted", dashed=False):
        color = T[kind] if kind != "muted" else T["muted"]
        marker = {"accent": "arrow-accent", "link": "arrow-link"}.get(kind, "arrow")
        dash = ' stroke-dasharray="5,4"' if dashed else ""
        self.edges.append(f'<line x1="{x0}" y1="{y}" x2="{x1 - 2}" y2="{y}" stroke="{color}" stroke-width="{1.6 if kind == "accent" else 1.2}"{dash} marker-end="url(#{marker})"/>')
        if label:
            self._label_h((x0 + x1) / 2, y, label, color)

    def vline(self, x, y0, y1, label=None, kind="muted", dashed=False):
        color = T[kind] if kind != "muted" else T["muted"]
        marker = {"accent": "arrow-accent", "link": "arrow-link"}.get(kind, "arrow")
        dash = ' stroke-dasharray="5,4"' if dashed else ""
        end = y1 - 2 if y1 > y0 else y1 + 2
        self.edges.append(f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{end}" stroke="{color}" stroke-width="1.2"{dash} marker-end="url(#{marker})"/>')
        if label:
            self._label_v(x, (y0 + y1) / 2, label, color)

    # ---------------- shapes
    def zone(self, x, y, w, h, label):
        self.extra.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="none" stroke="{T["rule"]}" stroke-dasharray="4,4"/>'
                          f'<text x="{x + 14}" y="{y + 20}" font-family="{MONO}" font-size="10" letter-spacing="1.2" fill="{T["soft"]}">{esc(label)}</text>')

    def node(self, x, y, w, h, name, sub, kind="plain", tag=None, name_size=14):
        fill, stroke = {"plain": (T["paper2"], T["muted"]), "accent": (T["accent_tint"], T["accent"]),
                        "store": (T["link_tint"], T["link"]), "hw": (T["paper2"], T["ink"]),
                        "ghost": (T["paper"], T["soft"])}[kind]
        dash = ' stroke-dasharray="4,3"' if kind == "ghost" else ""
        s = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{T["paper"]}"/>'
        s += f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" stroke="{stroke}" stroke-width="1.2"{dash}/>'
        ty = y + h / 2 - (6 if sub else -5)
        if tag:
            tw = 6.2 * len(tag) + 10
            s += (f'<rect x="{x + w - tw - 8}" y="{y + 8}" width="{tw:.1f}" height="15" rx="2" fill="none" stroke="{stroke}" stroke-width="0.8"/>'
                  f'<text x="{x + w - tw / 2 - 8:.1f}" y="{y + 19}" text-anchor="middle" font-family="{MONO}" font-size="8.5" fill="{stroke}">{esc(tag)}</text>')
            ty += 6
        s += f'<text x="{x + 14}" y="{ty}" font-family="{SANS}" font-weight="600" font-size="{name_size}" fill="{T["ink"]}">{esc(name)}</text>'
        if sub:
            s += f'<text x="{x + 14}" y="{ty + 18}" font-family="{MONO}" font-size="10" fill="{T["muted"]}">{esc(sub)}</text>'
        self.nodes.append(s)
        self.boxes.append((x, y, w, h, name))

    def text(self, x, y, s, size=11, color=None, font=None, anchor="start", weight="400", italic=False):
        st = ' font-style="italic"' if italic else ""
        self.extra.append(f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="{font or SANS}" font-size="{size}" '
                          f'font-weight="{weight}"{st} fill="{color or T["muted"]}">{esc(s)}</text>')

    def raw(self, s):
        self.extra.append(s)

    def under(self, s):
        self.edges.append(s)

    def legend(self, items, y):
        x = 32
        parts = [f'<line x1="24" y1="{y - 18}" x2="{self.w - 24}" y2="{y - 18}" stroke="{T["rule"]}"/>']
        for kind, label in items:
            if kind.startswith("line"):
                color = {"line": T["muted"], "line-accent": T["accent"], "line-link": T["link"]}[kind.split(":")[0]]
                dash = ' stroke-dasharray="5,4"' if kind.endswith(":dash") else ""
                parts.append(f'<line x1="{x}" y1="{y}" x2="{x + 26}" y2="{y}" stroke="{color}" stroke-width="1.4"{dash}/>')
            else:
                fill, stroke = {"hw": (T["paper2"], T["ink"]), "plain": (T["paper2"], T["muted"]),
                                "store": (T["link_tint"], T["link"]), "accent": (T["accent_tint"], T["accent"]),
                                "ghost": (T["paper"], T["soft"])}[kind]
                dash = ' stroke-dasharray="4,3"' if kind == "ghost" else ""
                parts.append(f'<rect x="{x}" y="{y - 7}" width="26" height="14" rx="3" fill="{fill}" stroke="{stroke}"{dash}/>')
            parts.append(f'<text x="{x + 34}" y="{y + 4}" font-family="{MONO}" font-size="10" fill="{T["muted"]}">{esc(label)}</text>')
            x += 34 + 6.2 * len(label) + 28
        self.extra.append("".join(parts))

    # ---------------- output
    def svg(self, standalone=False):
        defs = "".join(
            f'<marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{col}"/></marker>'
            for mid, col in [("arrow", T["muted"]), ("arrow-accent", T["accent"]), ("arrow-link", T["link"])])
        ns = ' xmlns="http://www.w3.org/2000/svg"' if standalone else ""
        vh = self.h - self.top
        body = (f'<rect y="{self.top}" width="{self.w}" height="{vh}" fill="{T["paper"]}"/>' + "".join(self.extra[:1])
                + "".join(self.edges) + "".join(self.nodes) + "".join(self.extra[1:]))
        return (f'<svg{ns} viewBox="0 {self.top} {self.w} {vh}" width="{self.w}" height="{vh}" role="img" '
                f'aria-labelledby="{self.slug}-title {self.slug}-desc">'
                f'<title id="{self.slug}-title">{esc(self.title)}</title><desc id="{self.slug}-desc">{esc(self.desc)}</desc>'
                f'<defs>{defs}</defs>{body}</svg>')

    def check(self):
        for i, (x, y, w, h, n) in enumerate(self.boxes):
            assert x >= 0 and y >= self.top and x + w <= self.w and y + h <= self.h, f"{self.slug}: {n} outside viewBox"
            for (x2, y2, w2, h2, n2) in self.boxes[i + 1:]:
                assert x + w <= x2 or x2 + w2 <= x or y + h <= y2 or y2 + h2 <= y, f"{self.slug}: {n} overlaps {n2}"

    def write(self, eyebrow, h1, note):
        self.check()
        page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(h1)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;600&family=Geist+Mono:wght@400&family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet">
<style>body{{margin:0;background:{T['paper']};color:{T['ink']};font-family:{SANS}}}
main{{max-width:{self.w + 48}px;margin:0 auto;padding:32px 24px}}
.eyebrow{{font-family:{MONO};font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:{T['soft']}}}
h1{{font-family:{SERIF};font-weight:400;font-size:40px;margin:6px 0 8px}}
p.note{{color:{T['muted']};max-width:760px;line-height:1.5;margin:0 0 20px}}
.scroll{{overflow-x:auto}} .scroll svg{{min-width:{self.w}px;display:block}}</style></head>
<body><main><div class="eyebrow">{esc(eyebrow)}</div><h1>{esc(h1)}</h1><p class="note">{esc(note)}</p>
<div class="scroll">{self.svg()}</div></main></body></html>"""
        (OUT / f"{self.slug}.html").write_text(page, encoding="utf-8")
        (OUT / f"{self.slug}.svg").write_text(self.svg(standalone=True), encoding="utf-8")
        print("wrote", self.slug)


# =============================================================== 1. system architecture
W, NW, NH = 1304, 168, 72
xs = [32, 300, 568, 836, 1104]
A, B, C = 168, 312, 456
d = D("idea4-architecture", W, 640, "Idea 4 system: rig to Canary to screens",
      "A bench rig is driven by an Arduino, sensed by an nRF52 DK that runs the fatigue odometer, sent over BLE to a "
      "laptop gateway, stored in Canary Historian, turned into alarms by Calcs and Events, and shown on an Axiom board; "
      "datathon results feed a separate engineer console.", top=108)
d.zone(16, 124, 752, 136, "BENCH HARDWARE")          # first extra = drawn under everything
d.zone(1088, 124, 200, 424, "CANARY  (WINDOWS PC)")
mid = A + NH / 2
d.hline(xs[0] + NW, xs[1], mid, "PWM + SERVO")
d.hline(xs[1] + NW, xs[2], mid, "MOTOR CURRENT")
d.hline(xs[2] + NW, xs[3], mid, "BLE 20 B/MIN", kind="accent")
d.hline(xs[3] + NW, xs[4], mid, "WRITE API", kind="link")
d.vline(xs[4] + NW / 2, A + NH, B, "TAGS")
d.vline(xs[4] + NW / 2, B + NH, C, "EVENTS")
d.hline(xs[1] + NW, xs[2], C + NH / 2, "CSV")
d.node(xs[0], A, NW, NH, "Arduino UNO", "drive + scenarios", "hw", "KIT")
d.node(xs[1], A, NW, NH, "Tabletop well", "motor, rod, brake", "hw", "3D PRINT")
d.node(xs[2], A, NW, NH, "nRF52 DK", "odometer + model", "accent", "EDGE AI")
d.node(xs[3], A, NW, NH, "Laptop gateway", "python + bleak", "plain")
d.node(xs[4], A, NW, NH, "Historian", "store + forward", "store")
d.node(xs[4], B, NW, NH, "Calcs & Events", "damage, alarms", "store")
d.node(xs[4], C, NW, NH, "Axiom board", "operator screen", "store")
d.node(xs[1], C, NW, NH, "Datathon results", "ideas 1 + 5 tables", "ghost")
d.node(xs[2], C, NW, NH, "Engineer console", "FastAPI + Streamlit", "plain")
d.text(xs[2], C + NH + 34, "Engineers decide which well gets a new rod string.", 12, T["muted"], SERIF, italic=True)
d.text(xs[4] - 148, C + NH + 34, "Operators see alarms live.", 12, T["muted"], SERIF, italic=True)
d.legend([("hw", "hardware"), ("plain", "our software"), ("store", "Canary software"), ("ghost", "files we already have"),
          ("accent", "focus: runs on the chip"), ("line-link", "HTTP / API")], 608)
d.write("Idea 4 . how it fits together", "From a spinning rod to an alarm on a screen",
        "Read left to right along the top row: the Arduino drives the rig, the nRF52 DK measures the motor current and runs "
        "the fatigue odometer on the chip, then sends one small summary per minute. The laptop writes it into Canary. "
        "Canary stores it, raises alarms, and shows them on an Axiom board.")

# =============================================================== 2. what Canary is (layer stack)
W2 = 1080
d = D("idea4-canary-stack", W2, 700, "What Canary is: five software layers",
      "Canary is a set of Windows programs: Store and Forward receives values, Historian stores them as tags, Calcs and "
      "Events derives new tags and alarms, Views serves data out, and Axiom shows dashboards. Sensors and devices are not part of Canary.", top=80)
d.raw("")   # keep first-extra slot empty (no zone)
bands = [
    ("Axiom", "web dashboards + trends", "plain", "Operator board: live current, damage index, regime, event table, chronic-well list"),
    ("Views", "the one door for reading data", "plain", "Axiom, Excel add-in, ODBC and our Streamlit console read through it"),
    ("Calcs & Events", "new tags + alarms from old tags", "accent", "damage rate = change in DamageIndex per hour; event 'stick-slip for 10+ min'"),
    ("Historian", "tag database: time, value, quality", "store", "Tags such as Rig.Current_mean, Rig.DamageIndex, Rig.Regime"),
    ("Store & Forward + Write API", "receives values, buffers if offline", "store", "Our laptop gateway posts each BLE summary here"),
    ("Data sources (not Canary)", "sensors, PLCs, devices, scripts", "ghost", "Our nRF52 DK + laptop gateway. In industry: SCADA, PLCs, OPC, MQTT"),
]
x0, bw, bh, gap, y0 = 96, 900, 76, 14, 112
d.text(x0, y0 - 18, "LAYER", 10, T["soft"], MONO)
d.text(x0 + 430, y0 - 18, "IN OUR PROJECT", 10, T["soft"], MONO)
for i, (name, sub, kind, ours) in enumerate(bands):
    y = y0 + i * (bh + gap)
    d.node(x0, y, bw, bh, name, sub, kind, "OURS" if kind == "ghost" else ("CANARY" if i < 5 else None))
    d.text(x0 + 430, y + bh / 2 + 4, ours, 11.5, T["ink"] if kind != "ghost" else T["muted"])
d.vline(56, y0 + 5 * (bh + gap) + bh, y0, None)
d.text(40, y0 + 2.5 * (bh + gap) + 6, "DATA", 10, T["soft"], MONO, anchor="middle")
d.text(40, y0 + 2.5 * (bh + gap) + 20, "UP", 10, T["soft"], MONO, anchor="middle")
d.legend([("plain", "Canary: show + serve"), ("store", "Canary: receive + store"), ("accent", "focus: where alarms are made"),
          ("ghost", "not Canary (our code / devices)")], 668)
d.write("Idea 4 . background", "What Canary is (and what it is not)",
        "Canary is software only. It runs on a Windows PC and has no sensors. Devices and scripts send it values; "
        "it stores each value with a time and a quality flag, calculates new values and alarms from them, and shows them on dashboards.")

# =============================================================== 3. team plan (Gantt by person)
W3 = 1340
d = D("idea4-team-plan", W3, 620, "Idea 4 team plan for four people",
      "Four lanes, one per person (hardware, firmware and BLE, data and Canary, app and story), across Saturday 09:00 to "
      "Sunday 12:00, with two shared milestones: the BLE packet contract at 10:00 and the first live tag in Canary at 18:00.", top=104)
d.raw("")
lanes = [("P1  Hardware", "print, wire, run rig"), ("P2  Firmware + BLE", "nRF52 DK code"),
         ("P3  Data + Canary", "gateway, tags, model"), ("P4  App + story", "console, slides, video")]
cols = [("SAT 09-13", 9, 13), ("SAT 13-18", 13, 18), ("SAT 18-23", 18, 23), ("SLEEP", 23, 31), ("SUN 07-12", 31, 36)]
tx0, px = 260, 46.0                      # x of 09:00, pixels per hour (sleep block squeezed below)
def hx(h):
    if h <= 23:
        return tx0 + (h - 9) * px
    if h <= 31:
        return tx0 + 14 * px + (h - 23) * 8
    return tx0 + 14 * px + 64 + (h - 31) * px
tasks = [
    ["Print + assemble rig", "Wire shunt + servo", "Uno scenarios, record", "Film the rig demo"],
    ["DK blinky, ADC read", "BLE packet sends", "Port odometer + tree", "Fix bugs, freeze"],
    ["Install Canary, tags", "Gateway BLE to Canary", "Train model, events", "Axiom board, video"],
    ["Well cards (ideas 1+5)", "Streamlit console", "Slides draft", "Video, README, submit"],
]
ly0, lh = 132, 96
for c, (lab, h0, h1) in enumerate(cols):
    d.text((hx(h0) + hx(h1)) / 2, ly0 - 14, lab, 10, T["soft"], MONO, anchor="middle")
    d.raw(f'<line x1="{hx(h0)}" y1="{ly0 - 6}" x2="{hx(h0)}" y2="{ly0 + 4 * lh}" stroke="{T["rule"]}"/>')
d.raw(f'<line x1="{hx(36)}" y1="{ly0 - 6}" x2="{hx(36)}" y2="{ly0 + 4 * lh}" stroke="{T["rule"]}"/>')
d.raw(f'<rect x="{hx(23)}" y="{ly0}" width="{hx(31) - hx(23)}" height="{4 * lh}" fill="{T["paper2"]}" opacity="0.6"/>')
for i, (lname, lsub) in enumerate(lanes):
    y = ly0 + i * lh
    d.raw(f'<line x1="24" y1="{y + lh}" x2="{W3 - 24}" y2="{y + lh}" stroke="{T["rule"]}"/>')
    d.text(32, y + 44, lname, 14, T["ink"], SANS, weight="600")
    d.text(32, y + 62, lsub, 10, T["muted"], MONO)
    spans = [(9, 13), (13, 18), (18, 23), (31, 36)]
    for (h0, h1), t in zip(spans, tasks[i]):
        d.node(int(hx(h0) + 4), y + 20, int(hx(h1) - hx(h0) - 8), 56, t, None, "plain", name_size=12.5)
# milestones (accent, 2 only)
for h, lab, yoff in [(10, "10:00  PACKET CONTRACT AGREED", 0), (18, "18:00  FIRST LIVE TAG IN CANARY", 0)]:
    x = hx(h)
    d.under(f'<line x1="{x}" y1="{ly0 - 4}" x2="{x}" y2="{ly0 + 4 * lh + 14}" stroke="{T["accent"]}" stroke-width="1.4" stroke-dasharray="5,4"/>')
    d.raw(f'<path d="M{x},{ly0 + 4 * lh + 12} l7,7 l-7,7 l-7,-7 z" fill="{T["accent"]}"/>')
    d.text(x + 12, ly0 + 4 * lh + 24, lab, 10, T["accent"], MONO)
d.text(hx(31) + 14, ly0 + 4 * lh + 24, "07:00  GO / NO-GO ON HARDWARE", 10, T["ink"], MONO)
d.raw(f'<path d="M{hx(31)},{ly0 + 4 * lh + 12} l7,7 l-7,7 l-7,-7 z" fill="none" stroke="{T["ink"]}"/>')
d.legend([("plain", "task block"), ("line-accent:dash", "shared milestone (whole team)")], 588)
d.write("Idea 4 . who does what", "Four people, four lanes, two handshakes",
        "Each person owns one lane end to end. The lanes only meet at two milestones: the BLE packet format (agreed in the "
        "first hour, so firmware and gateway can be built in parallel) and the first value that reaches Canary.")
