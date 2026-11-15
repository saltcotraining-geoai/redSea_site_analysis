# Clicks vs Code: Red Sea Site Analysis - workflow plan

Project name (decided 15 Nov 2026): **Clicks vs Code: Red Sea Site Analysis**; episode 1 = *Four Sites or Fifteen?*; repository `saltcotraining-geoai/redSea_site_analysis`.

**Question:** Where in Red Sea State is there land that faces northeast, has a gentle slope (2–5 %), and lies within 5 km of the Port Sudan–Khartoum railway? How large is each site, and how many people live within 5 km of it?

All measuring is in **UTM 36N (EPSG:32636)**. Red Sea State reaches about 39° E, outside zone 36 (30–36° E), so planar lengths and areas are slightly distorted. Phase 2 reports ellipsoidal `$area` next to planar `area($geometry)` to show how large the difference is.

## Step 1: railway check (done, 14 Nov 2026)

I clipped `railways` (EPSG:32636) to `adm1_name = 'Red Sea'` with a short standard-library script (`tools/railway_check.py`, no GDAL needed):

| Item | Result |
|---|---|
| Features intersecting Red Sea | **159** of 1,466 (155 `narrow_gauge`, 4 `rail`), all unnamed |
| Length inside the state | **420.0 km** |
| Vertex extent (m) | x 699,646–944,706, y 1,986,426–2,176,135 |
| Boundary crossings | **1**, on the western edge towards Berber/Atbarah (River Nile State) |
| Track > 20 km south of Haiya | only the western main line as it dips south-west; nothing towards Kassala |
| Northernmost track in Kassala State | y = 1,657,079, about 226 km south of the Red Sea boundary (y = 1,883,577) |

**Conclusion:** in this dataset `redSea_railways` is the main line only, **Port Sudan → Haiya → west to the River Nile border** (towards Atbarah and Khartoum). The **Haiya–Kassala branch is not in the data**, so no filtering is needed and the "clip, as in class" corridor already equals the Port Sudan–Khartoum line. Option A (the shortest path) would give the same corridor inside the state. It is worth doing only as a teaching comparison.

**Network topology:** the line ends do not share vertices (75 parts at a 1 m snap, 15 at 50 m, 6 at 500 m). This does not affect Buffer, but a shortest path (Option A) would need `native:snapgeometries` first, or a large tolerance in `native:shortestpathpointtopoint`.

Still to confirm on the class laptop: the feature count of the class file `redSea_railways` (expected 159).

## Phase 0: data preparation (`phase0_prepare.py`)

| # | Step | GUI path | Processing ID |
|---|---|---|---|
| 1 | Fix the states | Vector geometry > Fix geometries | `native:fixgeometries` |
| 2 | Red Sea State | Vector selection > Extract by expression | `native:extractbyexpression` |
| 3 | Clip masks (DEM +2 km, population +6 km) | Vector > Geoprocessing Tools > Buffer | `native:buffer` |
| 4 | Railway filter `fclass IN ('rail','narrow_gauge')` | Extract by expression | `native:extractbyexpression` |
| 5 | Fix the polygon layers | Fix geometries | `native:fixgeometries` |
| 6 | Railways, roads, rivers, water bodies, natural areas | Vector > Geoprocessing Tools > Clip | `native:clip` |
| 7 | Districts and towns (whole features) | Vector > Research Tools > Select by Location + Save selected features | `native:selectbylocation`, `native:saveselectedfeatures` |
| 8 | Spatial index: Processing already builds the GeoPackage R-tree when it writes each file, so no extra step | – | – |
| 9 | DEM clipped in EPSG:4326 | Raster > Extraction > Clip Raster by Mask Layer | `gdal:cliprasterbymasklayer` |
| 10 | DEM to UTM 36N, **bilinear**, 180 m | Raster > Projections > Warp (Reproject) | `gdal:warpreproject` |
| 11 | Population clipped (already UTM 36N) | Clip Raster by Mask Layer | `gdal:cliprasterbymasklayer` |
| 12 | Checks + manifest with a settings fingerprint | – | – |

Phase 0 clips the DEM before it reprojects it, which avoids warping the whole Sudan DEM (83 MB). The population mask gets a 6 km margin (the 5 km catchment plus one cell), so sites near the state border keep their full catchment. Buildings (1.7 M features) are switched off in `config.json` until the web map needs them.

Outputs (following the class layout) go under `output/`:
- `01_Data/`: `redSea_state.gpkg`, then in Phase 2 `railways_buff_5km.gpkg`, `best_locations.gpkg` and `redSea_pop.gpkg`
- `02_Raw_data/`: `redSea_railways`, `redSea_roads`, `redSea_rivers`, … (`.gpkg`)
- `03_Rasters/`: `redSea_dem_utm36n.tif`, `redSea_population_2020.tif`
- `logs/`: one log per run, naming every tool and Processing ID

### Phase 0 run 1 (14 Nov 2026, 12:00, fingerprint `b40b0116f588c867`)

| Output | Result |
|---|---|
| Red Sea State | 1 feature |
| Railways | 159 features, **419.6 km** (stdlib check: 420.0 km, which measures whole segments by their midpoint) |
| Roads / rivers / water bodies / natural areas | 15,479 / 707 / 47 / 1 |
| Districts / towns (Select by Location) | 15 / 3 (Port Sudan, Haiya, Tokar) |
| DEM, UTM 36N | 3,181 × 3,860 px at 180 m |
| Population | 637 × 762 px at 906.8 m |

Fixes after this run: the Create Spatial Index step was removed (it gave "already existing" errors), and the segfault at exit was replaced by a clean `os._exit(code)` with the traceback printed first. The fixes have not been re-run yet.

## Phase 2: analysis (`phase2_analysis.py`)

Decisions (14 Nov 2026): slope from **`gdal:slope` in percent**; ranking by a **multi-criteria score**, where every factor and the exclusion is a switch in `config.json`.

| Factor (`scoring.factors`) | Default | Weight | Better when | Tool |
|---|---|---|---|---|
| `area` (area_ha) | on | 0.30 | larger | Field Calculator |
| `population` (pop_5km) | on | 0.30 | larger | Zonal statistics |
| `road_distance` (dist_road_m) | on | 0.15 | closer | Centroids + Join attributes by nearest |
| `rail_distance` (dist_rail_m) | on | 0.10 | closer | Centroids + Join attributes by nearest |
| `compactness` (4πA/P²) | on | 0.15 | rounder | Field Calculator |
| `port_distance` (dist_port_km, Port Sudan) | off | 0.10 | closer | Extract by expression + Join attributes by nearest |
| `buildings_5km` (OSM 2026) | off | 0.10 | more | Centroids + Count points in polygon (needs buildings in Phase 0) |

- **Exclusion `exclusions.wadi_buffer`** (on, 300 m): Buffer the wadis and subtract them from the sites (`native:difference`) before the 150-acre filter. This is a hard rule, not a weight, because of flash-flood risk.
- **Normalisation `scoring.normalisation`** = `rank` (percentile 0–1, robust to one huge site); `minmax` and `log_minmax` are the alternatives. Only enabled factors count, and their weights are rescaled to sum to 1.
- **Sensitivity `scoring.scenarios`**: balanced, workforce, land and access. Each gives a `rank_<scenario>` field. The log lists the top 10 with the spread of ranks across scenarios and the sites that stay in the top 10 under all of them.
- The score itself is computed in `scoring.py` (pure Python, testable without QGIS), because QGIS expressions have no `rank()` function.

| # | Step | GUI path | Processing ID |
|---|---|---|---|
| 1 | Buffer the railways 5 km, dissolved → `railways_buff_5km` | Vector > Geoprocessing Tools > Buffer | `native:buffer` |
| 2 | Slope in percent | Raster > Analysis > Slope | `gdal:slope` (AS_PERCENT) |
| 3 | Aspect | Raster > Analysis > Aspect | `gdal:aspect` |
| 4 | Rule: `(A>=2)*(A<=5)*(B>=22.5)*(B<=67.5)` → 1, otherwise NoData | GDAL > Raster calculator | `gdal:rastercalculator` |
| 5 | Sieve, 19 cells, **validity mask off** | Raster > Analysis > Sieve | `gdal:sieve` |
| 6 | Polygonize, then keep DN = 1 | Raster > Conversion > Polygonize | `gdal:polygonize`, `native:extractbyexpression` |
| 7 | Dissolve, keeping disjoint patches separate | Vector > Geoprocessing Tools > Dissolve | `native:dissolve` |
| 8 | Intersection with the corridor, then singleparts | Vector > Geoprocessing Tools > Intersection | `native:intersection`, `native:multiparttosingleparts` |
| 9 | `area_m2`, `area_ha`, `area_acres`, `area_ell_m2` (`$area`), `planar_vs_ell_pct` → `candidate_patches` | Field Calculator | `native:fieldcalculator` |
| 10 | Keep `area_acres > 150`, then add `site_id` | Extract by expression | `native:extractbyexpression` |
| 11 | 5 km catchment per site | Buffer | `native:buffer` |
| 12 | Population SUM → `pop_5km` → `redSea_pop` | Zonal statistics | `native:zonalstatisticsfb` |
| 13 | `pop_5km` joined back onto the sites | Join Attributes by Field Value | `native:joinattributestable` |
| 14 | Criteria check: mean slope and mean aspect per site | Zonal statistics | `native:zonalstatisticsfb` |
| 8b | Wadi exclusion (switch): Buffer the wadis, then Difference, then singleparts | Buffer, Difference | `native:buffer`, `native:difference` |
| 15 | Score factors (switches): compactness, then distances via Centroids + Join by nearest, then buildings | Field Calculator, Centroids, Join attributes by nearest, Count points in polygon | `native:fieldcalculator`, `native:centroids`, `native:joinbynearest`, `native:countpointsinpolygon` |
| 16 | Save, then score, rank and sensitivity (`scoring.py`) → `best_locations` (+ `.csv`) | Save vector features to file | `native:savefeatures` |

Teaching notes:
- **Sieve:** with the default validity mask, NoData cells are ignored, so a small isolated patch has no neighbour to merge into and survives the sieve. Turning the mask off ("Do not use the default validity mask") lets the sieve remove it.
- **`$area`:** the ellipsoidal area needs an ellipsoid. A standalone script has no project settings, so the script sets EPSG:7030 on the project and checks the result against `QgsDistanceArea`.
- **Aspect:** it is measured from grid north. Outside zone 36 grid north differs from true north by about 1-2°, which is small next to the ±22.5° window.
- **Checks in the log:** the valid-cell count and hectares after each raster step, the corridor area, the planar vs ellipsoidal difference, how many sites meet the criteria by their mean values, and the number of overlapping catchment pairs.

## Independent check (`tools/independent_check.py`, numpy, 14 Nov 2026)

Phase 2 recomputed without QGIS on the Phase 0 rasters (Horn slope and aspect as in gdaldem, an approximate sieve, a raster corridor). This is the ground truth to compare `best_locations.gpkg` against.

**Finding:** with the brief's criteria (slope 2–5 %, aspect 22.5–67.5°, > 150 acres) the 5 km corridor holds **only 1 site (77.8 ha)**.
- In the corridor, 74 % of the land is < 2 % slope, and only 11 % faces northeast; the rule covers 5,485 ha in about 900 small patches.
- The sieve is not the cause: without a sieve there is still only 1 patch > 150 acres.
- Wider criteria change the count: aspect 0–90° gives 19 sites; slope 1–8 % gives 45; a 3×3-smoothed DEM gives 5.
- If the class dissolved all patches into **one** feature before the area test, "> 150 acres" applied to the 5,485 ha total. That would explain why the class seemed to get results. Compare with the class `best_locations.gpkg`.
- The wadi exclusion (300 m, `river` and `stream`) removes only about 9 ha at these sites.

**Decision needed:** keep the criteria (an honest "one site" answer) or widen the aspect or slope window.

## Runs and class comparison (15 Nov 2026)

**QGIS 3.40 run (your machine):** Phase 2 and Phase 3 ran end to end.
- Rule: 151,028 cells. Sieve: 9,472 cells. Polygonize: 266 patches. Only **1 site** in the corridor: 75.4 ha (186 acres), 3,510 people within 5 km, 21.4 km to a road, 4.1 km to the railway, compactness 0.186, mean slope 3.6 %, mean aspect 51°, about 36.91° E, 19.20° N.
- This agrees with the numpy check (150,880 / 9,398 cells; 1 site of 77.8 ha).
- Wadi exclusion: 0 ha removed, so both variants are identical.
- Dashboard: `output/dashboard/index.html` (0.77 MB); the browser tests pass on the real output. **Still open:** confirm on screen that the map draws.
- Fixes made during these runs: the manifest is read from `"outputs"` in Phase 3; site_id comes from `native:addautoincrementalfield` (start 1, largest first), because `@row_number` starts at 0 in Processing; Polygonize writes to a temporary output, because a fixed .gpkg path was appended to on every re-run (532 = 2 × 266); log files are closed on exit; and file copies are now checked on the device by size.

**Class project `training_raster_datat_20261018.qgs`** (the zips hold only the projects, not the data):
- The result layer is "Proposed Locations" = `./01_Data/best_locations.gpkg`, extent x 899,224–920,085, y 2,087,788–2,140,940 (**20.9 × 53.2 km**, about 36.8–37.0° E, 18.9–19.35° N, between Sinkat and Haiya). That means several features; the user remembers **5–6 sites**. Our 1 site lies inside this extent.
- Its fields are `DN, area_sqm, area_acres, fid_2, fclass, name`. The railway fields mean the class intersected with **non-dissolved per-segment buffers** (159 overlapping), which can split or duplicate patches.
- No slope, aspect or rule rasters were saved in the project, and there is no layer named "suitable sites" in any of the three projects.
- Reproduction attempts on this DEM: the brief's criteria give 1 site under every variant (sieve 0–19, 4- or 8-connected, per-segment summing); slope in degrees gives 0; **aspect 15–75° gives 4 patches** (20 pieces with per-segment buffers) in an extent of 18 × 62 km, the closest match.

**Next (on the class laptop, Mint 22.3, QGIS 3.44):** read `best_locations.gpkg` (count, duplicates, areas), any slope, aspect or rule rasters, and the QGIS Processing history (`~/.local/share/QGIS/QGIS3/profiles/default/history.db`, or `processing/processing.log`) for the exact class settings. Then decide on the criteria.

## Moving to the class laptop (15 Nov 2026)

- `pack_for_class_laptop.sh /media/$USER/<USB>` copies `~/Downloads/sdn_datasets` (data, project, fromClass) and `~/Desktop/site_selection_v4` to `<USB>/for_class_laptop/`. It uses rsync, so re-running copies only the changes, and it checks free space first.
- On the class laptop (Mint 22.3, QGIS 3.44), `bash <USB>/for_class_laptop/unpack_on_class_laptop.sh` puts everything in the same places, checks that `/usr/bin/python3` can import QGIS, and copies the class QGIS history (`history.db`, `processing.log`) into `fromClass/qgis_history/`.
- The project now works from any folder: if `data_root` or `output_root` don't exist, `load_config` uses the project's parent folder and `<project>/output`. Paths from another computer in the manifests are remapped, and the settings fingerprint no longer depends on absolute paths.
- The fingerprint formula changed, so run `/usr/bin/python3 demo.py` once (all phases, about 1 min). This also tests QGIS 3.44.

## Phase 3: live dashboard (`phase3_dashboard.py` + `dashboard_html.py`)

One self-contained HTML file (`output/dashboard/index.html`, about 0.7 MB). The data is embedded, Leaflet 1.9.4 comes from unpkg with SRI (`phase3.sri_check`), and there is no other CDN. The GeoJSON files are also written to `output/dashboard/data/`.

| # | Step | Tool / ID |
|---|---|---|
| 1 | Roads for the web map: drop residential, service, footway and path (about 1,700 of 15,479 kept) | `native:extractbyexpression` |
| 2 | Simplify in UTM (roads and rivers 50 m, districts 200 m, states 500 m, corridor 25 m, sites 5 m, catchments 50 m) | `native:simplifygeometries` |
| 3 | GeoJSON in EPSG:4326, RFC 7946, 5 decimals, via `options.ct` | `QgsVectorFileWriter.writeAsVectorFormatV3` |
| 4 | Clean up for Leaflet: drop empty geometries, turn GeometryCollection into Multi* | `normalize_for_leaflet()` |
| 5 | Marker position = point on surface | `QgsGeometry.pointOnSurface()` |

**Live in the browser** (same rules as `scoring.py`; JS–Python parity is tested for every variant, normalisation and scenario):
- Wadi exclusion switch (300 m / off). It changes which sites exist, because Phase 2 builds both variants.
- Factor tick boxes and weight sliders; scenario chips (balanced, workforce, land, access, custom); normalisation (rank, min-max, log).
- Top-N and minimum-score sliders, a table filter (`12`, `>100 ha`, `<2 km`), a sortable table linked to the map (click a row to zoom and show the 5 km catchment), ★ = top 10 under every scenario.
- CSV and GeoJSON export of what is shown (with variant, scenario and weights). Reset.
- The class styles; basemaps None (default, low bandwidth), OSM and Esri imagery. The map degrades to table-only if Leaflet cannot load.
- A warning when ≤ 2 sites.

**Fixed (needs a Phase 2 re-run):** slope, aspect, corridor width, wadi distance, minimum area.

Run everything: `/usr/bin/python3 demo.py` (`--from 2`, `--only 3`).

## Caveats to carry into the outputs

- 907 m population cells are coarse next to small sites; overlapping catchments count the same people twice.
- The population data is from 2020, before the 2023 war, so displacement has changed the real distribution.
- There is distortion from working outside UTM zone 36 (reported, not corrected).

## Class settings found and reproduced (15 Nov 2026)

Sources: the QGIS Processing history on the class laptop (`user-history.db`, 18 Oct 2026) and the class rasters in `~/Projects/2026/Project_20260913/02_Raw_data`.

| Step | Class (18 Oct) | Brief |
|---|---|---|
| DEM | whole Sudan warped first, **Nearest**, resolution blank (**181.4 m**), then clipped to the state | clip, then warp **bilinear 180 m** |
| Rule (GUI Raster Calculator) | **slope 1.5–5 %, aspect 22.5–75°** (matches `redSea_slope_aspect.tiff` cell for cell, 0 mismatches) | 2–5 %, 22.5–67.5° |
| Sieve | none | 19 cells |
| Polygonize | **8-connected** | 4-connected |
| Corridor | **Join Attributes by Location** (whole patches that touch the 5 km buffer) | Intersection (clipped) |

**Why the class kept only 4 sites:** with 8-connectedness, cells touching only at a corner become one polygon whose outline touches itself. GEOS calls it invalid, and Processing's default *Invalid features filtering = Skip* drops it **without a warning**. 223 of 1,474 corridor patches were dropped, including 11 of the 15 over 150 acres. Each of the 4 class sites is a single clean patch; each of the 11 dropped ones has corner-only joins.

**All 15 sites (class rasters, numpy check):** 503.5, 144.8\*, 131.6, 125.0, 105.3\*, 102.0, 102.0, 92.1, 88.9, 88.9\*, 82.3, 79.0, 69.1\*, 65.8, 62.5 ha (\* = kept in class), 1,843 ha in total. Site 1 (503.5 ha) lies only 22 % inside 5 km, because join-by-location keeps whole patches.

**Script changes:**
- `config.json`: `"profile": "class"` (or `"brief"`). Class outputs go to `output_class/`.
- `analysis.invalid_patches`: `fix` keeps all 15; `skip` reproduces the class 4.
- Phase 0: `raster.dem_warp_order`, `dem_resampling`, a null resolution means automatic.
- Phase 2: the validity check is a `class_kept` field (1 = valid, so the class run kept it), followed by Fix Geometries; also optional sieve and dissolve, `corridor_method`, `compute_edges` and `aspect_zero_flat`.
- The log compares the sites with `export_from_Class/proposed_sites.gpkg`.
- `scoring.py`: when all values are equal (one site), every site now scores 1.0. Before, lower-is-better factors were flipped to 0.

Originals are in `_backup_20261115/`. **Next:** run `/usr/bin/python3 demo.py` on the class laptop, then check that the log shows 15 sites and that all 4 class sites are 100 % covered.

## Final setup (15 Nov 2026, afternoon) - all checked on the class laptop

### Class profile: run results
- **Phase 0** copies the class DEM: `raster.dem_warp_order = use_class_dem`, from `~/Projects/2026/Project_20260913/02_Raw_data/redSea_dem_utm36n.tiff`. This is exact and takes seconds.
  - `class_grid` (Red Sea clip warped onto the class grid) is faster than a full warp but gives only about 80 % identical cells, because Nearest picks depend on GDAL's warp approximation.
  - `warp_then_clip` warps the whole Sudan DEM first, about 400 MB.
- **Phase 2:** 1,491 patches touch the corridor, 224 of them with invalid geometry. Of the **15 sites**, 11 are invalid; the 4 valid ones are the class sites. Without the wadi exclusion each is 100 % covered; with it, class fid 22 is 86.4 % covered (by site 8), as the 300 m wadi buffer removes part of it.
  - No-wadi variant: 1,843 ha. Wadi 300 m variant: 1,785 ha (481 ha removed).
  - Before people were counted once, site 9 near Port Sudan ranked first (88.9 ha, 111,781 people gross). See the final ranking below.
  - 20 pairs of catchments overlap. Site 1 (503 ha) is only 22 % inside 5 km, because join by location keeps whole patches.

### Run folders (like a qgis2web export)
```
output_class/                      prepared inputs (Phase 0), shared by all runs + phase0_manifest.json
output_class/runs/<date_time>/     one run: 01_Data (sites, csv), 03_Rasters (slope, aspect, rule),
                                   dashboard/, logs/, config_used.json, phase2_manifest.json
output_class/latest                link to the newest run (also runs/LATEST.txt)
```
- `demo.py` starts a new run folder every time and never touches older runs.
- Phase 0 is skipped when the prepared inputs match `config.json` and the input data (fingerprint). Use `--prepare` to force it.
- `--only 3` rebuilds the dashboard of the latest run. `--no-open` stops the dashboard opening in the default browser at the end.
- The GDAL command lines (`$`) and GDAL errors (`!`) are written to the logs. Phase 0 stops on a DEM with no valid cells, and Phase 2 stops on an empty rule raster.

### Dashboard (Phase 3)
- **Layout:**
  - a navy header with the wadi switch;
  - 4 summary cards (sites, land, top-ranked site, class run kept 4 of 15);
  - a controls column beside the map;
  - a full-width ranked table with coloured score breakdown bars, a kept/lost column and an All / Kept / Lost filter;
  - criteria, score and caveats cards;
  - a navy footer: "Prepared by saltco.org · Class exercise and data: Applied Spatial Analysis using QGIS - Week 5 & 6 · Built with free & open-source software (FOSS)". The text comes from `phase3.credits`.
- **Basemaps:** "Sudan map (local tiles)" is the default. It uses the class XYZ tiles at `~/Projects/.../03_Working_Dir/custom_tiles`, zoom 2-12, about 20.6-42.6° E, so it works offline. The map is limited to the tiles' extent. `mode: link` uses a relative path; `copy` makes one shared copy in `<output>/tiles`.
  - Esri imagery and None are also offered. The online OSM layer was removed.
- **Map:** sites the class lost have dashed rank badges.
- **Scoring:** a factor where every site has the same value (or there is only one site) scores 1 for every site, in both Python and JavaScript.
- **Tests:** all 19 browser tests in `tests/test_dashboard.py` pass, including JS = Python parity.

### Files and backups
- The previous versions of every changed file are in `_backup_20261115/`.

### Decisions (15 Nov 2026, 13:05)
- **The reference result is the class profile: 15 sites.** The user explains the 4 kept and 11 lost sites on camera.
- **Population is counted once.** A 907 m population cell whose centre lies inside two or more 5 km catchments goes to the **nearest site** (Phase 2 `unique_population()`, written into `pop_5km` with a `CASE WHEN "site_id" = ... THEN ... END` expression). The old count is kept as `pop_5km_gross`.
  - Checked on the 12:52 run (300 m variant): the gross count equals Zonal Statistics at every site (294,644).
  - Counted once it is **167,912** (473 shared cells, 43 % double counting removed). For example, site 1 drops from 34,818 to 2,731 and site 14 from 47,279 to 4,594; site 9 keeps 102,398.
  - The ranking changes, because population carries 30 % of the score.

### Final run (15 Nov 2026, 15:22, run 2026-11-15_152203)
- Phase 0 skipped (up to date); Phase 2 in 42 s; Phase 3 in 2 s; the dashboard opened in the browser.
- 15 sites, 1,785 ha. 16,005 of 104,102 patches invalid overall; 224 of the 1,491 that touch the corridor.
- People within 5 km: gross 294,644 (Zonal Statistics = cell check), **counted once 167,912**, 126,732 people in 473 shared cells. No-wadi variant: 295,147 vs 167,966.
- **Final top 5** (default weights, wadi 300 m): site 7 (0.700), 9 (0.693), 8 (0.650, kept in class), 12 (0.636), 3 (0.629). Sites 7, 9, 8, 12, 3, 2 and 1 are in the top 10 under every scenario.
- No-wadi variant: the full class site fid 22 (site 5 there, 105.3 ha) ranks first (0.714).
- Written into the blog post and the YouTube plan.
- **Next:** set `profiles.class.analysis.invalid_patches` to `"skip"` and run (expect 4 sites, all kept), then set it back to `"fix"` and run again so `latest` is the 15-site run.
