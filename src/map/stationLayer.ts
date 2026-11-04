/**
 * Stations: a dot per stop plus a label that appears once the view is zoomed in
 * enough for the names not to collide.
 */
import type { Map as MapLibreMap } from 'maplibre-gl';
import type { FeatureCollection, Point } from 'geojson';
import type { Network, RegionId, StopCode } from '../data/bundle';

export const STATION_SOURCE = 'jtv-stations';
export const STATION_CIRCLE_LAYER = 'jtv-station-circle';
export const STATION_LABEL_LAYER = 'jtv-station-label';

interface StationProps {
  code: StopCode;
  name: string;
  region: RegionId;
}

function toGeoJSON(net: Network): FeatureCollection<Point, StationProps> {
  return {
    type: 'FeatureCollection',
    features: Object.entries(net.bundle.stops).map(([code, stop]) => {
      // Drawn where trains stop, not at the raw coordinate - see snapStations().
      const at = net.stationPositions.get(code);
      return {
        type: 'Feature' as const,
        geometry: { type: 'Point' as const, coordinates: [at?.lon ?? stop.x, at?.lat ?? stop.y] },
        properties: { code, name: stop.n, region: stop.g },
      };
    }),
  };
}

export function addStationLayers(map: MapLibreMap, net: Network): void {
  map.addSource(STATION_SOURCE, { type: 'geojson', data: toGeoJSON(net) });

  map.addLayer({
    id: STATION_CIRCLE_LAYER,
    type: 'circle',
    source: STATION_SOURCE,
    paint: {
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 7, 2.6, 11, 4.5, 15, 7],
      'circle-color': '#ffffff',
      'circle-stroke-color': '#24303a',
      'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 7, 1, 13, 2],
      'circle-pitch-alignment': 'map',
    },
  });

  map.addLayer({
    id: STATION_LABEL_LAYER,
    type: 'symbol',
    source: STATION_SOURCE,
    minzoom: 9,
    layout: {
      'text-field': ['get', 'name'],
      'text-font': ['Noto Sans Bold'],
      'text-size': ['interpolate', ['linear'], ['zoom'], 9, 10, 14, 13],
      'text-offset': [0, 1.1],
      'text-anchor': 'top',
      'text-padding': 4,
    },
    paint: {
      'text-color': '#16222b',
      'text-halo-color': 'rgba(255,255,255,0.92)',
      'text-halo-width': 1.6,
    },
  });
}

/** Show only the given regions' stations; an empty set means show them all. */
export function setVisibleStationRegions(map: MapLibreMap, regions: Set<RegionId>): void {
  const filter = regions.size
    ? (['in', ['get', 'region'], ['literal', [...regions]]] as never)
    : null;
  for (const id of [STATION_CIRCLE_LAYER, STATION_LABEL_LAYER]) {
    if (map.getLayer(id)) map.setFilter(id, filter);
  }
}

export function enableStationHover(map: MapLibreMap): void {
  map.on('mouseenter', STATION_CIRCLE_LAYER, () => {
    map.getCanvas().style.cursor = 'pointer';
  });
  map.on('mouseleave', STATION_CIRCLE_LAYER, () => {
    map.getCanvas().style.cursor = '';
  });
}
