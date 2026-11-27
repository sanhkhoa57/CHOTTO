// Registered to the same crown groups and record IDs as the orbitable model.
class PaintedTree {
  // count leaves are split evenly over the leaf masses, in number order.
  constructor(wood, foliage, groups, count, woodFaces, ground) {
    this.wood = wood;
    this.faces = woodFaces.map(face=>({...face,exposed:exposedBark(face.points)}))
      .filter(face=>face.exposed.length>=3);
    this.ground = ground;
    this.patterns = [];
    this.accents = [];
    this.accentPoints = new Map();
    this.leafArt = document.getElementById("leaf-art");
    this.foliage = foliage;
    this.perLayer = Math.ceil(count/groups.length);
    this.layers = groups.map(([x,y,z,r],i) => ({
      x, y, z, index:i, width:r*3.05, height:r*1.85, flip:i%3 === 0 ? -1 : 1,
      rotation:.10*Math.sin(i*1.7), start:i*this.perLayer+1,
      count:Math.max(0,Math.min(this.perLayer,count-i*this.perLayer))
    }));
  }

  // Each leaf sits on one of the 300 painted hit points of its mass. Thousands of leaves
  // share a mass, so about ten share each point; the first record stands for them.
  sampleOf(layer,j) {
    return (j*137+layer.index*19)%300;
  }

  place(leaf) {
    const layer = this.layers[Math.floor((leaf.id-1)/this.perLayer)];
    const sample = this.sampleOf(layer,leaf.id-layer.start);
    leaf.paint = { layer,u:paintedLeafSamples[sample*2]/255,v:paintedLeafSamples[sample*2+1]/255 };
  }

  // Leaf numbers on one hit point: j ≡ (s-19i)·137⁻¹ (mod 300), and 137⁻¹ = 173.
  firstLeafAtSample(layer,sample) {
    const first = ((((sample-layer.index*19)%300)+300)%300*173)%300;
    return first < layer.count ? layer.start+first : 0;
  }

  get ready() {
    return this.wood.complete && this.wood.naturalWidth && this.foliage.complete && this.foliage.naturalWidth;
  }

  leafPoint(leaf,view,t=0,layerCenter=null) {
    const { layer,u,v } = leaf.paint;
    const dx=(u-.5)*layer.width*layer.flip, dy=(v-.5)*layer.height;
    const c=Math.cos(layer.rotation), s=Math.sin(layer.rotation);
    const center=layerCenter || project([layer.x+t*46,layer.y*(1-t*t),layer.z+t*30]);
    const sway=t ? 16*(Math.sin(t*10+leaf.id)-Math.sin(leaf.id)) : 0;
    return {
      x:center.x+(c*dx-s*dy+sway)*center.factor,
      y:center.y+(s*dx+c*dy)*(1-t*t)*center.factor,
      factor:center.factor, depth:center.depth
    };
  }

  prepareAccents(entries) {
    // Use the front records in each small patch so rear leaves don't shine through the crown.
    const depthAt=new Map(), cell=Math.max(9,18*view.scale);
    const key=p=>Math.floor(p.x/cell)+","+Math.floor(p.y/cell);
    for (const {point} of entries) {
      const k=key(point);
      depthAt.set(k,Math.max(depthAt.get(k)??-Infinity,point.depth));
    }
    this.accents=entries.filter(({point})=>depthAt.get(key(point))-point.depth<24);
  }

  drawAccents(ctx,seconds,animate) {
    this.accentPoints.clear();
    const art=this.leafArt;
    if (!art.naturalWidth) return;
    const aspect=art.naturalHeight/art.naturalWidth;
    for (const {leaf,point} of this.accents) {
      const phase=leaf.paint.layer.x*.012+leaf.paint.u*1.3;
      const gust=animate ? Math.sin(seconds*1.65+phase)*.72+Math.sin(seconds*3.1+phase)*.28 : 0;
      const length=(leaf.size*1.8+3)*point.factor;
      const x=point.x+canopyOffset(point.y)+gust*length*.15, y=point.y+gust*length*.055;
      this.accentPoints.set(leaf.id,{...point,x,y});
      ctx.save();
      ctx.translate(x,y);
      ctx.rotate(leaf.angle+gust*.22);
      ctx.scale(leaf.id%2 ? 1 : -1,1);
      const height=length*aspect*(.83+.15*gust);
      ctx.fillStyle="#16271966";
      ctx.beginPath();
      ctx.ellipse(length*.04,height*.25,length*.47,height*.36,0,0,2*Math.PI);
      ctx.fill();
      ctx.globalAlpha=.84;
      ctx.drawImage(art,-length*.5,-height*.5,length,height);
      ctx.restore();
    }
    if (!animate) return;
    // Short ink strokes follow a passing gust; leave quiet beats between gusts.
    const t=(seconds%7)/2.4;
    if (t>=1) return;
    const p=project([-640+1280*t,1000+30*Math.sin(t*Math.PI),220]);
    ctx.save();
    ctx.strokeStyle="#f6f1ca";
    ctx.globalAlpha=.42*Math.sin(t*Math.PI);
    ctx.lineWidth=Math.max(.7,view.scale*.9);
    ctx.lineCap="round";
    for (let i=0;i<2;i++) {
      const x=p.x+i*17*p.factor,y=p.y+i*7*p.factor;
      ctx.beginPath(); ctx.moveTo(x,y);
      ctx.quadraticCurveTo(x+21*p.factor,y-7*p.factor,x+(45-i*16)*p.factor,y-5*p.factor);
      ctx.stroke();
    }
    ctx.restore();
  }

  prepareBark(ctx) {
    for (let level=0;level<12;level++) {
      const tile=document.createElement("canvas");
      tile.width=this.wood.naturalWidth;
      tile.height=this.wood.naturalHeight;
      const brush=tile.getContext("2d");
      brush.drawImage(this.wood,0,0);
      brush.fillStyle=level<8 ? "#122026" : "#f2e1a5";
      brush.globalAlpha=level<8 ? (8-level)*.087 : (level-8)*.055;
      brush.fillRect(0,0,tile.width,tile.height);
      this.patterns.push(ctx.createPattern(tile,"repeat"));
    }
  }

  drawBark(ctx,face,points) {
    const lit=dot(face.normal,light);
    const pattern=this.patterns[Math.max(0,Math.min(11,Math.round(5.8+lit*5.2)))];
    const [u0,v0,u1,v1]=face.barkUV;
    const w=this.wood.naturalWidth,h=this.wood.naturalHeight;
    const du=(u1-u0)*w,dv=(v1-v0)*h;
    // Map each triangle of the tapered quad to the same continuous strip of painted grain.
    const triangle=(origin,along,up,u,v,sign)=>{
      const a=(along.x-origin.x)/(du*sign), b=(along.y-origin.y)/(du*sign);
      const c=(up.x-origin.x)/(dv*sign), d=(up.y-origin.y)/(dv*sign);
      if (Math.abs(a*d-b*c)<1e-8) return;
      pattern.setTransform({a,b,c,d,e:origin.x-a*u*w-c*v*h,f:origin.y-b*u*w-d*v*h});
      ctx.fillStyle=ctx.strokeStyle=pattern;
      ctx.beginPath();
      ctx.moveTo(origin.x,origin.y);
      ctx.lineTo(along.x,along.y);
      ctx.lineTo(up.x,up.y);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    };
    triangle(points[0],points[1],points[3],u0,v0,1);
    triangle(points[2],points[3],points[1],u1,v1,-1);
  }

  // Painter's order shared by the WebGL and Canvas 2D renderers.
  sorted(view,eye) {
    const items=[];
    for (const piece of this.ground) {
      const points=piece.vertices.map(project);
      items.push({piece,points,depth:points.reduce((sum,p)=>sum+p.depth,0)/points.length});
    }
    for (const face of this.faces) {
      if (dot(face.normal,eye)<-.08) continue;
      const points=face.points.map(project);
      const depth=points.reduce((sum,p)=>sum+p.depth,0)/4;
      items.push({face,points,depth});
    }
    for (const layer of this.layers) {
      if (!layer.count) continue;
      const point=project([layer.x,layer.y,layer.z]);
      // Leaves cover the twigs inside the crown, including on its far side.
      items.push({layer,point,depth:point.depth+layer.width*.22});
    }
    items.sort((a,b)=>a.depth-b.depth);
    return { items,visible:[] };
  }

  // Drawing only records which leaf masses are on screen; hit targets are built from them
  // on demand, because a turn of the view would otherwise rebuild tens of thousands.
  addVisible(layer,point,view,visible) {
    visible.push({layer,point});
  }

  // One live leaf per painted point (not every leaf in the mass); every 97th point only
  // for the leaves that flutter in the wind.
  targets(shown,view,fluttering=false) {
    const entries=[];
    for (const {layer,point} of shown) {
      for (let sample=0;sample<300;sample+=fluttering ? 97 : 1) {
        const id=this.firstLeafAtSample(layer,sample);
        if (!id) continue;
        const leaf=leafAt(id);
        entries.push({leaf,point:this.leafPoint(leaf,view,0,point)});
      }
    }
    return entries;
  }

  draw(ctx,view) {
    const drawn=treeGL?.draw(this,view,ctx);
    if (drawn) return drawn;
    if (!this.patterns.length) this.prepareBark(ctx);
    const eye=[view.sinYaw*view.cosPitch,view.sinPitch,view.cosYaw*view.cosPitch];
    const {items,visible}=this.sorted(view,eye);
    ctx.lineWidth=.55;
    ctx.lineJoin="round";
    for (const item of items) {
      if (item.piece) {
        const piece=item.piece;
        if(piece.sprite) {
          const p=item.points[0];
          const span=piece.width*p.factor;
          const width=span*(.62+.38*Math.abs(Math.cos(piece.angle-view.yaw)));
          ctx.drawImage(piece.sprite,p.x-width/2,p.y-span*.15,width,span*.195);
        } else {
          polygon(item.points,piece.color,ctx);
        }
        continue;
      }
      if (item.face) {
        const {face,points}=item;
        const clipped=face.exposed!==face.points;
        if (clipped) {
          ctx.save();
          tracePolygon(face.exposed.map(project),ctx);
          ctx.clip();
        }
        this.drawBark(ctx,face,points);
        if (face.edges) {
          ctx.save();
          ctx.globalAlpha=.42;
          inkFace({...face,points},eye,ctx);
          ctx.restore();
        }
        if (face.points.some(p=>p[1]<15)) {
          const [x,,z]=lerp(face.points[0],face.points[2],.5);
          const y=groundHeight(x,z);
          const base=project([x,y,z]),top=project([x,y+15,z]);
          const stain=ctx.createLinearGradient(base.x,base.y,top.x,top.y);
          stain.addColorStop(0,"#39362db8");
          stain.addColorStop(.45,"#60554059");
          stain.addColorStop(1,"#60554000");
          polygon(points,stain,ctx);
        }
        if (clipped) ctx.restore();
        continue;
      }
      const {layer,point}=item;
      ctx.save();
      const w=layer.width*point.factor,h=layer.height*point.factor;
      ctx.translate(point.x,point.y);
      ctx.rotate(layer.rotation);
      ctx.scale(layer.flip,1);
      ctx.drawImage(this.foliage,-w/2,-h/2,w,h);
      this.addVisible(layer,point,view,visible);
      ctx.restore();
    }
    return visible;
  }
}
