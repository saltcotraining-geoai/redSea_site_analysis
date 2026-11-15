# Clicks vs Code: Red Sea Site Analysis

*Episode 1 — Four Sites or Fifteen?* · a follow-up to *Applied Spatial Analysis Using QGIS* (Weeks 5 & 6)

**Where in Red Sea State, Sudan, is there land that faces northeast, has a gentle slope, and lies within 5 km of the Port Sudan–Khartoum railway? How large is each site, and how many people live within 5 km of it?**

This repository turns the Week 5 and Week 6 class exercise of *Applied Spatial Analysis Using QGIS — GIS for Surveyors (2026 Cohort)* into a repeatable PyQGIS workflow. One command prepares the data, finds and scores the sites, and opens an interactive dashboard that works offline.

> In class we found **4** sites. The same data and the same steps hold **15**. QGIS silently skipped the other 11 as *invalid geometry*. Read the story on [saltco.org](https://saltco.org/blog.html) and watch *Clicks vs Code: Four Sites or Fifteen?* on [YouTube @saltcoTraining](https://www.youtube.com/@saltcoTraining).

Built with **free & open-source software**: QGIS 3.40–3.44, GDAL, Python 3 and Leaflet, on Linux Mint.

---

## Quick start

```bash
git clone https://github.com/saltcotraining-geoai/redSea_site_analysis.git
cd redSea_site_analysis
/usr/bin/python3 demo.py
```

The data is not in this repository (the SRTM DEM alone is 83 MB). Put the project folder inside the class data folder, next to `01_Data/`, `02_DEM_Rasters/` and `03_Population_Raster/`, as on the class flash drive (`sdn_datasets/redSea_site_analysis/`); `config.json` → `paths` says where. Results are written to `output/` and `output_class/`, which git ignores.

Use the system Python (`/usr/bin/python3`), not conda: conda breaks the QGIS imports.

| Command | What it does |
|---|---|
| `python3 demo.py` | A new run: Phase 0 (only when needed), Phase 2 and Phase 3, then opens the dashboard in your browser |
| `python3 demo.py --prepare` | Also rebuilds the prepared inputs, even when they are up to date |
| `python3 demo.py --only 3` | Rebuilds the dashboard of the latest run |
| `python3 demo.py --only 0` | Prepares the inputs only |
| `python3 demo.py --no-open` | Does not open the browser at the end (handy while recording) |

## What the phases do

| Phase | Script | Steps (each is logged with its QGIS menu path and Processing ID) |
|---|---|---|
| 0 — prepare | `phase0_prepare.py` | Red Sea State boundary → clip railways, roads, rivers, water bodies, districts, towns → DEM to UTM 36N → population raster clipped with a 6 km margin |
| 2 — analyse | `phase2_analysis.py` | 5 km railway corridor → slope % and aspect → rule raster → Polygonize → validity check (fix or skip) → corridor step → wadi exclusion → area → > 150 acres → 5 km catchment population (each person counted once) → score factors → combined score, rank and weight sensitivity |
| 3 — dashboard | `phase3_dashboard.py` + `dashboard_html.py` | GeoJSON layers in EPSG:4326 → one self-contained `index.html`: map, ranked table, live weights and scenarios, CSV/GeoJSON export |

The scoring itself is in `scoring.py` (pure Python, testable without QGIS), because QGIS expressions have no `rank()` function. The dashboard repeats the same scoring in the browser, and `tests/test_dashboard.py` checks that both give the same result.

## Two profiles: class and brief

`config.json` → `"profile"` chooses the settings:

| Setting | `"class"` (what ran on 18 Oct 2026) | `"brief"` (the course brief) |
|---|---|---|
| DEM | The class DEM: whole Sudan warped with Nearest, automatic 181.4 m cells | Clipped, then warped bilinear to 180 m |
| Slope / aspect rule | 1.5–5 %, 22.5–75° | 2–5 %, 22.5–67.5° |
| Sieve | none | 19 cells |
| Polygonize | 8-connected | 4-connected |
| Corridor | Join Attributes by Location (whole patches that touch the 5 km corridor) | Intersection (clipped at 5 km) |
| Result | **15 sites** (4 kept by the class run) | **1 site** |

The class settings were read from the QGIS Processing history and checked against the class rule raster: 0 mismatches in 11.6 million cells.

`analysis.invalid_patches` decides what happens to patches whose cells touch only at a corner (invalid geometry after 8-connected Polygonize):

- `"fix"` (default) — Fix Geometries keeps every patch → 15 sites
- `"skip"` — drops them, as QGIS did in class → 4 sites

Every site carries a `class_kept` field (1 = the class run kept it).

### Results (class profile, run of 15 Nov 2026)

15 sites, 1,785 ha (300 m wadi exclusion on). About 167,900 people live within 5 km, each counted once; adding the overlapping catchments site by site would give 294,644. The top five with the default weights:

| Rank | Site | Area (ha) | People within 5 km (counted once) | To road (m) | Score | Class run |
|---|---|---|---|---|---|---|
| 1 | 7 | 92.1 | 7,782 | 172 | 0.700 | lost |
| 2 | 9 | 88.9 | 102,398 | 709 | 0.693 | lost |
| 3 | 8 | 90.9 | 5,945 | 3,605 | 0.650 | kept |
| 4 | 12 | 79.0 | 17,445 | 151 | 0.636 | lost |
| 5 | 3 | 131.6 | 8,052 | 4,515 | 0.629 | lost |

Sites 7, 9, 8, 12, 3, 2 and 1 stay in the top ten under all five weight scenarios. Without the wadi exclusion, site 8 is the full 105 ha class site and ranks first.

## Outputs: one folder per run

```
output_class/                      prepared inputs (Phase 0), shared by all runs
├── 01_Data/ 02_Raw_data/ 03_Rasters/
├── phase0_manifest.json
├── latest -> runs/<date_time>     the newest run
└── runs/<date_time>/              everything ONE run produced — never touched again
    ├── 01_Data/      best_locations*.gpkg + .csv, candidate patches, corridor, wadi buffer, catchments
    ├── 03_Rasters/   slope, aspect, rule
    ├── dashboard/    index.html + data/  (open or share this folder)
    ├── logs/         phase0/2/3 logs: every tool, its GUI path, Processing ID and GDAL command
    ├── config_used.json
    └── phase2_manifest.json
```

The `"brief"` profile writes to `output/` in the same layout. Phase 0 is skipped when the prepared inputs match `config.json` and the input data (a settings fingerprint).

## The dashboard

- Summary cards: sites, land, the top-ranked site, and how many sites the class run kept.
- Map with rank badges (dashed = lost in the class run), the 5 km catchment of the selected site, and three basemaps: **local XYZ tiles** (offline, default), Esri imagery, none.
- Ranked table with a coloured score-breakdown bar per site and an All / Kept in class / Lost in class filter.
- Live controls: wadi exclusion (300 m / off), weight scenarios (balanced, workforce, land, access), factor weights, normalisation, top-N and minimum score.
- Exports what you see as CSV or GeoJSON.

The local tiles come from QGIS *Generate XYZ tiles (Directory)*; set their folder in `config.json` → `phase3.custom_tiles`. `mode: "link"` points to the folder; `mode: "copy"` copies it once (about 333 MB) so the output folder can travel on a USB stick.

## Data

| Layer | File (under `sdn_datasets/`) | Note |
|---|---|---|
| Admin, railways, roads, rivers, water bodies, towns | `01_Data/training_utm36n/*.gpkg` | UTM 36N (EPSG:32636); railway = Port Sudan → Haiya → River Nile border, 159 segments, about 420 km |
| Elevation | `02_DEM_Rasters/srtm_sudan.tif` | SRTM, 6 arc-second (about 180 m) |
| Population | `03_Population_Raster/population_2020_1km.tif` | 2020 gridded population, about 907 m cells |

## Caveats

- **Population** is a 2020 model from **before the 2023 war**; displacement has changed where people live. A population cell inside two or more 5 km catchments is counted once, for the nearest site (`pop_5km`); `pop_5km_gross` counts it for every site.
- **Join by location** keeps whole patches: the largest site (about 500 ha) is only 22 % inside 5 km.
- **Projection**: Red Sea State lies outside UTM zone 36, so planar areas are about 0.3 % too large; both planar and ellipsoidal areas are reported.
- **Weights are judgements**: compare the ranking across the scenarios before choosing a site.

## Lessons this exercise teaches

1. Read the tool settings, not only the result — QGIS keeps a Processing history.
2. Check geometry validity after Polygonize; set *Invalid features filtering* to *stop*, not *skip*.
3. Choose Join by location or Intersection on purpose: "touches the corridor" ≠ "inside the corridor".
4. Count people once where buffers overlap.
5. Use Nearest resampling for categories, bilinear for elevation.
6. Make the work repeatable: logs, saved settings, one folder per run.

## Repository layout

```
config.json            all settings: profiles, criteria, scoring, styles, dashboard
demo.py                runs the phases, one folder per run, opens the dashboard
phase0_prepare.py      data preparation
phase2_analysis.py     site analysis and scoring
phase3_dashboard.py    dashboard data; dashboard_html.py = the page
scoring.py             normalisation, weights, ranks (pure Python)
sudan_common.py        config, paths, run folders, logging, manifests
tests/                 browser tests for the dashboard (Playwright + Chromium)
tools/                 independent numpy check, railway check, class comparison scripts
WORKFLOW_PLAN.md       the full working notes: decisions, runs and findings
```

## Credits and licence

Prepared by **[saltco.org](https://saltco.org)** — Sallah Yaya, *Computing & Capacity Building*. Class exercise and data: *Applied Spatial Analysis Using QGIS — GIS for Surveyors (2026 Cohort), Weeks 5 & 6*.

- YouTube: [@saltcoTraining](https://www.youtube.com/@saltcoTraining) — playlist *Applied Spatial Analysis Using QGIS — Live Sessions & Labs*
- GitHub: [saltcotraining-geoai/redSea_site_analysis](https://github.com/saltcotraining-geoai/redSea_site_analysis)

Code: [GNU GPL v3.0](LICENSE). Map data © OpenStreetMap contributors. Built with free & open-source software.
