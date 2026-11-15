import sys,re
src,dst=sys.argv[1],sys.argv[2]
h=open(src).read()
h=re.sub(r'<link rel="stylesheet" href="https://unpkg[^>]+>','',h)
h=re.sub(r'<script src="https://unpkg[^>]+></script>','<script src="leaflet_stub.js"></script>',h)
open(dst,'w').write(h)
