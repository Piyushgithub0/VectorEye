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
          onEachFeature: (feature: Feature, layer: L.Layer) => {
            if (layer instanceof L.Path) {
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
            }
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
          },
          geometry: f.geometry as Geometry,
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
          map.flyToBounds((path as L.Polygon).getBounds(), { padding: [40, 40] })
        }
      })
    })
  }, [selectedId])

  return (
    <div
      ref={containerRef}
      className="h-full w-full contour-bg"
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
      {!hasProject && (
        <div
          className={`absolute inset-0 z-[1000] flex items-center justify-center ${
            dragOver ? 'bg-cyan-400/10' : ''
          }`}
        >
          <div
            className={`panel rounded-lg px-10 py-8 text-center transition-colors ${
              dragOver ? 'border-2 border-dashed border-cyan-400' : ''
            }`}
          >
            <div className="mx-auto mb-4 h-12 w-12 text-cyan-400">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                className="h-full w-full"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5"
                />
              </svg>
            </div>
            <p className="text-sm font-medium text-text-primary">Drop an orthophoto to begin</p>
            <p className="mt-1 font-mono text-[11px] text-text-muted">Supports GeoTIFF</p>
            <p className="mt-3 font-mono text-[10px] text-text-muted opacity-60">
              POST /upload &middot; EPSG:32643
            </p>
          </div>
        </div>
      )}
    </div>
  )
}