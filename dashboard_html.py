"""Builds the Phase 3 dashboard: one self-contained HTML page (pure Python, no QGIS).

Only Leaflet comes from a CDN (low-bandwidth rule); all data is embedded.
The score is recomputed in the browser with the same rules as scoring.py,
so factor toggles, weights, scenarios and the wadi switch work live.
"""
import json
import time

# SRI values as published for unpkg leaflet@1.9.4 (e.g. Esri Leaflet install guide).
# If the browser blocks Leaflet ("integrity" error in the console), set "sri_check": false in config.phase3.
LEAFLET = {
    "1.9.4": {
        "css": "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",
        "css_sri": "sha512-Zcn6bjR/8RZbLEpLIeOwNtzREBAJnUKESxces60Mpoj+2okopSAcSUIUOseddDm0cxnGQzxIR7vJgsLZbdLE3w==",
        "js": "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
        "js_sri": "sha512-BwHfrr4c9kmRkLw6iXFdzcdWV/PGkVgiIyIWLLlTSXzWQzxuSg4DiQUCpauz/EWjgk5TYQqX/kvn9pG1NpYfqg==",
    }
}


def rgb(s, fallback="#888888"):
    """'205,176,22' -> '#cdb016'."""
    try:
        r, g, b = (int(v) for v in str(s).split(",")[:3])
        return f"#{r:02x}{g:02x}{b:02x}"
    except ValueError:
        return fallback


def build_html(data, leaflet_version="1.9.4", sri=True):
    lf = dict(LEAFLET[leaflet_version])
    if not sri:
        lf["css_sri"] = lf["js_sri"] = ""
    blob = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE
    for k, v in {
        "__TITLE__": data["meta"]["title"],
        "__CSS_SRIATTR__": f'integrity="{lf["css_sri"]}"' if lf["css_sri"] else "",
        "__JS_SRIATTR__": f'integrity="{lf["js_sri"]}"' if lf["js_sri"] else "",
        "__CSS__": lf["css"], "__JS__": lf["js"],
        "__DATA__": blob,
    }.items():
        html = html.replace(k, v)
    return html


def meta_block(cfg, variants_info, main_variant):
    A, P3, S = cfg["analysis"], cfg["phase3"], cfg["styles"]
    sc = cfg["scoring"]
    factors = {}
    for k, f in sc["factors"].items():
        factors[k] = {
            "field": f["field"], "label": P3["labels"].get(k, k), "unit": P3["units"].get(k, ""),
            "higher_is_better": f["higher_is_better"], "weight": f["weight"], "enabled": f["enabled"],
            "note": f.get("note", ""),
        }
    return {
        "title": P3["title"],
        "profile": cfg.get("_profile", "brief"),
        "credits": P3.get("credits", {}),
        "question": cfg["project"]["question"],
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "criteria": {
            "slope": f"{A['slope_percent_min']}-{A['slope_percent_max']} %",
            "aspect": f"{A['aspect_min_deg']}-{A['aspect_max_deg']} deg (northeast)",
            "corridor": f"{A['corridor_buffer_m'] / 1000:g} km from the railway",
            "min_area": f"> {A['min_site_acres']} acres",
            "catchment": f"{A['catchment_buffer_m'] / 1000:g} km",
            "crs": cfg["crs"]["analysis"],
        },
        "factors": factors,
        "scenarios": {k: v for k, v in sc.get("scenarios", {}).items() if isinstance(v, dict)},
        "normalisation": sc["normalisation"],
        "main_variant": main_variant,
        "variants": variants_info,
        "styles": {
            "roads": rgb(S["roads"]["color"]), "rivers": rgb(S["rivers"]["color"]),
            "districts": rgb(S["districts"]["outline"]), "states_fill": rgb(S["states"]["fill"]),
            "states_outline": rgb(S["states"]["outline"]), "red_sea": rgb(S["red_sea_state"]["outline"]),
            "rail": rgb(S["railways"]["color"]), "rail_marker": rgb(S["railways"]["marker_color"]),
            "buffer": rgb(S["railway_buffer"]["outline"]), "sites": rgb(S["proposed_sites"]["fill"]),
            "sites_outline": rgb(S["proposed_sites"]["outline"]), "population": rgb(S["population"]["fill"]),
        },
        "caveats": [
            "Population: WorldPop-style 2020 raster at about 907 m cells, before the 2023 war; displacement has changed the real distribution.",
            "Population is counted once: a 907 m population cell inside two or more 5 km catchments goes to the nearest site (pop_5km). pop_5km_gross (in the site popup and CSV) counts it for every site.",
            "Measured in UTM 36N; Red Sea State lies outside zone 36, so planar areas and distances are slightly distorted (see area_ell_m2).",
            "Distances are from the site centroid. Weights are judgements, not facts: check how the ranking moves between scenarios.",
            "Slope, aspect, corridor, wadi distance and minimum area are fixed here; changing them needs a Phase 2 re-run.",
        ],
    }


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="__CSS__" __CSS_SRIATTR__ crossorigin="">
<style>
:root{--ink:#17202b;--muted:#5f6b78;--line:#e2e6ea;--bg:#f3f4f2;--panel:#fff;--navy:#14213d;--gold:#cdb016;--gold-d:#9c8410;
 --accent:#c43c39;--site:#cdb016;--sel:#c43c39;--ok:#2e7d4f;--lost:#b0413e;--r:10px;--sh:0 1px 2px rgba(16,24,40,.06),0 1px 3px rgba(16,24,40,.08)}
*{box-sizing:border-box}
html,body{margin:0;font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,Ubuntu,"Noto Sans",sans-serif;color:var(--ink);background:var(--bg)}
/* ---- header band ---- */
#top{background:var(--navy);color:#fff;padding:18px 28px 16px;border-bottom:3px solid var(--gold);display:flex;gap:24px;align-items:flex-end;justify-content:space-between;flex-wrap:wrap}
#top .eyebrow{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--gold);margin:0 0 4px;font-weight:600}
h1{font-size:22px;line-height:1.2;margin:0 0 4px;font-weight:650;letter-spacing:-.01em}
.q{color:var(--muted);font-size:12.5px;margin:0}
#top .q{color:#c9d1dc;max-width:760px;font-size:13px}
.topctl{display:flex;flex-direction:column;align-items:flex-end;gap:5px}
.topctl .lbl{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#c9d1dc}
#top .seg{border-color:#3b4a6b}#top .seg button{background:transparent;color:#e6ebf2}#top .seg button+button{border-left-color:#3b4a6b}
#top .seg button.on{background:var(--gold);color:var(--navy);font-weight:600}
#variant-note{font-size:11.5px;color:#aab4c3}
.credit{margin:8px 0 0;font-size:12px;color:#c9d1dc}
.credit a{color:var(--gold);text-decoration:none;font-weight:600}.credit a:hover{text-decoration:underline}
.credit .dot{margin:0 7px;color:#56657f}
#footer{grid-column:1/-1;text-align:center;font-size:12.5px;color:var(--muted);border-top:3px solid var(--gold);background:var(--navy);color:#c9d1dc;border-radius:var(--r);padding:16px 18px;line-height:1.7}
#footer b{color:#fff}#footer #generated{font-size:11.5px;color:#93a0b4}
#footer a{color:var(--gold);font-weight:700;text-decoration:none;white-space:nowrap}#footer a:hover{text-decoration:underline}
/* ---- page grid ---- */
#page{max-width:1600px;margin:0 auto;padding:18px 28px 28px;display:grid;grid-template-columns:300px 1fr;gap:18px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--sh)}
/* KPI strip */
#kpis{grid-column:1/-1;display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px}
.kpi{padding:14px 16px;position:relative;overflow:hidden}
.kpi::before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--gold)}
.kpi.red::before{background:var(--accent)}.kpi.navy::before{background:var(--navy)}.kpi.green::before{background:var(--ok)}
.kpi .k{font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);font-weight:600}
.kpi .v{font-size:26px;font-weight:700;letter-spacing:-.02em;font-variant-numeric:tabular-nums;margin:2px 0 1px}
.kpi .v small{font-size:14px;color:var(--muted);font-weight:500}
.kpi .s{font-size:12px;color:var(--muted)}
/* side rail */
#side{grid-row:span 1;display:flex;flex-direction:column;height:min(68vh,720px);min-height:460px}
#scroll{overflow:auto;flex:1}
section{padding:12px 16px;border-bottom:1px solid var(--line)}
section:last-child{border-bottom:0}
h2{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin:0 0 9px;display:flex;justify-content:space-between;align-items:center;font-weight:650}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:7px;overflow:hidden}
.seg button{border:0;background:#fff;padding:5px 11px;font:inherit;font-size:12.5px;cursor:pointer;color:var(--ink)}
.seg button+button{border-left:1px solid var(--line)}
.seg button.on{background:var(--navy);color:#fff}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{border:1px solid var(--line);background:#fff;border-radius:999px;padding:4px 11px;font:inherit;font-size:12.5px;cursor:pointer;text-transform:capitalize}
.chip:hover{border-color:#b9c2cc}
.chip.on{background:var(--navy);border-color:var(--navy);color:#fff}
.fac{display:grid;grid-template-columns:18px 10px 1fr 78px 36px;gap:6px;align-items:center;padding:4px 0}
.fac .sw{width:10px;height:10px;border-radius:3px}
.fac label{font-size:13px;cursor:pointer}
.fac .dir{display:block;color:var(--muted);font-size:10.5px;line-height:1.1}
.fac input[type=range]{width:100%;accent-color:var(--navy)}
.fac .pct{text-align:right;font-variant-numeric:tabular-nums;font-size:12px;color:var(--muted)}
.fac.off label,.fac.off .pct,.fac.off .sw{opacity:.4}
.fac.na{opacity:.35}
.row{display:flex;gap:10px;align-items:center;margin:7px 0;font-size:13px}
.row>span:first-child{min-width:62px;color:var(--muted)}
.row input[type=range]{flex:1;accent-color:var(--navy)}
.row output{min-width:46px;text-align:right;font-variant-numeric:tabular-nums}
select,input[type=search]{font:inherit;font-size:12.5px;padding:5px 8px;border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--ink)}
.warn{background:#fff6e5;border:1px solid #f0d39a;color:#6b4a00;border-radius:8px;padding:8px 10px;font-size:12.5px;margin-top:8px}
.stats{display:none}
/* map */
#mapcard{position:relative;overflow:hidden;height:min(68vh,720px);min-height:460px}
#map{position:absolute;inset:0;background:#eef0ec}
.legend{background:rgba(255,255,255,.95);padding:9px 11px;border-radius:8px;box-shadow:var(--sh);font-size:12px;line-height:1.7}
.legend i{display:inline-block;width:18px;height:10px;margin-right:7px;vertical-align:middle;border:1px solid #666}
.legend .lostk{display:inline-block;width:14px;height:14px;border-radius:50%;border:1.5px dashed #333;background:var(--site);margin-right:9px;vertical-align:middle}
.rk{display:flex;align-items:center;justify-content:center;border-radius:50%;font:700 11px/1 system-ui,sans-serif;color:#17202b;border:1.5px solid #333;box-shadow:0 0 0 1.5px #fff,0 1px 3px rgba(0,0,0,.35)}
.rk.lost{border-style:dashed}
.rk.sel{border-color:var(--sel);box-shadow:0 0 0 2px var(--sel)}
.leaflet-popup-content{font-size:12.5px}
.pop table{font-size:12px}.pop td{padding:2px 4px}.pop td:first-child{text-align:left;color:var(--muted)}
#nomap{display:none;padding:24px;color:var(--muted)}
/* table */
#tablecard{grid-column:1/-1}
.tbar{display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid var(--line)}
.tbar h3{margin:0;font-size:16px;font-weight:650}
.tbar .sub{font-size:12px;color:var(--muted)}
.tools{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
#filter{width:230px}
.btn{border:1px solid var(--line);background:#fff;border-radius:6px;padding:5px 11px;font:inherit;font-size:12.5px;cursor:pointer}
.btn:hover{background:#f3f4f6}
.btn.primary{background:var(--navy);border-color:var(--navy);color:#fff}
.keys{display:flex;gap:12px;flex-wrap:wrap;font-size:11.5px;color:var(--muted);padding:8px 16px;border-bottom:1px solid var(--line)}
.keys i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px}
#tablewrap{overflow:auto;max-height:62vh}
table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}
th{position:sticky;top:0;z-index:1;background:#f8f9fa;border-bottom:1px solid var(--line);text-align:right;padding:8px 10px;cursor:pointer;white-space:nowrap;user-select:none;font-weight:600;font-size:11.5px;letter-spacing:.04em;text-transform:uppercase;color:var(--muted)}
th:first-child,td:first-child{text-align:center}
th.sorted{color:var(--ink)}
th.sorted::after{content:attr(data-dir);margin-left:4px;color:var(--accent)}
td{border-bottom:1px solid #eef0f2;padding:7px 10px;text-align:right;white-space:nowrap}
td.rk-cell b{display:inline-flex;width:24px;height:24px;border-radius:50%;align-items:center;justify-content:center;background:var(--gold);color:var(--navy);font-size:12px;border:1.5px solid #333}
tr.top3 td.rk-cell b{box-shadow:0 0 0 2px #fff,0 0 0 3.5px var(--navy)}
tr.lostc td.rk-cell b{border-style:dashed}
tbody tr{cursor:pointer;transition:background .12s}
tbody tr:hover{background:#f7f8f6}
tbody tr.sel{background:#fbeceb}
.star{color:#b8860b}
.bd{display:flex;align-items:center;gap:8px;justify-content:flex-end}
.bar{display:flex;width:170px;height:12px;border-radius:6px;background:#eef0f3;overflow:hidden}
.bar span{height:100%}
.bd b{min-width:40px;text-align:right}
.pill{display:inline-block;border-radius:999px;padding:2px 9px;font-size:11.5px;font-weight:600}
.pill.kept{background:#e5f3ea;color:var(--ok)}.pill.lost{background:#f8e6e5;color:var(--lost)}
/* about */
#about{grid-column:1/-1;display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}
#about .card{padding:14px 16px}
#about h4{margin:0 0 6px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
#about ul{margin:0;padding-left:18px;font-size:12.5px;color:#3b4652}
#about li{margin:3px 0}
#generated{grid-column:1/-1;text-align:center;font-size:11.5px;color:var(--muted)}
@media (max-width:900px){#page{grid-template-columns:1fr;padding:12px}#side{height:auto;min-height:0}#mapcard{height:60vh}#top{padding:14px}}
</style>
</head>
<body>
<header id="top">
 <div><p class="eyebrow" id="eyebrow">Site suitability analysis</p><h1 id="title"></h1><p class="q" id="question"></p></div>
 <div class="topctl"><span class="lbl">Wadi flood exclusion</span><span class="seg" id="variant"></span><span id="variant-note"></span></div>
</header>
<div id="page">
 <div id="kpis">
  <div class="card kpi"><div class="k">Sites shown</div><div class="v"><span id="s-n">0</span> <small>of <span id="s-m">0</span></small></div><div class="s">over 150 acres, within reach of the railway</div></div>
  <div class="card kpi navy"><div class="k">Suitable land</div><div class="v"><span id="s-ha">0</span> <small>ha</small></div><div class="s" id="k-acres"></div></div>
  <div class="card kpi red"><div class="k">Top-ranked site</div><div class="v" id="k-top">-</div><div class="s" id="k-top-s"></div></div>
  <div class="card kpi green" id="k-class-card"><div class="k">Class run (18 Oct)</div><div class="v" id="k-class">-</div><div class="s" id="k-class-s"></div></div>
 </div>
 <aside id="side" class="card">
  <div class="stats"><span>Scenario <b id="s-scn">-</b></span></div>
  <div id="scroll">
   <section><h2>Weight scenario</h2><div class="chips" id="scenarios"></div></section>
   <section>
    <h2>Score factors <select id="norm" title="How each factor is scaled to 0-1">
      <option value="rank">rank (percentile)</option><option value="minmax">min-max</option><option value="log_minmax">log, then min-max</option></select></h2>
    <div id="factors"></div>
   </section>
   <section>
    <h2>Show</h2>
    <div class="row"><span>Top</span><input type="range" id="topn" min="1" value="1"><output id="topn-o"></output></div>
    <div class="row"><span>Min score</span><input type="range" id="minscore" min="0" max="100" value="0"><output id="minscore-o"></output></div>
    <div class="row"><span>Colour</span><span class="seg" id="colour"><button data-v="class" class="on">class style</button><button data-v="score">by score</button></span></div>
    <div id="fewnote"></div>
   </section>
  </div>
 </aside>
 <main id="mapcard" class="card"><div id="map"><div id="nomap">The map library (Leaflet) could not load - check the internet connection. The table, scoring and exports still work.</div></div></main>
 <div id="tablecard" class="card">
  <div class="tbar">
   <div><h3>Ranked sites</h3><div class="sub">Click a row to zoom to the site and its 5 km catchment. Click a column to sort.</div></div>
   <div class="tools">
    <span class="seg" id="classf"></span>
    <input type="search" id="filter" placeholder="Filter: 12, >100 ha, <2 km">
    <button class="btn" id="csv">CSV</button><button class="btn" id="geojson">GeoJSON</button><button class="btn primary" id="reset">Reset</button>
   </div>
  </div>
  <div class="keys" id="keys"></div>
  <div id="tablewrap"><table><thead id="thead"></thead><tbody id="tbody"></tbody></table></div>
 </div>
 <div id="about">
  <div class="card"><h4>Fixed criteria</h4><ul id="criteria"></ul></div>
  <div class="card"><h4>How the score works</h4><ul>
   <li>Each factor is scaled to 0-1, where 1 is always best (closer for distances, larger for area and population).</li>
   <li><b>rank</b>: percentile rank, robust to one very large site. <b>min-max</b>: (x - min) / (max - min). <b>log</b>: ln(1 + x) before min-max.</li>
   <li>Only ticked factors count; their weights are rescaled to sum to 100 %. The coloured bar shows each factor's share of the score.</li>
   <li><span class="star">&#9733;</span> = in the top 10 under every scenario (a robust choice whatever the weights).</li></ul></div>
  <div class="card"><h4>Caveats</h4><ul id="caveats"></ul></div>
 </div>
 <div id="footer"><div id="credit2"></div><div id="credit3"></div><div id="generated"></div></div>
</div>
<script id="data" type="application/json">__DATA__</script>
<script src="__JS__" __JS_SRIATTR__ crossorigin=""></script>
<script>
"use strict";
const D = JSON.parse(document.getElementById("data").textContent);
const M = D.meta, F = M.factors, S = M.styles;
const $ = id => document.getElementById(id);

/* ---------------- scoring: same rules as scoring.py ---------------- */
function rankPct(v){const n=v.length;if(n===1)return[1];const o=v.map((x,i)=>i).sort((a,b)=>v[a]-v[b]);const r=new Array(n);let i=0;
 while(i<n){let j=i;while(j+1<n&&v[o[j+1]]===v[o[i]])j++;const avg=(i+j)/2;for(let k=i;k<=j;k++)r[o[k]]=avg/(n-1);i=j+1;}return r;}
function minmax(v){const lo=Math.min(...v),hi=Math.max(...v);return hi===lo?v.map(()=>1):v.map(x=>(x-lo)/(hi-lo));}
function normalise(values,method,hib){const have=[];values.forEach((x,i)=>{if(x!==null&&x!==undefined&&!Number.isNaN(x))have.push(i)});
 const out=values.map(()=>0);if(!have.length)return out;let v=have.map(i=>+values[i]);let n;
 if(method==="log_minmax")n=minmax(v.map(x=>Math.log1p(Math.max(x,0))));else if(method==="minmax")n=minmax(v);else n=rankPct(v);
 if(new Set(v).size===1)n=v.map(()=>1);          /* one site or all equal: full marks, same as scoring.py */
 else if(!hib)n=n.map(x=>1-x);have.forEach((i,k)=>out[i]=n[k]);return out;}
function effWeights(w,on){const keys=Object.keys(w).filter(k=>on[k]&&w[k]>0);const t=keys.reduce((s,k)=>s+w[k],0);const o={};if(t<=0)return o;keys.forEach(k=>o[k]=w[k]/t);return o;}
function scoreRows(rows,weights,method){const norms={};for(const k in weights)norms[k]=normalise(rows.map(r=>r.p[F[k].field]),method,F[k].higher_is_better);
 const sc=rows.map((r,i)=>Object.keys(weights).reduce((s,k)=>s+weights[k]*norms[k][i],0));return{sc,norms};}
const r9=x=>Math.round(x*1e9)/1e9;   // same rounding as scoring.ranks()
function ranks(sc,tie){const o=sc.map((x,i)=>i).sort((a,b)=>(r9(sc[b])-r9(sc[a]))||(tie[a]-tie[b]));const r=new Array(sc.length);o.forEach((i,k)=>r[i]=k+1);return r;}
window.SCORING={rankPct,minmax,normalise,effWeights,scoreRows,ranks};

/* ---------------- state ---------------- */
const VK = Object.keys(M.variants);
const avail = k => VK.some(v => D.sites[v].features.length && D.sites[v].features.some(f => f.properties[F[k].field] !== null && f.properties[F[k].field] !== undefined));
const st = {variant:M.main_variant, w:{}, on:{}, norm:M.normalisation, topn:null, minscore:0, sortKey:"rank", sortAsc:true,
            filter:"", sel:null, colour:"class", scenario:"balanced", classf:"all"};
const FCOL={area:"#cdb016",population:"#c43c39",road_distance:"#5b6b7a",rail_distance:"#17202b",compactness:"#4daf4a",port_distance:"#3a7bd5",buildings_5km:"#8e6c8a"};
const fcol=k=>FCOL[k]||"#999";
const HAS_CLASS=VK.some(v=>D.sites[v].features.some(f=>f.properties.class_kept!==undefined&&f.properties.class_kept!==null));
const kept=r=>r.p.class_kept===1||r.p.class_kept===true;
function defaults(){for(const k in F){st.w[k]=Math.round(F[k].weight*100);st.on[k]=F[k].enabled&&avail(k);}st.scenario="balanced";}
defaults();

/* ---------------- compute ---------------- */
let rows=[], view=[];
function compute(){
 const fc=D.sites[st.variant];
 rows=fc.features.map(f=>({id:f.properties.site_id,p:f.properties,f}));
 const w=effWeights(st.w,st.on);
 const {sc,norms}=scoreRows(rows,w,st.norm);
 const rk=ranks(sc,rows.map(r=>r.id));
 rows.forEach((r,i)=>{r.score=sc[i];r.rank=rk[i];r.n={};for(const k in norms)r.n[k]=norms[k][i];});
 // robustness: top 10 under every scenario (with the factors that are available)
 const scen={balanced:Object.fromEntries(Object.keys(F).map(k=>[k,F[k].enabled?F[k].weight:0])),...M.scenarios};
 const top=Math.min(10,rows.length);
 const ranksBy=Object.entries(scen).map(([n,sw])=>{const on={};for(const k in F)on[k]=avail(k);const ww=effWeights(sw,on);
   if(!Object.keys(ww).length)return null;return ranks(scoreRows(rows,ww,st.norm).sc,rows.map(r=>r.id));}).filter(Boolean);
 rows.forEach((r,i)=>{r.robust=ranksBy.length>0&&ranksBy.every(rr=>rr[i]<=top);r.spread=ranksBy.length?Math.max(...ranksBy.map(rr=>rr[i]))-Math.min(...ranksBy.map(rr=>rr[i])):0;});
 st._w=w;
}
function matchFilter(r){if(HAS_CLASS&&st.classf!=="all"&&(st.classf==="kept")!==kept(r))return false;
 const q=st.filter.trim();if(!q)return true;
 const m=q.match(/^([<>]=?)\s*(\d+(?:\.\d+)?)\s*(ha|people|pop|km)?$/i);
 if(m){const v=+m[2],u=(m[3]||"ha").toLowerCase();const x=u==="ha"?r.p.area_ha:(u==="km"?(r.p.dist_rail_m||0)/1000:r.p.pop_5km);
   return m[1]===">"?x>v:m[1]===">="?x>=v:m[1]==="<"?x<v:x<=v;}
 return String(r.id)===q||String(r.rank)===q;}
function applyView(){
 const n=rows.length; if(st.topn===null||st.topn>n)st.topn=n;
 view=rows.filter(r=>r.rank<=st.topn&&r.score*100>=st.minscore-1e-9&&matchFilter(r));
}

/* ---------------- table ---------------- */
const COLS=()=>{const c=[{k:"rank",t:"Rank",fmt:v=>`<b>${v}</b>`,cls:"rk-cell"},{k:"id",t:"Site",fmt:v=>v}];
 const show=[["area","area_ha",v=>fmtN(v,1)],["population","pop_5km",v=>fmtI(v)],["road_distance","dist_road_m",v=>fmtN(v/1000,1)],
  ["rail_distance","dist_rail_m",v=>fmtN(v/1000,1)],["compactness","compactness",v=>fmtN(v,2)],["port_distance","dist_port_km",v=>fmtN(v,0)],
  ["buildings_5km","buildings_5km",v=>fmtI(v)]];
 // area and population always; other factors only while they are ticked (keeps the table narrow)
 for(const [k,fld,fmt] of show)if(F[k]&&avail(k)&&(k==="area"||k==="population"||st.on[k]))c.push({k:"p."+fld,t:shortLabel(k),fmt,fac:k});
 c.push({k:"score",t:"Score breakdown",fmt:(v,r)=>breakdown(r)});c.push({k:"robust",t:"★",fmt:v=>v?'<span class="star" title="top 10 under every scenario">★</span>':""});
 if(HAS_CLASS)c.push({k:"p.class_kept",t:"Class run",fmt:(v,r)=>kept(r)?'<span class="pill kept">kept</span>':'<span class="pill lost" title="invalid geometry (cells touching at a corner): skipped by QGIS in class">lost</span>'});
 return c;};
function breakdown(r){const w=st._w||{};const segs=Object.keys(w).map(k=>{const c=w[k]*(r.n[k]||0);
  return `<span style="width:${(c*100).toFixed(1)}%;background:${fcol(k)}" title="${F[k].label}: ${(c*100).toFixed(0)} of 100 points"></span>`;}).join("");
 return `<div class="bd"><div class="bar">${segs}</div><b>${fmtN(r.score,3)}</b></div>`;}
const shortLabel=k=>({area:"ha",population:"Pop 5 km",road_distance:"Road km",rail_distance:"Rail km",compactness:"Compact",port_distance:"Port km",buildings_5km:"Bldgs"})[k]||k;
const fmtN=(v,d)=>v===null||v===undefined||Number.isNaN(v)?"-":(+v).toLocaleString("en",{minimumFractionDigits:d,maximumFractionDigits:d});
const fmtI=v=>v===null||v===undefined?"-":Math.round(v).toLocaleString("en");
const get=(r,k)=>k.startsWith("p.")?r.p[k.slice(2)]:r[k];
function renderTable(){
 const cols=COLS();if(!cols.some(c=>c.k===st.sortKey)){st.sortKey="rank";st.sortAsc=true;}
 $("thead").innerHTML="<tr>"+cols.map(c=>`<th data-k="${c.k}" class="${st.sortKey===c.k?"sorted":""}" data-dir="${st.sortAsc?"▲":"▼"}" title="${c.fac?(F[c.fac].label+" ("+F[c.fac].unit+")"+(st.on[c.fac]?"":" - not in score")):""}">${c.t}</th>`).join("")+"</tr>";
 const vs=new Set(view.map(r=>r.id));
 const sorted=[...rows].sort((a,b)=>{const x=get(a,st.sortKey),y=get(b,st.sortKey);const d=(x===y)?a.rank-b.rank:((x??-Infinity)>(y??-Infinity)?1:-1);return st.sortAsc?d:-d;});
 $("tbody").innerHTML=sorted.filter(r=>vs.has(r.id)).map(r=>`<tr data-id="${r.id}" class="${st.sel===r.id?"sel":""} ${r.rank<=3?"top3":""} ${HAS_CLASS&&!kept(r)?"lostc":""}">`+cols.map(c=>`<td class="${c.cls||""}">${c.fmt(get(r,c.k),r)}</td>`).join("")+"</tr>").join("");
 $("keys").innerHTML=Object.keys(st._w||{}).map(k=>`<span><i style="background:${fcol(k)}"></i>${F[k].label} ${Math.round(st._w[k]*100)}%</span>`).join("")+'<span>&nbsp;bar length = score (0-1)</span>';
 $("thead").querySelectorAll("th").forEach(th=>th.onclick=()=>{const k=th.dataset.k;if(st.sortKey===k)st.sortAsc=!st.sortAsc;else{st.sortKey=k;st.sortAsc=(k==="rank"||k==="id");}renderTable();});
 $("tbody").querySelectorAll("tr").forEach(tr=>tr.onclick=()=>select(+tr.dataset.id,true));
}

/* ---------------- controls ---------------- */
function renderStats(){
 const w=effWeights(st.w,st.on);
 for(const k in F){const el=document.querySelector(`#w-${k}`);if(el)el.parentElement.querySelector(".pct").textContent=w[k]?Math.round(w[k]*100)+"%":"-";}
 const n=rows.length;$("topn").max=Math.max(1,n);$("topn").value=st.topn;$("topn-o").textContent=st.topn+" / "+n;
 $("minscore-o").textContent=(st.minscore/100).toFixed(2);
 $("s-n").textContent=view.length;$("s-m").textContent=n;$("s-ha").textContent=fmtN(view.reduce((s,r)=>s+(r.p.area_ha||0),0),0);
 $("s-scn").textContent=st.scenario;
 $("k-acres").textContent=fmtN(view.reduce((s,r)=>s+(r.p.area_acres||0),0),0)+" acres · scenario "+st.scenario;
 const top=[...rows].sort((a,b)=>a.rank-b.rank)[0];
 if(top){$("k-top").innerHTML=`Site ${top.id} <small>score ${fmtN(top.score,2)}</small>`;
  $("k-top-s").textContent=`${fmtN(top.p.area_ha,0)} ha · ${fmtI(top.p.pop_5km)} people within 5 km · road ${fmtN((top.p.dist_road_m||0)/1000,1)} km`;}
 if(HAS_CLASS){const nk=rows.filter(kept).length;const t5=[...rows].sort((a,b)=>a.rank-b.rank).slice(0,5);const lost5=t5.filter(r=>!kept(r)).length;
  $("k-class").innerHTML=`${nk} <small>of ${rows.length} kept</small>`;
  $("k-class-s").textContent=`${rows.length-nk} lost to invalid geometry · ${lost5} of the top 5 were lost`;}
 const sc=$("scenarios");if(sc)sc.querySelectorAll("button[data-n]").forEach(b=>b.classList.toggle("on",b.dataset.n===st.scenario));
}
function renderControls(){
 $("variant").innerHTML=VK.map(v=>`<button data-v="${v}" class="${st.variant===v?"on":""}">${M.variants[v].short}</button>`).join("");
 $("variant").querySelectorAll("button").forEach(b=>b.onclick=()=>{st.variant=b.dataset.v;st.sel=null;st.topn=null;update(true);});
 const vi=M.variants[st.variant];$("variant-note").textContent=vi.note+" — "+D.sites[st.variant].features.length+" sites.";
 renderScenarioChips();
 const w=effWeights(st.w,st.on);
 $("factors").innerHTML=Object.keys(F).map(k=>{const a=avail(k);const f=F[k];return `<div class="fac ${st.on[k]?"":"off"} ${a?"":"na"}" title="${(f.note||"").replace(/"/g,"&quot;")}${a?"":" (not available in this run)"}">
  <input type="checkbox" id="on-${k}" ${st.on[k]?"checked":""} ${a?"":"disabled"}>
  <span class="sw" style="background:${fcol(k)}"></span>
  <label for="on-${k}">${f.label} <span class="dir">${f.higher_is_better?"↑ more is better":"↓ closer is better"}</span></label>
  <input type="range" id="w-${k}" min="0" max="100" value="${st.w[k]}" ${a&&st.on[k]?"":"disabled"} aria-label="${f.label} weight">
  <span class="pct">${w[k]?Math.round(w[k]*100)+"%":"-"}</span></div>`;}).join("");
 for(const k in F){const cb=$("on-"+k),sl=$("w-"+k);if(cb)cb.onchange=()=>{st.on[k]=cb.checked;st.scenario="custom";update();};
  if(sl)sl.oninput=()=>{st.w[k]=+sl.value;st.scenario="custom";update(false,true);};}
 $("norm").value=st.norm;
 renderStats();const n=rows.length;
 $("fewnote").innerHTML=n<=2?`<div class="warn">Only ${n} site${n===1?"":"s"} meet${n===1?"s":""} the criteria in this variant, so the ranking says little. Consider wider criteria (see "Fixed criteria") and re-run Phase 2.</div>`:"";
}
function setScenario(n){
 st.scenario=n;
 if(n==="balanced")defaults();
 else{const sw=M.scenarios[n];for(const k in F){st.w[k]=Math.round((sw[k]||0)*100);st.on[k]=(sw[k]||0)>0&&avail(k);}}
 update();
}
$("norm").onchange=e=>{st.norm=e.target.value;update();};
$("topn").oninput=e=>{st.topn=+e.target.value;update(false,true);};
$("minscore").oninput=e=>{st.minscore=+e.target.value;update(false,true);};
$("filter").oninput=e=>{st.filter=e.target.value;update(false,true);};
$("colour").querySelectorAll("button").forEach(b=>b.onclick=()=>{st.colour=b.dataset.v;$("colour").querySelectorAll("button").forEach(x=>x.classList.toggle("on",x===b));styleMap();});
function renderClassf(){const el=$("classf");if(!HAS_CLASS){el.style.display="none";return;}
 el.innerHTML=[["all","All"],["kept","Kept in class"],["lost","Lost in class"]].map(([v,t])=>`<button data-v="${v}" class="${st.classf===v?"on":""}">${t}</button>`).join("");
 el.querySelectorAll("button").forEach(b=>b.onclick=()=>{st.classf=b.dataset.v;renderClassf();update(false,true);});}
$("reset").onclick=()=>{defaults();st.classf="all";renderClassf();st.norm=M.normalisation;st.topn=null;st.minscore=0;$("minscore").value=0;st.filter="";$("filter").value="";st.sel=null;st.variant=M.main_variant;update(true);};

/* ---------------- exports ---------------- */
function download(name,text,type){const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([text],{type}));a.download=name;document.body.appendChild(a);a.click();setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove();},500);}
function exportRows(){return [...view].sort((a,b)=>a.rank-b.rank);}
const tag=()=>`${st.variant}_${st.scenario}_${st.norm}`;
$("csv").onclick=()=>{const fk=Object.keys(F).filter(avail);const head=["rank","site_id",...fk.map(k=>F[k].field),...fk.map(k=>"n_"+k),"score","robust_top10","variant","scenario","normalisation"];
 const lines=[head.join(",")];for(const r of exportRows())lines.push([r.rank,r.id,...fk.map(k=>r.p[F[k].field]??""),...fk.map(k=>r.n[k]!==undefined?r.n[k].toFixed(4):""),r.score.toFixed(4),r.robust?1:0,st.variant,st.scenario,st.norm].join(","));
 download(`sites_${tag()}.csv`,lines.join("\n"),"text/csv");};
$("geojson").onclick=()=>{const fc={type:"FeatureCollection",properties:{variant:st.variant,scenario:st.scenario,normalisation:st.norm,
  weights:Object.fromEntries(Object.entries(st._w).map(([k,v])=>[k,+v.toFixed(4)]))},
  features:exportRows().map(r=>({type:"Feature",geometry:r.f.geometry,properties:{...r.p,rank:r.rank,score:+r.score.toFixed(4),robust_top10:r.robust}}))};
 download(`sites_${tag()}.geojson`,JSON.stringify(fc),"application/geo+json");};

/* ---------------- map ---------------- */
const HAS_L=typeof L!=="undefined";
let map=null,siteLayers={},markers={},catchLayer=null,siteGroup=null,markerGroup=null;
const RAMP=["#fff3b0","#f6d860","#cdb016","#a07f0c","#5e4a07"];
function rampColour(s){return RAMP[Math.min(RAMP.length-1,Math.floor(s*RAMP.length))];}
function initMap(){
 if(!HAS_L){$("nomap").style.display="block";return;}
 map=L.map("map",{preferCanvas:false,zoomControl:true});
 const base={"None (low bandwidth)":L.layerGroup(),
  "Imagery (Esri)":L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",{maxZoom:18,attribution:"Esri, Maxar, Earthstar Geographics"})};
 const CT=D.custom_tiles;            /* local XYZ tiles (QGIS Generate XYZ tiles): work offline */
 if(CT)base[CT.label]=L.tileLayer(CT.url,{minZoom:CT.min_zoom,maxNativeZoom:CT.max_zoom,maxZoom:19,attribution:CT.attribution||"",...(CT.bounds?{bounds:CT.bounds}:{})});
 base[{none:"None (low bandwidth)",esri_imagery:"Imagery (Esri)",custom:CT?CT.label:"",osm:CT?CT.label:""}[D.default_basemap]||"None (low bandwidth)"].addTo(map);
 const svg=L.svg({padding:0.5});
 const ov={};
 const L_=D.layers;
 if(L_.states)ov["Sudan states"]=L.geoJSON(L_.states,{style:{color:S.states_outline,weight:1,fillColor:S.states_fill,fillOpacity:.55},interactive:false}).addTo(map);
 if(L_.districts)ov["Districts"]=L.geoJSON(L_.districts,{style:{color:S.districts,weight:.8,fill:false},onEachFeature:(f,l)=>l.bindTooltip(f.properties.name||"",{sticky:true})}).addTo(map);
 if(L_.rivers)ov["Rivers / wadis"]=L.geoJSON(L_.rivers,{style:{color:S.rivers,weight:1.1},interactive:false}).addTo(map);
 if(L_.roads)ov["Roads"]=L.geoJSON(L_.roads,{style:{color:S.roads,weight:1.1},interactive:false}).addTo(map);
 if(L_.corridor){const c=L.geoJSON(L_.corridor,{renderer:svg,style:{color:S.buffer,weight:1.1,fillColor:S.buffer,fillOpacity:.25},interactive:false});ov["Railway buffer 5 km"]=c.addTo(map);hatch(svg,c);}
 if(L_.red_sea)ov["Red Sea State"]=L.geoJSON(L_.red_sea,{style:{color:S.red_sea,weight:2.6,fill:false},interactive:false}).addTo(map);
 if(L_.railways){const g=L.layerGroup([L.geoJSON(L_.railways,{style:{color:S.rail,weight:1.6},interactive:false}),
   L.geoJSON(L_.railways,{style:{color:S.rail_marker,weight:3.4,dashArray:"0.1 14",lineCap:"round"},interactive:false})]);ov["Railway"]=g.addTo(map);}
 if(L_.towns)ov["Towns"]=L.geoJSON(L_.towns,{pointToLayer:(f,ll)=>L.circleMarker(ll,{radius:4,color:"#222",weight:1,fillColor:"#fff",fillOpacity:1})
   .bindTooltip(f.properties.name,{permanent:true,direction:"right",offset:[6,0],className:"town"})}).addTo(map);
 siteGroup=L.featureGroup().addTo(map);markerGroup=L.layerGroup().addTo(map);
 ov["Sites"]=siteGroup;ov["Site rank markers"]=markerGroup;
 L.control.layers(base,ov,{collapsed:true}).addTo(map);
 L.control.scale({imperial:false}).addTo(map);
 const lg=L.control({position:"bottomright"});
 lg.onAdd=()=>{const d=L.DomUtil.create("div","legend");d.innerHTML=
  `<div><i style="background:${S.sites};border-color:${S.sites_outline}"></i>Proposed site</div>
   <div><i style="background:transparent;border:2px solid ${S.population};border-radius:2px"></i>5 km catchment (selected)</div>
   <div><i style="background:repeating-linear-gradient(45deg,${S.buffer} 0 1px,transparent 1px 5px);border-color:${S.buffer}"></i>Railway buffer 5 km</div>
   <div><i style="height:3px;border:0;background:${S.rail};border-top:2px dotted ${S.rail_marker}"></i>Railway</div>
   <div><i style="background:transparent;border:2px solid ${S.red_sea}"></i>Red Sea State</div>`+
   (HAS_CLASS?`<div><span class="lostk"></span>Rank badge, dashed = lost in class run</div>`:"");return d;};
 lg.addTo(map);
 const b=L_.red_sea?L.geoJSON(L_.red_sea).getBounds():null;
 if(b&&b.isValid())map.fitBounds(b,{padding:[10,10]});else map.setView([19.5,36.5],7);
}
function hatch(svg,layer){
 // line-pattern hatch, as in the class style (SVG pattern on the Leaflet SVG renderer)
 const once=()=>{const root=svg._container;if(!root)return;if(!root.querySelector("#hatch")){const ns="http://www.w3.org/2000/svg";
  const defs=document.createElementNS(ns,"defs");const p=document.createElementNS(ns,"pattern");p.setAttribute("id","hatch");p.setAttribute("patternUnits","userSpaceOnUse");
  p.setAttribute("width","7");p.setAttribute("height","7");p.setAttribute("patternTransform","rotate(45)");
  const l=document.createElementNS(ns,"line");l.setAttribute("x1","0");l.setAttribute("y1","0");l.setAttribute("x2","0");l.setAttribute("y2","7");
  l.setAttribute("stroke",S.buffer);l.setAttribute("stroke-width","1.2");p.appendChild(l);defs.appendChild(p);root.insertBefore(defs,root.firstChild);}
  layer.eachLayer(x=>{const e=x.getElement&&x.getElement();if(e){e.setAttribute("fill","url(#hatch)");e.setAttribute("fill-opacity","1");}});};
 layer.on("add",()=>setTimeout(once,0));map.on("zoomend",once);setTimeout(once,0);
}
function buildSites(){
 if(!map)return;siteGroup.clearLayers();markerGroup.clearLayers();siteLayers={};markers={};
 if(catchLayer){map.removeLayer(catchLayer);catchLayer=null;}
 for(const r of rows){
  const l=L.geoJSON(r.f,{style:{weight:1,color:S.sites_outline,fillColor:S.sites,fillOpacity:.85}});
  l.on("click",()=>select(r.id,false));l.bindPopup(()=>popup(r));siteLayers[r.id]=l;siteGroup.addLayer(l);
  const ll=[r.p._lat,r.p._lon];
  const m=L.marker(ll,{icon:icon(r),riseOnHover:true,title:"Site "+r.id});m.on("click",()=>select(r.id,true));markers[r.id]=m;markerGroup.addLayer(m);
 }
}
function icon(r){const s=r.rank<=3?24:(r.rank<=10?20:16);const bg=st.colour==="score"?rampColour(r.score):S.sites;
 return L.divIcon({className:"",html:`<div class="rk ${st.sel===r.id?"sel":""} ${HAS_CLASS&&!kept(r)?"lost":""}" style="width:${s}px;height:${s}px;background:${bg}">${r.rank}</div>`,iconSize:[s,s],iconAnchor:[s/2,s/2]});}
function styleMap(){
 if(!map)return;const vs=new Set(view.map(r=>r.id));
 for(const r of rows){const l=siteLayers[r.id],m=markers[r.id];if(!l)continue;const vis=vs.has(r.id);
  l.setStyle({opacity:vis?1:0,fillOpacity:vis?.85:0,weight:st.sel===r.id?3:1,color:st.sel===r.id?S.population:S.sites_outline,
   fillColor:st.colour==="score"?rampColour(r.score):S.sites});
  if(vis){if(!markerGroup.hasLayer(m))markerGroup.addLayer(m);m.setIcon(icon(r));m.setZIndexOffset(1000-r.rank);}else if(markerGroup.hasLayer(m))markerGroup.removeLayer(m);}
}
function popup(r){const rowsH=Object.keys(F).filter(avail).map(k=>{const v=r.p[F[k].field];const disp=(k.endsWith("distance")&&F[k].field.endsWith("_m"))?fmtN(v/1000,2)+" km":(F[k].unit==="ha"?fmtN(v,1)+" ha":(k==="compactness"?fmtN(v,2):fmtI(v)+" "+F[k].unit));
  return `<tr><td>${F[k].label}</td><td>${disp}</td><td>${r.n[k]!==undefined?r.n[k].toFixed(2):"<i>off</i>"}</td></tr>`;}).join("");
 return `<div class="pop"><b>Site ${r.id}</b> - rank ${r.rank} of ${rows.length}${r.robust?' <span class="star">★</span>':""}<br>score ${r.score.toFixed(3)} (${st.scenario}, ${st.norm})
  <table><tr><td></td><td>value</td><td>0-1</td></tr>${rowsH}
  ${r.p.pop_5km_gross!==undefined&&r.p.pop_5km_gross!==null?`<tr><td>People, gross</td><td>${fmtI(r.p.pop_5km_gross)}</td><td><i>shared counted twice</i></td></tr>`:""}
  <tr><td>Acres</td><td>${fmtN(r.p.area_acres,0)}</td><td></td></tr><tr><td>Mean slope</td><td>${fmtN(r.p.slope_mean,2)} %</td><td></td></tr>
  <tr><td>Mean aspect</td><td>${fmtN(r.p.aspect_mean,0)}&deg;</td><td></td></tr><tr><td>Rank spread</td><td>${r.spread}</td><td></td></tr></table></div>`;}
function select(id,zoom){
 st.sel=(st.sel===id&&!zoom)?null:id;
 if(map){if(catchLayer){map.removeLayer(catchLayer);catchLayer=null;}
  const C=D.catchments&&D.catchments[st.variant];
  if(st.sel!==null&&C){const f=C.features.find(f=>f.properties.site_id===st.sel);if(f)catchLayer=L.geoJSON(f,{style:{color:S.population,weight:2,dashArray:"5 4",fill:true,fillColor:S.population,fillOpacity:.06},interactive:false}).addTo(map);}
  if(st.sel!==null&&zoom){const l=siteLayers[st.sel];const b=catchLayer?catchLayer.getBounds():l.getBounds();map.fitBounds(b,{maxZoom:13,padding:[30,30]});}
  if(st.sel!==null&&!zoom){const l=siteLayers[st.sel];l.openPopup();}}
 renderTable();styleMap();
 const tr=document.querySelector(`tr[data-id="${st.sel}"]`);if(tr&&!zoom)tr.scrollIntoView({block:"nearest"});
}

/* ---------------- update loop ---------------- */
function update(rebuild,light){
 // light = called while a slider is being dragged: do not rebuild the controls under the pointer
 compute();applyView();if(rebuild)buildSites();
 if(light){renderStats();if(st.scenario==="custom"&&!document.querySelector('#scenarios .chip.custom'))renderScenarioChips();}else renderControls();
 renderTable();styleMap();}
function renderScenarioChips(){const names=["balanced",...Object.keys(M.scenarios)];
 $("scenarios").innerHTML=names.map(n=>`<button class="chip ${st.scenario===n?"on":""}" data-n="${n}">${n}</button>`).join("")+(st.scenario==="custom"?'<button class="chip on custom">custom</button>':"");
 $("scenarios").querySelectorAll("button[data-n]").forEach(b=>b.onclick=()=>setScenario(b.dataset.n));}
function boot(){
 $("title").textContent=M.title;$("question").textContent=M.question;
 $("eyebrow").textContent="Site suitability analysis · "+(M.profile==="class"?"class settings (18 Oct 2026)":"course brief settings");
 if(!HAS_CLASS)$("k-class-card").style.display="none";renderClassf();
 const C=M.credits||{};const esc=t=>String(t||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"})[c]);
 const by=C.prepared_by?`Prepared by ${C.url?`<a href="${esc(C.url)}" target="_blank" rel="noopener">${esc(C.prepared_by)}</a>`:esc(C.prepared_by)}`:"";
 const course=C.course?`Class exercise and data: <b>${esc(C.course)}</b>`:"";
 const repo=C.url_repo?`Code: <a href="${esc(C.url_repo)}" target="_blank" rel="noopener">${esc(C.url_repo.replace(/^https?:\/\/(www\.)?/,""))}</a>`:"";
 $("credit2").innerHTML=[by,course,C.note?esc(C.note):""].filter(Boolean).join(' &nbsp;·&nbsp; ');
 $("credit3").innerHTML=repo;
 $("criteria").innerHTML=Object.entries(M.criteria).map(([k,v])=>`<li><b>${k}</b>: ${v}</li>`).join("")+
   Object.values(M.variants).map(v=>`<li><b>${v.short}</b>: ${v.note}</li>`).join("");
 $("caveats").innerHTML=M.caveats.map(c=>`<li>${c}</li>`).join("");
 $("generated").textContent="Generated "+M.generated+(M.test_data?" — TEST DATA: "+M.test_data:"");
 initMap();update(true);
}
boot();
</script>
</body>
</html>
"""
