import { useCallback, useState, useRef, useEffect } from 'react'
import type { FeatureType, FeatureStatus, Orthophoto, PipelineStage, VectorFeature } from './types'
import { TopBar } from './components/TopBar'
import { MapView } from './components/MapView'
import { FEATURE_TYPES } from './lib/constants'
import { getFeatures, updateFeature, batchUpdateFeatures, getOrthophoto, getLatestOrthophoto, uploadOrthophoto, getJobStatus, exportGeojson, generateReport, downloadBlob } from './api'
import { exportOrthophotoImage } from './lib/exportImage'
import { generateReportHtml } from './lib/reportHtml'
import { QCPanel } from './components/QCPanel'
import { UploadProgress } from './components/UploadProgress'
import type { JobStatus } from './api'

type QCView = 'detail' | 'list'

async function fetchFeaturesForOrthophoto(orthophotoId: number): Promise<VectorFeature[]> {
  const layerPromises = FEATURE_TYPES.map(async (type) => {
    try {
      const fc = await getFeatures(type, { orthophotoId })
      return (fc?.features || []).map((f) => {
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
    } catch {
      return []
    }
  })
  const results = await Promise.all(layerPromises)
  return results.flat()
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
  const [reportLoading, setReportLoading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const hasProject = stage !== 'idle' || orthophoto !== null

  // Load latest completed project on initial mount if available
  useEffect(() => {
    let active = true
    async function loadInitialProject() {
      try {
        const ox = await getLatestOrthophoto()
        if (!active || !ox || !ox.id) return
        setOrthophoto(ox)
        const loaded = await fetchFeaturesForOrthophoto(ox.id)
        if (!active) return
        setFeatures(loaded)
        setStage('complete')
      } catch {
        // No existing orthophoto found, stay idle
      }
    }
    loadInitialProject()
    return () => {
      active = false
    }
  }, [])

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
      setJobStatus({ stage: 'queued', message: 'Uploading file...', progress: 2, done: false })
      setSelectedId(null)
      setFeatures([])
      setOrthophoto(null)

      try {
        const { jobId } = await uploadOrthophoto(file)
        const id = Number(jobId)

        // Poll pipeline status until complete or error (up to 15 mins for full GPU inference)
        let isDone = false
        let finalStatus: JobStatus | null = null

        for (let i = 0; i < 900 && !isDone; i++) {
          await new Promise((r) => setTimeout(r, 1000))
          try {
            const s = await getJobStatus(jobId)
            finalStatus = s
            lastStatusRef.current = s
            setJobStatus(s)
            if (s.stage && ['tiling', 'detecting', 'vectorizing', 'complete'].includes(s.stage)) {
              setStage(s.stage as PipelineStage)
            }
            if (s.done || s.stage === 'complete' || s.stage === 'error') {
              isDone = true
            }
          } catch {
            // ignore transient polling errors
          }
        }

        if (!isDone) {
          throw new Error('Pipeline processing took longer than expected. Please check server logs.')
        }

        if (finalStatus?.stage === 'error') {
          throw new Error(finalStatus.message || finalStatus.error || 'Pipeline failed')
        }

        // Pipeline is complete! Fetch orthophoto metadata and features
        try {
          const ox = await getOrthophoto(id)
          setOrthophoto(ox)
        } catch (err) {
          console.error('Failed to load orthophoto:', err)
        }

        const loadedFeatures = await fetchFeaturesForOrthophoto(id)
        setFeatures(loadedFeatures)
        setStage('complete')
        setJobStatus(null) // Dismiss progress overlay so user enters the QC workspace immediately
      } catch (err) {
        console.error('Upload or pipeline failed:', err)
        setStage('idle')
        setJobStatus({ stage: 'error', message: 'Upload or processing failed', progress: 0, done: true })
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

  const handleBatchApprove = useCallback(
    async (target: FeatureType | 'high_conf' | 'all') => {
      const toApprove = features.filter((f) => {
        if (f.status === 'approved') return false
        if (target === 'high_conf') return f.confidence >= 0.75
        if (target === 'all') return true
        return f.type === target
      })
      if (toApprove.length === 0) return
      const ids = toApprove.map((f) => f.id)
      const idSet = new Set(ids)
      setFeatures((prev) =>
        prev.map((f) => (idSet.has(f.id) ? { ...f, status: 'approved' as const } : f)),
      )
      try {
        await batchUpdateFeatures(ids, 'approved')
      } catch (err) {
        console.error('Batch approve failed:', err)
      }
    },
    [features],
  )

  const handleUpdateFeature = useCallback(
    async (id: number, patch: { status?: FeatureStatus; type?: FeatureType; className?: string; geometry?: GeoJSON.Geometry }) => {
      setFeatures((prev) =>
        prev.map((f) => (f.id === id ? { ...f, ...patch } : f)),
      )
      try {
        await updateFeature(id, patch)
      } catch (err) {
        console.error('Update feature failed:', err)
      }
    },
    [],
  )

  const handleUpdateFeatureGeometry = useCallback(
    async (id: number, geometry: GeoJSON.Geometry) => {
      setFeatures((prev) =>
        prev.map((f) => (f.id === id ? { ...f, geometry } : f)),
      )
      try {
        await updateFeature(id, { geometry })
      } catch (err) {
        console.error('Update feature geometry failed:', err)
      }
    },
    [],
  )

  const handleExportCompositePng = useCallback(() => {
    if (!orthophoto) return
    const activeFeatures = features.filter((f) => f.status !== 'rejected')
    exportOrthophotoImage(orthophoto, activeFeatures)
  }, [orthophoto, features])

  const handleExportImage = useCallback(
    (type: FeatureType) => {
      if (!orthophoto) return
      const typeFeatures = features.filter((f) => f.type === type && f.status === 'approved')
      exportOrthophotoImage(orthophoto, typeFeatures)
    },
    [orthophoto, features],
  )

  const handleBatchReject = useCallback(
    async (target: FeatureType | 'low_conf' | 'needs_review') => {
      const toReject = features.filter((f) => {
        if (f.status === 'rejected') return false
        if (target === 'low_conf') return f.confidence < 0.5
        if (target === 'needs_review') return f.status === 'needs_review'
        return f.type === target
      })
      if (toReject.length === 0) return
      const ids = toReject.map((f) => f.id)
      const idSet = new Set(ids)
      setFeatures((prev) =>
        prev.map((f) => (idSet.has(f.id) ? { ...f, status: 'rejected' as const } : f)),
      )
      try {
        await batchUpdateFeatures(ids, 'rejected')
      } catch (err) {
        console.error('Batch reject failed:', err)
      }
    },
    [features],
  )

  const handleExportVector = useCallback(
    async (
      type: FeatureType | 'all' = 'all',
      format: 'geojson' | 'kml' | 'csv' = 'geojson',
      status: 'all' | 'approved' = 'all',
    ) => {
      if (!orthophoto) return
      try {
        const blob = await exportGeojson(type, {
          orthophotoId: orthophoto.id,
          status,
          format,
        })
        const stem = orthophoto.filename?.replace(/\.[^.]+$/, '') || 'vectoreye'
        const suffix = type === 'all' ? 'all-vectors' : type
        const scopeTag = status === 'approved' ? 'approved' : 'full'
        const ext = format === 'kml' ? 'kml' : format === 'csv' ? 'csv' : 'geojson'
        downloadBlob(blob, `${stem}-${suffix}-${scopeTag}.${ext}`)
      } catch (err) {
        console.error('Vector export failed:', err)
      }
    },
    [orthophoto],
  )

  const handleExportGeojson = useCallback(
    (type: FeatureType | 'all' = 'all', status: 'all' | 'approved' = 'all') => {
      return handleExportVector(type, 'geojson', status)
    },
    [handleExportVector],
  )

  const handleExportKml = useCallback(
    (type: FeatureType | 'all' = 'all', status: 'all' | 'approved' = 'all') => {
      return handleExportVector(type, 'kml', status)
    },
    [handleExportVector],
  )

  const handleExportCsv = useCallback(
    (type: FeatureType | 'all' = 'all', status: 'all' | 'approved' = 'all') => {
      return handleExportVector(type, 'csv', status)
    },
    [handleExportVector],
  )

  const handleGenerateReport = useCallback(
    async (format: 'html' | 'json' = 'html') => {
      if (!orthophoto) return
      setReportLoading(true)
      try {
        const report = await generateReport(orthophoto.id)
        const stem = orthophoto.filename?.replace(/\.[^.]+$/, '') || 'vectoreye'
        if (format === 'html') {
          const htmlContent = generateReportHtml(report, orthophoto, features)
          const blob = new Blob([htmlContent], { type: 'text/html;charset=utf-8' })
          downloadBlob(blob, `${stem}-QC-Analysis-Report.html`)
        } else {
          const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' })
          downloadBlob(blob, `${stem}-qc-report.json`)
        }
      } catch (err) {
        console.error('Report generation failed:', err)
      } finally {
        setReportLoading(false)
      }
    },
    [orthophoto, features],
  )

  const onSelectFeature = useCallback((f: VectorFeature) => {
    setSelectedId(f.id)
    setQcView('detail')
    setEditing(false)
  }, [])

  return (
    <div className="contour-bg flex h-screen flex-col overflow-hidden">
      <TopBar
        stage={stage}
        hasProject={hasProject}
        activeTypes={activeTypes}
        onToggleType={toggleType}
        onFileSelected={handleFileChange}
        fileInputRef={fileInputRef}
        onBrowseClick={() => fileInputRef.current?.click()}
        onGenerateReport={() => handleGenerateReport('html')}
        reportLoading={reportLoading}
        onExportVector={handleExportVector}
        onExportCompositePng={handleExportCompositePng}
      />

      <div className="relative flex-1 min-h-0 h-full w-full overflow-hidden">
        <MapView
          hasProject={hasProject}
          orthophoto={orthophoto}
          features={features}
          visibleTypes={activeTypes}
          selectedId={selectedId}
          onSelectFeature={onSelectFeature}
          onApprove={handleApprove}
          onReject={handleReject}
          editing={editing}
          onToggleEdit={() => setEditing((e) => !e)}
          onUpdateFeatureGeometry={handleUpdateFeatureGeometry}
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
              onUpdateFeature={handleUpdateFeature}
              onBatchApprove={handleBatchApprove}
              onBatchReject={handleBatchReject}
              onToggleEdit={() => setEditing((e) => !e)}
              editing={editing}
              onExportImage={handleExportImage}
              onExportCompositePng={handleExportCompositePng}
              onExportGeojson={handleExportGeojson}
              onExportKml={handleExportKml}
              onExportCsv={handleExportCsv}
              onGenerateReport={handleGenerateReport}
              reportLoading={reportLoading}
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
  return <div className="absolute inset-0 pointer-events-none z-[1050] overflow-hidden">{children}</div>
}

export default App