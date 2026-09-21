import ContourEditor from './ContourEditor.jsx'

/**
 * 零件卡片：外轮廓 + 孔洞列表的编辑。
 * part._index 为原始请求下标（用于错误定位高亮）。
 */
export default function PartCard({ part, index, onChange, onRemove, errorLoc }) {
  const update = (patch) => onChange({ ...part, ...patch })

  const setHole = (i, hole) =>
    update({ holes: part.holes.map((h, j) => (j === i ? hole : h)) })

  const addHole = () =>
    update({
      holes: [
        ...part.holes,
        {
          id: null,
          points: [
            { x: 2, y: 2 },
            { x: 6, y: 2 },
            { x: 6, y: 6 },
            { x: 2, y: 6 },
          ],
        },
      ],
    })

  const removeHole = (i) =>
    update({ holes: part.holes.filter((_, j) => j !== i) })

  const errHere = (contourIndex) =>
    errorLoc &&
    errorLoc.part_index === index &&
    errorLoc.contour_index === contourIndex
      ? errorLoc.message
      : null

  return (
    <section className="part-card">
      <header className="part-head">
        <span className="part-badge">零件 #{index}</span>
        <input
          className="id-input"
          placeholder="零件 id（可选）"
          value={part.id ?? ''}
          onChange={(e) => update({ id: e.target.value || null })}
        />
        <button type="button" className="btn btn-ghost btn-sm" onClick={onRemove}>
          删除零件
        </button>
      </header>

      <ContourEditor
        title="外轮廓"
        contour={part.outer}
        onChange={(outer) => update({ outer })}
        error={errHere(-1)}
      />

      <div className="holes-block">
        <div className="holes-head">
          <span>孔洞（{part.holes.length}）</span>
          <button type="button" className="btn btn-ghost btn-sm" onClick={addHole}>
            + 添加孔洞
          </button>
        </div>
        {part.holes.map((hole, i) => (
          <ContourEditor
            key={i}
            title={`孔洞 #${i}`}
            contour={hole}
            onChange={(h) => setHole(i, h)}
            onRemove={() => removeHole(i)}
            error={errHere(i)}
          />
        ))}
      </div>
    </section>
  )
}
