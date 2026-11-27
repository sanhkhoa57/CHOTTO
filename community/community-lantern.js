// An old storm lantern hung from the lowest bough on the right. It sways with the wind and
// lights itself in the evening. Painted every frame, over the cached tree.
class HangingLantern {
  // `at` is the point of the bough the cord is tied to, in world units.
  constructor(at) {
    this.at=at;
    this.cord=105;                       // world units from the bough to the handle
    this.height=150;
    this.width=this.height*120/190;
    this.metal=this.paint(false);
    this.flame=this.paint(true);
  }

  // The sprite is 120 x 190. `lit` paints only the glowing glass and its flame, with the
  // cage redrawn over them, so it can be laid over the unlit lantern after dark.
  paint(lit) {
    const sprite=document.createElement("canvas");
    sprite.width=240;
    sprite.height=380;
    const pen=sprite.getContext("2d");
    pen.scale(2,2);
    pen.lineJoin=pen.lineCap="round";
    const ink="#241a1c";
    const shape=(path,fill,stroke=ink,width=3)=>{
      const outline=new Path2D(path);
      if (fill) { pen.fillStyle=fill; pen.fill(outline); }
      if (stroke) { pen.strokeStyle=stroke; pen.lineWidth=width; pen.stroke(outline); }
    };
    // Worn dark brass: a lit stripe left of centre, shade toward both edges.
    const brass=pen.createLinearGradient(14,0,106,0);
    [[0,"#3a2a22"],[.28,"#a57c46"],[.42,"#d3ab68"],[.62,"#7d5a34"],[1,"#33251f"]]
      .forEach(([stop,colour])=>brass.addColorStop(stop,colour));
    const globe="M43 66C27 80 24 104 33 122C36 129 40 133 43 137L77 137C80 133 84 129 87 122C96 104 93 80 77 66Z";

    if (lit) {
      const light=pen.createRadialGradient(60,108,3,60,104,40);
      light.addColorStop(0,"#fffbe2");
      light.addColorStop(.35,"#ffd978");
      light.addColorStop(.75,"#f79a35");
      light.addColorStop(1,"#c9631f");
      shape(globe,light,null);
      shape("M60 82C70 98 73 108 67 117C63 123 57 123 53 117C47 108 50 98 60 82Z","#fff6cf",null);
      shape("M60 99C65 107 65 113 60 118C55 113 55 107 60 99Z","#ffb23e",null);
    } else {
      // Wire handle and the loop the cord is tied to.
      shape("M27 63C12 22 38 8 60 8C82 8 108 22 93 63",null,ink,6);
      shape("M27 63C12 22 38 8 60 8C82 8 108 22 93 63",null,"#8a6a42",2.5);
      shape("M54 9a6 6 0 1 0 12 0a6 6 0 1 0-12 0Z",null,ink,3);
      const glass=pen.createLinearGradient(30,66,92,137);
      glass.addColorStop(0,"rgba(226,236,226,.88)");
      glass.addColorStop(.55,"rgba(158,174,168,.72)");
      glass.addColorStop(1,"rgba(104,118,118,.85)");
      shape(globe,glass);
      shape("M60 108L60 122M52 122L68 122",null,"#3a2f2a",4);       // wick holder
      shape("M42 78C35 91 35 106 40 119",null,"rgba(255,255,255,.75)",3.5);
      // Chimney cap with its vent, then the burner collar and the oil tank.
      shape("M36 66L42 52L78 52L84 66Z",brass);
      shape("M45 52L47 40L73 40L75 52Z",brass);
      shape("M37 40C42 28 78 28 83 40Z",brass);
      shape("M49 46L71 46M44 59L76 59",null,ink,2.5);
      shape("M38 136L82 136L86 148L34 148Z",brass);
      shape("M34 148C16 150 12 168 24 174L96 174C108 168 104 150 86 148Z",brass);
      shape("M22 174L98 174L103 184L17 184Z",brass);
      shape("M20 161C45 167 75 167 100 161",null,ink,2);
    }
    // The wire cage crossing the glass.
    for (const path of ["M33 63C19 90 19 115 36 139","M87 63C101 90 101 115 84 139",
      "M28 93C49 101 71 101 92 93","M31 119C50 127 70 127 89 119","M60 67L60 78"]) {
      shape(path,null,lit ? "#5a2f18" : ink,3);
    }
    return sprite;
  }

  // Screen position of the knot, following the swaying crown, and the swing of the cord.
  pose(seconds,animate) {
    const knot=project(this.at);
    knot.x+=canopyOffset(knot.y);
    const swing=animate ? .055*Math.sin(seconds*1.25)+.022*Math.sin(seconds*2.9+1) : 0;
    const drop=(this.cord+this.height*.6)*knot.factor;
    return { knot, swing, glow:{ x:knot.x-Math.sin(swing)*drop, y:knot.y+Math.cos(swing)*drop } };
  }

  // When the trunk stands between the camera and the lantern, cuts its outline out of
  // whatever is painted next.
  hideBehindTrunk(pen,knot) {
    const y=this.at[1]-this.cord-this.height*.5;
    const depth=project([this.at[0],y,this.at[2]]).depth;
    const middle=trunk.findIndex(point=>point[1]>=y);
    if (depth>=project(trunk[middle]).depth) return;
    const outline=[];
    // As tall as the widest halo, so the cut never ends in a visible edge across the bole.
    for (let step=0;step<=12;step++) {
      const level=Math.max(0,y+420-step*70);
      const i=Math.max(1,trunk.findIndex(point=>point[1]>=level));
      const t=Math.max(0,Math.min(1,(level-trunk[i-1][1])/(trunk[i][1]-trunk[i-1][1])));
      const axis=project(lerp(trunk[i-1],trunk[i],t));
      // trunkRadii[0] belongs to the foot below the first trunk point.
      const radius=(trunkRadii[i]+(trunkRadii[i+1]-trunkRadii[i])*t)*axis.factor;
      outline.push({ x:axis.x+canopyOffset(axis.y), y:axis.y, radius });
    }
    const cut=new Path2D();
    cut.rect(0,0,view.width,view.height);
    outline.forEach((p,i)=>cut[i ? "lineTo" : "moveTo"](p.x-p.radius,p.y));
    for (const p of [...outline].reverse()) cut.lineTo(p.x+p.radius,p.y);
    cut.closePath();
    pen.clip(cut,"evenodd");
  }

  place(pen,sprite,{ knot,swing }) {
    pen.translate(knot.x,knot.y);
    pen.rotate(swing);
    const w=this.width*knot.factor, h=this.height*knot.factor;
    pen.drawImage(sprite,-w/2,this.cord*knot.factor,w,h);
  }

  // The unlit lantern and its cord. Painted on a layer that takes the light of the hour.
  drawBody(pen,pose) {
    const { knot,swing }=pose;
    pen.save();
    this.hideBehindTrunk(pen,knot);
    pen.save();
    pen.translate(knot.x,knot.y);
    pen.rotate(swing);
    pen.strokeStyle="#3b2c22";
    pen.lineWidth=Math.max(1,5*knot.factor);
    pen.beginPath();
    pen.moveTo(0,0);
    pen.lineTo(0,(this.cord+4)*knot.factor);
    pen.stroke();
    // A few turns of cord wound round the bough.
    pen.lineWidth=Math.max(1,9*knot.factor);
    pen.beginPath();
    pen.moveTo(-13*knot.factor,0);
    pen.lineTo(13*knot.factor,3*knot.factor);
    pen.stroke();
    pen.restore();
    this.place(pen,this.metal,pose);
    pen.restore();
  }

  // The pool of lamplight on the ground, painted before the tree so the trunk covers it.
  drawPool(pen,level) {
    const centre=project([this.at[0],0,this.at[2]]);
    const radius=430*centre.factor;
    pen.save();
    pen.globalCompositeOperation="lighter";
    pen.translate(centre.x,centre.y);
    pen.scale(radius,radius*Math.max(.12,view.sinPitch));
    const pool=pen.createRadialGradient(0,0,0,0,0,1);
    pool.addColorStop(0,"rgba(255,162,64,"+.26*level+")");
    pool.addColorStop(.5,"rgba(224,120,44,"+.11*level+")");
    pool.addColorStop(1,"rgba(180,90,30,0)");
    pen.fillStyle=pool;
    pen.fillRect(-1,-1,2,2);
    pen.restore();
  }

  // The burning glass and the halo it throws on the bark and leaves around it.
  drawLight(pen,pose,level,seconds,animate) {
    const flicker=animate ? 1+.05*Math.sin(seconds*9.1)+.035*Math.sin(seconds*23.7) : 1;
    const { knot,glow }=pose;
    pen.save();
    this.hideBehindTrunk(pen,knot);
    pen.save();
    pen.globalAlpha=level;
    this.place(pen,this.flame,pose);
    pen.restore();
    pen.globalCompositeOperation="lighter";
    for (const [reach,alpha,colour] of [[390,.26,"255,150,58"],[155,.4,"255,178,82"],[50,.46,"255,226,150"]]) {
      const radius=reach*knot.factor*flicker;
      const halo=pen.createRadialGradient(glow.x,glow.y,0,glow.x,glow.y,radius);
      halo.addColorStop(0,"rgba("+colour+","+alpha*level*flicker+")");
      halo.addColorStop(.45,"rgba("+colour+","+alpha*.36*level+")");
      halo.addColorStop(1,"rgba("+colour+",0)");
      pen.fillStyle=halo;
      pen.fillRect(glow.x-radius,glow.y-radius,2*radius,2*radius);
    }
    pen.restore();
  }
}
