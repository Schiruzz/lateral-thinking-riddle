// The figures of the constellations, used by sky.js.
// FIGURES: asterisms, a few main stars joined by straight lines, like real constellations; points in a box of
// about 100 around 0,0, bent by the riddle's seed so no two skies are the same.
// ATLAS: the thin drawings shown over a constellation of the truth for a few seconds, like old star maps.

const FIGURES = {
  // the cabin: walls, the line under the roof, a roof wider than the walls; no chimney (it would point at the solution)
  house: {points: [[-28, 32], [28, 31], [29, -2], [0, -33], [-29, -1], [-41, 6], [41, 7]],
          edges: [[0, 1], [1, 2], [0, 4], [4, 2], [5, 3], [3, 6]]},
  // the snowflake: a centre and six arms of uneven length
  snowflake: (() => {
    const points = [[0, 0]], edges = [];
    for (let i = 0; i < 6; i++) {
      const a = -Math.PI / 2 + i * Math.PI / 3;
      points.push([Math.cos(a) * 40, Math.sin(a) * 40]);
      edges.push([0, i + 1]);
    }
    return {points, edges, radial: true};
  })(),
  // the gull: wings bent down at the tips, a short tail
  gull: {points: [[-46, 8], [-28, -12], [-11, -6], [0, 5], [11, -6], [28, -12], [46, 8], [1, 17]],
         edges: [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [3, 7]]},
  // the child: a small figure, head, arms open, legs apart
  child: {points: [[0, -38], [0, -22], [-22, -10], [21, -12], [0, 6], [-13, 36], [12, 35]],
          edges: [[0, 1], [1, 2], [1, 3], [1, 4], [4, 5], [4, 6]]}
};

// a quadratic curve as a polyline
function atlasCurve(p0, c, p1, steps = 14) {
  const out = [];
  for (let i = 0; i <= steps; i++) {
    const t = i / steps, u = 1 - t;
    out.push([u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0], u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1]]);
  }
  return out;
}

function atlasCircle(cx, cy, r, steps = 24) {
  return Array.from({length: steps + 1}, (_, i) => [cx + Math.cos(i / steps * 2 * Math.PI) * r, cy + Math.sin(i / steps * 2 * Math.PI) * r]);
}

const ATLAS = {
  snowflake: () => {
    const lines = [];
    for (let i = 0; i < 6; i++) {
      const a = -Math.PI / 2 + i * Math.PI / 3, d = [Math.cos(a), Math.sin(a)];
      lines.push([[0, 0], [d[0] * 44, d[1] * 44]]);
      for (const [t, len] of [[0.4, 14], [0.68, 9]]) {
        const p = [d[0] * 44 * t, d[1] * 44 * t];
        for (const s of [-1, 1]) {
          const b = a + s * Math.PI / 4;
          lines.push([p, [p[0] + Math.cos(b) * len, p[1] + Math.sin(b) * len]]);
        }
      }
    }
    return lines;
  },
  child: () => [
    atlasCircle(0, -38, 8),
    atlasCurve([-5, -29], [-4, -8], [-3, 8]), atlasCurve([5, -29], [5, -8], [3, 8]),
    atlasCurve([-5, -26], [-15, -20], [-22, -10]), atlasCurve([5, -26], [15, -22], [21, -12]),
    atlasCurve([-3, 8], [-9, 22], [-13, 36]), atlasCurve([3, 8], [8, 22], [12, 35])
  ]
};
