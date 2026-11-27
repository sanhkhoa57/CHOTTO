// WebGL copy of PaintedTree.draw: same painter's order and colours, but thousands of
// bark faces go to the GPU in a few draw calls. Canvas 2D stays as the fallback.
const treeGL = (() => {
  const surface = document.createElement("canvas");
  const gl = surface.getContext("webgl2", { antialias:true, premultipliedAlpha:true });
  if (!gl) return null;
  const vertexSource = `#version 300 es
    in vec2 position; in vec2 uv; in vec4 color; in vec3 world; in vec2 mode; in vec3 normal;
    uniform vec2 size;
    out vec2 vUv; out vec4 vColor; out vec3 vWorld; flat out vec2 vMode; out vec3 vNormal;
    void main() {
      vUv=uv; vColor=color; vWorld=world; vMode=mode; vNormal=normal;
      gl_Position=vec4(position.x/size.x*2.-1., 1.-position.y/size.y*2., 0., 1.);
    }`;
  // mode.x: 0 flat colour, 1 cel-shaded bark, 2 painted image. mode.y: stain near the ground.
  const fragmentSource = `#version 300 es
    precision highp float;
    in vec2 vUv; in vec4 vColor; in vec3 vWorld; flat in vec2 vMode; in vec3 vNormal;
    uniform sampler2D wood, art;
    uniform vec3 sun, eye;
    out vec4 result;

    // Flat paint areas with soft-edged borders. Brush strokes push the borders around,
    // so each shadow edge looks drawn along the grain instead of following the mesh.
    vec3 celBark() {
      vec3 n=normalize(vNormal);
      vec4 brush=texture(wood,vUv), broad=texture(wood,vUv*vec2(.5,.31)+vec2(.37,.19));
      vec4 fine=texture(wood,vUv*vec2(2.,2.6)+vec2(.11,.53));
      // Hard thresholds keep the carved edges crisp instead of soft and plastic.
      float groove=smoothstep(.30,.55,brush.r), ridge=smoothstep(.30,.60,brush.g);
      float crack=smoothstep(.25,.60,brush.b)*.6+smoothstep(.30,.65,fine.b)*.5;
      // The bark breaks up the light, so no smooth gradient reads as plastic.
      float tone=dot(n,sun)*.42+.52+(ridge-groove)*.2+(broad.g-broad.r)*.18+(fine.g-fine.b)*.06;
      // Matte, muted wood: the lightest tone stays well below a shine.
      vec3 colour=vec3(.200,.190,.225);
      colour=mix(colour,vec3(.320,.290,.280),smoothstep(.405,.425,tone));
      colour=mix(colour,vec3(.440,.395,.350),smoothstep(.625,.645,tone));
      colour=mix(colour,vec3(.545,.495,.425),smoothstep(.825,.850,tone));
      // Warm and cool patches across the trunk, like lichen and weathered wood.
      float weather=sin(vWorld.x*.047+vWorld.y*.029)*sin(vWorld.z*.041-vWorld.y*.017)+(broad.r-.3)*.6;
      colour*=mix(vec3(.94,.97,1.02),vec3(1.03,1.,.95),smoothstep(-.4,.4,weather));
      colour=mix(colour,vec3(.13,.10,.15),groove*.82);
      colour=mix(colour,colour*vec3(.55,.52,.62),clamp(crack,0.,1.)*.75);
      colour+=vec3(.06,.05,.035)*ridge*smoothstep(.50,.78,tone);
      // Sky light catches the turning edge.
      float rim=smoothstep(.58,.80,1.-max(dot(n,eye),0.));
      colour=mix(colour,vec3(.600,.690,.735),rim*(1.-smoothstep(.55,.85,tone))*.07);
      return colour;
    }
    void main() {
      float ground=1.8*sin(vWorld.x*.103+vWorld.z*.064)+1.2*sin(vWorld.z*.137-vWorld.x*.041);
      float height=vWorld.y-ground;
      if (height<0.) discard;
      vec4 painted=texture(art,vUv);
      if (vMode.x<.5) result=vec4(vColor.rgb*vColor.a,vColor.a);
      else if (vMode.x<1.5) result=vec4(celBark(),1.);
      else result=painted;
      if (vMode.y>.5) {
        // Pale light bouncing off the ground settles the roots into the scene.
        float t=clamp((vWorld.y-vMode.y+1000.)/24.,0.,1.);
        result.rgb=mix(result.rgb,vec3(.44,.42,.41)*result.a,(1.-t)*(1.-t)*.55);
      }
    }`;
  const program = gl.createProgram();
  for (const [type,source] of [[gl.VERTEX_SHADER,vertexSource],[gl.FRAGMENT_SHADER,fragmentSource]]) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader,source);
    gl.compileShader(shader);
    gl.attachShader(program,shader);
  }
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program,gl.LINK_STATUS)) return null;

  const STRIDE = 16;
  let data = new Float32Array(STRIDE*65536), length = 0;
  let buffer, textures, blank, woodTexture, bound, sizeAt, sunAt, eyeAt;
  function setup() {
    gl.useProgram(program);
    sizeAt = gl.getUniformLocation(program,"size");
    sunAt = gl.getUniformLocation(program,"sun");
    eyeAt = gl.getUniformLocation(program,"eye");
    gl.uniform1i(gl.getUniformLocation(program,"wood"),0);
    gl.uniform1i(gl.getUniformLocation(program,"art"),1);
    buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
    let offset = 0;
    for (const [name,count] of [["position",2],["uv",2],["color",4],["world",3],["mode",2],["normal",3]]) {
      const at = gl.getAttribLocation(program,name);
      gl.enableVertexAttribArray(at);
      gl.vertexAttribPointer(at,count,gl.FLOAT,false,STRIDE*4,offset*4);
      offset += count;
    }
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE,gl.ONE_MINUS_SRC_ALPHA);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL,true);
    textures = new Map();
    woodTexture = blank = bound = null;
  }
  setup();
  let lost = false;
  surface.addEventListener("webglcontextlost",(event) => { event.preventDefault(); lost=true; });
  surface.addEventListener("webglcontextrestored",() => { setup(); lost=false; sceneKey=""; render(); });

  function upload(image,unit,wrap) {
    const texture = gl.createTexture();
    gl.activeTexture(gl.TEXTURE0+unit);
    gl.bindTexture(gl.TEXTURE_2D,texture);
    gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,image);
    gl.generateMipmap(gl.TEXTURE_2D);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR_MIPMAP_LINEAR);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,wrap);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,wrap);
    // Bark is seen at grazing angles along every limb; keep its grooves sharp there.
    const aniso=gl.getExtension("EXT_texture_filter_anisotropic");
    if (aniso) gl.texParameterf(gl.TEXTURE_2D,aniso.TEXTURE_MAX_ANISOTROPY_EXT,Math.min(8,gl.getParameter(aniso.MAX_TEXTURE_MAX_ANISOTROPY_EXT)));
    return texture;
  }

  // Leaf textures change only when leaves are erased, so re-upload on a new version.
  function artTexture(key,image,version) {
    let entry = textures.get(key);
    if (!entry || entry.image!==image || entry.version!==version) {
      // Draw what is queued before the upload replaces the bound texture.
      flush();
      if (entry) gl.deleteTexture(entry.texture);
      entry = { image,version,texture:upload(image,1,gl.CLAMP_TO_EDGE) };
      textures.set(key,entry);
      bound = entry.texture;
    }
    return entry.texture;
  }

  function flush() {
    if (!length) return;
    gl.bufferData(gl.ARRAY_BUFFER,data.subarray(0,length),gl.STREAM_DRAW);
    gl.drawArrays(gl.TRIANGLES,0,length/STRIDE);
    length = 0;
  }

  const plain = [1,1,1,1];
  const colors = new Map();
  function rgba(hex) {
    let value = colors.get(hex);
    if (!value) {
      value = [1,3,5,7].map((i) => i<hex.length ? parseInt(hex.slice(i,i+2),16)/255 : 1);
      colors.set(hex,value);
    }
    return value;
  }

  // Bark brushwork, drawn once. One tile covers about 54 x 146 world units, so plates and
  // grooves are sized to stay readable from afar. Red: deep grooves and breaks between
  // plates. Green: lit lips on the plate edges. Blue: fine cracks for close views.
  function brushwork() {
    const tile=document.createElement("canvas");
    const size=tile.width=tile.height=1024;
    const pen=tile.getContext("2d");
    pen.fillStyle="#000";
    pen.fillRect(0,0,size,size);
    pen.globalCompositeOperation="lighter";
    pen.lineCap=pen.lineJoin="round";
    let state=48271;
    const noise=()=>(state=(Math.imul(state,1664525)+1013904223)>>>0)/4294967296;
    // A wobbly line drawn nine times so it wraps around every tile edge.
    const line=(points,width,colour)=>{
      pen.strokeStyle=colour;
      pen.lineWidth=width;
      for (const dx of [-size,0,size]) for (const dy of [-size,0,size]) {
        pen.beginPath();
        for (const [x,y] of points) pen.lineTo(x+dx,y+dy);
        pen.stroke();
      }
    };
    // Vertical grooves; the wobble repeats exactly over the tile height.
    const columns=6, step=size/columns, grooves=[];
    for (let c=0;c<columns;c++) {
      const x0=(c+.5+(noise()-.5)*.35)*step, a=noise()*6.3, b=noise()*6.3, k=1+Math.floor(noise()*2);
      const at=(y)=>x0+18*Math.sin(2*Math.PI*k*y/size+a)+9*Math.sin(2*Math.PI*3*y/size+b);
      grooves.push(at);
      for (let y=0;y<size;y+=32) {
        const width=20+12*Math.sin(2*Math.PI*2*y/size+a);
        line([[at(y),y],[at(y+33),y+33]],width,"rgb(255,0,0)");
        line([[at(y)+width*.72,y],[at(y+33)+width*.72,y+33]],width*.32,"rgb(0,210,0)");
      }
    }
    // Horizontal breaks split each strip into plates.
    for (let c=0;c<columns;c++) {
      const left=grooves[c], right=grooves[(c+1)%columns], wrap=c===columns-1 ? size : 0;
      for (let n=0;n<3;n++) {
        const y=(n+noise()*.8)*size/3, tilt=(noise()-.5)*60, width=7+noise()*6;
        const from=left(y), to=right(y+tilt)+wrap;
        const points=[0,.25,.5,.75,1].map((t)=>[from+(to-from)*t,y+tilt*t+(t%1 ? (noise()-.5)*22 : 0)]);
        line(points,width,"rgb(220,0,0)");
        line(points.map(([x,py])=>[x,py+width*.9]),width*.4,"rgb(0,170,0)");
      }
    }
    // Shallow splits inside the plates.
    for (let i=0;i<70;i++) {
      const x=noise()*size, y=noise()*size, length=60+noise()*180, lean=(noise()-.5)*16;
      line([[x,y],[x+lean,y+length*.5],[x-lean*.5,y+length]],3+noise()*6,"rgb(140,0,0)");
    }
    // Fine cracks and grain.
    for (let i=0;i<650;i++) {
      const x=noise()*size, y=noise()*size, length=14+noise()*70, lean=(noise()-.5)*10;
      line([[x,y],[x+lean,y+length]],1.5+noise()*3,"rgb(0,0,255)");
    }
    return tile;
  }

  const noClip = [0,1000,0], noNormal = [0,1,0];
  function vertex(p,u,v,color,alpha,world,mode,stain,normal=noNormal) {
    if (length+STRIDE>data.length) {
      const bigger = new Float32Array(data.length*2);
      bigger.set(data);
      data = bigger;
    }
    data[length++]=p.x; data[length++]=p.y; data[length++]=u; data[length++]=v;
    data[length++]=color[0]; data[length++]=color[1]; data[length++]=color[2]; data[length++]=color[3]*alpha;
    data[length++]=world[0]; data[length++]=world[1]; data[length++]=world[2];
    data[length++]=mode; data[length++]=stain;
    data[length++]=normal[0]; data[length++]=normal[1]; data[length++]=normal[2];
  }

  // The clip test needs a world position at every corner, including ink off the face.
  function flat(points,hex,world) {
    const color = rgba(hex);
    for (let i=2;i<points.length;i++) {
      for (const k of [0,i-1,i]) vertex(points[k],0,0,color,1,world ? world[k] : noClip,0,0);
    }
  }

  function stroke(a,b,width,hex,alpha,wa,wb) {
    const dx=b.x-a.x, dy=b.y-a.y, span=Math.hypot(dx,dy);
    if (!span) return;
    const nx=-dy/span*width/2, ny=dx/span*width/2;
    const color=rgba(hex);
    const corners=[
      [{x:a.x+nx,y:a.y+ny},wa],[{x:b.x+nx,y:b.y+ny},wb],
      [{x:b.x-nx,y:b.y-ny},wb],[{x:a.x-nx,y:a.y-ny},wa]
    ];
    for (const k of [0,1,2,0,2,3]) vertex(corners[k][0],0,0,color,alpha,corners[k][1],0,0);
  }

  // Line art only where a limb turns away: no scratches or patches on each facet.
  function ink(face,points,eye,view) {
    const width=Math.max(.7,Math.min(1.8,1.15*view.scale));
    for (const [edge,a,b] of [[0,0,3],[1,1,2]]) {
      if (dot(mesh[face.edges[edge]].normal,eye)>=0) continue;
      // Opaque pieces that overlap a little read as one unbroken line.
      const from=points[a], to=points[b];
      const span=Math.hypot(to.x-from.x,to.y-from.y)||1;
      const dx=(to.x-from.x)/span*width*.5, dy=(to.y-from.y)/span*width*.5;
      stroke({x:from.x-dx,y:from.y-dy},{x:to.x+dx,y:to.y+dy},width,"#3a2c38",1,face.points[a],face.points[b]);
    }
  }

  function bark(face,points) {
    const [u0,v0,u1,v1]=face.barkUV;
    // Faces touching the ground carry the ground height for their bounce light.
    let stain=0;
    if (face.points.some((p) => p[1]<24)) {
      const [x,,z]=lerp(face.points[0],face.points[2],.5);
      stain=groundHeight(x,z)+1000;
    }
    const uvs=[[u0,v0],[u1,v0],[u1,v1],[u0,v1]];
    for (const k of [0,1,3,2,3,1]) vertex(points[k],uvs[k][0],uvs[k][1],plain,1,face.points[k],1,stain,face.smooth[k]);
  }

  function quad(corners,texture) {
    if (bound!==texture) {
      flush();
      gl.activeTexture(gl.TEXTURE1);
      gl.bindTexture(gl.TEXTURE_2D,texture);
      bound=texture;
    }
    const uvs=[[0,0],[1,0],[1,1],[0,1]];
    for (const k of [0,1,2,0,2,3]) vertex(corners[k],uvs[k][0],uvs[k][1],plain,1,noClip,2,0);
  }

  // Corners of a w by h picture centred on a point, then flipped and rotated.
  function placed(x,y,left,top,w,h,rotation=0,flip=1) {
    const c=Math.cos(rotation), s=Math.sin(rotation);
    return [[left,top],[left+w,top],[left+w,top+h],[left,top+h]].map(([px,py]) => ({
      x:x+c*px*flip-s*py, y:y+s*px*flip+c*py
    }));
  }

  function draw(tree,view,pen) {
    if (surface.width!==canvas.width || surface.height!==canvas.height) {
      surface.width=canvas.width;
      surface.height=canvas.height;
    }
    gl.viewport(0,0,surface.width,surface.height);
    gl.uniform2f(sizeAt,view.width,view.height);
    gl.clearColor(0,0,0,0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    if (!woodTexture) woodTexture=upload(brushwork(),0,gl.REPEAT);
    // Kept current in case the foliage picture is swapped.
    blank=artTexture(tree,tree.foliage,0);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D,woodTexture);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D,blank);
    bound=blank;
    const eye=[view.sinYaw*view.cosPitch,view.sinPitch,view.cosYaw*view.cosPitch];
    // The sun leans with the camera so the far side of the tree never goes flat and dark.
    const side=[.62*view.cosYaw+.55*view.sinYaw,.5,-.62*view.sinYaw+.55*view.cosYaw];
    gl.uniform3fv(sunAt,unit(light.map((v,axis) => v*.55+side[axis]*.6)));
    gl.uniform3fv(eyeAt,eye);
    const { items,visible }=tree.sorted(view,eye);
    for (const item of items) {
      if (item.piece) {
        const piece=item.piece;
        if (piece.sprite) {
          const p=item.points[0];
          const span=piece.width*p.factor;
          const width=span*(.62+.38*Math.abs(Math.cos(piece.angle-view.yaw)));
          quad(placed(p.x,p.y,-width/2,-span*.15,width,span*.195),artTexture(piece.sprite,piece.sprite,crater.rim ? 1 : 0));
        } else {
          flat(item.points,piece.color);
        }
      } else if (item.face) {
        bark(item.face,item.points);
        if (item.face.edges) ink(item.face,item.points,eye,view);
      } else {
        const {layer,point}=item;
        const w=layer.width*point.factor,h=layer.height*point.factor;
        quad(placed(point.x,point.y,-w/2,-h/2,w,h,layer.rotation,layer.flip),blank);
        tree.addVisible(layer,point,view,visible);
      }
    }
    flush();
    pen.drawImage(surface,0,0,view.width,view.height);
    return visible;
  }

  // Images opened straight from disk may not be uploaded to WebGL; fall back then.
  let blocked = false;
  return {
    draw(tree,view,pen) {
      if (lost || blocked) return null;
      try { return draw(tree,view,pen); }
      catch (error) {
        if (error.name!=="SecurityError") throw error;
        blocked=true;
        length=0;
        return null;
      }
    }
  };
})();
