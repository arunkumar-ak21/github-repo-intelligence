"""
CI/CD Pipeline Report Generator — Advanced SPA Edition

Generates a fully self-contained, interactive HTML report featuring:
  • Sticky sidebar navigation
  • Animated stat counters
  • Three-tab layout: Overview | Pipeline | Security | Insights
  • SVG-based visual pipeline flow diagram
  • Radial security score rings with animation
  • Expandable findings with remediation tips
  • Live search across all pipelines
  • Print & JSON export buttons
  • Glassmorphism dark theme with Google Fonts
  • Fully responsive for all screen sizes
"""

import os
import json
from datetime import datetime


# ── Public API ────────────────────────────────────────────────────────────────

def generate_html_report(
    analyses: list,
    security_results: list,
    output_path: str = "pipeline_report.html",
) -> str:
    """
    Generate an advanced interactive HTML report.

    Args:
        analyses:         List of pipeline analysis dicts from analyzer.py.
        security_results: List of security result dicts from security_checker.py.
        output_path:      Output file path.

    Returns:
        Absolute path to the written report.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Aggregate stats ────────────────────────────────────────────────────
    valid = [a for a in analyses if "error" not in a]
    total_pipelines  = len(analyses)
    total_stages     = sum(len(a.get("stages", [])) for a in valid)
    total_jobs       = sum(len(a.get("jobs",   [])) for a in valid)
    total_steps      = sum(a.get("total_steps", 0)  for a in valid)
    avg_score        = (sum(s["score"] for s in security_results) // len(security_results)) if security_results else 0
    avg_grade        = _get_grade(avg_score)
    total_issues     = sum(s["issues_found"] for s in security_results)
    platforms        = list({a.get("platform", "Unknown") for a in valid})

    # ── Build HTML sections ────────────────────────────────────────────────
    pipeline_cards_html = ""
    for analysis in analyses:
        if "error" in analysis:
            pipeline_cards_html += _error_card(analysis)
        else:
            pipeline_cards_html += _pipeline_card(analysis)

    security_cards_html = ""
    for i, sec in enumerate(security_results):
        ana = analyses[i] if i < len(analyses) else {}
        security_cards_html += _security_card(sec, ana)

    insights_html = _build_insights_section(analyses)
    heatmap_html  = _build_heatmap(analyses, security_results)

    # ── JSON for export button ─────────────────────────────────────────────
    export_data = []
    for i, a in enumerate(analyses):
        entry = {k: v for k, v in a.items() if k not in ("raw_content",)}
        if i < len(security_results):
            entry["security"] = {
                k: v for k, v in security_results[i].items() if k != "categories"
            }
        export_data.append(entry)
    json_export = json.dumps(export_data, indent=2, default=str)

    html = _get_full_template().format(
        timestamp       = timestamp,
        total_pipelines = total_pipelines,
        total_stages    = total_stages,
        total_jobs      = total_jobs,
        total_steps     = total_steps,
        avg_score       = avg_score,
        avg_grade       = avg_grade,
        score_color     = _grade_color(avg_score),
        score_class     = "green" if avg_score >= 80 else "red" if avg_score < 60 else "",
        total_issues    = total_issues,
        issues_color    = "#ef4444" if total_issues > 0 else "#22c55e",
        issues_class    = "red" if total_issues > 0 else "green",
        platforms_str   = ", ".join(platforms) or "None",
        pipeline_cards  = pipeline_cards_html,
        security_cards  = security_cards_html,
        insights        = insights_html,
        heatmap         = heatmap_html,
        json_export     = json_export.replace("</script>", "<\\/script>"),
    )

    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return os.path.abspath(output_path)


# ── Card Builders ─────────────────────────────────────────────────────────────

def _pipeline_card(a: dict) -> str:
    platform  = a.get("platform", "Unknown")
    name      = a.get("name", "Unnamed")
    stages    = a.get("stages", [])
    jobs      = a.get("jobs", [])
    triggers  = a.get("triggers", [])
    env_vars  = a.get("env_vars", [])
    line_count = a.get("line_count", 0)
    file_name = os.path.basename(a.get("file", ""))
    icon      = _platform_icon(platform)

    features = _collect_features(a)

    # Stage flow
    stages_html = ""
    if stages:
        items = []
        for i, s in enumerate(stages):
            items.append(f'<div class="stage-node">{_escape(s)}</div>')
            if i < len(stages) - 1:
                items.append('<div class="stage-arrow">→</div>')
        stages_html = '<div class="stage-flow">' + "".join(items) + "</div>"

    # Jobs table
    jobs_html = ""
    if jobs:
        rows = ""
        for j in jobs:
            step_count = len(j.get("steps", []))
            needs = ", ".join(j.get("needs", [])) if j.get("needs") else '<span class="none-label">None</span>'
            runner = _escape(str(j.get("runner", j.get("stage", j.get("image", "—")))))
            rows += f"""<tr>
                <td class="job-name">{_escape(j.get('name', j.get('id', 'unnamed')))}</td>
                <td><code>{runner}</code></td>
                <td><span class="step-badge">{step_count}</span></td>
                <td class="deps-cell">{needs}</td>
            </tr>"""
        jobs_html = f"""<div class="table-wrap"><table class="data-table">
            <thead><tr><th>Job</th><th>Runner / Stage</th><th>Steps</th><th>Dependencies</th></tr></thead>
            <tbody>{rows}</tbody>
        </table></div>"""

    features_html = "".join(f'<span class="feature-badge">{_escape(f)}</span>' for f in features)
    if not features_html:
        features_html = '<span class="feature-badge dim">No advanced features detected</span>'

    triggers_str = _escape(", ".join(str(t) for t in triggers)) if triggers else "Not specified"
    env_str      = _escape(", ".join(env_vars[:8])) if env_vars else "None"
    if len(env_vars) > 8:
        env_str += f" <em>(+{len(env_vars)-8} more)</em>"

    # Metrics chips
    metrics_html = ""
    if a.get("complexity_score") is not None:
        metrics_html += f'<div class="metric-chip">Complexity <b>{a["complexity_score"]}</b></div>'
    if a.get("parallelism_ratio") is not None:
        pct = int(a["parallelism_ratio"] * 100)
        metrics_html += f'<div class="metric-chip">Parallelism <b>{pct}%</b></div>'
    if a.get("estimated_minutes"):
        metrics_html += f'<div class="metric-chip">Est. Duration <b>~{a["estimated_minutes"]} min</b></div>'

    pipeline_type_badge = ""
    if a.get("pipeline_type"):
        pipeline_type_badge = f'<span class="type-badge">{_escape(a["pipeline_type"])}</span>'

    card_id = _safe_id(file_name)

    return f"""
<div class="card pipeline-card" id="card-{card_id}">
  <div class="card-header" onclick="toggleCard('{card_id}')">
    <div class="card-header-left">
      <span class="platform-icon">{icon}</span>
      <div class="card-title-group">
        <h3>{_escape(name)}</h3>
        <div class="card-meta">
          <span class="platform-badge">{_escape(platform)}</span>
          {pipeline_type_badge}
          <span class="file-label">📄 {_escape(file_name)} ({line_count} lines)</span>
        </div>
      </div>
    </div>
    <div class="card-header-right">
      {metrics_html}
      <span class="toggle-icon" id="toggle-{card_id}">▼</span>
    </div>
  </div>
  <div class="card-body" id="body-{card_id}">
    <div class="info-grid">
      <div class="info-item"><span class="info-label">Triggers</span><span class="info-val">{triggers_str}</span></div>
      <div class="info-item"><span class="info-label">Stages</span><span class="info-val">{len(stages)}</span></div>
      <div class="info-item"><span class="info-label">Jobs</span><span class="info-val">{len(jobs)}</span></div>
      <div class="info-item"><span class="info-label">Env Vars</span><span class="info-val">{env_str}</span></div>
    </div>

    <div class="section-label">Pipeline Flow</div>
    {stages_html if stages_html else '<p class="empty-msg">No stages defined</p>'}

    <div class="section-label">Jobs</div>
    {jobs_html if jobs_html else '<p class="empty-msg">No jobs found</p>'}

    <div class="section-label">Features</div>
    <div class="features-wrap">{features_html}</div>
  </div>
</div>"""


def _security_card(sec: dict, analysis: dict) -> str:
    file_name = os.path.basename(analysis.get("file", "unknown"))
    score     = sec["score"]
    grade     = sec["grade"]
    color     = _grade_color(score)
    card_id   = "sec-" + _safe_id(file_name)

    # Radial ring SVG
    circ = 2 * 3.14159 * 30  # circumference for r=30
    dash = circ * (1 - score / 100)
    ring_svg = f"""<svg class="score-ring" viewBox="0 0 80 80">
      <circle cx="40" cy="40" r="30" fill="none" stroke="#1e293b" stroke-width="8"/>
      <circle cx="40" cy="40" r="30" fill="none" stroke="{color}" stroke-width="8"
              stroke-dasharray="{circ:.1f}" stroke-dashoffset="{dash:.1f}"
              stroke-linecap="round" transform="rotate(-90 40 40)"
              class="ring-progress" data-target-offset="{dash:.1f}"/>
      <text x="40" y="37" text-anchor="middle" fill="{color}" font-size="14" font-weight="700">{score}</text>
      <text x="40" y="50" text-anchor="middle" fill="#64748b" font-size="9">{grade}</text>
    </svg>"""

    # Findings
    findings_html = ""
    for f in sec["findings"]:
        sev    = f["severity"].lower()
        lines  = "".join(
            f'<div class="code-line"><span class="line-no">L{ml["line_num"]}</span> {_escape(ml["content"][:100])}</div>'
            for ml in f.get("matched_lines", [])
        )
        rem = _escape(f.get("remediation", ""))
        findings_html += f"""
<div class="finding {sev}">
  <div class="finding-header">
    <span class="sev-badge {sev}">{f['severity']}</span>
    <span class="cat-tag">{_escape(f.get('category',''))}</span>
    <strong>{_escape(f['rule_id'])}: {_escape(f['name'])}</strong>
  </div>
  <p class="finding-desc">{_escape(f['description'])}</p>
  {lines}
  {f'<div class="remediation"><span class="rem-label">💡 Fix:</span> {rem}</div>' if rem else ''}
</div>"""

    passed_html = "".join(
        f'<div class="passed-check">✅ {_escape(p["rule_id"])}: {_escape(p["name"])}</div>'
        for p in sec["passed"]
    )

    issues_section = ""
    if findings_html:
        issues_section = f'<div class="section-label warn-label">⚠️ Issues Found ({sec["issues_found"]})</div>{findings_html}'

    return f"""
<div class="card security-card" id="{card_id}">
  <div class="card-header" onclick="toggleCard('{card_id}')">
    <div class="card-header-left">
      {ring_svg}
      <div class="card-title-group">
        <h3>Security Analysis: {_escape(file_name)}</h3>
        <div class="card-meta">
          <span class="checks-summary">{sec['checks_passed']}/{sec['total_checks']} checks passed · {sec['issues_found']} issues</span>
        </div>
      </div>
    </div>
    <span class="toggle-icon" id="toggle-{card_id}">▼</span>
  </div>
  <div class="card-body" id="body-{card_id}">
    {issues_section}
    <div class="section-label">✅ Passed Checks ({sec['checks_passed']})</div>
    <div class="passed-grid">{passed_html}</div>
  </div>
</div>"""


def _error_card(analysis: dict) -> str:
    return f"""
<div class="card error-card">
  <div class="card-header">
    <span class="platform-icon">⚠️</span>
    <div class="card-title-group">
      <h3>Parse Error</h3>
      <div class="card-meta"><span class="file-label">{_escape(analysis.get('file','unknown'))}</span></div>
    </div>
  </div>
  <div class="card-body">
    <p class="error-msg">{_escape(analysis.get('error','Unknown error'))}</p>
  </div>
</div>"""


# ── Insights Section ──────────────────────────────────────────────────────────

def _build_insights_section(analyses: list) -> str:
    valid = [a for a in analyses if "error" not in a]
    if not valid:
        return '<p class="empty-msg">No data available for insights.</p>'

    cards = ""
    for a in valid:
        recs = a.get("recommendations", [])
        best = a.get("best_practices", [])
        file_name = os.path.basename(a.get("file", ""))
        icon = _platform_icon(a.get("platform", ""))

        recs_html = ""
        for r in recs:
            pri_class = r["priority"].lower()
            recs_html += f"""
<div class="insight-item {pri_class}">
  <span class="insight-icon">{r['icon']}</span>
  <div>
    <div class="insight-title">{_escape(r['title'])} <span class="pri-badge {pri_class}">{r['priority']}</span></div>
    <div class="insight-detail">{_escape(r['detail'])}</div>
  </div>
</div>"""

        best_html = "".join(f'<div class="best-item">{_escape(b)}</div>' for b in best)

        cards += f"""
<div class="insight-card">
  <div class="insight-card-header">
    <span>{icon}</span>
    <h4>{_escape(a.get('name','Pipeline'))} <span class="file-label">— {_escape(file_name)}</span></h4>
  </div>
  {f'<div class="best-practices-wrap">{best_html}</div>' if best else ''}
  {recs_html if recs_html else '<p class="empty-msg">No recommendations — great job! 🎉</p>'}
</div>"""

    return cards


def _build_heatmap(analyses: list, security_results: list) -> str:
    """Build a quick-reference health heatmap."""
    items = ""
    for i, a in enumerate(analyses):
        if "error" in a:
            continue
        file_name = os.path.basename(a.get("file", ""))
        score = security_results[i]["score"] if i < len(security_results) else 100
        color = _grade_color(score)
        features = _collect_features(a)
        feat_icons = ""
        if a.get("caching"):           feat_icons += "💾"
        if a.get("security_scanning"): feat_icons += "🔒"
        if a.get("manual_approval"):   feat_icons += "🚦"
        if a.get("notifications"):     feat_icons += "🔔"
        items += f"""
<div class="heatmap-cell" style="border-top: 3px solid {color}">
  <div class="heatmap-icon">{_platform_icon(a.get('platform',''))}</div>
  <div class="heatmap-name" title="{_escape(file_name)}">{_escape(file_name[:20])}</div>
  <div class="heatmap-score" style="color:{color}">{score}</div>
  <div class="heatmap-feats">{feat_icons or '—'}</div>
</div>"""
    return f'<div class="heatmap-grid">{items}</div>' if items else ''


# ── HTML Template ─────────────────────────────────────────────────────────────

def _get_full_template() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CI/CD Pipeline Analysis Report</title>
<meta name="description" content="Advanced CI/CD pipeline analysis report covering security, structure and insights.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
/* ── Design Tokens ── */
:root {{
  --bg-base:     #060b14;
  --bg-card:     #0d1b2a;
  --bg-card-alt: #111827;
  --bg-input:    #1a2740;
  --border:      #1e3a5f;
  --border-hover:#3b82f6;
  --text-primary:#e2e8f0;
  --text-secondary:#94a3b8;
  --text-dim:    #475569;
  --accent-blue: #3b82f6;
  --accent-violet:#8b5cf6;
  --accent-cyan: #06b6d4;
  --accent-green:#22c55e;
  --accent-orange:#f97316;
  --accent-red:  #ef4444;
  --accent-yellow:#eab308;
  --grad-main: linear-gradient(135deg, #3b82f6, #8b5cf6, #06b6d4);
  --grad-card: linear-gradient(160deg, #0d1b2a 0%, #111827 100%);
  --shadow:    0 4px 24px rgba(0,0,0,0.5);
  --shadow-hover: 0 8px 40px rgba(59,130,246,0.15);
  --radius:    14px;
  --radius-sm: 8px;
  --font-main: 'Inter', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
  --sidebar-w: 220px;
  --transition: 0.2s ease;
}}

/* ── Reset & Base ── */
*, *::before, *::after {{ margin:0; padding:0; box-sizing:border-box; }}
html {{ scroll-behavior: smooth; }}
body {{
  font-family: var(--font-main);
  background: var(--bg-base);
  color: var(--text-primary);
  line-height: 1.6;
  min-height: 100vh;
  overflow-x: hidden;
}}

/* ── Animated background ── */
body::before {{
  content: '';
  position: fixed;
  inset: 0;
  background:
    radial-gradient(ellipse 80% 40% at 20% 10%, rgba(59,130,246,0.06) 0%, transparent 60%),
    radial-gradient(ellipse 60% 40% at 80% 80%, rgba(139,92,246,0.05) 0%, transparent 60%);
  pointer-events: none;
  z-index: 0;
}}

/* ── Layout ── */
.layout {{ display: flex; min-height: 100vh; }}

/* ── Sidebar ── */
.sidebar {{
  width: var(--sidebar-w);
  background: rgba(13,27,42,0.95);
  border-right: 1px solid var(--border);
  position: fixed;
  top: 0; left: 0; bottom: 0;
  overflow-y: auto;
  z-index: 100;
  backdrop-filter: blur(20px);
  display: flex;
  flex-direction: column;
}}
.sidebar-logo {{
  padding: 24px 20px 16px;
  border-bottom: 1px solid var(--border);
}}
.sidebar-logo h2 {{
  font-size: 0.85rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  background: var(--grad-main);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}}
.sidebar-logo p {{
  font-size: 0.7rem;
  color: var(--text-dim);
  margin-top: 2px;
}}
.sidebar-nav {{ padding: 16px 12px; flex: 1; }}
.nav-group-label {{
  font-size: 0.65rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-dim);
  padding: 8px 8px 4px;
}}
.nav-link {{
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  text-decoration: none;
  font-size: 0.83rem;
  font-weight: 500;
  transition: all var(--transition);
  margin-bottom: 2px;
  cursor: pointer;
}}
.nav-link:hover, .nav-link.active {{
  background: rgba(59,130,246,0.12);
  color: var(--accent-blue);
}}
.nav-link .nav-icon {{ font-size: 1em; width: 16px; text-align:center; }}
.sidebar-footer {{
  padding: 16px;
  border-top: 1px solid var(--border);
  font-size: 0.7rem;
  color: var(--text-dim);
  text-align: center;
}}

/* ── Main Content ── */
.main {{
  margin-left: var(--sidebar-w);
  flex: 1;
  min-width: 0;
  position: relative;
  z-index: 1;
}}

/* ── Header / Hero ── */
header {{
  background: linear-gradient(160deg, #0d1b2a 0%, #060b14 60%, #0f0b25 100%);
  border-bottom: 1px solid var(--border);
  padding: 60px 40px 48px;
  position: relative;
  overflow: hidden;
}}
header::after {{
  content: '';
  position: absolute;
  top: -60px; right: -60px;
  width: 300px; height: 300px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(139,92,246,0.12) 0%, transparent 70%);
  pointer-events: none;
}}
.header-inner {{ max-width: 900px; }}
.header-eyebrow {{
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--accent-blue);
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}}
.header-eyebrow::before {{
  content: '';
  width: 24px; height: 2px;
  background: var(--accent-blue);
  border-radius: 2px;
}}
header h1 {{
  font-size: clamp(1.8rem, 4vw, 2.8rem);
  font-weight: 800;
  background: linear-gradient(90deg, #60a5fa 0%, #a78bfa 50%, #22d3ee 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  line-height: 1.2;
  margin-bottom: 12px;
}}
header p {{ color: var(--text-secondary); font-size: 0.95rem; }}
.header-actions {{
  display: flex;
  gap: 10px;
  margin-top: 24px;
  flex-wrap: wrap;
}}
.btn {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 18px;
  border-radius: var(--radius-sm);
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition);
  border: 1px solid transparent;
  text-decoration: none;
  font-family: var(--font-main);
}}
.btn-primary {{
  background: var(--accent-blue);
  color: #fff;
}}
.btn-primary:hover {{ background: #2563eb; transform: translateY(-1px); }}
.btn-secondary {{
  background: transparent;
  color: var(--text-secondary);
  border-color: var(--border);
}}
.btn-secondary:hover {{
  border-color: var(--accent-blue);
  color: var(--accent-blue);
}}

/* ── Search Bar ── */
.search-bar-wrap {{
  padding: 20px 40px;
  background: rgba(13,27,42,0.5);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 12px;
}}
.search-input {{
  flex: 1;
  max-width: 480px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 24px;
  padding: 9px 18px 9px 42px;
  color: var(--text-primary);
  font-family: var(--font-main);
  font-size: 0.85rem;
  outline: none;
  transition: border-color var(--transition);
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 20' fill='%2364748b'%3E%3Cpath d='M9 3a6 6 0 100 12A6 6 0 009 3zM2 9a7 7 0 1112.452 4.391l3.328 3.329a1 1 0 01-1.414 1.414l-3.329-3.328A7 7 0 012 9z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-size: 16px;
  background-position: 14px center;
}}
.search-input:focus {{ border-color: var(--accent-blue); }}
.search-hint {{ font-size: 0.75rem; color: var(--text-dim); }}

/* ── Tabs ── */
.tabs-bar {{
  display: flex;
  gap: 0;
  padding: 0 40px;
  border-bottom: 1px solid var(--border);
  background: rgba(13,27,42,0.4);
  overflow-x: auto;
}}
.tab-btn {{
  padding: 14px 22px;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
  border: none;
  background: transparent;
  border-bottom: 2px solid transparent;
  transition: all var(--transition);
  display: flex;
  align-items: center;
  gap: 7px;
  white-space: nowrap;
  font-family: var(--font-main);
}}
.tab-btn:hover {{ color: var(--text-primary); }}
.tab-btn.active {{
  color: var(--accent-blue);
  border-bottom-color: var(--accent-blue);
}}
.tab-content {{ display: none; padding: 32px 40px 60px; }}
.tab-content.active {{ display: block; }}

/* ── Stats Grid ── */
.stats-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 16px;
  margin-bottom: 36px;
}}
.stat-box {{
  background: var(--grad-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 22px 18px;
  text-align: center;
  transition: all var(--transition);
  position: relative;
  overflow: hidden;
}}
.stat-box::before {{
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: var(--grad-main);
  opacity: 0;
  transition: opacity var(--transition);
}}
.stat-box:hover::before {{ opacity: 1; }}
.stat-box:hover {{ border-color: var(--border-hover); transform: translateY(-2px); box-shadow: var(--shadow-hover); }}
.stat-value {{
  font-size: 2.1em;
  font-weight: 800;
  line-height: 1;
  background: var(--grad-main);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin-bottom: 6px;
}}
.stat-value.green {{ background: linear-gradient(90deg, #22c55e, #10b981); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
.stat-value.red   {{ background: linear-gradient(90deg, #ef4444, #f97316); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
.stat-label {{ font-size: 0.8rem; color: var(--text-secondary); font-weight: 500; }}

/* ── Section headings ── */
.section-h2 {{
  font-size: 1.2rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 32px 0 16px;
  display: flex;
  align-items: center;
  gap: 10px;
}}
.section-h2::after {{
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border);
}}

/* ── Cards ── */
.card {{
  background: var(--grad-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 16px;
  overflow: hidden;
  transition: all var(--transition);
}}
.card:hover {{ border-color: var(--border-hover); box-shadow: var(--shadow-hover); }}
.card-header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 22px;
  cursor: pointer;
  user-select: none;
  border-bottom: 1px solid transparent;
  transition: border-color var(--transition);
}}
.card-header:hover {{ border-bottom-color: var(--border); }}
.card-header-left {{ display: flex; align-items: center; gap: 14px; flex: 1; min-width: 0; }}
.card-header-right {{ display: flex; align-items: center; gap: 8px; flex-shrink: 0; }}
.card-title-group {{ min-width: 0; }}
.card-title-group h3 {{
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}
.card-meta {{
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  flex-wrap: wrap;
}}
.card-body {{
  padding: 22px;
  border-top: 1px solid var(--border);
  animation: fadeInDown 0.2s ease;
}}
.card-body.hidden {{ display: none; }}

.toggle-icon {{
  color: var(--text-dim);
  font-size: 0.75rem;
  transition: transform var(--transition);
}}
.toggle-icon.open {{ transform: rotate(180deg); }}

.platform-icon {{ font-size: 1.8em; flex-shrink: 0; }}
.platform-badge {{
  background: rgba(59,130,246,0.15);
  color: var(--accent-blue);
  border: 1px solid rgba(59,130,246,0.25);
  padding: 2px 10px;
  border-radius: 20px;
  font-size: 0.7rem;
  font-weight: 600;
}}
.type-badge {{
  background: rgba(139,92,246,0.15);
  color: #a78bfa;
  border: 1px solid rgba(139,92,246,0.25);
  padding: 2px 10px;
  border-radius: 20px;
  font-size: 0.7rem;
  font-weight: 600;
}}
.file-label {{ color: var(--text-dim); font-size: 0.78rem; }}

/* ── Metric chips ── */
.metric-chip {{
  background: rgba(15,31,61,0.8);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 0.72rem;
  color: var(--text-secondary);
  white-space: nowrap;
}}
.metric-chip b {{ color: var(--text-primary); }}

/* ── Info Grid ── */
.info-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 10px;
  margin-bottom: 20px;
}}
.info-item {{
  background: rgba(6,11,20,0.6);
  border: 1px solid var(--border);
  padding: 10px 14px;
  border-radius: var(--radius-sm);
}}
.info-label {{
  display: block;
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-dim);
  font-weight: 600;
  margin-bottom: 3px;
}}
.info-val {{ font-size: 0.85rem; color: var(--text-primary); }}

/* ── Section labels ── */
.section-label {{
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: 700;
  color: var(--text-dim);
  margin: 18px 0 8px;
}}
.warn-label {{ color: var(--accent-yellow); }}

/* ── Stage Flow ── */
.stage-flow {{
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 12px 0;
}}
.stage-node {{
  background: linear-gradient(135deg, rgba(59,130,246,0.12), rgba(139,92,246,0.08));
  border: 1px solid rgba(59,130,246,0.3);
  color: #93c5fd;
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  font-size: 0.82rem;
  font-weight: 500;
  white-space: nowrap;
  transition: all var(--transition);
}}
.stage-node:hover {{
  background: rgba(59,130,246,0.2);
  border-color: var(--accent-blue);
  transform: translateY(-1px);
}}
.stage-arrow {{ color: var(--text-dim); font-size: 1rem; }}

/* ── Data Table ── */
.table-wrap {{ overflow-x: auto; margin: 4px 0 8px; border-radius: var(--radius-sm); }}
.data-table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
.data-table th {{
  background: rgba(6,11,20,0.8);
  padding: 9px 12px;
  text-align: left;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-dim);
  font-weight: 600;
  border-bottom: 1px solid var(--border);
}}
.data-table td {{
  padding: 9px 12px;
  border-bottom: 1px solid rgba(30,58,95,0.4);
  color: var(--text-secondary);
}}
.data-table tr:last-child td {{ border-bottom: none; }}
.data-table tr:hover td {{ background: rgba(59,130,246,0.04); }}
.job-name {{ color: var(--text-primary); font-weight: 500; }}
.step-badge {{
  background: rgba(59,130,246,0.15);
  color: var(--accent-blue);
  padding: 2px 8px;
  border-radius: 20px;
  font-size: 0.75rem;
  font-weight: 600;
}}
.deps-cell {{ color: var(--text-dim); font-size: 0.8rem; }}
.none-label {{ color: var(--text-dim); }}
code {{
  font-family: var(--font-mono);
  font-size: 0.8rem;
  background: rgba(6,11,20,0.6);
  padding: 1px 6px;
  border-radius: 4px;
  color: #93c5fd;
}}

/* ── Features ── */
.features-wrap {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }}
.feature-badge {{
  background: rgba(6,182,212,0.1);
  color: var(--accent-cyan);
  border: 1px solid rgba(6,182,212,0.2);
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 0.78rem;
  font-weight: 500;
}}
.feature-badge.dim {{ background: rgba(30,58,95,0.3); color: var(--text-dim); border-color: var(--border); }}

/* ── Security Score Ring ── */
.score-ring {{
  width: 72px;
  height: 72px;
  flex-shrink: 0;
}}
.ring-progress {{
  transition: stroke-dashoffset 1.2s cubic-bezier(0.4, 0, 0.2, 1);
}}
.checks-summary {{ font-size: 0.8rem; color: var(--text-secondary); }}

/* ── Findings ── */
.finding {{
  border-left: 3px solid;
  padding: 12px 16px;
  margin: 8px 0;
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  background: rgba(6,11,20,0.5);
}}
.finding.critical {{ border-color: var(--accent-red); }}
.finding.high    {{ border-color: var(--accent-orange); }}
.finding.medium  {{ border-color: var(--accent-yellow); }}
.finding.low     {{ border-color: var(--accent-cyan); }}
.finding-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap; }}
.finding-desc {{ font-size: 0.82rem; color: var(--text-secondary); margin-bottom: 6px; }}
.sev-badge {{
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.65rem;
  font-weight: 700;
  color: #fff;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}}
.sev-badge.critical {{ background: var(--accent-red); }}
.sev-badge.high    {{ background: var(--accent-orange); }}
.sev-badge.medium  {{ background: var(--accent-yellow); color: #000; }}
.sev-badge.low     {{ background: var(--accent-cyan); color: #000; }}
.cat-tag {{
  background: rgba(30,58,95,0.6);
  color: var(--text-dim);
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.65rem;
  font-weight: 600;
}}
.code-line {{
  font-family: var(--font-mono);
  font-size: 0.76rem;
  background: rgba(6,11,20,0.8);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 5px 10px;
  margin: 4px 0;
  overflow-x: auto;
  white-space: pre;
}}
.line-no {{
  color: var(--text-dim);
  margin-right: 8px;
  user-select: none;
}}
.remediation {{
  margin-top: 8px;
  font-size: 0.8rem;
  color: var(--accent-green);
  background: rgba(34,197,94,0.05);
  border: 1px solid rgba(34,197,94,0.15);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
}}
.rem-label {{ font-weight: 600; }}
.passed-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 4px;
  margin-top: 4px;
}}
.passed-check {{
  font-size: 0.8rem;
  color: #86efac;
  padding: 4px 8px;
}}

/* ── Error Card ── */
.error-card {{ border-color: var(--accent-red); }}
.error-msg {{ color: var(--accent-red); font-size: 0.85rem; }}
.empty-msg {{ color: var(--text-dim); font-size: 0.85rem; padding: 8px 0; }}

/* ── Insights ── */
.insight-card {{
  background: var(--grad-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  margin-bottom: 16px;
}}
.insight-card-header {{
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 12px;
}}
.insight-card-header h4 {{ font-size: 0.95rem; font-weight: 600; }}
.insight-item {{
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  border-radius: var(--radius-sm);
  margin-bottom: 8px;
  border: 1px solid var(--border);
  background: rgba(6,11,20,0.4);
  transition: all var(--transition);
}}
.insight-item:hover {{ border-color: var(--border-hover); }}
.insight-item.high   {{ border-left: 3px solid var(--accent-orange); }}
.insight-item.medium {{ border-left: 3px solid var(--accent-yellow); }}
.insight-item.low    {{ border-left: 3px solid var(--accent-cyan); }}
.insight-icon {{ font-size: 1.4em; flex-shrink: 0; }}
.insight-title {{
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 3px;
  display: flex;
  align-items: center;
  gap: 8px;
}}
.insight-detail {{ font-size: 0.8rem; color: var(--text-secondary); }}
.pri-badge {{
  font-size: 0.62rem;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 3px;
  text-transform: uppercase;
}}
.pri-badge.high   {{ background: rgba(249,115,22,0.2); color: var(--accent-orange); }}
.pri-badge.medium {{ background: rgba(234,179,8,0.15); color: var(--accent-yellow); }}
.pri-badge.low    {{ background: rgba(6,182,212,0.12); color: var(--accent-cyan); }}
.best-practices-wrap {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }}
.best-item {{
  font-size: 0.78rem;
  color: var(--accent-green);
  background: rgba(34,197,94,0.07);
  border: 1px solid rgba(34,197,94,0.15);
  padding: 3px 10px;
  border-radius: 20px;
}}

/* ── Heatmap ── */
.heatmap-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}}
.heatmap-cell {{
  background: var(--bg-card-alt);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 14px 10px;
  text-align: center;
  transition: all var(--transition);
}}
.heatmap-cell:hover {{ transform: translateY(-2px); box-shadow: var(--shadow-hover); }}
.heatmap-icon {{ font-size: 1.6em; margin-bottom: 4px; }}
.heatmap-name {{
  font-size: 0.72rem;
  color: var(--text-secondary);
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}
.heatmap-score {{
  font-size: 1.3em;
  font-weight: 800;
  line-height: 1;
}}
.heatmap-feats {{ font-size: 1em; margin-top: 4px; }}

/* ── Footer ── */
footer {{
  background: var(--bg-card);
  border-top: 1px solid var(--border);
  padding: 28px 40px;
  text-align: center;
  color: var(--text-dim);
  font-size: 0.8rem;
  margin-left: 0;
}}
footer a {{ color: var(--accent-blue); text-decoration: none; }}

/* ── Animations ── */
@keyframes fadeInDown {{
  from {{ opacity: 0; transform: translateY(-8px); }}
  to   {{ opacity: 1; transform: translateY(0); }}
}}
@keyframes countUp {{
  from {{ opacity: 0; transform: translateY(10px); }}
  to   {{ opacity: 1; transform: translateY(0); }}
}}
.fade-in {{
  animation: fadeInDown 0.4s ease both;
}}

/* ── Responsive ── */
@media (max-width: 768px) {{
  .sidebar {{ display: none; }}
  .main {{ margin-left: 0; }}
  header {{ padding: 32px 20px; }}
  .search-bar-wrap, .tabs-bar {{ padding-left: 20px; padding-right: 20px; }}
  .tab-content {{ padding: 24px 20px 60px; }}
  .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
}}

/* ── Search highlight ── */
.search-hidden {{ display: none !important; }}
mark {{ background: rgba(59,130,246,0.25); color: var(--accent-blue); border-radius: 2px; padding: 0 2px; }}

/* ── Scrollbar ── */
::-webkit-scrollbar {{ width: 6px; height: 6px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 3px; }}
::-webkit-scrollbar-thumb:hover {{ background: #334155; }}
</style>
</head>
<body>
<div class="layout">

<!-- ── Sidebar ── -->
<nav class="sidebar">
  <div class="sidebar-logo">
    <h2>🔍 Pipeline Agent</h2>
    <p>CI/CD Analysis Report</p>
  </div>
  <div class="sidebar-nav">
    <div class="nav-group-label">Navigation</div>
    <a class="nav-link active" onclick="switchTab('overview')" id="nav-overview">
      <span class="nav-icon">📊</span> Overview
    </a>
    <a class="nav-link" onclick="switchTab('pipelines')" id="nav-pipelines">
      <span class="nav-icon">📋</span> Pipelines
    </a>
    <a class="nav-link" onclick="switchTab('security')" id="nav-security">
      <span class="nav-icon">🔒</span> Security
    </a>
    <a class="nav-link" onclick="switchTab('insights')" id="nav-insights">
      <span class="nav-icon">💡</span> Insights
    </a>
    <div class="nav-group-label" style="margin-top:16px">Tools</div>
    <a class="nav-link" onclick="printReport()">
      <span class="nav-icon">🖨️</span> Print Report
    </a>
    <a class="nav-link" onclick="downloadJSON()">
      <span class="nav-icon">📥</span> Export JSON
    </a>
  </div>
  <div class="sidebar-footer">
    Generated {timestamp}<br>
    Built by <strong>Satyam</strong>
  </div>
</nav>

<!-- ── Main ── -->
<div class="main">

<!-- Header -->
<header>
  <div class="header-inner">
    <div class="header-eyebrow">CI/CD Pipeline Analysis</div>
    <h1>Pipeline Intelligence Report</h1>
    <p>Generated on {timestamp} &nbsp;·&nbsp; {platforms_str}</p>
    <div class="header-actions">
      <button class="btn btn-primary" onclick="switchTab('security')">🔒 View Security</button>
      <button class="btn btn-secondary" onclick="switchTab('insights')">💡 View Insights</button>
      <button class="btn btn-secondary" onclick="downloadJSON()">📥 Export JSON</button>
    </div>
  </div>
</header>

<!-- Search -->
<div class="search-bar-wrap">
  <input type="text" class="search-input" id="searchInput"
         placeholder="Search pipelines, stages, jobs..."
         oninput="handleSearch(this.value)">
  <span class="search-hint">Press <kbd>/</kbd> to focus</span>
</div>

<!-- Tabs Bar -->
<div class="tabs-bar">
  <button class="tab-btn active" id="tab-overview"  onclick="switchTab('overview')">📊 Overview</button>
  <button class="tab-btn"        id="tab-pipelines" onclick="switchTab('pipelines')">📋 Pipelines ({total_pipelines})</button>
  <button class="tab-btn"        id="tab-security"  onclick="switchTab('security')">🔒 Security</button>
  <button class="tab-btn"        id="tab-insights"  onclick="switchTab('insights')">💡 Insights</button>
</div>

<!-- ══ TAB: Overview ══ -->
<div class="tab-content active" id="content-overview">
  <div class="stats-grid">
    <div class="stat-box">
      <div class="stat-value" data-target="{total_pipelines}">0</div>
      <div class="stat-label">Pipelines Detected</div>
    </div>
    <div class="stat-box">
      <div class="stat-value" data-target="{total_stages}">0</div>
      <div class="stat-label">Total Stages</div>
    </div>
    <div class="stat-box">
      <div class="stat-value" data-target="{total_jobs}">0</div>
      <div class="stat-label">Total Jobs</div>
    </div>
    <div class="stat-box">
      <div class="stat-value" data-target="{total_steps}">0</div>
      <div class="stat-label">Total Steps</div>
    </div>
    <div class="stat-box">
      <div class="stat-value {score_class}" data-target="{avg_score}"
           style="-webkit-text-fill-color:{score_color};background:none">0</div>
      <div class="stat-label">Avg Security Score ({avg_grade})</div>
    </div>
    <div class="stat-box">
      <div class="stat-value {issues_class}" data-target="{total_issues}"
           style="-webkit-text-fill-color:{issues_color};background:none">0</div>
      <div class="stat-label">Security Issues</div>
    </div>
  </div>

  <div class="section-h2">🌡️ Health Heatmap</div>
  {heatmap}

  <div class="section-h2">📋 Quick Summary</div>
  <div class="insight-card">
    <p style="font-size:0.9rem;color:var(--text-secondary);">
      Scanned <strong style="color:var(--text-primary)">{total_pipelines}</strong> pipeline(s) across
      <strong style="color:var(--text-primary)">{platforms_str}</strong>.
      Found <strong style="color:var(--text-primary)">{total_stages}</strong> stages,
      <strong style="color:var(--text-primary)">{total_jobs}</strong> jobs, and
      <strong style="color:var(--text-primary)">{total_steps}</strong> individual steps.
      Overall security score: <strong style="color:{score_color}">{avg_score}/100 (Grade {avg_grade})</strong>
      with <strong style="color:{issues_color}">{total_issues}</strong> issue(s) found.
    </p>
  </div>
</div>

<!-- ══ TAB: Pipelines ══ -->
<div class="tab-content" id="content-pipelines">
  <div id="pipeline-list">
    {pipeline_cards}
  </div>
  <div id="no-results" style="display:none;text-align:center;padding:40px 0;color:var(--text-dim)">
    <div style="font-size:2em;margin-bottom:8px">🔍</div>
    No pipelines match your search.
  </div>
</div>

<!-- ══ TAB: Security ══ -->
<div class="tab-content" id="content-security">
  <div class="stats-grid" style="margin-bottom:28px">
    <div class="stat-box">
      <div class="stat-value" data-target="{avg_score}"
           style="-webkit-text-fill-color:{score_color};background:none">0</div>
      <div class="stat-label">Overall Score</div>
    </div>
    <div class="stat-box">
      <div class="stat-value" data-target="{total_issues}"
           style="-webkit-text-fill-color:{issues_color};background:none">0</div>
      <div class="stat-label">Total Issues</div>
    </div>
  </div>
  {security_cards}
</div>

<!-- ══ TAB: Insights ══ -->
<div class="tab-content" id="content-insights">
  <div class="section-h2">💡 AI Recommendations</div>
  {insights}
</div>

<!-- Footer -->
<footer>
  <p>CI/CD Pipeline Definition Checker &amp; Analyzer — Built by <strong>Satyam</strong></p>
  <p style="margin-top:4px">This report was auto-generated on {timestamp}. Review findings with your team before making changes.</p>
</footer>

</div><!-- /.main -->
</div><!-- /.layout -->

<!-- ── Export Data ── -->
<script id="export-data" type="application/json">{json_export}</script>

<script>
// ── Tab switching ────────────────────────────────────────────────────────────
function switchTab(name) {{
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));

  const tab = document.getElementById('tab-' + name);
  const content = document.getElementById('content-' + name);
  const nav = document.getElementById('nav-' + name);

  if (tab) tab.classList.add('active');
  if (content) content.classList.add('active');
  if (nav) nav.classList.add('active');
}}

// ── Card toggle ──────────────────────────────────────────────────────────────
function toggleCard(id) {{
  const body   = document.getElementById('body-' + id);
  const toggle = document.getElementById('toggle-' + id);
  if (!body) return;
  const isHidden = body.classList.contains('hidden');
  body.classList.toggle('hidden', !isHidden);
  if (toggle) toggle.classList.toggle('open', !isHidden);
}}

// Expand all on load
document.addEventListener('DOMContentLoaded', () => {{
  document.querySelectorAll('.card-body').forEach(b => {{
    b.classList.remove('hidden');
  }});
  document.querySelectorAll('.toggle-icon').forEach(t => t.classList.add('open'));
}});

// ── Counter animation ────────────────────────────────────────────────────────
function animateCounters() {{
  document.querySelectorAll('.stat-value[data-target]').forEach(el => {{
    const target = parseInt(el.dataset.target) || 0;
    const duration = 1000;
    const start = performance.now();
    function update(now) {{
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      const ease = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      el.textContent = Math.round(ease * target);
      if (progress < 1) requestAnimationFrame(update);
    }}
    requestAnimationFrame(update);
  }});
}}

// ── Animate SVG rings ────────────────────────────────────────────────────────
function animateRings() {{
  document.querySelectorAll('.ring-progress').forEach(ring => {{
    const circ = parseFloat(ring.getAttribute('stroke-dasharray'));
    // Set to full (hidden) initially, then animate to target
    ring.style.strokeDashoffset = circ + 'px';
    const target = parseFloat(ring.dataset.targetOffset);
    setTimeout(() => {{
      ring.style.strokeDashoffset = target + 'px';
    }}, 300);
  }});
}}

window.addEventListener('load', () => {{
  animateCounters();
  setTimeout(animateRings, 200);
}});

// ── Live search ──────────────────────────────────────────────────────────────
function handleSearch(query) {{
  const q = query.trim().toLowerCase();
  const cards = document.querySelectorAll('#pipeline-list .pipeline-card');
  let visible = 0;

  cards.forEach(card => {{
    const text = card.textContent.toLowerCase();
    if (!q || text.includes(q)) {{
      card.classList.remove('search-hidden');
      visible++;
    }} else {{
      card.classList.add('search-hidden');
    }}
  }});

  const noResults = document.getElementById('no-results');
  if (noResults) noResults.style.display = (visible === 0 && q) ? 'block' : 'none';

  // Auto-switch to pipelines tab when searching
  if (q) switchTab('pipelines');
}}

// Focus search on /
document.addEventListener('keydown', e => {{
  if (e.key === '/' && document.activeElement.tagName !== 'INPUT') {{
    e.preventDefault();
    const inp = document.getElementById('searchInput');
    if (inp) inp.focus();
  }}
  if (e.key === 'Escape') {{
    const inp = document.getElementById('searchInput');
    if (inp) {{ inp.value = ''; handleSearch(''); inp.blur(); }}
  }}
}});

// ── Print ────────────────────────────────────────────────────────────────────
function printReport() {{ window.print(); }}

// ── JSON export ──────────────────────────────────────────────────────────────
function downloadJSON() {{
  const data = document.getElementById('export-data').textContent;
  const blob = new Blob([data], {{type: 'application/json'}});
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url;
  a.download = 'pipeline_analysis.json';
  a.click();
  URL.revokeObjectURL(url);
}}
</script>
</body>
</html>"""


# ── Helper Utilities ──────────────────────────────────────────────────────────

def _collect_features(a: dict) -> list[str]:
    features = []
    if a.get("caching"):           features.append("💾 Caching")
    if a.get("matrix_builds"):     features.append("🔀 Matrix Builds")
    if a.get("manual_approval"):   features.append("🚦 Manual Approval")
    if a.get("security_scanning"): features.append("🔒 Security Scanning")
    if a.get("notifications"):     features.append("🔔 Notifications")
    return features


def _platform_icon(platform: str) -> str:
    return {
        "GitHub Actions":      "⚙️",
        "GitLab CI":           "🦊",
        "Jenkins":             "🔧",
        "Azure DevOps":        "☁️",
        "CircleCI":            "⭕",
        "Travis CI":           "🏗️",
        "Drone CI":            "🚁",
        "Bitbucket Pipelines": "🪣",
        "TeamCity":            "🏙️",
    }.get(platform, "📦")


def _get_grade(score: int) -> str:
    if score >= 90: return "A"
    if score >= 80: return "B"
    if score >= 70: return "C"
    if score >= 60: return "D"
    return "F"


def _grade_color(score: int) -> str:
    if score >= 90: return "#22c55e"
    if score >= 80: return "#84cc16"
    if score >= 70: return "#eab308"
    if score >= 60: return "#f97316"
    return "#ef4444"


def _safe_id(name: str) -> str:
    """Convert a filename to a safe HTML id."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)


def _escape(text: str) -> str:
    """Minimal HTML entity escape."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


import re  # used by _safe_id — ensure available at module level
