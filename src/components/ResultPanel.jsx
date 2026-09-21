/**
 * 补偿结果面板：按零件分组展示轨迹环的元信息
 * （role / id / 点数 / 绕向 / 面积 / 源轮廓下标）。
 */
export default function ResultPanel({ result }) {
  if (!result) return null

  return (
    <div className="result-panel">
      <div className="result-summary">
        <span>刀缝宽度 <b>{result.kerf_width}</b></span>
        <span>单侧偏移 <b>{result.offset}</b></span>
        <span>零件数 <b>{result.parts.length}</b></span>
      </div>

      {result.parts.map((part) => (
        <div key={part.part_index} className="result-part">
          <div className="result-part-head">
            <b>{part.id ?? `零件 #${part.part_index}`}</b>
            <span className="muted">part_index = {part.part_index}</span>
          </div>
          <RingRow ring={part.outer} />
          {part.holes.map((h) => (
            <RingRow key={h.source_contour_index} ring={h} />
          ))}
        </div>
      ))}
    </div>
  )
}

function RingRow({ ring }) {
  return (
    <div className="ring-row">
      <span className={`role-tag role-${ring.role}`}>
        {ring.role === 'outer' ? '外轮廓' : '孔洞'}
      </span>
      <span className="ring-id">{ring.id ?? '—'}</span>
      <span className="muted">{ring.points.length} 点</span>
      <span className="muted">{ring.orientation}</span>
      <span className="muted">面积 {ring.area.toFixed(4)}</span>
      <span className="muted">源 #{ring.source_contour_index}</span>
    </div>
  )
}
