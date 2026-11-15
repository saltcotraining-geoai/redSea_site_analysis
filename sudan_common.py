"""Shared helpers for the Sudan site analysis (PyQGIS, QGIS 3.40).

Names follow the Swellendam project (qgis_common.py / site_common.py) so the
tested versions can be dropped in later. Run with /usr/bin/python3, not conda.
"""
import hashlib
import json
import os
import sys
import time

_QGS = None
_OPEN_LOGS = []


# ---------------------------------------------------------------- config
def load_config(path=None):
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["_path"] = path
    _apply_profile(cfg)
    _portable_paths(cfg, os.path.dirname(os.path.abspath(path)))
    suffix = cfg.get("_output_suffix", "")
    if suffix and not cfg["paths"]["output_root"].rstrip("/").endswith(suffix):
        cfg["paths"]["output_root"] = cfg["paths"]["output_root"].rstrip("/") + suffix
    return cfg


def _apply_profile(cfg):
    """profile = "brief" | "class": overlay that profile's values on the config sections.

    Keys starting with "_" are notes. output_suffix sends the outputs to output<suffix>,
    so a brief run and a class run can sit side by side.
    """
    name = cfg.get("profile") or "brief"
    profiles = cfg.get("profiles", {})
    if name not in profiles:
        sys.exit(f"profile '{name}' not found in config.json (use one of {[k for k in profiles if not k.startswith('_')]})")
    for section, vals in profiles[name].items():
        if section == "output_suffix":
            cfg["_output_suffix"] = vals
        elif isinstance(vals, dict):
            cfg.setdefault(section, {}).update(vals)
    cfg["_profile"] = name
    print(f"profile: {name}")


def _portable_paths(cfg, project_dir):
    """Make the project work after copying it to another computer or folder.

    The project folder sits inside the data folder (sdn_datasets/sudan_site_analysis).
    If the configured data_root does not exist here, use the project's parent folder;
    if output_root is not under an existing folder, use <project>/output.
    """
    P = cfg["paths"]
    parent = os.path.dirname(project_dir)
    if not os.path.isdir(P["data_root"]) and os.path.isdir(os.path.join(parent, P["input_vector_dir"])):
        print(f"NOTE: data_root {P['data_root']} not found here - using {parent}")
        P["data_root"] = parent
    out_parent = os.path.dirname(P["output_root"].rstrip("/"))
    if not os.path.isdir(out_parent):
        new_out = os.path.join(project_dir, "output")
        print(f"NOTE: output_root {P['output_root']} not found here - using {new_out}")
        P["output_root"] = new_out


# ---------------------------------------------------------------- run folders
# <output_root>/                 prepared inputs, shared by all runs (Phase 0): 01_Data/redSea_state,
#                                02_Raw_data/*, 03_Rasters/DEM + population, phase0_manifest.json
# <output_root>/runs/<run_id>/   everything ONE run produced (Phase 2 + 3): rasters, sites, tables,
#                                dashboard, logs, config_used.json. Never touched by a later run.
# <output_root>/latest           link to the newest run (also runs/LATEST.txt)
RUN_ENV = "SUDAN_RUN_ID"


def new_run_id():
    return time.strftime("%Y-%m-%d_%H%M%S")


def runs_dir(cfg):
    return os.path.join(cfg["paths"]["output_root"], "runs")


def latest_run_id(cfg):
    p = os.path.join(runs_dir(cfg), "LATEST.txt")
    if os.path.exists(p):
        rid = open(p, encoding="utf-8").read().strip()
        if os.path.isdir(os.path.join(runs_dir(cfg), rid)):
            return rid
    ids = sorted(d for d in os.listdir(runs_dir(cfg))) if os.path.isdir(runs_dir(cfg)) else []
    ids = [d for d in ids if os.path.isdir(os.path.join(runs_dir(cfg), d))]
    return ids[-1] if ids else None


def use_run(cfg, mode):
    """Set cfg["paths"]["run_root"].

    mode "new":    the run started by demo.py (SUDAN_RUN_ID), or a new timestamped run (Phase 2)
    mode "latest": the run started by demo.py, or the newest existing run (Phase 3 on its own)
    mode "none":   no run folder (Phase 0 on its own: logs go to <output_root>/logs)
    """
    rid = os.environ.get(RUN_ENV)
    if not rid and mode == "new":
        rid = new_run_id()
    elif not rid and mode == "latest":
        rid = latest_run_id(cfg)
        if not rid:
            sys.exit(f"No run in {runs_dir(cfg)} yet - run phase2_analysis.py (or demo.py) first.")
    if not rid:
        cfg["paths"]["run_root"] = None
        return None
    root = os.path.join(runs_dir(cfg), rid)
    os.makedirs(root, exist_ok=True)
    cfg["paths"]["run_root"] = root
    cfg["_run_id"] = rid
    return root


def run_path(cfg, sub_key, name, ext=".gpkg"):
    """A file of the current run: <run_root>/<sub folder>/<name><ext>."""
    d = os.path.join(cfg["paths"]["run_root"], cfg["paths"][sub_key])
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name + ext)


def save_run_config(cfg):
    """Keep the exact settings of this run next to its results."""
    src = cfg["_path"]
    dst = os.path.join(cfg["paths"]["run_root"], "config_used.json")
    if not os.path.exists(dst):
        import shutil
        shutil.copyfile(src, dst)


def mark_latest(cfg):
    """runs/LATEST.txt + <output_root>/latest -> runs/<run_id> (a symlink on Linux)."""
    rid = cfg.get("_run_id")
    if not rid:
        return
    with open(os.path.join(runs_dir(cfg), "LATEST.txt"), "w", encoding="utf-8") as f:
        f.write(rid + "\n")
    link = os.path.join(cfg["paths"]["output_root"], "latest")
    try:
        if os.path.islink(link):
            os.remove(link)
        if not os.path.exists(link):
            os.symlink(os.path.join("runs", rid), link)
    except OSError:
        pass                                   # e.g. a USB stick without symlinks: LATEST.txt is enough


def data_path(cfg, *parts):
    return os.path.join(cfg["paths"]["data_root"], *parts)


def out_path(cfg, sub_key, name, ext=".gpkg"):
    d = os.path.join(cfg["paths"]["output_root"], cfg["paths"][sub_key])
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name + ext)


def class_filter_expression(field, values):
    """fclass IN ('rail','narrow_gauge') style filter."""
    quoted = ",".join("'" + v.replace("'", "''") + "'" for v in values)
    return f'"{field}" IN ({quoted})'


# ---------------------------------------------------------------- QGIS start
def init_qgis(prefix="/usr"):
    """Start QGIS headless and register the Processing providers (once)."""
    global _QGS
    if _QGS is not None:
        return _QGS
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qgis.core import QgsApplication
    QgsApplication.setPrefixPath(prefix, True)
    _QGS = QgsApplication([], False)
    _QGS.initQgis()
    for p in ("/usr/share/qgis/python/plugins", os.path.expanduser("~/.local/share/QGIS/QGIS3/profiles/default/python/plugins")):
        if os.path.isdir(p) and p not in sys.path:
            sys.path.append(p)
    from processing.core.Processing import Processing
    from qgis.analysis import QgsNativeAlgorithms
    Processing.initialize()
    reg = QgsApplication.processingRegistry()
    if reg.providerById("native") is None:
        reg.addProvider(QgsNativeAlgorithms())
    return _QGS


def exit_qgis(code=0):
    """End the process cleanly.

    Standalone PyQGIS often segfaults in exitQgis() or at interpreter teardown,
    when Python and C++ free the same layer/provider objects in the wrong order.
    The outputs are already written and closed by then, so we flush and leave
    with os._exit(code). demo.py then sees a real exit code (0 = success)
    instead of 139 from the segfault.
    """
    import gc
    for lg in _OPEN_LOGS:              # a phase that failed half-way still leaves a complete log
        lg.close()
    gc.collect()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


def wgs84():
    """A function, so no QGIS object exists before init_qgis()."""
    from qgis.core import QgsCoordinateReferenceSystem
    return QgsCoordinateReferenceSystem("EPSG:4326")


# ---------------------------------------------------------------- logging
class StepLog:
    """Prints and records every step with its GUI path and Processing ID."""

    def __init__(self, cfg, phase):
        d = os.path.join(cfg["paths"].get("run_root") or cfg["paths"]["output_root"], cfg["paths"]["logs_dir"])
        os.makedirs(d, exist_ok=True)
        self.path = os.path.join(d, f"{phase}_{time.strftime('%Y%m%d_%H%M%S')}.log")
        self.n = 0
        self._f = open(self.path, "w", encoding="utf-8")
        _OPEN_LOGS.append(self)
        self.write(f"# {phase}  ({time.strftime('%Y-%m-%d %H:%M:%S')})")

    def write(self, msg):
        print(msg, flush=True)
        self._f.write(msg + "\n")
        self._f.flush()

    def step(self, tool, gui_path, alg_id, detail=""):
        self.n += 1
        self.write(f"\n[{self.n:02d}] {tool}\n     GUI: {gui_path}\n     ID : {alg_id}" + (f"\n     {detail}" if detail else ""))
        return time.time()

    def done(self, t0, out=None, count=None):
        bits = [f"{time.time() - t0:.1f} s"]
        if count is not None:
            bits.append(f"{count:,} features")
        if out:
            bits.append(os.path.basename(str(out)))
        self.write("     -> " + " | ".join(bits))

    def close(self):
        if not self._f.closed:
            self._f.close()


def no_check_context():
    """A Processing context that does NOT filter invalid geometries.

    By default Processing skips features with invalid geometry (Settings > Options >
    Processing > General > Invalid features filtering). Use this context for a step that
    must see every feature. Keep the returned object alive while its layers are in use.
    """
    from qgis.core import QgsFeatureRequest, QgsProcessingContext, QgsProject
    ctx = QgsProcessingContext()
    ctx.setProject(QgsProject.instance())
    try:
        from qgis.core import Qgis
        ctx.setInvalidGeometryCheck(Qgis.InvalidGeometryCheck.NoCheck)
    except AttributeError:
        ctx.setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)
    return ctx


def _feedback(log):
    """Feedback that writes the GDAL command line and any errors/warnings into the log."""
    from qgis.core import QgsProcessingFeedback

    class LogFeedback(QgsProcessingFeedback):
        def reportError(self, error, fatalError=False):
            log.write(f"     ! {error}")

        def pushWarning(self, warning):
            log.write(f"     ! {warning}")

        def pushCommandInfo(self, info):          # e.g. the gdalwarp command, as in the GUI log
            log.write(f"     $ {info}")

        def pushConsoleInfo(self, info):
            if any(w in info.lower() for w in ("error", "warning", "failed")):
                log.write(f"     > {info.strip()}")

    return LogFeedback()


def run_alg(log, tool, gui_path, alg_id, params, detail="", context=None):
    """processing.run with a logged header; returns the result dict."""
    import processing
    from qgis.core import QgsVectorLayer
    t0 = log.step(tool, gui_path, alg_id, detail)
    kw = {"feedback": _feedback(log)}
    if context is not None:
        kw["context"] = context
    res = processing.run(alg_id, params, **kw)
    out = res.get("OUTPUT")
    count, label = None, out
    if isinstance(out, QgsVectorLayer):            # TEMPORARY_OUTPUT -> memory layer
        count, label = out.featureCount(), f"memory: {out.name()}"
    elif isinstance(out, str) and out.lower().endswith(".gpkg"):
        lyr = QgsVectorLayer(out, "tmp", "ogr")
        if lyr.isValid():
            count = lyr.featureCount()
    log.done(t0, label, count)
    return res


def phase0_fingerprint(cfg):
    """Same fingerprint in Phase 0 (writes it) and Phase 2 (checks it)."""
    P = cfg["paths"]
    vin = lambda n: data_path(cfg, P["input_vector_dir"], n + ".gpkg")
    inputs = [vin(cfg["study_area"]["layer"]), data_path(cfg, P["dem"]), data_path(cfg, P["population"])]
    inputs += [vin(v["source"]) for v in cfg["vector_layers"].values() if v.get("enabled", True)]
    return fingerprint(cfg, ["paths", "crs", "study_area", "vector_layers", "raster"], inputs)


# ---------------------------------------------------------------- staleness
def fingerprint(cfg, sections, input_files):
    """Hash of the config sections + input file size/mtime."""
    # Machine-independent: absolute roots are left out, input files are named relative to
    # data_root, so a copy on another computer (rsync -t keeps mtimes) is not "stale".
    h = hashlib.sha256()
    for s in sections:
        v = cfg.get(s)
        if s == "paths" and isinstance(v, dict):
            v = {k: x for k, x in v.items() if k not in ("data_root", "output_root", "run_root")}
        h.update(json.dumps(v, sort_keys=True).encode())
    root = cfg["paths"]["data_root"]
    for p in sorted(input_files):
        st = os.stat(p)
        h.update(f"{os.path.relpath(p, root)}|{st.st_size}|{int(st.st_mtime)}".encode())
    return h.hexdigest()[:16]


def remap_output(cfg, p):
    """A path stored in a manifest on another computer -> the same file under this output_root."""
    if not isinstance(p, str) or os.path.exists(p):
        return p
    base = os.path.basename(cfg["paths"]["output_root"].rstrip("/"))
    for marker in (f"/{base}/", "/output/"):
        parts = p.replace("\\", "/").split(marker, 1)
        if len(parts) == 2:
            q = os.path.join(cfg["paths"]["output_root"], parts[1])
            if os.path.exists(q):
                return q
    return p


def manifest_path(cfg, phase):
    """phase0 = prepared inputs (shared, output_root); phase2 = one run (run_root)."""
    root = cfg["paths"]["output_root"] if phase == "phase0" else cfg["paths"]["run_root"]
    return os.path.join(root, f"{phase}_manifest.json")


def phase0_up_to_date(cfg):
    """True when the prepared inputs were made from the current settings and inputs (Phase 0 can be skipped)."""
    p = manifest_path(cfg, "phase0")
    if not os.path.exists(p):
        return False
    with open(p, encoding="utf-8") as f:
        man = json.load(f)
    outs = [remap_output(cfg, v) for v in man.get("outputs", {}).values() if isinstance(v, str)]
    return man.get("fingerprint") == phase0_fingerprint(cfg) and all(os.path.exists(o) for o in outs)


def write_manifest(cfg, phase, fp, outputs):
    p = manifest_path(cfg, phase)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"phase": phase, "fingerprint": fp, "created": time.strftime("%Y-%m-%d %H:%M:%S"), "outputs": outputs}, f, indent=2)
    return p


def check_stale(cfg, phase, fp):
    """Warn (do not stop) when prepared data was built from other settings."""
    p = manifest_path(cfg, phase)
    if not os.path.exists(p):
        print(f"WARNING: no {phase} manifest - run {phase} first.")
        return True
    with open(p, encoding="utf-8") as f:
        old = json.load(f).get("fingerprint")
    if old != fp:
        print(f"WARNING: {phase} outputs are STALE (settings or inputs changed). Re-run {phase}.")
        return True
    return False
