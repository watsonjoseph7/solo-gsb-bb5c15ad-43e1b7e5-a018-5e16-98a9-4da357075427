/** 与基座 FastAPI 服务通信的轻量客户端。 */

export class ApiError extends Error {
  constructor(code, message, location, status) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.location = location
    this.status = status
  }
}

export async function fetchHealth(signal) {
  const res = await fetch('/health', { signal })
  if (!res.ok) throw new Error(`健康检查失败：HTTP ${res.status}`)
  return res.json()
}

/**
 * 提交刀缝补偿请求。
 * 成功返回响应 JSON；失败抛出 ApiError（422 时携带 code / location）。
 */
export async function postCompensation(payload) {
  let res
  try {
    res = await fetch('/api/v1/kerf-compensation', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  } catch (err) {
    throw new ApiError('NETWORK', `无法连接后端服务：${err.message}`, null, 0)
  }

  const body = await res.json().catch(() => null)
  if (res.ok) return body

  // 几何语义错误：{ error: { code, message, location } }
  if (body?.error) {
    throw new ApiError(
      body.error.code ?? 'GEOMETRY_ERROR',
      body.error.message ?? '几何语义错误',
      body.error.location ?? null,
      res.status,
    )
  }
  // 请求校验错误：FastAPI 默认 { detail: [...] }
  if (Array.isArray(body?.detail)) {
    const msg = body.detail
      .map((d) => `${(d.loc ?? []).join('.')}：${d.msg}`)
      .join('；')
    throw new ApiError('VALIDATION', `请求校验失败 — ${msg}`, null, res.status)
  }
  throw new ApiError(`HTTP_${res.status}`, `请求失败：HTTP ${res.status}`, null, res.status)
}
