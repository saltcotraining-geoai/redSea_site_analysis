"""Build a TEST dashboard without QGIS: Phase 0 layers (gpkg_lite) + independent_check sites."""
import sys; sys.setrecursionlimit(100000)
import json, math, os, sys
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))), "tools"))
import numpy as np
import gpkg_lite as g
import independent_check as ic
import dashboard_html as dh
from scipy import ndimage as ndi
from skimage import measure

ROOT = "/home/saltco/Downloads/sdn_datasets/sudan_site_analysis/output"
CHK = sys.argv[1]
OUT = sys.argv[2]
cfg = json.load(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))), "config.json")))
rd = lambda n: os.path.join(ROOT, "02_Raw_data", n + ".gpkg")


def dp(pts, tol):
    if len(pts) < 3:
        return pts
    a, b = np.array(pts[0]), np.array(pts[-1])
    ab = b - a
    L = np.hypot(*ab)
    P = np.array(pts)
    Q = P - a
    d = np.abs(ab[0] * Q[:, 1] - ab[1] * Q[:, 0]) / L if L else np.hypot(Q[:, 0], Q[:, 1])
    i = int(d.argmax())
    if d[i] > tol:
        return dp(pts[:i + 1], tol)[:-1] + dp(pts[i:], tol)
    return [pts[0], pts[-1]]


def tr(pts):
    return [list(ic.utm_to_wgs84(x, y)) for x, y in pts]


def lines_fc(path, tol, keep=lambda f: True, props=lambda f: {}):
    feats = []
    for f in g.read(path):
        if not keep(f):
            continue
        for ln in g.lines(f["geom"]):
            s = dp(ln, tol)
            if len(s) >= 2:
                feats.append({"type": "Feature", "properties": props(f), "geometry": {"type": "LineString", "coordinates": tr(s)}})
    return {"type": "FeatureCollection", "features": feats}


def poly_fc(path, tol, props=lambda f: {}):
    feats = []
    for f in g.read(path):
        polys = []
        for rings in g.polygons(f["geom"]):
            rr = [tr(dp(r, tol)) for r in rings]
            rr = [r for r in rr if len(r) >= 4]
            if rr:
                polys.append(rr)
        feats.append({"type": "Feature", "properties": props(f), "geometry": {"type": "MultiPolygon", "coordinates": polys}})
    return {"type": "FeatureCollection", "features": feats}


T = cfg["phase3"]["simplify_tolerance_m"]
excl = {"residential", "service", "footway", "path"}
layers = {
    "red_sea": poly_fc(os.path.join(ROOT, "01_Data", "redSea_state.gpkg"), T["states"]),
    "districts": poly_fc(rd("redSea_districts"), T["districts"], lambda f: {"name": f.get("adm2_name")}),
    "roads": lines_fc(rd("redSea_roads"), T["roads"], lambda f: f["fclass"] not in excl, lambda f: {"fclass": f["fclass"]}),
    "rivers": lines_fc(rd("redSea_rivers"), T["rivers"]),
    "railways": lines_fc(rd("redSea_railways"), 25),
    "towns": {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": f["NAME"]},
         "geometry": {"type": "Point", "coordinates": list(ic.utm_to_wgs84(*(f["geom"][1][0][1] if f["geom"][0] == "MultiPoint" else f["geom"][1])))}}
        for f in g.read(rd("redSea_towns"))]},
}
# corridor outline from a raster buffer (test only)
dem, x0, y0, res = ic.read_tif(os.path.join(ROOT, "03_Rasters", "redSea_dem_utm36n.tif"))
rails = [ln for f in g.read(rd("redSea_railways")) for ln in g.lines(f["geom"])]
cor = ndi.distance_transform_edt(~ic.rasterize_lines(rails, dem.shape, x0, y0, res)) * res <= 5000
cs = measure.find_contours(np.pad(cor, 1).astype(float), 0.5)
rings = [tr(dp([(x0 + (c - 1 + .5) * res, y0 - (r - 1 + .5) * res) for r, c in ct], T["corridor"])) for ct in cs if len(ct) > 20]
layers["corridor"] = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {},
                      "geometry": {"type": "Polygon", "coordinates": [rg]}} for rg in rings]}

variants, sites, catch = {}, {}, {}
for v in ("wadi300m", "nowadi"):
    fc = json.load(open(os.path.join(CHK, f"check_sites_{v}.geojson")))
    for f in fc["features"]:
        ring = f["geometry"]["coordinates"][0]
        f["properties"]["_lon"] = round(sum(p[0] for p in ring) / len(ring), 5)
        f["properties"]["_lat"] = round(sum(p[1] for p in ring) / len(ring), 5)
    sites[v] = fc
    cf = []
    for f in fc["features"]:      # approximate catchment: circle, test only
        p = f["properties"]
        rad = 5000 + math.sqrt(p["area_m2"] / math.pi)
        dlat = rad / 111320
        dlon = rad / (111320 * math.cos(math.radians(p["_lat"])))
        cf.append({"type": "Feature", "properties": {"site_id": p["site_id"], "pop_5km": p["pop_5km"]},
                   "geometry": {"type": "Polygon", "coordinates": [[[round(p["_lon"] + dlon * math.cos(t), 5), round(p["_lat"] + dlat * math.sin(t), 5)]
                                                                   for t in np.linspace(0, 2 * math.pi, 41)]]}})
    catch[v] = {"type": "FeatureCollection", "features": cf}
variants = {"wadi300m": {"short": "300 m", "note": "Land within 300 m of a wadi (river, stream) removed"},
            "nowadi": {"short": "off", "note": "No wadi exclusion"}}
meta = dh.meta_block(cfg, variants, "wadi300m")
meta["test_data"] = "numpy check with aspect 0-90 deg, approximate geometry and catchments (not the QGIS result)"
data = {"meta": meta, "layers": layers, "sites": sites, "catchments": catch, "default_basemap": "none"}
html = dh.build_html(data)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w").write(html)
print("wrote", OUT, f"{len(html) / 1e6:.2f} MB")
for k, v in layers.items():
    print(f"  {k:10s} {len(v['features']):6d} features {len(json.dumps(v)) / 1e3:8.0f} kB")
