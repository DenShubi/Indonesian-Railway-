/**
 * Line chips: one per route, in the route's own colour, toggling its track and trains.
 */
import type { Bundle, RouteId } from '../data/bundle';

export function initLinePanel(
  bundle: Bundle,
  visible: Set<RouteId>,
  onChange: () => void,
): void {
  const root = document.getElementById('lines') as HTMLElement;
  root.innerHTML = `<div class="panel-head">Lines</div>`;

  const list = document.createElement('div');
  list.className = 'chips';

  for (const [routeId, route] of Object.entries(bundle.routes)) {
    const trips = bundle.trips.filter((trip) => trip.r === routeId).length;
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'chip is-on';
    chip.style.setProperty('--chip', route.color);
    chip.innerHTML =
      `<span class="chip-dot"></span><span class="chip-name">${route.name}</span>` +
      `<span class="chip-count">${trips}</span>`;
    chip.addEventListener('click', () => {
      if (visible.has(routeId)) visible.delete(routeId);
      else visible.add(routeId);
      chip.classList.toggle('is-on', visible.has(routeId));
      onChange();
    });
    list.append(chip);
  }

  root.append(list);

  const note = document.createElement('p');
  note.className = 'panel-note';
  note.textContent = 'Click a train or a station for details.';
  root.append(note);
}
