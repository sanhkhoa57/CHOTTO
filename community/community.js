const canvas = document.querySelector("canvas");
const ctx = canvas.getContext("2d");
const byId = (id) => document.getElementById(id);
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");


const mesh = [];
const falling = [];
const landscape = byId("landscape");
const frontYaw = .12;
const fullTurn = 2*Math.PI;
const overview = {yaw:frontYaw, zoom:1, offsetX:0, offsetY:0};
const canopyZoom = 2.1;
const maxZoom = 18;
const view = { ...overview, pitch:.225, distance:2100, zoom:canopyZoom };
let seed = 912437;
let frame = 0;
let idle = false;
let windDue = 0;
let cursor = -1;
let selected = null;
let gesture = null;
let shown = [], visible = null;

function random() {
  seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
  return seed / 4294967296;
}

const dot = (a, b) => a[0]*b[0] + a[1]*b[1] + a[2]*b[2];
const cross = (a, b) => [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]];
const delta = (a, b) => a.map((value, index) => value-b[index]);
const unit = (v) => v.map((value) => value/Math.hypot(...v));
const lerp = (a, b, t) => a.map((value, i) => value+(b[i]-value)*t);
const light = unit([.72,.65,.30]);
const barkColors = ["#202821","#303329","#454638","#585745","#777460"];
const rootColors = ["#222a22","#303529","#444736","#535644","#79775e"];

const leafProfiles = [
  { outline:"M-.88 0C-.64-.39-.28-.54 .12-.42L.24-.44 .36-.33 .48-.34 .59-.23 .72-.22 1-.02C.64 .07 .34 .42 .04 .44C-.38 .48-.68 .29-.88 0Z", crease:"M-.88 0Q.05-.18 1-.02C.52-.23 .38-.33 .12-.42C-.28-.54-.64-.39-.88 0Z" },
  { outline:"M-.88 0C-.52-.14-.38-.36 .04-.31C.47-.37 .76-.17 1-.13C.71-.02 .52 .27 .19 .32C-.26 .4-.64 .18-.88 0Z", crease:"M-.88 0Q.02-.16 1-.13C.76-.17 .47-.37 .04-.31C-.38-.36-.52-.14-.88 0Z" },
  { outline:"M-.88 0C-.69-.33-.32-.57 .02-.49L.16-.53 .26-.44 .4-.45 .49-.34 .6-.32 .69-.22 1 .02C.82 .04 .61 .12 .48 .25L.32 .3 .26 .39 .1 .37C-.35 .5-.69 .27-.88 0Z", crease:"M-.88 0Q.01-.17 1 .02L.69-.22 .6-.32 .49-.34 .4-.45 .26-.44 .16-.53 .02-.49C-.32-.57-.69-.33-.88 0Z" }
].map(({ outline,crease }) => ({ outline:new Path2D(outline), crease:new Path2D(crease) }));
const veins = new Path2D("M-1.12 .10Q-.33-.19 .85-.045M-.57-.037Q-.47-.16-.4-.28M-.33-.078Q-.2-.21-.15-.32M-.08-.099Q.1-.24 .17-.32M.19-.105L.46-.25M-.58-.036Q-.44 .06-.39 .17M-.32-.078Q-.16 .03-.06 .22M-.04-.1Q.15-.01 .25 .17M.23-.104L.45 .09");

function smoothLimb(joints, radii, subdivisions) {
  const centers = [], widths = [];
  for (let i = 0; i < joints.length-1; i++) {
    const from = joints[i], to = joints[i+1];
    const before = joints[Math.max(0,i-1)], after = joints[Math.min(joints.length-1,i+2)];
    for (let j = 0; j < subdivisions; j++) {
      const t = j/subdivisions, t2 = t*t, t3 = t2*t;
      centers.push(from.map((a,k) => {
        const b = to[k], m = (b-before[k])*.5, n = (after[k]-a)*.5;
        return (2*t3-3*t2+1)*a+(t3-2*t2+t)*m+(-2*t3+3*t2)*b+(t3-t2)*n;
      }));
      widths.push(radii[i]+(radii[i+1]-radii[i])*t);
    }
  }
  centers.push(joints.at(-1));
  widths.push(radii.at(-1));
  return [centers,widths];
}

function barkMarks(points, i, j, shade) {
  const onBark = ([u,v]) => lerp(lerp(points[0],points[1],u),lerp(points[3],points[2],u),v);
  const token = (i*37+j*73+i*j*11)%97;
  const bow = .15*Math.sin(i*.41+j*.83);
  const ribbon = [[.28+bow,.03],[.51,.20],[.37-bow,.53],[.56+bow,.96],[.30+bow,.75],[.17,.44]];
  const marks = [{ points:ribbon.map(onBark),color:shade < 2 ? "#0c263075" : "#23353b76" }];
  if (token%5 < 2) {
    const glint = [[.67,.10],[.81,.27],[.74,.50],[.83,.69],[.56,.94],[.61,.57],[.47,.41]];
    marks.push({ points:glint.map(onBark),color:shade >= 3 ? "#a49f79a6" : "#56634c65" });
  }
  if (shade >= 3 && token > 74) {
    const dapple = [[.13,.22],[.44,.13],[.78,.29],[.68,.48],[.91,.56],[.61,.66],[.44,.89],[.30,.63],[.11,.56]];
    const w = .34+(token%9)*.064, h = .33+(token%7)*.084;
    const u = ((token*7)%13)/13*(1-w), v = ((token*11)%17)/17*(1-h);
    marks.push({ points:dapple.map(([x,y]) => onBark([u+x*w,v+y*h])),color:token > 88 ? "#b3ad89" : "#8e8b6d" });
  }
  if (token === 17 && i > 3) {
    const knot = [[.49,.09],[.78,.30],[.82,.57],[.61,.90],[.39,.85],[.19,.57],[.22,.30]];
    marks.push({ points:knot.map(onBark),color:"#112a33" });
    marks.push({ points:[[.49,.29],[.65,.44],[.58,.70],[.42,.80],[.33,.56],[.35,.42]].map(onBark),color:"#416466" });
  }
  return marks;
}

// Old wood is never a clean tube: knotted burls swell out, hollows sink in, the surface
// heaves irregularly and the foot of the trunk is fluted. Added to the radius, in world
// space, so neighbouring limbs share the same lumps.
const burls = [];
function relief(s, radius, angle) {
  const weight = Math.min(1,radius/22);
  let r = radius*weight*(
    .06*Math.sin(s[0]*.029+s[1]*.011+1.3)*Math.sin(s[2]*.033-s[1]*.019)+
    .035*Math.sin(s[1]*.071+s[0]*.05-s[2]*.04));
  // Deep flutes run up from the roots and fade with height.
  if (radius > 40) r += radius*.16*Math.cos(angle*7+s[1]*.004)*Math.exp(-Math.max(0,s[1])/260);
  for (const { centre,size,height } of burls) {
    const d = (s[0]-centre[0])**2+(s[1]-centre[1])**2+(s[2]-centre[2])**2;
    if (d < 9*size*size) r += height*Math.exp(-d/(size*size));
  }
  return r;
}

// Transport the orientation along the limb so broad curves have no sudden seams.
function limb(joints, radii, colors, sides = 8, grain = false, sculpted = false) {
  if (sculpted) [joints,radii] = smoothLimb(joints,radii,3);  let previousAxis;
  const rings = joints.map((point, i) => {
    const tangent = unit(delta(joints[Math.min(i+1,joints.length-1)], joints[Math.max(0,i-1)]));
    const axis = previousAxis
      ? unit(previousAxis.map((value,k) => value-tangent[k]*dot(previousAxis,tangent)))
      : unit(cross(tangent,Math.abs(tangent[1]) > .9 ? [1,0,0] : [0,1,0]));
    previousAxis = axis;
    const other = cross(tangent, axis);
    return Array.from({ length: sides }, (_, j) => {
      const angle = (j+.5)*Math.PI*2/sides + (grain ? .12*Math.sin(i*(sculpted ? .25 : .7)+j*.65) : 0);
      const ridges = sculpted ? .05*Math.cos(angle*5+i*.12)+.05*Math.sin(angle*3-i*.16) : .08*Math.sin(j*13+i*.31);
      const out = axis.map((a,k) => a*Math.cos(angle)+other[k]*Math.sin(angle));
      let radius = radii[i]*(1+ridges);
      if (grain) radius += relief(point.map((v,k) => v+radius*out[k]),radii[i],angle);
      return point.map((value, k) => value+radius*out[k]);
    });
  });
  const wraps = Math.max(1,Math.round(2*Math.PI*Math.max(...radii)/54));
  const limbStart = mesh.length;
  let along = 0;
  for (let i = 1; i < rings.length; i++) {
    const nextAlong = along + Math.hypot(...delta(joints[i],joints[i-1]))/146;
    const firstFace = mesh.length;
    for (let j = 0; j < sides; j++) {
      const next = (j+1)%sides;
      const points = [rings[i-1][j], rings[i-1][next], rings[i][next], rings[i][j]];
      let normal = unit(cross(delta(points[1], points[0]), delta(points[3], points[0])));
      if (dot(normal, delta(points[0], joints[i-1])) < 0) normal = normal.map((value) => -value);
      const shade = Math.max(0,Math.min(4,Math.floor(2+2.9*dot(normal,light))));
      const chase = .19+.51*(.5+.5*Math.sin(j*8.43));
      const curve = grain && radii[i-1] > 12 ? [
        lerp(points[0],points[1],chase),
        lerp(lerp(points[0],points[1],chase+.14),lerp(points[3],points[2],chase+.14),.54),
        lerp(points[3],points[2],chase)
      ] : null;
      const hatch = [];
      if (curve && shade <= 2 && (i+j)%(sculpted ? 4 : 3) === 1) {
        // Short tapered scratches follow the surface in the darker bark.
        for (let k = 0; k < 4; k++) {
          const across = .23+k*.13;
          const start = .2+.11*Math.sin(j*2+k*.65);
          hatch.push([
            lerp(lerp(points[0],points[1],across),lerp(points[3],points[2],across),start),
            lerp(lerp(points[0],points[1],across+.08),lerp(points[3],points[2],across+.08),start+.28+k*.055)
          ]);
        }
      }
      mesh.push({
        points, normal, color: colors[shade], curve, hatch,
        barkUV:[j*wraps/sides,along,(j+1)*wraps/sides,nextAlong],
        marks:sculpted && radii[i-1] > 16 ? barkMarks(points,i,j,shade) : [],
        edges: grain ? [firstFace+(j+sides-1)%sides,firstFace+next] : null
      });
    }
    along = nextAlong;
  }
  // Corner normals averaged over the touching faces, so light flows across the facets.
  const segments = rings.length-1;
  const corners = rings.map((ring,r) => ring.map((_,j) => {
    const sum = [0,0,0];
    for (const s of [r-1,r]) {
      if (s<0 || s>=segments) continue;
      for (const k of [(j+sides-1)%sides,j]) mesh[limbStart+s*sides+k].normal.forEach((v,axis) => { sum[axis]+=v; });
    }
    return unit(sum);
  }));
  for (let s = 0; s < segments; s++) for (let j = 0; j < sides; j++) {
    const next = (j+1)%sides;
    mesh[limbStart+s*sides+j].smooth = [corners[s][j],corners[s][next],corners[s+1][next],corners[s+1][j]];
  }
}

// Keep the base broad where it meets the buttresses, then give the trunk a long climb.
const trunk = [[5,33,6],[0,68,5],[-9,111,0],[-4,164,-6],[0,218,0]];
// The bole leans and wanders as it climbs instead of standing like a post.
for (let y = 296; y <= 1436; y += 95) {
  trunk.push([30*Math.sin(y*.0042+.6)+11*Math.sin(y*.013)-20,y,22*Math.cos(y*.0035)+9*Math.sin(y*.017+2)-28]);
}
const trunkRadii = [104,...trunk.map((_,i) => i < 5 ? [90,86,82,79,77][i] : Math.max(5,76*(1-((i-5)/13)**2.2)))];
// Burls (swellings) and hollows scattered up the bole, sized to the wood around them.
// Few and gentle: broad swellings, not warts.
for (let n = 0; n < 7; n++) {
  const i = 2+Math.floor(random()*(trunk.length-5)), angle = random()*fullTurn;
  const [x,y,z] = trunk[i], r = trunkRadii[i+1];
  const hollow = n%3 === 2;
  burls.push({ centre:[x+Math.cos(angle)*r,y+(random()-.5)*40,z+Math.sin(angle)*r],
    size:r*(.55+random()*.3), height:r*(hollow ? -.08 : .07+random()*.07) });
}
limb([[8,-19,8],...trunk],trunkRadii,barkColors,34,true,true);
// A raised fold winds down the left side of the bole into the arched side root.
limb([[-22,305,8],[-5,263,32],[-17,221,36],[-37,185,15],[-43,154,8],
  [-68,132,21],[-92,115,31],[-110,66,37],[-128,23,50],[-144,-7,54]],
  [3,7,10,12,15,13,9,5,3,2],barkColors,10,true,true);

// Raised buttresses divide into smaller, weight-bearing roots before reaching the rock.
const rootSystem = [
  { angle:1.40, reach:208, lift:125, knee:58, width:36 },
  { angle:2.35, reach:197, lift:160, knee:68, width:26 },
  { angle:3.05, reach:216, lift:105, knee:42, width:20 },
  { angle:3.76, reach:152, lift:133, knee:49, width:22 },
  { angle:4.46, reach:190, lift:90, knee:36, width:23 },
  { angle:5.28, reach:165, lift:102, knee:43, width:19 },
  { angle:6.05, reach:232, lift:134, knee:80, width:30 },
  { angle:.57, reach:136, lift:94, knee:28, width:20 }
];
const groundHeight = (x,z) => 1.8*Math.sin(x*.103+z*.064)+1.2*Math.sin(z*.137-x*.041);
const rootContacts = [];
rootSystem.forEach(({angle,reach,lift,knee,width}, index) => {
  // Heavier buttresses carry the thicker tower trunk.
  width *= 1.9; reach *= 1.65; lift *= 1.3;
  const rootPoint = (distance,height,bend) => [
    Math.cos(angle)*distance-Math.sin(angle)*bend,height,
    Math.sin(angle)*distance+Math.cos(angle)*bend
  ];
  // The last bend still carries weight when it disappears into the scree.
  const entry = reach*(.84+.045*Math.sin(index*2.2));
  const joints = [
    rootPoint(11,lift+9,0),rootPoint(48,lift*.64,8),rootPoint(reach*.48,knee*.72,14),
    rootPoint(reach*.7,knee*.26,-8),rootPoint(entry,0,-17),rootPoint(reach,-23,-10)
  ];
  limb(joints,[width*.42,width*.94,width*.72,width*.56,width*.37,width*.2],rootColors,10,true,true);
  rootContacts.push({point:joints[4],angle,width:width*.45});
  for (let fork = 0; fork < 3; fork++) {
    const start = joints[2+fork%2];
    const side = (index+fork)%2 ? 1 : -1;
    const splay = side*(28+fork*12);
    const foot = rootPoint(reach*(.68+fork*.11),0,splay);
    limb([start,lerp(start,foot,.38),rootPoint(reach*(.62+fork*.1),9,splay*.83),foot,
      rootPoint(reach*(.78+fork*.1),-9,splay+side*9)],
      [width*.28,width*.21,width*.17,width*.115,1.5],rootColors,7,true);
    rootContacts.push({point:foot,angle:angle+side*.4,width:width*.15});
  }
});

// Cache the clipped outline in world space. Bark, ink and hatching all stop at this edge.
function exposedBark(points) {
  if (points.every(p => p[1]>3)) return points;
  const outline = [];
  let a = points.at(-1), da = a[1]-groundHeight(a[0],a[2]);
  for (const b of points) {
    const db = b[1]-groundHeight(b[0],b[2]);
    if ((da<0)!==(db<0)) outline.push(lerp(a,b,da/(da-db)));
    if (db>=0) outline.push(b);
    a=b; da=db;
  }
  return outline.length===4 && outline.every((p,i)=>p===points[i]) ? points : outline;
}

// Fractured stone lips lie on both sides of the entry, in the same depth sort as the roots.
function groundFragments() {
  const pieces=[];
  rootContacts.forEach(({point:[cx,,cz],angle,width},index)=>{
    const cos=Math.cos(angle), sin=Math.sin(angle);
    const surface=(along,across,rise=0)=>{
      const x=cx+along*cos-across*sin, z=cz+along*sin+across*cos;
      return [x,groundHeight(x,z)+rise,z];
    };
    for (let n=0;n<(width>7 ? 5 : 2);n++) {
      const phase=index*5.7+n*2.4;
      const along=width*(.36+n*.49+.5*Math.sin(phase));
      const across=width*(n%2 ? -1 : 1)*(.55+.38*Math.cos(phase));
      const size=width*(.69+.27*Math.sin(phase+.9))/(1+n*.21);
      const outline=[[-1,-.35],[-.45,-.92],[.66,-.53],[1,.08],[.25,.73],[-.58,.49]];
      const ring=outline.map(([u,v])=>surface(along+size*u,across+size*v,-.45));
      const cap=outline.map(([u,v])=>surface(along+size*(u*.74-.08),across+size*v*.61,size*(.30+.08*u)));
      pieces.push({vertices:cap,color:n%2 ? "#a39c8c" : "#9a9486"});
      ring.forEach((a,i)=>{
        const next=(i+1)%ring.length, b=ring[next];
        let normal=unit(cross(delta(b,a),delta(cap[i],a)));
        if(normal[1]<0) normal=normal.map(value=>-value);
        const shades=["#504c42","#6f695b","#8e8676","#aba28f","#c1b7a0"];
        const shade=Math.max(0,Math.min(4,Math.round(1.4+dot(normal,light)*2.6)));
        pieces.push({vertices:[a,b,cap[next],cap[i]],color:shades[shade]});
      });
    }
    if(width>7) {
      const split=[[.5,-.13],[1.45,-.29],[2.02,.14],[2.82,-.32],[1.97,-.06],[1.47,-.52]]
        .map(([u,v])=>surface(width*u,width*v,.1));
      pieces.push({vertices:split,color:"#514a40b0"});
    }
  });
  return pieces;
}
// Every limb forks into thinner limbs, four levels deep: a bough splits into branches,
// branches into boughlets, boughlets into twigs. Thinner wood droops more under its weight.
const boughs = [];   // the heavier wood, which casts a shadow on the floor
const seats = [];    // ends of the second level, where the leaf masses sit
function grow(start, dir, length, radius, depth) {
  const across = unit(cross(dir,Math.abs(dir[1]) > .95 ? [1,0,0] : [0,1,0]));
  const up = cross(across,dir);
  const wiggle = (random()-.5)*.3*length, droop = (.04+.08*depth)*length;
  const at = (t) => start.map((v,k) => v+dir[k]*length*t+across[k]*wiggle*Math.sin(Math.PI*t)-(k===1 ? droop*t*t : 0));
  const joints = [0,.34,.67,1].map(at);
  const taper = depth === 3 ? [1,.7,.4,.08] : [1,.9,.8,.7];
  limb(joints,taper.map((f) => radius*f),barkColors,[12,10,7,5][depth],true,depth < 2);
  if (depth < 2) boughs.push(joints);
  // Leaves fill the inner crown too, not only the outer tips.
  if (depth === 1 || depth === 2) seats.push({ point:joints[3],dir,inner:depth === 1 });
  if (depth === 3) return;
  // One shoot leaves the side of the limb, the rest split from its end.
  const forks = depth === 0 ? 3 : 2+(random() < .45 ? 1 : 0);
  const turn = random()*fullTurn;
  for (let f = 0; f < forks; f++) {
    const side = f === 0 && forks > 2;
    const t = side ? .5+random()*.15 : 1;
    const spread = (side ? .75 : .38)+random()*.3;
    const phi = turn+f*fullTurn/forks;
    const child = unit(dir.map((v,k) => v*Math.cos(spread)+(across[k]*Math.cos(phi)+up[k]*Math.sin(phi))*Math.sin(spread)+(k===1 ? .22 : 0)));
    const thick = radius*(side ? .55 : .7*(f === 1 ? 1 : .82));
    // Twigs stay short so they end inside the leaf mass instead of poking out bare.
    grow(at(t),child,length*(depth === 2 ? .42 : .6+random()*.14),thick,depth+1);
  }
}
// Four tiers of limbs up the tower: the lowest reach furthest, the highest climb steepest.
for (const [from,angle,rise,length,radius] of [
  [9,.3,.35,485,40],[9,1.9,.4,450,38],[9,3.5,.35,500,40],[9,5.0,.4,465,39],
  [12,1.1,.5,390,34],[12,2.8,.45,410,34],[12,4.5,.5,380,33],
  [14,.2,.6,305,27],[14,2.2,.6,320,28],[14,4.2,.55,290,26],
  [16,1.3,.7,225,20],[16,4.0,.7,235,20]
]) grow(trunk[from],unit([Math.cos(angle),rise,Math.sin(angle)]),length,radius,0);
// A leader carries the top of the crown.
grow(trunk.at(-1),[0,1,0],215,14,1);

// One leaf mass at the end of each boughlet, lifted a little above the wood.
const crowns = seats.map(({ point,dir,inner },i) => {
  const r = (inner ? 125 : 98)+((i*37)%7)*5;
  return point.map((v,k) => v+dir[k]*r*.2+(k===1 ? r*.25 : 0)).concat(r);
});

// One leaf per phishing domain in the blacklist (community-leaves.js), numbered in list
// order. Leaves are not stored: an object is made only for a leaf that is shown as a hit
// target, selected, dropped or falling, with traits derived from its number.
const leafCount = leafSource.count;
const leafCache = new Map();
function leafHash(id, salt) {
  let h = Math.imul(id^salt,2654435761)>>>0;
  h = Math.imul(h^(h>>>15),2246822507)>>>0;
  return ((h^(h>>>13))>>>0)/4294967296;
}
function leafAt(id) {
  let leaf = leafCache.get(id);
  if (!leaf) {
    leaf = {
      id, size:3+leafHash(id,1)*7, angle:(leafHash(id,2)-.5)*2.7,
      profile:leafProfiles[id%leafProfiles.length]
    };
    painting.place(leaf);
    leafCache.set(id,leaf);
  }
  return leaf;
}

// Domains load in gzip packs of leafSource.shard names, only when a leaf is opened.
const packs = new Map();
function domainOf(id) {
  const n = Math.floor((id-1)/leafSource.shard);
  if (!packs.has(n)) {
    packs.set(n,fetch(`leaves/leaves-${String(n).padStart(3,"0")}.txt.gz`)
      .then((response) => { if (!response.ok) throw new Error(response.status); return response.arrayBuffer(); })
      .then(async (data) => {
        const bytes = new Uint8Array(data);
        // A host may already have unpacked it (Content-Encoding); only gunzip real gzip.
        if (bytes[0] !== 0x1f || bytes[1] !== 0x8b) return new TextDecoder().decode(bytes);
        return new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"))).text();
      })
      .then((text) => text.split("\n"))
      .catch((error) => { packs.delete(n); throw error; }));
  }
  return packs.get(n).then((names) => names[(id-1)%leafSource.shard]);
}

function project([x,y,z]) {
  const horizontal = x*view.cosYaw-z*view.sinYaw;
  const depth = x*view.sinYaw+z*view.cosYaw;
  const vertical = y*view.cosPitch-depth*view.sinPitch;
  const near = depth*view.cosPitch+y*view.sinPitch;
  const perspective = view.distance/Math.max(80,view.distance-near);
  const factor = view.scale*perspective;
  return { x:view.x+horizontal*factor, y:view.y-vertical*factor, depth:near, factor };
}

function tracePolygon(points, pen) {
  pen.beginPath();
  pen.moveTo(points[0].x,points[0].y);
  for (const point of points.slice(1)) pen.lineTo(point.x,point.y);
  pen.closePath();
}

function polygon(points, color, pen) {
  tracePolygon(points,pen);
  pen.fillStyle = color;
  pen.fill();
}

function drawFallingLeaf(leaf,point,t) {
  const r=point.factor*leaf.size;
  ctx.save();
  ctx.translate(point.x,point.y);
  ctx.rotate(leaf.angle+t*7);
  if (leaf.id%11===0 && painting.leafArt.naturalWidth) {
    const w=r*2.25, h=w*painting.leafArt.naturalHeight/painting.leafArt.naturalWidth;
    ctx.drawImage(painting.leafArt,-w/2,-h/2,w,h);
  } else {
    ctx.scale(r,r*(.56+.30*Math.cos(t*9)));
    ctx.fillStyle="#d9a35a"; ctx.fill(leaf.profile.outline);
    ctx.fillStyle="#ffe0a0"; ctx.fill(leaf.profile.crease);
    ctx.strokeStyle="#694f31"; ctx.lineWidth=.045; ctx.stroke(leaf.profile.outline);
    if (r>6) { ctx.lineWidth=.03; ctx.stroke(veins); }
  }
  ctx.restore();
}

function inkFace(item, eye, pen) {
  if (!item.edges) return;
  if (view.scale > .43) {
    for (const mark of item.marks) polygon(mark.points.map(project),mark.color,pen);
  }
  const [a,b,c,d] = item.points;
  pen.strokeStyle = "#0e2732";
  pen.lineWidth = Math.max(.9,Math.min(2.8,2.05*view.scale));
  pen.beginPath();
  if (dot(mesh[item.edges[0]].normal,eye) < 0) {
    pen.moveTo(a.x,a.y);
    pen.lineTo(d.x,d.y);
  }
  if (dot(mesh[item.edges[1]].normal,eye) < 0) {
    pen.moveTo(b.x,b.y);
    pen.lineTo(c.x,c.y);
  }
  pen.stroke();
  if (!item.curve) return;
  const [start,curve,end] = item.curve.map(project);
  pen.strokeStyle = "#173b43c9";
  pen.lineWidth = Math.max(.5,Math.min(1.7,.94*view.scale));
  pen.beginPath();
  pen.moveTo(start.x,start.y);
  pen.quadraticCurveTo(curve.x,curve.y,end.x,end.y);
  pen.stroke();
  if (view.scale < .55 || !item.hatch.length) return;
  pen.strokeStyle = "#0f303c9c";
  pen.lineWidth = Math.max(.45,Math.min(1,.54*view.scale));
  pen.beginPath();
  for (const [from,to] of item.hatch) {
    const p = project(from), q = project(to);
    pen.moveTo(p.x,p.y);
    pen.lineTo(q.x,q.y);
  }
  pen.stroke();
}

// Bend the upper tree around the horizon, above the roots and ground details.
let sway = 0, swayBase = 0;
function canopyOffset(y) {
  return sway*Math.max(0,swayBase-y);
}

function drawTree(split) {
  const width = treeImage.width/view.dpr;
  const height = treeImage.height/view.dpr;
  if (!sway || !split) {
    ctx.drawImage(treeImage,0,0,width,height);
    return;
  }
  // Keep both clips on the same device-pixel row and sample the full texture on each side.
  // Cropping the source into two images leaves a thin seam when the upper image is skewed.
  const upper = split/view.dpr;
  ctx.save();
  ctx.beginPath();
  ctx.rect(0,0,width,upper);
  ctx.clip();
  ctx.transform(1,0,-sway,1,swayBase*sway,0);
  ctx.drawImage(treeImage,0,0,width,height);
  ctx.restore();
  if (split < treeImage.height) {
    ctx.save();
    ctx.beginPath();
    ctx.rect(0,upper,width,height-upper);
    ctx.clip();
    ctx.drawImage(treeImage,0,0,width,height);
    ctx.restore();
  }
}

function draw(now) {
  frame = 0;
  // Wind alone is capped at 60 fps, also on 120 and 144 Hz screens.
  if (idle && now < windDue-3) { render(); idle = true; return; }
  idle = false;
  windDue = Math.max(windDue+1000/60,now);
  view.cosYaw = Math.cos(view.yaw);
  view.sinYaw = Math.sin(view.yaw);
  view.cosPitch = Math.cos(view.pitch);
  view.sinPitch = Math.sin(view.pitch);
  view.scale = view.base*view.zoom;
  // Use the same camera for the terrain and the tree.
  const left = view.width*view.offsetX, top = view.height*view.offsetY;
  view.x = view.anchorX*view.zoom+left;
  view.y = view.anchorY*view.zoom+top;
  landscape.style.transform = `matrix(${view.zoom},0,0,${view.zoom},${left},${top})`;
  ctx.setTransform(view.dpr,0,0,view.dpr,0,0);
  ctx.clearRect(0,0,view.width,view.height);
  if (!painting.ready) return;
  // Ground leaves brown with age, so the scene is also repainted every ten minutes.
  const key = [view.yaw,view.pitch,view.scale,view.x,view.y,view.distance,canvas.width,canvas.height,
    groundVersion,Math.floor(Date.now()/600000)].join("|");
  if (key !== sceneKey) {
    sceneKey = key;
    scene.width=canvas.width;
    scene.height=canvas.height;
    const pen=scene.getContext("2d");
    pen.setTransform(view.dpr,0,0,view.dpr,0,0);
    crater.draw(pen,view,painting);
    drawGroundShadow(pen);
    drawGroundLeaves(pen);
    treeImage.width=canvas.width;
    treeImage.height=canvas.height;
    const treePen=treeImage.getContext("2d");
    treePen.setTransform(view.dpr,0,0,view.dpr,0,0);
    shown=painting.draw(treePen,view);
    visible=null;
    painting.prepareAccents(painting.targets(shown,view,true));
  }
  const animateWind = !reducedMotion.matches;
  const seconds = windClock(now,animateWind);
  const horizon = view.y-view.distance*view.scale*Math.tan(view.pitch);
  const split = Math.round(horizon*view.dpr);
  swayBase = split/view.dpr;
  sway = animateWind ? .010*Math.sin(seconds*.85)+.003*Math.sin(seconds*1.7) : 0;
  crater.drawSky(ctx,view,seconds);
  ctx.drawImage(scene,0,0,view.width,view.height);
  drawTree(Math.min(treeImage.height,Math.max(0,split)));
  painting.drawAccents(ctx,seconds,animateWind);
  if (selected?.ground) {
    const hit = groundHits.find((h) => h.leaf === selected);
    if (hit) {
      ctx.lineWidth = 2;
      ctx.strokeStyle = "#fff3cd";
      ctx.beginPath();
      ctx.ellipse(hit.x,hit.y,hit.r+5,(hit.r+5)*.6,0,0,Math.PI*2);
      ctx.stroke();
    }
  } else if (selected) {
    const accent = painting.accentPoints.get(selected.id);
    const point = accent || painting.leafPoint(selected,view);
    const x = accent ? point.x : point.x+canopyOffset(point.y);
    ctx.lineWidth = 2;
    ctx.strokeStyle = "#fff3cd";
    ctx.beginPath();
    ctx.arc(x,point.y,Math.max(9, selected.size*point.factor+3),0,Math.PI*2);
    ctx.stroke();
  }
  for (let i = falling.length-1; i >= 0; i--) {
    const { leaf, start, entry } = falling[i];
    if (now < start) continue;
    const t = (now-start)/1450;
    if (t >= 1) {
      falling.splice(i,1);
      // A fallen domain only shows on the ground once its fall has played.
      entry.landing = false;
      groundVersion++;
      continue;
    }
    const point = painting.leafPoint(leaf,view,t);
    point.x += canopyOffset(point.y)*(1-t);
    ctx.globalAlpha = Math.min(1,(1-t)*5);
    if (t > .24 && leaf.id%3 === 0) {
      const streak = Math.min(15,leaf.size*point.factor)*t;
      ctx.strokeStyle = "#253b42a1";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(point.x-streak,point.y-streak*.8);
      ctx.quadraticCurveTo(point.x-streak*1.1,point.y-streak*1.4,point.x-streak*.8,point.y-streak*2.4);
      ctx.stroke();
    }
    drawFallingLeaf(leaf,point,t);
  }
  ctx.globalAlpha = 1;
  if (falling.length) render();
  else if (animateWind && !document.hidden) { render(); idle = true; }
}

let windTime = 0, windLast = null;
function windClock(now,animateWind) {
  if (animateWind && windLast !== null) windTime += Math.max(0,Math.min(.1,(now-windLast)/1000));
  windLast = animateWind ? now : null;
  return windTime;
}

// Leaf hit targets for the current view, built only when a tap or "Chọn lá" needs them.
function hitTargets() {
  if (!visible) visible = painting.targets(shown,view);
  return visible;
}

function render() {
  idle = false;
  if (!frame) frame = requestAnimationFrame(draw);
}

const crater = new PaintedCrater(byId("crater-art"),byId("panorama-art"));
const painting = new PaintedTree(byId("wood-art"),byId("foliage-art"),crowns,leafCount,mesh,[...groundFragments(),...crater.ledges()]);
for (const asset of [crater.image,crater.panorama]) asset.addEventListener("load",()=>{ sceneKey=""; render(); });
const scene=document.createElement("canvas");
const treeImage=document.createElement("canvas");
let sceneKey="";
reducedMotion.addEventListener("change",render);
document.addEventListener("visibilitychange",()=>{
  windLast = null;
  if (!document.hidden) render();
});
for (const asset of [painting.wood,painting.foliage,painting.leafArt]) {
  asset.addEventListener("load",()=>{ sceneKey=""; render(); });
  if (asset!==painting.leafArt) {
    const failed=()=>{ byId("status").textContent="Chưa tải được hình cây. Hãy tải lại trang."; };
    asset.addEventListener("error",failed);
    if (asset.complete && !asset.naturalWidth) failed();
  }
}

function drawGroundShadow(pen) {
  function wash(x,z,width,height,opacity) {
    const p=project([x,1,z]);
    pen.save();
    pen.translate(p.x,p.y);
    pen.scale(width*p.factor,height*p.factor);
    const shade=pen.createRadialGradient(0,0,0,0,0,1);
    shade.addColorStop(0,"rgba(24,35,34,"+opacity+")");
    shade.addColorStop(1,"rgba(24,35,34,0)");
    pen.fillStyle=shade; pen.fillRect(-1,-1,2,2);
    pen.restore();
  }
  wash(0,0,102,14,.43);
  for (const {point:[x,,z],width,angle} of rootContacts) {
    const p=project([x,groundHeight(x,z),z]);
    const axis=project([x+width*3*Math.cos(angle),groundHeight(x,z),z+width*3*Math.sin(angle)]);
    pen.save();
    pen.translate(p.x,p.y);
    pen.rotate(Math.atan2(axis.y-p.y,axis.x-p.x));
    pen.scale(Math.max(width*p.factor,Math.hypot(axis.x-p.x,axis.y-p.y)),Math.max(1,width*p.factor*.45));
    const contact=pen.createRadialGradient(0,0,0,0,0,1);
    contact.addColorStop(0,"#312d24c9");
    contact.addColorStop(.45,"#3e392d7d");
    contact.addColorStop(1,"#3e392d00");
    pen.fillStyle=contact;
    pen.fillRect(-1,-1,2,2);
    pen.restore();
  }
}
function lookSideways(yaw) {
  view.yaw = ((yaw%fullTurn)+fullTurn)%fullTurn;
  render();
}
function resize() {
  const dpr = Math.min(2,devicePixelRatio || 1);
  if (view.width === canvas.clientWidth && view.height === canvas.clientHeight && view.dpr === dpr) return;
  const opening = view.width === undefined;
  view.width = canvas.clientWidth;
  view.height = canvas.clientHeight;
  view.dpr = dpr;
  const compact = view.width <= 650;
  const anchorX = compact ? .51 : .50;
  const anchorY = compact ? .62 : .86;
  // Fit the full crown at zoom 1, including on narrow screens.
  view.base = Math.min(view.width/3550,view.height/(compact ? 4300 : 3200));
  view.anchorX = view.width*anchorX;
  // On phones the info card covers the lower third, so the roots stand above it.
  view.anchorY = view.height*anchorY;
  if (opening) {
    view.offsetX = anchorX*(1-canopyZoom);
    view.offsetY = (anchorY-.10)*(1-canopyZoom);
  }
  canvas.width = Math.round(view.width*view.dpr);
  canvas.height = Math.round(view.height*view.dpr);
  if (frame) cancelAnimationFrame(frame);
  draw(performance.now());
}

function fit() {
  Object.assign(view,overview);
  updateZoomControls();
  render();
}

function fromRoots() {
  view.zoom = 1;
  view.offsetX = view.offsetY = 0;
  zoom(1.4/view.base,view.anchorX,view.anchorY);
}

function updateZoomControls() {
  byId("out").disabled = view.zoom<=1;
  byId("in").disabled = view.zoom>=maxZoom;
}

function zoom(factor, x = view.width/2, y = view.height*.63) {
  const previous = view.zoom;
  view.zoom = Math.max(1,Math.min(maxZoom,previous*factor));
  const ratio = view.zoom/previous;
  // Store the crop in viewport fractions so resizing preserves the framing.
  const crop = (offset,focus) => Math.max(1-view.zoom,Math.min(0,offset*ratio+focus*(1-ratio)));
  view.offsetX = crop(view.offsetX,x/view.width);
  view.offsetY = crop(view.offsetY,y/view.height);
  updateZoomControls();
  render();
}

function refresh() {
  byId("live").textContent = leafCount.toLocaleString("vi-VN");
  byId("fresh").textContent = leafSource.fresh.toLocaleString("vi-VN");
  byId("dead").textContent = groundLeaves.length.toLocaleString("vi-VN");
  byId("domain").hidden = !selected;
  if (!selected) {
    byId("record").textContent = "Danh sách chặn · " + leafSource.source;
    byId("status").textContent = "Khám phá tán cây";
    render();
    return;
  }
  const leaf = selected;
  if (leaf.ground) {
    const when = new Date(leaf.t*1000).toLocaleString("vi-VN",{ hour:"2-digit",minute:"2-digit",day:"2-digit",month:"2-digit" });
    byId("record").textContent = "Lá đã rụng · " + leafSource.source;
    byId("status").textContent = "Đã ngừng hoạt động · rụng lúc " + when;
  } else {
    const fresh = leaf.id > leafCount-leafSource.fresh;
    byId("record").textContent = "Lá #" + leaf.id.toLocaleString("vi-VN") + " · " + leafSource.source;
    byId("status").textContent = fresh ? "Còn hoạt động · mới thêm" : "Còn hoạt động";
  }
  // Defanged so it can never be clicked or auto-linked: example[.]com
  const show = (name) => { if (selected === leaf) byId("domain").textContent = name ? name.replace(/\./g,"[.]") : "Không có tên miền"; };
  if (leaf.domain) show(leaf.domain);
  else {
    byId("domain").textContent = "Đang tải tên miền…";
    domainOf(leaf.id).then(show,() => {
      if (selected === leaf) byId("domain").textContent = "Chưa tải được tên miền. Thử lại sau.";
    });
  }
  render();
}

// Leaves on the ground: domains that left the active list in the last seven days
// (community/leaves/fallen.json, rebuilt daily). Each leaf lies at a spot under the crown
// fixed by its name, browns with age, and is removed here when its time expires.
const groundLife = 7*86400;
const groundFadeTime = 12*3600;
let groundLeaves = [], groundHits = [], groundVersion = 0;
function addGroundLeaf(entry) {
  const key = entry.domain;
  let h = 2166136261;
  for (let i = 0; i < key.length; i++) h = Math.imul(h^key.charCodeAt(i),16777619);
  const angle = leafHash(h>>>0,7)*fullTurn, reach = 120+Math.sqrt(leafHash(h>>>0,8))*560;
  Object.assign(entry,{ ground:true, x:Math.cos(angle)*reach, z:Math.sin(angle)*reach,
    size:4+leafHash(h>>>0,9)*4, turn:leafHash(h>>>0,10)*Math.PI, profile:leafProfiles[(h>>>0)%leafProfiles.length] });
  groundLeaves.push(entry);
  groundVersion++;
}
function pruneGround() {
  const cutoff = Date.now()/1000-groundLife, before = groundLeaves.length;
  groundLeaves = groundLeaves.filter((leaf) => leaf.t > cutoff);
  if (groundLeaves.length === before) return;
  groundVersion++;
  if (selected?.ground && !groundLeaves.includes(selected)) selected = null;
  refresh();
}
// Domains that fell since this browser last looked play their fall from the crown (newest
// 35, a stand-in leaf picked by name since the real one has left the list). The list is
// re-read every 10 minutes, so a leaf that falls while the page is open falls live.
const seenKey = "chotto-community-fallen-seen";
const knownFallen = new Set();
function loadFallen() {
  fetch("leaves/fallen.json?"+Math.floor(Date.now()/600000), { cache:"no-cache" })
    .then((response) => response.ok ? response.json() : { leaves:[] })
    .then(({ leaves }) => {
      let seen = 0;
      try { seen = Number(localStorage.getItem(seenKey)) || 0; } catch {}
      const fresh = [];
      for (const [domain,t] of leaves) {
        if (knownFallen.has(domain)) continue;
        knownFallen.add(domain);
        const entry = { domain,t };
        addGroundLeaf(entry);
        if (t > seen) fresh.push(entry);
      }
      if (!reducedMotion.matches && leafCount) {
        const start = performance.now()+400;
        fresh.sort((a,b) => b.t-a.t).slice(0,35).forEach((entry,i) => {
          let h = 2166136261;
          for (let k = 0; k < entry.domain.length; k++) h = Math.imul(h^entry.domain.charCodeAt(k),16777619);
          const id = (h>>>0)%leafCount+1;
          entry.landing = true;
          falling.push({ leaf:leafAt(id),start:start+i*140,entry });
        });
      }
      const newest = Math.max(seen,...leaves.map(([,t]) => t));
      try { localStorage.setItem(seenKey,String(newest)); } catch {}
      pruneGround();
      groundVersion++;
      refresh();
    })
    .catch(() => {});
}
loadFallen();
setInterval(() => { pruneGround(); loadFallen(); },10*60*1000);

// Flat on the floor, fresh yellow turning brown, fading over the last half day.
function drawGroundLeaves(pen) {
  groundHits = [];
  const now = Date.now()/1000;
  const lying = groundLeaves.slice().sort((a,b) => a.t-b.t).slice(-2500);
  for (const leaf of lying) {
    if (leaf.landing) continue;
    const p = project([leaf.x,groundHeight(leaf.x,leaf.z)+.6,leaf.z]);
    if (p.x < -20 || p.y < -20 || p.x > view.width+20 || p.y > view.height+20) continue;
    const elapsed = Math.max(0,now-leaf.t);
    const age = Math.min(1,elapsed/groundLife), r = leaf.size*p.factor*1.5;
    const fade = Math.min(1,Math.max(0,(elapsed-(groundLife-groundFadeTime))/groundFadeTime));
    const tone = [201+(138-201)*age,176+(90-176)*age,74+(50-74)*age].map(Math.round);
    pen.save();
    pen.globalAlpha = 1-.7*fade;
    pen.translate(p.x,p.y);
    pen.scale(1,.42);
    pen.rotate(leaf.turn);
    pen.scale(r,r);
    pen.fillStyle = `rgb(${tone})`;
    pen.fill(leaf.profile.outline);
    pen.fillStyle = "rgba(255,240,200,.35)";
    pen.fill(leaf.profile.crease);
    pen.strokeStyle = "#4a3624";
    pen.lineWidth = .07;
    pen.stroke(leaf.profile.outline);
    pen.restore();
    groundHits.push({ leaf,x:p.x,y:p.y,r:Math.max(5,r) });
  }
}

canvas.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.repeat || !leafCount) return;
  event.preventDefault();
  const onscreen = hitTargets().filter(({ point }) => {
    const x = point.x+canopyOffset(point.y);
    return x >= 12 && point.y >= 12 && x <= view.width-12 && point.y <= view.height-12;
  });
  if (onscreen.length) {
    cursor = (cursor+149)%onscreen.length;
    selected = onscreen[cursor].leaf;
  } else {
    fit();
    selected = leafAt(1);
  }
  refresh();
});
byId("in").onclick = () => zoom(1.25);
byId("out").onclick = () => zoom(.8);
byId("fit").onclick = fit;
byId("roots").onclick = fromRoots;
byId("left").onclick = () => lookSideways(view.yaw-fullTurn/12);
byId("right").onclick = () => lookSideways(view.yaw+fullTurn/12);

canvas.addEventListener("wheel", (event) => {
  if (event.ctrlKey || event.metaKey) return;
  event.preventDefault();
  zoom(event.deltaY < 0 ? 1.12 : 1/1.12,event.offsetX,event.offsetY);
}, { passive:false });
canvas.addEventListener("pointerdown", (event) => {
  if (gesture || event.button !== 0) return;
  canvas.setPointerCapture(event.pointerId);
  gesture = {
    id:event.pointerId, x:event.clientX, y:event.clientY, yaw:view.yaw, dragged:false
  };
});
canvas.addEventListener("pointermove", (event) => {
  if (gesture?.id !== event.pointerId) return;
  const dx = event.clientX-gesture.x, dy = event.clientY-gesture.y;
  if (Math.hypot(dx,dy) > 5) gesture.dragged = true;
  if (!gesture.dragged) return;
  lookSideways(gesture.yaw+dx*fullTurn/view.width);
});
canvas.addEventListener("lostpointercapture", () => { gesture = null; });
canvas.addEventListener("pointerup", (event) => {
  if (gesture?.id !== event.pointerId) return;
  const dragged = gesture.dragged;
  gesture = null;
  if (dragged) return;
  const bounds = canvas.getBoundingClientRect();
  const x = event.clientX-bounds.left, y = event.clientY-bounds.top;
  const close=(leaf,point,offset=0) => Math.hypot(x-point.x-offset,y-point.y)<Math.max(6,leaf.size*point.factor*.85);
  const picked = painting.accents.findLast(({leaf}) => {
    const point=painting.accentPoints.get(leaf.id);
    return point && close(leaf,point);
  }) || hitTargets().findLast(({leaf,point}) => close(leaf,point,canopyOffset(point.y)))
    || groundHits.findLast((hit) => Math.hypot(x-hit.x,y-hit.y) < hit.r+4);
  if (picked) {
    selected = picked.leaf;
    refresh();
  }
});
new ResizeObserver(resize).observe(canvas);
resize();
updateZoomControls();
refresh();
