/**
 * Trains, drawn as instanced 3D boxes inside a MapLibre custom layer.
 *
 * The layer works in web-mercator units: [0,0] is the top-left of the mercator
 * world, [1,1] the bottom-right, and with renderingMode '3d' the z axis is
 * conformal, so a cube with equal x/y/z lengths renders as a cube. One metre is
 * MercatorCoordinate.meterInMercatorCoordinateUnits() at a given latitude.
 *
 * Everything lives in a single InstancedMesh, so the whole fleet costs one draw
 * call and the layer stays cheap even if the network grows to every line on Java.
 */
import { MercatorCoordinate } from 'maplibre-gl';
import type { CustomLayerInterface, CustomRenderMethodInput, Map as MapLibreMap, Point } from 'maplibre-gl';
import {
  AmbientLight,
  BoxGeometry,
  Camera,
  Color,
  DirectionalLight,
  InstancedMesh,
  Matrix4,
  MeshLambertMaterial,
  Quaternion,
  Scene,
  Vector3,
  WebGLRenderer,
} from 'three';
import type { TrainState } from '../sim/trains';

/** Room for far more trains than Wilayah 8 runs, so expansion needs no change here. */
const CAPACITY = 512;

/** True-to-life proportions in metres: a short commuter set. */
const TRAIN_LENGTH = 80;
const TRAIN_WIDTH = 3.2;
const TRAIN_HEIGHT = 4.2;
/** Lift the body off the ground plane so it does not z-fight with the track line. */
const RAIL_HEIGHT = 1.6;
/**
 * A real train is a hairline on screen below about zoom 16 - 3.2 m is well under
 * one pixel at city scale - so the body is never drawn smaller than this, the way
 * Mini Tokyo 3D keeps its vehicles legible when zoomed out.
 *
 * The floor itself eases down as the view pulls back: at region scale a 20 px
 * vehicle is a sensible marker, but with a whole island on screen the same 20 px
 * swamps the line it is running on.
 */
const MIN_PIXEL_LENGTH = 20;
const MIN_PIXEL_WIDTH = 5;
const MIN_PIXEL_HEIGHT = 3.5;
/** Fraction of the minimum sizes used at the widest zooms. */
const FAR_SHRINK = 0.45;

function pixelFloorScale(zoom: number): number {
  const t = Math.max(0, Math.min(1, (zoom - 7.5) / 3.5));
  return FAR_SHRINK + (1 - FAR_SHRINK) * t;
}
/** Metres per CSS pixel in web mercator at a given zoom and latitude. */
function metresPerPixel(zoom: number, lat: number): number {
  return (156543.03392 * Math.cos((lat * Math.PI) / 180)) / 2 ** zoom;
}

export class TrainLayer implements CustomLayerInterface {
  readonly id = 'jtv-trains';
  readonly type = 'custom' as const;
  readonly renderingMode = '3d' as const;

  private map!: MapLibreMap;
  private renderer!: WebGLRenderer;
  private scene!: Scene;
  private camera!: Camera;
  private mesh!: InstancedMesh;

  private states: TrainState[] = [];
  private selectedId: string | null = null;
  private colors = new Map<string, Color>();

  private readonly matrix = new Matrix4();
  private readonly position = new Vector3();
  private readonly quaternion = new Quaternion();
  private readonly scale = new Vector3();
  private readonly zAxis = new Vector3(0, 0, 1);
  private readonly tint = new Color();

  /** Frames drawn, for debugging from the console. */
  frames = 0;

  /** routeId -> colour, taken from the bundle. */
  constructor(routeColors: Record<string, string>) {
    for (const [route, hex] of Object.entries(routeColors)) {
      this.colors.set(route, new Color(hex));
    }
  }

  onAdd(map: MapLibreMap, gl: WebGL2RenderingContext): void {
    this.map = map;
    this.camera = new Camera();
    this.scene = new Scene();

    this.scene.add(new AmbientLight(0xffffff, 1.9));
    const sun = new DirectionalLight(0xffffff, 1.4);
    sun.position.set(-0.4, -0.9, 1.6);
    this.scene.add(sun);

    const geometry = new BoxGeometry(1, 1, 1);
    const material = new MeshLambertMaterial();
    this.mesh = new InstancedMesh(geometry, material, CAPACITY);
    this.mesh.count = 0;
    this.mesh.frustumCulled = false;
    this.scene.add(this.mesh);

    this.renderer = new WebGLRenderer({ canvas: map.getCanvas(), context: gl });
    this.renderer.autoClear = false;
  }

  onRemove(): void {
    this.mesh.geometry.dispose();
    (this.mesh.material as MeshLambertMaterial).dispose();
    this.renderer.dispose();
  }

  /** Hands the layer the fleet to draw on the next frame. */
  setTrains(states: TrainState[], selectedId: string | null): void {
    this.states = states;
    this.selectedId = selectedId;
    this.syncInstances();
  }

  /**
   * Nearest train to a point in screen pixels, within `radius`.
   * Screen-space picking rather than a raycast: with a projection matrix handed
   * to us by MapLibre there is no three.js camera to raycast from, and this
   * matches what the user sees.
   */
  pick(point: Point, radius = 24): TrainState | null {
    if (!this.map) return null;
    let best: TrainState | null = null;
    let bestDist = radius * radius;
    for (const state of this.states) {
      const screen = this.map.project([state.lon, state.lat]);
      const dx = screen.x - point.x;
      const dy = screen.y - point.y;
      const dist = dx * dx + dy * dy;
      if (dist < bestDist) {
        bestDist = dist;
        best = state;
      }
    }
    return best;
  }

  private syncInstances(): void {
    if (!this.map) return;
    const zoom = this.map.getZoom();

    const count = Math.min(this.states.length, CAPACITY);
    for (let i = 0; i < count; i++) {
      const state = this.states[i];
      const merc = MercatorCoordinate.fromLngLat([state.lon, state.lat], 0);
      const metre = merc.meterInMercatorCoordinateUnits();
      const mpp = metresPerPixel(zoom, state.lat) * pixelFloorScale(zoom);
      const selected = state.trip.id === this.selectedId;
      const bump = selected ? 1.35 : 1;
      const lengthM = Math.max(TRAIN_LENGTH, MIN_PIXEL_LENGTH * mpp) * bump;
      const widthM = Math.max(TRAIN_WIDTH, MIN_PIXEL_WIDTH * mpp) * bump;
      const heightM = Math.max(TRAIN_HEIGHT, MIN_PIXEL_HEIGHT * mpp);

      // Mercator axes are x=east, y=south, so a geographic bearing b points along
      // (sin b, -cos b); rotate the box's local +x onto it.
      const angle = Math.atan2(-Math.cos(state.bearing), Math.sin(state.bearing));

      this.position.set(merc.x, merc.y, merc.z + (RAIL_HEIGHT + heightM / 2) * metre);
      this.quaternion.setFromAxisAngle(this.zAxis, angle);
      this.scale.set(lengthM * metre, widthM * metre, heightM * metre);
      this.matrix.compose(this.position, this.quaternion, this.scale);
      this.mesh.setMatrixAt(i, this.matrix);

      const base = this.colors.get(state.trip.r) ?? new Color('#cccccc');
      this.tint.copy(base);
      if (selected) this.tint.lerp(new Color('#ffffff'), 0.45);
      else if (state.dwelling) this.tint.lerp(new Color('#ffffff'), 0.22);
      this.mesh.setColorAt(i, this.tint);
    }

    this.mesh.count = count;
    this.mesh.instanceMatrix.needsUpdate = true;
    if (this.mesh.instanceColor) this.mesh.instanceColor.needsUpdate = true;
  }

  render(_gl: WebGL2RenderingContext, options: CustomRenderMethodInput): void {
    this.frames += 1;
    if (this.mesh.count === 0) return;
    // mainMatrix maps mercator world coordinates straight to clip space, which is
    // all a mercator-only custom layer needs.
    this.camera.projectionMatrix = new Matrix4().fromArray(
      Array.from(options.defaultProjectionData.mainMatrix),
    );
    this.renderer.resetState();
    this.renderer.render(this.scene, this.camera);
  }
}
