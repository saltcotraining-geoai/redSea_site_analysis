# Dashboard tests (no QGIS)

Logic tests in headless Chromium with a Leaflet stand-in (`leaflet_stub.js`), so they run offline.
Needs: python3 playwright (+ `playwright install chromium`), numpy, scipy, tifffile, scikit-image.

    python3 tests/make_js_test_html.py output/dashboard/index.html /tmp/stub.html
    cp tests/leaflet_stub.js /tmp/
    python3 tests/test_dashboard.py /tmp/stub.html

`test_dashboard.py` checks: no JS errors, JS scoring == scoring.py for every variant x normalisation x scenario,
variant switch, factor toggles, slider drag, scenarios, top-N / min-score / text filters, sorting, row selection,
CSV and GeoJSON export, reset. With only one site, the "variant toggle" and "scenarios differ" checks fail by design.

`build_test_dashboard.py <check_dir> <out.html>` builds a TEST page from `tools/independent_check.py` output
(approximate geometry and circular catchments) - for trying the controls with more sites.
