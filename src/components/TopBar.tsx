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
}

export function TopBar({
  stage,
  hasProject,
  activeTypes,
  onToggleType,
  onFileSelected,
  fileInputRef,
  onBrowseClick,
}: TopBarProps) {
  return (
    <header className="panel z-[1100] relative flex items-center gap-5 px-4 py-2.5">
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
        Upload
      </button>

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