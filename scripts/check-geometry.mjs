/**
 * Sanity check on the animation bundle, run with: npm run verify:geometry
 *
 * Fails on structural problems that would break the animation:
 *   - unknown stop or shape references
 *   - distance along the shape going backwards within a trip
 *   - times going backwards, or departure before arrival
 *
 * Reports (without failing) how far each raw station coordinate sits from the
 * routed track. Anything over a few hundred metres means the shape does not
 * really serve that station, or its coordinate is wrong.
 */
import { readFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const bundle = JSON.parse(await readFile(resolve(root, 'data/bundle.json'), 'utf8'));

function pointAtDist(shape, km) {
  const { c, d } = shape;
  const last = d.length - 1;
  if (km <= d[0]) return c[0];
  if (km >= d[last]) return c[last];
  let lo = 0;
  let hi = last;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (d[mid] <= km) lo = mid;
    else hi = mid;
  }
  const span = d[hi] - d[lo];
  const f = span > 1e-9 ? (km - d[lo]) / span : 0;
  return [c[lo][0] + (c[hi][0] - c[lo][0]) * f, c[lo][1] + (c[hi][1] - c[lo][1]) * f];
}

function haversine(a, b) {
  const p = Math.PI / 180;
  const h =
    Math.sin(((b[1] - a[1]) * p) / 2) ** 2 +
    Math.cos(a[1] * p) * Math.cos(b[1] * p) * Math.sin(((b[0] - a[0]) * p) / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.sqrt(h));
}

const errors = [];
/** stop code -> smallest observed distance from its coordinate to the track */
const offsets = new Map();
let keyframes = 0;

for (const trip of bundle.trips) {
  const shape = bundle.shapes[trip.s];
  if (!shape) {
    errors.push(`${trip.id}: unknown shape ${trip.s}`);
    continue;
  }
  if (!bundle.routes[trip.r]) errors.push(`${trip.id}: unknown route ${trip.r}`);

  let prevDist = -Infinity;
  let prevTime = -Infinity;

  for (const [arrival, departure, distance, code] of trip.k) {
    keyframes += 1;
    const stop = bundle.stops[code];
    if (!stop) {
      errors.push(`${trip.id}: unknown stop ${code}`);
      continue;
    }
    if (distance < prevDist - 1e-6) {
      errors.push(`${trip.id} @ ${code}: distance goes backwards (${distance} < ${prevDist})`);
    }
    if (arrival < prevTime) {
      errors.push(`${trip.id} @ ${code}: arrival ${arrival} precedes previous departure ${prevTime}`);
    }
    if (departure < arrival) errors.push(`${trip.id} @ ${code}: departure precedes arrival`);
    prevDist = distance;
    prevTime = departure;

    const off = haversine(pointAtDist(shape, distance), [stop.x, stop.y]);
    const seen = offsets.get(code);
    if (seen === undefined || off < seen) offsets.set(code, off);
  }
}

const bands = { '<100 m': 0, '100-300 m': 0, '300 m-1 km': 0, '>1 km': 0 };
for (const off of offsets.values()) {
  if (off < 100) bands['<100 m'] += 1;
  else if (off < 300) bands['100-300 m'] += 1;
  else if (off < 1000) bands['300 m-1 km'] += 1;
  else bands['>1 km'] += 1;
}

console.log(`${bundle.trips.length} trips, ${keyframes} keyframes, ${offsets.size} stations called at`);
console.log('\nraw station coordinate vs routed track:');
for (const [band, n] of Object.entries(bands)) console.log(`  ${band.padEnd(12)} ${n}`);

const worst = [...offsets.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
console.log('\nworst offsets (re-source these from OSM):');
for (const [code, off] of worst) {
  console.log(`  ${code.padEnd(5)} ${bundle.stops[code].n.padEnd(22)} ${(off / 1000).toFixed(2)} km`);
}

if (errors.length) {
  console.error(`\n${errors.length} structural problem(s):`);
  for (const line of errors.slice(0, 30)) console.error(`  - ${line}`);
  process.exit(1);
}
console.log('\nstructure OK: references resolve, distances and times are monotonic');
