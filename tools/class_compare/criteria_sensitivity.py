import sys, os, numpy as np, json
sys.path.insert(0,__import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))
import independent_check as ic, gpkg_lite as g
from scipy import ndimage as ndi
root=sys.argv[1] if len(sys.argv)>1 else '/home/saltco/Downloads/sdn_datasets/sudan_site_analysis/output'
dem,x0,y0,res=ic.read_tif(f'{root}/03_Rasters/redSea_dem_utm36n.tif')
slope,asp=ic.horn(dem,res)
rails=[ln for f in g.read(f'{root}/02_Raw_data/redSea_railways.gpkg') for ln in g.lines(f['geom'])]
rail_d=ndi.distance_transform_edt(~ic.rasterize_lines(rails,dem.shape,x0,y0,res))*res
state=[g.polygons(f['geom']) for f in g.read(f'{root}/01_Data/redSea_state.gpkg')][0]
cor=rail_d<=5000; cor&=ic.poly_mask(state,dem.shape,x0,y0,res,only=cor)
cell=res*res/1e4; mn=150*0.40468564224/cell
print('slope in corridor: pct cells by class', {k:round(100*float(((slope>=a)&(slope<b)&cor).sum()/cor.sum()),1) for k,(a,b) in {'<2':(0,2),'2-5':(2,5),'5-10':(5,10),'>10':(10,1e9)}.items()})
nea=(asp>=22.5)&(asp<=67.5)
print('NE aspect share in corridor', round(100*float((nea&cor).sum()/cor.sum()),1),'%')
rule=(slope>=2)&(slope<=5)&nea
print('rule cells in corridor', int((rule&cor).sum()), 'ha', round(float((rule&cor).sum()*cell)))
for conn in (4,8):
    st=ndi.generate_binary_structure(2,1 if conn==4 else 2)
    for sv in (0,19):
        m=ic.sieve(rule,sv,st) if sv else rule
        lab,k=ndi.label(m&cor,st); sz=np.bincount(lab.ravel())[1:]
        print(f'conn {conn} sieve {sv:>2}: patches {k:>6}, max {sz.max()*cell if k else 0:>7.1f} ha, >150ac {int((sz>mn).sum())}, >50ac {int((sz>mn/3).sum())}, >20ha {int((sz*cell>20).sum())}')
# dissolve-all (class gotcha): total area of all patches
print('total rule area in corridor (if everything dissolved into one feature):', round(float((rule&cor).sum()*cell)),'ha')
# smoothing DEM effect
dem_s=ndi.uniform_filter(np.nan_to_num(dem,nan=0),3)
s2,a2=ic.horn(np.where(np.isnan(dem),np.nan,dem_s),res)
r2=(s2>=2)&(s2<=5)&(a2>=22.5)&(a2<=67.5)
st=ndi.generate_binary_structure(2,1)
lab,k=ndi.label(ic.sieve(r2,19,st)&cor,st); sz=np.bincount(lab.ravel())[1:]
print(f'3x3 smoothed DEM, conn4 sieve19: patches {k}, >150ac {int((sz>mn).sum())}, max {sz.max()*cell:.0f} ha')
# wider window aspect 0-90
r3=(slope>=2)&(slope<=5)&(asp>=0)&(asp<=90)
lab,k=ndi.label(ic.sieve(r3,19,st)&cor,st); sz=np.bincount(lab.ravel())[1:]
print(f'aspect 0-90 (NE quadrant): patches {k}, >150ac {int((sz>mn).sum())}')
r4=(slope>=1)&(slope<=8)&nea
lab,k=ndi.label(ic.sieve(r4,19,st)&cor,st); sz=np.bincount(lab.ravel())[1:]
print(f'slope 1-8 %: patches {k}, >150ac {int((sz>mn).sum())}')
