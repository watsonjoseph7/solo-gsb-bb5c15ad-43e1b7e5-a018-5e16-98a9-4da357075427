/**
 * 单条闭合轮廓编辑器：可选 id + 点坐标表格（增删点、编辑坐标）。
 */
export default function ContourEditor({ title, contour, onChange, onRemove, error }) {
  const setId = (id) => onChange({ ...contour, id: id || null })

  const setPoint = (i, axis, raw) => {
    const points = contour.points.map((p, j) =>
      j === i ? { ...p, [axis]: raw === '' ? '' : Number(raw) } : p,
    )
    onChange({ ...contour, points })
  }

  const addPoint = () =>
    onChange({ ...contour, points: [...contour.points, { x: 0, y: 0 }] })

  const removePoint = (i) =>
    onChange({
      ...contour,
      points: contour.points.filter((_, j) => j !== i),
    })

  return (
    <div className={`contour-editor ${error ? 'contour-error' : ''}`}>
      <div className="contour-head">
        <span className="contour-title">{title}</span>
        <input
          className="id-input"
          placeholder="轮廓 id（可选）"
          value={contour.id ?? ''}
          onChange={(e) => setId(e.target.value)}
        />
        {onRemove && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={onRemove}>
            删除
          </button>
        )}
      </div>

      <table className="points-table">
        <thead>
          <tr>
            <th>#</th>
            <th>x</th>
            <th>y</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {contour.points.map((p, i) => (
            <tr key={i}>
              <td className="idx">{i}</td>
              <td>
                <input
                  type="number"
                  step="any"
                  value={p.x}
                  onChange={(e) => setPoint(i, 'x', e.target.value)}
                />
              </td>
              <td>
                <input
                  type="number"
                  step="any"
                  value={p.y}
                  onChange={(e) => setPoint(i, 'y', e.target.value)}
                />
              </td>
              <td>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  title="删除该点"
                  onClick={() => removePoint(i)}
                >
                  ×
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <button type="button" className="btn btn-ghost btn-sm" onClick={addPoint}>
        + 添加点
      </button>
      {error && <div className="contour-error-tag">⚠ {error}</div>}
    </div>
  )
}
