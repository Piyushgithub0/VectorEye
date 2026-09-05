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
  onApprove?: (id: number) => void
  onReject?: (id: number) => void
  editing?: boolean
  onToggleEdit?: () => void
  onUpdateFeatureGeometry?: (id: number, geometry: Geometry) => void
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
  if (type === 'water') {
    return {
      ...base,
      color: '#06b6d4',
      fillColor: '#06b6d4',
      fillOpacity: 0.45,
      weight: 2,
    }
  }
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
  onApprove,
  onReject,
  editing = false,
  onToggleEdit,
  onUpdateFeatureGeometry,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const overlayRef = useRef<L.ImageOverlay | null>(null)
  const currentOrthoIdRef = useRef<number | null>(null)
  const editMarkersRef = useRef<L.LayerGroup | null>(null)
  const layerRefs = useRef<Map<string, L.GeoJSON>>(new Map())
  const selectedRef = useRef<L.Path | null>(null)
  const [dragOver, setDragOver] = useState(false)

  useEffect(() => {
    ;(window as any)._veApprove = (id: number) => {
      onApprove?.(id)
      mapRef.current?.closePopup()
    }
    ;(window as any)._veReject = (id: number) => {
      onReject?.(id)
      mapRef.current?.closePopup()
    }
    return () => {
      delete (window as any)._veApprove
      delete (window as any)._veReject
    }
  }, [onApprove, onReject])

  // Initialize map once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = L.map(containerRef.current, {
      zoomControl: true,
      attributionControl: true,
      preferCanvas: true, // HTML5 Canvas for silky smooth vector rendering without GPU memory bloat
    }).setView([18.52, 73.77], 14)
    mapRef.current = map

    // Dedicated pane for orthophoto between basemap (200) and vector layers (400)
    const orthoPane = map.createPane('orthoPane')
    orthoPane.style.zIndex = '300'
    orthoPane.style.pointerEvents = 'none'

    const satelliteLayer = L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      {
        attribution:
          '&copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
        maxZoom: 19,
      },
    )

    const streetLayer = L.tileLayer(
      'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      {
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19,
      },
    )

    satelliteLayer.addTo(map)

    L.control
      .layers(
        {
          'Satellite (Esri)': satelliteLayer,
          'Streets (OSM)': streetLayer,
        },
        undefined,
        { position: 'topright' },
      )
      .addTo(map)

    // Automatically adjust map viewport when container resizes
    let ro: ResizeObserver | null = null
    if (window.ResizeObserver && containerRef.current) {
      ro = new ResizeObserver(() => {
        map.invalidateSize()
      })
      ro.observe(containerRef.current)
    }

    // Delayed initial invalidate to ensure layout is ready
    const timer = window.setTimeout(() => {
      map.invalidateSize()
    }, 150)

    return () => {
      window.clearTimeout(timer)
      if (ro) ro.disconnect()
      if (editMarkersRef.current) {
        editMarkersRef.current.remove()
        editMarkersRef.current = null
      }
      overlayRef.current = null
      currentOrthoIdRef.current = null
      map.remove()
      mapRef.current = null
    }
  }, [])

  // Invalidate map size when hasProject changes
  useEffect(() => {
    if (mapRef.current) {
      mapRef.current.invalidateSize()
    }
  }, [hasProject])

  // Orthophoto overlay - cached by ID so it NEVER tears down on unrelated state changes
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    if (orthophoto?.bounds && Array.isArray(orthophoto.bounds) && orthophoto.bounds.length === 2) {
      // If we already have the overlay loaded for this exact orthophoto ID, retain it firmly
      if (overlayRef.current && currentOrthoIdRef.current === orthophoto.id) {
        return
      }

      if (overlayRef.current) {
        overlayRef.current.remove()
        overlayRef.current = null
      }

      const raw = orthophoto.bounds as [number, number][]
      const south = Math.min(raw[0][0], raw[1][0])
      const north = Math.max(raw[0][0], raw[1][0])
      const west = Math.min(raw[0][1], raw[1][1])
      const east = Math.max(raw[0][1], raw[1][1])

      if (isNaN(south) || isNaN(north) || isNaN(west) || isNaN(east)) return
      if (south === north || west === east) return

      const bounds = L.latLngBounds([south, west], [north, east])
      const overlay = L.imageOverlay(
        `/api/orthophoto/${orthophoto.id}/image`,
        bounds,
        { opacity: 0.95, pane: 'orthoPane', interactive: false },
      )

      overlay.on('load', () => {
        // Overlay loaded smoothly
      })
      overlay.on('error', () => {
        console.warn('Orthophoto image overlay failed to load')
      })

      overlay.addTo(map)
      overlayRef.current = overlay
      currentOrthoIdRef.current = orthophoto.id
      map.fitBounds(bounds, { padding: [30, 30], maxZoom: 18, animate: false })
    } else if (overlayRef.current) {
      overlayRef.current.remove()
      overlayRef.current = null
      currentOrthoIdRef.current = null
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
            // Distinct shape per type: trees as green circles, others as styled circles
            if (type === 'trees') {
              return L.circleMarker(latlng, {
                radius: 7,
                weight: 1.5,
                color: '#22c55e',
                fillColor: '#22c55e',
                fillOpacity: 0.6,
              })
            }
            // Distinct shape per type: trees as green circles, water as cyan, others as styled circles
            if (type === 'trees') {
              return L.circleMarker(latlng, {
                radius: 7,
                weight: 1.5,
                color: '#22c55e',
                fillColor: '#22c55e',
                fillOpacity: 0.6,
              })
            }
            if (type === 'water') {
              return L.circleMarker(latlng, {
                radius: 7,
                weight: 1.5,
                color: '#06b6d4',
                fillColor: '#06b6d4',
                fillOpacity: 0.6,
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
            const props = feature.properties || {}
            const featId = props.id ?? 0
            const featType = props.type || type
            const confPct = Math.round(Number(props.confidence ?? 0) * 100)
            const status = props.status || 'pending'
            const statusCol = status === 'approved' ? '#10b981' : status === 'needs_review' ? '#f59e0b' : '#ef4444'

            layer.bindTooltip(
              `<div style="font-family: monospace; font-size: 11px;">
                <strong>#${featId} ${props.class || featType}</strong><br/>
                <span>Confidence: <strong>${confPct}%</strong></span><br/>
                <span style="color: ${statusCol}; text-transform: uppercase;">● ${status}</span>
              </div>`,
              { sticky: true, opacity: 0.95 }
            )

            layer.bindPopup(
              `<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 12px; min-width: 175px; padding: 2px; color: #f1f5f9;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; border-bottom: 1px solid rgba(255,255,255,0.15); padding-bottom: 4px;">
                  <strong style="color: #22d3ee; font-size: 13px;">#${featId} ${props.class || featType}</strong>
                  <span style="color: ${statusCol}; font-weight: 700; font-size: 10px; text-transform: uppercase;">● ${status}</span>
                </div>
                <div style="font-size: 11px; margin-bottom: 8px; color: #94a3b8; font-family: monospace;">
                  Confidence: <strong style="color: #38bdf8;">${confPct}%</strong>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px;">
                  <button
                    onclick="window._veApprove && window._veApprove(${featId})"
                    style="background: #10b981; color: #042f2e; border: none; border-radius: 4px; padding: 6px 8px; font-weight: 700; font-size: 11px; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 4px;"
                  >
                    ✓ Approve
                  </button>
                  <button
                    onclick="window._veReject && window._veReject(${featId})"
                    style="background: #ef4444; color: #450a0a; border: none; border-radius: 4px; padding: 6px 8px; font-weight: 700; font-size: 11px; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 4px;"
                  >
                    ✗ Reject
                  </button>
                </div>
              </div>`,
              { maxWidth: 240 }
            )

            layer.on('click', () => {
              onSelectFeature({
                id: featId,
                type: featType,
                className: props.class || props.className || '',
                confidence: Number(props.confidence ?? 0),
                status: status,
                geometry: feature.geometry,
                created_at: props.created_at ?? '',
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
    let hasAnyFeatures = false
    layers.forEach((group, type) => {
      const typeFeatures = features.filter((f) => f.type === type && f.status !== 'rejected')
      if (typeFeatures.length > 0) {
        hasAnyFeatures = true
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

    // If orthophoto bounds weren't fitted yet, fit to the features
    if (hasAnyFeatures && (!orthophoto?.bounds || orthophoto.bounds.length !== 2)) {
      try {
        const allBounds = L.latLngBounds([])
        layerRefs.current.forEach((group) => {
          group.eachLayer((l: any) => {
            if (l.getBounds) allBounds.extend(l.getBounds())
            else if (l.getLatLng) allBounds.extend(l.getLatLng())
          })
        })
        if (allBounds.isValid()) {
          map.fitBounds(allBounds, { padding: [40, 40] })
        }
      } catch {
        // ignore bounds fit error
      }
    }
    map.invalidateSize()
  }, [layers, mapRef, features, orthophoto])

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
          path.setStyle({ weight: 3.5, color: '#22d3ee', opacity: 1 })
          selectedRef.current = path
          const ll = (layer as L.CircleMarker).getLatLng?.()
          if (ll) {
            map.flyToBounds(L.latLngBounds(ll, ll), { padding: [60, 60], maxZoom: 18 })
          } else if (typeof (path as L.Polygon).getBounds === 'function') {
            map.flyToBounds((path as L.Polygon).getBounds(), { padding: [50, 50], maxZoom: 18 })
          }
        }
      })
    })
  }, [selectedId])

  // Vertex handles for GIS analyst geometry editing
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    if (editMarkersRef.current) {
      editMarkersRef.current.remove()
      editMarkersRef.current = null
    }

    if (!editing || selectedId === null) return

    const feat = features.find((f) => f.id === selectedId)
    if (!feat || !feat.geometry) return

    const g = feat.geometry
    if (g.type !== 'Polygon' && g.type !== 'LineString') return

    const markerGroup = L.layerGroup().addTo(map)
    editMarkersRef.current = markerGroup

    const isPolygon = g.type === 'Polygon'
    const ring: number[][] = isPolygon
      ? [...(g.coordinates[0] as number[][])]
      : [...(g.coordinates as number[][])]

    const customIcon = L.divIcon({
      className: 've-vertex-marker',
      html: '<div style="width: 13px; height: 13px; background: #fbbf24; border: 2px solid #78350f; border-radius: 50%; box-shadow: 0 0 8px #f59e0b; cursor: grab;"></div>',
      iconSize: [13, 13],
      iconAnchor: [6.5, 6.5],
    })

    ring.forEach((pt, idx) => {
      // GeoJSON pt is [lon, lat], Leaflet is [lat, lon]
      const marker = L.marker([pt[1], pt[0]], {
        icon: customIcon,
        draggable: true,
      })

      marker.on('drag', (e: any) => {
        const newLL = e.target.getLatLng()
        ring[idx] = [newLL.lng, newLL.lat]
        if (isPolygon && (idx === 0 || idx === ring.length - 1)) {
          ring[0] = [newLL.lng, newLL.lat]
          ring[ring.length - 1] = [newLL.lng, newLL.lat]
        }
        if (selectedRef.current && typeof (selectedRef.current as any).setLatLngs === 'function') {
          const newPath = ring.map((c) => [c[1], c[0]])
          ;(selectedRef.current as any).setLatLngs(isPolygon ? [newPath] : newPath)
        }
      })

      marker.on('dragend', () => {
        const newGeom: Geometry = isPolygon
          ? { type: 'Polygon', coordinates: [ring] }
          : { type: 'LineString', coordinates: ring }
        onUpdateFeatureGeometry?.(selectedId, newGeom)
      })

      markerGroup.addLayer(marker)
    })

    return () => {
      if (editMarkersRef.current) {
        editMarkersRef.current.remove()
        editMarkersRef.current = null
      }
    }
  }, [editing, selectedId, features, onUpdateFeatureGeometry])

  const selectedFeature = features.find((f) => f.id === selectedId)

  return (
    <div className="relative h-full w-full">
      <div
        ref={containerRef}
        className={`absolute inset-0 h-full w-full contour-bg ${hasProject ? 'project' : ''} ${dragOver ? 'dragging' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragOver(false)
        }}
      />

      {editing && selectedFeature && (
        <div className="pointer-events-auto absolute top-4 left-1/2 -translate-x-1/2 z-[1060] flex items-center gap-3 rounded-xl border border-amber-400/60 bg-[#0c1220]/95 px-4 py-2 shadow-2xl backdrop-blur-md font-mono text-xs text-amber-300 animate-in fade-in slide-in-from-top-2">
          <span className="flex h-2.5 w-2.5 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-500"></span>
          </span>
          <span>
            Editing Boundary for <strong>#{selectedFeature.id} {selectedFeature.className || selectedFeature.type}</strong> &mdash; Drag amber vertices to reshape
          </span>
          <button
            onClick={() => onToggleEdit?.()}
            className="rounded-lg bg-amber-400/20 hover:bg-amber-400/35 text-amber-200 border border-amber-400/50 px-3 py-1 font-bold transition-all cursor-pointer"
          >
            ✓ Done Editing
          </button>
        </div>
      )}
    </div>
  )
}