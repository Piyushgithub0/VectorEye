import type { VectorFeature, FeatureType } from '../types'
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
  onToggleEdit: (f: VectorFeature) => void
  editing: boolean
  onExport: (type: FeatureType) => void
}

function ConfidenceDot({ confidence, forced }: { confidence: number; forced: boolean }) {
  if (forced) {
    return <span className="h-2 w-2 rounded-full bg-conf-low ring-1 ring-conf-low/40" />
  }
  const tier = confidenceTier(confidence)
  const color = tier === 'high' ? 'bg-conf-high' : tier === 'medium' ? 'bg-conf-medium' : 'bg-conf-low'
  return <span className={`h-2 w-2 rounded-full ${color}`} />
}

function StatusTag({ status, forcedReview }: { status: string; forcedReview: boolean }) {
  if (forcedReview) {
    return (
      <span className="rounded border border-conf-low/40 bg-conf-low/10 px-1.5 py-0.5 font-mono text-[10px] text-conf-low">
        needs review
      </span>
    )
  }
  const map: Record<string, { label: string; cls: string }> = {
    approved: { label: 'approved', cls: 'text-conf-high border-conf-high/40 bg-conf-high/10' },
    rejected: { label: 'rejected', cls: 'text-text-muted border-text-muted/40 bg-text-muted/10' },
    pending: { label: 'pending', cls: 'text-cyan-400 border-cyan-400/40 bg-cyan-400/10' },
    needs_review: { label: 'needs review', cls: 'text-conf-low border-conf-low/40 bg-conf-low/10' },
  }
  const s = map[status] ?? map.pending
  return (
    <span className={`rounded border px-1.5 py-0.5 font-mono text-[10px] ${s.cls}`}>
      {s.label}
    </span>
  )
}

function ExportMenu({ onExport }: { onExport: (type: FeatureType) => void }) {
  const types: FeatureType[] = ['buildings', 'roads', 'water', 'trees', 'farms']
  return (
    <details className="relative">
      <summary className="cursor-pointer list-none rounded-md border border-purple-400/40 px-3 py-1.5 text-xs font-medium text-purple-400 transition-colors hover:bg-purple-400/10">
        Export
      </summary>
      <div className="absolute bottom-full right-0 mb-2 w-52 panel z-20 rounded-md py-1">
        {types.map((type) => (
          <button
            key={type}
            onClick={() => onExport(type)}
            className="block w-full px-4 py-2 text-left text-xs font-mono text-text-primary transition-colors hover:bg-cyan-400/10"
          >
            Export {FEATURE_LABELS[type]} (GeoJSON)
          </button>
        ))}
      </div>
    </details>
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
  onToggleEdit,
  editing,
  onExport,
}: QCPanelProps) {
  const filtered = features.filter((f) => f.type === activeType)
  const needsReviewCount = filtered.filter(
    (f) =>
      f.status === 'needs_review' ||
      activeType === 'farms' ||
      confidenceTier(f.confidence) === 'low',
  ).length

  return (
    <aside className="pointer-events-none absolute right-3 top-3 bottom-3 z-[1050] flex w-[360px] flex-col">
      <div className="panel pointer-events-auto flex flex-col overflow-hidden rounded-lg">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-cyan-400/10 px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold text-text-primary">
              QC Panel
            </h2>
            <p className="font-mono text-[10px] text-text-muted">
              {FEATURE_LABELS[activeType]} &middot; {filtered.length} features &middot;{' '}
              <span className="text-conf-low">{needsReviewCount} need review</span>
            </p>
          </div>
          <div className="flex rounded-md border border-cyan-400/20 p-0.5 text-[11px]">
            <button
              onClick={() => onViewChange('list')}
              className={`rounded px-2 py-1 font-mono transition-colors ${
                view === 'list' ? 'bg-cyan-400/15 text-cyan-400' : 'text-text-muted hover:text-text-primary'
              }`}
            >
              list
            </button>
            <button
              onClick={() => onViewChange('detail')}
              className={`rounded px-2 py-1 font-mono transition-colors ${
                view === 'detail' ? 'bg-cyan-400/15 text-cyan-400' : 'text-text-muted hover:text-text-primary'
              }`}
            >
              detail
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto">
          {view === 'list' ? (
            filtered.length === 0 ? (
              <ListEmpty activeType={activeType} />
            ) : (
              <ul className="divide-y divide-cyan-400/5">
                {[...filtered]
                  .sort((a, b) => a.confidence - b.confidence)
                  .map((f) => {
                    const forcedReview = activeType === 'farms'
                    return (
                      <li key={f.id}>
                        <button
                          onClick={() => onSelectFeature(f)}
                          className={`flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors ${
                            selectedId === f.id
                              ? 'bg-cyan-400/10'
                              : 'hover:bg-cyan-400/5'
                          }`}
                        >
                          <ConfidenceDot confidence={f.confidence} forced={forcedReview} />
                          <span className="font-mono text-xs text-cyan-400">
                            #{String(f.id).padStart(3, '0')}
                          </span>
                          <span className="font-mono text-xs text-text-primary">
                            {pct(f.confidence)}
                          </span>
                          <span className="ml-auto">
                            <StatusTag status={f.status} forcedReview={forcedReview} />
                          </span>
                        </button>
                      </li>
                    )
                  })
                }
              </ul>
            )
          ) : selectedId ? (
<DetailView
              featureId={selectedId}
              onApprove={() => onApprove(selectedId)}
              onReject={() => onReject(selectedId)}
              onToggleEdit={() => onToggleEdit(findFeature(features, selectedId))}
              editing={editing}
              features={features}
/>
          ) : (
            <div className="p-6 text-center">
              <p className="text-sm text-text-muted">
                Select a feature on the map to inspect it
              </p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-cyan-400/10 px-4 py-3">
          <span className="font-mono text-[10px] text-text-muted">
            layer: {activeType}
          </span>
          <ExportMenu onExport={onExport} />
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
    <div className="p-6 text-center">
      <p className="text-sm text-text-muted">
        No {FEATURE_LABELS[activeType].toLowerCase()} features detected yet
      </p>
    </div>
  )
}

function DetailView({
  featureId,
  onApprove,
  onReject,
  onToggleEdit,
  editing,
  features,
}: {
  featureId: number
  onApprove: () => void
  onReject: () => void
  onToggleEdit: (f: VectorFeature) => void
  editing: boolean
  features: VectorFeature[]
}) {
  const feature = findFeature(features, featureId)
  const forcedReview = feature.type === 'farms'
  const tier = confidenceTier(feature.confidence)
  const confColor = tier === 'high' ? 'text-conf-high' : tier === 'medium' ? 'text-conf-medium' : 'text-conf-low'

  return (
    <div className="p-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="font-mono text-xs text-cyan-400">#{String(feature.id).padStart(3, '0')}</p>
          <p className="mt-1 text-sm font-semibold uppercase tracking-wider text-purple-400">
            {FEATURE_LABELS[feature.type]}
          </p>
          {forcedReview && (
            <p className="mt-1 font-mono text-[10px] text-conf-low">needs review (weak class)</p>
          )}
        </div>
        <StatusTag status={feature.status} forcedReview={forcedReview} />
      </div>

      {/* Confidence */}
      <div className="mt-5">
        <p className="font-mono text-[10px] text-text-muted">CONFIDENCE</p>
        <p className={`mt-1 font-mono text-3xl font-semibold ${confColor}`}>
          {pct(feature.confidence)}
        </p>
      </div>

      {/* Meta data */}
      <div className="mt-5 space-y-2 rounded-md border border-cyan-400/10 bg-cyan-400/5 p-3">
        <Row label="TYPE" value={feature.type} />
        <Row label="STATUS" value={feature.status} />
        <Row label="CREATED" value={new Date(feature.created_at).toLocaleTimeString()} />
        <Row label="SRID" value="EPSG:4326" />
      </div>

      {/* Actions */}
      <div className="mt-5 flex gap-2">
        <button
          onClick={onApprove}
          className="flex-1 rounded-md border border-cyan-400/50 bg-cyan-400/15 px-3 py-2 text-xs font-semibold text-cyan-400 transition-colors hover:bg-cyan-400/25"
        >
          Approve
        </button>
        <button
          onClick={onReject}
          className="flex-1 rounded-md border border-conf-low/50 px-3 py-2 text-xs font-semibold text-conf-low transition-colors hover:bg-conf-low/10"
        >
          Reject
        </button>
      </div>
      <button
        onClick={() => onToggleEdit(feature)}
        className={`mt-2 w-full rounded-md border px-3 py-2 text-xs font-medium transition-colors ${
          editing
            ? 'border-purple-400/60 bg-purple-400/15 text-purple-400'
            : 'border-cyan-400/20 text-text-muted hover:text-text-primary'
        }`}
      >
        {editing ? 'Editing — click feature to finish' : 'Edit geometry'}
      </button>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="font-mono text-[10px] text-text-muted">{label}</span>
      <span className="font-mono text-[11px] text-text-primary">{value}</span>
    </div>
  )
}