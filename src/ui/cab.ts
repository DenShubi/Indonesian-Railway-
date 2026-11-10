/**
 * The two headlights on the cab apron.
 *
 * Left lamp shows and hides the lines panel. Right lamp folds the cab away so the
 * map has the whole window, with a small button in the corner to bring it back.
 * It deliberately does not ask the browser for fullscreen: the point is to get the
 * chrome out of the way, and a real fullscreen request can be refused outright, can
 * hang behind a permission prompt, or - inside an embedded frame - never settle at
 * all, which left the button looking broken.
 */
import type { Map as MapLibreMap } from 'maplibre-gl';

export function initCab(map: MapLibreMap): void {
  const linesLamp = document.getElementById('lamp-lines') as HTMLButtonElement;
  const mapLamp = document.getElementById('lamp-full') as HTMLButtonElement;
  const restore = document.getElementById('cab-restore') as HTMLButtonElement;
  const lines = document.getElementById('lines') as HTMLElement;

  /* ---------- left lamp: the lines panel ---------- */

  function setLinesVisible(on: boolean): void {
    lines.classList.toggle('hidden', !on);
    linesLamp.classList.toggle('is-on', on);
    linesLamp.setAttribute('aria-pressed', String(on));
    linesLamp.setAttribute('aria-label', on ? 'Hide the lines panel' : 'Show the lines panel');
  }

  setLinesVisible(true);
  linesLamp.addEventListener('click', () => setLinesVisible(lines.classList.contains('hidden')));

  /* ---------- right lamp: the map takes the window ---------- */

  function setMapOnly(on: boolean): void {
    document.body.classList.toggle('is-immersive', on);
    mapLamp.classList.toggle('is-on', on);
    mapLamp.setAttribute('aria-pressed', String(on));
    mapLamp.setAttribute('aria-label', on ? 'Show the cab again' : 'Fill the window with the map');
    restore.hidden = !on;
    // The windscreen just changed size; MapLibre needs telling, and the border and
    // padding resolve over a frame or two.
    requestAnimationFrame(() => map.resize());
    window.setTimeout(() => map.resize(), 150);
  }

  mapLamp.addEventListener('click', () => {
    setMapOnly(!document.body.classList.contains('is-immersive'));
  });

  restore.addEventListener('click', () => setMapOnly(false));

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && document.body.classList.contains('is-immersive')) {
      setMapOnly(false);
    }
  });
}
