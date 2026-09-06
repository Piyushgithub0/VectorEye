import type { Orthophoto, VectorFeature, FeatureType, FeatureStatus } from './types'

const API = '/api'

export async function uploadOrthophoto(file: File): Promise<{ jobId: string }> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${API}/upload`, { method: 'POST', body: form })
  if (!res.ok) throw new Error('Upload failed')
  return res.json()
}

export async function getFeatures(
  type: FeatureType,
  opts: { minConfidence?: number; status?: FeatureStatus; orthophotoId?: number } = {},
): Promise<GeoJSON.FeatureCollection> {
  const params = new URLSearchParams()
  if (opts.minConfidence !== undefined)
    params.set('min_confidence', String(opts.minConfidence))
  if (opts.status) params.set('status', opts.status)
  if (opts.orthophotoId !== undefined)
    params.set('orthophoto_id', String(opts.orthophotoId))
  const res = await fetch(`${API}/features/${type}?${params.toString()}`)
  if (!res.ok) throw new Error('Failed to load features')
  return res.json()
}

export async function updateFeature(
  id: number,
  patch: { status?: FeatureStatus; type?: FeatureType; className?: string; geometry?: GeoJSON.Geometry },
): Promise<VectorFeature> {
  const res = await fetch(`${API}/features/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
  if (!res.ok) throw new Error('Failed to update feature')
  return res.json()
}

export async function batchUpdateFeatures(
  featureIds: number[],
  status: FeatureStatus,
): Promise<{ updated: number; status: FeatureStatus }> {
  const res = await fetch(`${API}/features/batch-status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ feature_ids: featureIds, status }),
  })
  if (!res.ok) throw new Error('Failed to batch update features')
  return res.json()
}

export async function exportGeojson(
  type: FeatureType | 'all',
  opts: {
    orthophotoId?: number
    status?: FeatureStatus | 'all'
    format?: 'geojson' | 'csv' | 'kml'
    minConfidence?: number
  } = {},
): Promise<Blob> {
  const params = new URLSearchParams()
  if (opts.orthophotoId !== undefined)
    params.set('orthophoto_id', String(opts.orthophotoId))
  if (opts.status) params.set('status', opts.status)
  if (opts.format) params.set('format', opts.format)
  if (opts.minConfidence !== undefined)
    params.set('min_confidence', String(opts.minConfidence))
  const res = await fetch(`${API}/export/${type}?${params.toString()}`)
  if (!res.ok) throw new Error('Export failed')
  return res.blob()
}

export type AnalyticalReport = {
  orthophoto_id: number
  filename: string
  generated_at: string
  summary: string
  statistics: Record<string, unknown>
  recommendations: string[]
  narrative: string | null
}

export async function generateReport(
  orthophotoId: number,
  mistralApiKey?: string,
): Promise<AnalyticalReport> {
  const params = new URLSearchParams()
  if (mistralApiKey) params.set('mistral_api_key', mistralApiKey)
  const qs = params.toString()
  const res = await fetch(
    `${API}/report/${orthophotoId}/generate${qs ? `?${qs}` : ''}`,
    { method: 'POST' },
  )
  if (!res.ok) throw new Error('Report generation failed')
  return res.json()
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export async function getOrthophoto(id: number): Promise<Orthophoto> {
  const res = await fetch(`${API}/orthophoto/${id}`)
  if (!res.ok) throw new Error('Failed to load orthophoto')
  return res.json()
}

export async function getOrthophotoLocation(id: number): Promise<import('./types').OrthophotoLocation> {
  const res = await fetch(`${API}/orthophoto/${id}/location`)
  if (!res.ok) throw new Error('Failed to load orthophoto location')
  return res.json()
}

export async function getLatestOrthophoto(): Promise<Orthophoto> {
  const res = await fetch(`${API}/orthophoto/latest`)
  if (!res.ok) throw new Error('Failed to load latest orthophoto')
  return res.json()
}

export type JobStatus = {
  stage: string
  message: string
  progress: number
  done: boolean
  error?: string
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const res = await fetch(`${API}/jobs/${jobId}/status`)
  if (!res.ok) throw new Error('Failed to load job status')
  return res.json()
}

export function getOrthophotoImageUrl(id: number): string {
  return `${API}/orthophoto/${id}/image`
}