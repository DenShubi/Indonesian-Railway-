// Copies the animation bundle produced by the Python pipeline into public/,
// so data/bundle.json stays the single source of truth.
import { copyFile, mkdir, stat } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const src = resolve(root, 'data/bundle.json');
const dest = resolve(root, 'public/data/bundle.json');

try {
  await stat(src);
} catch {
  console.error(`[sync:data] missing ${src} — run the Python pipeline first (scripts/make_bundle.py)`);
  process.exit(1);
}

await mkdir(dirname(dest), { recursive: true });
await copyFile(src, dest);
const { size } = await stat(dest);
console.log(`[sync:data] public/data/bundle.json  ${(size / 1024).toFixed(0)} KB`);
