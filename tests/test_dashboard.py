"""Browser tests for the dashboard logic (Leaflet stubbed). Run: python3 test_dashboard.py <stub.html>"""
import json, sys, os
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
import scoring
from playwright.sync_api import sync_playwright

page_path = os.path.abspath(sys.argv[1])
fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"])
    pg = b.new_page(accept_downloads=True)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.goto("file://" + page_path)
    pg.wait_for_timeout(500)
    check(not errs, f"no JS errors on load {errs[:3]}")

    D = pg.evaluate("JSON.parse(document.getElementById('data').textContent)")
    F = D["meta"]["factors"]
    nrows = pg.locator("#tbody tr").count()
    main = D["meta"]["main_variant"]
    check(nrows == len(D["sites"][main]["features"]), f"table shows all {nrows} sites of main variant")

    # ---- scoring parity JS vs scoring.py for every normalisation x scenario
    cfgF = {k: {"field": v["field"], "higher_is_better": v["higher_is_better"], "weight": v["weight"], "enabled": True} for k, v in F.items()}
    for vname, fc in D["sites"].items():
        rows = [f["properties"] for f in fc["features"]]
        avail = {k for k in F if any(r.get(F[k]["field"]) is not None for r in rows)}
        scen = {"balanced": {k: F[k]["weight"] for k in F if F[k]["enabled"]}, **D["meta"]["scenarios"]}
        for method in ("rank", "minmax", "log_minmax"):
            for sn, sw in scen.items():
                ff = {k: dict(cfgF[k], enabled=(k in avail)) for k in F}
                try:
                    w = scoring.effective_weights(ff, sw)
                except ValueError:
                    continue
                py_s, _ = scoring.score(rows, ff, w, method)
                py_r = scoring.ranks(py_s, [r["site_id"] for r in rows])
                js = pg.evaluate("""([rows,w,method,F])=>{const S=window.SCORING;
                    const rr=rows.map(p=>({p}));const on={};for(const k in w)on[k]=true;
                    const ew=S.effWeights(w,on);const {sc}=S.scoreRows(rr,ew,method);return {sc,rk:S.ranks(sc,rows.map(p=>p.site_id))};}""",
                                 [rows, {k: v for k, v in sw.items() if k in avail}, method, F])
                ok = all(abs(a - b) < 1e-9 for a, b in zip(py_s, js["sc"])) and py_r == js["rk"]
                if not ok:
                    check(False, f"parity {vname} {method} {sn}")
    check(not [f for f in fails if f.startswith("parity")], "scoring parity JS == scoring.py (all variants x normalisations x scenarios)")

    def ranks_in_table():
        return [int(t) for t in pg.locator("#tbody tr td:first-child").all_inner_texts()]

    def first_site():
        return pg.locator("#tbody tr").first.get_attribute("data-id")

    # ---- variant toggle
    ha0 = pg.inner_text("#s-ha")
    other = [v for v in D["sites"] if v != main][0]
    pg.click(f'#variant button[data-v="{other}"]')
    ha1 = pg.inner_text("#s-ha")
    n1 = pg.locator("#tbody tr").count()
    check(n1 == len(D["sites"][other]["features"]) and ha0 != ha1, f"variant toggle: {main} {ha0} ha -> {other} {ha1} ha, {n1} rows")
    pg.click(f'#variant button[data-v="{main}"]')

    # ---- factor toggle changes effective weights and possibly order
    before = first_site()
    pct_before = pg.locator("#factors .pct").all_inner_texts()
    pg.uncheck("#on-population")
    pct_after = pg.locator("#factors .pct").all_inner_texts()
    check(pct_before != pct_after and pg.inner_text("#s-scn") == "custom", f"unticking population re-weights {pct_before} -> {pct_after}")
    pg.check("#on-population")

    # ---- slider drag (input events) keeps the same slider element (not re-rendered)
    h1 = pg.evaluate("document.getElementById('w-area')===document.getElementById('w-area')")
    el = pg.evaluate_handle("document.getElementById('w-area')")
    pg.evaluate("e=>{e.value=100;e.dispatchEvent(new Event('input'))}", el)
    same = pg.evaluate("e=>e===document.getElementById('w-area')", el)
    check(same, "weight slider is not rebuilt while dragging")
    pct = pg.locator("#factors .fac").first.locator(".pct").inner_text()
    check(pct != "-", f"area weight now {pct}")

    # ---- scenario buttons change ranking
    orders = {}
    for sn in ["balanced"] + list(D["meta"]["scenarios"]):
        pg.click(f'#scenarios button[data-n="{sn}"]')
        pg.click('th[data-k="rank"]') if pg.locator('th.sorted').get_attribute("data-k") != "rank" else None
        orders[sn] = [r for r in pg.locator("#tbody tr").evaluate_all("rs=>rs.map(r=>r.dataset.id)")]
    check(len({tuple(v[:5]) for v in orders.values()}) > 1, "scenarios give different top 5: " + json.dumps({k: v[:5] for k, v in orders.items()}))
    pg.click('#scenarios button[data-n="balanced"]')

    # ---- normalisation switch
    pg.select_option("#norm", "minmax")
    mm = pg.locator("#tbody tr").evaluate_all("rs=>rs.map(r=>r.dataset.id)")
    pg.select_option("#norm", "rank")
    check(True, f"min-max top 5 {mm[:5]} vs rank top 5 {orders['balanced'][:5]}")

    # ---- top N and min score filters
    pg.evaluate("e=>{e.value=5;e.dispatchEvent(new Event('input'))}", pg.evaluate_handle("document.getElementById('topn')"))
    check(pg.locator("#tbody tr").count() == min(5, nrows) and pg.inner_text("#s-n") == str(min(5, nrows)), "top-N = 5 filters table and counter")
    pg.evaluate("e=>{e.value=e.max;e.dispatchEvent(new Event('input'))}", pg.evaluate_handle("document.getElementById('topn')"))
    pg.evaluate("e=>{e.value=60;e.dispatchEvent(new Event('input'))}", pg.evaluate_handle("document.getElementById('minscore')"))
    ok = pg.evaluate("()=>[...document.querySelectorAll('#tbody tr .bd b')].every(td=>+td.textContent>=0.6)")
    check(ok, f"min score 0.60 keeps {pg.locator('#tbody tr').count()} rows, all >= 0.60")
    pg.evaluate("e=>{e.value=0;e.dispatchEvent(new Event('input'))}", pg.evaluate_handle("document.getElementById('minscore')"))

    # ---- text filter
    pg.fill("#filter", ">100 ha")
    ok = pg.evaluate("()=>[...document.querySelectorAll('#tbody tr td:nth-child(3)')].every(td=>parseFloat(td.textContent.replace(/,/g,''))>100)")
    check(ok, f"filter '>100 ha' keeps {pg.locator('#tbody tr').count()} rows")
    pg.fill("#filter", "")

    # ---- sorting
    pg.click('th[data-k="p.area_ha"]')          # first click on a value column = descending
    vals = [float(t.replace(",", "")) for t in pg.locator("#tbody tr td:nth-child(3)").all_inner_texts()]
    check(vals == sorted(vals, reverse=True), "sort by area descending")
    pg.click('th[data-k="p.area_ha"]')
    vals = [float(t.replace(",", "")) for t in pg.locator("#tbody tr td:nth-child(3)").all_inner_texts()]
    check(vals == sorted(vals), "second click: ascending")
    pg.click('th[data-k="rank"]')

    # ---- row click selects + highlights
    fid = first_site()
    pg.locator("#tbody tr").first.click()
    check(pg.locator("#tbody tr.sel").count() == 1 and pg.evaluate("L._calls.fitBounds") >= 1, f"row click selects site {fid} and zooms")

    # ---- exports
    with pg.expect_download() as dl:
        pg.click("#csv")
    csv_text = open(dl.value.path()).read().splitlines()
    check(len(csv_text) == pg.locator("#tbody tr").count() + 1 and csv_text[0].startswith("rank,site_id"), f"CSV export: {len(csv_text) - 1} rows, header {csv_text[0][:60]}...")
    with pg.expect_download() as dl:
        pg.click("#geojson")
    gj = json.load(open(dl.value.path()))
    check(gj["type"] == "FeatureCollection" and len(gj["features"]) == len(csv_text) - 1 and "weights" in gj["properties"], f"GeoJSON export: {len(gj['features'])} features, weights {gj['properties']['weights']}")

    # ---- reset
    pg.click("#reset")
    check(pg.inner_text("#s-scn") == "balanced" and pg.locator("#tbody tr").count() == nrows, "reset restores defaults")

    check(not errs, f"no JS errors after interaction {errs[:3]}")
    b.close()

print("\n" + ("ALL PASSED" if not fails else f"{len(fails)} FAILED"))
sys.exit(1 if fails else 0)
