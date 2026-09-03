import { useCallback, useState, useRef } from 'react'
import type { FeatureType, Orthophoto, PipelineStage, VectorFeature } from './types'
import { TopBar } from './components/TopBar'
import { MapView } from './components/MapView'
import { FEATURE_TYPES } from './lib/constants'
import { getFeatures, updateFeature, getOrthophoto, uploadOrthophoto } from './api'
import { exportOrthophotoImage } from './lib/exportImage'
import { QCPanel } from './components/QCPanel'
import { UploadProgress } from './components/UploadProgress'
import type { JobStatus } from './api'

type QCView = 'detail' | 'list'

async function pollForFeatures(
  orthophotoId: number,
  attempt: number,
  setStage: (s: PipelineStage) => void,
  setFeatures: React.Dispatch<React.SetStateAction<VectorFeature[]>>,
): Promise<void> {
  const allFeatures: VectorFeature[] = []
  const resolved = new Set<string>()

  for (const type of FEATURE_TYPES) {
    try {
      const fc = await getFeatures(type, { orthophotoId })
      resolved.add(type)
      const feats: VectorFeature[] = fc.features.map((f) => {
        const p = f.properties as { id?: number; type?: string; className?: string; confidence?: number; status?: string }
        return {
          id: p?.id ?? 0,
          type: (p?.type ?? type) as FeatureType,
          className: p?.className ?? '',
          confidence: p?.confidence ?? 0,
          status: (p?.status ?? 'pending') as VectorFeature['status'],
          geometry: f.geometry as GeoJSON.Geometry,
          created_at: '',
        }
      })
      allFeatures.push(...feats)
    } catch {
      // Feature type not ready yet — will retry next round.
    }
  }

  if (resolved.size === FEATURE_TYPES.length) {
    setFeatures(allFeatures)
    return
  }

  if (attempt < 25) {
    setStage(attempt < 5 ? 'detecting' : 'vectorizing')
    window.setTimeout(() => pollForFeatures(orthophotoId, attempt + 1, setStage, setFeatures), 1200)
  } else {
    if (allFeatures.length > 0) setFeatures(allFeatures)
  }
}

function App() {
  const [stage, setStage] = useState<PipelineStage>('idle')
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null)
  const lastStatusRef = useRef<JobStatus | null>(null)
  const [orthophoto, setOrthophoto] = useState<Orthophoto | null>(null)
  const [features, setFeatures] = useState<VectorFeature[]>([])
  const [activeTypes, setActiveTypes] = useState<Set<FeatureType>>(() => new Set(FEATURE_TYPES))
  const [activeType, setActiveType] = useState<FeatureType>('buildings')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [qcView, setQcView] = useState<QCView>('detail')
  const [editing, setEditing] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const hasProject = stage !== 'idle'

  const toggleType = useCallback((type: FeatureType) => {
    setActiveTypes((prev) => {
      const next = new Set(prev)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return next
    })
    setActiveType(type)
    setSelectedId(null)
  }, [setActiveTypes, setActiveType])

  const handleFileChange = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (!file) return
      setStage('tiling')
      setJobStatus({ stage: 'queued', message: 'Starting pipeline', progress: 0, done: false })
      setSelectedId(null)
      setFeatures([])
      setOrthophoto(null)

      try {
        const { jobId } = await uploadOrthophoto(file)
        const id = Number(jobId)

        // Poll job status for the immersive progress HUD
        const statusTimer = window.setInterval(async () => {
          try {
            const s = await (await import('./api')).getJobStatus(jobId)
            lastStatusRef.current = s
            setJobStatus(s)
            if (s.stage === 'complete' || s.stage === 'error') {
              window.clearInterval(statusTimer)
            }
          } catch {
            // ignore transient polling errors
          }
        }, 700)

        try {
          // Load orthophoto metadata
          let ox: Orthophoto | null = null
          try {
            ox = await getOrthophoto(id)
          } catch {
            // Orthophoto may not be ready yet
          }
          setOrthophoto(ox)

          // Show detecting stage, poll for features
          setStage('detecting')
          await pollForFeatures(id, 0, setStage, setFeatures)
          setStage('complete')
        } catch (err) {
          console.error('Upload failed:', err)
          setStage('idle')
          setJobStatus({ stage: 'error', message: 'Upload failed', progress: 0, done: true })
        }
      } catch (err) {
        console.error('Upload failed:', err)
        setStage('idle')
        setJobStatus({ stage: 'error', message: 'Upload failed', progress: 0, done: true })
      }
    },
    [],
  )

  const handleApprove = useCallback(async (id: number) => {
    try {
      const updated = await updateFeature(id, { status: 'approved' })
      setFeatures((prev) =>
        prev.map((x) => (x.id === id ? { ...x, status: 'approved' } : x)),
      )
      if (selectedId === id) setSelectedId(id)
      return updated
    } catch {
      setFeatures((prev) =>
        prev.map((x) => (x.id === id ? { ...x, status: 'approved' } : x)),
      )
    }
  }, [selectedId])

  const handleReject = useCallback(async (id: number) => {
    try {
      const updated = await updateFeature(id, { status: 'rejected' })
      setFeatures((prev) =>
        prev.map((x) => (x.id === id ? { ...x, status: 'rejected' } : x)),
      )
      if (selectedId === id) setSelectedId(id)
      return updated
    } catch {
      setFeatures((prev) =>
        prev.map((x) => (x.id === id ? { ...x, status: 'rejected' } : x)),
      )
    }
  }, [selectedId])

  const handleExport = useCallback(
    (type: FeatureType) => {
      if (!orthophoto) return
      const typeFeatures = features.filter((f) => f.type === type)
      exportOrthophotoImage(orthophoto, typeFeatures)
    },
    [orthophoto, features],
  )

  const onSelectFeature = useCallback((f: VectorFeature) => {
    setSelectedId(f.id)
    setQcView('detail')
    setEditing(false)
  }, [])

  return (
    <div className="contour-bg flex h-screen flex-col">
      <TopBar
        stage={stage}
        hasProject={hasProject}
        activeTypes={activeTypes}
        onToggleType={toggleType}
        onFileSelected={handleFileChange}
        fileInputRef={fileInputRef}
        onBrowseClick={() => fileInputRef.current?.click()}
      />

      <div className="relative flex-1">
        <MapView
          hasProject={hasProject}
          orthophoto={orthophoto}
          features={features}
          visibleTypes={activeTypes}
          selectedId={selectedId}
          onSelectFeature={(f) => {
            onSelectFeature(f)
          }}
        />

        {hasProject && (
          <QPanelWrapper>
            <QCPanel
              activeType={activeType}
              features={features}
              selectedId={selectedId}
              view={qcView}
              onViewChange={setQcView}
              onSelectFeature={onSelectFeature}
              onApprove={handleApprove}
              onReject={handleReject}
              onToggleEdit={() => setEditing((e) => !e)}
              editing={editing}
              onExport={handleExport}
            />
          </QPanelWrapper>
        )}

        {jobStatus && jobStatus.stage !== 'complete' && jobStatus.stage !== 'error' && (
          <UploadProgress status={jobStatus} />
        )}
      </div>
    </div>
  )
}

function QPanelWrapper({ children }: { children: React.ReactNode }) {
  return <div className="relative z-10">{children}</div>
}

export default App