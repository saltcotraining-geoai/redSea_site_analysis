#!/usr/bin/python3
"""Phase 2 - site analysis for Red Sea State.

Corridor -> slope % / aspect -> rule raster -> sieve -> polygonize -> invalid-patch check
(fix or skip) -> dissolve -> intersection (brief) or join by location (class) -> wadi exclusion -> areas -> > 150 acres
-> 5 km catchment population -> criteria check -> score factors (switches)
-> combined score, rank and weight-sensitivity table.

Every step logs the QGIS tool, its GUI path and its Processing ID.
Run:  /usr/bin/python3 phase2_analysis.py [config.json]
"""
import csv
import os
import sys

from sudan_common import (StepLog, check_stale, exit_qgis, init_qgis, load_config, mark_latest, no_check_context,
                          out_path, phase0_fingerprint, run_alg, run_path, save_run_config, use_run, write_manifest)

ACRE_M2 = 4046.8564224
T = "TEMPORARY_OUTPUT"


def main(cfg_path=None):
    cfg = load_config(cfg_path)
    init_qgis()
    from qgis.core import (Qgis, QgsCoordinateReferenceSystem, QgsDistanceArea, QgsProject,
                           QgsRasterBandStats, QgsRasterLayer, QgsVectorLayer)

    A, S = cfg["analysis"], cfg["crs"]["analysis"]
    use_run(cfg, "new")
    save_run_config(cfg)
    log = StepLog(cfg, "phase2")
    log.write(f"profile: {cfg['_profile']}  |  run folder: {cfg['paths']['run_root']}")

    # Processing takes the ellipsoid for $area from the project, so set it here
    # (a standalone script has no project settings otherwise).
    proj = QgsProject.instance()
    proj.setCrs(QgsCoordinateReferenceSystem(S))
    proj.setEllipsoid(A["ellipsoid"])
    proj.setAreaUnits(Qgis.AreaUnit.SquareMeters)

    if check_stale(cfg, "phase0", phase0_fingerprint(cfg)):
        log.write("WARNING: Phase 0 outputs do not match the current settings - results may be out of date.")

    raw = lambda n: out_path(cfg, "clipped_inputs_dir", n)          # prepared inputs (shared)
    o1 = lambda n: run_path(cfg, "outputs_dir", n)                   # this run
    ras = lambda n: run_path(cfg, "rasters_dir", n, ".tif")          # this run
    dem = out_path(cfg, "rasters_dir", cfg["raster"]["dem_output_utm"], ".tif")
    pop = out_path(cfg, "rasters_dir", cfg["raster"]["population_output"], ".tif")
    eight = A["connectedness"] == 8

    def raster_cells(path, label):
        r = QgsRasterLayer(path, label)
        import warnings
        with warnings.catch_warnings():        # bandStatistics() is flagged deprecated in 3.40 but still correct;
            warnings.simplefilter("ignore", DeprecationWarning)   # it is only used for this log check
            try:
                st = r.dataProvider().bandStatistics(1, Qgis.RasterBandStatistic.All)
            except (AttributeError, TypeError):
                st = r.dataProvider().bandStatistics(1, QgsRasterBandStats.All)
        cell_ha = r.rasterUnitsPerPixelX() * r.rasterUnitsPerPixelY() / 1e4
        log.write(f"     check: {st.elementCount:,} valid cells = {st.elementCount * cell_ha:,.0f} ha | "
                  f"min {st.minimumValue:.2f}  max {st.maximumValue:.2f}  mean {st.mean:.2f}")
        return st

    def calc(layer, name, ftype, formula, out=T, length=20, prec=3, context=None, note=""):
        return run_alg(log, "Field Calculator", "Attributes > Field Calculator  (Processing: Field calculator)",
                       "native:fieldcalculator",
                       {"INPUT": layer, "FIELD_NAME": name, "FIELD_TYPE": ftype, "FIELD_LENGTH": length,
                        "FIELD_PRECISION": prec, "FORMULA": formula, "OUTPUT": out},
                       detail=f"{name} = {formula}" + (f"\n     {note}" if note else ""), context=context)["OUTPUT"]

    # ---------------------------------------------------------- 1. railway corridor
    corridor = o1(A["corridor_output"])
    run_alg(log, "Buffer (dissolved)", "Vector > Geoprocessing Tools > Buffer  [Dissolve result = on]",
            "native:buffer",
            {"INPUT": raw(cfg["vector_layers"]["railways"]["output"]), "DISTANCE": A["corridor_buffer_m"],
             "SEGMENTS": A.get("corridor_segments", 8), "END_CAP_STYLE": 0, "JOIN_STYLE": 0, "MITER_LIMIT": 2,
             "DISSOLVE": True, "OUTPUT": corridor}, detail=f"{A['corridor_buffer_m']} m around redSea_railways")
    cl = QgsVectorLayer(corridor, "c", "ogr")
    corr_ha = sum(f.geometry().area() for f in cl.getFeatures()) / 1e4
    log.write(f"     check: corridor area {corr_ha:,.0f} ha (planar)")

    # ---------------------------------------------------------- 2-3. slope and aspect
    slope = ras("redSea_slope_pct")
    run_alg(log, "Slope", "Raster > Analysis > Slope  [Slope expressed as percent = on]", "gdal:slope",
            {"INPUT": dem, "BAND": 1, "SCALE": 1.0, "AS_PERCENT": True, "COMPUTE_EDGES": A.get("compute_edges", True),
             "ZEVENBERGEN": False, "OPTIONS": "", "EXTRA": "", "OUTPUT": slope},
            detail="percent, on the UTM 36N DEM (metres in x, y and z, so scale = 1)")
    raster_cells(slope, "slope")

    aspect = ras("redSea_aspect")
    run_alg(log, "Aspect", "Raster > Analysis > Aspect", "gdal:aspect",
            {"INPUT": dem, "BAND": 1, "TRIG_ANGLE": False, "ZERO_FLAT": A.get("aspect_zero_flat", False),
             "COMPUTE_EDGES": A.get("compute_edges", True),
             "ZEVENBERGEN": False, "OPTIONS": "", "EXTRA": "", "OUTPUT": aspect},
            detail="degrees clockwise from GRID north; flat cells = "
                   + ("0 (Return 0 for flat = on, as in class)" if A.get("aspect_zero_flat") else "NoData") + ". "
                   "Grid vs true north differs by about 1-2 deg here (outside zone 36), small next to the +/-22.5 deg window")
    raster_cells(aspect, "aspect")

    # ---------------------------------------------------------- 4. rule raster
    smin, smax = A["slope_percent_min"], A["slope_percent_max"]
    amin, amax = A["aspect_min_deg"], A["aspect_max_deg"]
    formula = f"(A>={smin})*(A<={smax})*(B>={amin})*(B<={amax})"
    rule = ras("redSea_rule")
    run_alg(log, "Raster Calculator", "Processing Toolbox > GDAL > Raster miscellaneous > Raster calculator",
            "gdal:rastercalculator",
            {"INPUT_A": slope, "BAND_A": 1, "INPUT_B": aspect, "BAND_B": 1, "FORMULA": formula,
             "NO_DATA": 0, "EXTENT_OPT": 0, "RTYPE": 0, "OPTIONS": "", "EXTRA": "", "OUTPUT": rule},
            detail=f"{formula}  -> 1, otherwise NoData (0 is set as NoData, Byte)\n"
                   f"     GUI Raster Calculator equivalent: (\"slope@1\" >= {smin} AND \"slope@1\" <= {smax} AND "
                   f"\"aspect@1\" >= {amin} AND \"aspect@1\" <= {amax})"
                   + ("  - the class rule (redSea_slope_aspect.tiff, matched cell by cell)" if cfg["_profile"] == "class" else ""))
    if raster_cells(rule, "rule").elementCount == 0:
        sys.exit("STOP: the rule raster has no cells. Check the slope/aspect checks above and re-run Phase 0.")

    # ---------------------------------------------------------- 5. sieve (0 = skip, as in class)
    sieved = ras("redSea_rule_sieved")
    if A["sieve_threshold_cells"] > 0:
        run_alg(log, "Sieve", "Raster > Analysis > Sieve", "gdal:sieve",
                {"INPUT": rule, "THRESHOLD": A["sieve_threshold_cells"], "EIGHT_CONNECTEDNESS": eight,
                 "NO_MASK": True, "MASK_LAYER": None, "EXTRA": "", "OUTPUT": sieved},
                detail=f"threshold {A['sieve_threshold_cells']} cells. 'Do not use the default validity mask' = on: "
                       "otherwise NoData cells are ignored and isolated small patches have no neighbour to merge into, "
                       "so they would survive the sieve")
        raster_cells(sieved, "sieved")
    else:
        sieved = rule
        log.write("\n-- no Sieve (sieve_threshold_cells = 0, as in class): Polygonize uses the rule raster")

    # ---------------------------------------------------------- 6-7. polygonize, DN = 1, dissolve
    poly = run_alg(log, "Polygonize (Raster to Vector)", "Raster > Conversion > Polygonize (Raster to Vector)",
                   "gdal:polygonize",
                   {"INPUT": sieved, "BAND": 1, "FIELD": "DN", "EIGHT_CONNECTEDNESS": eight, "EXTRA": "",
                    "OUTPUT": T},
                   detail=f"{'8' if eight else '4'}-connected. Temporary output: a fixed .gpkg path would be appended "
                          "to on every re-run")["OUTPUT"]

    # ---------------------------------------------------------- 6b. invalid patches (why the class kept only 4)
    # With 8-connectedness, cells that touch only at a corner become ONE polygon whose
    # outline touches itself at that corner. GEOS calls that invalid, and Processing's
    # default "Invalid features filtering = Skip" drops such features WITHOUT a warning.
    # So these steps run with a context that does not filter, mark each patch, and then
    # either fix it (keep all patches) or skip it (reproduce the class run).
    nchk = no_check_context()          # kept alive while its memory layers are in use
    dn1 = run_alg(log, "Extract by Expression", "Processing Toolbox > Vector selection > Extract by expression",
                  "native:extractbyexpression", {"INPUT": poly, "EXPRESSION": '"DN" = 1', "OUTPUT": T},
                  detail='"DN" = 1  (invalid features filtering = off for this step)', context=nchk)["OUTPUT"]
    dn1 = calc(dn1, "class_kept", 1, "if(is_valid($geometry), 1, 0)", length=1, prec=0, context=nchk,
               note="1 = valid geometry (the class run kept it); 0 = corners touch, so the class run skipped it")
    n_all = dn1.featureCount()
    n_bad = sum(1 for f in dn1.getFeatures() if f["class_kept"] == 0)
    log.write(f"     check: {n_bad:,} of {n_all:,} patches have invalid geometry (cells touching only at a corner)")
    policy = A.get("invalid_patches", "fix")
    if policy == "fix":
        dn1 = run_alg(log, "Fix Geometries", "Processing Toolbox > Vector geometry > Fix geometries",
                      "native:fixgeometries", {"INPUT": dn1, "METHOD": 1, "OUTPUT": T},
                      detail="invalid_patches = fix: every patch is kept (Structure method, area unchanged)",
                      context=nchk)["OUTPUT"]
    else:
        dn1 = run_alg(log, "Extract by Expression", "Processing Toolbox > Vector selection > Extract by expression",
                      "native:extractbyexpression", {"INPUT": dn1, "EXPRESSION": '"class_kept" = 1', "OUTPUT": T},
                      detail="invalid_patches = skip: drop them, as Processing did in class", context=nchk)["OUTPUT"]

    if A.get("dissolve_patches", True):
        dn1 = run_alg(log, "Dissolve", "Vector > Geoprocessing Tools > Dissolve  [Keep disjoint features separate = on]",
                      "native:dissolve",
                      {"INPUT": dn1, "FIELD": [], "SEPARATE_DISJOINT": True, "OUTPUT": T},
                      detail="merges polygons that touch; disjoint patches stay separate features")["OUTPUT"]
    run_alg(log, "Create Spatial Index", "Processing Toolbox > Vector general > Create spatial index",
            "native:createspatialindex", {"INPUT": dn1}, detail="memory layer, before the corridor step")

    # ---------------------------------------------------------- 8. corridor: intersection (brief) or join (class)
    if A.get("corridor_method", "intersection") == "join_by_location":
        single = run_alg(log, "Join Attributes by Location", "Vector > Data Management Tools > Join Attributes by Location",
                         "native:joinattributesbylocation",
                         {"INPUT": dn1, "JOIN": corridor, "PREDICATE": [0], "JOIN_FIELDS": ["fclass", "name"],
                          "METHOD": 1, "DISCARD_NONMATCHING": True, "PREFIX": "", "OUTPUT": T},
                         detail="intersects, discard non-matching: WHOLE patches that touch the 5 km corridor "
                                "(as in class; a patch can reach beyond 5 km)")["OUTPUT"]
        nb = sum(1 for f in single.getFeatures() if f["class_kept"] == 0)
        log.write(f"     check: {single.featureCount():,} patches touch the corridor, {nb:,} of them invalid before fixing")
    else:
        inter = run_alg(log, "Intersection", "Vector > Geoprocessing Tools > Intersection", "native:intersection",
                        {"INPUT": dn1, "OVERLAY": corridor, "INPUT_FIELDS": ["DN", "class_kept"],
                         "OVERLAY_FIELDS": ["fclass", "name"], "OVERLAY_FIELDS_PREFIX": "", "GRID_SIZE": None,
                         "OUTPUT": T},
                        detail="suitable land inside the 5 km railway corridor")["OUTPUT"]
        single = run_alg(log, "Multipart to Singleparts", "Vector > Geometry Tools > Multipart to Singleparts",
                         "native:multiparttosingleparts", {"INPUT": inter, "OUTPUT": T},
                         detail="the corridor edge can cut a patch in two: each piece becomes its own site")["OUTPUT"]

    # ---------------------------------------------------------- 8b. exclusion: wadi flood buffer (switch)
    # Both variants are built when make_both_variants = true, so the dashboard can switch
    # between them live. "enabled" decides which one is the main best_locations.gpkg.
    wx = cfg.get("exclusions", {}).get("wadi_buffer", {})
    wadi_tag = f"wadi{wx.get('distance_m', 0)}m"
    variants = {"nowadi": single}
    if wx.get("enabled") or wx.get("make_both_variants"):
        src = raw(cfg["vector_layers"][wx["layer"]]["output"])
        if wx.get("expression"):
            src = run_alg(log, "Extract by Expression", "Processing Toolbox > Vector selection > Extract by expression",
                          "native:extractbyexpression", {"INPUT": src, "EXPRESSION": wx["expression"], "OUTPUT": T},
                          detail=wx["expression"])["OUTPUT"]
        wbuf = o1(f"wadi_buffer_{wx['distance_m']}m")
        run_alg(log, "Buffer (dissolved)", "Vector > Geoprocessing Tools > Buffer  [Dissolve result = on]",
                "native:buffer",
                {"INPUT": src, "DISTANCE": wx["distance_m"], "SEGMENTS": 5, "END_CAP_STYLE": 0, "JOIN_STYLE": 0,
                 "MITER_LIMIT": 2, "DISSOLVE": True, "OUTPUT": wbuf},
                detail=f"EXCLUSION: {wx['distance_m']} m either side of the wadis (flash-flood risk)")
        before_ha = sum(f.geometry().area() for f in single.getFeatures()) / 1e4
        diff = run_alg(log, "Difference", "Vector > Geoprocessing Tools > Difference", "native:difference",
                       {"INPUT": single, "OVERLAY": wbuf, "GRID_SIZE": None, "OUTPUT": T},
                       detail="suitable land minus the wadi buffer")["OUTPUT"]
        if A.get("corridor_method", "intersection") == "join_by_location":
            wsingle = diff     # fixed patches can be multipart (pieces touching at a corner): keep each patch whole
            log.write("     (no Multipart to Singleparts: a fixed patch stays one site even if its pieces touch only at a corner)")
        else:
            wsingle = run_alg(log, "Multipart to Singleparts", "Vector > Geometry Tools > Multipart to Singleparts",
                              "native:multiparttosingleparts", {"INPUT": diff, "OUTPUT": T},
                              detail="a wadi can cut a site in two")["OUTPUT"]
        after_ha = sum(f.geometry().area() for f in wsingle.getFeatures()) / 1e4
        log.write(f"     check: wadi exclusion removed {before_ha - after_ha:,.0f} ha of {before_ha:,.0f} ha "
                  f"({100 * (before_ha - after_ha) / max(before_ha, 1e-9):.1f} %)")
        variants[wadi_tag] = wsingle
    main_key = wadi_tag if wx.get("enabled") else "nowadi"
    order = [main_key] + [k for k in variants if k != main_key]
    log.write(f"\n-- variants: {order}  (main = {main_key} -> best_locations.gpkg)")

    # ======================================================================
    # Steps 9-16 run once per variant (with / without the wadi exclusion)
    # ======================================================================
    def build(single, vname, sfx):
        log.write(f"\n\n######## variant: {vname}  (outputs suffix '{sfx}') ########")
        # ---------------------------------------------------------- 9. area fields

        lyr = calc(single, "area_m2", 0, "area($geometry)")
        lyr = calc(lyr, "area_ha", 0, '"area_m2" / 10000')
        lyr = calc(lyr, "area_acres", 0, f'"area_m2" / {ACRE_M2}')
        lyr = calc(lyr, "area_ell_m2", 0, "$area")
        lyr = calc(lyr, "planar_vs_ell_pct", 0, '100 * ("area_m2" - "area_ell_m2") / "area_ell_m2"', prec=4)
        candidates = o1(A["candidates_output"] + sfx)
        lyr = calc(lyr, "acres_ok", 1, f'"area_acres" > {A["min_site_acres"]}', out=candidates, length=1, prec=0)

        # ---------------------------------------------------------- 10. > 150 acres
        big = run_alg(log, "Extract by Expression", "Processing Toolbox > Vector selection > Extract by expression",
                      "native:extractbyexpression",
                      {"INPUT": candidates, "EXPRESSION": f'"area_acres" > {A["min_site_acres"]}', "OUTPUT": T},
                      detail=f'"area_acres" > {A["min_site_acres"]}  (about {A["min_site_acres"] * ACRE_M2 / 1e4:.1f} ha)')["OUTPUT"]
        n_sites = big.featureCount()
        if n_sites == 0:
            log.write(f"\n[{vname}] No site is larger than the minimum area. Check the rule raster and the corridor.")
            return None
        # @row_number starts at 0 in Processing (QGIS 3.40), so number the sites with a tool
        # that has an explicit start: site 1 = largest site.
        big = run_alg(log, "Add Autoincremental Field", "Processing Toolbox > Vector table > Add autoincremental field",
                      "native:addautoincrementalfield",
                      {"INPUT": big, "FIELD_NAME": "site_id", "START": 1, "MODULUS": 0, "GROUP_FIELDS": [],
                       "SORT_EXPRESSION": '"area_ha"', "SORT_ASCENDING": False, "SORT_NULLS_FIRST": False,
                       "OUTPUT": T}, detail="site_id from 1, largest site first")["OUTPUT"]

        # ---------------------------------------------------------- 11-12. catchment population
        catch = run_alg(log, "Buffer", "Vector > Geoprocessing Tools > Buffer", "native:buffer",
                        {"INPUT": big, "DISTANCE": A["catchment_buffer_m"], "SEGMENTS": 8, "END_CAP_STYLE": 0,
                         "JOIN_STYLE": 0, "MITER_LIMIT": 2, "DISSOLVE": False, "OUTPUT": T},
                        detail=f"{A['catchment_buffer_m']} m catchment per site (not dissolved: one per site)")["OUTPUT"]
        zs = run_alg(log, "Zonal Statistics", "Processing Toolbox > Raster analysis > Zonal statistics",
                     "native:zonalstatisticsfb",
                     {"INPUT": catch, "INPUT_RASTER": pop, "RASTER_BAND": 1, "COLUMN_PREFIX": "pop_",
                      "STATISTICS": [1], "OUTPUT": T},
                     detail="SUM of the 2020 population raster (907 m cells) in each catchment")["OUTPUT"]
        # Each person counted ONCE: a population cell inside two or more catchments goes only to the
        # NEAREST site (if condition below). Zonal Statistics counts it for every catchment -> pop_5km_gross.
        uniq, gross_chk, shared = unique_population(big, zs, pop)
        case = "CASE " + " ".join(f'WHEN "site_id" = {sid} THEN {round(v)}' for sid, v in sorted(uniq.items())) + " ELSE 0 END"
        zs = calc(zs, "pop_5km_gross", 1, 'round(coalesce("pop_sum", 0))', length=10, prec=0,
                  note="every person in the catchment, also those shared with another site's catchment")
        pop_layer = o1(A["population_output"] + sfx)
        t0 = log.step("Field Calculator", "Attributes > Field Calculator  (Processing: Field calculator)",
                      "native:fieldcalculator",
                      "pop_5km = CASE WHEN \"site_id\" = 1 THEN ... END  (people counted once: a cell in several "
                      "catchments goes to the nearest site; values from unique_population())")
        import processing
        processing.run("native:fieldcalculator", {"INPUT": zs, "FIELD_NAME": "pop_5km", "FIELD_TYPE": 1,
                                                  "FIELD_LENGTH": 10, "FIELD_PRECISION": 0, "FORMULA": case,
                                                  "OUTPUT": pop_layer})
        log.done(t0, pop_layer, n_sites)
        g_tot = sum(f["pop_5km_gross"] for f in QgsVectorLayer(pop_layer, "p", "ogr").getFeatures())
        u_tot = round(sum(uniq.values()))
        log.write(f"     check: gross {g_tot:,} (Zonal Statistics) vs {round(gross_chk):,} (cell check); "
                  f"counted once {u_tot:,}; {g_tot - u_tot:,} people sat in overlapping catchments "
                  f"({shared:,} shared cells) and are now counted for their nearest site only")

        sites = run_alg(log, "Join Attributes by Field Value", "Vector > Data Management Tools > Join Attributes by Field Value",
                        "native:joinattributestable",
                        {"INPUT": big, "FIELD": "site_id", "INPUT_2": pop_layer, "FIELD_2": "site_id",
                         "FIELDS_TO_COPY": ["pop_5km", "pop_5km_gross"], "METHOD": 1, "DISCARD_NONMATCHING": False,
                         "PREFIX": "", "OUTPUT": T},
                        detail="pop_5km (counted once) and pop_5km_gross back onto the sites")["OUTPUT"]

        # ---------------------------------------------------------- 13. criteria check (zonal stats on the sites)
        chk = run_alg(log, "Zonal Statistics", "Processing Toolbox > Raster analysis > Zonal statistics",
                      "native:zonalstatisticsfb",
                      {"INPUT": sites, "INPUT_RASTER": slope, "RASTER_BAND": 1, "COLUMN_PREFIX": "slope_",
                       "STATISTICS": [2], "OUTPUT": T}, detail="criteria check: mean slope % per site")["OUTPUT"]
        chk = run_alg(log, "Zonal Statistics", "Processing Toolbox > Raster analysis > Zonal statistics",
                      "native:zonalstatisticsfb",
                      {"INPUT": chk, "INPUT_RASTER": aspect, "RASTER_BAND": 1, "COLUMN_PREFIX": "aspect_",
                       "STATISTICS": [2], "OUTPUT": T}, detail="criteria check: mean aspect per site")["OUTPUT"]

        # ---------------------------------------------------------- 14. score factors (switches in config "scoring")
        SC = cfg["scoring"]
        F = {k: dict(v) for k, v in SC["factors"].items()}
        on = lambda k: k in F            # compute every factor; "enabled" only sets the default score
        lyr = chk

        if on("compactness"):
            lyr = calc(lyr, "compactness", 0, "4 * pi() * area($geometry) / (perimeter($geometry) ^ 2)", prec=4)

        dist_jobs = []          # (factor, target layer, field to copy, scale, unit)
        if on("road_distance"):
            dist_jobs.append(("road_distance", raw(cfg["vector_layers"]["roads"]["output"]), "fclass", 1, "m"))
        if on("rail_distance"):
            dist_jobs.append(("rail_distance", raw(cfg["vector_layers"]["railways"]["output"]), "fclass", 1, "m"))
        if on("port_distance"):
            town = F["port_distance"]["town"]
            port = run_alg(log, "Extract by Expression", "Processing Toolbox > Vector selection > Extract by expression",
                           "native:extractbyexpression",
                           {"INPUT": raw(cfg["vector_layers"]["towns"]["output"]),
                            "EXPRESSION": f"\"NAME\" = '{town}'", "OUTPUT": T}, detail=f"the port: {town}")["OUTPUT"]
            if port.featureCount() == 1:
                dist_jobs.append(("port_distance", port, "NAME", 1000, "km"))
            else:
                log.write(f"  WARNING: {town} not found in redSea_towns - port_distance not available")
                F.pop("port_distance")

        if dist_jobs:
            cent = run_alg(log, "Centroids", "Vector > Geometry Tools > Centroids", "native:centroids",
                           {"INPUT": lyr, "ALL_PARTS": False, "OUTPUT": T},
                           detail="one point per site, for the distance factors")["OUTPUT"]
            for key, target, copy_field, scale, unit in dist_jobs:
                fld = F[key]["field"]
                jn = run_alg(log, "Join Attributes by Nearest", "Processing Toolbox > Vector general > Join attributes by nearest",
                             "native:joinbynearest",
                             {"INPUT": cent, "INPUT_2": target, "FIELDS_TO_COPY": [copy_field], "DISCARD_NONMATCHING": False,
                              "PREFIX": "nn_", "NEIGHBORS": 1, "MAX_DISTANCE": None, "OUTPUT": T},
                             detail=f"{key}: site centroid to nearest feature (adds a 'distance' field, in m)")["OUTPUT"]
                jn = calc(jn, fld, 0, f'"distance" / {scale}' if scale != 1 else '"distance"', prec=3)
                lyr = run_alg(log, "Join Attributes by Field Value", "Vector > Data Management Tools > Join Attributes by Field Value",
                              "native:joinattributestable",
                              {"INPUT": lyr, "FIELD": "site_id", "INPUT_2": jn, "FIELD_2": "site_id",
                               "FIELDS_TO_COPY": [fld], "METHOD": 1, "DISCARD_NONMATCHING": False, "PREFIX": "",
                               "OUTPUT": T}, detail=f"{fld} ({unit}) back onto the sites")["OUTPUT"]

        if on("buildings_5km"):
            bpath = raw(cfg["vector_layers"]["buildings"]["output"])
            if not (cfg["vector_layers"]["buildings"].get("enabled") and os.path.exists(bpath)):
                log.write("  NOTE: buildings_5km needs vector_layers.buildings.enabled = true and Phase 0 re-run - not available")
                F.pop("buildings_5km")
            else:
                bcent = run_alg(log, "Centroids", "Vector > Geometry Tools > Centroids", "native:centroids",
                                {"INPUT": bpath, "ALL_PARTS": False, "OUTPUT": T}, detail="one point per building")["OUTPUT"]
                run_alg(log, "Create Spatial Index", "Processing Toolbox > Vector general > Create spatial index",
                        "native:createspatialindex", {"INPUT": bcent}, detail="memory layer, before counting")
                cnt = run_alg(log, "Count Points in Polygon", "Vector > Analysis Tools > Count Points in Polygon",
                              "native:countpointsinpolygon",
                              {"POLYGONS": pop_layer, "POINTS": bcent, "WEIGHT": None, "CLASSFIELD": None,
                               "FIELD": F["buildings_5km"]["field"], "OUTPUT": T},
                              detail="OSM buildings in each 5 km catchment")["OUTPUT"]
                lyr = run_alg(log, "Join Attributes by Field Value", "Vector > Data Management Tools > Join Attributes by Field Value",
                              "native:joinattributestable",
                              {"INPUT": lyr, "FIELD": "site_id", "INPUT_2": cnt, "FIELD_2": "site_id",
                               "FIELDS_TO_COPY": [F["buildings_5km"]["field"]], "METHOD": 1,
                               "DISCARD_NONMATCHING": False, "PREFIX": "", "OUTPUT": T},
                              detail="buildings_5km back onto the sites")["OUTPUT"]

        best = o1(A["sites_output"] + sfx)
        run_alg(log, "Save Vector Features to File", "Processing Toolbox > Vector general > Save vector features to file",
                "native:savefeatures", {"INPUT": lyr, "LAYER_NAME": "", "DATASOURCE_OPTIONS": "", "LAYER_OPTIONS": "",
                                        "OUTPUT": best})

        # ---------------------------------------------------------- 15. combined score, rank, sensitivity
        import scoring
        method = SC["normalisation"]
        t0 = log.step("Combined score and rank", "Python (scoring.py) - QGIS expressions have no rank() function",
                      "-", f"normalisation = {method}; only enabled factors count, weights rescaled to sum to 1")
        bl = QgsVectorLayer(best, "best", "ogr")
        feats = list(bl.getFeatures())
        to_num = lambda v: None if v is None or str(v) == "NULL" else float(v)
        rows = [{**{F[k]["field"]: to_num(f[F[k]["field"]]) for k in F
                    if bl.fields().indexOf(F[k]["field"]) >= 0},
                 "site_id": f["site_id"]} for f in feats]
        sids = [r["site_id"] for r in rows]

        weights = scoring.effective_weights(F)
        main_scores, norms = scoring.score(rows, F, weights, method)
        main_ranks = scoring.ranks(main_scores, sids)
        log.write("     weights: " + ", ".join(f"{k} {w:.3f}" for k, w in weights.items()))

        scen = {}
        for name, sw in SC.get("scenarios", {}).items():
            try:
                w = weights if not isinstance(sw, dict) else scoring.effective_weights(F, sw)
            except ValueError:
                log.write(f"     scenario '{name}' skipped: none of its factors is enabled")
                continue
            sc_, _ = scoring.score(rows, F, w, method)
            scen[name] = scoring.ranks(sc_, sids)

        try:
            from qgis.PyQt.QtCore import QMetaType
            DBL, INT = QMetaType.Type.Double, QMetaType.Type.Int
        except (ImportError, AttributeError):
            from qgis.PyQt.QtCore import QVariant
            DBL, INT = QVariant.Double, QVariant.Int
        from qgis.core import QgsField
        new_fields = [QgsField(f"n_{k}", DBL) for k in weights] + [QgsField("score", DBL), QgsField("rank", INT)]
        new_fields += [QgsField(f"rank_{n}", INT) for n in scen]
        pr = bl.dataProvider()
        pr.addAttributes([fl for fl in new_fields if bl.fields().indexOf(fl.name()) < 0])
        bl.updateFields()
        idx = {fl.name(): bl.fields().indexOf(fl.name()) for fl in new_fields}
        changes = {}
        for i, f in enumerate(feats):
            ch = {idx[f"n_{k}"]: round(norms[k][i], 4) for k in weights}
            ch[idx["score"]] = round(main_scores[i], 4)
            ch[idx["rank"]] = main_ranks[i]
            for n, rk in scen.items():
                ch[idx[f"rank_{n}"]] = rk[i]
            changes[f.id()] = ch
        pr.changeAttributeValues(changes)
        log.done(t0, best, len(feats))

        # ---------------------------------------------------------- 16. checks and summary
        log.write(f"\n== Checks [{vname}]")
        bl = QgsVectorLayer(best, "best", "ogr")
        feats = sorted(bl.getFeatures(), key=lambda f: f["rank"])

        da = QgsDistanceArea()
        da.setSourceCrs(bl.crs(), proj.transformContext())
        da.setEllipsoid(A["ellipsoid"])
        f0 = feats[0]
        py_ell = da.measureArea(f0.geometry())
        log.write(f"  ellipsoidal area, site rank 1: field $area {f0['area_ell_m2']:,.0f} m2 vs QgsDistanceArea {py_ell:,.0f} m2")
        if abs(f0["area_ell_m2"] - f0["area_m2"]) < 1e-6:
            log.write("  WARNING: $area equals area($geometry) - the ellipsoid was not applied")
        diffs = [f["planar_vs_ell_pct"] for f in feats]
        log.write(f"  UTM 36N planar area is {min(diffs):+.2f} % to {max(diffs):+.2f} % vs ellipsoidal (outside-zone distortion)")

        bad = [f["site_id"] for f in feats
               if not (smin <= (f["slope_mean"] or -1) <= smax and amin <= (f["aspect_mean"] or -1) <= amax)]
        log.write(f"  criteria: {n_sites - len(bad)} of {n_sites} sites have mean slope {smin}-{smax} % and mean aspect {amin}-{amax} deg"
                  + (f"; outside: site_id {bad} (the sieve can fill small gaps)" if bad else ""))

        cg = [f.geometry() for f in QgsVectorLayer(pop_layer, "p", "ogr").getFeatures()]
        pairs = sum(1 for i in range(len(cg)) for j in range(i + 1, len(cg)) if cg[i].intersects(cg[j]))
        log.write(f"  catchments: {pairs} overlapping pairs - people in an overlap are counted once, for the nearest site "
                  f"(pop_5km); pop_5km_gross counts them for every site")

        dropped = [f["site_id"] for f in feats if f["class_kept"] == 0]
        log.write(f"  invalid geometry: {len(dropped)} of {n_sites} sites (site_id {sorted(dropped)}) have cells touching "
                  f"only at a corner. Processing skips such features by default, so a class run keeps "
                  f"{n_sites - len(dropped)} sites" + (" - these were fixed and kept here" if policy == "fix" else ""))
        ref = A.get("class_reference")
        if ref:
            ref = ref if os.path.isabs(ref) else os.path.join(os.path.dirname(cfg["_path"]), ref)
            if os.path.exists(ref):
                log.write(f"  class reference {os.path.basename(ref)}: share of each class site covered by our sites")
                for rf in QgsVectorLayer(ref, "ref", "ogr").getFeatures():
                    rg = rf.geometry()
                    hits = [(f["site_id"], rg.intersection(f.geometry()).area()) for f in feats
                            if f.geometry().intersects(rg)]
                    cov = sum(a for _, a in hits) / rg.area() * 100
                    log.write(f"    class fid {rf.id():>5}  {rg.area() / 1e4:6.1f} ha  covered {cov:5.1f} %  "
                              f"by site_id {[h[0] for h in hits]}")
            else:
                log.write(f"  class reference not found: {ref}")

        fac_fields = [F[k]["field"] for k in weights]

        def fmt_cell(c, v):
            if v is None:
                return f"{'-':>11}"
            if c == "compactness":
                return f"{v:>11.3f}"
            if c in ("pop_5km", "buildings_5km") or c.endswith("_m"):
                return f"{v:>11,.0f}"
            return f"{v:>11.1f}"
        tot_ha = sum(f["area_ha"] for f in feats)
        log.write(f"\n== [{vname}] {n_sites} sites, {tot_ha:,.0f} ha in total | score: {method}-normalised, "
                  + " + ".join(f"{w:.2f} x {k}" for k, w in weights.items()))
        hdr = (f"  {'rank':>4} {'site':>4} " + " ".join(f"{c[:11]:>11}" for c in fac_fields)
               + f" {'score':>6} {'class_kept':>10}")
        log.write(hdr)
        for f in feats[:25]:
            log.write(f"  {f['rank']:>4} {f['site_id']:>4} "
                      + " ".join(fmt_cell(c, to_num(f[c])) for c in fac_fields)
                      + f" {f['score']:>6.3f} {('yes' if f['class_kept'] == 1 else 'no'):>10}")

        if scen:
            log.write("\n== Sensitivity: rank under each weight scenario (top 10 by the main score)")
            log.write(f"  {'site':>4} {'rank':>4} " + " ".join(f"{n[:9]:>9}" for n in scen) + "   spread")
            for f in feats[:10]:
                rs = [f[f"rank_{n}"] for n in scen]
                log.write(f"  {f['site_id']:>4} {f['rank']:>4} " + " ".join(f"{r:>9}" for r in rs)
                          + f"   {max(rs + [f['rank']]) - min(rs + [f['rank']]):>6}")
            stable = [f["site_id"] for f in feats if all(f[f"rank_{n}"] <= 10 for n in scen) and f["rank"] <= 10]
            log.write(f"  in the top 10 under every scenario: site_id {stable if stable else 'none'}")

        csv_path = run_path(cfg, "outputs_dir", A["sites_output"] + sfx, ".csv")
        names = (["rank", "site_id", "area_ha", "area_acres", "area_m2", "area_ell_m2", "pop_5km", "pop_5km_gross"]
                 + [c for c in fac_fields if c not in ("area_ha", "pop_5km")]
                 + ["slope_mean", "aspect_mean", "class_kept"] + [f"n_{k}" for k in weights] + ["score"]
                 + [f"rank_{n}" for n in scen])
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(names)
            for f in feats:
                w.writerow([None if str(f[n]) == "NULL" else f[n] for n in names])
        log.write(f"\n  table: {csv_path}")

        return {"variant": vname, "sites": best, "population": pop_layer, "candidates": candidates,
                "table": csv_path, "n_sites": n_sites, "weights": weights,
                "factors_available": {k: F[k]["field"] for k in F}}

    results = {}
    for k in order:
        results[k] = build(variants[k], k, "" if k == main_key else f"_{k}")
    results = {k: v for k, v in results.items() if v}
    if not results:
        log.close()
        return

    write_manifest(cfg, "phase2", phase0_fingerprint(cfg),
                   {"corridor": corridor, "slope": slope, "aspect": aspect, "rule": rule, "sieved": sieved,
                    "profile": cfg["_profile"], "main_variant": main_key, "variants": results,
                    "wadi_buffer": wbuf if len(variants) > 1 else None,
                    "normalisation": cfg["scoring"]["normalisation"]})
    mark_latest(cfg)
    log.write(f"\nPhase 2 done. Run folder: {cfg['paths']['run_root']}\nLog: {log.path}")
    log.close()

def unique_population(sites, catchments, pop_path):
    """People per site, each population cell counted ONCE.

    A cell belongs to a catchment when its centre lies inside it (the same rule Zonal Statistics
    uses for SUM). If the cell is inside two or more catchments, it goes to the nearest site
    (the shortest distance from the cell centre to the site polygon; a tie goes to the lower site_id).
    Returns ({site_id: people}, gross total, number of shared cells).
    """
    from qgis.core import QgsGeometry, QgsPointXY, QgsRasterLayer, QgsRectangle
    site_geom = {f["site_id"]: f.geometry() for f in sites.getFeatures()}
    catch = {f["site_id"]: f.geometry() for f in catchments.getFeatures()}
    for g in catch.values():
        g.prepareGeometry()
    r = QgsRasterLayer(pop_path, "pop")
    pr, ext = r.dataProvider(), r.extent()
    cw, ch = r.rasterUnitsPerPixelX(), r.rasterUnitsPerPixelY()
    bb = QgsRectangle(next(iter(catch.values())).boundingBox())
    for g in catch.values():
        bb.combineExtentWith(g.boundingBox())
    c0 = max(0, int((bb.xMinimum() - ext.xMinimum()) // cw))
    c1 = min(r.width(), int((bb.xMaximum() - ext.xMinimum()) // cw) + 1)
    r0 = max(0, int((ext.yMaximum() - bb.yMaximum()) // ch))
    r1 = min(r.height(), int((ext.yMaximum() - bb.yMinimum()) // ch) + 1)
    x0, y0 = ext.xMinimum() + c0 * cw, ext.yMaximum() - r0 * ch
    block = pr.block(1, QgsRectangle(x0, y0 - (r1 - r0) * ch, x0 + (c1 - c0) * cw, y0), c1 - c0, r1 - r0)
    uniq = {sid: 0.0 for sid in site_geom}
    gross, shared = 0.0, 0
    for row in range(r1 - r0):
        for col in range(c1 - c0):
            if block.isNoData(row, col):
                continue
            v = block.value(row, col)
            if not v or v <= 0:
                continue
            p = QgsGeometry.fromPointXY(QgsPointXY(x0 + (col + 0.5) * cw, y0 - (row + 0.5) * ch))
            inside = [sid for sid, g in catch.items() if g.contains(p)]
            if not inside:
                continue
            gross += v * len(inside)
            if len(inside) == 1:                       # in one catchment only: that site
                uniq[inside[0]] += v
            else:                                      # shared: the nearest site gets the people
                shared += 1
                nearest = min(inside, key=lambda sid: (site_geom[sid].distance(p), sid))
                uniq[nearest] += v
    return uniq, gross, shared


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
