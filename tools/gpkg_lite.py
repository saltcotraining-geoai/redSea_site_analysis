"""Minimal GeoPackage reader (no GDAL): parses GPKG binary headers + WKB."""
import sqlite3, struct

def _wkb(buf, off=0):
    bo = '<' if buf[off] == 1 else '>'
    t = struct.unpack_from(bo + 'I', buf, off + 1)[0]
    off += 5
    has_z = (t // 1000) in (1, 3) or (t & 0x80000000)
    has_m = (t // 1000) in (2, 3) or (t & 0x40000000)
    t = (t & 0xFFFF) % 1000
    dim = 2 + bool(has_z) + bool(has_m)

    def pts(off):
        n = struct.unpack_from(bo + 'I', buf, off)[0]; off += 4
        out = [struct.unpack_from(bo + 'dd', buf, off + i * 8 * dim) for i in range(n)]
        return out, off + n * 8 * dim

    if t == 1:
        p = struct.unpack_from(bo + 'dd', buf, off); return ('Point', p), off + 8 * dim
    if t == 2:
        p, off = pts(off); return ('LineString', p), off
    if t == 3:
        n = struct.unpack_from(bo + 'I', buf, off)[0]; off += 4; rings = []
        for _ in range(n):
            r, off = pts(off); rings.append(r)
        return ('Polygon', rings), off
    if t in (4, 5, 6, 7):
        n = struct.unpack_from(bo + 'I', buf, off)[0]; off += 4; parts = []
        for _ in range(n):
            g, off = _wkb(buf, off); parts.append(g)
        return ({4: 'MultiPoint', 5: 'MultiLineString', 6: 'MultiPolygon', 7: 'GeometryCollection'}[t], parts), off
    raise ValueError(f'WKB type {t}')

def parse(blob):
    flags = blob[3]
    env = (flags >> 1) & 7
    off = 8 + {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[env]
    return _wkb(blob, off)[0]

def read(path, table=None):
    c = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    table = table or c.execute('select table_name from gpkg_contents').fetchone()[0]
    gcol = c.execute('select column_name from gpkg_geometry_columns where table_name=?', (table,)).fetchone()[0]
    cols = [r[1] for r in c.execute(f'pragma table_info("{table}")')]
    for row in c.execute(f'select * from "{table}"'):
        d = dict(zip(cols, row))
        g = d.pop(gcol)
        d['geom'] = parse(g) if g else None
        yield d

def polygons(geom):
    """List of rings-lists from Polygon / MultiPolygon."""
    k, v = geom
    if k == 'Polygon': return [v]
    return [p[1] for p in v]

def lines(geom):
    k, v = geom
    if k == 'LineString': return [v]
    return [p[1] for p in v]

def point_in_rings(x, y, rings):
    inside = False
    for ring in rings:
        n = len(ring); j = n - 1
        for i in range(n):
            xi, yi = ring[i]; xj, yj = ring[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                inside = not inside
            j = i
    return inside

def point_in_polys(x, y, polys):
    return any(point_in_rings(x, y, r) for r in polys)
