import sys, xml.etree.ElementTree as ET
for q in sys.argv[1:]:
    t=ET.parse(q); r=t.getroot()
    print("\n=====", q.split('/')[-1], "| crs:", (r.find('.//projectCrs//authid').text if r.find('.//projectCrs//authid') is not None else '?'))
    for ml in r.iter('maplayer'):
        name=(ml.findtext('layername') or '').strip(); ds=(ml.findtext('datasource') or '').strip()
        typ=ml.get('type'); geom=ml.get('geometry') or ''
        ext=ml.find('extent'); e=None
        if ext is not None: e=[round(float(ext.findtext(k)),4) for k in ('xmin','ymin','xmax','ymax')]
        crs=ml.findtext('.//srs/spatialrefsys/authid')
        print(f" - {name!r:34s} {typ:7s} {geom:8s} {crs or '':11s} {ds[:110]}")
        if e: print(f"     extent {e}")
