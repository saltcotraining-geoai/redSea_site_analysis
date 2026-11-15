import sys, numpy as np, math
sys.path.insert(0,__import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))
import independent_check as ic, gpkg_lite as g
from scipy import ndimage as ndi
R=sys.argv[1] if len(sys.argv)>1 else '/home/saltco/Downloads/sdn_datasets/sudan_site_analysis/output'
dem,x0,y0,res=ic.read_tif(f'{R}/03_Rasters/redSea_dem_utm36n.tif')
slope,asp=ic.horn(dem,res); deg=np.degrees(np.arctan(slope/100)); cell=res*res/1e4; mn=150*0.40468564224/cell
rails=[ln for f in g.read(f'{R}/02_Raw_data/redSea_railways.gpkg') for ln in g.lines(f['geom'])]
cor=ndi.distance_transform_edt(~ic.rasterize_lines(rails,dem.shape,x0,y0,res))*res<=5000
st=ndi.generate_binary_structure(2,1)
CLASS=(899224,2087788,920085,2140940)
def run(name,rule,sv):
    m=ic.sieve(rule,sv,st) if sv else rule
    lab,k=ndi.label(m&cor,st); objs=ndi.find_objects(lab); sz=np.bincount(lab.ravel())
    keep=[i for i in range(1,k+1) if sz[i]>mn]
    if not keep: print(f'{name:42s} 0 sites'); return
    ex=[min(x0+objs[i-1][1].start*res for i in keep), min(y0-objs[i-1][0].stop*res for i in keep),
        max(x0+objs[i-1][1].stop*res for i in keep), max(y0-objs[i-1][0].start*res for i in keep)]
    inside=all(CLASS[0]-2000<=v for v in [ex[0]]) 
    print(f'{name:42s} {len(keep):3d} sites, {sum(sz[i] for i in keep)*cell:7.0f} ha, extent {[round(v) for v in ex]} ({(ex[2]-ex[0])/1e3:.1f} x {(ex[3]-ex[1])/1e3:.1f} km)')
ne=(asp>=22.5)&(asp<=67.5)
for sv in (0,19):
    run(f'slope 2-5 % , sieve {sv}', (slope>=2)&(slope<=5)&ne, sv)
    run(f'slope 2-5 DEGREES, sieve {sv}', (deg>=2)&(deg<=5)&ne, sv)
print('class extent', CLASS, '(20.9 x 53.2 km)')
