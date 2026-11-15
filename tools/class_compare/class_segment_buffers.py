import sys, numpy as np, math
sys.path.insert(0,__import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))
import independent_check as ic, gpkg_lite as g
from scipy import ndimage as ndi
R=sys.argv[1] if len(sys.argv)>1 else '/home/saltco/Downloads/sdn_datasets/sudan_site_analysis/output'
dem,x0,y0,res=ic.read_tif(f'{R}/03_Rasters/redSea_dem_utm36n.tif')
slope,asp=ic.horn(dem,res); cell=res*res/1e4; acre_cells=150*0.40468564224/cell
rule=(slope>=2)&(slope<=5)&(asp>=22.5)&(asp<=67.5)
st=ndi.generate_binary_structure(2,1)
variants={'no sieve':rule,'sieve19':ic.sieve(rule,19,st)}
segs=[(f['fid'],g.lines(f['geom'])) for f in g.read(f'{R}/02_Raw_data/redSea_railways.gpkg')]
CLASS=(899223.77,2087788.26,920085.33,2140939.87)
print('class extent', CLASS, 'size km', round((CLASS[2]-CLASS[0])/1000,1), round((CLASS[3]-CLASS[1])/1000,1))
for vn,m in variants.items():
    out=[]
    for fid,lns in segs:
        xs=[p[0] for l in lns for p in l]; ys=[p[1] for l in lns for p in l]
        c0=max(0,int((min(xs)-5200-x0)/res)); c1=min(dem.shape[1],int((max(xs)+5200-x0)/res)+1)
        r0=max(0,int((y0-max(ys)-5200)/res)); r1=min(dem.shape[0],int((y0-min(ys)+5200)/res)+1)
        sub=ic.rasterize_lines(lns,(r1-r0,c1-c0),x0+c0*res,y0-r0*res,res)
        buf=ndi.distance_transform_edt(~sub)*res<=5000
        hit=buf&m[r0:r1,c0:c1]
        n=int(hit.sum())
        if n>acre_cells:
            rr,cc=np.nonzero(hit)
            out.append((fid,round(n*cell,1),x0+(c0+cc.min())*res,y0-(r0+rr.max()+1)*res,x0+(c0+cc.max()+1)*res,y0-(r0+rr.min())*res))
    if out:
        ex=(min(o[2] for o in out),min(o[3] for o in out),max(o[4] for o in out),max(o[5] for o in out))
    print(f'\n[{vn}] dissolve-all then intersect with per-segment buffers: {len(out)} features > 150 acres')
    for o in out[:12]: print('   seg fid',o[0],'area',o[1],'ha')
    if out: print('   union extent', [round(v) for v in ex], 'size km', round((ex[2]-ex[0])/1000,1), round((ex[3]-ex[1])/1000,1))
