# Class comparison scripts (15 Nov 2026)

Stdlib + numpy/scipy/tifffile/scikit-image; no QGIS. Each reads the Phase 0 outputs
(default `/home/saltco/Downloads/sdn_datasets/sudan_site_analysis/output`, or pass the path).

| Script | What it does |
|---|---|
| `class_layers.py <file.qgs ...>` | Lists the layers, sources and extents of an unzipped class project |
| `criteria_sensitivity.py` | Slope/aspect shares in the corridor; site counts with and without sieve, 4/8-connectivity, wider criteria |
| `class_segment_buffers.py` | Class workflow guess: dissolve all patches, intersect with 159 per-segment (non-dissolved) buffers |
| `class_slope_degrees.py` | Tests "slope tool left in degrees" (2-5 deg) against 2-5 % |
| `class_param_search.py` | Grid of aspect window x sieve x connectivity x buffer method, ranked by fit to the class extent |

Findings are in `WORKFLOW_PLAN.md` ("Runs and class comparison").
