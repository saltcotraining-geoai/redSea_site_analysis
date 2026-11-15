#!/usr/bin/python3
"""Phase 0 - data preparation for the Sudan site analysis (Red Sea State).

Study area -> fix -> clip vectors -> clip + reproject DEM -> clip population.
Every step logs the QGIS tool, its GUI path and its Processing ID.

Run:  /usr/bin/python3 phase0_prepare.py [config.json]
"""
import os
import sys

from sudan_common import (StepLog, check_stale, data_path, exit_qgis, init_qgis, load_config,
                          out_path, phase0_fingerprint, run_alg, use_run, write_manifest)

POLYGON_LAYERS = {"admin1_states", "admin2_districts", "water_bodies", "natural_areas"}


def main(cfg_path=None):
    cfg = load_config(cfg_path)
    init_qgis()
    from qgis.core import QgsRasterLayer, QgsVectorLayer
    import processing  # noqa: F401  (registers algorithms)

    P, A = cfg["paths"], cfg["crs"]["analysis"]
    vin = lambda name: data_path(cfg, P["input_vector_dir"], name + ".gpkg")
    work = lambda name: out_path(cfg, "clipped_inputs_dir", "_work_" + name)
    use_run(cfg, "none")       # prepared inputs are shared by all runs; only the log goes into the run folder
    log = StepLog(cfg, "phase0")
    outputs = {}

    fp = phase0_fingerprint(cfg)
    log.write(f"profile: {cfg['_profile']}  |  prepared inputs (shared by all runs): {cfg['paths']['output_root']}")
    log.write(f"settings fingerprint: {fp}")

    # ---------------------------------------------------------- 1. study area
    sa = cfg["study_area"]
    fixed = run_alg(log, "Fix Geometries", "Processing Toolbox > Vector geometry > Fix geometries",
                    "native:fixgeometries", {"INPUT": vin(sa["layer"]), "OUTPUT": "TEMPORARY_OUTPUT"})["OUTPUT"]
    state = out_path(cfg, "outputs_dir", sa["output"])
    run_alg(log, "Extract by Expression", "Processing Toolbox > Vector selection > Extract by expression",
            "native:extractbyexpression",
            {"INPUT": fixed, "EXPRESSION": sa["expression"], "OUTPUT": state}, detail=sa["expression"])
    n = QgsVectorLayer(state, "s", "ogr").featureCount()
    if n != 1:
        sys.exit(f"Study area expected 1 feature, got {n}. Check {sa['expression']}")
    outputs["study_area"] = state

    # ---------------------------------------------------------- 2. masks with margins
    R = cfg["raster"]
    masks = {}
    for key, margin in (("dem", R["dem_clip_margin_m"]), ("pop", R["population_clip_margin_m"])):
        masks[key] = work(f"mask_{key}_{margin}m")
        run_alg(log, "Buffer", "Vector > Geoprocessing Tools > Buffer", "native:buffer",
                {"INPUT": state, "DISTANCE": margin, "SEGMENTS": 8, "END_CAP_STYLE": 0, "JOIN_STYLE": 0,
                 "MITER_LIMIT": 2, "DISSOLVE": True, "OUTPUT": masks[key]},
                detail=f"{margin} m margin for the {key} clip mask")

    # ---------------------------------------------------------- 3. vector layers
    for key, v in cfg["vector_layers"].items():
        if not v.get("enabled", True):
            log.write(f"\n-- skip {key} (enabled = false)")
            continue
        src = vin(v["source"])
        if v.get("expression"):
            src = run_alg(log, "Extract by Expression", "Processing Toolbox > Vector selection > Extract by expression",
                          "native:extractbyexpression",
                          {"INPUT": src, "EXPRESSION": v["expression"], "OUTPUT": "TEMPORARY_OUTPUT"},
                          detail=f"{key}: {v['expression']}")["OUTPUT"]
        if v["source"] in POLYGON_LAYERS:
            src = run_alg(log, "Fix Geometries", "Processing Toolbox > Vector geometry > Fix geometries",
                          "native:fixgeometries", {"INPUT": src, "OUTPUT": "TEMPORARY_OUTPUT"},
                          detail=key)["OUTPUT"]
        dst = out_path(cfg, "clipped_inputs_dir", v["output"])

        if v["method"] == "clip":
            run_alg(log, "Clip", "Vector > Geoprocessing Tools > Clip", "native:clip",
                    {"INPUT": src, "OVERLAY": state, "OUTPUT": dst}, detail=key)
        else:  # select_by_location: keep whole features (districts, towns)
            lyr = src if not isinstance(src, str) else QgsVectorLayer(src, key, "ogr")
            run_alg(log, "Select by Location", "Vector > Research Tools > Select by Location",
                    "native:selectbylocation",
                    {"INPUT": lyr, "PREDICATE": [0], "INTERSECT": state, "METHOD": 0}, detail=f"{key}: intersects")
            run_alg(log, "Save Selected Features", "Processing Toolbox > Vector general > Save selected features",
                    "native:saveselectedfeatures", {"INPUT": lyr, "OUTPUT": dst}, detail=key)
        # No Create Spatial Index here: Processing already builds the GeoPackage
        # R-tree when it writes the file (running it again gives "already existing").
        # native:createspatialindex is used in Phase 2 on memory layers.
        outputs[key] = dst

    # ---------------------------------------------------------- 4. DEM to UTM 36N
    # brief: clip (4326, +margin) -> warp (bilinear, 180 m)       - fast, smooth slope
    # class: warp the whole Sudan DEM (nearest, automatic 181.4 m) -> clip to the state
    #        - what the class ran on 18 Oct 2026, so the grid and values match its rasters
    RESAMPLING = {"nearest": 0, "bilinear": 1, "cubic": 2, "cubicspline": 3, "lanczos": 4, "average": 5}
    rs_name = R.get("dem_resampling", "bilinear")
    rs_code = RESAMPLING[rs_name]
    res_m = R.get("dem_target_resolution_m")
    res_txt = f"{res_m} m cells" if res_m else "automatic resolution (Warp's default, about 181.4 m here)"
    dem_utm = out_path(cfg, "rasters_dir", R["dem_output_utm"], ".tif")

    def fresh(path):
        # gdalwarp writes INTO an existing file instead of replacing it, so remove old outputs first
        for p in (path, path + ".aux.xml"):
            if os.path.exists(p):
                os.remove(p)

    def warp(src, dst, detail, as_class=False):
        fresh(dst)
        run_alg(log, "Warp (Reproject)", "Raster > Projections > Warp (Reproject)", "gdal:warpreproject",
                {"INPUT": src, "SOURCE_CRS": cfg["crs"]["dem_source"] if as_class else None, "TARGET_CRS": A,
                 "RESAMPLING": rs_code, "NODATA": None if as_class else R["dem_nodata"],
                 "TARGET_RESOLUTION": res_m, "OPTIONS": "", "DATA_TYPE": 0, "TARGET_EXTENT": None,
                 "TARGET_EXTENT_CRS": None, "MULTITHREADING": not as_class, "EXTRA": "", "OUTPUT": dst},
                detail=detail + (" | class parameters: Source CRS EPSG:4326, NoData blank, multithreading off"
                                 if as_class else ""))
        valid_or_stop(dst, "Warp")

    def valid_or_stop(path, step):
        from qgis.core import Qgis, QgsRasterBandStats
        r = QgsRasterLayer(path, "chk")
        try:
            st = r.dataProvider().bandStatistics(1, Qgis.RasterBandStatistic.All)
        except (AttributeError, TypeError):
            st = r.dataProvider().bandStatistics(1, QgsRasterBandStats.All)
        log.write(f"     check: {st.elementCount:,} valid cells, min {st.minimumValue:.0f} max {st.maximumValue:.0f} m")
        if st.elementCount == 0:
            sys.exit(f"STOP: {os.path.basename(path)} has no valid cells after {step}. "
                     f"See the GDAL lines (! and >) above. Delete {os.path.dirname(path)} and re-run.")

    def clip(src, mask, dst, detail):
        fresh(dst)
        run_alg(log, "Clip Raster by Mask Layer", "Raster > Extraction > Clip Raster by Mask Layer",
                "gdal:cliprasterbymasklayer",
                {"INPUT": src, "MASK": mask, "SOURCE_CRS": None, "TARGET_CRS": None,
                 "NODATA": R["dem_nodata"], "ALPHA_BAND": False, "CROP_TO_CUTLINE": True, "KEEP_RESOLUTION": True,
                 "SET_RESOLUTION": False, "MULTITHREADING": True, "OPTIONS": "", "DATA_TYPE": 0, "EXTRA": "",
                 "OUTPUT": dst}, detail=detail)
        valid_or_stop(dst, "Clip")

    dem_mask = masks["dem"] if R["dem_clip_margin_m"] > 0 else state
    order = R.get("dem_warp_order", "clip_then_warp")
    if order == "use_class_dem":
        import shutil
        src = os.path.expanduser(R["dem_class_file"])
        if not os.path.exists(src):
            sys.exit(f"STOP: class DEM not found: {src}. Set raster.dem_warp_order to class_grid or warp_then_clip.")
        t0 = log.step("Copy the class DEM", "(none - the class already ran Warp + Clip on 18 Oct)", "-",
                      f"{src}: whole Sudan warped with Nearest (automatic 181.4 m), clipped to the state")
        fresh(dem_utm)
        shutil.copyfile(src, dem_utm)
        log.done(t0, dem_utm)
        valid_or_stop(dem_utm, "copy")
    elif order == "class_grid":
        # 1) clip the 4326 DEM with a 2 km margin (so the warp has source cells at the edges)
        # 2) warp only that clip, Nearest, onto the class grid (fixed cell size + extent)
        # 3) clip to the state itself, as in class
        g = R["dem_class_grid"]
        x_max = g["x_min"] + g["cols"] * g["cell_m"]
        y_min = g["y_max"] - g["rows"] * g["cell_m"]
        m2k = work("mask_dem_2000m")
        run_alg(log, "Buffer", "Vector > Geoprocessing Tools > Buffer", "native:buffer",
                {"INPUT": state, "DISTANCE": 2000, "SEGMENTS": 8, "END_CAP_STYLE": 0, "JOIN_STYLE": 0,
                 "MITER_LIMIT": 2, "DISSOLVE": True, "OUTPUT": m2k}, detail="2000 m margin for the 4326 DEM clip")
        dem_clip = out_path(cfg, "rasters_dir", R["dem_output_clip"], ".tif")
        clip(data_path(cfg, P["dem"]), m2k, dem_clip, "Red Sea only, still in EPSG:4326 (fast)")
        grid_utm = out_path(cfg, "rasters_dir", "_work_dem_classgrid", ".tif")
        fresh(grid_utm)
        run_alg(log, "Warp (Reproject)", "Raster > Projections > Warp (Reproject)", "gdal:warpreproject",
                {"INPUT": dem_clip, "SOURCE_CRS": cfg["crs"]["dem_source"], "TARGET_CRS": A, "RESAMPLING": rs_code,
                 "NODATA": None, "TARGET_RESOLUTION": g["cell_m"], "OPTIONS": "", "DATA_TYPE": 0,
                 "TARGET_EXTENT": f"{g['x_min']},{x_max},{y_min},{g['y_max']} [{A}]", "TARGET_EXTENT_CRS": A,
                 "MULTITHREADING": False, "EXTRA": "", "OUTPUT": grid_utm},
                detail=f"{rs_name}, {g['cell_m']:.4f} m, extent = the class grid ({g['cols']} x {g['rows']} cells)")
        valid_or_stop(grid_utm, "Warp")
        clip(grid_utm, state, dem_utm, "Keep resolution = on, mask = the state itself (no margin), as in class")
    elif order == "warp_then_clip":
        sdn_utm = out_path(cfg, "rasters_dir", "_work_sdn_dem_utm36n", ".tif")
        warp(data_path(cfg, P["dem"]), sdn_utm,
             f"whole Sudan DEM, {rs_name}, {res_txt} (as in class; about 400 MB)", as_class=True)
        clip(sdn_utm, dem_mask, dem_utm,
             "Keep resolution = on: the clipped grid stays aligned with the warped one"
             + ("" if R["dem_clip_margin_m"] > 0 else "; mask = the state itself (no margin), as in class"))
    else:
        dem_clip = out_path(cfg, "rasters_dir", R["dem_output_clip"], ".tif")
        clip(data_path(cfg, P["dem"]), dem_mask, dem_clip,
             f"DEM stays in {cfg['crs']['dem_source']} for the clip (cheaper than warping all of Sudan)")
        warp(dem_clip, dem_utm, f"{rs_name}, {res_txt}, before Slope and Aspect")
    outputs["dem_utm"] = dem_utm

    # ---------------------------------------------------------- 5. population (already UTM 36N)
    pop = out_path(cfg, "rasters_dir", R["population_output"], ".tif")
    run_alg(log, "Clip Raster by Mask Layer", "Raster > Extraction > Clip Raster by Mask Layer",
            "gdal:cliprasterbymasklayer",
            {"INPUT": data_path(cfg, P["population"]), "MASK": masks["pop"], "SOURCE_CRS": None, "TARGET_CRS": None,
             "NODATA": R["population_nodata"], "ALPHA_BAND": False, "CROP_TO_CUTLINE": True,
             "KEEP_RESOLUTION": True, "SET_RESOLUTION": False, "MULTITHREADING": True, "OPTIONS": "",
             "DATA_TYPE": 0, "EXTRA": "", "OUTPUT": pop},
            detail=R["population_margin_note"])
    outputs["population"] = pop

    # ---------------------------------------------------------- 6. checks
    log.write("\n== Checks")
    for key, p in outputs.items():
        if p.endswith(".gpkg"):
            lyr = QgsVectorLayer(p, key, "ogr")
            log.write(f"  {key:14s} {lyr.featureCount():>9,} features  {lyr.crs().authid()}")
        else:
            r = QgsRasterLayer(p, key)
            log.write(f"  {key:14s} {r.width()} x {r.height()} px  {r.rasterUnitsPerPixelX():.1f} m  {r.crs().authid()}")
    rail = QgsVectorLayer(outputs["railways"], "r", "ogr")
    km = sum(f.geometry().length() for f in rail.getFeatures()) / 1000
    log.write(f"  railway length in Red Sea: {km:.1f} km (stdlib check found 420.0 km, 159 features)")
    if abs(km - 420.0) > 5:
        log.write("  WARNING: railway length differs from the stdlib check by more than 5 km")

    write_manifest(cfg, "phase0", fp, outputs)
    check_stale(cfg, "phase0", fp)
    log.write(f"\nPhase 0 done. Log: {log.path}")
    log.close()


if __name__ == "__main__":
    import traceback
    code = 1
    try:
        main(sys.argv[1] if len(sys.argv) > 1 else None)
        code = 0
    except SystemExit as e:          # e.g. study area not found
        print(e, file=sys.stderr)
    except Exception:                # os._exit would otherwise hide the traceback
        traceback.print_exc()
    finally:
        exit_qgis(code)
