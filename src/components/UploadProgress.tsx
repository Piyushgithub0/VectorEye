import type { JobStatus } from '../api'

interface UploadProgressProps {
  status: JobStatus | null
}

const STAGES = [
  { key: 'tiling', label: 'TILING', sub: 'Reading terrain' },
  { key: 'detecting', label: 'DETECTING', sub: 'AI scanning features' },
  { key: 'vectorizing', label: 'VECTORIZING', sub: 'Building geometry' },
  { key: 'complete', label: 'READY', sub: 'Features mapped' },
]

// Map backend stages to a 0..4 progress index for the stepper.
const STAGE_ORDER = ['queued', 'tiling', 'detecting', 'vectorizing', 'complete']

function stageIndex(stage: string | undefined): number {
  const i = STAGE_ORDER.indexOf(stage ?? 'queued')
  return i === -1 ? 0 : i
}

export function UploadProgress({ status }: UploadProgressProps) {
  const stage = status?.stage ?? 'queued'
  const pct = status?.progress ?? 0
  const idx = stageIndex(stage)
  const message = status?.message || 'Warming up engines'
  const isError = stage === 'error'

  function done(key: string): boolean {
    if (isError) return false
    if (key === 'complete') return stage === 'complete'
    const keyIdx = STAGE_ORDER.indexOf(key)
    return keyIdx !== -1 && keyIdx < idx
  }
  const active = (key: string): boolean => {
    if (isError) return false
    const keyIdx = STAGE_ORDER.indexOf(key)
    return keyIdx !== -1 && keyIdx === idx
  }

  return (
    <div className="pointer-events-none absolute inset-0 z-[900] flex items-center justify-center bg-[#0a0e17]/70 backdrop-blur-sm">
      <div className="relative w-full max-w-lg rounded-2xl border border-cyan-400/20 bg-[#111622]/80 p-8 shadow-[0_0_40px_rgba(34,211,238,0.15)]">
        {/* HUD corner accents */}
        <div className="pointer-events-none absolute left-0 top-0 h-6 w-6 border-l-2 border-t-2 border-cyan-400/60" />
        <div className="pointer-events-none absolute right-0 top-0 h-6 w-6 border-r-2 border-t-2 border-cyan-400/60" />
        <div className="pointer-events-none absolute bottom-0 left-0 h-6 w-6 border-b-2 border-l-2 border-cyan-400/60" />
        <div className="pointer-events-none absolute bottom-0 right-0 h-6 w-6 border-b-2 border-r-2 border-cyan-400/60" />

        <div className="mb-6 flex items-center justify-between font-mono">
          <span className={`text-[11px] uppercase tracking-[0.25em] ${isError ? 'text-red-400' : 'text-cyan-300'}`}>
            {isError ? status?.error || 'Pipeline failed' : message}
          </span>
          <span className="text-sm font-bold text-cyan-200">{pct}%</span>
        </div>

        {/* Overall progress bar */}
        <div className="mb-8 h-1.5 w-full overflow-hidden rounded-full bg-white/10">
          <div
            className={`h-full transition-all duration-500 ${isError ? 'bg-red-500' : 'bg-gradient-to-r from-cyan-400 to-purple-500'}`}
            style={{ width: `${isError ? 100 : pct}%` }}
          />
        </div>

        {/* Stepper */}
        <div className="grid grid-cols-4 gap-3">
          {STAGES.map((s) => {
            const isDone = done(s.key)
            const isActive = active(s.key)
            const isErr = isError && s.key === 'error'
            const color = isErr ? 'text-red-400' : isDone ? 'text-emerald-400' : isActive ? 'text-cyan-300' : 'text-white/30'
            return (
              <div key={s.key} className="flex flex-col items-center gap-2 text-center">
                <div
                  className={`flex h-9 w-9 items-center justify-center rounded-full border font-mono text-xs transition-all ${
                    isErr
                      ? 'border-red-500 bg-red-500/10'
                      : isDone
                      ? 'border-emerald-400 bg-emerald-400/10'
                      : isActive
                      ? 'border-cyan-400 bg-cyan-400/10 shadow-[0_0_14px_rgba(34,211,238,0.4)]'
                      : 'border-white/15 bg-white/5'
                  }`}
                >
                  {isActive && !isErr ? (
                    <span className="h-3 w-3 animate-pulse rounded-full bg-cyan-300" />
                  ) : isDone ? (
                    <span className="text-emerald-300">✓</span>
                  ) : (
                    <span className={color}>{s.key === 'error' ? '!' : ''}</span>
                  )}
                </div>
                <span className={`font-mono text-[10px] uppercase tracking-widest ${color}`}>{s.label}</span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}