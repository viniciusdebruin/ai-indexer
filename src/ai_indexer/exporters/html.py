"""HTML dashboard exporter.

Renders the Code Nebula v8 dashboard by injecting project data into the
templates/nebula/ assets.  Uses Jinja2 when available; falls back to
simple string substitution of known placeholders.
"""

from __future__ import annotations

import importlib.resources
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_indexer.exporters.base import BaseExporter

log = logging.getLogger("ai-indexer.html")

try:
    from jinja2 import Environment, FileSystemLoader
    _JINJA2 = True
except ImportError:
    _JINJA2 = False
    log.warning("jinja2 not installed — using fallback template rendering.")

# Templates: src/ai_indexer/exporters/html.py → [0]exporters → [1]ai_indexer → [2]src → [3]project_root
_TEMPLATES_DIR = Path(__file__).parents[3] / "templates" / "nebula"


class HtmlExporter(BaseExporter):
    extension = ".html"

    def export(self, data: dict[str, Any], output_path: Path) -> None:
        context = self._build_context(data)
        html = self._render(context)
        output_path.write_text(html, encoding="utf-8")
        log.info("HTML dashboard written: %s", output_path)

    # ── Context builder ──────────────────────────────────────────────────────

    def _build_context(self, data: dict[str, Any]) -> dict[str, Any]:
        files    = data.get("files") or {}
        graph    = data.get("dependency_graph") or {}
        rev      = data.get("reverse_graph") or {}
        modules  = data.get("modules") or {}
        hotspots = data.get("hotspots") or []
        version  = data.get("version", "8.0.0")
        project  = data.get("project", "")
        ts       = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Lean file records for nebula.js
        all_files_lean: dict[str, Any] = {}
        for path, fd in files.items():
            all_files_lean[path] = {
                "file":            fd.get("f") or fd.get("file", path),
                "domain":          (fd.get("d") or {}).get("value") or fd.get("domain", ""),
                "priority":        fd.get("ps") or fd.get("priority_score", 0),
                "fan_in":          fd.get("fi") or fd.get("fan_in", 0),
                "criticality":     fd.get("c") or fd.get("criticality", "supporting"),
                "entrypoint":      fd.get("ep") or fd.get("entrypoint", False),
                "role_hint":       fd.get("rh") or fd.get("role_hint", ""),
                "warnings":        (fd.get("warns") or fd.get("warnings", []))[:3],
                "refactor_effort": fd.get("re") or fd.get("refactor_effort", 0.0),
                "blast_radius":    fd.get("br") or fd.get("blast_radius", 0),
            }

        edge_list: list[list[str]] = [
            [src, dst] for src, dsts in graph.items() for dst in dsts
        ]

        cyclic: set[str] = set()
        for src, dsts in graph.items():
            for dst in dsts:
                if src in (rev.get(dst) or []):
                    cyclic.add(src); cyclic.add(dst)

        n_files  = max(len(files), 1)
        n_warns  = sum(len((fd.get("warns") or fd.get("warnings", []))) for fd in files.values())
        n_cycles = len(cyclic)
        health   = max(0.0, 1.0 - (n_warns / (n_files * 2)) - (n_cycles / (n_files * 4)))

        top20    = sorted(all_files_lean.values(), key=lambda x: x["priority"], reverse=True)[:20]
        mod_summary = [
            {"name": n, "count": len(fs), "sample": fs[0] if fs else ""}
            for n, fs in sorted(modules.items(), key=lambda kv: len(kv[1]), reverse=True)[:15]
        ]
        warning_files = [
            (fd.get("f") or fd.get("file", p), fd.get("warns") or fd.get("warnings", []))
            for p, fd in files.items()
            if (fd.get("warns") or fd.get("warnings", []))
        ]

        stats = {
            "total_files":  len(files),
            "critical":     sum(1 for fd in files.values() if (fd.get("c") or fd.get("criticality")) == "critical"),
            "domains":      len({(fd.get("d") or {}).get("value") for fd in files.values()} - {None}),
            "entrypoints":  sum(1 for fd in files.values() if fd.get("ep") or fd.get("entrypoint")),
        }

        modules_nebula = {k: list(v)[:50] for k, v in list(modules.items())[:20]}

        return {
            "version":       version,
            "project":       project,
            "ts":            ts,
            "health":        health,
            "stats":         stats,
            "all_files":     all_files_lean,
            "edges":         edge_list,
            "modules":       modules_nebula,
            "cyclic":        sorted(cyclic),
            "top20":         top20,
            "mod_summary":   mod_summary,
            "warning_files": warning_files,
        }

    # ── Rendering ────────────────────────────────────────────────────────────

    def _render(self, ctx: dict[str, Any]) -> str:
        styles_css = ((_TEMPLATES_DIR / "styles.css").read_text(encoding="utf-8")
                      if (_TEMPLATES_DIR / "styles.css").exists() else "")
        nebula_js  = ((_TEMPLATES_DIR / "nebula.js").read_text(encoding="utf-8")
                      if (_TEMPLATES_DIR / "nebula.js").exists() else "")

        # JSON data blobs (values come from internal analysis — trusted)
        data_block = (
            f'const ALL_FILES={json.dumps(ctx["all_files"], ensure_ascii=False, separators=(",",":"))};'
            f'const FULL_EDGES={json.dumps(ctx["edges"],    ensure_ascii=False, separators=(",",":"))};'
            f'const MODULES_DATA={json.dumps(ctx["modules"],ensure_ascii=False, separators=(",",":"))};'
            f'const CYCLIC_SET=new Set({json.dumps(ctx["cyclic"], ensure_ascii=False, separators=(",",":"))});'
            f'const HEALTH_SCORE={ctx["health"]:.4f};'
            f'const PROJECT_NAME={json.dumps(ctx["project"])};'
        )

        if _JINJA2 and (_TEMPLATES_DIR / "index.html").exists():
            env = Environment(
                loader=FileSystemLoader(str(_TEMPLATES_DIR)),
                autoescape=True,
            )
            tmpl = env.get_template("index.html")
            return tmpl.render(
                data_block=data_block,
                styles_css=styles_css,
                nebula_js=nebula_js,
                **ctx,
            )

        # Fallback: inline everything
        return self._render_inline(ctx, data_block, styles_css, nebula_js)

    def _render_inline(
        self,
        ctx: dict[str, Any],
        data_block: str,
        styles_css: str,
        nebula_js: str,
    ) -> str:
        stats  = ctx["stats"]
        top20  = ctx["top20"]
        mods   = ctx["mod_summary"]
        warns  = ctx["warning_files"]
        proj   = ctx["project"]
        ts     = ctx["ts"]
        ver    = ctx["version"]

        def stat_card(value: Any, label: str) -> str:
            sv = str(value)
            sl = label
            return (
                f'<div class="stat-card">'
                f'<div class="stat-value">{sv}</div>'
                f'<div class="stat-label">{sl}</div>'
                f'</div>'
            )

        stats_html = (
            '<div class="stats-grid">'
            + stat_card(stats["total_files"],  "Total Files")
            + stat_card(stats["critical"],     "Critical")
            + stat_card(stats["domains"],      "Domains")
            + stat_card(stats["entrypoints"],  "Entrypoints")
            + '</div>'
        )

        def safe(s: str) -> str:
            return (s.replace("&","&amp;").replace("<","&lt;")
                     .replace(">","&gt;").replace('"',"&quot;"))

        rows = ""
        for h in top20:
            crit = h.get("criticality","supporting")
            bc   = ("badge-critical" if crit=="critical" else
                    "badge-infra"    if crit=="infra"    else
                    "badge-config"   if crit=="config"   else "badge-default")
            re_v = f'{h.get("refactor_effort",0.0):.1f}'
            br_v = str(h.get("blast_radius",0))
            rows += (
                f'<tr data-priority="{h["priority"]}" data-domain="{safe(h.get("domain",""))}">'
                f'<td>{safe(h.get("file",""))}</td>'
                f'<td><span class="badge {bc}">{safe(crit)}</span></td>'
                f'<td>{h["priority"]}</td>'
                f'<td>{safe(h.get("domain",""))}</td>'
                f'<td>{re_v}</td><td>{br_v}</td></tr>'
            )
        table_html = (
            '<div class="table-card">'
            '<h2 style="font-size:.95rem;font-weight:600;color:#0f172a;margin-bottom:12px;">Top 20 Hotspots</h2>'
            '<table><thead><tr>'
            '<th>File</th><th>Criticality</th><th>Priority</th>'
            '<th>Domain</th><th>Refactor Effort</th><th>Blast Radius</th>'
            f'</tr></thead><tbody>{rows}</tbody></table></div>'
        )

        mod_items = "".join(
            f'<div class="module-card"><div class="module-name">{safe(m["name"])}</div>'
            f'<div class="module-count">{m["count"]} file{"s" if m["count"]!=1 else ""}</div>'
            f'<div class="module-sample">{safe(m["sample"])}</div></div>'
            for m in mods
        )
        mods_html = (
            f'<div class="chart-card"><h2>Modules</h2>'
            f'<div class="modules-grid">{mod_items}</div></div>'
        )

        warn_items = ""
        for fp, wl in warns[:20]:
            msgs = "".join(
                f'<div class="warn-msg">&bull; {safe(w)}</div>' for w in wl[:3]
            )
            warn_items += (
                f'<div class="warn-item">'
                f'<div class="warn-file">{safe(fp)}</div>{msgs}</div>'
            )
        warns_html = (
            f'<div class="chart-card"><h2>Architectural Warnings ({len(warns)} files)</h2>'
            f'<div class="warn-list">'
            + (warn_items or '<p style="color:#64748b;font-size:.83rem;">No warnings detected.</p>')
            + '</div></div>'
        )

        # Legend items
        _leg = [
            ("auth","#ffd700"),("database","#1a80ff"),("ui","#ff19cc"),
            ("api","#19e699"),("billing","#f2c141"),("utils","#80e619"),
            ("config","#e6990a"),("cache","#66b3ff"),("security","#ff5050"),("shared","#e0e0e0"),
        ]
        leg_html = "\n".join(
            f'<div class="leg-item"><div class="leg-dot" style="background:{c}"></div>'
            f'<span>{d}</span></div>'
            for d, c in _leg
        )

        # CDN scripts for Three.js + extras + TWEEN
        cdn = (
            '<script src="https://cdn.jsdelivr.net/npm/three@0.163.0/build/three.min.js"></script>'
            '<script src="https://cdn.jsdelivr.net/npm/three@0.163.0/examples/js/controls/OrbitControls.js"></script>'
            '<script src="https://cdn.jsdelivr.net/npm/three@0.163.0/examples/js/postprocessing/EffectComposer.js"></script>'
            '<script src="https://cdn.jsdelivr.net/npm/three@0.163.0/examples/js/postprocessing/RenderPass.js"></script>'
            '<script src="https://cdn.jsdelivr.net/npm/three@0.163.0/examples/js/postprocessing/UnrealBloomPass.js"></script>'
            '<script src="https://cdn.jsdelivr.net/npm/three@0.163.0/examples/js/postprocessing/ShaderPass.js"></script>'
            '<script src="https://cdn.jsdelivr.net/npm/three@0.163.0/examples/js/shaders/LuminosityHighPassShader.js"></script>'
            '<script src="https://cdn.jsdelivr.net/npm/three@0.163.0/examples/js/shaders/CopyShader.js"></script>'
            '<script src="https://cdn.jsdelivr.net/npm/three@0.163.0/examples/js/renderers/CSS2DRenderer.js"></script>'
            '<script src="https://cdn.jsdelivr.net/npm/@tweenjs/tween.js@18.6.4/dist/tween.umd.js"></script>'
            '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>'
        )

        switcher = """<script>
function switchView(v){
  var nv=document.getElementById('nebula-view');
  var dv=document.getElementById('dash-view');
  var nc=document.getElementById('nebula-controls');
  var lg=document.getElementById('nebula-legend');
  var ip=document.getElementById('info-panel');
  var pt=document.getElementById('project-title');
  if(v==='nebula'){
    nv.style.display='block';dv.style.display='none';
    nc.style.display='flex';pt.style.display='block';
    document.body.style.overflow='hidden';
  } else {
    nv.style.display='none';dv.style.display='block';
    nc.style.display='none';lg.style.display='none';
    ip.style.display='none';pt.style.display='none';
    document.body.style.overflow='auto';document.body.style.background='#f0f4f8';
  }
}
document.getElementById('btn-to-dash').addEventListener('click',function(){switchView('dash');});
var nb=document.getElementById('btn-to-nebula');
if(nb) nb.addEventListener('click',function(){switchView('nebula');});
</script>"""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>Code Nebula v8 &middot; {safe(proj)}</title>
{cdn}
</head>
<body>
<script>{data_block}</script>
<style>{styles_css}</style>
<style>
.modules-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(195px,1fr));gap:12px;}}
.module-card{{background:#f8fafc;border-radius:9px;padding:13px;border:1px solid #e2e8f0;}}
.module-name{{font-weight:600;font-size:.83rem;color:#0f172a;margin-bottom:4px;}}
.module-count{{font-size:.72rem;color:#64748b;}}
.module-sample{{font-size:.68rem;color:#94a3b8;font-family:monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:3px;}}
</style>
<div id="project-title">{safe(proj)}</div>
<div id="nebula-view"><canvas id="nebula-canvas"></canvas></div>
<div id="nebula-controls">
  <button class="nb-btn" id="btn-to-dash">Dashboard</button>
  <button class="nb-btn" id="btn-tour">Tour</button>
  <button class="nb-btn" id="btn-legend">Legend</button>
</div>
<div id="info-panel">
  <button id="info-close">&times;</button>
  <div id="info-content"></div>
</div>
<div id="nebula-legend">{leg_html}</div>
<div id="dash-view">
  <div class="container">
    <div class="header">
      <div>
        <h1>AI Context Index &middot; {safe(proj)}</h1>
        <div class="subtitle">Generated {safe(ts)} &middot; v{safe(ver)}</div>
      </div>
    </div>
    {stats_html}
    {table_html}
    {mods_html}
    {warns_html}
    <div id="back-bar">
      <button class="nb-btn" id="btn-to-nebula" style="background:#1a3460;border-color:#2d5a9e;">
        Back to Nebula
      </button>
    </div>
  </div>
</div>
<script>{nebula_js}</script>
{switcher}
</body>
</html>"""
