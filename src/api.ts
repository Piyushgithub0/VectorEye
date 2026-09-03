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

export async function updateFeature(id: number, patch: { status?: FeatureStatus }): Promise<VectorFeature> {
  const res = await fetch(`${API}/features/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
  if (!res.ok) throw new Error('Failed to update feature')
  return res.json()
}

export async function exportGeojson(type: FeatureType): Promise<Blob> {
  const res = await fetch(`${API}/export/${type}`)
  if (!res.ok) throw new Error('Export failed')
  return res.blob()
}

export async function getOrthophoto(id: number): Promise<Orthophoto> {
  const res = await fetch(`${API}/orthophoto/${id}`)
  if (!res.ok) throw new Error('Failed to load orthophoto')
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