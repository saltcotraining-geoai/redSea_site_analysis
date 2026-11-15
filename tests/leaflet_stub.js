// Minimal Leaflet stand-in for logic tests only (records calls, renders nothing).
(function(){
 const calls={fitBounds:0,setStyle:0,setIcon:0,popups:0};
 function chain(extra){
  const t=Object.assign({_set:new Set(),_h:{}},extra||{});
  const p=new Proxy(t,{get(o,k){
   if(k in o)return o[k];
   if(k==="getBounds")return()=>({isValid:()=>true});
   if(k==="hasLayer")return l=>o._set.has(l);
   if(k==="addLayer")return l=>{o._set.add(l);return p};
   if(k==="removeLayer")return l=>{o._set.delete(l);return p};
   if(k==="clearLayers")return()=>{o._set.clear();return p};
   if(k==="eachLayer")return fn=>{(o._children||[]).forEach(fn);return p};
   if(k==="on")return(ev,fn)=>{(o._h[ev]=o._h[ev]||[]).push(fn);return p};
   if(k==="fire")return(ev)=>{(o._h[ev]||[]).forEach(f=>f());return p};
   if(k==="setStyle")return s=>{calls.setStyle++;o._style=s;return p};
   if(k==="setIcon")return i=>{calls.setIcon++;o._icon=i;return p};
   if(k==="fitBounds")return()=>{calls.fitBounds++;return p};
   if(k==="openPopup")return()=>{calls.popups++;return p};
   if(k==="getElement")return()=>null;
   if(typeof k==="symbol")return undefined;
   return(...a)=>p;}});
  return p;}
 const L={_calls:calls,
  map:(id)=>chain(),tileLayer:()=>chain(),layerGroup:(a)=>chain(),featureGroup:()=>chain(),svg:()=>chain({_container:null}),
  geoJSON:(d,o)=>chain({_data:d,_opts:o}),circleMarker:()=>chain(),marker:(ll,o)=>chain({_ll:ll}),divIcon:o=>o,
  control:Object.assign(()=>chain({addTo(){if(this.onAdd)this.onAdd();return this}}),{layers:()=>chain(),scale:()=>chain()}),
  DomUtil:{create:(t,c)=>{const e=document.createElement(t);e.className=c||"";return e}}};
 window.L=L;
})();
