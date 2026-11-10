/**
 * The left panel: which network you are looking at, and which of its lines are on.
 *
 * Caveats about a region's timetable edition stay out of here. They are a fact
 * about the data pipeline, they are recorded in the README, and on screen they
 * only amount to telling a reader the project is unfinished.
 */
import type { Network, RegionId, RouteId } from '../data/bundle';

export interface LinePanel {
  /** Re-render the chips, e.g. after the region changed. */
  refresh(): void;
}

export function initLinePanel(
  net: Network,
  visible: Set<RouteId>,
  region: { current: RegionId | null },
  onRegionChange: (id: RegionId | null) => void,
  onLinesChange: () => void,
): LinePanel {
  const root = document.getElementById('lines') as HTMLElement;

  function render(): void {
    root.innerHTML = '';

    const picker = document.createElement('div');
    picker.className = 'regions';
    const entries: Array<[RegionId | null, string]> = [
      [null, 'All Java'],
      ...net.regions.map((r) => [r.id, r.name] as [RegionId, string]),
    ];
    for (const [id, label] of entries) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'btn btn-region' + (region.current === id ? ' is-active' : '');
      button.textContent = label;
      button.addEventListener('click', () => onRegionChange(id));
      picker.append(button);
    }
    root.append(picker);

    const shown = region.current
      ? net.regions.filter((r) => r.id === region.current)
      : net.regions;

    for (const r of shown) {
      const head = document.createElement('div');
      head.className = 'panel-head';
      head.textContent = r.name;
      root.append(head);

      const list = document.createElement('div');
      list.className = 'chips';
      for (const routeId of net.routeIdsByRegion.get(r.id) ?? []) {
        const route = net.bundle.routes[routeId];
        const trips = net.tripsByRoute.get(routeId)?.length ?? 0;
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'chip' + (visible.has(routeId) ? ' is-on' : '');
        chip.style.setProperty('--chip', route.color);
        chip.innerHTML =
          `<span class="chip-dot"></span><span class="chip-name">${route.name}</span>` +
          `<span class="chip-count">${trips}</span>`;
        chip.addEventListener('click', () => {
          if (visible.has(routeId)) visible.delete(routeId);
          else visible.add(routeId);
          chip.classList.toggle('is-on', visible.has(routeId));
          onLinesChange();
        });
        list.append(chip);
      }
      root.append(list);
    }

    const hint = document.createElement('p');
    hint.className = 'panel-note';
    hint.textContent = 'Click a train or a station for details.';
    root.append(hint);
  }

  render();
  return { refresh: render };
}
