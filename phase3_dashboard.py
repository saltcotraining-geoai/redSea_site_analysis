#!/usr/bin/python3
"""Phase 3 - live dashboard and web map (Leaflet, one self-contained HTML page).

Simplify (UTM, metres) -> save as GeoJSON in EPSG:4326 (RFC 7946) -> clean for
Leaflet -> embed in output/dashboard/index.html. The score, factor toggles,
weights, scenarios and the wadi switch run live in the browser (same rules as
scoring.py). Only Leaflet comes from a CDN.

Run:  /usr/bin/python3 phase3_dashboard.py [config.json]
"""
import json
import os
import sys

from sudan_common import (StepLog, check_stale, data_path, exit_qgis, init_qgis, load_config, manifest_path, out_path,
                          phase0_fingerprint, remap_output, run_alg, use_run, wgs84)
import dashboard_html as dh


def normalize_for_leaflet(fc, kind):
    """Leaflet 1.9 crashes on GeometryCollection / empty geometries: keep only parts of `kind`."""
    want = {"polygon": ("Polygon", "MultiPolygon"), "line": ("LineString", "MultiLineString"),
            "point": ("Point", "MultiPoint")}[kind]
    multi = want[1]
    out = []
    for f in fc.get("features", []):
        g = f.get("geometry")
        if not g:
            continue
        if g["type"] == "GeometryCollection":
            parts = []
            for p in g.get("geometries", []):
                if p["type"] == want[0]:
                    parts.append(p["coordinates"])
                elif p["type"] == multi:
                    parts.extend(p["coordinates"])
            if not parts:
                continue
            g = {"type": multi, "coordinates": parts}
        if g["type"] not in want or not g.get("coordinates"):
            continue
        f["geometry"] = g
        out.append(f)
    fc["features"] = out
    fc.pop("name", None)
    fc.pop("crs", None)
    return fc


def main(cfg_path=None):
    cfg = load_config(cfg_path)
    init_qgis()
    from qgis.core import (QgsCoordinateTransform, QgsProject, QgsVectorFileWriter, QgsVectorLayer)

    P, P3, S = cfg["paths"], cfg["phase3"], cfg["crs"]["analysis"]
    use_run(cfg, "latest")
    log = StepLog(cfg, "phase3")
    log.write(f"run folder: {P['run_root']}")
    man_path = manifest_path(cfg, "phase2")
    if not os.path.exists(man_path):
        sys.exit("No phase2_manifest.json - run phase2_analysis.py first.")
    with open(man_path, encoding="utf-8") as fh:
        man = json.load(fh)
    res2 = man["outputs"]            # write_manifest() nests the phase results under "outputs"
    res2["corridor"] = remap_output(cfg, res2["corridor"])     # manifest may come from another computer
    for v in res2["variants"].values():
        for k in ("sites", "population", "candidates", "table"):
            v[k] = remap_output(cfg, v[k])
    if man.get("fingerprint") != phase0_fingerprint(cfg):
        log.write("WARNING: Phase 2 was built from other Phase 0 settings - re-run Phase 2.")
    check_stale(cfg, "phase0", phase0_fingerprint(cfg))

    out_dir = os.path.join(P["run_root"], os.path.dirname(P3["output_html"]))
    data_dir = os.path.join(out_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    prec = P3["coordinate_precision"]
    tol = P3["simplify_tolerance_m"]
    raw = lambda n: out_path(cfg, "clipped_inputs_dir", n)

    def save_vector(layer, name, fields=None, rename=None):
        """GeoJSON in EPSG:4326 via options.ct (layer stays in UTM; fixes the targetCrs pitfall)."""
        if isinstance(layer, str):
            layer = QgsVectorLayer(layer, name, "ogr")
        path = os.path.join(data_dir, name + ".geojson")
        if os.path.exists(path):
            os.remove(path)
        o = QgsVectorFileWriter.SaveVectorOptions()
        o.driverName = "GeoJSON"
        o.fileEncoding = "UTF-8"
        o.layerOptions = ["RFC7946=YES", f"COORDINATE_PRECISION={prec}", "WRITE_BBOX=NO"]
        o.ct = QgsCoordinateTransform(layer.crs(), wgs84(), QgsProject.instance())
        if fields is not None:
            o.attributes = [layer.fields().indexOf(f) for f in fields if layer.fields().indexOf(f) >= 0]
        err = QgsVectorFileWriter.writeAsVectorFormatV3(layer, path, QgsProject.instance().transformContext(), o)
        if err[0] != QgsVectorFileWriter.NoError:
            raise RuntimeError(f"save_vector {name}: {err[1]}")
        with open(path, encoding="utf-8") as fh:
            fc = json.load(fh)
        if rename:
            for f in fc["features"]:
                for a, b in rename.items():
                    if a in f["properties"]:
                        f["properties"][b] = f["properties"].pop(a)
        return fc

    def simplify(src, t, label):
        return run_alg(log, "Simplify", "Vector > Geometry Tools > Simplify", "native:simplifygeometries",
                       {"INPUT": src, "METHOD": 0, "TOLERANCE": t, "OUTPUT": "TEMPORARY_OUTPUT"},
                       detail=f"{label}: Douglas-Peucker {t} m (in UTM, before reprojecting)")["OUTPUT"]

    def export(src, name, kind, t, fields=None, rename=None):
        lyr = simplify(src, t, name) if t else src
        t0 = log.step("Save Vector Features (GeoJSON, EPSG:4326)", "Layer > Export > Save Features As... [RFC7946, CRS EPSG:4326]",
                      "QgsVectorFileWriter.writeAsVectorFormatV3", f"{name}: precision {prec} decimals")
        fc = normalize_for_leaflet(save_vector(lyr, name, fields, rename), kind)
        log.done(t0, name + ".geojson", len(fc["features"]))
        return fc

    VL = cfg["vector_layers"]
    layers = {}
    layers["states"] = export(data_path(cfg, P["input_vector_dir"], cfg["study_area"]["layer"] + ".gpkg"),
                              "states", "polygon", tol["states"], ["adm1_name"], {"adm1_name": "name"})
    layers["red_sea"] = export(out_path(cfg, "outputs_dir", cfg["study_area"]["output"]), "red_sea", "polygon",
                               tol["states"] / 5, [])
    layers["districts"] = export(raw(VL["districts"]["output"]), "districts", "polygon", tol["districts"],
                                 ["adm2_name"], {"adm2_name": "name"})
    roads = run_alg(log, "Extract by Expression", "Processing Toolbox > Vector selection > Extract by expression",
                    "native:extractbyexpression",
                    {"INPUT": raw(VL["roads"]["output"]), "EXPRESSION": P3["roads_expression"], "OUTPUT": "TEMPORARY_OUTPUT"},
                    detail=P3["roads_note"])["OUTPUT"]
    layers["roads"] = export(roads, "roads", "line", tol["roads"], ["fclass"])
    layers["rivers"] = export(raw(VL["rivers"]["output"]), "rivers", "line", tol["rivers"], ["fclass"])
    layers["railways"] = export(raw(VL["railways"]["output"]), "railways", "line", 25, [])
    layers["towns"] = export(raw(VL["towns"]["output"]), "towns", "point", 0, ["NAME", "POP_MAX"],
                             {"NAME": "name", "POP_MAX": "pop"})
    layers["corridor"] = export(res2["corridor"], "corridor", "polygon", tol["corridor"], [])

    # ---------------------------------------------------------- sites and catchments per variant
    keep = ["site_id", "area_m2", "area_ha", "area_acres", "area_ell_m2", "planar_vs_ell_pct", "pop_5km",
            "slope_mean", "aspect_mean", "class_kept", "pop_5km_gross"] + [f["field"] for f in cfg["scoring"]["factors"].values()]
    keep = list(dict.fromkeys(keep))
    sites, catch, vinfo = {}, {}, {}
    wx = cfg["exclusions"]["wadi_buffer"]
    for v, res in res2["variants"].items():
        sl = QgsVectorLayer(res["sites"], v, "ogr")
        fc = export(sl, f"sites_{v}", "polygon", tol["sites"], keep)
        # marker position: a point inside each site (point on surface), in WGS84
        ct = QgsCoordinateTransform(sl.crs(), wgs84(), QgsProject.instance())
        pos = {}
        for f in sl.getFeatures():
            pt = f.geometry().pointOnSurface().asPoint()
            q = ct.transform(pt)
            pos[f["site_id"]] = (round(q.x(), prec), round(q.y(), prec))
        for f in fc["features"]:
            f["properties"]["_lon"], f["properties"]["_lat"] = pos[f["properties"]["site_id"]]
        sites[v] = fc
        catch[v] = export(res["population"], f"catchments_{v}", "polygon", tol["catchments"], ["site_id", "pop_5km"])
        if v == "nowadi":
            vinfo[v] = {"short": "off", "note": "No wadi exclusion"}
        else:
            vinfo[v] = {"short": f"{wx['distance_m']} m",
                        "note": f"Land within {wx['distance_m']} m of a wadi removed ({wx.get('expression') or 'all waterways'})"}
        log.write(f"     {v}: {len(fc['features'])} sites")

    # ---------------------------------------------------------- page
    t0 = log.step("Build dashboard page", "Python (dashboard_html.py)", "-",
                  "one HTML file, data embedded, Leaflet from CDN, scoring in the browser")
    meta = dh.meta_block(cfg, vinfo, res2["main_variant"])
    data = {"meta": meta, "layers": layers, "sites": sites, "catchments": catch,
            "default_basemap": P3.get("default_basemap", "none"),
            "custom_tiles": custom_tiles(cfg, log, os.path.dirname(os.path.join(P["run_root"], P3["output_html"])))}
    if data["custom_tiles"] is None and data["default_basemap"] == "custom":
        data["default_basemap"] = "none"
    html = dh.build_html(data, P3.get("leaflet_version", "1.9.4"), P3.get("sri_check", True))
    html_path = os.path.join(P["run_root"], P3["output_html"])
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    log.done(t0, html_path)
    log.write(f"     size {len(html.encode()) / 1e6:.2f} MB  (layers also in {data_dir})")
    for k, fc in layers.items():
        log.write(f"     {k:10s} {len(fc['features']):6,} features")
    log.write(f"\nPhase 3 done. Open: {html_path}\nLog: {log.path}")
    log.close()


def custom_tiles(cfg, log, html_dir):
    """Local XYZ tiles (z/x/y.png from QGIS 'Generate XYZ tiles (Directory)') as a basemap.

    mode "link": the page points to the tile folder with a relative path - nothing is copied,
                 but the page only shows the tiles on a computer that has that folder.
    mode "copy": the tiles are copied once to <output_root>/tiles (about 333 MB), shared by all
                 runs, so the whole output folder can be moved (USB, another laptop) as one piece.
    """
    import shutil
    ct = cfg["phase3"].get("custom_tiles") or {}
    if not ct.get("enabled"):
        return None
    t0 = log.step("Local XYZ tiles as basemap", "Processing Toolbox > Raster tools > Generate XYZ tiles (Directory) - made in class",
                  "-", f"mode = {ct.get('mode', 'link')}")
    src = os.path.expanduser(ct["path"])
    zooms = sorted(int(d) for d in os.listdir(src) if d.isdigit()) if os.path.isdir(src) else []
    if not zooms:
        log.write(f"     ! no z/x/y tiles in {src} - local basemap left out")
        return None
    if ct.get("mode", "link") == "copy":
        dst = os.path.join(cfg["paths"]["output_root"], "tiles")      # one shared copy, not 333 MB per run
        if not os.path.isdir(dst):
            shutil.copytree(src, dst)
        rel = os.path.relpath(dst, html_dir).replace(os.sep, "/")
    else:
        rel = os.path.relpath(src, html_dir).replace(os.sep, "/")
    n = sum(len(fs) for _, _, fs in os.walk(src))
    # extent of the tiles (from the deepest zoom), so the map does not ask for tiles that were never made
    import math
    z = zooms[-1]
    zdir = os.path.join(src, str(z))
    xs = [int(d) for d in os.listdir(zdir) if d.isdigit()]
    ys = [int(f.split(".")[0]) for x in (min(xs), max(xs), xs[len(xs) // 2]) for f in os.listdir(os.path.join(zdir, str(x)))
          if f.split(".")[0].isdigit()]
    lon = lambda x: x / 2 ** z * 360 - 180
    lat = lambda y: math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / 2 ** z))))
    bounds = [[round(lat(max(ys) + 1), 4), round(lon(min(xs)), 4)], [round(lat(min(ys)), 4), round(lon(max(xs) + 1), 4)]]
    log.done(t0, rel)
    log.write(f"     {n:,} tiles, zoom {zooms[0]}-{zooms[-1]} (deeper zooms enlarge zoom {zooms[-1]}); "
              f"extent lat {bounds[0][0]} to {bounds[1][0]}, lon {bounds[0][1]} to {bounds[1][1]}")
    return {"url": rel + "/{z}/{x}/{y}.png", "label": ct.get("label", "Local tiles"), "min_zoom": zooms[0],
            "max_zoom": zooms[-1], "bounds": bounds, "attribution": ct.get("attribution", "")}


if __name__ == "__main__":
    import traceback
    code = 1
    try:
        main(sys.argv[1] if len(sys.argv) > 1 else None)
        code = 0
    except SystemExit as e:
        print(e, file=sys.stderr)
    except Exception:
        traceback.print_exc()
    finally:
        exit_qgis(code)
