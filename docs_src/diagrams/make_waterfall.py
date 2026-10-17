"""Draws the classic Waterfall 'staircase' with the mid-semester status of each phase."""
phases = [("Feasibility Study", "Complete", "done"), ("Requirements Analysis (SRS)", "Complete", "done"),
          ("System Design", "Complete", "done"), ("Implementation", "~60% - in progress", "doing"),
          ("Testing", "Started - 20 tests", "doing"), ("Deployment", "Planned", "todo"), ("Maintenance", "Planned", "todo")]
colors = {"done": ("#dcfce7", "#15803d"), "doing": ("#fef3c7", "#b45309"), "todo": ("#f1f5f9", "#64748b")}
bw, bh, dx, dy = 260, 52, 105, 62
W, H = 40 + dx * (len(phases) - 1) + bw + 20, 30 + dy * (len(phases) - 1) + bh + 20
out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="Segoe UI, Arial, sans-serif">',
       '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
       '<path d="M0 0L10 5L0 10z" fill="#334155"/></marker></defs><rect width="100%" height="100%" fill="#fff"/>']
for i, (name, status, kind) in enumerate(phases):
    x, y = 20 + i * dx, 20 + i * dy
    fill, stroke = colors[kind]
    out.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
    out.append(f'<text x="{x + bw / 2}" y="{y + 22}" text-anchor="middle" font-size="15" font-weight="700" fill="#0f172a">{i + 1}. {name}</text>')
    out.append(f'<text x="{x + bw / 2}" y="{y + 41}" text-anchor="middle" font-size="12.5" fill="{stroke}">{status}</text>')
    if i < len(phases) - 1:
        out.append(f'<path d="M{x + bw} {y + bh / 2} H{x + dx + bw / 2} V{y + dy - 2}" fill="none" stroke="#334155" stroke-width="1.8" marker-end="url(#a)"/>')
out.append('</svg>')
open("waterfall.svg", "w").write("\n".join(out))
