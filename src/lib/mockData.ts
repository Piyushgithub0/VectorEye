import type { VectorFeature } from '../types'

type FeatureType = 'buildings' | 'roads' | 'water' | 'trees' | 'farms'

const base: [number, number] = [18.52, 73.77]

let nextId = 1

function makeFeature(
  type: FeatureType,
  geometry: GeoJSON.Geometry,
  confidence: number,
  status: VectorFeature['status'] = 'pending',
): VectorFeature {
  return {
    id: nextId++,
    type,
    className: type.slice(0, -1),
    confidence,
    status: type === 'farms' ? 'needs_review' : status,
    geometry,
    created_at: new Date().toISOString(),
  }
}

export const DEMO_ORTHOPHOTO = {
  id: 1,
  filename: 'district-14-ortho.tif',
  bounds: [
    [base[0] - 0.02, base[1] - 0.02],
    [base[0] + 0.02, base[1] + 0.02],
  ],
  width: 4096,
  height: 4096,
}

export function buildDemoFeatures(): VectorFeature[] {
  const features: VectorFeature[] = []
  const [cy, cx] = base

  const buildings: [number, number, number, number][] = [
    [0.001, 0.001, 0.0008, 0.0006],
    [0.004, 0.003, 0.0007, 0.0008],
    [-0.003, -0.001, 0.0006, 0.0007],
    [0.006, -0.004, 0.001, 0.0005],
    [-0.005, 0.004, 0.0005, 0.001],
    [0.001, -0.006, 0.0012, 0.0006],
    [0.008, 0.001, 0.0006, 0.0011],
    [-0.004, 0.007, 0.0004, 0.0009],
    [0.004, -0.002, 0.0009, 0.0005],
    [-0.001, 0.002, 0.0005, 0.0007],
  ]
  buildings.forEach(([dx, dy, w, h]) => {
    features.push(
      makeFeature(
        'buildings',
        {
          type: 'Polygon',
          coordinates: [[
            [cx + dx - w, cy + dy - h],
            [cx + dx + w, cy + dy - h],
            [cx + dx + w, cy + dy + h],
            [cx + dx - w, cy + dy + h],
            [cx + dx - w, cy + dy - h],
          ]],
        } as GeoJSON.Polygon,
        Math.random() * 0.3 + 0.5,
        Math.random() > 0.5 ? 'pending' : 'approved',
      ),
    )
  })

  const roads: [number, number][][] = [
    [
      [cx - 0.015, cy - 0.012],
      [cx - 0.008, cy - 0.004],
      [cx, cy],
      [cx + 0.006, cy + 0.005],
      [cx + 0.012, cy + 0.01],
    ],
    [
      [cx + 0.002, cy - 0.012],
      [cx + 0.003, cy - 0.006],
      [cx, cy],
      [cx - 0.005, cy + 0.006],
      [cx - 0.008, cy + 0.012],
    ],
    [
      [cx - 0.012, cy - 0.012],
      [cx - 0.006, cy - 0.006],
      [cx - 0.002, cy],
      [cx - 0.006, cy + 0.006],
      [cx - 0.009, cy + 0.012],
    ],
  ]
  roads.forEach((pts) => {
    features.push(makeFeature('roads', {
      type: 'LineString',
      coordinates: pts,
    } as GeoJSON.LineString, Math.random() * 0.25 + 0.55))
  })

  // Water — a river bend polygon
  const riverPoly: GeoJSON.Polygon = {
    type: 'Polygon',
    coordinates: [
      [
        [cx + 0.009, cy - 0.012],
        [cx + 0.013, cy - 0.008],
        [cx + 0.014, cy - 0.003],
        [cx + 0.013, cy + 0.001],
        [cx + 0.014, cy + 0.005],
        [cx + 0.012, cy + 0.009],
        [cx + 0.009, cy + 0.012],
        [cx + 0.008, cy + 0.008],
        [cx + 0.009, cy + 0.004],
        [cx + 0.01, cy - 0.001],
        [cx + 0.009, cy - 0.006],
        [cx + 0.008, cy - 0.011],
        [cx + 0.009, cy - 0.012],
      ],
    ],
  }
  features.push(makeFeature('water', riverPoly, 0.87, 'pending'))

  // Trees — crown polygons clustered in a grove
  const treeCenters: [number, number][] = [
    [-0.012, -0.008],
    [-0.011, -0.005],
    [-0.014, -0.003],
    [-0.01, -0.001],
    [-0.013, 0.002],
    [-0.011, 0.005],
    [-0.015, 0.007],
    [-0.012, 0.009],
    [-0.009, 0.007],
  ]
  treeCenters.forEach(([dx, dy]) => {
    features.push(
      makeFeature(
        'trees',
        {
          type: 'Polygon',
          coordinates: [[
            [cx + dx - 0.0012, cy + dy - 0.0012],
            [cx + dx + 0.0012, cy + dy - 0.0012],
            [cx + dx + 0.0012, cy + dy + 0.0012],
            [cx + dx - 0.0012, cy + dy + 0.0012],
            [cx + dx - 0.0012, cy + dy - 0.0012],
          ]],
        } as GeoJSON.Polygon,
        Math.random() * 0.3 + 0.5,
      ),
    )
  })

  // Farms — large field polygons, forced to needs_review
  const farmPoly: GeoJSON.Polygon = {
    type: 'Polygon',
    coordinates: [
      [
        [cx - 0.012, cy + 0.013],
        [cx - 0.004, cy + 0.014],
        [cx - 0.003, cy + 0.018],
        [cx - 0.011, cy + 0.017],
        [cx - 0.012, cy + 0.013],
      ],
    ],
  }
  features.push(makeFeature('farms', farmPoly, 0.62))
  const farmPoly2: GeoJSON.Polygon = {
    type: 'Polygon',
    coordinates: [
      [
        [cx + 0.004, cy - 0.014],
        [cx + 0.012, cy - 0.015],
        [cx + 0.013, cy - 0.011],
        [cx + 0.005, cy - 0.01],
        [cx + 0.004, cy - 0.014],
      ],
    ],
  }
  features.push(makeFeature('farms', farmPoly2, 0.55))

  return features
}