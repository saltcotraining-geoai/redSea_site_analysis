import sys, math, collections
sys.path.insert(0, '.')
import gpkg_lite as g
D = sys.argv[1]
states = list(g.read(f'{D}/admin1_states.gpkg'))
rs = [s for s in states if s['adm1_name'] == 'Red Sea'][0]
polys = g.polygons(rs['geom'])
print('Red Sea area_sqkm', rs['area_sqkm'])
xs=[p[0] for r in polys for p in r[0]]; ys=[p[1] for r in polys for p in r[0]]
print('Red Sea extent', round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys)))
towns = list(g.read(f'{D}/cities_towns.gpkg'))
for t in towns:
    x,y = g.lines(t['geom'])[0][0] if t['geom'][0]=='MultiPoint' and False else (t['geom'][1][0][1] if t['geom'][0]=='MultiPoint' else t['geom'][1])
    t['xy']=(x,y); t['in']=g.point_in_polys(x,y,polys)
print('Towns in Red Sea:', [(t['NAME'],t['POP_MAX']) for t in towns if t['in']])
rails = list(g.read(f'{D}/railways.gpkg'))
inside=[]; tot_len=0
for r in rails:
    L=0; Lin=0
    for ln in g.lines(r['geom']):
        for a,b in zip(ln,ln[1:]):
            s=math.dist(a,b); L+=s
            m=((a[0]+b[0])/2,(a[1]+b[1])/2)
            if g.point_in_polys(*m,polys): Lin+=s
    r['L']=L; r['Lin']=Lin
    if Lin>0: inside.append(r)
print(f'\nFeatures intersecting Red Sea: {len(inside)} / {len(rails)}; clipped length {sum(r["Lin"] for r in inside)/1000:.1f} km')
print('by fclass/name:', collections.Counter((r['fclass'],r['name']) for r in inside))
# connectivity on clipped features (snap endpoints to 1 m)
key=lambda p:(round(p[0]),round(p[1]))
adj=collections.defaultdict(set); deg=collections.Counter()
for r in inside:
    for ln in g.lines(r['geom']):
        a,b=key(ln[0]),key(ln[-1]); adj[a].add(b); adj[b].add(a); deg[a]+=1; deg[b]+=1
seen=set(); comps=[]
for n in adj:
    if n in seen: continue
    st=[n]; c=set()
    while st:
        u=st.pop()
        if u in c: continue
        c.add(u); st.extend(adj[u]-c)
    seen|=c; comps.append(c)
print('connected components (1 m snap):', len(comps), 'sizes', sorted((len(c) for c in comps), reverse=True)[:10])
junc=[n for n,d in deg.items() if d>=3]
def near(p):
    t=min(towns,key=lambda t:math.dist(t['xy'],p)); return t['NAME'], round(math.dist(t['xy'],p)/1000,1)
print('junctions (deg>=3):', len(junc))
for j in junc: print('  ', j, 'nearest town', near(j))
# exit points: segments crossing the boundary
print('\nboundary crossings:')
for r in inside:
    for ln in g.lines(r['geom']):
        for a,b in zip(ln,ln[1:]):
            ia,ib=g.point_in_polys(*a,polys),g.point_in_polys(*b,polys)
            if ia!=ib:
                p=a if ia else b
                print('  ', key(p), 'fid', r['fid'], r['fclass'], r['name'], 'nearest', near(p))
# vertices south of Haiya
haiya=[t for t in towns if t['NAME'].lower().startswith('haiy') or 'haya' in t['NAME'].lower()]
print('\nHaiya record:', [(t['NAME'],t['xy']) for t in haiya])
