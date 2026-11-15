import sys, numpy as np, itertools
sys.path.insert(0,__import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))
import independent_check as ic, gpkg_lite as g
from scipy import ndimage as ndi
R=sys.argv[1] if len(sys.argv)>1 else '/home/saltco/Downloads/sdn_datasets/sudan_site_analysis/output'
dem,x0,y0,res=ic.read_tif(f'{R}/03_Rasters/redSea_dem_utm36n.tif')
slope,asp=ic.horn(dem,res); cell=res*res/1e4; mn=150*0.40468564224/cell
segs=[g.lines(f['geom']) for f in g.read(f'{R}/02_Raw_data/redSea_railways.gpkg')]
allr=[l for s in segs for l in s]
raild=ndi.distance_transform_edt(~ic.rasterize_lines(allr,dem.shape,x0,y0,res))*res
cor=raild<=5000
# per-segment buffer windows (precompute)
segbuf=[]
for lns in segs:
    xs=[p[0] for l in lns for p in l]; ys=[p[1] for l in lns for p in l]
    c0=max(0,int((min(xs)-5200-x0)/res)); c1=min(dem.shape[1],int((max(xs)+5200-x0)/res)+1)
    r0=max(0,int((y0-max(ys)-5200)/res)); r1=min(dem.shape[0],int((y0-min(ys)+5200)/res)+1)
    sub=ic.rasterize_lines(lns,(r1-r0,c1-c0),x0+c0*res,y0-r0*res,res)
    segbuf.append((r0,r1,c0,c1,ndi.distance_transform_edt(~sub)*res<=5000))
CL=(899224,2087788,920085,2140940)
def ext_of(boxes):
    return (min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes))
res_list=[]
for (amin,amax),sv,conn in itertools.product([(22.5,67.5),(0,90),(15,75)],[0,5,10,19],[4,8]):
    st=ndi.generate_binary_structure(2,1 if conn==4 else 2)
    rule=(slope>=2)&(slope<=5)&(asp>=amin)&(asp<=amax)
    m=ic.sieve(rule,sv,st) if sv else rule
    # A: separate patches in dissolved corridor
    lab,k=ndi.label(m&cor,st); objs=ndi.find_objects(lab); sz=np.bincount(lab.ravel())
    keep=[i for i in range(1,k+1) if sz[i]>mn]
    boxes=[(x0+objs[i-1][1].start*res,y0-objs[i-1][0].stop*res,x0+objs[i-1][1].stop*res,y0-objs[i-1][0].start*res) for i in keep]
    res_list.append(('patches',amin,amax,sv,conn,len(keep),ext_of(boxes) if boxes else None))
    # B: separate patches x per-segment buffers (non-dissolved buffer, singlepart): each patch piece per segment
    cntB=0; boxesB=[]
    for r0,r1,c0,c1,b in segbuf:
        l2,k2=ndi.label(m[r0:r1,c0:c1]&b,st); s2=np.bincount(l2.ravel())
        o2=ndi.find_objects(l2)
        for i in range(1,k2+1):
            if s2[i]>mn:
                cntB+=1; o=o2[i-1]; boxesB.append((x0+(c0+o[1].start)*res,y0-(r0+o[0].stop)*res,x0+(c0+o[1].stop)*res,y0-(r0+o[0].start)*res))
    res_list.append(('patch x segbuf',amin,amax,sv,conn,cntB,ext_of(boxesB) if boxesB else None))
def score(e):
    if not e: return 9e9
    return sum(abs(a-b) for a,b in zip(e,CL))
print('class extent',CL,'20.9 x 53.2 km\n')
for r in sorted(res_list,key=lambda r:(score(r[6]))) [:14]:
    e=r[6]; 
    print(f'{r[0]:15s} aspect {r[1]}-{r[2]} sieve {r[3]:>2} conn {r[4]}: {r[5]:>3} features', (f'extent {[round(v) for v in e]} ({(e[2]-e[0])/1e3:.1f}x{(e[3]-e[1])/1e3:.1f} km) misfit {score(e)/1000:.0f} km' if e else ''))
