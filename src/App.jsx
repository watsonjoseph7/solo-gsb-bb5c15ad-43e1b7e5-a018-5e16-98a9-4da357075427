import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchHealth, postCompensation, ApiError } from './api.js'
import { EXAMPLE_REQUEST, squarePoints, circlePoints } from './geometry.js'
import ContourCanvas from './components/ContourCanvas.jsx'
import PartCard from './components/PartCard.jsx'
import ResultPanel from './components/ResultPanel.jsx'

let uid = 0
const nextUid = () => ++uid

function newPart(index) {
  return {
    _key: nextUid(),
    _index: index,
    id: null,
    outer: { id: null, points: squarePoints(10 + index * 30, 10, 10) },
    holes: [],
  }
}

/** 去掉前端内部字段，构造请求 payload。 */
function toPayload(kerfWidth, parts) {
  return {
    kerf_width: Number(kerfWidth),
    parts: parts.map((p) => ({
      id: p.id ?? null,
      outer: { id: p.outer.id ?? null, points: p.outer.points },
      holes: p.holes.map((h) => ({ id: h.id ?? null, points: h.points })),
    })),
  }
}

export default function App() {
  const [health, setHealth] = useState(null)
  const [healthErr, setHealthErr] = useState(null)
  const [kerfWidth, setKerfWidth] = useState(0.4)
  const [parts, setParts] = useState(() => {
    const example = EXAMPLE_REQUEST.parts.map((p) => ({ ...p, _key: nextUid() }))
    return reindex(example)
  })
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  function reindex(list) {
    return list.map((p, i) => ({ ...p, _index: i }))
  }

  // 健康检查（每 10s 轮询）
  useEffect(() => {
    let stop = false
    const ctrl = new AbortController()
    const tick = () =>
      fetchHealth(ctrl.signal)
        .then((h) => !stop && (setHealth(h), setHealthErr(null)))
        .catch((e) => !stop && (setHealth(null), setHealthErr(e.message)))
    tick()
    const timer = setInterval(tick, 10000)
    return () => {
      stop = true
      ctrl.abort()
      clearInterval(timer)
    }
  }, [])

  const updatePart = useCallback((key, next) => {
    setParts((prev) => prev.map((p) => (p._key === key ? { ...next, _key: key } : p)))
  }, [])

  const removePart = useCallback((key) => {
    setParts((prev) => reindex(prev.filter((p) => p._key !== key)))
  }, [])

  const addPart = useCallback(() => {
    setParts((prev) => reindex([...prev, newPart(prev.length)]))
  }, [])

  const loadExample = useCallback(() => {
    const ex = JSON.parse(JSON.stringify(EXAMPLE_REQUEST))
    setKerfWidth(ex.kerf_width)
    setParts(reindex(ex.parts.map((p) => ({ ...p, _key: nextUid() }))))
    setResult(null)
    setError(null)
  }, [])

  const addCircleHoleDemo = useCallback(() => {
    setParts((prev) => {
      if (prev.length === 0) return prev
      const last = prev[prev.length - 1]
      const holes = [
        ...last.holes,
        { id: `circle-${last.holes.length}`, points: circlePoints(10, 10, 4, 20) },
      ]
      return prev.map((p) => (p._key === last._key ? { ...p, holes } : p))
    })
  }, [])

  const submit = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      const payload = toPayload(kerfWidth, parts)
      const res = await postCompensation(payload)
      setResult(res)
    } catch (e) {
      setResult(null)
      if (e instanceof ApiError) setError({ code: e.code, message: e.message, location: e.location })
      else setError({ code: 'UNKNOWN', message: String(e), location: null })
    } finally {
      setBusy(false)
    }
  }, [kerfWidth, parts])

  const errorLoc = useMemo(() => {
    if (!error?.location) return null
    return { ...error.location, message: error.message }
  }, [error])

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">◧</span>
          <div>
            <h1>刀缝补偿工作台</h1>
            <p className="muted">激光切割 · 外轮廓外扩 / 孔洞内缩 kerf_width / 2</p>
          </div>
        </div>
        <div className={`health ${health ? 'ok' : 'down'}`} title={healthErr || ''}>
          <span className="dot" />
          {health ? `后端在线 · GEOS ${health.geos_version}` : '后端离线（请先启动基座服务 :8000）'}
        </div>
      </header>

      <main className="layout">
        <aside className="panel editor-panel">
          <div className="panel-title">输入</div>

          <label className="field">
            <span>刀缝宽度 kerf_width</span>
            <input
              type="number"
              min="0"
              step="any"
              value={kerfWidth}
              onChange={(e) => setKerfWidth(e.target.value)}
            />
          </label>

          <div className="toolbar">
            <button type="button" className="btn" onClick={addPart}>+ 零件</button>
            <button type="button" className="btn" onClick={addCircleHoleDemo}>+ 圆孔示例</button>
            <button type="button" className="btn" onClick={loadExample}>载入示例</button>
          </div>

          <div className="parts-list">
            {parts.map((part) => (
              <PartCard
                key={part._key}
                part={part}
                index={part._index}
                onChange={(next) => updatePart(part._key, next)}
                onRemove={() => removePart(part._key)}
                errorLoc={errorLoc}
              />
            ))}
            {parts.length === 0 && (
              <p className="muted empty-hint">还没有零件，点击「+ 零件」或「载入示例」。</p>
            )}
          </div>

          <button
            type="button"
            className="btn btn-primary submit-btn"
            disabled={busy || parts.length === 0}
            onClick={submit}
          >
            {busy ? '计算中…' : '计算刀缝补偿'}
          </button>

          {error && (
            <div className="error-box" role="alert">
              <div className="error-code">{error.code}</div>
              <div>{error.message}</div>
              {error.location && (
                <div className="error-loc">
                  定位：part_index={error.location.part_index}
                  ，contour_index={error.location.contour_index}
                  {error.location.part_id != null && `，part_id=${error.location.part_id}`}
                  {error.location.contour_id != null && `，contour_id=${error.location.contour_id}`}
                </div>
              )}
            </div>
          )}
        </aside>

        <section className="panel view-panel">
          <div className="panel-title">轨迹预览</div>
          <ContourCanvas inputParts={parts} result={result} errorLoc={errorLoc} />
          <ResultPanel result={result} />
        </section>
      </main>
    </div>
  )
}
