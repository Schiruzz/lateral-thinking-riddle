// The sky of a game: the Night (an eclipse) at the top, a veiled sky below where the found facts build the
// constellation of what the player sees; at the victory it becomes the constellation of the truth and takes its name.
// Drawn on a canvas, animated with GSAP. It knows nothing of the riddle: the page gives it each fact once found.
// Needs gsap and figures.js (FIGURES, ATLAS).

const SKY_W = 390, SKY_H = 460;                     // the drawing's own units; the canvas is scaled to the page
const NIGHT_X = SKY_W / 2, NIGHT_Y = 78, NIGHT_R = 34;
const FIGURE_X = SKY_W / 2, FIGURE_Y = 284, FIGURE_SCALE = 2.45;
const STILL = matchMedia("(prefers-reduced-motion: reduce)").matches;

// a random generator from a text: the same riddle always gets the same sky
function seeded(text) {
  let state = 0;
  for (const char of text) state = Math.imul(31, state) + char.charCodeAt(0) | 0;
  return () => {   // mulberry32
    state = state + 0x6D2B79F5 | 0;
    let t = Math.imul(state ^ state >>> 15, 1 | state);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

function gauss(random) { return (random() + random() + random() - 1.5) / 1.5; }

// the main stars of a figure, bent by the seed, in sky units
function placeFigure(figure, random) {
  const turn = (random() - 0.5) * 0.16;
  return figure.points.map(([x, y], i) => {
    if (figure.radial && i > 0) {
      // an arm: its own length and a small swing of its angle
      const a = Math.atan2(y, x) + (random() - 0.5) * 0.26, r = Math.hypot(x, y) * (0.78 + random() * 0.4);
      x = Math.cos(a) * r; y = Math.sin(a) * r;
    } else {
      x += (random() - 0.5) * 6; y += (random() - 0.5) * 6;
    }
    const rx = x * Math.cos(turn) - y * Math.sin(turn), ry = x * Math.sin(turn) + y * Math.cos(turn);
    return {x: FIGURE_X + rx * FIGURE_SCALE, y: FIGURE_Y + ry * FIGURE_SCALE};
  });
}

// the minor stars: near the figure's lines, without lines of their own, as in a real constellation
function placeMinor(points, edges, count, random) {
  const out = [];
  for (let tries = 0; out.length < count && tries < 6000; tries++) {
    const [i, j] = edges[Math.floor(random() * edges.length)];
    const t = 0.15 + random() * 0.7, a = points[i], b = points[j];
    const len = Math.hypot(b.x - a.x, b.y - a.y) || 1;
    const off = (random() < 0.5 ? -1 : 1) * (14 + random() * 26);
    const p = {x: a.x + (b.x - a.x) * t - (b.y - a.y) / len * off, y: a.y + (b.y - a.y) * t + (b.x - a.x) / len * off};
    if ([...points, ...out].some(o => Math.hypot(o.x - p.x, o.y - p.y) < 22)) continue;
    if (p.x < 16 || p.x > SKY_W - 16 || p.y < 140 || p.y > SKY_H - 40) continue;
    out.push(p);
  }
  return out;
}

// a soft round light, drawn once and reused for every glow
function sprite(rgb) {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d");
  const grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  grad.addColorStop(0, `rgba(${rgb},1)`);
  grad.addColorStop(0.18, `rgba(${rgb},0.55)`);
  grad.addColorStop(0.45, `rgba(${rgb},0.12)`);
  grad.addColorStop(1, `rgba(${rgb},0)`);
  g.fillStyle = grad;
  g.fillRect(0, 0, 128, 128);
  return c;
}

class Sky {
  constructor(canvas) {
    this.canvas = canvas;
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = SKY_W * this.dpr;
    canvas.height = SKY_H * this.dpr;
    this.ctx = canvas.getContext("2d");
    this.veilCanvas = document.createElement("canvas");
    this.veilCanvas.width = canvas.width;
    this.veilCanvas.height = canvas.height;
    this.warm = sprite("255,236,200");
    this.cold = sprite("190,215,255");
    this.white = sprite("255,250,240");
    const tick = (time) => { this.draw(time / 1000); requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
  }

  // a new game: the stars of the figure of what the player sees, all still behind the veil
  load(game) {
    this.seed = game.seed;
    const random = seeded(game.seed);
    const figure = FIGURES[game.figure];
    const main = placeFigure(figure, random);
    const minor = placeMinor(main, figure.edges, game.stars - main.length, random);
    const star = (p, isMain) => ({x: p.x, y: p.y, main: isMain, text: "", given: false, key: false, lit: false,
      glow: 0, flash: 0, reveal: {r: 0}, size: isMain ? 1.35 + random() * 0.3 : 0.8 + random() * 0.25,
      twinkle: 0.6 + random() * 1.4, phase: random() * 2 * Math.PI, fly: null, scale: 1, fade: 1});
    this.stars = [...main.map(p => star(p, true)), ...minor.map(p => star(p, false))];
    // the figure is built along its lines as facts are found: its main stars first, a minor one every other one
    const order = [], minorStars = this.stars.filter(s => !s.main);
    this.stars.filter(s => s.main).forEach((s, i) => { order.push(s); if (i % 2 && minorStars.length) order.push(minorStars.shift()); });
    this.order = [...order, ...minorStars];
    this.lines = figure.edges.map(([a, b]) => ({a: this.stars[a], b: this.stars[b], p: 0, fade: 1}));
    this.truthLines = null;
    // the deep sky: three layers of small stars, denser around the figure so a found fact opens a cluster
    const deep = seeded(game.seed + "-deep");
    const tint = () => { const r = deep(); return r < 0.25 ? "190,210,255" : r < 0.85 ? "235,240,250" : "255,225,190"; };
    this.dust = [];
    for (const [count, rmin, rmax, amax, layer] of [[800, 0.25, 0.6, 0.55, 0], [280, 0.45, 0.95, 0.75, 1], [60, 0.8, 1.5, 0.9, 2]]) {
      for (let i = 0; i < count; i++) this.dust.push({x: deep() * SKY_W, y: deep() * SKY_H, r: rmin + deep() * (rmax - rmin),
        a: 0.25 + deep() * amax, c: tint(), tw: 0.5 + deep() * 2.5, ph: deep() * 2 * Math.PI, layer});
    }
    for (const s of this.stars) {
      for (let i = 0; i < 24; i++) this.dust.push({x: s.x + gauss(deep) * 40, y: s.y + gauss(deep) * 40,
        r: 0.3 + deep() * 0.8, a: 0.35 + deep() * 0.6, c: tint(), tw: 0.5 + deep() * 2.5, ph: deep() * 2 * Math.PI, layer: 3});
    }
    // the nebulae: their colour turns when a sealed scene opens
    this.clouds = Array.from({length: 4}, () => ({x: 40 + deep() * (SKY_W - 80), y: 80 + deep() * (SKY_H - 140),
      r: 150 + deep() * 120, from: [50 + deep() * 70, 70 + deep() * 60, 160 + deep() * 40], to: [120 + deep() * 90, 70 + deep() * 70, 120 + deep() * 80]}));
    this.fog = this.makeFog(deep);
    // the corona of the Night: long uneven streamers, longer at the sides as in a real eclipse
    const night = seeded(game.seed + "-night");
    this.streamers = Array.from({length: 90}, () => {
      const a = night() * 2 * Math.PI, side = Math.abs(Math.cos(a));
      return {a, len: NIGHT_R * (0.35 + night() * 0.5 + side * night() * 1.6), w: 0.6 + night() * 2.2,
              alpha: 0.05 + night() * 0.12, ph: night() * 2 * Math.PI, sp: 0.2 + night() * 0.5};
    });
    this.prominences = Array.from({length: 3}, () => ({a: night() * 2 * Math.PI, h: 2 + night() * 3, ph: night() * 2 * Math.PI}));
    this.veil = {alpha: 0.94};
    this.mix = {v: 0};
    this.wave = null;
    this.comet = null;
    this.dim = {v: 1};
    this.shine = {v: 0};
    this.atlas = {a: 0, lines: null};
    this.label = {a: 0, name: "", epithet: ""};
    this.sceneOpen = false;
    this.voice = {listen: 0, think: 0, speak: 0, flare: 0};
  }

  // the veil: dark mist with some texture, so the hidden sky is not a flat black
  makeFog(random) {
    const c = document.createElement("canvas");
    c.width = this.veilCanvas.width; c.height = this.veilCanvas.height;
    const g = c.getContext("2d");
    g.scale(this.dpr, this.dpr);
    g.fillStyle = "rgb(5,8,17)";
    g.fillRect(0, 0, SKY_W, SKY_H);
    for (let i = 0; i < 70; i++) {
      const x = random() * SKY_W, y = random() * SKY_H, r = 30 + random() * 110;
      const grad = g.createRadialGradient(x, y, 0, x, y, r);
      grad.addColorStop(0, random() < 0.5 ? "rgba(30,40,70,0.22)" : "rgba(0,0,6,0.35)");
      grad.addColorStop(1, "rgba(0,0,0,0)");
      g.fillStyle = grad;
      g.fillRect(x - r, y - r, 2 * r, 2 * r);
    }
    return c;
  }

  // the Night follows the game: "idle", "listening", "thinking" or "speaking"
  setVoice(state) {
    if (!this.voice) return;
    gsap.to(this.voice, {listen: +(state === "listening"), think: +(state === "thinking"), speak: +(state === "speaking"),
                         duration: 0.4, ease: "sine.inOut", overwrite: "auto"});
  }

  // a found fact lights the next star of the figure; a fact given by a hint arrives as a spark from the corona
  light(fact, delay = 0) {
    const s = this.order.find(x => !x.lit);
    if (!s) return;
    Object.assign(s, {lit: true, text: fact.text, given: fact.given});
    if (!fact.given) { gsap.delayedCall(delay, () => this.ignite(s, fact.sealed)); return; }
    const a = Math.atan2(s.y - NIGHT_Y, s.x - NIGHT_X);
    const from = {x: NIGHT_X + Math.cos(a) * (NIGHT_R + 6), y: NIGHT_Y + Math.sin(a) * (NIGHT_R + 6)};
    const bend = (s.x < NIGHT_X ? -1 : 1) * 0.3;
    const comet = {q: 0, trail: [], fadeTrail: 0, from, to: s,
      c: {x: (from.x + s.x) / 2 - (s.y - from.y) * bend, y: (from.y + s.y) / 2 + (s.x - from.x) * bend}};
    this.comet = comet;
    gsap.to(comet, {q: 1, duration: STILL ? 0 : 1.2, delay, ease: "power2.in", onComplete: () => {
      gsap.to(comet, {fadeTrail: 1, duration: 0.6, onComplete: () => { if (this.comet === comet) this.comet = null; }});
      this.ignite(s, fact.sealed);
    }});
  }

  ignite(s, sealed) {
    s.flash = 1;
    gsap.to(s, {glow: 1, duration: 1.4, ease: "power2.out"});
    gsap.to(s, {flash: 0, duration: 1.6, ease: "power2.out"});
    gsap.to(s.reveal, {r: 70 + Math.random() * 24, duration: STILL ? 0 : 2.6, ease: "power3.out"});
    for (const line of this.lines) {
      if (line.p || (line.a !== s && line.b !== s)) continue;
      const other = line.a === s ? line.b : line.a;
      if (!other.glow) continue;
      line.from = other;   // the light runs from the star already known to the new one
      gsap.to(line, {p: 1, duration: STILL ? 0 : 1.3, delay: 0.5, ease: "power1.inOut"});
    }
    if (sealed && !this.sceneOpen) this.openScene(s);
  }

  // a sealed scene opens: a wave runs through the sky, the mist thins and the colours turn
  openScene(s) {
    this.sceneOpen = true;
    this.wave = {x: s.x, y: s.y, r: 0, a: 0.5};
    gsap.to(this.wave, {r: 700, a: 0, duration: 3.2, ease: "power2.out"});
    gsap.to(this.mix, {v: 1, duration: 4, ease: "sine.inOut"});
    gsap.to(this.veil, {alpha: 0.84, duration: 3, ease: "sine.inOut"});
  }

  // the lit star under a point of the canvas, in page pixels, or null
  starAt(x, y) {
    const k = SKY_W / this.canvas.clientWidth;
    let best = null;
    for (const s of this.stars) {
      if (!s.glow || !s.text) continue;
      const [sx, sy] = this.position(s);
      const d = Math.hypot(sx - x * k, sy - y * k);
      if (d < 22 && (!best || d < best.d)) best = {s, d};
    }
    return best && best.s;
  }

  // the finale: the figure completes, becomes the constellation of the truth and takes its name; then done()
  finale(truth, done) {
    for (const s of this.stars) s.key = truth.keys.includes(s.text);
    const rest = this.order.filter(s => !s.lit);
    truth.remaining.forEach((text, i) => { if (rest[i]) Object.assign(rest[i], {lit: true, text, key: truth.keys.includes(text)}); });
    const lighting = rest.filter(s => s.lit);
    const t = gsap.timeline({onComplete: done});
    lighting.forEach((s, i) => t.call(() => this.ignite(s, false), null, 0.12 * i));
    const start = 0.12 * lighting.length + 1.4;
    t.to(this.veil, {alpha: 0, duration: 2.4, ease: "power2.inOut"}, start)
     .to(this.shine, {v: 1, duration: 0.7, ease: "sine.out", yoyo: true, repeat: 1}, start + 1.4)
     .to(this.lines, {fade: 0, duration: 0.9}, start + 2.4)
     .to(this.dim, {v: 0.6, duration: 1.8}, start + 2.6)
     .call(() => this.transform(truth.figure), null, start + 2.8)
     // the name: the Night flares, the atlas drawing appears and fades, the name stays
     .call(() => { Object.assign(this.label, {name: truth.name, epithet: truth.epithet}); this.atlas.lines = ATLAS[truth.figure] ? ATLAS[truth.figure]() : []; }, null, start + 6.2)
     .to(this.voice, {flare: 1, duration: 0.8, ease: "power2.out"}, start + 6.2)
     .to(this.atlas, {a: 0.4, duration: 1.4, ease: "sine.inOut"}, start + 6.2)
     .to(this.label, {a: 1, duration: 1.6, ease: "sine.inOut"}, start + 6.8)
     .to(this.voice, {flare: 0, duration: 2.4, ease: "sine.inOut"}, start + 7.4)
     .to(this.atlas, {a: 0, duration: 2, ease: "sine.inOut"}, start + 9.4);
  }

  // every lit star flies to the constellation of the truth; its main stars take the key facts
  transform(name) {
    const stars = this.stars.filter(s => s.lit);
    const figure = FIGURES[name];
    const random = seeded(this.seed + "-truth");
    const main = placeFigure(figure, random);
    const minor = placeMinor(main, figure.edges, Math.max(0, stars.length - main.length), random);
    const angle = p => Math.atan2(p.y - FIGURE_Y, p.x - FIGURE_X);
    const rank = s => (s.key ? 2 : 0) + (s.main ? 1 : 0);
    const byImportance = [...stars].sort((a, b) => rank(b) - rank(a) || b.size - a.size);
    const forMain = byImportance.slice(0, main.length).sort((a, b) => angle(a) - angle(b));
    const forMinor = byImportance.slice(main.length).sort((a, b) => angle(a) - angle(b));
    const mainOrder = main.map((p, i) => ({p, i})).sort((a, b) => angle(a.p) - angle(b.p));
    const placed = [];
    forMain.forEach((s, k) => { placed[mainOrder[k].i] = s; this.flyTo(s, mainOrder[k].p, k, true); });
    [...minor].sort((a, b) => angle(a) - angle(b)).forEach((p, k) => forMinor[k] && this.flyTo(forMinor[k], p, k + main.length, false));
    this.truthLines = figure.edges.map(([a, b]) => ({a: placed[a], b: placed[b], p: 0, fade: 1, from: placed[a]}));
    this.truthLines.forEach((line, i) => gsap.to(line, {p: 1, duration: 1.1, delay: 2.2 + i * 0.22, ease: "power1.inOut"}));
  }

  flyTo(s, goal, i, isMain) {
    const bend = 0.22 * (i % 2 ? 1 : -1);
    s.fly = {q: 0, x0: s.x, y0: s.y, x1: goal.x, y1: goal.y,
      cx: (s.x + goal.x) / 2 - (goal.y - s.y) * bend, cy: (s.y + goal.y) / 2 + (goal.x - s.x) * bend};
    gsap.to(s.fly, {q: 1, duration: STILL ? 0 : 2, delay: i * 0.04, ease: "power3.inOut"});
    // the figure must read: its main stars grow, the minor ones step back; importance shows only now
    gsap.to(s, {scale: isMain ? (s.key ? 1.9 : 1.4) : 0.75, fade: isMain ? 1 : 0.55, duration: 1.2, delay: 2.2, ease: "back.out(2)"});
  }

  position(s) {
    if (!s.fly) return [s.x, s.y];
    const q = s.fly.q, u = 1 - q;
    return [u * u * s.fly.x0 + 2 * u * q * s.fly.cx + q * q * s.fly.x1, u * u * s.fly.y0 + 2 * u * q * s.fly.cy + q * q * s.fly.y1];
  }

  drawLine(ctx, line) {
    if (line.p <= 0 || line.fade <= 0 || !line.a || !line.b) return;
    const from = line.from || line.a, to = from === line.a ? line.b : line.a;
    const [ax, ay] = this.position(from), [bx, by] = this.position(to);
    const ex = ax + (bx - ax) * line.p, ey = ay + (by - ay) * line.p;
    const grad = ctx.createLinearGradient(ax, ay, bx, by);
    grad.addColorStop(0, "rgba(220,232,255,0)");
    grad.addColorStop(0.16, `rgba(220,232,255,${0.5 * line.fade})`);
    grad.addColorStop(0.84, `rgba(220,232,255,${0.5 * line.fade})`);
    grad.addColorStop(1, "rgba(220,232,255,0)");
    ctx.strokeStyle = grad;
    ctx.lineWidth = 0.9;
    ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(ex, ey); ctx.stroke();
    if (line.p < 1) ctx.drawImage(this.cold, ex - 10, ey - 10, 20, 20);   // the light running along the line
  }

  // the Night: a total eclipse; a black disc, a thin rose chromosphere, a white inner corona and long streamers
  drawNight(ctx, time) {
    const v = this.voice;
    const breathe = 1 + 0.06 * Math.sin(time * 1.1);
    const talk = v.speak * (0.12 + 0.12 * Math.sin(time * 8.7) + 0.08 * Math.sin(time * 13.3 + 1));
    const reach = (breathe + talk + 0.9 * v.flare) * (1 - 0.45 * v.listen);   // listening, the corona holds its breath
    const spin = v.think * time * 0.35;
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    const glow = NIGHT_R * (3.4 + v.flare * 1.6);
    ctx.globalAlpha = 0.55 + 0.25 * v.flare;
    ctx.drawImage(this.white, NIGHT_X - glow, NIGHT_Y - glow, glow * 2, glow * 2);
    ctx.globalAlpha = 1;
    for (const s of this.streamers) {
      const a = s.a + spin;
      const len = s.len * reach * (0.85 + 0.15 * Math.sin(time * s.sp + s.ph));
      const x0 = NIGHT_X + Math.cos(a) * NIGHT_R * 0.98, y0 = NIGHT_Y + Math.sin(a) * NIGHT_R * 0.98;
      const x1 = NIGHT_X + Math.cos(a) * (NIGHT_R + len), y1 = NIGHT_Y + Math.sin(a) * (NIGHT_R + len);
      const grad = ctx.createLinearGradient(x0, y0, x1, y1);
      grad.addColorStop(0, `rgba(245,248,255,${s.alpha * 2.2})`);
      grad.addColorStop(1, "rgba(220,232,255,0)");
      ctx.strokeStyle = grad;
      ctx.lineWidth = s.w;
      ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
    }
    const inner = ctx.createRadialGradient(NIGHT_X, NIGHT_Y, NIGHT_R * 0.95, NIGHT_X, NIGHT_Y, NIGHT_R * (1.55 + 0.25 * talk + 0.4 * v.flare));
    inner.addColorStop(0, "rgba(255,252,245,0.95)");
    inner.addColorStop(0.25, "rgba(235,242,255,0.45)");
    inner.addColorStop(1, "rgba(200,220,255,0)");
    ctx.fillStyle = inner;
    ctx.beginPath(); ctx.arc(NIGHT_X, NIGHT_Y, NIGHT_R * 2.2, 0, 2 * Math.PI); ctx.fill();
    // the chromosphere and its prominences: brighter while speaking
    ctx.strokeStyle = `rgba(255,120,150,${0.35 + 0.4 * v.speak + 0.4 * v.flare})`;
    ctx.lineWidth = 1.4;
    ctx.beginPath(); ctx.arc(NIGHT_X, NIGHT_Y, NIGHT_R + 0.6, 0, 2 * Math.PI); ctx.stroke();
    for (const p of this.prominences) {
      const h = p.h * (1 + 0.3 * Math.sin(time * 0.7 + p.ph) + 0.6 * v.speak);
      const x = NIGHT_X + Math.cos(p.a) * (NIGHT_R + h * 0.5), y = NIGHT_Y + Math.sin(p.a) * (NIGHT_R + h * 0.5);
      const grad = ctx.createRadialGradient(x, y, 0, x, y, h * 1.6);
      grad.addColorStop(0, "rgba(255,110,140,0.7)");
      grad.addColorStop(1, "rgba(255,110,140,0)");
      ctx.fillStyle = grad;
      ctx.beginPath(); ctx.arc(x, y, h * 1.6, 0, 2 * Math.PI); ctx.fill();
    }
    ctx.restore();
    // the disc: darker than the sky, with a faint earthshine
    const disc = ctx.createRadialGradient(NIGHT_X - NIGHT_R * 0.3, NIGHT_Y - NIGHT_R * 0.3, 0, NIGHT_X, NIGHT_Y, NIGHT_R);
    disc.addColorStop(0, "#0A0F1C");
    disc.addColorStop(1, "#010205");
    ctx.fillStyle = disc;
    ctx.beginPath(); ctx.arc(NIGHT_X, NIGHT_Y, NIGHT_R, 0, 2 * Math.PI); ctx.fill();
  }

  draw(time) {
    if (!this.stars) return;
    const ctx = this.ctx;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    const night = ctx.createLinearGradient(0, 0, 0, SKY_H);
    night.addColorStop(0, "#04070F");
    night.addColorStop(1, "#0A1226");
    ctx.fillStyle = night;
    ctx.fillRect(0, 0, SKY_W, SKY_H);
    // nebulae
    ctx.globalCompositeOperation = "lighter";
    this.clouds.forEach((cloud, i) => {
      const rgb = [0, 1, 2].map(k => Math.round(cloud.from[k] + (cloud.to[k] - cloud.from[k]) * this.mix.v)).join(",");
      const x = cloud.x + Math.sin(time * 0.05 + i) * 12, y = cloud.y + Math.cos(time * 0.04 + i) * 10;
      const grad = ctx.createRadialGradient(x, y, 0, x, y, cloud.r);
      grad.addColorStop(0, `rgba(${rgb},${0.16 + 0.1 * this.shine.v})`);
      grad.addColorStop(1, `rgba(${rgb},0)`);
      ctx.fillStyle = grad;
      ctx.fillRect(x - cloud.r, y - cloud.r, 2 * cloud.r, 2 * cloud.r);
    });
    // deep sky: the far layers drift slowly, every star breathes at its own pace
    for (const s of this.dust) {
      const drift = STILL ? 0 : s.layer === 0 ? time * 1.2 : s.layer === 1 ? time * 0.5 : 0;
      const x = ((s.x + drift) % SKY_W + SKY_W) % SKY_W;
      const alpha = s.a * this.dim.v * (0.65 + 0.35 * Math.sin(time * s.tw + s.ph)) * (1 + 0.6 * this.shine.v);
      ctx.fillStyle = `rgba(${s.c},${Math.min(alpha, 1)})`;
      if (s.r < 0.7) ctx.fillRect(x - s.r, s.y - s.r, s.r * 2, s.r * 2);
      else { ctx.beginPath(); ctx.arc(x, s.y, s.r, 0, 2 * Math.PI); ctx.fill(); }
    }
    ctx.globalCompositeOperation = "source-over";
    // the veil, cleared around the Night and around every found fact
    if (this.veil.alpha > 0.01) {
      const v = this.veilCanvas.getContext("2d");
      v.setTransform(1, 0, 0, 1, 0, 0);
      v.globalCompositeOperation = "source-over";
      v.clearRect(0, 0, this.veilCanvas.width, this.veilCanvas.height);
      v.globalAlpha = this.veil.alpha;
      v.drawImage(this.fog, 0, 0);
      v.globalAlpha = 1;
      v.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
      v.globalCompositeOperation = "destination-out";
      for (const [x, y, r] of [[NIGHT_X, NIGHT_Y, 140], ...this.stars.map(s => [s.x, s.y, s.reveal.r])]) {
        if (r < 1) continue;
        const grad = v.createRadialGradient(x, y, 0, x, y, r);
        grad.addColorStop(0, "rgba(0,0,0,0.92)");
        grad.addColorStop(0.55, "rgba(0,0,0,0.6)");
        grad.addColorStop(1, "rgba(0,0,0,0)");
        v.fillStyle = grad;
        v.fillRect(x - r, y - r, 2 * r, 2 * r);
      }
      ctx.drawImage(this.veilCanvas, 0, 0, SKY_W, SKY_H);
    }
    if (this.wave && this.wave.a > 0.01) {
      ctx.strokeStyle = `rgba(200,220,255,${this.wave.a})`;
      ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.arc(this.wave.x, this.wave.y, this.wave.r, 0, 2 * Math.PI); ctx.stroke();
    }
    this.drawNight(ctx, time);
    for (const line of this.lines) this.drawLine(ctx, line);
    if (this.truthLines) for (const line of this.truthLines) this.drawLine(ctx, line);
    // the atlas drawing, thin and pale, over the constellation of the truth
    if (this.atlas.a > 0.005 && this.atlas.lines) {
      ctx.save();
      ctx.globalAlpha = this.atlas.a;
      ctx.strokeStyle = "rgb(205,220,250)";
      ctx.lineWidth = 0.9;
      ctx.lineCap = "round";
      ctx.setLineDash([3, 3]);
      for (const line of this.atlas.lines) {
        ctx.beginPath();
        line.forEach(([x, y], i) => ctx[i ? "lineTo" : "moveTo"](FIGURE_X + x * FIGURE_SCALE, FIGURE_Y + y * FIGURE_SCALE));
        ctx.stroke();
      }
      ctx.restore();
    }
    // the name of the constellation, with its epithet
    if (this.label.a > 0.01) {
      ctx.save();
      ctx.globalAlpha = this.label.a;
      ctx.textAlign = "center";
      ctx.fillStyle = "#E4ECFA";
      ctx.font = "500 22px 'Cormorant Garamond', Georgia, serif";
      if ("letterSpacing" in ctx) ctx.letterSpacing = "7px";
      ctx.fillText(this.label.name, FIGURE_X, SKY_H - 32);
      if ("letterSpacing" in ctx) ctx.letterSpacing = "0px";
      ctx.globalAlpha = this.label.a * 0.8;
      ctx.fillStyle = "#B9C8E2";
      ctx.font = "italic 400 15px 'Cormorant Garamond', Georgia, serif";
      ctx.fillText(this.label.epithet, FIGURE_X, SKY_H - 12);
      ctx.restore();
    }
    // the stars of the facts: a glow, a core and the thin spikes of a real star photograph
    for (const s of this.stars) {
      if (s.glow <= 0) continue;
      const [x, y] = this.position(s);
      const pulse = STILL ? 1 : 0.85 + 0.15 * Math.sin(time * s.twinkle + s.phase);
      const k = s.size * s.scale * (1 + 0.5 * this.shine.v);
      const g = s.glow * s.fade;
      const halo = 54 * k * pulse;
      ctx.globalAlpha = 0.8 * g;
      ctx.drawImage(this.warm, x - halo / 2, y - halo / 2, halo, halo);
      const spike = 15 * k * pulse * g;
      ctx.globalAlpha = 0.55 * g;
      for (const [dx, dy] of [[1, 0], [0, 1]]) {
        const grad = ctx.createLinearGradient(x - dx * spike, y - dy * spike, x + dx * spike, y + dy * spike);
        grad.addColorStop(0, "rgba(255,245,225,0)");
        grad.addColorStop(0.5, "rgba(255,245,225,1)");
        grad.addColorStop(1, "rgba(255,245,225,0)");
        ctx.strokeStyle = grad;
        ctx.lineWidth = 0.8;
        ctx.beginPath(); ctx.moveTo(x - dx * spike, y - dy * spike); ctx.lineTo(x + dx * spike, y + dy * spike); ctx.stroke();
      }
      ctx.globalAlpha = g;
      ctx.fillStyle = "#FFFBF2";
      ctx.beginPath(); ctx.arc(x, y, 1.9 * k, 0, 2 * Math.PI); ctx.fill();
      if (s.flash > 0.01) {   // the flash of a new light
        ctx.globalAlpha = s.flash;
        ctx.strokeStyle = "rgba(255,240,215,0.9)";
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.arc(x, y, 6 + (1 - s.flash) * 34, 0, 2 * Math.PI); ctx.stroke();
        const burst = 72 * s.flash;
        ctx.drawImage(this.warm, x - burst / 2, y - burst / 2, burst, burst);
      }
      ctx.globalAlpha = 1;
    }
    // the spark of a hint
    if (this.comet) {
      const c = this.comet, q = c.q, u = 1 - q;
      const x = u * u * c.from.x + 2 * u * q * c.c.x + q * q * c.to.x;
      const y = u * u * c.from.y + 2 * u * q * c.c.y + q * q * c.to.y;
      if (q > 0 && q < 1) c.trail.push([x, y]);
      if (c.trail.length > 26) c.trail.shift();
      const fade = 1 - c.fadeTrail;
      c.trail.forEach(([tx, ty], i) => {
        const k = i / c.trail.length;
        ctx.globalAlpha = k * 0.6 * fade;
        const r = 3 + k * 9;
        ctx.drawImage(this.cold, tx - r, ty - r, r * 2, r * 2);
      });
      ctx.globalAlpha = fade;
      if (q > 0 && q < 1) ctx.drawImage(this.cold, x - 14, y - 14, 28, 28);
      ctx.globalAlpha = 1;
    }
  }
}
