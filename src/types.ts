export type FeatureType = 'buildings' | 'roads' | 'water' | 'trees' | 'farms'

export type FeatureStatus = 'pending' | 'needs_review' | 'approved' | 'rejected'

export interface VectorFeature {
  id: number
  type: FeatureType
  className: string
  confidence: number // 0.0 - 1.0
  status: FeatureStatus
  geometry: GeoJSON.Geometry
  created_at: string
}

export type PipelineStage =
  | 'idle'
  | 'tiling'
  | 'detecting'
  | 'vectorizing'
  | 'complete'

export interface Orthophoto {
  id: number
  filename: string
  bounds: [[number, number], [number, number]] // [[south, west], [north, east]] for leaflet
  width: number
  height: number
}