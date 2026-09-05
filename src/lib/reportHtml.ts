import type { AnalyticalReport } from '../api'
import type { Orthophoto, VectorFeature } from '../types'
import { FEATURE_LABELS } from './constants'

export function generateReportHtml(
  report: AnalyticalReport,
  orthophoto: Orthophoto | null,
  features: VectorFeature[],
): string {
  const stats = (report.statistics || {}) as Record<string, any>

  // Compute live counts directly from active features state
  const statusCounts = { approved: 0, rejected: 0, needs_review: 0, pending: 0 }
  const byType: Record<string, { total: number; approved: number; rejected: number; needs_review: number; pending: number }> = {}

  if (features && features.length > 0) {
    for (const f of features) {
      const st = (f.status || 'pending') as keyof typeof statusCounts
      if (statusCounts[st] !== undefined) statusCounts[st]++
      if (!byType[f.type]) {
        byType[f.type] = { total: 0, approved: 0, rejected: 0, needs_review: 0, pending: 0 }
      }
      byType[f.type].total++
      if (byType[f.type][st] !== undefined) byType[f.type][st]++
    }
  } else {
    Object.assign(statusCounts, stats.status_counts || {})
    Object.assign(byType, stats.by_feature_type || {})
  }

  const approvedTotal = statusCounts.approved
  const total = (features && features.length) || stats.total_features || 0
  const rate = total > 0 ? Math.round((approvedTotal / total) * 100) : 0
  const filename = orthophoto?.filename || report.filename || 'orthophoto.tif'
  const generatedDate = new Date(report.generated_at || Date.now()).toLocaleString()

  const summaryParts = [
    `${approvedTotal.toLocaleString()} approved (${rate}%)`,
    `${statusCounts.needs_review.toLocaleString()} need review`,
    `${statusCounts.rejected.toLocaleString()} rejected`,
  ]
  if (statusCounts.pending > 0) {
    summaryParts.push(`${statusCounts.pending.toLocaleString()} pending`)
  }
  const summaryText = `Detected ${total.toLocaleString()} features across ${Object.keys(byType).length} classes: ${summaryParts.join(', ')}.`

  let narrative = report.narrative
  if (!narrative || narrative.includes('HTTP Error') || narrative.includes('unavailable') || narrative.includes('429') || narrative.includes('Too Many Requests')) {
    const classNames = Object.keys(byType).map((t) => FEATURE_LABELS[t as keyof typeof FEATURE_LABELS] || t).join(', ')
    narrative = `Automated geospatial intelligence audit completed for ${total.toLocaleString()} vector features across layers (${classNames}). Currently ${approvedTotal.toLocaleString()} features (${rate}%) satisfy high-precision geometric confidence standards and are approved for cadastral delivery. ${
      statusCounts.needs_review > 0
        ? `${statusCounts.needs_review.toLocaleString()} features are queued for analyst review to verify low-confidence boundaries.`
        : 'All features have satisfied boundary confidence criteria.'
    } ${
      statusCounts.rejected > 0
        ? `${statusCounts.rejected.toLocaleString()} non-conforming detections were rejected.`
        : ''
    }`
  }

  const layerRows = Object.entries(byType)
    .map(([type, counts]) => {
      const label = FEATURE_LABELS[type as keyof typeof FEATURE_LABELS] || type
      const count = counts.total || 0
      const app = counts.approved || 0
      const rev = counts.needs_review || 0
      const rej = counts.rejected || 0
      return `
        <tr>
          <td style="padding: 10px 14px; font-weight: 600; text-transform: capitalize;">${label}</td>
          <td style="padding: 10px 14px; text-align: right; font-family: monospace;">${count.toLocaleString()}</td>
          <td style="padding: 10px 14px; text-align: right; font-family: monospace; color: #10b981;">${app.toLocaleString()}</td>
          <td style="padding: 10px 14px; text-align: right; font-family: monospace; color: #f59e0b;">${rev.toLocaleString()}</td>
          <td style="padding: 10px 14px; text-align: right; font-family: monospace; color: #ef4444;">${rej.toLocaleString()}</td>
        </tr>
      `
    })
    .join('')

  const liveRecs: string[] = []
  if (statusCounts.needs_review > 0) {
    liveRecs.push(`Review ${statusCounts.needs_review.toLocaleString()} low-confidence features before final municipal export.`)
  }
  if (statusCounts.pending > 0) {
    liveRecs.push(`Complete QC verification on ${statusCounts.pending.toLocaleString()} pending features prior to analyst sign-off.`)
  }
  if (statusCounts.rejected > 0) {
    liveRecs.push(`${statusCounts.rejected.toLocaleString()} non-conforming features were rejected and will be omitted from vector export deliverables.`)
  }
  if (approvedTotal > 0) {
    liveRecs.push(`${approvedTotal.toLocaleString()} verified vector features (${rate}%) meet high precision geometric standards and are approved for GIS release.`)
  }
  if (rate === 100) {
    liveRecs.push(`100% Quality Control achieved — full dataset ready for immediate CAD/GIS production deployment.`)
  }
  const recommendations = liveRecs
    .map((r) => `<li style="margin-bottom: 8px; line-height: 1.5;">${r}</li>`)
    .join('')

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>VectorEye QC Analytical Report - ${filename}</title>
  <style>
    @media print {
      body { background: #fff !important; color: #111 !important; }
      .no-print { display: none !important; }
      .page-card { box-shadow: none !important; border: 1px solid #ddd !important; }
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background: #0a0e17;
      color: #e2e8f0;
      padding: 40px 20px;
    }
    .container {
      max-width: 900px;
      margin: 0 auto;
    }
    .page-card {
      background: #111622;
      border: 1px solid rgba(34, 211, 238, 0.25);
      border-radius: 12px;
      padding: 36px;
      box-shadow: 0 12px 40px rgba(0,0,0,0.5);
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      border-bottom: 1px solid rgba(34, 211, 238, 0.2);
      padding-bottom: 24px;
      margin-bottom: 28px;
    }
    .logo {
      font-size: 24px;
      font-weight: 700;
      letter-spacing: 2px;
    }
    .logo span { color: #22d3ee; }
    .badge {
      font-family: monospace;
      font-size: 11px;
      padding: 4px 10px;
      border-radius: 6px;
      background: rgba(34, 211, 238, 0.15);
      color: #22d3ee;
      border: 1px solid rgba(34, 211, 238, 0.3);
      text-transform: uppercase;
    }
    .grid-4 {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
      margin-bottom: 30px;
    }
    .stat-card {
      background: rgba(15, 23, 42, 0.7);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 8px;
      padding: 16px;
      text-align: center;
    }
    .stat-label {
      font-size: 10px;
      letter-spacing: 1px;
      text-transform: uppercase;
      color: #94a3b8;
      margin-bottom: 6px;
    }
    .stat-val {
      font-size: 26px;
      font-weight: 700;
      font-family: monospace;
    }
    h2 {
      font-size: 16px;
      letter-spacing: 1px;
      text-transform: uppercase;
      color: #22d3ee;
      margin: 28px 0 14px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    p {
      line-height: 1.6;
      color: #cbd5e1;
      font-size: 14px;
      margin-bottom: 12px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 10px;
      background: rgba(15, 23, 42, 0.5);
      border-radius: 8px;
      overflow: hidden;
      font-size: 13px;
    }
    th {
      background: rgba(34, 211, 238, 0.1);
      color: #22d3ee;
      padding: 12px 14px;
      text-align: left;
      font-weight: 600;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 1px;
    }
    th:not(:first-child) { text-align: right; }
    td { border-bottom: 1px solid rgba(255,255,255,0.05); }
    ul { margin-left: 20px; font-size: 13px; color: #cbd5e1; }
    .print-btn {
      background: #22d3ee;
      color: #0a0e17;
      font-weight: 600;
      border: none;
      padding: 10px 20px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 13px;
      transition: opacity 0.2s;
    }
    .print-btn:hover { opacity: 0.85; }
    .footer {
      margin-top: 40px;
      padding-top: 20px;
      border-top: 1px solid rgba(255,255,255,0.08);
      display: flex;
      justify-content: space-between;
      font-size: 11px;
      color: #64748b;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="no-print" style="margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
      <span style="font-size: 13px; color: #94a3b8;">VectorEye Automated GIS QC Audit Report</span>
      <button class="print-btn" onclick="window.print()">Print / Save as PDF</button>
    </div>

    <div class="page-card">
      <div class="header">
        <div>
          <div class="logo">VECTOR<span>EYE</span></div>
          <p style="margin-top: 6px; font-size: 12px; color: #94a3b8;">Geospatial Feature Extraction &amp; Quality Control Audit</p>
        </div>
        <div style="text-align: right;">
          <div class="badge">GIS Analyst Sign-off</div>
          <p style="margin-top: 6px; font-size: 11px; font-family: monospace; color: #64748b;">${generatedDate}</p>
        </div>
      </div>

      <div class="grid-4">
        <div class="stat-card">
          <div class="stat-label">Total Features</div>
          <div class="stat-val" style="color: #22d3ee;">${total.toLocaleString()}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Approved</div>
          <div class="stat-val" style="color: #10b981;">${approvedTotal.toLocaleString()}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Needs Review</div>
          <div class="stat-val" style="color: #f59e0b;">${(statusCounts.needs_review || 0).toLocaleString()}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Approval Rate</div>
          <div class="stat-val" style="color: #a855f7;">${rate}%</div>
        </div>
      </div>

      <h2>Executive Summary</h2>
      <p>${summaryText}</p>
      ${narrative ? `<p style="font-style: italic; color: #94a3b8; border-left: 2px solid #22d3ee; padding-left: 12px; margin-top: 8px;">${narrative}</p>` : ''}

      <h2>Raster Georeferencing Details</h2>
      <table style="margin-bottom: 24px;">
        <tr>
          <th style="width: 35%;">Parameter</th>
          <th style="text-align: left;">Value</th>
        </tr>
        <tr>
          <td style="padding: 10px 14px; font-weight: 600;">Source File</td>
          <td style="padding: 10px 14px; font-family: monospace;">${filename}</td>
        </tr>
        <tr>
          <td style="padding: 10px 14px; font-weight: 600;">Raster Dimensions</td>
          <td style="padding: 10px 14px; font-family: monospace;">${orthophoto?.width || stats.width || 'N/A'} &times; ${orthophoto?.height || stats.height || 'N/A'} px</td>
        </tr>
        <tr>
          <td style="padding: 10px 14px; font-weight: 600;">Coordinate Reference System</td>
          <td style="padding: 10px 14px; font-family: monospace;">${stats.crs || 'EPSG:4326 (WGS84)'}</td>
        </tr>
        <tr>
          <td style="padding: 10px 14px; font-weight: 600;">Geographic Bounding Box</td>
          <td style="padding: 10px 14px; font-family: monospace; font-size: 11px;">
            ${orthophoto?.bounds ? JSON.stringify(orthophoto.bounds) : 'Standard extent'}
          </td>
        </tr>
      </table>

      <h2>Feature Inventory &amp; QC Breakdown</h2>
      <table>
        <thead>
          <tr>
            <th>Feature Layer</th>
            <th>Extracted</th>
            <th>Approved</th>
            <th>Needs Review</th>
            <th>Rejected</th>
          </tr>
        </thead>
        <tbody>
          ${layerRows || '<tr><td colspan="5" style="padding: 14px; text-align: center;">No layers found</td></tr>'}
        </tbody>
        <tfoot>
          <tr style="border-top: 2px solid rgba(34, 211, 238, 0.3); font-weight: 700; background: rgba(34, 211, 238, 0.05);">
            <td style="padding: 10px 14px; text-transform: uppercase; color: #22d3ee;">Total</td>
            <td style="padding: 10px 14px; text-align: right; font-family: monospace;">${total.toLocaleString()}</td>
            <td style="padding: 10px 14px; text-align: right; font-family: monospace; color: #10b981;">${approvedTotal.toLocaleString()}</td>
            <td style="padding: 10px 14px; text-align: right; font-family: monospace; color: #f59e0b;">${(statusCounts.needs_review || 0).toLocaleString()}</td>
            <td style="padding: 10px 14px; text-align: right; font-family: monospace; color: #ef4444;">${(statusCounts.rejected || 0).toLocaleString()}</td>
          </tr>
        </tfoot>
      </table>

      <h2>Quality Recommendations</h2>
      <ul>
        ${recommendations || '<li>All features satisfy standard geometric confidence criteria.</li>'}
      </ul>

      <div class="footer">
        <span>VectorEye v0.1.0 &middot; Deep Learning Geospatial Intelligence Platform</span>
        <span>Generated for Analyst Verification &middot; Confidential</span>
      </div>
    </div>
  </div>
</body>
</html>`
}
