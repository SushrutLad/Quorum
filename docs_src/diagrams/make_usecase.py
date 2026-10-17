"""Draws the use-case diagram as a clean SVG (Mermaid has no real use-case diagram)."""
W, H = 900, 760
cases = [
    ("UC-01", "Log in / Log out"), ("UC-02", "Register customer"), ("UC-03", "Create connection & meter"),
    ("UC-04", "Record meter reading"), ("UC-05", "Generate bill"), ("UC-08", "Record counter payment"),
    ("UC-10", "Resolve complaint"), ("UC-11", "Report / resolve outage"), ("UC-12", "Manage tariffs"),
    ("UC-13", "Manage employees"), ("UC-14", "View dashboard & reports"), ("UC-06", "View / print bill"),
    ("UC-07", "Pay bill online"), ("UC-09", "Raise complaint"), ("UC-15", "View usage & notifications"),
]
actors = {  # name: (x, y, use cases, side)
    "Employee": (90, 260, ["UC-01", "UC-02", "UC-03", "UC-04", "UC-08", "UC-10", "UC-11"], "L"),
    "Admin": (810, 230, ["UC-01", "UC-02", "UC-11", "UC-12", "UC-13", "UC-14"], "R"),
    "Customer": (810, 590, ["UC-01", "UC-06", "UC-07", "UC-09", "UC-15"], "R"),
}
box_x, box_w, top, gap = 250, 400, 70, 44
cx = box_x + box_w / 2
pos = {code: (cx, top + 30 + i * gap) for i, (code, _) in enumerate(cases)}
rx, ry = 150, 17

out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="Segoe UI, Arial, sans-serif" font-size="13">',
       '<rect width="100%" height="100%" fill="#fff"/>',
       f'<rect x="{box_x}" y="{top - 20}" width="{box_w}" height="{len(cases) * gap + 30}" rx="10" fill="#f8fafc" stroke="#64748b"/>',
       f'<text x="{cx}" y="{top - 30}" text-anchor="middle" font-weight="700" font-size="15">EUMS - Energy &amp; Utility Management System</text>']
for name, (x, y, ucs, side) in actors.items():
    for code in ucs:
        ux, uy = pos[code]
        ex = ux - rx if side == "L" else ux + rx
        out.append(f'<line x1="{x + (22 if side == "L" else -22)}" y1="{y}" x2="{ex}" y2="{uy}" stroke="#94a3b8"/>')
# include relationships
for a, b in [("UC-04", "UC-05"), ("UC-07", "UC-06")]:
    (x1, y1), (x2, y2) = pos[a], pos[b]
    out.append(f'<path d="M{x1 - rx} {y1} C {x1 - rx - 60} {y1}, {x2 - rx - 60} {y2}, {x2 - rx} {y2}" fill="none" stroke="#2563eb" stroke-dasharray="5 4" marker-end="url(#arr)"/>')
    out.append(f'<text x="{x1 - rx - 58}" y="{(y1 + y2) / 2 + 4}" text-anchor="end" fill="#2563eb" font-size="11">&lt;&lt;include&gt;&gt;</text>')
out.insert(1, '<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10z" fill="#2563eb"/></marker></defs>')
for code, text in cases:
    x, y = pos[code]
    out.append(f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" fill="#eff6ff" stroke="#2563eb"/>')
    out.append(f'<text x="{x}" y="{y + 4}" text-anchor="middle"><tspan font-weight="600">{code}</tspan> {text.replace("&", "&amp;")}</text>')
for name, (x, y, _, _) in actors.items():
    out.append(f'<g stroke="#0f172a" stroke-width="2" fill="none"><circle cx="{x}" cy="{y - 38}" r="11"/>'
               f'<line x1="{x}" y1="{y - 27}" x2="{x}" y2="{y + 5}"/><line x1="{x - 18}" y1="{y - 15}" x2="{x + 18}" y2="{y - 15}"/>'
               f'<line x1="{x}" y1="{y + 5}" x2="{x - 14}" y2="{y + 28}"/><line x1="{x}" y1="{y + 5}" x2="{x + 14}" y2="{y + 28}"/></g>')
    out.append(f'<text x="{x}" y="{y + 46}" text-anchor="middle" font-weight="700">{name}</text>')
out.append('</svg>')
open("usecase.svg", "w").write("\n".join(out))
