// The crater painting supplies both the distant rim and a ground texture around the tree.
// All lengths on the ground are in the same world units as the roots.
class PaintedCrater {
  constructor(image,panorama) {
    this.image=image;
    // Seamless strip cut from the same painting by community/tools/make_community_panorama.py.
    this.panorama=panorama;
    // Two ground planes: the cracked sand around the roots (it melts into the painting) and,
    // over it, the cast shadow, which reaches much farther and moves with the sun.
    this.sandRadius=900;
    this.radius=2450;
    this.shadow=document.createElement("canvas");
    this.shadow.width=this.shadow.height=1536;
    this.shadowStep=null;
  }

  // The scene follows the viewer's own clock (hour 0..24). The sun is up from 05:45 to
  // 18:15 and the moon takes the night shift. Both rise in the south-east, cross high over
  // the south and set in the south-west (a winter path, so they stay within sight).
  // Compass bearings grow clockwise; the opening view faces south.
  skyState(hour) {
    const rise=5.75, set=18.25, sweep=.6*Math.PI;
    const day=hour>=rise && hour<set;
    const progress=day ? (hour-rise)/(set-rise) : ((hour-set+24)%24)/(24-set+rise);
    const height=Math.sin(Math.PI*progress);
    const azimuth=Math.PI+sweep*(progress-.5);
    // The same direction as a bearing of the sky and the ground, see drawSky.
    const bearing=azimuth-Math.PI-frontYaw;
    // Shadows are stylised: long even at noon, and never longer than the shadow plane.
    const stretch=1.12-.24*height;
    return {
      ...this.daylight(hour), day, azimuth, bearing, height,
      // The lantern warms up over half an hour at dusk and goes out after daybreak.
      lamp:Math.max(0,Math.min(1,(hour-17.6)/.5),Math.min(1,(6.4-hour)/.5)),
      elevation:.1+.68*height,
      // Moonlight casts only a faint shadow.
      strength:Math.min(1,height/.3)*(day ? 1 : .45),
      light:[Math.sin(bearing)*stretch,1,-Math.cos(bearing)*stretch]
    };
  }

  // Sky colours (top to horizon), the wash laid over the land and tree, and how much of
  // the night shows, blended between a few hours of the day.
  daylight(hour) {
    if (!this.daylightKeys) {
      const night={ sky:["#040916","#0a1533","#152750","#2b4066"], wash:[16,30,70,.62], night:1 };
      const dawn={ sky:["#1a2a5e","#4c5f9e","#d18b8e","#ffc08a"], wash:[84,56,92,.32], night:.2 };
      const morning={ sky:["#1e5aa8","#4a93d8","#a6cfe6","#f4e3cc"], wash:[255,184,120,.08], night:0 };
      const noon={ sky:["#123f86","#2a73c6","#6aaee0","#bfe0ef"], wash:[255,184,120,0], night:0 };
      const golden={ sky:["#1d4584","#5686c0","#e3b08a","#ffd190"], wash:[206,116,46,.17], night:0 };
      const sunset={ sky:["#1b2a5e","#575192","#d9747a","#ffa564"], wash:[96,48,80,.34], night:.2 };
      this.daylightKeys=[[0,night],[4.75,night],[5.75,dawn],[7.25,morning],[9,noon],[15.5,noon],
        [17.25,golden],[18.25,sunset],[19.5,night],[24,night]];
    }
    const keys=this.daylightKeys;
    const next=Math.max(1,keys.findIndex(([at])=>at>=hour));
    const [from,a]=keys[next-1], [to,b]=keys[next];
    const t=(hour-from)/(to-from);
    const mix=(x,y)=>x+(y-x)*t;
    const channel=(hex,i)=>parseInt(hex.slice(1+2*i,3+2*i),16);
    const wash=a.wash.map((value,i)=>mix(value,b.wash[i]));
    return {
      sky:a.sky.map((hex,n)=>"rgb("+[0,1,2].map(i=>Math.round(mix(channel(hex,i),channel(b.sky[n],i)))).join(",")+")"),
      wash:wash[3]<.005 ? "" : "rgba("+wash.slice(0,3).map(Math.round).join(",")+","+wash[3].toFixed(3)+")",
      night:mix(a.night,b.night)
    };
  }

  ledges() {
    this.rockArt=document.createElement("canvas");
    this.rockArt.width=246;
    this.rockArt.height=71;
    return [
      [-310,260,105,.80],[-391,244,38,.15],[335,320,136,-.48],[278,350,49,-.61],
      [396,-210,62,-.97],[-295,-354,84,.26],[-341,-330,35,.54],[-492,36,78,-1.42]
    ].map(([x,z,width,angle])=>({vertices:[[x,0,z]],sprite:this.rockArt,width,angle}));
  }

  prepare(view) {
    const image=this.image, w=image.naturalWidth, h=image.naturalHeight;
    const rock=this.rockArt.getContext("2d");
    const outline=new Path2D("M7 52L14 29 64 16 117 6 167 1 195 5 234 14 238 35 226 40 191 50 155 56 145 62 112 63 94 67 77 63 64 65 51 60 32 60 24 55 16 57Z");
    rock.clip(outline);
    rock.drawImage(image,12,752,246,71,0,0,246,71);
    this.period=this.panorama.naturalWidth;
    this.rim=document.createElement("canvas");
    this.rim.width=2*this.period;
    this.rim.height=h;
    const rim=this.rim.getContext("2d");
    rim.drawImage(this.panorama,0,0);
    const air=rim.createLinearGradient(0,h*.30,0,h*.78);
    air.addColorStop(0,"#b6ccce00");
    air.addColorStop(.69,"#b6ccce48");
    air.addColorStop(1,"#b6ccce00");
    rim.fillStyle=air;
    // The strip's sky is transparent: haze only the rock, the sky is drawn behind it.
    rim.globalCompositeOperation="source-atop";
    rim.fillRect(0,0,this.period,h);
    rim.globalCompositeOperation="source-over";
    rim.drawImage(this.rim,0,0,this.period,h,this.period,0,this.period,h);

    this.sand=this.paintSand();
  }

  // Cracked ground seen from above, in the painting's colours. Drawn rather than unwarped
  // from the painting, which left cut corners, smears and mirrored folds when orbiting.
  paintSand() {
    const canvas=document.createElement("canvas");
    const size=canvas.width=canvas.height=1024;
    const brush=canvas.getContext("2d");
    let state=71933;
    const noise=()=>(state=(Math.imul(state,1664525)+1013904223)>>>0)/4294967296;
    brush.fillStyle="#c9c4b9";
    brush.fillRect(0,0,size,size);

    // Voronoi slabs on a jittered grid: each cell is clipped by its neighbours.
    const spacing=92, count=Math.ceil(size/spacing)+2;
    const seeds=Array.from({length:count*count},(_,i)=>[
      (i%count-.5+(noise()-.5)*.95)*spacing,(Math.floor(i/count)-.5+(noise()-.5)*.95)*spacing
    ]);
    const cells=seeds.map(([x,y],i)=>{
      let cell=[[x-200,y-200],[x+200,y-200],[x+200,y+200],[x-200,y+200]];
      for (let dy=-2;dy<=2;dy++) for (let dx=-2;dx<=2;dx++) {
        const col=i%count+dx, row=Math.floor(i/count)+dy;
        if ((!dx && !dy) || col<0 || row<0 || col>=count || row>=count) continue;
        const [ox,oy]=seeds[row*count+col];
        const side=([px,py])=>(px-(x+ox)/2)*(ox-x)+(py-(y+oy)/2)*(oy-y);
        const clipped=[];
        cell.forEach((from,k)=>{
          const to=cell[(k+1)%cell.length], f=side(from), g=side(to);
          if (f<=0) clipped.push(from);
          if ((f<=0)!==(g<=0)) clipped.push(lerp(from,to,f/(f-g)));
        });
        cell=clipped;
      }
      return cell;
    });
    const tones=["#d2cdc2","#cbc5b8","#c4c0b6","#d6d0c3","#c8c1b2"];
    for (const cell of cells) {
      brush.beginPath();
      for (const [x,y] of cell) brush.lineTo(x,y);
      brush.closePath();
      brush.globalAlpha=.55;
      brush.fillStyle=tones[Math.floor(noise()*tones.length)];
      brush.fill();
    }

    // Soft washes of warm and cool paint.
    for (let i=0;i<170;i++) {
      const x=noise()*size, y=noise()*size, r=24+noise()*90;
      const wash=brush.createRadialGradient(x,y,0,x,y,r);
      const tone=["219,214,201","170,165,154","190,176,152","178,180,176"][i%4];
      wash.addColorStop(0,"rgba("+tone+",.34)");
      wash.addColorStop(1,"rgba("+tone+",0)");
      brush.globalAlpha=1;
      brush.fillStyle=wash;
      brush.fillRect(x-r,y-r,2*r,2*r);
    }

    // Hand-drawn cracks: only some slab edges, wobbling and varying in weight.
    brush.lineCap="round";
    for (const cell of cells) {
      cell.forEach((from,k)=>{
        const to=cell[(k+1)%cell.length];
        // The same edge belongs to two cells, so decide from its midpoint.
        const token=Math.abs(Math.sin((from[0]+to[0])*12.9898+(from[1]+to[1])*78.233))*43758.5453%1;
        if (token<.42 || from[0]+from[1]>to[0]+to[1]) return;
        const dx=to[0]-from[0], dy=to[1]-from[1], length=Math.hypot(dx,dy)||1;
        const points=[0,.25,.5,.75,1].map((s,n)=>{
          const bend=n%4 ? (noise()-.5)*9 : 0;
          return [from[0]+dx*s-dy/length*bend,from[1]+dy*s+dx/length*bend];
        });
        for (const [colour,weight,shift] of [["#e8e3d6",1.4,2.2],["#8d877a",1+token*2.2,0]]) {
          brush.globalAlpha=.35+.55*token;
          brush.strokeStyle=colour;
          brush.lineWidth=weight;
          brush.beginPath();
          for (const [x,y] of points) brush.lineTo(x+shift,y+shift);
          brush.stroke();
        }
      });
    }

    // Grit and a few flat pebbles.
    for (let i=0;i<4200;i++) {
      const x=noise()*size, y=noise()*size, r=.4+noise()**6*2.6;
      brush.globalAlpha=.25+noise()*.4;
      brush.fillStyle=i%3 ? "#8f897b" : "#e6e1d4";
      brush.beginPath();
      brush.ellipse(x,y,r*1.3,r,noise()*Math.PI,0,2*Math.PI);
      brush.fill();
    }
    // A long, uneven fade: no ring shows where the drawn ground hands over to the painting.
    const half=size/2;
    const fade=brush.createRadialGradient(half,half,0,half,half,half);
    for (const [at,alpha] of [[0,1],[.22,.96],[.42,.72],[.6,.42],[.78,.17],[.9,.05],[1,0]]) {
      fade.addColorStop(at,"rgba(0,0,0,"+alpha+")");
    }
    brush.globalAlpha=1;
    brush.globalCompositeOperation="destination-in";
    brush.fillStyle=fade;
    brush.fillRect(0,0,size,size);
    brush.globalCompositeOperation="source-over";
    return canvas;
  }

  bakeShadow(tree,light) {
    const size=this.shadow.width, pixels=size/(2*this.radius);
    const shade=this.shadow.getContext("2d");
    shade.setTransform(1,0,0,1,0,0);
    shade.globalCompositeOperation="source-over";
    shade.clearRect(0,0,size,size);
    shade.save();
    shade.translate(size/2,size/2);
    shade.scale(pixels,pixels);
    // Stylised cast: the crown is spread wider than life and the reach is tuned so the long
    // shadow still lands on the painted floor instead of fading out past its edge.
    const spread=1.35, reach=.62;
    const cast=([x,y,z])=>[x*spread-y*reach*light[0]/light[1],z*spread-y*reach*light[2]/light[1]];
    for(const stone of tree.ground) {
      if(!stone.sprite) continue;
      const [x,,z]=stone.vertices[0];
      shade.beginPath();
      shade.ellipse(x-stone.width*.06,z,stone.width*.5,stone.width*.16,stone.angle,0,Math.PI*2);
      shade.fill();
    }
    shade.lineCap="round";
    for(const limb of [trunk,...boughs]) {
      for(let i=1;i<limb.length;i++) {
        shade.lineWidth=spread*(limb===trunk ? 73 : 28)*(1-.55*i/limb.length);
        shade.beginPath();
        shade.moveTo(...cast(limb[i-1]));
        shade.lineTo(...cast(limb[i]));
        shade.stroke();
      }
    }
    for(const layer of tree.layers) {
      if(!layer.count) continue;
      const [x,z]=cast([layer.x,layer.y,layer.z]);
      shade.save();
      shade.translate(x,z);
      shade.rotate(layer.rotation);
      shade.scale(layer.flip,1);
      shade.drawImage(tree.foliage,-layer.width*spread/2,-layer.height*spread/2,layer.width*spread,layer.height*spread);
      shade.restore();
    }
    shade.restore();
    shade.globalCompositeOperation="source-in";
    shade.fillStyle="#27363a";
    shade.fillRect(0,0,size,size);
    // Only a safety fade at the very edge of the layer, beyond the reach of the shadow.
    const fade=shade.createRadialGradient(size/2,size/2,size*.46,size/2,size/2,size*.5);
    fade.addColorStop(0,"#000");
    fade.addColorStop(1,"transparent");
    shade.globalCompositeOperation="destination-in";
    shade.fillStyle=fade;
    shade.fillRect(0,0,size,size);
    shade.globalCompositeOperation="source-over";
    this.shadowPattern=shade.createPattern(this.shadow,"no-repeat");
  }

  // The moving shadow, projected on its own transparent layer. The crown is only cast
  // again when the clock moves on (once a minute).
  drawShadow(pen,view,tree,sun,step) {
    if(!this.rim) return;
    if(!sun.strength) return;
    if(step!==this.shadowStep) {
      this.shadowStep=step;
      this.bakeShadow(tree,sun.light);
    }
    pen.save();
    pen.globalAlpha=.42*sun.strength;
    this.drawPlane(pen,view,this.shadowPattern,this.shadow.width,this.radius);
    pen.restore();
  }

  // A picture lying flat on the ground, centred on the trunk. One row of a horizontal
  // plane has constant depth and an affine texture mapping.
  drawPlane(pen,view,pattern,size,radius) {
    const focal=view.distance*view.scale, units=2*radius/size;
    pen.fillStyle=pattern;
    const step=Math.max(1,Math.round(view.dpr*2));
    // The far edge of a wide plane may sit behind the camera's horizon; clamp it there.
    const far=project([-radius*view.sinYaw,0,-radius*view.cosYaw]).y;
    const horizon=view.y-focal*Math.tan(view.pitch);
    const start=Math.max(0,Math.floor(Math.max(far,horizon+1)*view.dpr));
    for(let py=start;py<view.height*view.dpr;py+=step) {
      const y=(py+step*.5)/view.dpr;
      const slope=(y-view.y)/focal;
      const depth=view.distance*slope/(view.sinPitch+slope*view.cosPitch);
      if(depth>radius) break;
      if(depth< -radius) continue;
      const perspective=view.distance/(view.distance-depth*view.cosPitch);
      const across=units*view.scale*perspective;
      const along=across*perspective*view.sinPitch;
      const a=across*view.cosYaw,c=-across*view.sinYaw;
      const b=along*view.sinYaw,d=along*view.cosYaw;
      pattern.setTransform({a,b,c,d,e:view.x-(a+c)*size/2,f:y-along*depth/units-(b+d)*size/2});
      pen.fillRect(0,py/view.dpr,view.width,step/view.dpr);
    }
  }

  // Painted sky behind the crater rim: deepening blue, the travelling sun and drifting
  // cumulus. Drawn every frame on its own layer, under the cached scene (whose sky is clear).
  // Sky features sit at fixed bearings and turn with the camera at full speed.
  drawSky(pen,view,seconds,state) {
    const focal=view.distance*view.scale;
    const horizon=view.y-focal*Math.tan(view.pitch);
    const at=(bearing,elevation)=>{
      const ray=Math.atan2(Math.sin(bearing+view.yaw),Math.cos(bearing+view.yaw));
      if (Math.abs(ray)>1.35) return null;
      return {x:view.x+focal*Math.tan(ray),y:horizon-focal*Math.tan(elevation)/Math.cos(ray),scale:focal/Math.cos(ray)};
    };
    const elevationY=(e)=>horizon-focal*Math.tan(e);
    const air=pen.createLinearGradient(0,elevationY(1.1),0,horizon);
    [0,.45,.8,1].forEach((stop,i)=>air.addColorStop(stop,state.sky[i]));
    pen.fillStyle=air;
    pen.fillRect(0,0,view.width,horizon+2);

    if (state.night>.25) this.drawStars(pen,at,seconds,(state.night-.25)/.75);
    // Sun and moon rise and set behind the crater wall, which is painted over this layer.
    const body=at(state.bearing,state.elevation);
    if (body && state.day) this.drawSun(pen,body);
    else if (body) this.drawMoon(pen,body);

    // Soft cumulus, painted once into sprites. Each drifts with the wind at its own pace.
    if (!this.clouds) this.clouds=this.paintClouds();
    for (const cloud of this.clouds) {
      const c=at(cloud.bearing+seconds*cloud.speed,cloud.elevation);
      if (!c) continue;
      const w=c.scale*cloud.size, h=w*cloud.sprite.height/cloud.sprite.width*cloud.squash;
      // At night only a faint trace of each cloud is left against the dark.
      pen.globalAlpha=Math.min(1,.45+cloud.elevation*1.6)*(1-.84*state.night);
      pen.drawImage(cloud.sprite,c.x-w/2,c.y-h*.72,w,h);
    }
    pen.globalAlpha=1;
  }

  drawStars(pen,at,seconds,strength) {
    if (!this.stars) {
      let state=52711;
      const noise=()=>(state=(Math.imul(state,1664525)+1013904223)>>>0)/4294967296;
      this.stars=Array.from({length:520},()=>({
        bearing:noise()*fullTurn, elevation:.08+noise()*1.0, size:.5+noise()**4*1.7, phase:noise()*fullTurn
      }));
    }
    pen.fillStyle="#eef3ff";
    for (const star of this.stars) {
      const p=at(star.bearing,star.elevation);
      if (!p || p.y<0) continue;
      pen.globalAlpha=strength*(.62+.38*Math.sin(seconds*1.3+star.phase));
      pen.fillRect(p.x,p.y,star.size,star.size);
    }
    pen.globalAlpha=1;
  }

  drawMoon(pen,moon) {
    const radius=moon.scale*.021;
    const halo=pen.createRadialGradient(moon.x,moon.y,0,moon.x,moon.y,radius*7);
    halo.addColorStop(0,"rgba(190,208,255,.34)");
    halo.addColorStop(1,"rgba(190,208,255,0)");
    pen.fillStyle=halo;
    pen.fillRect(moon.x-radius*7,moon.y-radius*7,radius*14,radius*14);
    const disc=(x,y,r,colour)=>{
      pen.fillStyle=colour;
      pen.beginPath();
      pen.arc(moon.x+x*radius,moon.y+y*radius,r*radius,0,fullTurn);
      pen.fill();
    };
    disc(0,0,1,"#eef1f8");
    disc(-.3,-.2,.26,"#cdd5e6");
    disc(.32,.22,.18,"#d4dbea");
    disc(-.05,.48,.13,"#d4dbea");
  }

  // Atmospheric haze spreads much farther than the small, bright solar disc.
  drawSun(pen,sun) {
    const size=sun.scale;
    const layer=(radius,stops)=>{
      const glow=pen.createRadialGradient(sun.x,sun.y,0,sun.x,sun.y,radius);
      for (const [at,colour] of stops) glow.addColorStop(at,colour);
      pen.fillStyle=glow;
      pen.fillRect(sun.x-radius,sun.y-radius,2*radius,2*radius);
    };
    layer(size*.28,[
      [0,"rgba(236,244,251,.42)"],[.28,"rgba(219,236,250,.23)"],
      [.63,"rgba(203,228,247,.07)"],[1,"rgba(203,228,247,0)"]
    ]);
    layer(size*.10,[
      [0,"rgba(255,254,245,.91)"],[.18,"rgba(255,253,242,.53)"],
      [.44,"rgba(255,247,225,.20)"],[.74,"rgba(255,243,218,.04)"],[1,"rgba(255,243,218,0)"]
    ]);
    layer(size*.026,[
      [0,"#fffefa"],[.78,"#fffdf2"],
      [.9,"rgba(255,252,236,.78)"],[1,"rgba(255,250,232,0)"]
    ]);
  }

  paintClouds() {
    let state=9157;
    const noise=()=>(state=(Math.imul(state,1664525)+1013904223)>>>0)/4294967296;
    const sprites=Array.from({length:7},() => {
      const sprite=document.createElement("canvas");
      const w=sprite.width=512, h=sprite.height=256, base=h*.74;
      const pen=sprite.getContext("2d");
      // Billows pile up into a dome over a flat base; edges stay soft.
      const puffs=[];
      for (let i=0;i<34;i++) {
        const t=noise()*2-1, dome=1-t*t;
        const r=(22+noise()*42)*(.45+.75*dome);
        puffs.push([w/2+t*w*.36,base-r*.35-dome*noise()*h*.42,r]);
      }
      pen.filter="blur(1.5px)";
      for (const [x,y,r] of puffs) {
        const puff=pen.createRadialGradient(x-r*.2,y-r*.25,0,x,y,r);
        puff.addColorStop(0,"rgba(255,255,255,.95)");
        puff.addColorStop(.55,"rgba(250,252,255,.75)");
        puff.addColorStop(1,"rgba(245,249,255,0)");
        pen.fillStyle=puff;
        pen.fillRect(x-r,y-r,2*r,2*r);
      }
      pen.filter="none";
      // Thin wisps trail off the sides.
      for (let i=0;i<10;i++) {
        const x=w/2+(noise()*2-1)*w*.44, y=base-noise()*h*.15, rx=40+noise()*70, ry=6+noise()*9;
        const wisp=pen.createRadialGradient(x,y,0,x,y,rx);
        wisp.addColorStop(0,"rgba(255,255,255,.35)");
        wisp.addColorStop(1,"rgba(255,255,255,0)");
        pen.save(); pen.translate(x,y); pen.scale(1,ry/rx); pen.translate(-x,-y);
        pen.fillStyle=wisp; pen.fillRect(x-rx,y-rx,2*rx,2*rx);
        pen.restore();
      }
      // Volume: warm light on the crowns, cool grey shade under the belly.
      pen.globalCompositeOperation="source-atop";
      const light=pen.createLinearGradient(0,h*.1,0,base+12);
      light.addColorStop(0,"rgba(255,244,222,.35)");
      light.addColorStop(.45,"rgba(255,255,255,0)");
      light.addColorStop(.78,"rgba(150,170,196,.35)");
      light.addColorStop(1,"rgba(118,138,168,.62)");
      pen.fillStyle=light;
      pen.fillRect(0,0,w,h);
      return sprite;
    });
    return Array.from({length:22},(_,i) => {
      const elevation=.14+noise()**1.2*.72;
      return {
        sprite:sprites[i%sprites.length], bearing:noise()*fullTurn, elevation,
        size:.4+noise()*.45, squash:.55+Math.min(.6,elevation*1.2),
        // Higher clouds look slower; all drift the same way.
        speed:.010+noise()*.008-elevation*.006
      };
    });
  }

  draw(pen,view,tree) {
    if(!this.image.complete || !this.image.naturalWidth) return;
    if(!this.panorama.complete || !this.panorama.naturalWidth) return;
    if(!this.rim) this.prepare(view);
    const w=this.image.naturalWidth, h=this.rim.height;
    const focal=view.distance*view.scale;
    const horizon=view.y-focal*Math.tan(view.pitch);
    const horizonInArt=h*.815-w/2*Math.tan(view.pitch);
    // The strip spans a quarter turn. It slides at half the orbit speed, close to the far
    // edge of the floor, so the wall and the ground don't swim against each other.
    const perRadian=this.period/(Math.PI/2);
    const sample=x=>{
      const ray=Math.atan((x-view.x)/focal);
      return {
        u:600+(ray-view.yaw*.5)*perRadian,
        scale:focal/perRadian/Math.cos(ray)
      };
    };
    pen.save();
    for(let x=0;x<view.width;x+=4) {
      const width=Math.min(4,view.width-x);
      const a=sample(x),b=sample(x+width),scale=(a.scale+b.scale)/2;
      const top=horizon-horizonInArt*scale;
      const sx=((a.u%this.period)+this.period)%this.period;
      const sw=b.u-a.u;
      pen.save();
      pen.translate(x,0);
      pen.drawImage(this.rim,sx,0,sw,h,0,top,width,h*scale);
      const bottom=top+h*scale;
      if(bottom<view.height) {
        // Melt the last of the painted gravel into plain ground on tall views.
        const fadeFrom=bottom-h*.10*scale;
        const ground=pen.createLinearGradient(0,fadeFrom,0,bottom);
        ground.addColorStop(0,"#c3beb300");
        ground.addColorStop(1,"#c3beb3");
        pen.fillStyle=ground;
        pen.fillRect(0,fadeFrom,width,view.height-fadeFrom);
      }
      pen.restore();
    }
    if(!this.sandPattern) this.sandPattern=pen.createPattern(this.sand,"no-repeat");
    this.drawPlane(pen,view,this.sandPattern,this.sand.width,this.sandRadius);
    pen.restore();
  }
}
