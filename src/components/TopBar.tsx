import { useState, useRef, useEffect } from 'react'
import type { FeatureType, PipelineStage } from '../types'
import { FEATURE_LABELS, FEATURE_TYPES, FORCE_NEEDS_REVIEW } from '../lib/constants'

function Logo() {
  return (
    <div className="flex items-center gap-2">
      <span className="relative flex h-2.5 w-2.5">
        <span className="absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-60 animate-ping" />
        <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-cyan-400" />
      </span>
      <span className="text-sm font-semibold tracking-widest text-text-primary">
        Vector<span className="text-cyan-400">Eye</span>
      </span>
    </div>
  )
}

function StageIndicator({ stage, hasProject }: { stage: PipelineStage; hasProject: boolean }) {
  if (stage === 'idle') return null
  if (stage === 'complete') {
    return (
      <span className="font-mono text-[11px] text-conf-high">PIPELINE COMPLETE</span>
    )
  }
  const stageLabel =
    stage === 'tiling' ? 'Tiling...' : stage === 'detecting' ? 'Detecting features...' : 'Vectorizing...'
  return (
    <span className="flex items-center gap-2 font-mono text-[11px] text-cyan-400">
      <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-pulse" />
      {stageLabel}
      {!hasProject && <span className="text-text-muted">(no orthophoto)</span>}
    </span>
  )
}

interface TopBarProps {
  stage: PipelineStage
  hasProject: boolean
  activeTypes: Set<FeatureType>
  onToggleType: (type: FeatureType) => void
  onFileSelected: (e: React.ChangeEvent<HTMLInputElement>) => void
  fileInputRef: React.RefObject<HTMLInputElement | null>
  onBrowseClick: () => void
  onGenerateReport?: () => void
  reportLoading?: boolean
  onExportVector?: (type: FeatureType | 'all', format: 'geojson' | 'kml' | 'csv', status: 'all' | 'approved') => void
  onExportCompositePng?: () => void
}

export function TopBar({
  stage,
  hasProject,
  activeTypes,
  onToggleType,
  onFileSelected,
  fileInputRef,
  onBrowseClick,
  onGenerateReport,
  reportLoading,
  onExportVector,
  onExportCompositePng,
}: TopBarProps) {
  const [showExportMenu, setShowExportMenu] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowExportMenu(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])
  return (
    <header className="panel z-[1100] relative flex items-center gap-4 px-4 py-2.5">
      <Logo />

      <input
        ref={fileInputRef}
        type="file"
        accept=".tif,.tiff,.geotiff"
        className="hidden"
        onChange={(e) => onFileSelected(e)}
      />
      <button
        onClick={onBrowseClick}
        className="rounded-md border border-cyan-400/40 px-3 py-1.5 text-xs font-medium text-cyan-400 transition-colors hover:bg-cyan-400/10 hover:border-cyan-400/60"
      >
        Upload Raster
      </button>

      {hasProject && onExportVector && (
        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setShowExportMenu(!showExportMenu)}
            className="flex items-center gap-1.5 rounded-md border border-emerald-500/50 bg-emerald-500/15 px-3 py-1.5 text-xs font-bold text-emerald-300 hover:bg-emerald-500/25 transition-all"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            Download Vectors ▾
          </button>
          {showExportMenu && (
            <div className="absolute left-0 mt-1 w-56 rounded-lg border border-emerald-500/30 bg-[#0d1322] shadow-2xl z-[1300] py-1 text-xs font-mono">
              <button
                onClick={() => {
                  onExportVector('all', 'geojson', 'all')
                  setShowExportMenu(false)
                }}
                className="w-full px-3 py-2 text-left text-emerald-300 hover:bg-emerald-500/20 flex items-center justify-between transition-colors"
              >
                <span>GeoJSON (All Vectors)</span>
                <span className="text-[10px] text-text-muted">.geojson</span>
              </button>
              <button
                onClick={() => {
                  onExportVector('all', 'geojson', 'approved')
                  setShowExportMenu(false)
                }}
                className="w-full px-3 py-2 text-left text-text-primary hover:bg-emerald-500/20 flex items-center justify-between transition-colors"
              >
                <span>GeoJSON (Approved Only)</span>
                <span className="text-[10px] text-text-muted">.geojson</span>
              </button>
              <button
                onClick={() => {
                  onExportVector('all', 'kml', 'all')
                  setShowExportMenu(false)
                }}
                className="w-full px-3 py-2 text-left text-cyan-300 hover:bg-cyan-500/20 flex items-center justify-between transition-colors"
              >
                <span>Google Earth (KML)</span>
                <span className="text-[10px] text-text-muted">.kml</span>
              </button>
              <button
                onClick={() => {
                  onExportVector('all', 'csv', 'all')
                  setShowExportMenu(false)
                }}
                className="w-full px-3 py-2 text-left text-text-muted hover:bg-white/10 flex items-center justify-between transition-colors"
              >
                <span>Attribute Table (CSV)</span>
                <span className="text-[10px] text-text-muted">.csv</span>
              </button>
              {onExportCompositePng && (
                <button
                  onClick={() => {
                    onExportCompositePng()
                    setShowExportMenu(false)
                  }}
                  className="w-full px-3 py-2 text-left text-amber-300 hover:bg-amber-500/20 flex items-center justify-between transition-colors border-t border-cyan-400/10 font-semibold"
                >
                  <span>Vector + Image (PNG)</span>
                  <span className="text-[10px] text-text-muted">.png</span>
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {hasProject && onGenerateReport && (
        <button
          onClick={onGenerateReport}
          disabled={reportLoading}
          className="flex items-center gap-1.5 rounded-md border border-purple-500/50 bg-purple-500/15 px-3 py-1.5 text-xs font-bold text-purple-300 hover:bg-purple-500/25 transition-all disabled:opacity-50"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          {reportLoading ? 'Generating…' : 'Download QC Report'}
        </button>
      )}

      <div className="flex items-center gap-1.5">
        {FEATURE_TYPES.map((type) => {
          const active = activeTypes.has(type)
          return (
            <button
              key={type}
              onClick={() => onToggleType(type)}
              aria-pressed={active}
              title={
                FORCE_NEEDS_REVIEW[type]
                  ? `${FEATURE_LABELS[type]} — always needs review`
                  : `Toggle ${FEATURE_LABELS[type].toLowerCase()} layer`
              }
              className={`relative rounded-md px-3 py-1.5 text-xs transition-colors ${
                active
                  ? 'bg-cyan-400/15 text-cyan-400 border border-cyan-400/40'
                  : 'border border-transparent text-text-muted hover:text-text-primary'
              }`}
            >
              <span
                className={`inline-block h-1.5 w-1.5 rounded-full mr-1.5 ${
                  FORCE_NEEDS_REVIEW[type] ? 'bg-conf-low' : 'bg-cyan-400'
                }`}
              />
              {FEATURE_LABELS[type]}
            </button>
          )
        })}
      </div>

      <div className="ml-auto">
        <StageIndicator stage={stage} hasProject={hasProject} />
      </div>
    </header>
  )
}