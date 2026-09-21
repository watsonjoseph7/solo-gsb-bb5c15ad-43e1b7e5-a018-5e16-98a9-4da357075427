import { useEffect, useMemo, useRef } from 'react'
import { boundsOf } from '../geometry.js'

/**
 * 轨迹画布：原始输入轮廓（虚线）叠加补偿后刀具中心轨迹（实线）。
 * 数学坐标系（y 向上），绘制时做 y 翻转；网格步长自适应。
 */
export default function ContourCanvas({ inputParts, result, errorLoc }) {
  const canvasRef = useRef(null)
  const wrapRef = useRef(null)

  const scene = useMemo(() => {
    const inputRings = []
    for (const part of inputParts) {
      if (part.outer?.points?.length >= 3) {
        inputRings.push({
          pts: part.outer.points,
          role: 'outer',
          partIndex: part._index,
          contourIndex: -1,
        })
      }
      ;(part.holes || []).forEach((h, i) => {
        if (h.points?.length >= 3) {
          inputRings.push({
            pts: h.points,
            role: 'hole',
            partIndex: part._index,
            contourIndex: i,
          })
        }
      })
    }
    const outRings = []
    if (result?.parts) {
      for (const part of result.parts) {
        outRings.push({ ...part.outer, pts: part.outer.points })
        for (const h of part.holes) outRings.push({ ...h, pts: h.points })
      }
    }
    const bounds = boundsOf([
      ...inputRings.map((r) => r.pts),
      ...outRings.map((r) => r.pts),
    ])
    return { inputRings, outRings, bounds }
  }, [inputParts, result])

  useEffect(() => {
    const canvas = canvasRef.current
    const wrap = wrapRef.current
    if (!canvas || !wrap) return

    const draw = () => {
      const dpr = window.devicePixelRatio || 1
      const w = wrap.clientWidth
      const h = Math.max(340, wrap.clientHeight)
      canvas.width = w * dpr
      canvas.height = h * dpr
      canvas.style.width = `${w}px`
      canvas.style.height = `${h}px`
      const ctx = canvas.getContext('2d')
      ctx.scale(dpr, dpr)
      ctx.fillStyle = '#0d1117'
      ctx.fillRect(0, 0, w, h)

      const b = scene.bounds
      if (!b) {
        ctx.fillStyle = '#8b949e'
        ctx.font = '14px system-ui, sans-serif'
        ctx.textAlign = 'center'
        ctx.fillText('添加零件轮廓后在此预览', w / 2, h / 2)
        return
      }

      const pad = 36
      const spanX = Math.max(b.maxX - b.minX, 1e-6)
      const spanY = Math.max(b.maxY - b.minY, 1e-6)
      const scale = Math.min((w - pad * 2) / spanX, (h - pad * 2) / spanY)
      const ox = pad + (w - pad * 2 - spanX * scale) / 2
      const oy = pad + (h - pad * 2 - spanY * scale) / 2
      const toX = (x) => ox + (x - b.minX) * scale
      const toY = (y) => h - (oy + (y - b.minY) * scale) // y 翻转

      // 网格（1/2/5 序列自适应步长）
      const raw = Math.max(spanX, spanY) / 10
      const mag = Math.pow(10, Math.floor(Math.log10(raw)))
      const step = raw / mag >= 5 ? 5 * mag : raw / mag >= 2 ? 2 * mag : mag
      ctx.strokeStyle = '#21262d'
      ctx.lineWidth = 1
      ctx.beginPath()
      for (let gx = Math.floor(b.minX / step) * step; gx <= b.maxX + step; gx += step) {
        ctx.moveTo(toX(gx), toY(b.minY))
        ctx.lineTo(toX(gx), toY(b.maxY))
      }
      for (let gy = Math.floor(b.minY / step) * step; gy <= b.maxY + step; gy += step) {
        ctx.moveTo(toX(b.minX), toY(gy))
        ctx.lineTo(toX(b.maxX), toY(gy))
      }
      ctx.stroke()

      const trace = (pts) => {
        ctx.beginPath()
        pts.forEach((p, i) => {
          if (i === 0) ctx.moveTo(toX(p.x), toY(p.y))
          else ctx.lineTo(toX(p.x), toY(p.y))
        })
        ctx.closePath()
      }

      const isErr = (ring) =>
        errorLoc &&
        ring.partIndex === errorLoc.part_index &&
        ring.contourIndex === errorLoc.contour_index

      // 原始输入轮廓：虚线
      for (const ring of scene.inputRings) {
        trace(ring.pts)
        ctx.setLineDash([6, 4])
        ctx.lineWidth = 1.5
        ctx.strokeStyle = isErr(ring)
          ? '#f85149'
          : ring.role === 'outer'
            ? '#8b949e'
            : '#6e7681'
        ctx.stroke()
        ctx.setLineDash([])
        ctx.fillStyle = '#8b949e'
        for (const p of ring.pts) {
          ctx.fillRect(toX(p.x) - 1.5, toY(p.y) - 1.5, 3, 3)
        }
      }

      // 补偿后轨迹：实线 + 顶点圆点
      for (const ring of scene.outRings) {
        const color = ring.role === 'outer' ? '#58a6ff' : '#d2a8ff'
        trace(ring.pts)
        ctx.lineWidth = 2
        ctx.strokeStyle = color
        ctx.stroke()
        ctx.fillStyle = color
        for (const p of ring.pts) {
          ctx.beginPath()
          ctx.arc(toX(p.x), toY(p.y), 2.2, 0, Math.PI * 2)
          ctx.fill()
        }
      }

      ctx.fillStyle = '#8b949e'
      ctx.font = '11px ui-monospace, monospace'
      ctx.textAlign = 'left'
      ctx.fillText(`grid ${step} · scale ${scale.toFixed(2)} px/unit`, 10, h - 10)
    }

    draw()
    const ro = new ResizeObserver(draw)
    ro.observe(wrap)
    return () => ro.disconnect()
  }, [scene, errorLoc])

  return (
    <div className="canvas-wrap" ref={wrapRef}>
      <canvas ref={canvasRef} />
      <div className="canvas-legend">
        <span><i className="swatch swatch-input" />原始轮廓</span>
        <span><i className="swatch swatch-outer" />外轮廓轨迹</span>
        <span><i className="swatch swatch-hole" />孔洞轨迹</span>
        {errorLoc && <span><i className="swatch swatch-error" />出错轮廓</span>}
      </div>
    </div>
  )
}
