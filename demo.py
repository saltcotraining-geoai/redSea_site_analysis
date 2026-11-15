#!/usr/bin/python3
"""Run the phases in order, each in its own process (PyQGIS state never leaks between phases).

Every run gets its own timestamped folder (like a qgis2web export):
  <output>/runs/<date_time>/   sites, tables, rasters, dashboard, logs and config_used.json of THAT run
  <output>/latest              link to the newest run
The prepared inputs (Phase 0) stay in <output>/ and are shared by all runs; Phase 0 is skipped
when they are up to date with config.json and the input data.

  /usr/bin/python3 demo.py             # new run: Phase 0 (only if needed), 2 and 3, then open the dashboard
  /usr/bin/python3 demo.py --prepare   # also rebuild the prepared inputs (Phase 0) even if up to date
  /usr/bin/python3 demo.py --only 3    # rebuild the dashboard of the latest run
  /usr/bin/python3 demo.py --only 0    # just the prepared inputs
  /usr/bin/python3 demo.py --no-open   # do not open the dashboard in the browser at the end
"""
import contextlib
import io
import os
import subprocess
import sys
import time
import webbrowser

PY = "/usr/bin/python3"          # conda breaks the QGIS imports
HERE = os.path.dirname(os.path.abspath(__file__))
PHASES = [(0, "phase0_prepare.py"), (2, "phase2_analysis.py"), (3, "phase3_dashboard.py")]
sys.path.insert(0, HERE)
import sudan_common as sc        # plain Python, no QGIS


def config():
    with contextlib.redirect_stdout(io.StringIO()):   # load_config prints its path notes
        return sc.load_config()


def main(argv):
    only = int(argv[argv.index("--only") + 1]) if "--only" in argv else None
    start = int(argv[argv.index("--from") + 1]) if "--from" in argv else 0
    cfg = config()
    env = dict(os.environ)
    run_id = None

    if only == 3:                                   # dashboard only: the latest run
        run_id = sc.latest_run_id(cfg)
        if not run_id:
            print(f"No run yet in {sc.runs_dir(cfg)} - run demo.py without --only first.")
            return 1
    elif only != 0:                                 # a new run (Phase 2 makes new results)
        run_id = sc.new_run_id()
    if run_id:
        env[sc.RUN_ENV] = run_id
        print(f"Run: {run_id}  ->  {os.path.join(sc.runs_dir(cfg), run_id)}", flush=True)

    for n, script in PHASES:
        if (only is not None and n != only) or n < start:
            continue
        if n == 0 and only is None and "--prepare" not in argv and sc.phase0_up_to_date(cfg):
            print(f"\n===== Phase 0: prepared inputs are up to date in {cfg['paths']['output_root']} - skipped "
                  f"(use --prepare to rebuild) =====", flush=True)
            continue
        print(f"\n===== Phase {n}: {script} =====", flush=True)
        t0 = time.time()
        rc = subprocess.call([PY, os.path.join(HERE, script)], cwd=HERE, env=env)
        print(f"===== Phase {n} exit {rc} ({time.time() - t0:.0f} s) =====", flush=True)
        if rc != 0:
            logs = os.path.join(sc.runs_dir(cfg), run_id, "logs") if run_id else os.path.join(cfg["paths"]["output_root"], "logs")
            print(f"Stopped: phase {n} failed. See {logs}/")
            return rc

    if run_id and (only in (None, 3)) and start <= 3:
        html = os.path.join(sc.runs_dir(cfg), run_id, cfg["phase3"]["output_html"])
        print(f"\nRun folder: {os.path.join(sc.runs_dir(cfg), run_id)}\nLatest:     {os.path.join(cfg['paths']['output_root'], 'latest')}")
        if "--no-open" not in argv:
            open_dashboard(html)
    return 0


def open_dashboard(html):
    """Open the dashboard in the user's default browser (xdg-open on Linux)."""
    if not os.path.exists(html):
        print(f"Dashboard not found: {html}")
        return
    print(f"\nOpening the dashboard in your default browser:\n  {html}", flush=True)
    try:
        if not webbrowser.open("file://" + html):
            print("  (no browser found - open the file above by hand)")
    except Exception as e:                       # e.g. no desktop session over SSH
        print(f"  (could not start a browser: {e} - open the file above by hand)")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
