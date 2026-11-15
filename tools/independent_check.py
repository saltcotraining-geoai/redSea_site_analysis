#!/usr/bin/env python3
"""Independent numpy check of Phase 2 (no QGIS, no GDAL).

Recomputes the site analysis on the Phase 0 rasters with plain numpy/scipy:
Horn slope and aspect (the same formulas as gdaldem), the rule, an approximate
sieve, the 5 km corridor, the optional wadi exclusion, areas, catchment
population and the score factors. Use it as ground truth to compare with
best_locations.gpkg; it is an approximation (raster corridor, no exact clipping).

Needs: numpy, scipy, tifffile, scikit-image, matplotlib.
Run:   python3 tools/independent_check.py <output_root> <out_dir> ['{"aspect_max_deg": 90}']
       (the optional JSON overrides "analysis" settings, to test other criteria)
"""
import json
import math
import os
import sys

import numpy as np
import tifffile
from matplotlib.path import Path
from scipy import ndimage as ndi
from skimage import measure

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gpkg_lite as g  # noqa: E402

ACRE_HA = 0.40468564224


# ------------------------------------------------------------------ UTM 36N -> WGS84
def utm_to_wgs84(x, y, zone=36):
    a, f = 6378137.0, 1 / 298.257223563
    k0, e2 = 0.9996, f * (2 - f)
    ep2 = e2 / (1 - e2)
    x = x - 500000.0
    m = y / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    p1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu) + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
          + (151 * e1 ** 3 / 96) * math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    n1 = a / math.sqrt(1 - e2 * math.sin(p1) ** 2)
    t1, c1 = math.tan(p1) ** 2, ep2 * math.cos(p1) ** 2
    r1 = a * (1 - e2) / (1 - e2 * math.sin(p1) ** 2) ** 1.5
    d = x / (n1 * k0)
    lat = p1 - (n1 * math.tan(p1) / r1) * (d ** 2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * ep2) * d ** 4 / 24
                                           + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * ep2 - 3 * c1 ** 2) * d ** 6 / 720)
    lon = (d - (1 + 2 * t1 + c1) * d ** 3 / 6 + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * ep2 + 24 * t1 ** 2) * d ** 5 / 120) / math.cos(p1)
    return round(math.degrees(lon) + (zone - 1) * 6 - 180 + 3, 5), round(math.degrees(lat), 5)


# ------------------------------------------------------------------ raster io
def read_tif(path):
    t = tifffile.TiffFile(path)
    p = t.pages[0]
    tags = {k.name: k.value for k in p.tags}
    a = p.asarray().astype("float64")
    nd = float(tags["GDAL_NODATA"])
    sx = tags["ModelPixelScaleTag"][0]
    tp = tags["ModelTiepointTag"]
    a[a == nd] = np.nan
    return a, tp[3], tp[4], sx          # array, x0 (left), y0 (top), cell size


def horn(dem, res):
    """gdaldem slope (percent) and aspect (deg from grid north), Horn method."""
    p = np.pad(dem, 1, constant_values=np.nan)
    a, b, c = p[:-2, :-2], p[:-2, 1:-1], p[:-2, 2:]
    d, f = p[1:-1, :-2], p[1:-1, 2:]
    gg, h, i = p[2:, :-2], p[2:, 1:-1], p[2:, 2:]
    dx = ((c + 2 * f + i) - (a + 2 * d + gg)) / (8 * res)
    dy = ((gg + 2 * h + i) - (a + 2 * b + c)) / (8 * res)
    slope = 100 * np.hypot(dx, dy)
    asp = np.degrees(np.arctan2(dy, -dx))
    asp = np.where(asp > 90, 450 - asp, 90 - asp)
    asp[(dx == 0) & (dy == 0)] = np.nan          # flat = NoData, as gdaldem
    asp[asp >= 360] -= 360
    return slope, asp


def rasterize_lines(lines, shape, x0, y0, res, step=None):
    m = np.zeros(shape, bool)
    step = step or res / 3
    for ln in lines:
        for (xa, ya), (xb, yb) in zip(ln, ln[1:]):
            n = max(1, int(math.dist((xa, ya), (xb, yb)) / step))
            t = np.linspace(0, 1, n + 1)
            cs = ((xa + (xb - xa) * t - x0) / res).astype(int)
            rs = ((y0 - (ya + (yb - ya) * t)) / res).astype(int)
            ok = (rs >= 0) & (rs < shape[0]) & (cs >= 0) & (cs < shape[1])
            m[rs[ok], cs[ok]] = True
    return m


def poly_mask(polys, shape, x0, y0, res, only=None):
    """Cell-centre-in-polygon. only: boolean mask limiting the cells tested."""
    m = np.zeros(shape, bool)
    rr, cc = np.nonzero(only) if only is not None else np.indices(shape).reshape(2, -1)
    pts = np.column_stack([x0 + (cc + 0.5) * res, y0 - (rr + 0.5) * res])
    inside = np.zeros(len(pts), bool)
    for rings in polys:
        outer = Path(rings[0]).contains_points(pts)
        for hole in rings[1:]:
            outer &= ~Path(hole).contains_points(pts)
        inside |= outer
    m[rr, cc] = inside
    return m


def sieve(mask, n, structure):
    """Approximate gdal_sieve -nomask on a 0/1 raster: small 1-patches -> 0, small 0-holes -> 1."""
    lab, k = ndi.label(mask, structure)
    sizes = ndi.sum(mask, lab, range(1, k + 1))
    out = mask.copy()
    out[np.isin(lab, np.nonzero(sizes < n)[0] + 1)] = False
    lab0, k0 = ndi.label(~out, structure)
    sizes0 = ndi.sum(~out, lab0, range(1, k0 + 1))
    out[np.isin(lab0, np.nonzero(sizes0 < n)[0] + 1)] = True
    return out


# ------------------------------------------------------------------ main
def main(root, out_dir, overrides=None):
    cfg = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")))
    cfg["analysis"].update(overrides or {})
    A, X = cfg["analysis"], cfg["exclusions"]["wadi_buffer"]
    os.makedirs(out_dir, exist_ok=True)
    rd = lambda n: os.path.join(root, "02_Raw_data", n + ".gpkg")

    dem, x0, y0, res = read_tif(os.path.join(root, "03_Rasters", cfg["raster"]["dem_output_utm"] + ".tif"))
    pop, px0, py0, pres = read_tif(os.path.join(root, "03_Rasters", cfg["raster"]["population_output"] + ".tif"))
    shape = dem.shape
    cell_ha = res * res / 1e4
    st4 = ndi.generate_binary_structure(2, 1 if A["connectedness"] == 4 else 2)

    slope, asp = horn(dem, res)
    rule = ((slope >= A["slope_percent_min"]) & (slope <= A["slope_percent_max"])
            & (asp >= A["aspect_min_deg"]) & (asp <= A["aspect_max_deg"]))
    print(f"rule cells {rule.sum():,} = {rule.sum() * cell_ha:,.0f} ha")
    sv = sieve(rule, A["sieve_threshold_cells"], st4)
    print(f"sieved cells {sv.sum():,}")

    state = [g.polygons(f["geom"]) for f in g.read(os.path.join(root, "01_Data", "redSea_state.gpkg"))][0]
    rails = [ln for f in g.read(rd("redSea_railways")) for ln in g.lines(f["geom"])]
    roads = [ln for f in g.read(rd("redSea_roads")) for ln in g.lines(f["geom"])]
    rivers = [ln for f in g.read(rd("redSea_rivers")) for ln in g.lines(f["geom"])]
    towns = {f["NAME"]: (f["geom"][1][0][1] if f["geom"][0] == "MultiPoint" else f["geom"][1])
             for f in g.read(rd("redSea_towns"))}

    rail_d = ndi.distance_transform_edt(~rasterize_lines(rails, shape, x0, y0, res)) * res
    road_d = ndi.distance_transform_edt(~rasterize_lines(roads, shape, x0, y0, res)) * res
    corridor = rail_d <= A["corridor_buffer_m"]
    inside = poly_mask(state, shape, x0, y0, res, only=corridor)
    corridor &= inside
    print(f"corridor {corridor.sum() * cell_ha:,.0f} ha")
    wadi = ndi.distance_transform_edt(~rasterize_lines(rivers, shape, x0, y0, res)) * res <= X["distance_m"]

    base = sv & corridor
    variants = {"nowadi": base, f"wadi{X['distance_m']}m": base & ~wadi}
    min_cells = A["min_site_acres"] * ACRE_HA / cell_ha
    port = towns.get("Port Sudan")
    summary = {}
    for vname, m in variants.items():
        lab, k = ndi.label(m, st4)
        objs = ndi.find_objects(lab)
        feats = []
        sid = 0
        for li, sl in enumerate(objs, start=1):
            cm = lab[sl] == li
            n = int(cm.sum())
            if n <= min_cells:
                continue
            sid += 1
            rr, cc = np.nonzero(cm)
            rr, cc = rr + sl[0].start, cc + sl[1].start
            cx, cy = x0 + (cc.mean() + 0.5) * res, y0 - (rr.mean() + 0.5) * res
            # outer boundary -> polygon (marching squares on the padded patch)
            pad = np.pad(cm, 1).astype(float)
            cont = max(measure.find_contours(pad, 0.5), key=len)
            ring = [(x0 + (sl[1].start + c - 1 + 0.5) * res, y0 - (sl[0].start + r - 1 + 0.5) * res) for r, c in cont]
            area_m2 = n * res * res
            per = sum(math.dist(p, q) for p, q in zip(ring, ring[1:]))
            # 5 km catchment population: pop cells whose centre lies within 5 km of the site cells
            mg = int(A["catchment_buffer_m"] / res) + 2
            r0, r1 = max(0, sl[0].start - mg), min(shape[0], sl[0].stop + mg)
            c0, c1 = max(0, sl[1].start - mg), min(shape[1], sl[1].stop + mg)
            sub = lab[r0:r1, c0:c1] == li
            dsub = ndi.distance_transform_edt(~sub) * res <= A["catchment_buffer_m"]
            pr0 = int((py0 - (y0 - r1 * res)) / pres) + 1
            pr_a, pr_b = max(0, int((py0 - (y0 - r0 * res)) / pres)), min(pop.shape[0], pr0)
            pc_a = max(0, int(((x0 + c0 * res) - px0) / pres))
            pc_b = min(pop.shape[1], int(((x0 + c1 * res) - px0) / pres) + 1)
            psum = 0.0
            for pr in range(pr_a, pr_b):
                for pc in range(pc_a, pc_b):
                    v = pop[pr, pc]
                    if np.isnan(v):
                        continue
                    ex, ey = px0 + (pc + 0.5) * pres, py0 - (pr + 0.5) * pres
                    rr_, cc_ = int((y0 - ey) / res) - r0, int((ex - x0) / res) - c0
                    if 0 <= rr_ < dsub.shape[0] and 0 <= cc_ < dsub.shape[1] and dsub[rr_, cc_]:
                        psum += v
            ri, ci = int((y0 - cy) / res), int((cx - x0) / res)
            props = {
                "site_id": sid,
                "area_m2": round(area_m2, 1), "area_ha": round(area_m2 / 1e4, 2),
                "area_acres": round(area_m2 / 4046.8564224, 1),
                "pop_5km": int(round(psum)),
                "dist_road_m": round(float(road_d[ri, ci]), 1),
                "dist_rail_m": round(float(rail_d[ri, ci]), 1),
                "dist_port_km": round(math.dist((cx, cy), port) / 1000, 2) if port else None,
                "compactness": round(4 * math.pi * area_m2 / per ** 2, 4) if per else None,
                "slope_mean": round(float(np.nanmean(slope[rr, cc])), 2),
                "aspect_mean": round(float(np.nanmean(asp[rr, cc])), 1),
            }
            feats.append({"type": "Feature", "properties": props,
                          "geometry": {"type": "Polygon", "coordinates": [[list(utm_to_wgs84(x, y)) for x, y in ring[::2] + [ring[0]]]]}})
        tot = sum(f["properties"]["area_ha"] for f in feats)
        summary[vname] = {"n_sites": len(feats), "total_ha": round(tot, 1)}
        print(f"[{vname}] {len(feats)} sites, {tot:,.0f} ha")
        with open(os.path.join(out_dir, f"check_sites_{vname}.geojson"), "w") as fh:
            json.dump({"type": "FeatureCollection", "features": feats}, fh)
    summary["settings"] = {k: A[k] for k in ("slope_percent_min", "slope_percent_max", "aspect_min_deg", "aspect_max_deg",
                                             "sieve_threshold_cells", "min_site_acres", "corridor_buffer_m")}
    json.dump(summary, open(os.path.join(out_dir, "check_summary.json"), "w"), indent=2)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], json.loads(sys.argv[3]) if len(sys.argv) > 3 else None)
