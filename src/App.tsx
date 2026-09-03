import { useCallback, useState, useRef } from 'react'
import type { FeatureType, Orthophoto, PipelineStage, VectorFeature } from './types'
import { TopBar } from './components/TopBar'
import { MapView } from './components/MapView'
import { FEATURE_TYPES } from './lib/constants'
import { buildDemoFeatures, DEMO_ORTHOPHOTO } from './lib/mockData'
import { QCPanel } from './components/QCPanel'

type QCView = 'detail' | 'list'

function App() {
  const [stage, setStage] = useState<PipelineStage>('idle')
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
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (!file) return
      setStage('tiling')
      setSelectedId(null)
      setFeatures([])
      const stages: PipelineStage[] = ['detecting', 'vectorizing', 'complete']
      let i = 0
      const interval = window.setInterval(() => {
        i++
        if (i < stages.length) {
          setStage(stages[i])
        } else {
          window.clearInterval(interval)
          const demo = buildDemoFeatures()
          setFeatures(demo)
          setOrthophoto(DEMO_ORTHOPHOTO as unknown as Orthophoto)
          window.setTimeout(() => {}, 4000)
        }
      }, 1200)
    },
    [],
  )

  const handleApprove = useCallback((id: number) => {
    setFeatures((prev) =>
      prev.map((x) => (x.id === id ? { ...x, status: 'approved' } : x)),
    )
    if (selectedId === id) setSelectedId(id)
  }, [selectedId])

  const handleReject = useCallback((id: number) => {
    setFeatures((prev) =>
      prev.map((x) => (x.id === id ? { ...x, status: 'rejected' } : x)),
    )
    if (selectedId === id) setSelectedId(id)
  }, [selectedId])

  const handleExport = useCallback((type: FeatureType) => {
    const geoms = features.filter((f) => f.type === type && f.status !== 'rejected')
    const fc = {
      type: 'FeatureCollection',
      features: geoms.map((f) => ({
        type: 'Feature',
        properties: {
          id: f.id,
          class: f.className,
          confidence: f.confidence,
          status: f.status,
        },
        geometry: f.geometry,
      })),
    }
    const blob = new Blob([JSON.stringify(fc, null, 2)], { type: 'application/geo+json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${type}-vectoreye.geojson`
    a.click()
    URL.revokeObjectURL(url)
  }, [features])

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
        )}
      </div>
    </div>
  )
}

export default App