/* POV Scene Kit — first-person robot-bartender scenes.
   Requires three.js r128 (UMD global THREE) loaded first.
   Exposes one global: POVScene. See README.md for the config shape. */
(function (global) {
  'use strict';
  if (typeof THREE === 'undefined') { global.POVScene = { error: 'three.js not loaded' }; return; }

  var M = THREE.MathUtils, V3 = THREE.Vector3, QT = THREE.Quaternion;
  var UP = new V3(0, 1, 0);

  /* ---------------- easing + small helpers ---------------- */
  function ease(t)    { return t < 0.5 ? 2*t*t : 1 - Math.pow(-2*t + 2, 2)/2; }
  function easeIn(t)  { return t*t; }
  function easeOut(t) { return 1 - Math.pow(1 - t, 3); }
  function seg(t, a, b) { return M.clamp((t - a) / (b - a), 0, 1); }
  function v3(a)      { return new V3(a[0], a[1], a[2]); }
  function eulerQ(e, order) { return new QT().setFromEuler(new THREE.Euler(e[0], e[1], e[2], order || 'ZXY')); }
  function pick(a, b) { return a === undefined ? b : a; }
  function toGrey(c) { var y = 0.2126*c.r + 0.7152*c.g + 0.0722*c.b; return c.setRGB(y, y, y); }

  function aim(mesh, a, b, base) {
    var d = new V3().subVectors(b, a), len = d.length();
    mesh.position.copy(a).addScaledVector(d, 0.5);
    mesh.quaternion.setFromUnitVectors(UP, d.clone().normalize());
    mesh.scale.y = len / base;
    return { len: len, dir: d.normalize() };
  }

  /* Two-bone IK: where the elbow sits between shoulder and wrist. */
  function solveElbow(S, W, L1, L2, pole) {
    var dir = new V3().subVectors(W, S);
    var d = Math.min(dir.length(), L1 + L2 - 0.002);
    dir.normalize();
    var a = (L1*L1 - L2*L2 + d*d) / (2*d);
    var h = Math.sqrt(Math.max(0, L1*L1 - a*a));
    var perp = pole.clone().addScaledVector(dir, -pole.dot(dir));
    if (perp.lengthSq() < 1e-6) perp.set(0, -1, 0).addScaledVector(dir, dir.y);
    perp.normalize();
    return S.clone().addScaledVector(dir, a).addScaledVector(perp, h);
  }

  /* ---------------- canvas textures ---------------- */
  function cv(w, h) { var c = document.createElement('canvas'); c.width = w; c.height = h; return c; }
  function toTex(c, rx, ry) {
    var t = new THREE.CanvasTexture(c);
    t.encoding = THREE.sRGBEncoding; t.anisotropy = 4;
    if (rx) { t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(rx, ry); }
    return t;
  }
  function woodTex(top, bottom) {
    var c = cv(1024, 512), x = c.getContext('2d');
    var g = x.createLinearGradient(0, 0, 0, 512);
    g.addColorStop(0, top || '#3b2417'); g.addColorStop(0.55, '#2b1a10'); g.addColorStop(1, bottom || '#20130a');
    x.fillStyle = g; x.fillRect(0, 0, 1024, 512);
    for (var i = 0; i < 300; i++) {
      var a = 0.03 + Math.random()*0.11;
      x.strokeStyle = 'rgba(' + (92 + Math.random()*70 | 0) + ',' + (56 + Math.random()*38 | 0) + ',' + (30 + Math.random()*24 | 0) + ',' + a + ')';
      x.lineWidth = 0.5 + Math.random()*2.6;
      var yy = Math.random()*512;
      x.beginPath(); x.moveTo(0, yy);
      for (var xx = 0; xx <= 1024; xx += 28) { yy += (Math.random() - 0.5)*4.5; x.lineTo(xx, yy); }
      x.stroke();
    }
    return toTex(c, 2, 1);
  }
  function labelTex(o) {
    var c = cv(768, 384), x = c.getContext('2d');
    x.fillStyle = o.bg; x.fillRect(0, 0, 768, 384);
    x.strokeStyle = o.fg; x.lineWidth = 7; x.strokeRect(26, 26, 716, 332);
    x.textAlign = 'center'; x.fillStyle = o.fg;
    x.font = '500 30px monospace'; x.fillText(o.kicker || '', 384, 108);
    x.font = 'bold 74px monospace';
    var w = (o.name || '').split(' ');
    if (w.length > 1) { x.fillText(w[0], 384, 206); x.fillText(w.slice(1).join(' '), 384, 278); }
    else { x.fillText(o.name || '', 384, 236); }
    x.font = '500 26px monospace'; x.fillText(o.foot || '', 384, 330);
    return toTex(c, 2, 1);
  }

  /* ---------------- prop builders ---------------- */
  function latheFrom(points, scale, maxY) {
    var pts = [], i;
    for (i = 0; i < points.length; i++) {
      if (maxY !== undefined && points[i][1] > maxY) break;
      pts.push(new THREE.Vector2(points[i][0]*scale, points[i][1]));
    }
    var last = pts[pts.length - 1];
    if (maxY !== undefined) { pts.push(new THREE.Vector2(last.x, maxY), new THREE.Vector2(0, maxY)); }
    return new THREE.LatheGeometry(pts, 36);
  }

  function buildBottle(b) {
    var g = new THREE.Group();
    g.position.set(b.x, 0, b.z);
    g.rotation.y = b.yaw || 0;
    var body = new THREE.Mesh(latheFrom(b.profile, 1.0),
      new THREE.MeshStandardMaterial({ color: b.shell, roughness: 0.08, metalness: 0.0,
        transparent: true, opacity: pick(b.shellOpacity, 0.52), side: THREE.DoubleSide, depthWrite: false }));
    g.add(body);
    var inner = new THREE.Mesh(latheFrom(b.profile, 0.9, b.fill),
      new THREE.MeshStandardMaterial({ color: b.liquid, roughness: 0.25, metalness: 0.0,
        transparent: true, opacity: 0.92 }));
    g.add(inner);
    if (b.label) {
      var lab = new THREE.Mesh(new THREE.CylinderGeometry(b.labelR, b.labelR, b.labelH, 36, 1, true),
        new THREE.MeshStandardMaterial({ map: labelTex(b.label), roughness: 0.72, metalness: 0.0, side: THREE.DoubleSide }));
      lab.position.y = b.labelY + b.labelH/2;
      g.add(lab);
    }
    var cap = new THREE.Mesh(new THREE.CylinderGeometry(0.0215, 0.0215, 0.026, 20),
      new THREE.MeshStandardMaterial({ color: b.cap, roughness: 0.35, metalness: 0.55 }));
    cap.position.y = b.mouthY + 0.011;
    g.add(cap);
    g.traverse(function (o) { if (o.isMesh && o.material.opacity > 0.9) o.castShadow = true; });
    return { cfg: b, group: g, inner: inner,
             home: { pos: new V3(b.x, 0, b.z), quat: new QT().setFromEuler(new THREE.Euler(0, b.yaw || 0, 0)) } };
  }

  function buildVessel(V) {
    var group = new THREE.Group();
    group.position.set(V.x, 0, V.z);
    var glass = new THREE.Mesh(
      new THREE.LatheGeometry(V.profile.map(function (p) { return new THREE.Vector2(p[0], p[1]); }), 44),
      new THREE.MeshStandardMaterial({ color: pick(V.tint, 0xdcecf2), metalness: 0.0, roughness: 0.03,
        transparent: true, opacity: pick(V.opacity, 0.44), side: THREE.DoubleSide, depthWrite: false }));
    group.add(glass);

    function innerR(y) {
      var t = M.clamp((y - V.base) / (V.rim - V.base), 0, 1);
      return M.lerp(V.rBase, V.rRim, t);
    }
    var liquidMat = new THREE.MeshStandardMaterial({ color: 0xf0c75a, roughness: 0.22, metalness: 0.0, transparent: true, opacity: 0.93 });
    var liquid = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.037, 0.01, 28, 1), liquidMat);
    liquid.visible = false; group.add(liquid);
    var lastH = -1;
    function setLiquid(h) {
      if (h <= V.base + 0.0015) { liquid.visible = false; return; }
      liquid.visible = true;
      if (Math.abs(h - lastH) > 0.0006) {
        lastH = h;
        liquid.geometry.dispose();
        liquid.geometry = new THREE.CylinderGeometry(innerR(h)*0.985, innerR(V.base)*0.985, h - V.base, 28, 1);
      }
      liquid.position.y = V.base + (h - V.base)/2;
    }
    var foam = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.006, 28, 1),
      new THREE.MeshStandardMaterial({ color: 0xfdf0d2, roughness: 0.8, transparent: true, opacity: 0 }));
    foam.visible = false; group.add(foam);

    var ice = [], iceMat = new THREE.MeshStandardMaterial({ color: 0xdcf1ff, roughness: 0.08, metalness: 0.0, transparent: true, opacity: 0.48 });
    for (var i = 0; i < (V.ice || 0); i++) {
      var s = 0.013 + Math.random()*0.009;
      var cube = new THREE.Mesh(new THREE.BoxGeometry(s, s*0.8, s*0.9), iceMat);
      var a = Math.random()*Math.PI*2, r = Math.random()*0.019;
      cube.position.set(Math.cos(a)*r, 0.019 + (i % 3)*0.019, Math.sin(a)*r);
      cube.rotation.set(Math.random(), Math.random(), Math.random());
      cube.userData.y0 = cube.position.y;
      group.add(cube); ice.push(cube);
    }
    return { cfg: V, group: group, innerR: innerR, liquid: liquid, liquidMat: liquidMat,
             setLiquid: setLiquid, foam: foam, ice: ice,
             fillHeight: function (ml) { return V.base + (ml / V.capacity) * V.fillRange; } };
  }

  var TOOLS = {};
  TOOLS.spoon = function (mats) {
    var g = new THREE.Group();
    var stem = new THREE.Mesh(new THREE.CylinderGeometry(0.0035, 0.0042, 0.215, 10), mats.steel);
    stem.position.y = 0.1075; g.add(stem);
    var twist = new THREE.Mesh(new THREE.TorusGeometry(0.0062, 0.0017, 6, 22), mats.steel);
    twist.position.y = 0.13; twist.rotation.x = 0.5; g.add(twist);
    var bowl = new THREE.Mesh(new THREE.SphereGeometry(0.0125, 14, 10), mats.steel);
    bowl.scale.set(1, 0.42, 1.15); bowl.position.y = 0.006; g.add(bowl);
    var knob = new THREE.Mesh(new THREE.SphereGeometry(0.0075, 12, 10), mats.steel);
    knob.position.y = 0.215; g.add(knob);
    return g;
  };
  TOOLS.pick = function (mats, o) {
    o = o || {};
    var g = new THREE.Group();
    var stick = new THREE.Mesh(new THREE.CylinderGeometry(0.0022, 0.0022, 0.1, 8),
      new THREE.MeshStandardMaterial({ color: 0xe6d7b4, roughness: 0.8 }));
    stick.position.y = 0.05; g.add(stick);
    var wedge = new THREE.Mesh(new THREE.CylinderGeometry(0.026, 0.026, 0.012, 16, 1, false, 0, Math.PI*0.62),
      new THREE.MeshStandardMaterial({ color: pick(o.fruit, 0xf5cf4c), roughness: 0.55 }));
    wedge.position.set(0, 0.072, 0); wedge.rotation.set(Math.PI/2, 0, 0.5); g.add(wedge);
    var rind = new THREE.Mesh(new THREE.TorusGeometry(0.026, 0.0035, 6, 14, Math.PI*0.62),
      new THREE.MeshStandardMaterial({ color: pick(o.rind, 0xb98b2a), roughness: 0.7 }));
    rind.position.copy(wedge.position); rind.rotation.copy(wedge.rotation); g.add(rind);
    var cherry = new THREE.Mesh(new THREE.SphereGeometry(0.0095, 14, 12),
      new THREE.MeshStandardMaterial({ color: pick(o.berry, 0xb4142c), roughness: 0.28 }));
    cherry.position.set(0.006, 0.047, 0.004); g.add(cherry);
    if (o.parasol !== false) {
      var para = new THREE.Group();
      para.position.set(-0.004, 0.096, 0.002); para.rotation.z = 0.35;
      var ps = new THREE.Mesh(new THREE.CylinderGeometry(0.0012, 0.0012, 0.055, 6),
        new THREE.MeshStandardMaterial({ color: 0xd8c9a4, roughness: 0.85 }));
      ps.position.y = 0.012; para.add(ps);
      var canopy = new THREE.Mesh(new THREE.ConeGeometry(0.028, 0.017, 10, 1, true),
        new THREE.MeshStandardMaterial({ color: pick(o.parasolColor, 0xef5f8a), roughness: 0.65, side: THREE.DoubleSide }));
      canopy.position.y = 0.045; para.add(canopy);
      g.add(para);
    }
    return g;
  };

  /* ---------------- robot hand + arm ---------------- */
  function makeHand(side, mats, rig) {
    var s = (side === 'left') ? -1 : 1;
    var g = new THREE.Group();
    var palm = new THREE.Mesh(new THREE.BoxGeometry(0.082, 0.026, 0.092), mats.shell);
    palm.position.set(0, 0, -0.03); g.add(palm);
    var plate = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.009, 0.072), mats.metal);
    plate.position.set(0, 0.016, -0.034); g.add(plate);
    var core = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.006, 0.03), mats.servo);
    core.position.set(0, 0.021, -0.034); g.add(core);
    var pad = new THREE.Mesh(new THREE.BoxGeometry(0.066, 0.006, 0.062), mats.rubber);
    pad.position.set(0, -0.015, -0.034); g.add(pad);
    var collar = new THREE.Mesh(new THREE.CylinderGeometry(0.031, 0.027, 0.03, 20), mats.metal);
    collar.rotation.x = Math.PI/2; collar.position.set(0, 0, 0.016); g.add(collar);
    var ring = new THREE.Mesh(new THREE.TorusGeometry(0.0315, 0.0035, 8, 22), mats.servo);
    ring.position.set(0, 0, 0.004); g.add(ring);

    var fingers = [];
    function finger(x, z, scale) {
      var root = new THREE.Group(); root.position.set(x, 0.001, z);
      var servo = new THREE.Mesh(new THREE.CylinderGeometry(0.0105, 0.0105, 0.022, 12), mats.servo);
      servo.rotation.z = Math.PI/2; root.add(servo);
      var prox = new THREE.Mesh(new THREE.BoxGeometry(0.019, 0.019, 0.042*scale), mats.metal);
      prox.position.z = -0.021*scale; root.add(prox);
      var mid = new THREE.Group(); mid.position.z = -0.042*scale;
      var knuckle = new THREE.Mesh(new THREE.CylinderGeometry(0.0085, 0.0085, 0.019, 10), mats.shell);
      knuckle.rotation.z = Math.PI/2; mid.add(knuckle);
      var dist = new THREE.Mesh(new THREE.BoxGeometry(0.016, 0.016, 0.032*scale), mats.metal);
      dist.position.z = -0.016*scale; mid.add(dist);
      var tip = new THREE.Mesh(new THREE.SphereGeometry(0.0085, 10, 8), mats.rubber);
      tip.position.z = -0.032*scale; mid.add(tip);
      root.add(mid); g.add(root);
      fingers.push({ root: root, mid: mid });
    }
    finger(-0.027, -0.070, 1.0);
    finger( 0.000, -0.072, 1.08);
    finger( 0.027, -0.068, 0.96);

    // Fingers point along -z and the palm faces -y, so a right hand's thumb is on
    // its -x side (and a left hand's on +x), like a real hand held palm down.
    var ts = -s;
    var thumb = new THREE.Group();
    thumb.position.set(0.040*ts, -0.004, -0.026);
    thumb.rotation.set(0, -0.55*ts, -0.35*ts);
    var tServo = new THREE.Mesh(new THREE.CylinderGeometry(0.011, 0.011, 0.022, 12), mats.servo);
    tServo.rotation.z = Math.PI/2; thumb.add(tServo);
    var tProx = new THREE.Mesh(new THREE.BoxGeometry(0.019, 0.019, 0.034), mats.metal);
    tProx.position.z = -0.017; thumb.add(tProx);
    var tMid = new THREE.Group(); tMid.position.z = -0.034;
    var tDist = new THREE.Mesh(new THREE.BoxGeometry(0.0165, 0.0165, 0.028), mats.metal);
    tDist.position.z = -0.014; tMid.add(tDist);
    var tTip = new THREE.Mesh(new THREE.SphereGeometry(0.0085, 10, 8), mats.rubber);
    tTip.position.z = -0.028; tMid.add(tTip);
    thumb.add(tMid); g.add(thumb);
    g.traverse(function (o) { if (o.isMesh) o.castShadow = true; });

    var forearm = new THREE.Mesh(new THREE.CylinderGeometry(0.020, 0.030, 1, 16), mats.metal);
    forearm.castShadow = true;
    var upper = new THREE.Mesh(new THREE.CylinderGeometry(0.034, 0.044, 1, 16), mats.shell);
    upper.castShadow = true;
    var bands = [0, 1].map(function () { return new THREE.Mesh(new THREE.TorusGeometry(0.026, 0.0038, 8, 20), mats.servo); });
    var elbow = new THREE.Mesh(new THREE.SphereGeometry(0.040, 18, 14), mats.shell);

    return {
      side: side, group: g, parts: [g, forearm, upper, elbow].concat(bands),
      fingers: fingers, thumb: thumb, thumbMid: tMid,
      forearm: forearm, upper: upper, bands: bands, elbow: elbow,
      shoulder: new V3(rig.shoulder[0]*s, rig.shoulder[1], rig.shoulder[2]),
      pole: new V3(rig.pole[0]*s, rig.pole[1], rig.pole[2]).normalize(),
      state: { pos: new V3(), quat: new QT(), curl: 0, init: false },
      setCurl: function (c) {
        for (var i = 0; i < this.fingers.length; i++) {
          this.fingers[i].root.rotation.x = -c*1.18 - 0.06;
          this.fingers[i].mid.rotation.x  = -c*1.30;
        }
        this.thumb.rotation.y = (-0.55 + c*0.62)*ts;
        this.thumb.rotation.x = -c*0.42;
        this.thumbMid.rotation.x = -c*0.55;
      }
    };
  }

  /* ---------------- timeline ---------------- */
  var PHASES = {
    pour:  [['reach', 1.2], ['grip', 0.32], ['lift', 1.05], ['pour', 2.2], ['up', 0.55], ['back', 1.0], ['rel', 0.3]],
    stir:  [['reach', 1.0], ['grip', 0.3], ['stir', 3.6], ['out', 0.5], ['back', 0.9], ['rel', 0.3]],
    place: [['reach', 1.0], ['grip', 0.3], ['place', 1.35], ['settle', 0.4], ['rel', 0.3], ['back', 0.65]],
    serve: [['reach', 0.9], ['grip', 0.25], ['push', 1.0], ['rel', 0.25], ['drop', 0.9]]
  };
  function chain(t0, parts) {
    var s = {}, t = t0;
    for (var i = 0; i < parts.length; i++) { s[parts[i][0]] = { a: t, b: t + parts[i][1], d: parts[i][1] }; t += parts[i][1]; }
    return { seg: s, t0: t0, t1: t };
  }

  /* ================= plan mode =================
     cfg.plan = { actions: [{ kind, hand, target, t0, dur, step, gap }] } plays a
     compiled skill chain instead of a hand-written recipe. Actions may overlap
     in time (one per hand), which is how a parallel schedule shows.
     kinds: locate, grasp, move, pour, release, stir, blend, wipe, unknown, gap.
     Props come from the catalog below by target name. The world is simulated
     once at create time; each frame replays the end state of every finished
     action and interpolates the running ones, so seeking is exact. */

  // Target name -> prop kind. First match wins; anything else is a small box.
  var PROP_KINDS = [
    ['blender', /blend|jug|mixer/],
    ['shaker',  /shaker|cocktail/],
    ['scoop',   /scoop|ladle/],
    ['glass',   /glass|cup|mug|tumbler|bowl|vessel|pitcher/],
    ['bottle',  /bottle|juice|milk|water|wine|beer|soda|cola|oil|syrup|vodka|rum|gin|whisk(e)?y|tonic|lemonade|liquor|carton|cream|yog/],
    ['cloth',   /cloth|towel|rag|sponge|napkin|wipe|tissue/],
    ['fruit',   /banana|berr|apple|orange|lemon|lime|fruit|mango|kiwi|peach|pear|grape|ice|tomato|carrot|egg|avocado|pineapple|melon|cherr|nut/],
    ['spoon',   /spoon|stirrer/],
    ['table',   /^$|table|counter|surface|desk|worktop/],
    ['station', /shelf|sink|bin|trash|fridge|cabinet|cupboard|drawer|rack|tray|coaster|dishwasher|station|plate|board/]
  ];
  // A part of a known thing ("blender lid", "banana peel", "lid of the jar") is
  // not that thing: it is drawn as a stand-in, like any other unknown name.
  var PART = '(?:lid|cap|cover|button|switch|knob|dial|lever|handle|peel|skin|rind|shell|pit|core|stem|seed|' +
             'cork|spout|nozzle|plug|cord|blade|label|sticker|wrapper)(?:s|es)?';
  var PART_RE = new RegExp('(?:^|\\s)' + PART + '$|^' + PART + ' of\\b');
  function propKind(name) {
    var n = String(name || '').toLowerCase().trim();
    if (PART_RE.test(n)) return 'box';
    for (var i = 0; i < PROP_KINDS.length; i++) if (PROP_KINDS[i][1].test(n)) return PROP_KINDS[i][0];
    return 'box';
  }

  // Where each kind stands on the counter, [x, z]. Picked by the side of the
  // hand that touches the prop first, so arms rarely cross.
  var SLOTS = {
    glass:   [[0.1, -0.05], [-0.1, -0.05], [0.0, -0.14]],
    blender: [[0.0, -0.33], [-0.2, -0.36]],
    shaker:  [[0.0, -0.22], [0.12, -0.3]],
    scoop:   [[0.24, -0.2], [-0.24, -0.2]],
    bottle:  [[-0.22, -0.30], [0.22, -0.30], [-0.33, -0.16], [0.33, -0.16], [-0.12, -0.42], [0.12, -0.42]],
    fruit:   [[-0.25, -0.08], [0.25, -0.08], [-0.14, -0.20], [0.15, -0.18], [-0.33, -0.28], [0.35, -0.06]],
    cloth:   [[-0.20, 0.03], [0.20, 0.03]],
    spoon:   [[0.21, 0.07], [-0.21, 0.07]],
    box:     [[-0.15, -0.13], [0.16, -0.12], [-0.30, -0.01], [0.30, -0.01], [0.0, -0.26]],
    station: [[0.36, -0.42], [-0.38, -0.42], [0.0, -0.48]]
  };
  var TABLE_SPOTS = [[0.31, 0.02], [0.36, -0.12], [0.19, 0.07]];   // mirrored for the left hand

  var PROPS = {};
  function lathe(points, segs) {
    return new THREE.LatheGeometry(points.map(function (p) { return new THREE.Vector2(p[0], p[1]); }), segs || 28);
  }
  function plainMat(c, o) {
    var m = { color: c, roughness: 0.82, metalness: 0.0 };
    for (var k in (o || {})) m[k] = o[k];
    return new THREE.MeshStandardMaterial(m);
  }
  function shellMat() {
    return plainMat(0xe2e2e2, { roughness: 0.12, transparent: true, opacity: 0.4, side: THREE.DoubleSide, depthWrite: false });
  }
  function addLiquid(P, r, base, max) {
    var geo = new THREE.CylinderGeometry(r, r*0.92, 1, 24); geo.translate(0, 0.5, 0);
    P.liqMat = plainMat(0x6a6a6a, { roughness: 0.3, transparent: true, opacity: 0.92 });
    P.liquid = new THREE.Mesh(geo, P.liqMat);
    P.liquid.position.y = base; P.liquid.visible = false;
    P.group.add(P.liquid);
    P.liqBase = base; P.liqMax = max; P.liqR = r;
    P.chunkMeshes = [];
    for (var k = 0; k < 6; k++) {
      var c = new THREE.Mesh(new THREE.IcosahedronGeometry(0.017, 0), plainMat(0x3a3a3a));
      c.visible = false; P.group.add(c); P.chunkMeshes.push(c);
    }
  }
  PROPS.bottle = function (P) {
    P.group.add(new THREE.Mesh(lathe([[0, 0], [0.031, 0], [0.032, 0.012], [0.032, 0.15], [0.024, 0.18],
      [0.015, 0.196], [0.014, 0.226], [0.016, 0.236], [0, 0.236]]), shellMat()));
    var cap = new THREE.Mesh(new THREE.CylinderGeometry(0.0165, 0.0165, 0.02, 16), plainMat(0x555555));
    cap.position.y = 0.238; P.group.add(cap);
    addLiquid(P, 0.028, 0.006, 0.15);
    P.fill0 = 0.85; P.cap = 0.6; P.height = 0.25; P.mouthY = 0.24; P.pourer = true; P.container = true;
    P.hold = { mode: 'side', y: 0.17, reach: -0.1, tilt: 0.22, curl: 0.86 };
    // 'a large bottle' is the thing being filled: bigger, and empty to start.
    if (/large|big|empty|carafe|decanter/.test(P.name)) {
      var k = 1.3;
      P.group.children.forEach(function (c) { c.scale.multiplyScalar(k); c.position.multiplyScalar(k); });
      P.fill0 = 0; P.cap = 1.2; P.height *= k; P.mouthY *= k; P.liqBase *= k; P.liqMax *= k;
      P.hold.y *= k; P.hold.reach = -0.11;
    }
  };
  PROPS.shaker = function (P) {
    P.group.add(new THREE.Mesh(lathe([[0, 0], [0.036, 0], [0.044, 0.14], [0.041, 0.14],
      [0.033, 0.006], [0, 0.006]], 32), plainMat(0xb0b0b0, { roughness: 0.35, metalness: 0.5, side: THREE.DoubleSide })));
    var lid = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.044, 0.05, 24), plainMat(0x8a8a8a, { metalness: 0.5, roughness: 0.4 }));
    lid.position.y = 0.165; P.group.add(lid);
    addLiquid(P, 0.036, 0.006, 0.12);
    P.fill0 = 0; P.cap = 0.8; P.height = 0.19; P.mouthY = 0.14; P.pourer = true; P.container = true;
    P.hold = { mode: 'side', y: 0.08, reach: -0.122, tilt: 0.12, curl: 0.84 };
  };
  PROPS.glass = function (P) {
    if (/bowl/.test(P.name)) {
      P.group.add(new THREE.Mesh(lathe([[0, 0], [0.04, 0], [0.072, 0.055], [0.068, 0.055],
        [0.037, 0.006], [0, 0.006]], 36), plainMat(0xc8c8c8, { side: THREE.DoubleSide })));
      addLiquid(P, 0.05, 0.006, 0.04);
      P.fill0 = 0; P.cap = 0.6; P.height = 0.055; P.mouthY = 0.055; P.pourer = true; P.container = true;
      P.hold = { mode: 'side', y: 0.03, reach: -0.15, tilt: 0.1, curl: 0.7 };
      return;
    }
    P.group.add(new THREE.Mesh(lathe([[0, 0], [0.034, 0], [0.036, 0.004], [0.042, 0.11],
      [0.039, 0.11], [0.033, 0.009], [0, 0.009]], 32), shellMat()));
    addLiquid(P, 0.036, 0.009, 0.092);
    P.fill0 = 0; P.cap = 0.3; P.height = 0.11; P.mouthY = 0.11; P.pourer = true; P.container = true;
    P.hold = { mode: 'side', y: 0.055, reach: -0.122, tilt: 0.1, curl: 0.8 };
  };
  PROPS.scoop = function (P) {
    var cup = new THREE.Mesh(lathe([[0, 0], [0.028, 0], [0.032, 0.04], [0.029, 0.04], [0.025, 0.004], [0, 0.004]], 24),
      plainMat(0xa0a0a0, { metalness: 0.4, roughness: 0.4, side: THREE.DoubleSide }));
    P.group.add(cup);
    var handle = new THREE.Mesh(new THREE.CylinderGeometry(0.007, 0.007, 0.11, 10), plainMat(0x6a6a6a));
    handle.rotation.x = Math.PI/2; handle.position.set(0, 0.02, 0.085); P.group.add(handle);
    addLiquid(P, 0.026, 0.004, 0.034);
    P.fill0 = 0.8; P.cap = 0.15; P.height = 0.04; P.mouthY = 0.04; P.pourer = true; P.container = true;
    P.hold = { mode: 'side', y: 0.02, reach: -0.17, tilt: 0.05, curl: 0.85 };
  };
  PROPS.blender = function (P, scene) {
    // The motor base stays put; the jug on it is the prop that moves.
    var base = new THREE.Group();
    var body = new THREE.Mesh(new THREE.BoxGeometry(0.13, 0.09, 0.13), plainMat(0x7c7c7c));
    body.position.y = 0.045; body.castShadow = true; base.add(body);
    var btn = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 0.01, 16), plainMat(0x3c3c3c));
    btn.rotation.x = Math.PI/2; btn.position.set(0, 0.045, 0.067); base.add(btn);
    scene.add(base);
    P.base = base; P.button = btn;
    P.group.add(new THREE.Mesh(lathe([[0, 0], [0.042, 0], [0.056, 0.17], [0.052, 0.17],
      [0.039, 0.007], [0, 0.007]], 32), shellMat()));
    var rim = new THREE.Mesh(new THREE.TorusGeometry(0.055, 0.004, 6, 32), plainMat(0x5a5a5a));
    rim.rotation.x = Math.PI/2; rim.position.y = 0.17; P.group.add(rim);
    var handle = new THREE.Mesh(new THREE.BoxGeometry(0.012, 0.11, 0.02), plainMat(0x5a5a5a));
    handle.position.set(0.064, 0.09, 0); P.group.add(handle);
    addLiquid(P, 0.046, 0.007, 0.15);
    P.fill0 = 0; P.cap = 1.0; P.height = 0.17; P.mouthY = 0.17; P.pourer = true; P.container = true;
    P.lift = 0.09;   // the jug sits on the base
    P.hold = { mode: 'side', y: 0.075, reach: -0.132, tilt: 0.12, curl: 0.82 };
  };
  PROPS.fruit = function (P) {
    var m = plainMat(0x8f8f8f, { roughness: 0.6 }), mesh;
    if (/banana/.test(P.name)) {
      var R = 0.07;
      mesh = new THREE.Mesh(new THREE.TorusGeometry(R, 0.016, 8, 18, 1.4), m);
      mesh.rotation.z = -Math.PI/2 - 0.7; mesh.position.y = R;   // arc midpoint to the origin
      var flat = new THREE.Group(); flat.rotation.x = -Math.PI/2; flat.add(mesh);
      flat.position.y = 0.016; P.group.add(flat);
      P.height = 0.032;
    } else {
      var r = /berr|cherr|grape|nut/.test(P.name) ? 0.02 : 0.032;
      mesh = new THREE.Mesh(new THREE.SphereGeometry(r, 16, 12), m);
      mesh.scale.y = /straw/.test(P.name) ? 1.2 : 1; mesh.position.y = r*mesh.scale.y;
      P.group.add(mesh);
      P.height = 2*r*mesh.scale.y;
    }
    mesh.castShadow = true;
    P.hold = { mode: 'top', y: P.height*0.55, curl: 0.62 };
  };
  PROPS.cloth = function (P) {
    var c = new THREE.Mesh(new THREE.BoxGeometry(0.13, 0.01, 0.095), plainMat(0xa6a6a6, { roughness: 1 }));
    c.position.y = 0.005; c.rotation.y = 0.15; c.castShadow = true; P.group.add(c);
    P.height = 0.01;
    P.hold = { mode: 'flat', y: 0.01, curl: 0.42 };
  };
  PROPS.spoon = function (P, scene, mats) {
    P.group.add(TOOLS.spoon(mats));
    P.homeQuat = eulerQ([0, 0.4, Math.PI/2]); P.homeY = 0.008;
    P.height = 0.02;
    P.hold = { mode: 'side', y: 0.175, reach: -0.094, tilt: 0.2, curl: 0.86 };
  };
  PROPS.station = function (P) {
    var s = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.1, 0.14), plainMat(0x767676));
    s.position.y = 0.05; s.castShadow = true; s.receiveShadow = true; P.group.add(s);
    P.height = 0.1; P.fixed = true;
    P.hold = { mode: 'side', y: 0.02, reach: -0.1, tilt: 0, curl: 0.6 };
  };
  PROPS.box = function (P) {
    var b = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.05, 0.05), plainMat(0x9a9a9a));
    b.position.y = 0.025; b.castShadow = true; P.group.add(b);
    P.height = 0.05;
    P.hold = { mode: 'side', y: 0.025, reach: -0.088, tilt: 0.1, curl: 0.72 };
  };
  // A model-designed stand-in: a list of primitives (see app/props.py). Data
  // only -- shapes, sizes, positions, grey shades -- assembled here.
  PROPS.generated = function (P) {
    var spec = P.spec || { parts: [], hold: { mode: 'side', y: 0.025 }, height_m: 0.05 };
    spec.parts.forEach(function (q) {
      var s = q.size, geo;
      if (q.shape === 'cylinder') geo = new THREE.CylinderGeometry(s[0], s[1], s[2], 24);
      else if (q.shape === 'sphere') geo = new THREE.SphereGeometry(s[0], 18, 14);
      else if (q.shape === 'cone') geo = new THREE.ConeGeometry(s[0], s[1], 20);
      else if (q.shape === 'torus') geo = new THREE.TorusGeometry(s[0], s[1], 8, 24);
      else geo = new THREE.BoxGeometry(s[0], s[1], s[2]);
      var g = Math.round(q.shade * 255);
      var m = new THREE.Mesh(geo, plainMat((g << 16) | (g << 8) | g, { roughness: 0.7 }));
      m.position.set(q.pos[0], q.pos[1], q.pos[2]);
      m.rotation.set(q.rot[0], q.rot[1], q.rot[2]);
      m.castShadow = true;
      P.group.add(m);
    });
    P.height = spec.height_m;
    P.fixed = !!spec.fixed;
    var mode = spec.hold.mode;
    P.hold = mode === 'top' ? { mode: 'top', y: spec.hold.y, curl: 0.62 }
           : mode === 'flat' ? { mode: 'flat', y: spec.hold.y, curl: 0.42 }
           : { mode: 'side', y: spec.hold.y, reach: -0.1, tilt: 0.1, curl: 0.72 };
  };
  PROPS.patch = function (P) {
    P.mat = plainMat(0x4c4c4c, { transparent: true, opacity: 0.6, depthWrite: false });
    var m = new THREE.Mesh(new THREE.PlaneGeometry(0.2, 0.12), P.mat);
    m.rotation.x = -Math.PI/2; m.position.y = 0.0015; m.receiveShadow = true; P.group.add(m);
    P.height = 0; P.fill0 = 1; P.fixed = true;
  };

  function buildPlan(plan, scene, mats, K) {
    function copyOf(a, extra) { var o = {}, k; for (k in a) o[k] = a[k]; for (k in extra) o[k] = extra[k]; return o; }
    // 'place' is a carry followed by a release, played as one step.
    var raw = [];
    (plan.actions || []).forEach(function (a) {
      if (a.kind !== 'place') { raw.push(a); return; }
      raw.push(copyOf(a, { kind: 'move', dur: a.dur*0.6 }),
               copyOf(a, { kind: 'release', t0: a.t0 + a.dur*0.6, dur: a.dur*0.4 }));
    });
    var acts = raw.map(function (a, i) {
      var o = copyOf(a, {});
      o.order = i; o.t1 = a.t0 + a.dur;
      return o;
    }).sort(function (a, b) { return a.t0 - b.t0 || a.order - b.order; });
    acts.forEach(function (a, i) { a.idx = i; });
    function nextOf(a) {
      for (var i = a.idx + 1; i < acts.length; i++) if (acts[i].hand === a.hand) return acts[i];
      return null;
    }
    var onStation = {}, onTop = {}, onSide = {};
    // A step that fixes the held thing where it is: the hand lets go of it there.
    var FASTEN = /(^|[^a-z])(attach|affix|fasten|fix|mount|screw|bolt|clip|snap|join|connect|insert|plug|glue|stick|tape|install|assembl|fit|hook|hang|weld|nail)/i;
    function fastens(a) { return !!a && (a.kind === 'gap' || a.kind === 'unknown') && FASTEN.test(a.label || ''); }

    /* --- props --- */
    var props = {}, list = [], used = {}, ghosts = [];
    var sim = {}, init = {}, W = {};      // prop states: simulation, t = 0, this frame
    function sgn(side) { return side === 'left' ? -1 : 1; }
    function slotFor(kind, side) {
      var want = sgn(side), pools = [SLOTS[kind] || SLOTS.box, SLOTS.box, SLOTS.fruit, SLOTS.bottle];
      for (var p = 0; p < pools.length; p++) {
        var pool = pools[p], best = null;
        for (var i = 0; i < pool.length; i++) {
          var key = pool[i].join(','); if (used[key]) continue;
          if (pool[i][0]*want >= 0) { best = pool[i]; break; }
          if (!best) best = pool[i];
        }
        if (best) { used[best.join(',')] = true; return best; }
      }
      var n = list.length;   // ran out of slots: a loose row at the back
      return [-0.3 + (n % 7)*0.1, -0.5];
    }
    function addProp(name, kind, side, at) {
      var P = { id: 'p' + list.length, name: name, kind: kind, group: new THREE.Group(),
                fill0: 0, cap: 0.5, lift: 0, height: 0.05 };
      if (kind === 'generated') P.spec = (plan.specs || {})[norm(name)];
      (PROPS[kind] || PROPS.box)(P, scene, mats);
      var xz = at || slotFor(kind, side);
      P.home = { pos: new V3(xz[0], P.homeY !== undefined ? P.homeY : P.lift, xz[1]),
                 quat: P.homeQuat || new QT() };
      if (P.base) P.base.position.set(xz[0], 0, xz[1]);
      P.box = new THREE.Box3().setFromObject(P.group);     // its bounds, about its own origin
      if (P.box.isEmpty()) P.box.set(new V3(-0.025, 0, -0.025), new V3(0.025, P.height || 0.05, 0.025));
      P.group.traverse(function (o) { if (o.isMesh && !(o.material.transparent && o.material.opacity < 0.5)) o.castShadow = true; });
      scene.add(P.group);
      sim[P.id] = St(P); init[P.id] = St(P); W[P.id] = St(P);
      list.push(P);
      if (name) (props[name] = props[name] || []).push(P);
      return P;
    }
    function norm(n) { return String(n || '').toLowerCase().trim(); }
    // The first copy still in play. Once a loose thing has gone into a
    // container, asking for it again means the next one: a second strawberry
    // appears beside where the first stood (it was waiting there all along).
    function propOf(name) {
      var all = props[norm(name)];
      if (!all) return null;
      for (var i = 0; i < all.length; i++) if (!sim[all[i].id].hidden) return all[i];
      var first = all[0], j = all.length;
      if (first.kind !== 'fruit' && first.kind !== 'box') return all[j - 1];
      var s = first.home.pos.x < 0 ? -1 : 1;
      return addProp(first.name, first.kind, null,
        [first.home.pos.x - 0.045*j*s, first.home.pos.z - 0.035*j]);
    }
    // A target is a prop unless it names a place on the counter.
    acts.forEach(function (a) {
      var n = norm(a.target);
      if (!n || props[n] || a.kind === 'gap') return;
      var kind = propKind(n);
      // A kitchen has one blender: "blender", "blender jar" and "blender base"
      // are all that one prop (its parts were made stand-ins above).
      var B = kind === 'blender' && list.filter(function (p) { return p.kind === 'blender'; })[0];
      if (B) { props[n] = props[B.name]; return; }
      // No builder for this name: use the model's design when the page fetched one.
      if (kind === 'box' && plan.specs && plan.specs[n]) kind = 'generated';
      if (kind !== 'table') addProp(n, kind, a.hand);
    });
    var spoon = null;
    if (acts.some(function (a) { return a.kind === 'stir'; })) {
      spoon = list.filter(function (p) { return p.kind === 'spoon'; })[0] || addProp('', 'spoon', 'right');
    }

    /* --- poses --- */
    var GRASP = K.GRASP;
    function yawQ(side, pitch) { return new QT().setFromEuler(new THREE.Euler(pitch, 0.35*sgn(side), 0, 'YXZ')); }
    function holdAt(P, pos, quat, side) {
      var h = P.hold, q, p;
      if (h.mode === 'side') {
        q = quat.clone().multiply(K.gripQuat(side, h.tilt));
        p = new V3(0, h.y, 0).applyQuaternion(quat).add(pos);
        return { pos: p.sub(new V3(GRASP.x, GRASP.y, h.reach).applyQuaternion(q)), quat: q, curl: h.curl };
      }
      var flat = h.mode === 'flat';
      q = yawQ(side, flat ? -0.12 : -0.95);
      p = pos.clone(); p.y += h.y;
      return { pos: p.sub(new V3(0, flat ? -0.02 : -0.022, flat ? -0.07 : -0.088).applyQuaternion(q)),
               quat: q, curl: h.curl };
    }
    function hoverAt(point, side) {
      var q = yawQ(side, -0.5);
      return { pos: point.clone().add(new V3(0, 0.07, 0)).sub(GRASP.clone().applyQuaternion(q)), quat: q, curl: 0.3 };
    }
    function relOf(st, pose) {
      var inv = st.quat.clone().invert();
      return { p: pose.pos.clone().sub(st.pos).applyQuaternion(inv), q: inv.multiply(pose.quat), curl: pose.curl };
    }
    function carried(st, rel) {
      return { pos: rel.p.clone().applyQuaternion(st.quat).add(st.pos), quat: st.quat.clone().multiply(rel.q), curl: rel.curl };
    }
    function topOf(P, st) { return st.pos.clone().add(new V3(0, P.height, 0)); }
    // P's bounds turned by quat, still about its origin, on world axes.
    function boundsOf(P, quat) {
      var b = P.box, out = new THREE.Box3();
      for (var i = 0; i < 8; i++)
        out.expandByPoint(new V3(i & 1 ? b.max.x : b.min.x, i & 2 ? b.max.y : b.min.y, i & 4 ? b.max.z : b.min.z)
                            .applyQuaternion(quat));
      return out;
    }
    function withCurl(pose, c) { return { pos: pose.pos, quat: pose.quat, curl: c }; }

    /* --- world state --- */
    function St(P) { return { pos: P.home.pos.clone(), quat: P.home.quat.clone(), fill: P.fill0,
                              chunks: 0, blend: 0, swirl: 0, fold: 0, hidden: false }; }
    function cp(dst, src) {
      dst.pos.copy(src.pos); dst.quat.copy(src.quat); dst.fill = src.fill; dst.chunks = src.chunks;
      dst.blend = src.blend; dst.swirl = src.swirl; dst.fold = src.fold; dst.hidden = src.hidden; return dst;
    }
    function clone(s) { return cp({ pos: new V3(), quat: new QT() }, s); }
    // Things fastened to a prop ride along with it from then on: D.id -> [{ D, P, p, q }],
    // P's place and turn in D's frame. Picking P up again takes it off.
    var riders = {};
    function detach(P) {
      for (var id in riders) riders[id] = riders[id].filter(function (r) { return r.P !== P; });
    }
    function attach(P, D) {
      detach(P);
      var ds = sim[D.id], ps = sim[P.id], inv = ds.quat.clone().invert();
      (riders[D.id] = riders[D.id] || []).push({ D: D, P: P,
        p: ps.pos.clone().sub(ds.pos).applyQuaternion(inv), q: inv.multiply(ps.quat) });
    }
    // The riders of the props in `moved`, and theirs, parents first.
    function ridersOf(moved) {
      var out = [];
      (function walk(ps) {
        ps.forEach(function (D) {
          (riders[D.id] || []).forEach(function (r) {
            if (out.indexOf(r) >= 0 || moved.indexOf(r.P) >= 0) return;
            out.push(r); walk([r.P]);
          });
        });
      })(moved);
      return out;
    }
    function ride(r, ds, rs) {     // rs: where r.P is when its parent is at ds
      rs.pos.copy(r.p).applyQuaternion(ds.quat).add(ds.pos);
      rs.quat.copy(ds.quat).multiply(r.q);
      if (ds.hidden) rs.hidden = true;
    }
    var hs = {
      left:  { pose: K.restPose('left'),  hold: null, rel: null, over: null, spot: 0 },
      right: { pose: K.restPose('right'), hold: null, rel: null, over: null, spot: 0 }
    };
    function spotFor(side) {
      var s = TABLE_SPOTS[hs[side].spot++ % TABLE_SPOTS.length];
      return new V3(s[0]*sgn(side), 0, s[1]);
    }

    /* --- transient visuals: streams, scan rings, placeholders --- */
    var fx = {};
    ['left', 'right'].forEach(function (side) {
      var tube = new THREE.Mesh(new THREE.CylinderGeometry(0.005, 0.007, 1, 10, 1, true),
        plainMat(0x6a6a6a, { transparent: true, opacity: 0.9, side: THREE.DoubleSide }));
      var ring = new THREE.Mesh(new THREE.TorusGeometry(1, 0.05, 6, 40), plainMat(0x3a3a3a, { transparent: true }));
      ring.rotation.x = Math.PI/2;
      tube.visible = ring.visible = false;
      scene.add(tube, ring);
      fx[side] = { tube: tube, ring: ring };
    });
    function placeholder(dashed) {
      // dashed: a skill that does not exist yet; solid: one this kit cannot draw
      var geo = new THREE.EdgesGeometry(new THREE.BoxGeometry(0.07, 0.07, 0.07));
      var mat = dashed
        ? new THREE.LineDashedMaterial({ color: 0x222222, dashSize: 0.01, gapSize: 0.007 })
        : new THREE.LineBasicMaterial({ color: 0x2e2e2e });
      var box = new THREE.LineSegments(geo, mat);
      if (dashed) box.computeLineDistances();
      box.visible = false; scene.add(box); ghosts.push(box);
      return box;
    }

    /* --- the choreography of each skill --- */
    var DO = {};
    function hide(o) { o.visible = false; }

    DO.locate = function (a, h) {
      var P = propOf(a.target), start = h.pose;
      var point = P ? topOf(P, sim[P.id]) : spotFor(a.hand).setY(0);
      var radius = P ? (P.kind === 'blender' ? 0.09 : P.kind === 'bottle' || P.kind === 'glass' ? 0.06 : 0.05) : 0.05;
      // look from just above, not from over the top of a tall bottle
      var end = h.hold ? start : hoverAt(point.clone().setY(Math.min(point.y, 0.12)), a.hand);
      var ringAt = new V3(point.x, 0.003, point.z);
      a.play = function (u, T) {
        T[a.hand] = K.lerpPose(start, end, ease(seg(u, 0, 0.7)));
        var r = fx[a.hand].ring;
        r.visible = true; r.position.copy(ringAt);
        var k = radius*(1.25 - 0.25*easeOut(seg(u, 0, 0.6)));
        r.scale.set(k, k, k*0.6);
        r.material.opacity = Math.sin(Math.PI*u)*0.9;
      };
      a.handEnd = end;
    };

    DO.grasp = function (a, h) {
      var P = propOf(a.target);
      if (P && h.hold === P) {                     // already holding it: settle the grip
        var g = carried(sim[P.id], h.rel);
        a.play = function (u, T, snap) { T[a.hand] = withCurl(g, M.lerp(g.curl, 0.45, Math.sin(Math.PI*u))); snap[a.hand] = true; };
        a.handEnd = g; return;
      }
      var other = hs[a.hand === 'left' ? 'right' : 'left'];
      if (!P || P.fixed || h.hold || sim[P.id].hidden || other.hold === P) return DO.unknown(a, h);
      var st = sim[P.id], start = h.pose;
      var gp = holdAt(P, st.pos, st.quat, a.hand);
      var open = withCurl(gp, 0.15);
      var pre = withCurl({ pos: gp.pos.clone().add(new V3(0, 0.05, 0.05)), quat: gp.quat }, 0.15);
      a.play = function (u, T, snap) {
        if (u < 0.55) T[a.hand] = K.lerpPose(start, pre, ease(seg(u, 0, 0.55)));
        else if (u < 0.8) T[a.hand] = K.lerpPose(pre, open, ease(seg(u, 0.55, 0.8)));
        else { T[a.hand] = withCurl(gp, M.lerp(0.15, gp.curl, ease(seg(u, 0.8, 1)))); snap[a.hand] = true; }
      };
      h.hold = P; h.rel = relOf(st, gp); h.over = null; detach(P);
      a.handEnd = gp;
    };

    DO.move = function (a, h) {
      var D = propOf(a.target), start = h.pose;
      if (!h.hold) {
        var end = hoverAt(D ? topOf(D, sim[D.id]) : spotFor(a.hand), a.hand);
        a.play = function (u, T) { T[a.hand] = K.lerpPose(start, end, ease(u)); };
        a.handEnd = end;
        return;
      }
      var H = h.hold, rel = h.rel, from = clone(sim[H.id]), to = clone(from), s = sgn(a.hand);
      var next = nextOf(a), pourNext = !!next && next.kind === 'pour', fastenNext = fastens(next);
      to.quat.copy(H.home.quat);
      h.over = null; h.overY = null; h.atD = null;
      if (D && D === H) {                                   // the jug back onto its own base
        to.pos.copy(H.home.pos); h.over = 'floor';
      } else if (D && D.kind === H.kind && (H.kind === 'glass' || H.kind === 'box') && !pourNext) {
        var dk = sim[D.id];                                 // stack it: cups nest, boxes sit on top
        var top = dk.pos.y + (H.kind === 'glass' ? 0.028 : D.height);
        to.pos.set(dk.pos.x, top + 0.05, dk.pos.z); h.overY = top;
      } else if (D && D.container && H.pourer) {            // stand beside it, ready to pour
        var ds = sim[D.id];
        to.pos.set(ds.pos.x + 0.12*s, ds.pos.y + D.mouthY + 0.03, ds.pos.z + 0.05);
        if (!pourNext) { to.pos.y = 0.04; h.overY = 0; }    // or just set it down next to it
      } else if (D && D.container) {                        // hold it over the opening
        var dc = sim[D.id];
        to.pos.set(dc.pos.x, dc.pos.y + D.mouthY + 0.035, dc.pos.z); h.over = D;
      } else if (D && D.kind === 'station') {               // side by side on the shelf
        var n = onStation[D.id] = (onStation[D.id] || 0) + 1, dst = sim[D.id];
        var off = [0, -0.065, 0.065, -0.035, 0.035][(n - 1) % 5];
        to.pos.set(dst.pos.x + off, dst.pos.y + D.height + 0.05, dst.pos.z + ((n - 1) % 5 > 2 ? 0.035 : 0));
        h.overY = dst.pos.y + D.height;
      } else if (D && D.kind === 'generated' && (fastenNext || (next && next.kind === 'release'))) {
        var dg = sim[D.id], db = boundsOf(D, dg.quat), dc0 = db.getCenter(new V3()), dh = db.getSize(new V3()).multiplyScalar(0.5);
        var hb = boundsOf(H, to.quat), hh = hb.getSize(new V3()).multiplyScalar(0.5);
        var L = dh.x >= dh.z ? 'x' : 'z', N = L === 'x' ? 'z' : 'x';     // D's long side, and across it
        // A fastened thing goes against D's side unless it is big enough to cover D's top (a lid).
        if (fastenNext && Math.max(hh.x, hh.z) < 0.7*Math.min(dh.x, dh.z)) {
          var j = onSide[D.id] = (onSide[D.id] || 0) + 1;
          var slot = [[1, 1], [1, -1], [-1, 1], [-1, -1], [1, 0], [-1, 0]][(j - 1) % 6];
          // turn it so its broadest face meets D's side
          var thin = hh.x <= hh.y && hh.x <= hh.z ? 'x' : hh.y <= hh.z ? 'y' : 'z';
          if (thin !== N && hh[thin] < 0.85*hh[N]) {
            var axis = thin === 'y' ? (L === 'x' ? new V3(1, 0, 0) : new V3(0, 0, 1)) : UP;
            to.quat.premultiply(new QT().setFromAxisAngle(axis, Math.PI/2));
            hb = boundsOf(H, to.quat); hh = hb.getSize(new V3()).multiplyScalar(0.5);
          }
          to.pos.y = dg.pos.y + db.min.y - hb.min.y;
          to.pos[N] = dg.pos[N] + (slot[0] > 0 ? db.max[N] + 0.002 - hb.min[N] : db.min[N] - 0.002 - hb.max[N]);
          to.pos[L] = dg.pos[L] + dc0[L] + slot[1]*Math.max(0, dh[L] - 1.4*hh[L]) - (hb.min[L] + hb.max[L])/2;
        } else {                                            // set on top, side by side if several
          var k = onTop[D.id] = (onTop[D.id] || 0) + 1;
          var room = Math.max(0, dh[L] - hh[L]), off2 = [0, -1, 1, -0.5, 0.5][(k - 1) % 5]*Math.min(room, 2.2*hh[L]);
          var top2 = dg.pos.y + db.max.y - hb.min.y;
          to.pos.set(dg.pos.x + dc0.x - (hb.min.x + hb.max.x)/2, top2, dg.pos.z + dc0.z - (hb.min.z + hb.max.z)/2);
          to.pos[L] += off2;
          if (!fastenNext) { to.pos.y += 0.05; h.overY = top2; }   // release lowers it the last bit
        }
        if (fastenNext) h.atD = D;
      } else if (D) {                                       // next to another thing
        to.pos.copy(sim[D.id].pos).add(new V3(0.1*s, 0.04, 0.04));
      } else {                                              // a free spot on the counter
        to.pos.copy(spotFor(a.hand)).setY(0.04);
      }
      var mid = Math.max(0.06, 0.1 - Math.abs(to.pos.y - from.pos.y));
      a.play = function (u, T, snap) {
        var p = ease(u), w = W[H.id];
        w.pos.lerpVectors(from.pos, to.pos, p); w.pos.y += Math.sin(p*Math.PI)*mid;
        w.quat.copy(from.quat).slerp(to.quat, p);
        T[a.hand] = carried(w, rel); snap[a.hand] = true;
      };
      cp(sim[H.id], to);
      a.touch = [H]; a.handEnd = carried(to, rel);
    };

    DO.pour = function (a, h) {
      var D = propOf(a.target), H = h.hold, rel = h.rel;
      if (!D || !D.container || D === H) {   // pour into whatever container is nearest instead
        D = list.filter(function (p) { return p.container && p !== H && !sim[p.id].hidden; })
          .sort(function (x, y) { return sim[x.id].pos.distanceTo(sim[H ? H.id : x.id].pos) - sim[y.id].pos.distanceTo(sim[H ? H.id : y.id].pos); })[0];
      }
      if (!H || !H.pourer || !D) return DO.unknown(a, h);
      var from = clone(sim[H.id]), ds = sim[D.id];
      var d = new V3(ds.pos.x - from.pos.x, 0, ds.pos.z - from.pos.z);
      if (d.lengthSq() < 1e-6) d.set(-sgn(a.hand), 0, 0);
      d.normalize();
      var tilt = new QT().setFromAxisAngle(new V3().crossVectors(UP, d), H.kind === 'bottle' ? 1.95 : 1.62);
      var pq = tilt.multiply(from.quat);
      var mouth = new V3(ds.pos.x, ds.pos.y + D.mouthY + 0.05, ds.pos.z).addScaledVector(d, -0.018);
      var pp = mouth.clone().sub(new V3(0, H.mouthY, 0).applyQuaternion(pq));
      var give = H.kind === 'bottle' ? Math.min(from.fill, 0.38) : from.fill*0.85;
      var hEnd = clone(from), dEnd = clone(ds), d0 = ds.fill;
      hEnd.fill = from.fill - give;
      dEnd.fill = Math.min(0.92, d0 + give*H.cap/D.cap);
      dEnd.blend = Math.max(ds.blend, H.kind === 'blender' ? sim[H.id].blend : 0);
      var tube = fx[a.hand].tube;
      a.play = function (u, T, snap) {
        var w = W[H.id], wd = W[D.id];
        if (u < 0.3) {
          var p = ease(seg(u, 0, 0.3));
          w.pos.lerpVectors(from.pos, pp, p); w.quat.copy(from.quat).slerp(pq, p);
        } else if (u < 0.78) {
          var f = seg(u, 0.3, 0.78);
          w.pos.copy(pp); w.pos.y += Math.sin(u*40)*0.0015; w.quat.copy(pq);
          w.fill = M.lerp(from.fill, hEnd.fill, f);
          wd.fill = M.lerp(d0, dEnd.fill, f); wd.swirl = u*12; wd.blend = dEnd.blend;
          if (give > 0.005) {
            w.quat.copy(pq); var m = new V3(0, H.mouthY + 0.004, 0).applyQuaternion(pq).add(pp);
            var surf = new V3(wd.pos.x, wd.pos.y + D.liqBase + Math.max(0.004, wd.fill*D.liqMax), wd.pos.z);
            tube.visible = true; aim(tube, m, surf, 1);
          }
        } else {
          var b = ease(seg(u, 0.78, 1));
          w.pos.lerpVectors(pp, from.pos, b); w.quat.copy(pq).slerp(from.quat, b);
          w.fill = hEnd.fill; wd.fill = dEnd.fill; wd.blend = dEnd.blend;
        }
        T[a.hand] = carried(w, rel); snap[a.hand] = true;
      };
      cp(sim[H.id], hEnd); cp(sim[D.id], dEnd);
      a.touch = [H, D]; a.handEnd = carried(hEnd, rel);
    };

    DO.release = function (a, h) {
      var start = h.pose, rest = K.restPose(a.hand), H = h.hold;
      if (!H) {
        a.play = function (u, T) { T[a.hand] = K.lerpPose(start, rest, ease(u)); };
        a.handEnd = rest; return;
      }
      var from = clone(sim[H.id]), rel = h.rel, D = h.over;
      if (D && D !== 'floor' && D.container) {               // drop it in
        var dEnd = clone(sim[D.id]); dEnd.chunks += 1;
        var hEnd = clone(from); hEnd.hidden = true;
        a.play = function (u, T, snap) {
          var w = W[H.id], wd = W[D.id];
          var open = carried(from, rel);
          if (u < 0.3) { T[a.hand] = withCurl(open, M.lerp(rel.curl, 0.15, ease(seg(u, 0, 0.3)))); snap[a.hand] = true; return; }
          T[a.hand] = K.lerpPose(withCurl(open, 0.15), rest, ease(seg(u, 0.3, 1)));
          if (u < 0.6) {
            var f = easeIn(seg(u, 0.3, 0.6));
            w.pos.copy(from.pos); w.pos.y = M.lerp(from.pos.y, wd.pos.y + D.liqBase + 0.03, f);
          } else { w.hidden = true; wd.chunks = dEnd.chunks; }
        };
        cp(sim[H.id], hEnd); cp(sim[D.id], dEnd);
        a.touch = [H, D];
      } else {                                               // set it down
        var floor = h.overY != null ? h.overY : 0;
        var down = clone(from); down.pos.y = floor + (D === 'floor' ? H.lift : 0);
        if (H.kind === 'spoon') down.pos.y = H.home.pos.y;
        var held = carried(down, rel);
        a.play = function (u, T, snap) {
          var w = W[H.id];
          if (u < 0.35) {
            w.pos.lerpVectors(from.pos, down.pos, ease(seg(u, 0, 0.35)));
            T[a.hand] = carried(w, rel); snap[a.hand] = true;
          } else {
            cp(w, down);
            if (u < 0.55) { T[a.hand] = withCurl(held, M.lerp(rel.curl, 0.15, ease(seg(u, 0.35, 0.55)))); snap[a.hand] = true; }
            else T[a.hand] = K.lerpPose(withCurl(held, 0.15), rest, ease(seg(u, 0.55, 1)));
          }
        };
        cp(sim[H.id], down);
        a.touch = [H];
      }
      h.hold = null; h.rel = null; h.over = null; h.overY = null; h.atD = null;
      a.handEnd = rest;
    };

    DO.stir = function (a, h) {
      var D = propOf(a.target);
      if (!D || !D.container) D = list.filter(function (p) { return p.container; })[0];
      var S = h.hold && h.hold.kind === 'spoon' ? h.hold : spoon;
      if (!D || !S || (h.hold && h.hold !== S)) return DO.unknown(a, h);
      var start = h.pose, rest = K.restPose(a.hand), s0 = clone(sim[S.id]), ds = sim[D.id];
      var grip0 = holdAt(S, s0.pos, s0.quat, a.hand), b0 = ds.blend;
      var bEnd = Math.max(b0, 0.6), keep = h.hold === S;
      function spin(ph, into) {
        var q = new QT().setFromEuler(new THREE.Euler(Math.sin(ph)*0.2, 0, Math.cos(ph)*0.2, 'ZXY'));
        var wd = W[D.id];
        var p = new V3(wd.pos.x + Math.cos(ph)*0.014, wd.pos.y + D.liqBase + 0.006 + (1 - into)*0.2, wd.pos.z + Math.sin(ph)*0.014);
        return { pos: p, quat: q };
      }
      a.play = function (u, T, snap) {
        var w = W[S.id], wd = W[D.id];
        if (!keep && u < 0.2) {
          T[a.hand] = K.lerpPose(start, withCurl(grip0, M.lerp(0.15, 0.86, seg(u, 0.12, 0.2))), ease(seg(u, 0, 0.14)));
          return;
        }
        var into = keep ? Math.min(1, u/0.1) : seg(u, 0.2, 0.3);
        var out = keep ? 0 : seg(u, 0.8, 0.95);
        var sp = spin(u*40, ease(into));
        if (out > 0) { sp.pos.lerp(s0.pos, ease(out)); sp.quat.slerp(s0.quat, ease(out)); }
        else if (into < 1) { sp.pos.lerp(s0.pos, 1 - ease(into)); sp.quat.slerp(s0.quat, 1 - ease(into)); }
        w.pos.copy(sp.pos); w.quat.copy(sp.quat);
        wd.swirl = u*16; wd.blend = M.lerp(b0, bEnd, seg(u, 0.3, 0.8));
        var g = holdAt(S, w.pos, w.quat, a.hand);
        if (!keep && u > 0.95) T[a.hand] = K.lerpPose(withCurl(g, 0.2), rest, ease(seg(u, 0.95, 1)));
        else { T[a.hand] = g; snap[a.hand] = true; }
      };
      var dEnd = clone(ds); dEnd.blend = bEnd;
      cp(sim[D.id], dEnd);
      a.touch = [D, S];
      a.handEnd = keep ? holdAt(S, s0.pos, s0.quat, a.hand) : rest;
    };

    DO.blend = function (a, h) {
      var B = propOf(a.target);
      if (!B || B.kind !== 'blender') B = list.filter(function (p) { return p.kind === 'blender'; })[0];
      if (!B) return DO.unknown(a, h);
      var start = h.pose, rest = K.restPose(a.hand), bs = clone(sim[B.id]);
      var btn = B.base.position.clone().add(new V3(0, 0.045, 0.072));
      var q = new QT().setFromEuler(new THREE.Euler(-0.12, 0, 0, 'YXZ'));
      var press = { pos: btn.clone().sub(new V3(0, 0, -0.152).applyQuaternion(q)), quat: q, curl: 0.08 };
      var pre = { pos: press.pos.clone().add(new V3(0, 0.02, 0.05)), quat: q, curl: 0.08 };
      var free = !h.hold;
      var end = clone(bs); end.fill = Math.min(0.9, bs.fill + bs.chunks*0.07); end.chunks = 0; end.blend = 1;
      a.play = function (u, T) {
        if (free) {
          if (u < 0.3) T[a.hand] = K.lerpPose(start, pre, ease(seg(u, 0, 0.3)));
          else if (u < 0.45) T[a.hand] = K.lerpPose(pre, press, Math.sin(Math.PI*seg(u, 0.3, 0.45)));
          else T[a.hand] = K.lerpPose(pre, rest, ease(seg(u, 0.45, 1)));
          B.button.position.z = 0.067 - 0.006*Math.sin(Math.PI*seg(u, 0.33, 0.42));
        }
        var w = W[B.id];
        if (u > 0.4) {
          var k = seg(u, 0.4, 0.95);
          w.blend = k; w.swirl = u*60; w.chunks = bs.chunks;
          w.fill = M.lerp(bs.fill, end.fill, k);
          var shake = Math.sin(Math.PI*k)*0.0025;
          w.pos.x += Math.sin(u*170)*shake; w.pos.z += Math.cos(u*150)*shake;
        }
      };
      cp(sim[B.id], end);
      a.touch = [B];
      a.handEnd = free ? rest : start;
    };

    DO.wipe = function (a, h) {
      var C = h.hold, rel = h.rel;
      if (C && C.kind !== 'cloth') return DO.unknown(a, h);
      var T0 = propOf(a.target), s = sgn(a.hand), start = h.pose;
      var c = T0 && T0.kind !== 'cloth' ? sim[T0.id].pos.clone().setY(0)
            : new V3(0.06*s, 0, 0.0);
      var patch = addProp('', 'patch', a.hand, [c.x, c.z]);
      var pEnd = clone(sim[patch.id]); pEnd.fill = 0;
      var from = C ? clone(sim[C.id]) : null;
      function path(u) { return new V3(c.x + Math.sin(u*Math.PI*7)*0.075, 0, c.z + (u - 0.5)*0.07); }
      var cEnd = C ? clone(from) : null;
      if (C) cEnd.pos.copy(path(1));
      var rest = K.restPose(a.hand);
      a.play = function (u, T, snap) {
        var k = seg(u, 0.15, 0.88), pt = path(k);
        W[patch.id].fill = 1 - k;
        if (C) {
          var w = W[C.id];
          if (u < 0.15) w.pos.lerpVectors(from.pos, path(0), ease(seg(u, 0, 0.15)));
          else w.pos.copy(pt);
          w.pos.y = u < 0.15 ? Math.sin(Math.PI*seg(u, 0, 0.15))*0.03 : 0;
          T[a.hand] = carried(w, rel); snap[a.hand] = true;
        } else {
          var flat = { pos: pt.clone().add(new V3(0, 0.03, 0.09)), quat: yawQ(a.hand, -0.1), curl: 0.1 };
          if (u < 0.15) T[a.hand] = K.lerpPose(start, flat, ease(seg(u, 0, 0.15)));
          else if (u < 0.88) T[a.hand] = flat;
          else T[a.hand] = K.lerpPose(flat, rest, ease(seg(u, 0.88, 1)));
        }
      };
      cp(sim[patch.id], pEnd);
      a.touch = C ? [patch, C] : [patch];
      if (C) { cp(sim[C.id], cEnd); a.handEnd = carried(cEnd, rel); }
      else a.handEnd = rest;
    };

    DO.shake = function (a, h) {
      var H = h.hold, rel = h.rel;
      if (!H) return DO.unknown(a, h);
      var from = clone(sim[H.id]), end = clone(from); end.blend = 1;
      a.play = function (u, T, snap) {
        var w = W[H.id], env = Math.sin(Math.PI*u);
        w.pos.copy(from.pos); w.pos.y += env*0.09 + Math.sin(u*Math.PI*16)*0.03*env;
        w.pos.x += Math.sin(u*Math.PI*16 + 1)*0.012*env;
        w.swirl = u*30; w.blend = Math.max(from.blend, u);
        T[a.hand] = carried(w, rel); snap[a.hand] = true;
      };
      cp(sim[H.id], end);
      a.touch = [H]; a.handEnd = carried(end, rel);
    };

    DO.fold = function (a, h) {
      var H = h.hold, rel = h.rel;
      if (!H || H.kind !== 'cloth') return DO.unknown(a, h);
      var from = clone(sim[H.id]), end = clone(from); end.fold = 1;
      a.play = function (u, T, snap) {
        var w = W[H.id];
        w.pos.copy(from.pos); w.pos.y += Math.sin(Math.PI*u)*0.05;
        w.fold = ease(seg(u, 0.2, 0.8));
        T[a.hand] = carried(w, rel); snap[a.hand] = true;
      };
      cp(sim[H.id], end);
      a.touch = [H]; a.handEnd = carried(end, rel);
    };

    DO.unknown = function (a, h) {
      a.placeholder = true;
      var P = propOf(a.target), box = placeholder(a.kind === 'gap' || !!a.gap);
      var at = P && !sim[P.id].hidden ? topOf(P, sim[P.id]).add(new V3(0, 0.07, 0))
             : h.pose.pos.clone().add(new V3(0, 0.06, -0.12));
      var start = h.pose, holding = !!h.hold;
      // Fastening what the hand just put against something: it stays there, the hand lets go.
      var letGo = holding && h.atD && fastens(a) && (!a.target || P === h.atD);
      var rest = K.restPose(a.hand), rel = h.rel;
      a.play = function (u, T, snap) {
        box.visible = true; box.position.copy(at);
        box.rotation.y = u*2.4;
        var k = 1 + Math.sin(u*Math.PI*4)*0.08; box.scale.set(k, k, k);
        if (letGo) {
          if (u < 0.6) { T[a.hand] = withCurl(start, M.lerp(rel.curl, 0.15, ease(seg(u, 0.35, 0.6)))); snap[a.hand] = true; }
          else T[a.hand] = K.lerpPose(withCurl(start, 0.15), rest, ease(seg(u, 0.6, 1)));
          return;
        }
        if (holding) snap[a.hand] = true;
        if (a.hand) T[a.hand] = start;
      };
      a.handEnd = start;
      if (letGo) { attach(h.hold, h.atD); h.hold = null; h.rel = null; h.atD = null; a.handEnd = rest; }
    };
    DO.gap = DO.unknown;

    /* --- simulate once --- */
    acts.forEach(function (a) {
      a.touch = [];
      var h = a.hand === 'left' || a.hand === 'right' ? hs[a.hand] : null;
      if (!h) {        // no hand: a placeholder in the middle of the counter
        a.hand = null;
        var box = placeholder(a.kind === 'gap' || !!a.gap), at = new V3(0, 0.16, -0.16);
        a.play = function (u) { box.visible = true; box.position.copy(at); box.rotation.y = u*2.4; };
      } else {
        (DO[a.kind] || DO.unknown)(a, h);
        if (a.handEnd) h.pose = a.handEnd;
        a.holdEnd = !!h.hold;
      }
      // whatever is fastened to a moved prop moves with it
      a.riders = ridersOf(a.touch);
      a.riders.forEach(function (r) { ride(r, sim[r.D.id], sim[r.P.id]); a.touch.push(r.P); });
      a.end =a.touch.map(function (P) { return { id: P.id, st: clone(sim[P.id]) }; });
    });

    /* --- per frame --- */
    var api = { props: list, actions: acts, active: [], gap: false, end: acts.reduce(function (m, a) { return Math.max(m, a.t1); }, 0) };
    api.evaluate = function (t, T, snap) {
      list.forEach(function (P) { cp(W[P.id], init[P.id]); });
      ['left', 'right'].forEach(function (s) { hide(fx[s].tube); hide(fx[s].ring); });
      ghosts.forEach(hide);
      list.forEach(function (P) { if (P.button) P.button.position.z = 0.067; });
      api.active = []; api.gap = false;
      for (var i = 0; i < acts.length; i++) {
        var a = acts[i];
        if (t < a.t0) break;
        if (t >= a.t1) {
          for (var k = 0; k < a.end.length; k++) cp(W[a.end[k].id], a.end[k].st);
          if (a.hand) { T[a.hand] = a.handEnd; snap[a.hand] = a.holdEnd; }
          continue;
        }
        if (a.hand) snap[a.hand] = false;
        a.play((t - a.t0)/(a.t1 - a.t0), T, snap);
        for (var r = 0; r < a.riders.length; r++) ride(a.riders[r], W[a.riders[r].D.id], W[a.riders[r].P.id]);
        api.active.push(a.step);
        if (a.kind === 'gap' || a.gap) api.gap = true;
      }
    };
    var liquidA = new THREE.Color(0x6a6a6a), liquidB = new THREE.Color(0xb8b8b8);
    api.render = function () {
      list.forEach(function (P) {
        var s = W[P.id];
        P.group.position.copy(s.pos); P.group.quaternion.copy(s.quat);
        P.group.visible = !s.hidden;
        P.group.scale.set(1 - 0.5*s.fold, 1 + s.fold, 1);
        if (P.kind === 'patch') { P.mat.opacity = s.fill*0.6; P.group.visible = s.fill > 0.01; }
        if (!P.liquid) return;
        P.liquid.visible = s.fill > 0.01;
        P.liquid.scale.y = Math.max(0.001, s.fill*P.liqMax);
        P.liquid.rotation.y = s.swirl;
        P.liqMat.color.copy(liquidA).lerp(liquidB, s.blend);
        for (var k = 0; k < P.chunkMeshes.length; k++) {
          var c = P.chunkMeshes[k], on = k < s.chunks && s.blend < 0.98;
          c.visible = on;
          if (!on) continue;
          var ang = k*2.1 + s.swirl*0.8, r = (k % 3 === 2 ? 0.006 : 0.02);
          c.position.set(Math.cos(ang)*r, P.liqBase + 0.014 + Math.floor(k/3)*0.02, Math.sin(ang)*r);
          var sc = 1 - s.blend; c.scale.set(sc, sc, sc);
          c.rotation.set(ang, ang*0.7, 0);
        }
      });
    };
    return api;
  }

  /* ---------------- the scene ---------------- */
  function create(cfg) {
    var canvas = cfg.canvas;
    var renderer;
    try { renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true }); }
    catch (err) { if (cfg.onError) cfg.onError(err); return null; }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputEncoding = THREE.sRGBEncoding;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = pick(cfg.exposure, cfg.style === 'plain' ? 1.0 : 1.12);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    /* style 'plain': grey tones only, no labels, no set dressing, still camera.
       Same choreography, so a recipe works in either style unchanged. */
    var PLAIN = cfg.style === 'plain';
    var PLAN = !!cfg.plan;
    var BG = pick(cfg.background, PLAIN ? 0xb4b4b4 : 0x07080b);
    var scene = new THREE.Scene();
    scene.background = new THREE.Color(BG);
    scene.fog = new THREE.Fog(BG, PLAIN ? 1.6 : 1.0, PLAIN ? 4.5 : 3.4);

    var cam = cfg.camera || {};
    var camera = new THREE.PerspectiveCamera(pick(cam.fov, 58), 1, 0.06, 24);
    var CAM_BASE = v3(cam.pos || [0, 0.54, 0.70]);
    var CAM_LOOK = v3(cam.look || [0, 0.03, -0.18]);

    var mats = {
      metal:  new THREE.MeshStandardMaterial({ color: 0xbcc6d0, metalness: 0.58, roughness: 0.26 }),
      shell:  new THREE.MeshStandardMaterial({ color: 0x3d4650, metalness: 0.42, roughness: 0.48 }),
      rubber: new THREE.MeshStandardMaterial({ color: 0x14171b, metalness: 0.1, roughness: 0.9 }),
      steel:  new THREE.MeshStandardMaterial({ color: 0xdde4ea, metalness: 0.62, roughness: 0.18 }),
      servo:  new THREE.MeshStandardMaterial({ color: 0x0a2a33, metalness: 0.4, roughness: 0.35,
                 emissive: new THREE.Color(pick(cfg.accent, 0x3ad8ff)), emissiveIntensity: 1.5 })
    };

    /* room */
    var counter = new THREE.Mesh(new THREE.BoxGeometry(2.6, 0.09, 1.25), PLAIN
      ? new THREE.MeshStandardMaterial({ color: 0x6a6a6a, roughness: 0.85, metalness: 0.0 })
      : new THREE.MeshStandardMaterial({ map: woodTex(), color: 0xb08a63, roughness: 0.46, metalness: 0.06 }));
    counter.position.set(0, -0.045, -0.2); counter.receiveShadow = true; scene.add(counter);

    if (!PLAN) {
    var matCfg = cfg.mat || { size: [0.86, 0.24], pos: [-0.05, -0.33] };
    var bar = new THREE.Mesh(new THREE.BoxGeometry(matCfg.size[0], 0.006, matCfg.size[1]),
      new THREE.MeshStandardMaterial({ color: 0x0c0e11, roughness: 1.0, metalness: 0.0 }));
    bar.position.set(matCfg.pos[0], 0.003, matCfg.pos[1]); bar.receiveShadow = true; scene.add(bar);
    }

    var wall = new THREE.Mesh(new THREE.PlaneGeometry(4.4, 2.6),
      new THREE.MeshStandardMaterial({ color: PLAIN ? 0x5c5c5c : 0x14181f, roughness: 0.95 }));
    wall.position.set(0, 0.6, -1.15); scene.add(wall);

    if (!PLAIN) {
    var shelf = new THREE.Mesh(new THREE.BoxGeometry(2.0, 0.035, 0.18),
      new THREE.MeshStandardMaterial({ color: 0x2a1a11, roughness: 0.6 }));
    shelf.position.set(0, 0.46, -1.0); scene.add(shelf);
    }
    var hues = [0x3d5c3a, 0x5a3321, 0x24415c, 0x5c4a20, 0x3a2446, 0x1f4a44, 0x523224, 0x2d3b52];
    for (var i = 0; i < (PLAIN ? 0 : pick(cfg.backBar, 14)); i++) {
      var hh = 0.14 + Math.random()*0.13, rr = 0.026 + Math.random()*0.014;
      var sb = new THREE.Mesh(new THREE.CylinderGeometry(rr*0.42, rr, hh, 12),
        new THREE.MeshStandardMaterial({ color: hues[i % hues.length], roughness: 0.25, metalness: 0.1 }));
      sb.position.set(-0.92 + i*0.14 + Math.random()*0.03, 0.478 + hh/2, -1.0 + (Math.random() - 0.5)*0.05);
      scene.add(sb);
    }

    /* lights */
    scene.add(PLAIN ? new THREE.HemisphereLight(0xffffff, 0x4a4a4a, 0.5)
                    : new THREE.HemisphereLight(0x3a4a66, 0x120c07, 0.42));
    var pendant = new THREE.SpotLight(PLAIN ? 0xffffff : 0xffd9a4, PLAIN ? 1.15 : 2.5, 4.2, 0.72, 0.72, 1.5);
    pendant.position.set(0.06, 1.02, -0.02);
    pendant.target.position.set(0, 0.03, -0.14);
    pendant.castShadow = true;
    pendant.shadow.mapSize.set(1024, 1024);
    pendant.shadow.camera.near = 0.2; pendant.shadow.camera.far = 2.4; pendant.shadow.bias = -0.0012;
    scene.add(pendant, pendant.target);
    if (!PLAIN) {
    var shadeG = new THREE.Group(); shadeG.position.copy(pendant.position); scene.add(shadeG);
    var shade = new THREE.Mesh(new THREE.ConeGeometry(0.13, 0.12, 24, 1, true),
      new THREE.MeshStandardMaterial({ color: 0x1b1f25, metalness: 0.7, roughness: 0.4, side: THREE.DoubleSide }));
    shade.position.y = 0.06; shadeG.add(shade);
    shadeG.add(new THREE.Mesh(new THREE.SphereGeometry(0.026, 14, 12),
      new THREE.MeshStandardMaterial({ color: 0xffe6bd, emissive: new THREE.Color(0xffd79a), emissiveIntensity: 2.4 })));
    var rimL = new THREE.PointLight(0x58d8ff, 1.25, 2.2, 1.9); rimL.position.set(-0.62, 0.40, 0.30); scene.add(rimL);
    var warmL = new THREE.PointLight(0xff9a54, 0.95, 2.4, 1.8); warmL.position.set(0.86, 0.30, 0.30); scene.add(warmL);
    var fillL = new THREE.PointLight(0xbcd0ff, 0.50, 1.8, 2.0); fillL.position.set(0, 0.42, 0.62); scene.add(fillL);
    var backL = new THREE.PointLight(0x3c6bff, 0.34, 1.9, 2.0); backL.position.set(0.1, 0.30, -0.80); scene.add(backL);
    } else {
      var front = new THREE.DirectionalLight(0xffffff, 0.3);
      front.position.set(0, 0.8, 1.2); scene.add(front);
    }

    /* props */
    var vessel = PLAN ? null : buildVessel(cfg.vessel);
    if (vessel) scene.add(vessel.group);

    var bottles = {}, bottleList = [];
    (cfg.bottles || []).forEach(function (b) {
      if (PLAIN) { var nb = {}; for (var k in b) nb[k] = b[k]; nb.label = null; b = nb; }
      var o = buildBottle(b);
      bottles[b.id] = o; bottleList.push(o);
      scene.add(o.group);
    });

    var streams = {};
    bottleList.forEach(function (b) {
      var tube = new THREE.Mesh(new THREE.CylinderGeometry(0.0062, 0.0092, 1, 10, 1, true),
        new THREE.MeshStandardMaterial({ color: b.cfg.stream, roughness: 0.15, metalness: 0.0,
          transparent: true, opacity: 0.95, side: THREE.DoubleSide,
          emissive: new THREE.Color(b.cfg.stream), emissiveIntensity: 0.4 }));
      tube.visible = false; scene.add(tube);
      var ring = new THREE.Mesh(new THREE.TorusGeometry(0.015, 0.0042, 8, 20),
        new THREE.MeshStandardMaterial({ color: b.cfg.stream, roughness: 0.2, transparent: true, opacity: 0.8 }));
      ring.rotation.x = Math.PI/2; ring.visible = false; scene.add(ring);
      streams[b.cfg.id] = { tube: tube, ring: ring };
    });

    var tools = {};
    Object.keys(cfg.tools || {}).forEach(function (key) {
      var tc = cfg.tools[key];
      var make = typeof tc.build === 'function' ? tc.build : TOOLS[tc.build || key];
      var opts = {}; for (var ok in (tc.options || {})) opts[ok] = tc.options[ok];
      if (PLAIN) opts.parasol = false;
      var g = make(mats, opts);
      var home = { pos: v3(tc.home.pos), quat: eulerQ(tc.home.euler) };
      var set = tc.set ? { pos: v3(tc.set.pos), quat: eulerQ(tc.set.euler) } : null;
      g.position.copy(home.pos); g.quaternion.copy(home.quat);
      scene.add(g);
      tools[key] = { group: g, home: home, set: set, grip: pick(tc.grip, 0.175), reach: pick(tc.reach, -0.094) };
    });

    // A plan is watched from further back, so its shoulders sit above the counter.
    var rig = cfg.arms || (PLAN ? { shoulder: [0.24, 0.32, 0.3], pole: [1, -0.4, 0.3], girth: 0.7 } : {});
    var armRig = { shoulder: rig.shoulder || [0.315, -0.125, 0.62], pole: rig.pole || [0.80, -0.52, 0.30] };
    var L1 = pick(rig.upper, 0.46), L2 = pick(rig.fore, 0.44);
    var hands = { left: makeHand('left', mats, armRig), right: makeHand('right', mats, armRig) };
    ['left', 'right'].forEach(function (k) {
      hands[k].parts.forEach(function (p) { scene.add(p); });
      var g = pick(rig.girth, 1);       // thinner links read better from far away
      [hands[k].upper, hands[k].forearm].forEach(function (m) { m.scale.x = m.scale.z = g; });
      hands[k].elbow.scale.setScalar(g);
      hands[k].bands.forEach(function (b) { b.scale.setScalar(g); });
    });

    /* poses */
    var GRASP = new V3(0, -0.028, -0.100);
    function gripQuat(side, tilt, yaw) {
      // Roll the palm to face inward (right hand palm -x, left hand palm +x), thumb up.
      return new QT().setFromEuler(new THREE.Euler(tilt || 0, yaw || 0, side === 'left' ? Math.PI/2 : -Math.PI/2, 'ZXY'));
    }
    function holdPose(obj, localY, side, tilt, reach) {
      obj.updateMatrixWorld();
      var p = obj.localToWorld(new V3(0, localY, 0));
      var q = obj.getWorldQuaternion(new QT()).multiply(gripQuat(side, tilt));
      var off = new V3(GRASP.x, GRASP.y, reach === undefined ? GRASP.z : reach).applyQuaternion(q);
      return { pos: p.sub(off), quat: q, curl: 0.86 };
    }
    function restPose(side) {
      var s = (side === 'left') ? -1 : 1;
      // a plan's camera sits further back, so the hands rest where it can see them
      return { pos: PLAN ? new V3(0.24*s, 0.07, 0.12) : new V3(0.255*s, 0.030, 0.265),
               quat: new QT().setFromEuler(new THREE.Euler(-0.26, 0.42*s, 0.22*s, 'ZXY')), curl: 0.24 };
    }
    function steadyPose(side, zOff) {
      var s = (side === 'left') ? -1 : 1;
      return { pos: new V3(cfg.vessel.x + 0.128*s, 0.022, cfg.vessel.z + pick(zOff, 0.105)),
               quat: new QT().setFromEuler(new THREE.Euler(-0.18, 0.62*s, 0.30*s, 'ZXY')), curl: 0.40 };
    }
    function lerpPose(a, b, t) {
      return { pos: new V3().lerpVectors(a.pos, b.pos, t), quat: a.quat.clone().slerp(b.quat, t), curl: M.lerp(a.curl, b.curl, t) };
    }

    var planMode = PLAN ? buildPlan(cfg.plan, scene, mats,
      { GRASP: GRASP, restPose: restPose, gripQuat: gripQuat, lerpPose: lerpPose }) : null;

    if (PLAIN) {
      // One pass turns everything grey, so a recipe's colours never leak through.
      scene.traverse(function (o) {
        if (!o.material) return;
        [].concat(o.material).forEach(function (m) {
          if (m.color) toGrey(m.color);
          if (m.emissive) { m.emissive.setRGB(0, 0, 0); m.emissiveIntensity = 0; }
          if (m.map) { m.map = null; m.needsUpdate = true; }
        });
      });
    }


    /* script -> timeline */
    var cursor = pick(cfg.lead, 1.6);
    var timeline = (cfg.script || []).map(function (a) {
      var parts = PHASES[a.kind].map(function (p) { return [p[0], (a.dur && a.dur[p[0]] !== undefined) ? a.dur[p[0]] : p[1]]; });
      var c = chain(cursor, parts);
      cursor = c.t1;
      var act = {}; for (var k in a) act[k] = a[k];
      act.seg = c.seg; act.t0 = c.t0; act.t1 = c.t1;
      return act;
    });
    var duration = (planMode ? Math.max(cursor, planMode.end) : cursor) + pick(cfg.tail, 2.0);

    /* per-frame state */
    var poured = {}, flags = {}, target = {}, snapped = {};
    bottleList.forEach(function (b) { poured[b.cfg.id] = 0; });
    var caption = cfg.idleCaption || 'Standing by', stateTxt = 'idle', gripCount = 0;
    var stirAmt = 0, swirl = 0, push = 0;

    function totalMl() { var s = 0; for (var k in poured) s += poured[k]; return s; }

    function evaluate(t) {
      caption = cfg.idleCaption || 'Standing by'; stateTxt = 'idle'; gripCount = 0;
      target.left = restPose('left'); target.right = restPose('right');
      snapped.left = snapped.right = false;
      stirAmt = 0; push = 0; flags = {};

      bottleList.forEach(function (b) {
        b.group.position.copy(b.home.pos); b.group.quaternion.copy(b.home.quat);
        streams[b.cfg.id].tube.visible = false; streams[b.cfg.id].ring.visible = false;
      });
      Object.keys(tools).forEach(function (k) {
        tools[k].group.position.copy(tools[k].home.pos);
        tools[k].group.quaternion.copy(tools[k].home.quat);
      });

      for (var ai = 0; ai < timeline.length; ai++) {
        var act = timeline[ai], s = act.seg;

        if (act.kind === 'pour') {
          var b = bottles[act.bottle], c = b.cfg;
          poured[c.id] = act.ml * seg(t, s.pour.a, s.pour.b);
          if (t < act.t0 || t >= act.t1) continue;
          var hand = act.hand, other = hand === 'left' ? 'right' : 'left';
          gripCount = 1;
          var tilt = (c.x < cfg.vessel.x) ? 1.02 : -1.02;
          var pourQuat = new QT().setFromEuler(new THREE.Euler(0, (c.yaw || 0)*0.4, tilt, 'ZXY'));
          var mouthOff = new V3(0, c.mouthY, 0).applyQuaternion(pourQuat);
          var mouthTarget = new V3(cfg.vessel.x + (c.x < cfg.vessel.x ? -0.012 : 0.012), 0.272, cfg.vessel.z - 0.004);
          var pourPos = mouthTarget.clone().sub(mouthOff);
          var overPos = new V3(c.x*0.8, 0.165, c.z + 0.03);
          caption = act.caption || caption;

          if (t < s.reach.b) {
            var p = ease(seg(t, s.reach.a, s.reach.b));
            var grab = holdPose(b.group, c.neckY, hand, 0.22); grab.curl = 0.16;
            target[hand] = lerpPose(restPose(hand), grab, p);
            stateTxt = 'reach'; caption = act.reachCaption || act.caption || caption;
          } else if (t < s.grip.b) {
            var g2 = holdPose(b.group, c.neckY, hand, 0.22);
            g2.curl = M.lerp(0.16, 0.86, ease(seg(t, s.grip.a, s.grip.b)));
            target[hand] = g2; snapped[hand] = true; stateTxt = 'grip';
          } else if (t < s.lift.b) {
            var p3 = ease(seg(t, s.lift.a, s.lift.b));
            var pos = new V3().lerpVectors(b.home.pos, pourPos, p3);
            pos.lerp(overPos, Math.sin(p3*Math.PI)*0.35);
            pos.y += Math.sin(p3*Math.PI)*0.045;
            b.group.position.copy(pos);
            b.group.quaternion.copy(b.home.quat.clone().slerp(pourQuat, easeIn(p3)));
            target[hand] = holdPose(b.group, c.neckY, hand, 0.22); snapped[hand] = true;
            target[other] = steadyPose(other);
            stateTxt = 'pour'; gripCount = 2;
          } else if (t < s.pour.b) {
            var pp = seg(t, s.pour.a, s.pour.b);
            b.group.position.copy(pourPos);
            b.group.position.y += Math.sin(t*5.0)*0.0022;
            b.group.quaternion.copy(pourQuat).multiply(
              new QT().setFromEuler(new THREE.Euler(0, 0, tilt*0.18*easeOut(Math.min(1, pp*2.2)), 'ZXY')));
            target[hand] = holdPose(b.group, c.neckY, hand, 0.22); snapped[hand] = true;
            target[other] = steadyPose(other);
            stateTxt = 'pour'; gripCount = 2;
            b.group.updateMatrixWorld();
            var mouth = b.group.localToWorld(new V3(0, c.mouthY + 0.004, 0));
            var hit = new V3(cfg.vessel.x, vessel.fillHeight(totalMl()) + 0.002, cfg.vessel.z);
            var st = streams[c.id];
            st.tube.visible = true;
            aim(st.tube, mouth, hit, 1);
            var w = 0.85 + Math.sin(t*22)*0.12;
            st.tube.scale.x = w; st.tube.scale.z = w;
            st.ring.visible = true; st.ring.position.copy(hit);
            var rp = 1 + Math.sin(t*16)*0.22;
            st.ring.scale.set(rp, rp, 1);
            st.ring.material.opacity = 0.55 + Math.sin(t*16)*0.2;
          } else if (t < s.up.b) {
            var p5 = ease(seg(t, s.up.a, s.up.b));
            b.group.position.copy(new V3().lerpVectors(pourPos, overPos, p5));
            b.group.quaternion.copy(pourQuat.clone().slerp(b.home.quat, p5));
            target[hand] = holdPose(b.group, c.neckY, hand, 0.22); snapped[hand] = true;
            target[other] = steadyPose(other);
            stateTxt = 'return'; gripCount = 2; caption = act.backCaption || caption;
          } else if (t < s.back.b) {
            var p6 = ease(seg(t, s.back.a, s.back.b));
            var bp = new V3().lerpVectors(overPos, b.home.pos, p6);
            bp.y += Math.sin(p6*Math.PI)*0.02;
            b.group.position.copy(bp);
            b.group.quaternion.copy(b.home.quat);
            target[hand] = holdPose(b.group, c.neckY, hand, 0.22); snapped[hand] = true;
            stateTxt = 'return'; caption = act.backCaption || caption;
          } else {
            var p7 = ease(seg(t, s.rel.a, s.rel.b));
            var g7 = holdPose(b.group, c.neckY, hand, 0.22);
            g7.curl = M.lerp(0.86, 0.24, p7);
            target[hand] = lerpPose(g7, restPose(hand), p7*0.65);
            stateTxt = 'return'; caption = act.backCaption || caption;
          }
        }

        else if (act.kind === 'stir') {
          var tool = tools[act.tool];
          if (t >= s.stir.a) stirAmt = seg(t, s.stir.a, s.stir.a + 1.6);
          if (stirAmt > 0.98 && act.sets) flags[act.sets] = true;
          if (t < act.t0 || t >= act.t1) continue;
          var sh = act.hand, so = sh === 'left' ? 'right' : 'left';
          caption = act.caption || caption; stateTxt = 'swirl'; gripCount = 2;
          target[so] = steadyPose(so, 0.075);
          var lean = 0.2;
          var stirQ = function (ph) {
            return new QT().setFromEuler(new THREE.Euler(Math.sin(ph)*lean, 0, Math.cos(ph)*lean, 'ZXY'));
          };
          if (t < s.reach.b) {
            var sp = ease(seg(t, s.reach.a, s.reach.b));
            var sg = holdPose(tool.group, tool.grip, sh, 0.2, tool.reach); sg.curl = 0.16;
            target[sh] = lerpPose(restPose(sh), sg, sp); stateTxt = 'reach';
          } else if (t < s.grip.b) {
            var sg2 = holdPose(tool.group, tool.grip, sh, 0.2, tool.reach);
            sg2.curl = M.lerp(0.16, 0.86, ease(seg(t, s.grip.a, s.grip.b)));
            target[sh] = sg2; snapped[sh] = true; stateTxt = 'grip';
          } else if (t < s.stir.b) {
            var inPos = Math.min(1, seg(t, s.stir.a, s.stir.b)*4);
            var ph = t*7.2;
            var spin = new V3(cfg.vessel.x + Math.cos(ph)*0.016, 0.028, cfg.vessel.z + Math.sin(ph)*0.016);
            tool.group.position.copy(new V3().lerpVectors(tool.home.pos, spin, ease(inPos)));
            tool.group.quaternion.copy(tool.home.quat.clone().slerp(stirQ(ph), ease(inPos)));
            target[sh] = holdPose(tool.group, tool.grip, sh, 0.2, tool.reach); snapped[sh] = true;
            swirl = ph;
          } else if (t < s.out.b) {
            var op = ease(seg(t, s.out.a, s.out.b));
            var ph2 = s.out.a*7.2;
            var spin2 = new V3(cfg.vessel.x + Math.cos(ph2)*0.016, 0.028, cfg.vessel.z + Math.sin(ph2)*0.016);
            tool.group.position.copy(new V3().lerpVectors(spin2, new V3(cfg.vessel.x + 0.02, 0.26, cfg.vessel.z + 0.05), op));
            tool.group.quaternion.copy(stirQ(ph2).slerp(tool.home.quat, op*0.5));
            target[sh] = holdPose(tool.group, tool.grip, sh, 0.2, tool.reach); snapped[sh] = true;
          } else if (t < s.back.b) {
            var bp2 = ease(seg(t, s.back.a, s.back.b));
            tool.group.position.copy(new V3().lerpVectors(new V3(cfg.vessel.x + 0.02, 0.26, cfg.vessel.z + 0.05), tool.home.pos, bp2));
            tool.group.quaternion.copy(stirQ(0).slerp(tool.home.quat, Math.min(1, bp2*1.6)));
            target[sh] = holdPose(tool.group, tool.grip, sh, 0.2, tool.reach); snapped[sh] = true;
          } else {
            var rp2 = ease(seg(t, s.rel.a, s.rel.b));
            var rg = holdPose(tool.group, tool.grip, sh, 0.2, tool.reach);
            rg.curl = M.lerp(0.86, 0.24, rp2);
            target[sh] = lerpPose(rg, restPose(sh), rp2*0.6);
          }
        }

        else if (act.kind === 'place') {
          var pt = tools[act.tool];
          if (t >= s.settle.a) {
            if (act.sets) flags[act.sets] = true;
            pt.group.position.copy(pt.set.pos); pt.group.quaternion.copy(pt.set.quat);
          }
          if (t < act.t0 || t >= act.t1) continue;
          var ph3 = act.hand, po = ph3 === 'left' ? 'right' : 'left';
          caption = act.caption || caption; stateTxt = 'garnish'; gripCount = 1;
          if (t >= s.place.a) target[po] = steadyPose(po, 0.075);
          if (t < s.reach.b) {
            var q1 = ease(seg(t, s.reach.a, s.reach.b));
            var pg = holdPose(pt.group, pt.grip, ph3, 0.3, pt.reach); pg.curl = 0.18;
            target[ph3] = lerpPose(restPose(ph3), pg, q1); stateTxt = 'reach';
          } else if (t < s.grip.b) {
            var pg2 = holdPose(pt.group, pt.grip, ph3, 0.3, pt.reach);
            pg2.curl = M.lerp(0.18, 0.8, ease(seg(t, s.grip.a, s.grip.b)));
            target[ph3] = pg2; snapped[ph3] = true;
          } else if (t < s.settle.b) {
            var q3 = (t < s.place.b) ? ease(seg(t, s.place.a, s.place.b)) : 1;
            var pp2 = new V3().lerpVectors(pt.home.pos, pt.set.pos, q3);
            pp2.y += Math.sin(q3*Math.PI)*0.075;
            pt.group.position.copy(pp2);
            pt.group.quaternion.copy(pt.home.quat.clone().slerp(pt.set.quat, q3));
            var pg3 = holdPose(pt.group, pt.grip, ph3, 0.3, pt.reach); pg3.curl = 0.8;
            target[ph3] = pg3; snapped[ph3] = true;
          } else {
            pt.group.position.copy(pt.set.pos); pt.group.quaternion.copy(pt.set.quat);
            var pg4 = holdPose(pt.group, pt.grip, ph3, 0.3, pt.reach);
            if (t < s.rel.b) {
              pg4.curl = M.lerp(0.8, 0.2, ease(seg(t, s.rel.a, s.rel.b)));
              target[ph3] = pg4; snapped[ph3] = true;
            } else {
              pg4.curl = 0.2;
              target[ph3] = lerpPose(pg4, restPose(ph3), ease(seg(t, s.back.a, s.back.b)));
            }
          }
        }

        else if (act.kind === 'serve') {
          var dist = pick(act.push, 0.072);
          if (t >= s.push.a) push = dist * easeOut(seg(t, s.push.a, s.push.b));
          if (t < act.t0) continue;
          if (t >= act.t1) { caption = act.doneCaption || act.caption || caption; stateTxt = 'served'; continue; }
          caption = act.caption || caption; stateTxt = 'serve'; gripCount = 2;
          var hold = function (side) {
            var q = gripQuat(side, 0.1);
            var p = new V3(cfg.vessel.x, 0.075, cfg.vessel.z + push);
            return { pos: p.clone().sub(new V3(GRASP.x, GRASP.y, -0.128).applyQuaternion(q)), quat: q, curl: 0.72 };
          };
          if (t < s.reach.b) {
            var q5 = ease(seg(t, s.reach.a, s.reach.b));
            ['left', 'right'].forEach(function (side) {
              var h = hold(side); h.curl = 0.2;
              target[side] = lerpPose(restPose(side), h, q5);
            });
            stateTxt = 'reach';
          } else if (t < s.rel.b) {
            ['left', 'right'].forEach(function (side) {
              var h = hold(side);
              if (t < s.grip.b) h.curl = M.lerp(0.2, 0.72, ease(seg(t, s.grip.a, s.grip.b)));
              if (t >= s.rel.a) h.curl = M.lerp(0.72, 0.25, ease(seg(t, s.rel.a, s.rel.b)));
              target[side] = h; snapped[side] = true;
            });
          } else {
            var q7 = ease(seg(t, s.drop.a, s.drop.b));
            ['left', 'right'].forEach(function (side) {
              var h = hold(side); h.curl = 0.25;
              var down = restPose(side);
              down.pos = down.pos.clone().add(new V3(0.06*(side === 'left' ? -1 : 1), -0.30, 0.12));
              target[side] = lerpPose(h, down, q7);
            });
            caption = act.doneCaption || caption; stateTxt = 'served';
          }
        }
      }
    }

    function applyHand(h, tgt, snap, dt) {
      var st = h.state;
      if (!st.init || snap) {
        st.pos.copy(tgt.pos); st.quat.copy(tgt.quat); st.curl = tgt.curl; st.init = true;
      } else {
        var k = 1 - Math.exp(-16*dt);
        st.pos.lerp(tgt.pos, k); st.quat.slerp(tgt.quat, k); st.curl = M.lerp(st.curl, tgt.curl, k);
      }
      h.group.position.copy(st.pos);
      h.group.quaternion.copy(st.quat);
      h.setCurl(st.curl);
      h.group.updateMatrixWorld();
      var wrist = h.group.localToWorld(new V3(0, 0, 0.028));
      var elbowPos = solveElbow(h.shoulder, wrist, L1, L2, h.pole);
      aim(h.upper, h.shoulder, elbowPos, 1);
      var info = aim(h.forearm, elbowPos, wrist, 1);
      h.elbow.position.copy(elbowPos);
      for (var i = 0; i < h.bands.length; i++) {
        h.bands[i].position.copy(elbowPos).addScaledVector(info.dir, info.len*(0.34 + i*0.34));
        h.bands[i].quaternion.copy(h.forearm.quaternion).multiply(new QT().setFromEuler(new THREE.Euler(Math.PI/2, 0, 0)));
      }
    }

    /* drink colour mixing */
    var mixCol = new THREE.Color();
    var finishCol = new THREE.Color(pick((cfg.vessel || {}).finish, 0xf5dc9c));
    var bottleCol = {};
    bottleList.forEach(function (b) { bottleCol[b.cfg.id] = new THREE.Color(b.cfg.liquid); });

    /* camera + loop */
    var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var look = { x: 0, y: 0, tx: 0, ty: 0 };
    var playing = true, clock = 0, holdTime = false, last = performance.now(), raf = 0;

    function onPointer(e) {
      look.tx = (e.clientX / window.innerWidth - 0.5) * 2;
      look.ty = (e.clientY / window.innerHeight - 0.5) * 2;
    }
    window.addEventListener('pointermove', onPointer);

    // fit: 'parent' sizes to the canvas's own box (embedded); default is the window.
    var FIT = cfg.fit === 'parent', ro = null;
    function resize() {
      var w = FIT ? canvas.clientWidth : window.innerWidth, h = FIT ? canvas.clientHeight : window.innerHeight;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    }
    window.addEventListener('resize', resize);
    if (FIT && typeof ResizeObserver !== 'undefined') { ro = new ResizeObserver(resize); ro.observe(canvas); }
    resize();

    function frame(now) {
      var dt = Math.min(0.05, (now - last) / 1000); last = now;
      if (playing && !holdTime) { clock += dt; if (clock > duration) clock = 0; }
      draw(dt);
      raf = requestAnimationFrame(frame);
    }
    function draw(dt) {

      if (planMode) {
        target.left = restPose('left'); target.right = restPose('right');
        snapped.left = snapped.right = false;
        planMode.evaluate(clock, target, snapped);
        planMode.render();
      } else evaluate(clock);
      applyHand(hands.left, target.left, snapped.left, dt);
      applyHand(hands.right, target.right, snapped.right, dt);

      if (vessel) {
      vessel.group.position.z = cfg.vessel.z + push;
      var ml = totalMl();
      var hgt = vessel.fillHeight(ml);
      vessel.setLiquid(hgt);
      if (ml > 1) {
        mixCol.setRGB(0, 0, 0);
        for (var id in poured) mixCol.add(bottleCol[id].clone().multiplyScalar(poured[id] / ml));
        mixCol.lerp(finishCol, stirAmt*0.7);
        if (PLAIN) toGrey(mixCol);
        vessel.liquidMat.color.copy(mixCol);
        vessel.liquidMat.opacity = 0.88 + stirAmt*0.08;
      }
      vessel.liquid.rotation.y = swirl*0.5;
      vessel.liquid.rotation.z = (stirAmt > 0 && stirAmt < 1 ? 0.035 : 0) * Math.sin(swirl);
      vessel.foam.visible = stirAmt > 0.02;
      if (vessel.foam.visible) {
        vessel.foam.material.opacity = stirAmt*0.62;
        vessel.foam.position.y = hgt - 0.002;
        var fr = vessel.innerR(hgt)*0.97;
        vessel.foam.scale.set(fr/0.05, 1, fr/0.05);
      }
      for (var ic = 0; ic < vessel.ice.length; ic++) {
        var cube = vessel.ice[ic];
        var sub = M.clamp((hgt - cube.userData.y0) / 0.03, 0, 1);
        cube.position.y = cube.userData.y0 + sub*0.004 + (reduce ? 0 : Math.sin(clock*1.6 + ic)*0.0012*sub);
        cube.rotation.y += dt*0.12*sub;
      }
      bottleList.forEach(function (b) {
        b.inner.scale.y = Math.max(0.06, 1 - poured[b.cfg.id] / b.cfg.ml * 0.55);
      });
      }

      look.x += (look.tx - look.x) * Math.min(1, dt*3);
      look.y += (look.ty - look.y) * Math.min(1, dt*3);
      var bob = (reduce || PLAIN) ? 0 : 1;
      if (PLAIN) { look.x = look.y = 0; }
      camera.position.set(
        CAM_BASE.x + look.x*0.055 + bob*Math.sin(clock*0.62)*0.009,
        CAM_BASE.y + look.y*-0.03 + bob*Math.sin(clock*0.85 + 1.2)*0.007,
        CAM_BASE.z + bob*Math.sin(clock*0.44)*0.006);
      camera.up.set(bob*Math.sin(clock*0.5)*0.012, 1, 0);
      camera.lookAt(CAM_LOOK.x + look.x*0.085, CAM_LOOK.y + look.y*-0.05, CAM_LOOK.z);

      if (cfg.onFrame) {
        cfg.onFrame({
          t: clock, duration: duration, state: stateTxt, caption: caption,
          poured: poured, totalMl: ml, flags: flags, grip: gripCount,
          active: planMode ? planMode.active : [], gap: planMode ? planMode.gap : false,
          fade: clock > duration - 0.45 ? (clock - (duration - 0.45))/0.45 : (clock < 0.3 ? 1 - clock/0.3 : 0)
        });
      }
      renderer.render(scene, camera);
    }
    raf = requestAnimationFrame(frame);

    return {
      THREE: THREE, scene: scene, camera: camera, renderer: renderer, duration: duration,
      props: planMode ? planMode.props : [], actions: planMode ? planMode.actions : [], hands: hands,
      play:    function () { playing = true; },
      pause:   function () { playing = false; },
      toggle:  function () { playing = !playing; return playing; },
      isPlaying: function () { return playing; },
      hold:    function (on) { holdTime = on; },
      seek:    function (t) { clock = M.clamp(t, 0, duration); },
      restart: function () { clock = 0; },
      time:    function () { return clock; },
      // Draw one exact moment now, hands settled (for stills and contact sheets).
      renderAt: function (t) { clock = M.clamp(t, 0, duration); draw(1); return renderer.domElement; },
      dispose: function () {
        cancelAnimationFrame(raf);
        window.removeEventListener('pointermove', onPointer);
        window.removeEventListener('resize', resize);
        if (ro) ro.disconnect();
        renderer.dispose(); renderer.forceContextLoss();
      }
    };
  }

  global.POVScene = { create: create, tools: TOOLS, props: PROPS, propKind: propKind,
                      textures: { wood: woodTex, label: labelTex }, version: '1.1.0' };
})(window);
