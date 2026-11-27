// The crater painting supplies both the distant rim and a ground texture around the tree.
// All lengths on the ground are in the same world units as the roots.
class PaintedCrater {
  constructor(image,panorama) {
    this.image=image;
    // Seamless strip cut from the same painting by tools/make_community_panorama.py.
    this.panorama=panorama;
    this.radius=860;
    this.floor=document.createElement("canvas");
    this.floor.width=this.floor.height=1024;
    this.shadow=document.createElement("canvas");
    this.shadow.width=this.shadow.height=this.floor.width;
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
    const size=canvas.width=canvas.height=this.floor.width;
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
    return canvas;
  }

  bakeFloor(tree) {
    const size=this.floor.width, pixels=size/(2*this.radius);
    const shade=this.shadow.getContext("2d");
    shade.setTransform(1,0,0,1,0,0);
    shade.clearRect(0,0,size,size);
    shade.save();
    shade.translate(size/2,size/2);
    shade.scale(pixels,pixels);
    const cast=([x,y,z])=>[x-y*light[0]/light[1],z-y*light[2]/light[1]];
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
        shade.lineWidth=(limb===trunk ? 73 : 28)*(1-.55*i/limb.length);
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
      shade.drawImage(tree.foliage,-layer.width/2,-layer.height/2,layer.width,layer.height);
      shade.restore();
    }
    shade.restore();
    shade.globalCompositeOperation="source-in";
    shade.fillStyle="#27363a";
    shade.fillRect(0,0,size,size);
    shade.globalCompositeOperation="source-over";

    const brush=this.floor.getContext("2d");
    brush.clearRect(0,0,size,size);
    brush.drawImage(this.sand,0,0);
    brush.save();
    brush.globalAlpha=.42;
    brush.filter="blur(2px)";
    brush.drawImage(this.shadow,0,0);
    brush.restore();
    const fade=brush.createRadialGradient(size/2,size/2,size*.33,size/2,size/2,size*.5);
    fade.addColorStop(0,"#000");
    fade.addColorStop(1,"transparent");
    brush.save();
    brush.globalCompositeOperation="destination-in";
    brush.fillStyle=fade;
    brush.fillRect(0,0,size,size);
    brush.restore();
    this.pattern=brush.createPattern(this.floor,"no-repeat");
  }

  // Painted sky behind the crater rim: deepening blue, a slowly wandering sun and drifting
  // cumulus. Drawn every frame on its own layer, under the cached scene (whose sky is clear).
  // Sky features sit at fixed bearings and turn with the camera at full speed.
  drawSky(pen,view,seconds) {
    const focal=view.distance*view.scale;
    const horizon=view.y-focal*Math.tan(view.pitch);
    const at=(bearing,elevation)=>{
      const ray=Math.atan2(Math.sin(bearing+view.yaw),Math.cos(bearing+view.yaw));
      if (Math.abs(ray)>1.35) return null;
      return {x:view.x+focal*Math.tan(ray),y:horizon-focal*Math.tan(elevation)/Math.cos(ray),scale:focal/Math.cos(ray)};
    };
    const elevationY=(e)=>horizon-focal*Math.tan(e);
    const air=pen.createLinearGradient(0,elevationY(1.1),0,horizon);
    air.addColorStop(0,"#123f86");
    air.addColorStop(.45,"#2a73c6");
    air.addColorStop(.8,"#6aaee0");
    air.addColorStop(1,"#bfe0ef");
    pen.fillStyle=air;
    pen.fillRect(0,0,view.width,horizon+2);

    // The sun creeps along a low arc, about one degree every ten seconds.
    const sun=at(.30+seconds*.0018,.60+.04*Math.sin(seconds*.021));
    if (sun) this.drawSun(pen,view,sun,seconds);

    // Soft cumulus, painted once into sprites. Each drifts with the wind at its own pace.
    if (!this.clouds) this.clouds=this.paintClouds();
    for (const cloud of this.clouds) {
      const c=at(cloud.bearing+seconds*cloud.speed,cloud.elevation);
      if (!c) continue;
      const w=c.scale*cloud.size, h=w*cloud.sprite.height/cloud.sprite.width*cloud.squash;
      pen.globalAlpha=Math.min(1,.45+cloud.elevation*1.6);
      pen.drawImage(cloud.sprite,c.x-w/2,c.y-h*.72,w,h);
    }
    pen.globalAlpha=1;
  }

  // A bright core that blooms into the sky, a warm inner halo, faint shimmering rays and a
  // few lens ghosts on the line through the middle of the view.
  drawSun(pen,view,sun,seconds) {
    const size=sun.scale;
    const layer=(radius,stops)=>{
      const glow=pen.createRadialGradient(sun.x,sun.y,0,sun.x,sun.y,radius);
      for (const [at,colour] of stops) glow.addColorStop(at,colour);
      pen.fillStyle=glow;
      pen.fillRect(sun.x-radius,sun.y-radius,2*radius,2*radius);
    };
    layer(size*.9,[[0,"rgba(214,236,250,.55)"],[.4,"rgba(170,212,242,.25)"],[1,"rgba(170,212,242,0)"]]);
    pen.save();
    pen.globalCompositeOperation="lighter";
    layer(size*.16,[[0,"rgba(255,246,220,.85)"],[.3,"rgba(255,232,180,.35)"],[1,"rgba(255,226,170,0)"]]);
    // Thin rays turn very slowly and breathe.
    pen.translate(sun.x,sun.y);
    pen.rotate(seconds*.012);
    for (let i=0;i<22;i++) {
      const angle=i*fullTurn/22+.13*Math.sin(i*2.7);
      const breathe=.65+.35*Math.sin(seconds*.7+i*1.9);
      const reach=size*(.14+.2*((i*7)%5)/5)*breathe, spread=.008+.006*((i*3)%4)/4;
      const ray=pen.createLinearGradient(0,0,Math.cos(angle)*reach,Math.sin(angle)*reach);
      ray.addColorStop(0,`rgba(255,248,226,${.32*breathe})`);
      ray.addColorStop(1,"rgba(255,248,226,0)");
      pen.fillStyle=ray;
      pen.beginPath();
      pen.moveTo(0,0);
      pen.lineTo(Math.cos(angle-spread)*reach,Math.sin(angle-spread)*reach);
      pen.lineTo(Math.cos(angle+spread)*reach,Math.sin(angle+spread)*reach);
      pen.fill();
    }
    pen.setTransform(view.dpr,0,0,view.dpr,0,0);
    // Blinding core.
    layer(size*.035,[[0,"#ffffff"],[.45,"rgba(255,255,250,.98)"],[.7,"rgba(255,250,232,.5)"],[1,"rgba(255,246,220,0)"]]);
    // Lens ghosts mirror the sun through the centre of the frame.
    const cx=view.width/2, cy=view.height/2;
    for (const [t,r,colour] of [[.35,.012,"rgba(255,214,150,.16)"],[.7,.028,"rgba(170,220,255,.10)"],[1.25,.018,"rgba(200,255,210,.10)"],[1.6,.05,"rgba(255,200,170,.07)"]]) {
      const x=sun.x+(cx-sun.x)*t*2, y=sun.y+(cy-sun.y)*t*2, radius=size*r;
      const ghost=pen.createRadialGradient(x,y,radius*.6,x,y,radius);
      ghost.addColorStop(0,colour);
      ghost.addColorStop(1,"rgba(255,255,255,0)");
      pen.fillStyle=ghost;
      pen.beginPath(); pen.arc(x,y,radius,0,fullTurn); pen.fill();
    }
    pen.restore();
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
    if(!this.pattern) this.bakeFloor(tree);
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
    const size=this.floor.width, units=2*this.radius/size;
    pen.fillStyle=this.pattern;
    // One row of a horizontal plane has constant depth and an affine texture mapping.
    const step=Math.max(1,Math.round(view.dpr*2));
    const start=Math.max(0,Math.floor(project([ -this.radius*view.sinYaw,0,-this.radius*view.cosYaw ]).y*view.dpr));
    for(let py=start;py<view.height*view.dpr;py+=step) {
      const y=(py+step*.5)/view.dpr;
      const slope=(y-view.y)/focal;
      const depth=view.distance*slope/(view.sinPitch+slope*view.cosPitch);
      if(depth>this.radius) break;
      const perspective=view.distance/(view.distance-depth*view.cosPitch);
      const across=units*view.scale*perspective;
      const along=across*perspective*view.sinPitch;
      const a=across*view.cosYaw,c=-across*view.sinYaw;
      const b=along*view.sinYaw,d=along*view.cosYaw;
      this.pattern.setTransform({a,b,c,d,e:view.x-(a+c)*size/2,f:y-along*depth/units-(b+d)*size/2});
      pen.fillRect(0,py/view.dpr,view.width,step/view.dpr);
    }
    pen.restore();
  }
}
