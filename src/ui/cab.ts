/**
 * The two headlights on the cab apron, and the immersive view they lead to.
 *
 * Left lamp shows and hides the lines panel. Right lamp asks for browser
 * fullscreen and folds the cab away, so the windscreen becomes the whole
 * display; a small button in the corner brings it back. Fullscreen can be
 * refused - an iframe without `allow="fullscreen"`, or iOS Safari on iPhone,
 * where the API does not exist - and the request can simply never settle, so the
 * cab folds away first and the browser is asked afterwards. The view gains the
 * chrome's space either way.
 */
import type { Map as MapLibreMap } from 'maplibre-gl';

export function initCab(map: MapLibreMap): void {
  const linesLamp = document.getElementById('lamp-lines') as HTMLButtonElement;
  const fullLamp = document.getElementById('lamp-full') as HTMLButtonElement;
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

  /* ---------- right lamp: immersive ---------- */

  function setImmersive(on: boolean): void {
    document.body.classList.toggle('is-immersive', on);
    fullLamp.classList.toggle('is-on', on);
    fullLamp.setAttribute('aria-pressed', String(on));
    fullLamp.setAttribute('aria-label', on ? 'Leave fullscreen' : 'Fill the screen with the map');
    restore.hidden = !on;
    // The windscreen just changed size; MapLibre needs telling, and the border
    // and padding animate away over a frame or two.
    requestAnimationFrame(() => map.resize());
    window.setTimeout(() => map.resize(), 150);
  }

  fullLamp.addEventListener('click', () => {
    const entering = !document.body.classList.contains('is-immersive');
    // Fold the cab first and ask the browser afterwards. Awaiting the request
    // would make the whole button depend on it, and it can hang behind a
    // permission prompt or never settle at all inside an embedded frame.
    setImmersive(entering);
    void (async () => {
      try {
        if (entering) await document.documentElement.requestFullscreen?.();
        else if (document.fullscreenElement) await document.exitFullscreen();
      } catch {
        // Refused or unsupported: the view already has the cab's space.
      }
    })();
  });

  restore.addEventListener('click', () => {
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => {});
    setImmersive(false);
  });

  // Escape leaves fullscreen without going through our buttons.
  document.addEventListener('fullscreenchange', () => {
    if (!document.fullscreenElement && document.body.classList.contains('is-immersive')) {
      setImmersive(false);
    }
  });
}
