// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

window.seeker = (() => {
  const canvas = document.getElementById("seeker");
  if (!canvas) return { run() {} };
  const ctx = canvas.getContext("2d");
  const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const GOLD = tint("gold"), CYAN = tint("cyan"), BRONZE = tint("bronze");
  const CELL = 12;
  const MODES = [
    { name: "Arcane ripple", hue: CYAN, bias: 0 },
    { name: "Hunter's instinct", hue: tint("orange"), bias: 1 },
  ];

  let running = false, raf = 0, round = 0, stopAt = 0;
  let w = 0, h = 0, cols = 0, rows = 0, dpr = 1;
  let wall, dist, came, seen, open, start, goal, mode, phase, trail, t0, doneAt;

  function size() {
    dpr = window.devicePixelRatio || 1;
    w = canvas.clientWidth; h = canvas.clientHeight;
    canvas.width = Math.max(1, Math.round(w * dpr)); canvas.height = Math.max(1, Math.round(h * dpr));
    cols = Math.max(8, Math.floor(w / CELL)); rows = Math.max(5, Math.floor(h / CELL));
  }

  const idx = (c, r) => r * cols + c;

  function newRound() {
    size();
    mode = MODES[round++ % MODES.length];
    for (let tries = 0; tries < 20; tries++) {
      wall = new Uint8Array(cols * rows);
      const clumps = Math.round(cols * rows / 26);
      for (let k = 0; k < clumps; k++) {
        let c = Math.floor(Math.random() * cols), r = Math.floor(Math.random() * rows);
        for (let s = 0; s < 5; s++) {
          if (c >= 0 && c < cols && r >= 0 && r < rows) wall[idx(c, r)] = 1;
          c += Math.floor(Math.random() * 3) - 1; r += Math.floor(Math.random() * 3) - 1;
        }
      }
      start = idx(1 + Math.floor(Math.random() * 3), Math.floor(Math.random() * rows));
      goal = idx(cols - 2 - Math.floor(Math.random() * 3), Math.floor(Math.random() * rows));
      wall[start] = 0; wall[goal] = 0;
      if (reachable()) break;
    }
    dist = new Float32Array(cols * rows).fill(Infinity);
    came = new Int32Array(cols * rows).fill(-1);
    seen = new Float32Array(cols * rows);
    dist[start] = 0;
    open = [start];
    phase = "search"; trail = []; t0 = performance.now(); doneAt = 0;
  }

  function neighbours(i) {
    const c = i % cols, r = (i - c) / cols, out = [];
    for (const [dc, dr] of [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [1, -1], [-1, 1], [-1, -1]]) {
      const nc = c + dc, nr = r + dr;
      if (nc < 0 || nc >= cols || nr < 0 || nr >= rows) continue;
      const j = idx(nc, nr);
      if (wall[j] || (dc && dr && (wall[idx(c + dc, r)] || wall[idx(c, r + dr)]))) continue;
      out.push([j, dc && dr ? Math.SQRT2 : 1]);
    }
    return out;
  }

  function reachable() {
    const seenR = new Uint8Array(cols * rows), stack = [start];
    seenR[start] = 1;
    while (stack.length) {
      const i = stack.pop();
      if (i === goal) return true;
      for (const [j] of neighbours(i)) if (!seenR[j]) { seenR[j] = 1; stack.push(j); }
    }
    return false;
  }

  const guess = (i) => {
    const c = i % cols, r = (i - c) / cols, gc = goal % cols, gr = (goal - gc) / cols;
    return Math.hypot(c - gc, r - gr);
  };

  function step(now, n) {
    for (let k = 0; k < n && open.length; k++) {
      let best = 0, bestF = Infinity;
      for (let q = 0; q < open.length; q++) {
        const f = dist[open[q]] + mode.bias * guess(open[q]);
        if (f < bestF) { bestF = f; best = q; }
      }
      const i = open.splice(best, 1)[0];
      if (seen[i]) continue;
      seen[i] = now;
      if (i === goal) {
        for (let j = goal; j !== -1; j = came[j]) trail.unshift(j);
        phase = "thread"; doneAt = now;
        return;
      }
      for (const [j, cost] of neighbours(i)) {
        if (seen[j] || dist[i] + cost >= dist[j]) continue;
        dist[j] = dist[i] + cost; came[j] = i;
        open.push(j);
      }
    }
    if (!open.length) newRound();
  }

  const centre = (i) => { const c = i % cols, r = (i - c) / cols; return [(c + 0.5) * w / cols, (r + 0.5) * h / rows]; };

  function draw(now) {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const cw = w / cols, ch = h / rows;
    for (let i = 0; i < cols * rows; i++) {
      const [x, y] = centre(i);
      if (wall[i]) {
        ctx.fillStyle = tint("black", 0.55);
        ctx.fillRect(x - cw / 2 + 1, y - ch / 2 + 1, cw - 2, ch - 2);
        ctx.strokeStyle = BRONZE; ctx.globalAlpha = 0.35;
        ctx.strokeRect(x - cw / 2 + 1.5, y - ch / 2 + 1.5, cw - 3, ch - 3);
        ctx.globalAlpha = 1;
        continue;
      }
      if (seen[i]) {
        const age = (now - seen[i]) / 1000, flare = Math.max(0, 1 - age * 2.2);
        ctx.globalAlpha = 0.18 + 0.6 * flare;
        ctx.strokeStyle = mode.hue; ctx.lineWidth = 1;
        const s = Math.min(cw, ch) * (0.22 + 0.12 * flare);
        ctx.beginPath();
        ctx.moveTo(x, y - s); ctx.lineTo(x + s, y); ctx.lineTo(x, y + s); ctx.lineTo(x - s, y); ctx.closePath();
        ctx.moveTo(x - s * 0.5, y); ctx.lineTo(x + s * 0.5, y);
        ctx.stroke();
      } else {
        ctx.globalAlpha = 0.12; ctx.fillStyle = BRONZE;
        ctx.fillRect(x - 0.75, y - 0.75, 1.5, 1.5);
      }
      ctx.globalAlpha = 1;
    }
    for (const i of open) {
      if (seen[i]) continue;
      const [x, y] = centre(i), r = Math.min(cw, ch) * 0.7;
      const g = ctx.createRadialGradient(x, y, 0, x, y, r);
      g.addColorStop(0, mode.hue); g.addColorStop(1, tint("black", 0));
      ctx.globalAlpha = 0.45 + 0.25 * Math.sin(now / 140 + i);
      ctx.fillStyle = g; ctx.fillRect(x - r, y - r, r * 2, r * 2);
      ctx.globalAlpha = 1;
    }
    if (phase === "thread" && trail.length) {
      const shown = Math.min(trail.length, Math.floor((now - doneAt) / 45) + 1);
      ctx.strokeStyle = GOLD; ctx.lineWidth = 2; ctx.shadowColor = GOLD; ctx.shadowBlur = 8;
      ctx.beginPath();
      trail.slice(0, shown).forEach((i, k) => { const [x, y] = centre(i); if (k) ctx.lineTo(x, y); else ctx.moveTo(x, y); });
      ctx.stroke();
      ctx.shadowBlur = 0;
      const [sx, sy] = centre(trail[shown - 1]);
      ctx.fillStyle = tint("glint"); ctx.beginPath(); ctx.arc(sx, sy, 2.2, 0, Math.PI * 2); ctx.fill();
      if (now - doneAt > trail.length * 45 + 1100) newRound();
    }
    const [fx, fy] = centre(start), flick = 1 + 0.25 * Math.sin(now / 90);
    const fire = ctx.createRadialGradient(fx, fy, 0, fx, fy, 7 * flick);
    fire.addColorStop(0, tint("fire-core")); fire.addColorStop(0.4, tint("orange")); fire.addColorStop(1, tint("fire-end", 0));
    ctx.fillStyle = fire; ctx.fillRect(fx - 8, fy - 8, 16, 16);
    const [gx, gy] = centre(goal), tw = 5 + 1.5 * Math.sin(now / 200);
    ctx.fillStyle = GOLD; ctx.shadowColor = GOLD; ctx.shadowBlur = 10;
    ctx.beginPath();
    for (let k = 0; k < 8; k++) {
      const a = k * Math.PI / 4, r = k % 2 ? tw * 0.35 : tw;
      ctx.lineTo(gx + Math.sin(a) * r, gy - Math.cos(a) * r);
    }
    ctx.closePath(); ctx.fill(); ctx.shadowBlur = 0;
    ctx.font = "italic 10px Marcellus, Georgia, serif"; ctx.textAlign = "right"; ctx.fillStyle = mode.hue; ctx.globalAlpha = 0.6;
    ctx.fillText(mode.name, w - 6, h - 6);
    ctx.globalAlpha = 1;
  }

  function frame(now) {
    if (!running && now > stopAt) { raf = 0; return; }
    if (phase === "search") step(now, still ? 0 : 3);
    draw(now);
    raf = still ? 0 : askFrame(frame);
  }

  return {
    run(on) {
      if (on === running) return;
      running = on;
      if (on) {
        if (!wall || canvas.clientWidth !== w || canvas.clientHeight !== h) newRound();
        if (still) {
          newRound();
          for (let k = 0; k < 400 && phase === "search"; k++) step(performance.now(), 1);
          doneAt = performance.now() - trail.length * 45 - 10;
          draw(performance.now());
          return;
        }
        if (!raf) raf = askFrame(frame);
      } else {
        stopAt = performance.now() + 700;
      }
    },
  };
})();
