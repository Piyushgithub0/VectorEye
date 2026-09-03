import type { FeatureType } from '../types'

export const FEATURE_TYPES: FeatureType[] = [
  'buildings',
  'roads',
  'water',
  'trees',
  'farms',
]

export const FORCE_NEEDS_REVIEW: Record<FeatureType, boolean> = {
  buildings: false,
  roads: false,
  water: false,
  trees: false,
  farms: true,
}

export function confidenceTier(confidence: number): 'high' | 'medium' | 'low' {
  if (confidence >= 0.8) return 'high'
  if (confidence >= 0.5) return 'medium'
  return 'low'
}

export function pct(confidence: number): string {
  return `${Math.round(confidence * 100)}%`
}

export const CONFIDENCE_COLORS = {
  high: '#22c55e',
  medium: '#eab308',
  low: '#ef4444',
} as const

export const FEATURE_LABELS: Record<FeatureType, string> = {
  buildings: 'Buildings',
  roads: 'Roads',
  water: 'Water',
  trees: 'Trees',
  farms: 'Farms',
}