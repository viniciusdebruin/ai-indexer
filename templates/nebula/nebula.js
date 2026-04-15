/**
 * Code Nebula v8 — Cinematic Three.js visualisation
 *
 * Features:
 *  - UnrealBloomPass via EffectComposer (nodes with priority > 80 glow intensely)
 *  - QuadraticBezierCurve3 edges with directional particle flow
 *  - Gas cloud (Points) around module clusters
 *  - CSS2DRenderer labels (crisp typography)
 *  - TWEEN.js fly-to-node animations on click
 */

// ── Scene setup ───────────────────────────────────────────────────────────────
const canvas   = document.getElementById("nebula-canvas");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(canvas.clientWidth, canvas.clientHeight);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.1;

const scene  = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(55, canvas.clientWidth / canvas.clientHeight, 0.1, 6000);
camera.position.set(0, 0, 380);

const controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.enableDamping   = true;
controls.dampingFactor   = 0.04;
controls.autoRotate      = true;
controls.autoRotateSpeed = 0.25;
controls.minDistance     = 30;
controls.maxDistance     = 1500;

// ── Effect Composer + Bloom ───────────────────────────────────────────────────
const composer   = new THREE.EffectComposer(renderer);
composer.addPass(new THREE.RenderPass(scene, camera));
const bloomPass  = new THREE.UnrealBloomPass(
  new THREE.Vector2(canvas.clientWidth, canvas.clientHeight),
  0.9, 0.5, 0.55
);
composer.addPass(bloomPass);

// ── CSS2D label renderer ──────────────────────────────────────────────────────
const labelRenderer = new THREE.CSS2DRenderer();
labelRenderer.setSize(canvas.clientWidth, canvas.clientHeight);
labelRenderer.domElement.style.cssText =
  "position:absolute;top:0;left:0;pointer-events:none;";
document.getElementById("nebula-view").appendChild(labelRenderer.domElement);

// ── Ambient nebula background ─────────────────────────────────────────────────
const nebVS = `
  varying vec2 vUv;
  void main(){ vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.); }
`;
const nebFS = `
  varying vec2 vUv;
  uniform float uTime, uHealth;
  float h21(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5); }
  float noise(vec2 p){
    vec2 i=floor(p),f=fract(p),u=f*f*(3.-2.*f);
    return mix(mix(h21(i),h21(i+vec2(1,0)),u.x),mix(h21(i+vec2(0,1)),h21(i+vec2(1,1)),u.x),u.y);
  }
  void main(){
    vec2 uv=(vUv-.5)*3.;
    float n=noise(uv*1.2+uTime*.025)+noise(uv*2.5-uTime*.018)*.5+noise(uv*5.+uTime*.01)*.25;
    n=clamp(n/1.5,0.,1.);
    vec3 cold=mix(vec3(.01,.02,.08),vec3(.03,.09,.24),n);
    vec3 warm=mix(vec3(.07,.02,.01),vec3(.28,.08,.0),n);
    gl_FragColor=vec4(mix(warm,cold,uHealth),n*.15+.04);
  }
`;
const nebMat = new THREE.ShaderMaterial({
  vertexShader: nebVS, fragmentShader: nebFS,
  uniforms: { uTime: { value: 0 }, uHealth: { value: HEALTH_SCORE } },
  transparent: true, depthWrite: false, side: THREE.DoubleSide,
});
const nebPlane = new THREE.Mesh(new THREE.PlaneGeometry(5000, 5000), nebMat);
nebPlane.position.z = -900;
scene.add(nebPlane);

// ── Background stars ──────────────────────────────────────────────────────────
(function buildBgStars() {
  const N = 2500, pos = new Float32Array(N * 3);
  for (let i = 0; i < N; i++) {
    const r  = 450 + Math.random() * 650;
    const th = Math.random() * Math.PI * 2;
    const ph = Math.acos(2 * Math.random() - 1);
    pos[i*3]   = r * Math.sin(ph) * Math.cos(th);
    pos[i*3+1] = r * Math.sin(ph) * Math.sin(th);
    pos[i*3+2] = r * Math.cos(ph);
  }
  const bg = new THREE.BufferGeometry();
  bg.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  scene.add(new THREE.Points(bg, new THREE.PointsMaterial({
    color: 0xffffff, size: 0.55, transparent: true, opacity: 0.35, sizeAttenuation: true,
  })));
})();

// ── Domain colour palette ─────────────────────────────────────────────────────
const DC = {
  auth: new THREE.Color(1,0.85,0.1), database: new THREE.Color(0.1,0.5,1),
  ui: new THREE.Color(1,0.1,0.8),    api: new THREE.Color(0.1,0.9,0.6),
  services: new THREE.Color(0.6,0.3,1), utils: new THREE.Color(0.5,0.9,0.2),
  config: new THREE.Color(0.9,0.6,0.1), billing: new THREE.Color(0.95,0.75,0.1),
  leads: new THREE.Color(0.2,1,0.4),    cache: new THREE.Color(0.4,0.7,1),
  security: new THREE.Color(1,0.3,0.3), search: new THREE.Color(0.3,0.85,0.7),
  default: new THREE.Color(0.4,0.4,0.6),
};
function domCol(d) { return DC[d] || DC.default; }

// ── Force layout ──────────────────────────────────────────────────────────────
const fileKeys = Object.keys(ALL_FILES);
const N_nodes  = fileKeys.length;
const dirCenters = {};
const nodes = fileKeys.map((k, i) => {
  const fd  = ALL_FILES[k];
  const dir = k.split("/").slice(0, -1).join("/") || "root";
  if (!dirCenters[dir]) {
    const ang = Object.keys(dirCenters).length * 2.399;
    const r   = 30 + Math.sqrt(Object.keys(dirCenters).length) * 28;
    dirCenters[dir] = {
      x: r * Math.cos(ang), y: r * Math.sin(ang) * 0.6, z: (Math.random()-0.5)*70,
    };
  }
  const dc = dirCenters[dir];
  return {
    k, fd, idx: i,
    x: dc.x + (Math.random()-0.5)*28, y: dc.y + (Math.random()-0.5)*28, z: dc.z + (Math.random()-0.5)*28,
    vx: 0, vy: 0, vz: 0, seed: Math.random() * Math.PI * 2,
  };
});
const nodeIdx = {};
fileKeys.forEach((k, i) => { nodeIdx[k] = i; });

(function forceLayout() {
  const kIdeal = Math.sqrt(55000 / Math.max(N_nodes, 1));
  const step   = Math.max(1, Math.floor(N_nodes / 80));
  for (let iter = 0; iter < 90; iter++) {
    const cool = 0.92 - iter * 0.007;
    for (let i = 0; i < N_nodes; i += step) {
      for (let j = i+1; j < N_nodes; j += step) {
        const ni=nodes[i], nj=nodes[j];
        const dx=nj.x-ni.x, dy=nj.y-ni.y, dz=nj.z-ni.z;
        const dist=Math.sqrt(dx*dx+dy*dy+dz*dz)+1;
        const f=Math.min(kIdeal*kIdeal/dist,160), inv=1/dist;
        ni.vx-=dx*inv*f; ni.vy-=dy*inv*f; ni.vz-=dz*inv*f;
        nj.vx+=dx*inv*f; nj.vy+=dy*inv*f; nj.vz+=dz*inv*f;
      }
    }
    FULL_EDGES.forEach(([src,dst]) => {
      const ni=nodes[nodeIdx[src]], nj=nodes[nodeIdx[dst]];
      if(!ni||!nj) return;
      const dx=nj.x-ni.x, dy=nj.y-ni.y, dz=nj.z-ni.z;
      const dist=Math.sqrt(dx*dx+dy*dy+dz*dz)+1;
      const f=Math.min(Math.max((dist-kIdeal)*0.03,-18),18), inv=1/dist;
      ni.vx+=dx*inv*f; ni.vy+=dy*inv*f; ni.vz+=dz*inv*f;
      nj.vx-=dx*inv*f; nj.vy-=dy*inv*f; nj.vz-=dz*inv*f;
    });
    nodes.forEach(n => {
      const sp=Math.sqrt(n.vx*n.vx+n.vy*n.vy+n.vz*n.vz);
      if(sp>35){const s=35/sp; n.vx*=s; n.vy*=s; n.vz*=s;}
      n.x+=n.vx*cool; n.y+=n.vy*cool; n.z+=n.vz*cool;
      n.vx*=0.6; n.vy*=0.6; n.vz*=0.6;
    });
  }
  nodes.forEach(n => {
    if(!isFinite(n.x)) n.x=(Math.random()-.5)*120;
    if(!isFinite(n.y)) n.y=(Math.random()-.5)*120;
    if(!isFinite(n.z)) n.z=(Math.random()-.5)*120;
  });
})();

// ── Node geometry ─────────────────────────────────────────────────────────────
const posArr  = new Float32Array(N_nodes * 3);
const colArr  = new Float32Array(N_nodes * 3);
const sizeArr = new Float32Array(N_nodes);
const seedArr = new Float32Array(N_nodes);
nodes.forEach((n, i) => {
  posArr[i*3]=n.x; posArr[i*3+1]=n.y; posArr[i*3+2]=n.z;
  const col=domCol(n.fd.domain);
  colArr[i*3]=col.r; colArr[i*3+1]=col.g; colArr[i*3+2]=col.b;
  sizeArr[i] = 2.5 + (n.fd.priority||0)*0.08;
  seedArr[i] = n.seed;
});

const starVS = `
  attribute float aSize; attribute vec3 aColor; attribute float aSeed;
  uniform float uTime; varying vec3 vColor; varying float vGlow;
  void main(){
    vColor=aColor;
    float pulse=1.+0.12*sin(uTime*2.+aSeed*6.28);
    vGlow=aSize>9.?1.:0.;
    gl_PointSize=aSize*pulse;
    gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);
  }
`;
const starFS = `
  varying vec3 vColor; varying float vGlow;
  void main(){
    vec2 uv=gl_PointCoord*2.-1.; float d=dot(uv,uv);
    if(d>1.) discard;
    float alpha=exp(-d*3.5)+exp(-d*1.2)*.4;
    gl_FragColor=vec4(vColor*(1.+vGlow*2.),alpha);
  }
`;
const starGeo = new THREE.BufferGeometry();
starGeo.setAttribute("position", new THREE.BufferAttribute(posArr, 3));
starGeo.setAttribute("aColor",   new THREE.BufferAttribute(colArr, 3));
starGeo.setAttribute("aSize",    new THREE.BufferAttribute(sizeArr, 1));
starGeo.setAttribute("aSeed",    new THREE.BufferAttribute(seedArr, 1));
const starMat = new THREE.ShaderMaterial({
  vertexShader: starVS, fragmentShader: starFS,
  uniforms: { uTime: { value: 0 } },
  transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
});
const stars = new THREE.Points(starGeo, starMat);
scene.add(stars);

// ── QuadraticBezierCurve3 edges + directional flow ────────────────────────────
const edgePositions = [], flowParts = [];
FULL_EDGES.slice(0, 600).forEach(([srcK, dstK]) => {
  const ni=nodes[nodeIdx[srcK]], nj=nodes[nodeIdx[dstK]];
  if(!ni||!nj) return;
  const src=new THREE.Vector3(ni.x,ni.y,ni.z);
  const dst=new THREE.Vector3(nj.x,nj.y,nj.z);
  const mid=src.clone().lerp(dst,0.5).add(
    new THREE.Vector3((Math.random()-.5)*30,(Math.random()-.5)*30,(Math.random()-.5)*20)
  );
  const curve=new THREE.QuadraticBezierCurve3(src,mid,dst);
  const pts=curve.getPoints(24);
  for(let i=0;i<pts.length-1;i++){
    edgePositions.push(pts[i].x,pts[i].y,pts[i].z,pts[i+1].x,pts[i+1].y,pts[i+1].z);
  }
  flowParts.push({curve, t:Math.random(), speed:0.004+Math.random()*0.006});
});
if(edgePositions.length){
  const eg=new THREE.BufferGeometry();
  eg.setAttribute("position",new THREE.BufferAttribute(new Float32Array(edgePositions),3));
  scene.add(new THREE.LineSegments(eg,new THREE.LineBasicMaterial({
    color:0x2255aa, transparent:true, opacity:0.18,
    blending:THREE.AdditiveBlending, depthWrite:false,
  })));
}
const fPosArr=new Float32Array(flowParts.length*3);
const fGeo=new THREE.BufferGeometry();
fGeo.setAttribute("position",new THREE.BufferAttribute(fPosArr,3));
scene.add(new THREE.Points(fGeo,new THREE.PointsMaterial({
  color:0x88ccff, size:3.5, transparent:true, opacity:0.75,
  blending:THREE.AdditiveBlending, depthWrite:false, sizeAttenuation:true,
})));

// ── Gas Cloud around module clusters ─────────────────────────────────────────
Object.values(MODULES_DATA).forEach(files => {
  if(files.length < 3) return;
  const center=new THREE.Vector3();
  let count=0;
  files.forEach(k=>{const n=nodes[nodeIdx[k]]; if(n){center.add(new THREE.Vector3(n.x,n.y,n.z));count++;}});
  if(!count) return;
  center.divideScalar(count);
  const N=180, pos=new Float32Array(N*3), rad=20+files.length*1.5;
  for(let i=0;i<N;i++){
    const r=rad*(0.3+Math.random()*0.7);
    const th=Math.random()*Math.PI*2, ph=Math.acos(2*Math.random()-1);
    pos[i*3]=center.x+r*Math.sin(ph)*Math.cos(th);
    pos[i*3+1]=center.y+r*Math.sin(ph)*Math.sin(th)*0.6;
    pos[i*3+2]=center.z+r*Math.cos(ph)*0.6;
  }
  const cg=new THREE.BufferGeometry();
  cg.setAttribute("position",new THREE.BufferAttribute(pos,3));
  scene.add(new THREE.Points(cg,new THREE.PointsMaterial({
    color:0x334466, size:5, transparent:true, opacity:0.07,
    blending:THREE.AdditiveBlending, depthWrite:false, sizeAttenuation:true,
  })));
});

// ── CSS2D Labels ──────────────────────────────────────────────────────────────
nodes.forEach(n => {
  if(n.fd.priority < 70 && !n.fd.entrypoint) return;
  const div=document.createElement("div");
  div.style.cssText="font:600 9px/1 monospace;color:#9ac;background:rgba(5,10,25,.7);padding:1px 4px;border-radius:3px;pointer-events:none;white-space:nowrap;";
  div.textContent = n.k.split("/").pop() || n.k;  // safe: textContent only
  const label=new THREE.CSS2DObject(div);
  label.position.set(n.x, n.y+sizeArr[n.idx]*0.6+2, n.z);
  scene.add(label);
});

// ── Info panel (safe DOM — no innerHTML with untrusted data) ──────────────────
const infoPan = document.getElementById("info-panel");
const infoCls = document.getElementById("info-close");
infoCls.addEventListener("click", ()=>{ infoPan.style.display="none"; });

function makeRow(label, value) {
  const row=document.createElement("div"); row.className="ni-row";
  const l=document.createElement("span"); l.className="ni-label"; l.textContent=label;
  const v=document.createElement("span"); v.className="ni-val";   v.textContent=value;
  row.appendChild(l); row.appendChild(v);
  return row;
}

function showInfo(idx) {
  const n=nodes[idx]; if(!n) return;
  const fd=n.fd;
  const content=document.getElementById("info-content");
  while(content.firstChild) content.removeChild(content.firstChild);

  const fileDiv=document.createElement("div"); fileDiv.className="ni-file";
  fileDiv.textContent=fd.file||n.k;
  content.appendChild(fileDiv);

  content.appendChild(makeRow("domain",      fd.domain||"–"));
  content.appendChild(makeRow("priority",    String(fd.priority||0)));
  content.appendChild(makeRow("criticality", fd.criticality||"–"));
  content.appendChild(makeRow("fan-in",      String(fd.fan_in||0)));

  const re=fd.refactor_effort != null ? fd.refactor_effort.toFixed(2) : "–";
  content.appendChild(makeRow("refactor effort", re));

  // Effort bar
  const bar=document.createElement("div"); bar.className="ni-re-bar";
  const pct=Math.min(100,(parseFloat(re)/150)*100)||0;
  bar.style.width=pct+"%";
  content.appendChild(bar);

  content.appendChild(makeRow("blast radius", String(fd.blast_radius||0)+" files"));

  if(fd.role_hint){
    const hint=document.createElement("div"); hint.className="ni-hint";
    hint.textContent=fd.role_hint;
    content.appendChild(hint);
  }
  (fd.warnings||[]).slice(0,2).forEach(w=>{
    const d=document.createElement("div"); d.className="ni-warn";
    d.textContent="⚠ "+w;
    content.appendChild(d);
  });

  infoPan.style.display="block";
}

// ── Raycaster + click ─────────────────────────────────────────────────────────
const ray=new THREE.Raycaster(); ray.params.Points.threshold=4;
const mouse=new THREE.Vector2();
canvas.addEventListener("click", evt => {
  evt.preventDefault();
  const rect=canvas.getBoundingClientRect();
  mouse.x=((evt.clientX-rect.left)/rect.width)*2-1;
  mouse.y=-((evt.clientY-rect.top)/rect.height)*2+1;
  ray.setFromCamera(mouse,camera);
  const hits=ray.intersectObject(stars);
  if(hits.length){ showInfo(hits[0].index); flyToNode(hits[0].index); }
  else { infoPan.style.display="none"; }
});

// ── TWEEN fly-to-node ─────────────────────────────────────────────────────────
function flyToNode(idx) {
  const n=nodes[idx];
  const target=new THREE.Vector3(n.x,n.y,n.z);
  const dest=target.clone().add(new THREE.Vector3(0,0,65));
  controls.autoRotate=false;
  new TWEEN.Tween(camera.position)
    .to({x:dest.x,y:dest.y,z:dest.z},900)
    .easing(TWEEN.Easing.Cubic.InOut).start();
  new TWEEN.Tween(controls.target)
    .to({x:target.x,y:target.y,z:target.z},900)
    .easing(TWEEN.Easing.Cubic.InOut).start();
}

// ── Guided tour ───────────────────────────────────────────────────────────────
let tourActive=false, tourIdx=0, tourTimer=null;
const tourNodes=nodes.filter(n=>n.fd.entrypoint||n.fd.criticality==="critical").slice(0,10);
document.getElementById("btn-tour").addEventListener("click", function() {
  if(tourActive){ tourActive=false; clearTimeout(tourTimer); this.textContent="Tour"; controls.autoRotate=true; }
  else { tourActive=true; controls.autoRotate=false; this.textContent="Stop"; advanceTour(); }
});
function advanceTour(){
  if(!tourActive||!tourNodes.length) return;
  const n=tourNodes[tourIdx%tourNodes.length];
  flyToNode(n.idx); showInfo(n.idx); tourIdx++;
  tourTimer=setTimeout(advanceTour,3200);
}

// ── Legend toggle ─────────────────────────────────────────────────────────────
document.getElementById("btn-legend").addEventListener("click", ()=>{
  const el=document.getElementById("nebula-legend");
  el.style.display=el.style.display==="none"?"flex":"none";
});

// ── Resize ────────────────────────────────────────────────────────────────────
window.addEventListener("resize", ()=>{
  const w=window.innerWidth, h=window.innerHeight;
  camera.aspect=w/h; camera.updateProjectionMatrix();
  renderer.setSize(w,h); composer.setSize(w,h);
  labelRenderer.setSize(w,h); bloomPass.resolution.set(w,h);
});

// ── Animation loop ────────────────────────────────────────────────────────────
let clock=0;
(function animate(){
  requestAnimationFrame(animate);
  clock+=0.01;
  starMat.uniforms.uTime.value=clock;
  nebMat.uniforms.uTime.value=clock;
  TWEEN.update();
  flowParts.forEach((fp,i)=>{
    fp.t=(fp.t+fp.speed)%1;
    const pt=fp.curve.getPoint(fp.t);
    fPosArr[i*3]=pt.x; fPosArr[i*3+1]=pt.y; fPosArr[i*3+2]=pt.z;
  });
  fGeo.getAttribute("position").needsUpdate=true;
  controls.update();
  composer.render();
  labelRenderer.render(scene,camera);
})();
