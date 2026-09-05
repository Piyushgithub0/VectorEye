import type { Orthophoto, VectorFeature } from '../types'

const CONFIDENCE_LINE = { high: '#22c55e', medium: '#eab308', low: '#ef4444' } as const

function tier(c: number): keyof typeof CONFIDENCE_LINE {
  if (c >= 0.8) return 'high'
  if (c >= 0.5) return 'medium'
  return 'low'
}

function lonLatToPx(
  lon: number,
  lat: number,
  bounds: [[number, number], [number, number]],
  width: number,
  height: number,
): [number, number] {
  const [[south, west], [north, east]] = bounds
  const x = ((lon - west) / (east - west || 1)) * width
  const y = ((north - lat) / (north - south || 1)) * height
  return [x, y]
}

interface Drawable {
  type: 'polygon' | 'line' | 'point'
  coords: number[][][] // rings for polygon, path for line, single point for point
  color: string
  label: string
}

const LAYER_COLORS: Record<string, string> = {
  buildings: '#38bdf8', // Sky cyan
  roads: '#f59e0b',     // Amber / gold
  water: '#06b6d4',     // Cyan
  trees: '#22c55e',     // Emerald green
  farms: '#ec4899',     // Pink / rose
}

function getFeatureColor(f: VectorFeature): string {
  if (f.type === 'farms' || f.status === 'needs_review') return '#ef4444'
  return LAYER_COLORS[f.type] || CONFIDENCE_LINE[tier(f.confidence)]
}

function featureToDrawable(
  f: VectorFeature,
  bounds: [[number, number], [number, number]],
  width: number,
  height: number,
): Drawable[] {
  const g = f.geometry
  const outc = getFeatureColor(f)
  const toPx = (p: number[]): number[] => {
    const [x, y] = lonLatToPx(p[0], p[1], bounds, width, height)
    return [x, y]
  }
  if (g.type === 'Polygon') {
    return [{
      type: 'polygon',
      coords: g.coordinates.map((ring) => ring.map(toPx)),
      color: outc,
      label: f.type,
    }]
  }
  if (g.type === 'MultiPolygon') {
    return g.coordinates.map((poly) => ({
      type: 'polygon' as const,
      coords: poly.map((ring) => ring.map(toPx)),
      color: outc,
      label: f.type,
    }))
  }
  if (g.type === 'LineString') {
    return [{
      type: 'line',
      coords: [g.coordinates.map(toPx)],
      color: outc,
      label: f.type,
    }]
  }
  if (g.type === 'MultiLineString') {
    return [{
      type: 'line',
      coords: g.coordinates.map((line) => line.map(toPx)),
      color: outc,
      label: f.type,
    }]
  }
  if (g.type === 'Point') {
    return [{
      type: 'point',
      coords: [[toPx(g.coordinates as number[])]],
      color: outc,
      label: f.type,
    }]
  }
  return []
}

/**
 * Export an orthophoto with its approved/non-rejected features drawn on top
 * as a PNG image.
 */
export function exportOrthophotoImage(orthophoto: Orthophoto, features: VectorFeature[]): void {
  const bounds = orthophoto.bounds as [[number, number], [number, number]]
  const image = new Image()
  image.crossOrigin = 'anonymous'
  image.onload = () => {
    const canvas = document.createElement('canvas')
    canvas.width = image.width
    canvas.height = image.height
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    // Draw the orthophoto as the base.
    if (image.width > 0 && image.height > 0) {
      ctx.drawImage(image, 0, 0, image.width, image.height)
    }
    const active = features.filter((f) => f.status !== 'rejected')
    const drawables: Drawable[] = []
    for (const f of active) {
      drawables.push(...featureToDrawable(f, bounds, image.width, image.height))
    }
    for (const d of drawables) {
      if (d.type === 'polygon' || d.type === 'line') {
        for (const path of d.coords) {
          ctx.beginPath()
          ctx.moveTo(path[0][0], path[0][1])
          for (let i = 1; i < path.length; i++) ctx.lineTo(path[i][0], path[i][1])
          ctx.closePath()
          if (d.type === 'polygon') {
            ctx.fillStyle = d.color
            ctx.globalAlpha = 0.35
            ctx.fill()
            ctx.globalAlpha = 1
            ctx.strokeStyle = d.color
            ctx.lineWidth = 2
            ctx.stroke()
          } else {
            ctx.strokeStyle = d.color
            ctx.lineWidth = 3
            ctx.stroke()
          }
        }
      } else if (d.type === 'point') {
        const [cx, cy] = d.coords[0][0]
        ctx.beginPath()
        ctx.arc(cx, cy, 5, 0, Math.PI * 2)
        ctx.fillStyle = d.color
        ctx.fill()
      }
    }
    const a = document.createElement('a')
    a.download = `${orthophoto.filename?.replace(/\.[^.]+$/, '') || 'orthophoto'}-vector-overlay.png`
    a.href = canvas.toDataURL('image/png')
    a.click()
  }
  image.onerror = () => {
    // Fallback: export the raw feature data as JSON so the user isn't left with nothing.
    exportFeaturesJson(orthophoto, features)
  }
  image.src = `/api/orthophoto/${orthophoto.id}/image`
}

export function exportFeaturesJson(orthophoto: Orthophoto, features: VectorFeature[]): void {
  const geoms = features.filter((f) => f.status !== 'rejected')
  const fc = {
    type: 'FeatureCollection',
    features: geoms.map((f) => ({
      type: 'Feature',
      properties: {
        id: f.id,
        class: f.className,
        type: f.type,
        confidence: f.confidence,
        status: f.status,
      },
      geometry: f.geometry,
    })),
  }
  const blob = new Blob([JSON.stringify(fc, null, 2)], { type: 'application/geo+json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${orthophoto.filename?.replace(/\.[^.]+$/, '') || 'orthophoto'}-features.geojson`
  a.click()
  URL.revokeObjectURL(url)
}