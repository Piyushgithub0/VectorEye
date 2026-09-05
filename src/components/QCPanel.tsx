import { useState } from 'react'
import type { VectorFeature, FeatureType, FeatureStatus } from '../types'
import { confidenceTier, FEATURE_LABELS, pct } from '../lib/constants'

interface QCPanelProps {
  activeType: FeatureType
  features: VectorFeature[]
  selectedId: number | null
  view: 'detail' | 'list'
  onViewChange: (view: 'detail' | 'list') => void
  onSelectFeature: (f: VectorFeature) => void
  onApprove: (id: number) => void
  onReject: (id: number) => void
  onUpdateFeature?: (id: number, patch: { status?: FeatureStatus; type?: FeatureType; className?: string }) => void
  onBatchApprove?: (type: FeatureType | 'high_conf' | 'all') => void
  onBatchReject?: (target: FeatureType | 'low_conf' | 'needs_review') => void
  onToggleEdit: (f: VectorFeature) => void
  editing: boolean
  onExportImage: (type: FeatureType) => void
  onExportCompositePng?: () => void
  onExportGeojson: (type: FeatureType | 'all', status?: 'all' | 'approved') => void
  onExportKml?: (type: FeatureType | 'all', status?: 'all' | 'approved') => void
  onExportCsv: (type: FeatureType | 'all', status?: 'all' | 'approved') => void
  onGenerateReport: (format?: 'html' | 'json') => void
  reportLoading?: boolean
}

function ConfidenceDot({ confidence, forced }: { confidence: number; forced: boolean }) {
  if (forced) {
    return <span className="h-2 w-2 rounded-full bg-amber-400 ring-1 ring-amber-400/40" />
  }
  const tier = confidenceTier(confidence)
  const color = tier === 'high' ? 'bg-emerald-400' : tier === 'medium' ? 'bg-amber-400' : 'bg-red-400'
  return <span className={`h-2 w-2 rounded-full ${color}`} />
}

function StatusTag({ status, forcedReview }: { status: string; forcedReview?: boolean }) {
  if (forcedReview) {
    return (
      <span className="rounded border border-amber-400/40 bg-amber-400/10 px-1.5 py-0.5 font-mono text-[10px] text-amber-400">
        needs review
      </span>
    )
  }
  const map: Record<string, { label: string; cls: string }> = {
    approved: { label: 'approved', cls: 'text-emerald-400 border-emerald-400/40 bg-emerald-400/10' },
    rejected: { label: 'rejected', cls: 'text-red-400 border-red-400/40 bg-red-400/10' },
    pending: { label: 'pending', cls: 'text-cyan-400 border-cyan-400/40 bg-cyan-400/10' },
    needs_review: { label: 'needs review', cls: 'text-amber-400 border-amber-400/40 bg-amber-400/10' },
  }
  const s = map[status] ?? map.pending
  return (
    <span className={`rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider ${s.cls}`}>
      {s.label}
    </span>
  )
}

export function QCPanel({
  activeType,
  features,
  selectedId,
  view,
  onViewChange,
  onSelectFeature,
  onApprove,
  onReject,
  onUpdateFeature,
  onBatchApprove,
  onBatchReject,
  onToggleEdit,
  editing,
  onExportImage,
  onExportCompositePng,
  onExportGeojson,
  onExportKml,
  onExportCsv,
  onGenerateReport,
  reportLoading,
}: QCPanelProps) {
  const [showExportModal, setShowExportModal] = useState(false)
  const filtered = features.filter((f) => f.type === activeType)
  const approvedCount = filtered.filter((f) => f.status === 'approved').length
  const needsReviewCount = filtered.filter(
    (f) =>
      f.status === 'needs_review' ||
      activeType === 'farms' ||
      confidenceTier(f.confidence) === 'low',
  ).length

  return (
    <aside className="pointer-events-none absolute right-3 top-3 bottom-3 z-[1050] flex w-[380px] flex-col">
      <div className="panel pointer-events-auto flex h-full flex-col overflow-hidden rounded-xl border border-cyan-400/20 bg-[#0e1422]/90 shadow-2xl backdrop-blur-md">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-cyan-400/10 px-4 py-3 bg-[#131b2e]/60">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold tracking-wide text-text-primary">
                GIS Analyst QC Panel
              </h2>
              <span className="rounded bg-cyan-400/15 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-widest text-cyan-300 border border-cyan-400/30">
                PRO
              </span>
            </div>
            <p className="font-mono text-[10px] text-text-muted mt-0.5">
              {FEATURE_LABELS[activeType]} &middot; {filtered.length} total &middot;{' '}
              <span className="text-emerald-400 font-semibold">{approvedCount} approved</span> &middot;{' '}
              <span className="text-amber-400">{needsReviewCount} review</span>
            </p>
          </div>
          <div className="flex rounded-lg border border-cyan-400/20 p-0.5 text-[11px] bg-black/20">
            <button
              onClick={() => onViewChange('list')}
              className={`rounded px-2.5 py-1 font-mono transition-colors ${
                view === 'list' ? 'bg-cyan-400/20 text-cyan-300 font-bold' : 'text-text-muted hover:text-text-primary'
              }`}
            >
              List
            </button>
            <button
              onClick={() => onViewChange('detail')}
              className={`rounded px-2.5 py-1 font-mono transition-colors ${
                view === 'detail' ? 'bg-cyan-400/20 text-cyan-300 font-bold' : 'text-text-muted hover:text-text-primary'
              }`}
            >
              Detail
            </button>
          </div>
        </div>

        {/* Analyst Batch Controls */}
        <div className="border-b border-cyan-400/10 bg-[#0a0f1d]/80 px-3 py-2 flex flex-col gap-1.5 text-[10px] font-mono">
          <div className="flex items-center justify-between gap-1">
            <span className="text-text-muted shrink-0 uppercase tracking-wider text-[9px]">Approve:</span>
            <button
              onClick={() => onBatchApprove?.('high_conf')}
              title="Approve all features with confidence ≥ 75%"
              className="flex-1 rounded border border-emerald-500/40 bg-emerald-500/10 py-1 px-1.5 text-emerald-300 hover:bg-emerald-500/25 transition-colors text-center truncate"
            >
              ✓ &ge;75%
            </button>
            <button
              onClick={() => onBatchApprove?.(activeType)}
              title="Approve all features in the currently selected layer"
              className="flex-1 rounded border border-cyan-400/40 bg-cyan-400/10 py-1 px-1.5 text-cyan-300 hover:bg-cyan-400/25 transition-colors text-center truncate"
            >
              ✓ Layer
            </button>
            <button
              onClick={() => onBatchApprove?.('all')}
              title="Approve all extracted vector features across all layers"
              className="flex-1 rounded border border-emerald-400/60 bg-emerald-400/20 py-1 px-1.5 text-emerald-200 hover:bg-emerald-400/35 transition-colors text-center font-bold truncate"
            >
              ✓ All (100%)
            </button>
          </div>
          {onBatchReject && (
            <div className="flex items-center justify-between gap-1">
              <span className="text-text-muted shrink-0 uppercase tracking-wider text-[9px]">Reject:</span>
              <button
                onClick={() => onBatchReject('low_conf')}
                title="Reject all low confidence features (< 50%)"
                className="flex-1 rounded border border-red-500/40 bg-red-500/10 py-1 px-1.5 text-red-300 hover:bg-red-500/25 transition-colors text-center truncate"
              >
                ✗ Low &lt;50%
              </button>
              <button
                onClick={() => onBatchReject(activeType)}
                title="Reject all features in current layer"
                className="flex-1 rounded border border-red-500/40 bg-red-500/10 py-1 px-1.5 text-red-300 hover:bg-red-500/25 transition-colors text-center truncate"
              >
                ✗ Layer
              </button>
            </div>
          )}
        </div>

        {/* Body Content */}
        <div className="flex-1 overflow-y-auto min-h-0">
          {view === 'list' ? (
            filtered.length === 0 ? (
              <ListEmpty activeType={activeType} />
            ) : (
              <ul className="divide-y divide-cyan-400/5">
                {[...filtered]
                  .sort((a, b) => a.confidence - b.confidence)
                  .map((f) => {
                    const forcedReview = activeType === 'farms'
                    const isSelected = selectedId === f.id
                    return (
                      <li key={f.id}>
                        <div
                          className={`flex w-full items-center gap-2.5 px-3 py-2 transition-colors ${
                            isSelected ? 'bg-cyan-400/15 border-l-2 border-cyan-400' : 'hover:bg-cyan-400/5'
                          }`}
                        >
                          <button
                            onClick={() => onSelectFeature(f)}
                            className="flex min-w-0 flex-1 items-center gap-2 text-left"
                          >
                            <ConfidenceDot confidence={f.confidence} forced={forcedReview} />
                            <span className="font-mono text-xs font-semibold text-cyan-400">
                              #{String(f.id).padStart(3, '0')}
                            </span>
                            <span className="font-mono text-xs text-text-primary">
                              {pct(f.confidence)}
                            </span>
                            <span className="ml-auto">
                              <StatusTag status={f.status} forcedReview={forcedReview} />
                            </span>
                          </button>
                          <div className="flex shrink-0 items-center gap-1 font-mono text-[10px]">
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                onApprove(f.id)
                              }}
                              title="Approve feature"
                              aria-label={`Approve feature ${f.id}`}
                              className={`rounded border px-1.5 py-1 font-semibold flex items-center gap-0.5 transition-all ${
                                f.status === 'approved'
                                  ? 'border-emerald-400 bg-emerald-400/25 text-emerald-300 font-bold'
                                  : 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/25'
                              }`}
                            >
                              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>
                              Approve
                            </button>
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                onReject(f.id)
                              }}
                              title="Reject feature"
                              aria-label={`Reject feature ${f.id}`}
                              className={`rounded border px-1.5 py-1 font-semibold flex items-center gap-0.5 transition-all ${
                                f.status === 'rejected'
                                  ? 'border-red-400 bg-red-400/25 text-red-300 font-bold'
                                  : 'border-red-500/40 bg-red-500/10 text-red-400 hover:bg-red-500/25'
                              }`}
                            >
                              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                              Reject
                            </button>
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                onSelectFeature(f)
                                onToggleEdit(f)
                              }}
                              title="Edit feature geometry on map"
                              aria-label={`Edit feature ${f.id}`}
                              className="rounded border border-amber-400/40 bg-amber-400/10 px-1.5 py-1 font-semibold text-amber-300 hover:bg-amber-400/25 transition-all flex items-center gap-0.5"
                            >
                              ✎ Edit
                            </button>
                          </div>
                        </div>
                      </li>
                    )
                  })}
              </ul>
            )
          ) : selectedId ? (
            <DetailView
              featureId={selectedId}
              onApprove={() => onApprove(selectedId)}
              onReject={() => onReject(selectedId)}
              onUpdateFeature={onUpdateFeature}
              onToggleEdit={() => onToggleEdit(findFeature(features, selectedId))}
              editing={editing}
              features={features}
            />
          ) : (
            <div className="p-8 text-center">
              <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-cyan-400/10 text-cyan-400 border border-cyan-400/20">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="m12 8 4 4-4 4M8 12h8"/></svg>
              </div>
              <p className="text-sm font-medium text-text-primary">Feature Inspector</p>
              <p className="mt-1 text-xs text-text-muted">
                Click any polygon, line, or circle marker on the map to inspect, edit, or approve it.
              </p>
            </div>
          )}
        </div>

        {/* Analyst Deliverables / Download Bar */}
        <div className="border-t border-cyan-400/15 bg-[#111728]/95 p-3 space-y-2">
          <div className="flex items-center justify-between text-[11px] font-mono text-text-muted">
            <span className="uppercase tracking-wider font-semibold text-cyan-300">Vector Deliverables</span>
            <span className="text-text-muted">{filtered.length} in layer</span>
          </div>

          <div className="grid grid-cols-2 gap-1.5 text-[11px] font-mono">
            <button
              onClick={() => onExportGeojson('all', 'all')}
              title="Download all extracted vectors as standard GeoJSON"
              className="rounded border border-emerald-500/40 bg-emerald-500/15 py-1.5 px-2 text-center text-emerald-300 hover:bg-emerald-500/25 transition-colors font-medium flex items-center justify-center gap-1"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
              GeoJSON (All)
            </button>
            <button
              onClick={() => onExportGeojson('all', 'approved')}
              title="Download approved vectors as standard GeoJSON"
              className="rounded border border-cyan-400/40 bg-cyan-400/10 py-1.5 px-2 text-center text-cyan-300 hover:bg-cyan-400/20 transition-colors font-medium flex items-center justify-center gap-1"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
              GeoJSON (Approved)
            </button>
          </div>

          <div className="grid grid-cols-3 gap-1.5 text-[10px] font-mono">
            <button
              onClick={() => onExportKml?.('all', 'all')}
              title="Download vector geometries formatted for Google Earth (KML)"
              className="rounded border border-cyan-400/30 bg-cyan-400/10 py-1 text-center text-cyan-300 hover:bg-cyan-400/20 transition-colors"
            >
              KML (Earth)
            </button>
            <button
              onClick={() => onExportCsv('all', 'all')}
              title="Download vector geometries and attributes as CSV/WKT table"
              className="rounded border border-cyan-400/30 bg-cyan-400/10 py-1 text-center text-cyan-300 hover:bg-cyan-400/20 transition-colors"
            >
              CSV Table
            </button>
            <button
              onClick={() => onGenerateReport('json')}
              disabled={reportLoading}
              title="Download full JSON statistics and audit metadata"
              className="rounded border border-purple-400/30 bg-purple-400/10 py-1 text-center text-purple-300 hover:bg-purple-400/20 transition-colors disabled:opacity-50"
            >
              Audit JSON
            </button>
          </div>

          {onExportCompositePng && (
            <button
              onClick={onExportCompositePng}
              title="Download raster orthophoto with all vector geometries overlaid as high-res PNG"
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-amber-400/50 bg-amber-400/15 px-3 py-2 text-xs font-bold text-amber-300 shadow-md shadow-amber-500/10 hover:bg-amber-400/25 transition-all"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/></svg>
              Download Composite PNG (Image + Vector Overlay)
            </button>
          )}

          <button
            onClick={() => onGenerateReport('html')}
            disabled={reportLoading}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-cyan-500 to-purple-600 px-3 py-2 text-xs font-bold text-white shadow-lg shadow-cyan-500/20 hover:opacity-95 transition-opacity disabled:opacity-50"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            {reportLoading ? 'Generating Analysis…' : 'Download Executive QC Report (PDF/HTML)'}
          </button>
        </div>
      </div>
    </aside>
  )
}

function findFeature(features: VectorFeature[], id: number): VectorFeature {
  return features.find((f) => f.id === id) ?? { id: 0, type: 'buildings' as FeatureType, className: 'building', confidence: 0, status: 'pending', geometry: { type: 'Point', coordinates: [0, 0] } as VectorFeature['geometry'], created_at: new Date().toISOString() }
}

function ListEmpty({ activeType }: { activeType: FeatureType }) {
  return (
    <div className="p-8 text-center">
      <p className="text-sm text-text-muted">
        No {FEATURE_LABELS[activeType].toLowerCase()} features detected yet.
      </p>
    </div>
  )
}

function DetailView({
  featureId,
  onApprove,
  onReject,
  onUpdateFeature,
  onToggleEdit,
  editing,
  features,
}: {
  featureId: number
  onApprove: () => void
  onReject: () => void
  onUpdateFeature?: (id: number, patch: { status?: FeatureStatus; type?: FeatureType; className?: string }) => void
  onToggleEdit: (f: VectorFeature) => void
  editing: boolean
  features: VectorFeature[]
}) {
  const feature = findFeature(features, featureId)
  const forcedReview = feature.type === 'farms'
  const tier = confidenceTier(feature.confidence)
  const confColor = tier === 'high' ? 'text-emerald-400' : tier === 'medium' ? 'text-amber-400' : 'text-red-400'
  const allTypes: FeatureType[] = ['buildings', 'roads', 'water', 'trees', 'farms']
  const allStatuses: FeatureStatus[] = ['approved', 'needs_review', 'pending', 'rejected']

  return (
    <div className="p-4 space-y-4">
      {/* Feature Title & Status */}
      <div className="flex items-start justify-between">
        <div>
          <p className="font-mono text-xs font-bold text-cyan-400">#{String(feature.id).padStart(3, '0')}</p>
          <p className="mt-0.5 text-sm font-semibold uppercase tracking-wider text-purple-400">
            {FEATURE_LABELS[feature.type]}
          </p>
        </div>
        <StatusTag status={feature.status} forcedReview={forcedReview} />
      </div>

      {/* Confidence Display */}
      <div className="rounded-lg border border-cyan-400/15 bg-cyan-400/5 p-3 flex items-center justify-between">
        <div>
          <p className="font-mono text-[10px] text-text-muted uppercase tracking-wider">Detection Confidence</p>
          <p className={`mt-0.5 font-mono text-2xl font-bold ${confColor}`}>
            {pct(feature.confidence)}
          </p>
        </div>
        <div className="text-right">
          <span className={`inline-block font-mono text-[11px] uppercase font-semibold ${confColor}`}>
            {tier} Tier
          </span>
        </div>
      </div>

      {/* Analyst Decision Actions */}
      <div>
        <p className="mb-2 font-mono text-[10px] uppercase tracking-wider text-text-muted">Analyst Decision</p>
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={onApprove}
            className={`flex items-center justify-center gap-1.5 rounded-lg border py-2 px-3 text-xs font-bold transition-all ${
              feature.status === 'approved'
                ? 'border-emerald-400 bg-emerald-400/20 text-emerald-300 shadow-md shadow-emerald-500/20'
                : 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/25'
            }`}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>
            Approve
          </button>
          <button
            onClick={onReject}
            className={`flex items-center justify-center gap-1.5 rounded-lg border py-2 px-3 text-xs font-bold transition-all ${
              feature.status === 'rejected'
                ? 'border-red-400 bg-red-400/20 text-red-300 shadow-md shadow-red-500/20'
                : 'border-red-500/40 bg-red-500/10 text-red-400 hover:bg-red-500/25'
            }`}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            Reject
          </button>
        </div>
      </div>

      {/* Analyst Reclassification & Status Dropdowns */}
      <div className="space-y-3 rounded-lg border border-cyan-400/15 bg-black/20 p-3 text-xs">
        <div>
          <label className="mb-1 block font-mono text-[10px] uppercase text-text-muted">
            Reclassify Category
          </label>
          <select
            value={feature.type}
            onChange={(e) => {
              const newType = e.target.value as FeatureType
              onUpdateFeature?.(feature.id, { type: newType, className: newType.slice(0, -1) || newType })
            }}
            className="w-full rounded border border-cyan-400/30 bg-[#0d1322] px-2.5 py-1.5 font-mono text-xs text-text-primary focus:border-cyan-400 focus:outline-none"
          >
            {allTypes.map((t) => (
              <option key={t} value={t}>
                {FEATURE_LABELS[t]} ({t})
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-1 block font-mono text-[10px] uppercase text-text-muted">
            Update QC Status
          </label>
          <select
            value={feature.status}
            onChange={(e) => {
              const newStatus = e.target.value as FeatureStatus
              onUpdateFeature?.(feature.id, { status: newStatus })
            }}
            className="w-full rounded border border-cyan-400/30 bg-[#0d1322] px-2.5 py-1.5 font-mono text-xs text-text-primary focus:border-cyan-400 focus:outline-none"
          >
            {allStatuses.map((s) => (
              <option key={s} value={s}>
                {s.toUpperCase()}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Geometry Edit Toggle */}
      <button
        onClick={() => onToggleEdit(feature)}
        className={`w-full rounded-lg border px-3 py-2 text-xs font-semibold transition-all ${
          editing
            ? 'border-purple-400 bg-purple-400/20 text-purple-300 shadow-md shadow-purple-500/20'
            : 'border-cyan-400/30 text-text-muted hover:text-cyan-300 hover:border-cyan-400/60'
        }`}
      >
        {editing ? 'Editing Active — Click Map to Complete' : '✎ Edit Feature Boundary'}
      </button>

      {/* Technical Metadata */}
      <div className="space-y-1.5 rounded-lg border border-white/5 bg-white/5 p-3 font-mono text-[11px]">
        <Row label="ID" value={`#${feature.id}`} />
        <Row label="CLASS" value={feature.className || feature.type} />
        <Row label="STATUS" value={feature.status} />
        <Row label="GEOMETRY" value={feature.geometry?.type || 'Polygon'} />
        <Row label="PROJECTION" value="EPSG:4326 (WGS84)" />
      </div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[10px] text-text-muted">{label}</span>
      <span className="font-semibold text-text-primary">{value}</span>
    </div>
  )
}