import { useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import type { Feature, FeatureCollection, Geometry } from 'geojson'
import type { Orthophoto, VectorFeature } from '../types'

interface MapViewProps {
  hasProject: boolean
  orthophoto: Orthophoto | null
  features: VectorFeature[]
  visibleTypes: Set<string>
  selectedId: number | null
  onSelectFeature: (feature: VectorFeature) => void
}

function polygonCentroid(geometry: Geometry): Geometry {
  const ty = geometry.type
  let ring: number[][] = []
  if (ty === 'Polygon') ring = geometry.coordinates[0] as number[][]
  else if (ty === 'MultiPolygon') ring = geometry.coordinates[0][0] as number[][]
  else if (ty === 'Point') return geometry
  else if (ty === 'LineString') {
    const c = geometry.coordinates as number[][]
    return { type: 'Point', coordinates: [c[0][0], c[0][1]] }
  }
  if (ring.length === 0) return { type: 'Point', coordinates: [0, 0] }
  let x = 0
  let y = 0
  for (const [lon, lat] of ring) {
    x += lon
    y += lat
  }
  const n = ring.length + 1 // include the closing repeat
  return { type: 'Point', coordinates: [x / n, y / n] }
}

function styleFeature(
  feature: Feature | undefined,
  type: string,
): L.PathOptions {
  const props = feature?.properties ?? {}
  const forcedReview = type === 'farms' || (props.status === 'needs_review')
  const confidenceNum = Number(props.confidence ?? 0)
  const tier =
    confidenceNum >= 0.8
      ? 'high'
      : confidenceNum >= 0.5
      ? 'medium'
      : 'low'

  const base: L.PathOptions = { weight: 1.5, opacity: 0.9 }
  if (forcedReview) {
    return {
      ...base,
      color: '#ef4444',
      dashArray: '6 4',
      fillOpacity: 0.15,
      weight: 2,
    }
  }
  const color = tier === 'high' ? '#22c55e' : tier === 'medium' ? '#eab308' : '#ef4444'
  return { ...base, color, fillColor: color, fillOpacity: 0.35 }
}

export function MapView({
  hasProject,
  orthophoto,
  features,
  visibleTypes,
  selectedId,
  onSelectFeature,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const overlayRef = useRef<L.ImageOverlay | null>(null)
  const layerRefs = useRef<Map<string, L.GeoJSON>>(new Map())
  const selectedRef = useRef<L.Path | null>(null)
  const [dragOver, setDragOver] = useState(false)

  // Initialize map once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = L.map(containerRef.current, {
      zoomControl: true,
      attributionControl: true,
    }).setView([18.52, 73.77], 14)
    mapRef.current = map

    L.tileLayer('https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png?key=cb1_2ub4_1_0c315dcf25af5295a1cbf784', {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>',
      subdomains: 'abcd',
      maxZoom: 19,
    }).addTo(map)

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  // Orthophoto overlay
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (orthophoto?.bounds) {
      if (overlayRef.current) overlayRef.current.remove()
      const bounds = L.latLngBounds(orthophoto.bounds as [number, number][])
      const overlay = L.imageOverlay(
        `/api/orthophoto/${orthophoto?.id}/image`,
        bounds,
        { opacity: 0.95 },
      ).addTo(map)
      overlayRef.current = overlay
      map.fitBounds(bounds as L.LatLngBounds)
    } else if (overlayRef.current) {
      overlayRef.current.remove()
      overlayRef.current = null
    }
  }, [orthophoto])

  // Data-driven layer groups recreated when visible types change
  const layers = useMemo(() => {
    const groups = new Map<string, L.GeoJSON>()
    for (const type of Array.from(visibleTypes)) {
      groups.set(
        type,
        L.geoJSON(null, {
          style: (feature?: Feature) => styleFeature(feature, type),
          pointToLayer: (feature, latlng) => {
            // Distinct shape per type: trees as small green circles, others as
            // polygons (buildings/roads/water/farms render as their geometry).
            if (type === 'trees') {
              return L.circleMarker(latlng, {
                radius: 8,
                weight: 2,
                color: '#22c55e',
                fillColor: '#22c55e',
                fillOpacity: 0.55,
              })
            }
            const col = styleFeature(feature, type).color ?? '#22c55e'
            return L.circleMarker(latlng, {
              radius: 6,
              weight: 1.5,
              color: col,
              fillColor: col,
              fillOpacity: 0.5,
            })
          },
          onEachFeature: (feature: Feature, layer: L.Layer) => {
            layer.on('click', () => {
              onSelectFeature({
                id: feature.properties?.id ?? 0,
                type: feature.properties?.type ?? '',
                className: feature.properties?.className ?? '',
                confidence: Number(feature.properties?.confidence ?? 0),
                status: feature.properties?.status ?? 'pending',
                geometry: feature.geometry,
                created_at: feature.properties?.created_at ?? '',
              } as VectorFeature)
            })
          },
        }),
      )
    }
    return groups
  }, [visibleTypes, onSelectFeature])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    layerRefs.current.forEach((g) => g.remove())
    layerRefs.current.clear()
    layers.forEach((group, type) => {
      const typeFeatures = features.filter((f) => f.type === type && f.status !== 'rejected')
      if (typeFeatures.length > 0) {
        const geojsonFeatures: Feature[] = typeFeatures.map((f) => ({
          type: 'Feature',
          properties: {
            id: f.id,
            class: f.className,
            confidence: f.confidence,
            status: f.status,
            type: f.type,
          },
          // Render trees as distinct circle markers via their polygon centroid.
          geometry: (type === 'trees' ? polygonCentroid(f.geometry) : f.geometry) as Geometry,
        } as Feature))
        group.addData({
          type: 'FeatureCollection',
          features: geojsonFeatures,
        } as FeatureCollection)
        group.addTo(map)
        layerRefs.current.set(type, group)
      }
    })
  }, [layers, mapRef, features])

  // Highlight selected feature
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (selectedRef.current) {
      selectedRef.current.setStyle({ weight: 1.5, opacity: 0.9 })
      selectedRef.current = null
    }
    if (selectedId === null) return
    layerRefs.current.forEach((group) => {
      group.eachLayer((layer: L.Layer) => {
        if (!(layer instanceof L.Path)) return
        const path = layer as L.Path
        const pathEl = path as L.Path & { feature?: Feature }
        const feat = pathEl.feature
        const props = feat?.properties
        if (props && Number(props.id ?? -1) === selectedId) {
          path.setStyle({ weight: 3, opacity: 1 })
          selectedRef.current = path
          const ll = (layer as L.CircleMarker).getLatLng?.()
          if (ll) {
            map.flyToBounds(L.latLngBounds(ll, ll), { padding: [60, 60] })
          } else if (typeof (path as L.Polygon).getBounds === 'function') {
            map.flyToBounds((path as L.Polygon).getBounds(), { padding: [40, 40] })
          }
        }
      })
    })
  }, [selectedId])

  return (
    <div
      ref={containerRef}
      className={`h-full w-full contour-bg ${hasProject ? 'project' : ''} ${dragOver ? 'dragging' : ''}`}
      onDragOver={(e) => {
        e.preventDefault()
        setDragOver(true)
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragOver(false)
      }}
    >
    </div>
  )
}