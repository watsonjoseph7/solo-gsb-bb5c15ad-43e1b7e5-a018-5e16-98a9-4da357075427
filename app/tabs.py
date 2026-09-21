"""微连接（留桥 / tabs）切割段生成。

在已生成的**补偿轨迹**（规范化点列，首尾不重复）上，沿弧长居中留出
不切割的缺口，把闭合环切成若干按切割顺序排列的开放段。

输入约定
--------
- ``coords``：补偿后、绕向 / 起点已规范化的闭合点列（与响应 ``points`` 一致），
  切割方向即点列前进方向，起点 ``coords[0]`` 对应归一化位置 0；
- 每个 tab 以归一化周长位置 ``position``（0 ≤ p < 1）与实际宽度 ``width`` 给出，
  缺口为 ``[position*L - width/2, position*L + width/2]``（L 为补偿轨迹周长）。

合并规则（在闭合环上）
----------------------
1. 缺口跨越首尾（s=0）时拆成 [0,·] 与 [·,L] 两段参与一维合并，最终按闭合环接回；
2. 互相重叠或首尾相接的缺口合并；从两侧抵达首尾点的缺口同样在首尾处合并；
3. 合并后缺口总长度覆盖整圈（没有任何切割段）时抛出
   :class:`CompensationError`（``TAB_COVERS_RING``），由上层整单拒绝。

输出
----
开放段列表（折线点列），顺序即沿环从起点出发的切割顺序：
段内保留轨迹全部原拐点，并在留桥边界处精确插入插值点；
未配置 tabs 时仅返回一个与完整环点列一致的段。
"""

from __future__ import annotations

import bisect
import math

from .errors import CompensationError, ErrorCode
from .schemas import Tab

# 浮点容差按周长缩放（坐标单位自洽），用于端点相接判定与整圈覆盖判定
_TOL_REL = 1e-9


def _cumulative_lengths(
    coords: list[tuple[float, float]],
) -> tuple[list[float], float]:
    """返回各顶点的累计弧长（长度 n+1，末值为周长 L）。"""
    n = len(coords)
    cum = [0.0]
    total = 0.0
    for i in range(n):
        x1, y1 = coords[i]
        x2, y2 = coords[(i + 1) % n]
        total += math.hypot(x2 - x1, y2 - y1)
        cum.append(total)
    return cum, total


def _point_at(
    coords: list[tuple[float, float]],
    cum: list[float],
    s: float,
) -> tuple[float, float]:
    """弧长位置 s 处的精确坐标（边为直线段，线性插值即精确）。"""
    n = len(coords)
    length = cum[-1]
    # 归一到 [0, L]；L 与 0 是同一点（起点）
    s = min(max(s, 0.0), length)
    i = bisect.bisect_right(cum, s) - 1
    if i >= n:
        return coords[0]
    edge_len = cum[i + 1] - cum[i]
    if edge_len <= 0.0:
        return coords[i]
    t = (s - cum[i]) / edge_len
    if t <= 0.0:
        return coords[i]
    if t >= 1.0:
        return coords[(i + 1) % n]
    x1, y1 = coords[i]
    x2, y2 = coords[(i + 1) % n]
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def _same_point(
    a: tuple[float, float],
    b: tuple[float, float],
    tol: float,
) -> bool:
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def _merge_intervals(
    intervals: list[tuple[float, float]],
    tol: float,
) -> list[tuple[float, float]]:
    """合并一维重叠 / 相接区间（输入会被排序）。"""
    intervals.sort()
    merged: list[tuple[float, float]] = []
    for a, b in intervals:
        if merged and a <= merged[-1][1] + tol:
            if b > merged[-1][1]:
                merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return merged


def _build_segment_points(
    coords: list[tuple[float, float]],
    cum: list[float],
    start: float,
    end: float,
    *,
    wrap: bool,
    tol: float,
) -> list[tuple[float, float]]:
    """构造从弧长 start 前进到 end 的开放折线段点列。

    - 保留路径上的全部原拐点（顶点严格位于区间内部时纳入）；
    - 两端插入精确的留桥边界点；与拐点重合时去重；
    - ``wrap=True`` 表示区间跨越首尾（end < start，或经 s=L/0 绕行）。
    """
    length = cum[-1]
    points: list[tuple[float, float]] = [_point_at(coords, cum, start)]

    n = len(coords)
    if wrap:
        # 弧从 start 前进、越过 s=L/0 到 end：按穿越顺序收集内部拐点，
        # 先收 s>start 的顶点，再收首尾顶点（恰位于接缝，且不是端点时），
        # 最后收 s<end 的顶点；首尾顶点是循环点（s=0≡L），不在 1..n-1 中
        for i in range(1, n):
            if cum[i] > start + tol:
                points.append(coords[i])
        if start < length - tol and end > tol:
            points.append(coords[0])
        for i in range(1, n):
            if cum[i] < end - tol:
                points.append(coords[i])
    else:
        # 非跨越弧不含首尾顶点（s=0），仅收集严格位于 (start, end) 内的顶点
        for i in range(1, n):
            if start + tol < cum[i] < end - tol:
                points.append(coords[i])

    end_s = end % length if end > 0.0 else 0.0
    end_point = _point_at(coords, cum, end_s)
    if not _same_point(points[-1], end_point, tol):
        points.append(end_point)

    # 边界点与相邻拐点可能仅差浮点误差，去重保证折线干净
    deduped = [points[0]]
    for p in points[1:]:
        if not _same_point(deduped[-1], p, tol):
            deduped.append(p)
    return deduped


def build_segments(
    coords: list[tuple[float, float]],
    tabs: list[Tab],
    *,
    part_index: int,
    contour_index: int,
    part_id: str | None,
    contour_id: str | None,
) -> list[list[tuple[float, float]]]:
    """在补偿轨迹上扣除留桥，返回按切割顺序排列的开放段。

    留桥覆盖整圈时抛出带原始轮廓定位的 :class:`CompensationError`。
    """
    # 未配置 tabs：仅含完整环，点列与响应 points 完全一致
    if not tabs:
        return [list(coords)]

    cum, length = _cumulative_lengths(coords)
    tol = _TOL_REL * max(1.0, length)

    def _cover_error(detail: str) -> CompensationError:
        return CompensationError(
            ErrorCode.TAB_COVERS_RING,
            part_index=part_index,
            contour_index=contour_index,
            part_id=part_id,
            contour_id=contour_id,
            detail=detail,
        )

    # ---- 1. 每个留桥 -> [0, L] 上的区间；跨首尾者拆成首尾两段 ----
    intervals: list[tuple[float, float]] = []
    for tab in tabs:
        width = tab.width
        if width + tol >= length:
            # 单个留桥即达到 / 超过整圈周长
            raise _cover_error(
                f"留桥宽度 {width:g} 不小于补偿轨迹周长 {length:g}"
            )
        center = tab.position * length
        start = center - width / 2.0
        end = center + width / 2.0
        if start < -tol:
            # 越过 s=0：尾段 [start+L, L]，首段 [0, end]
            intervals.append((start + length, length))
            intervals.append((0.0, max(end, 0.0)))
        elif end > length + tol:
            # 越过 s=L：首段 [0, end-L]，尾段 [start, L]
            intervals.append((0.0, end - length))
            intervals.append((max(start, 0.0), length))
        else:
            # 不跨越；边界恰好落在首尾点时贴边，便于在首尾处相接合并
            a = 0.0 if start <= tol else start
            b = length if end >= length - tol else end
            intervals.append((a, b))

    # ---- 2. 一维合并重叠 / 相接区间 ----
    merged = _merge_intervals(intervals, tol)

    # 单一区间即覆盖 [0, L]
    for a, b in merged:
        if a <= tol and b >= length - tol:
            raise _cover_error("留桥合并后覆盖补偿轨迹整圈")

    # 缺口总长度达到周长即整圈覆盖（合并后各区间互不重叠）
    gap_total = sum(b - a for a, b in merged)
    if gap_total >= length - tol:
        raise _cover_error("留桥合并后覆盖补偿轨迹整圈")

    # ---- 3. 首尾相接判定 ----
    # head：缺口覆盖 s=0 一侧（[0,·]）；tail：缺口覆盖 s=L 一侧（[·,L]）。
    # 二者同时存在（或为同一整圈区间，前面已拒绝）时，缺口跨越 / 包夹首尾点。
    head = next((iv for iv in merged if iv[0] <= tol), None)
    tail = next((iv for iv in merged if iv[1] >= length - tol), None)
    seam_gapped = head is not None and tail is not None

    # ---- 4. 在 [0, L] 内求缺口补集（切割片段）----
    pieces: list[tuple[float, float]] = []
    cur = 0.0
    for a, b in merged:
        if a > cur + tol:
            pieces.append((cur, a))
        if b > cur:
            cur = b
    if cur < length - tol:
        pieces.append((cur, length))

    # ---- 5. 按从 s=0 出发的切割顺序排列，并处理跨首尾的切割段 ----
    segments: list[list[tuple[float, float]]] = []

    if seam_gapped:
        # s=0 位于缺口中：切割段互不跨越首尾，按弧长升序即可
        for a, b in pieces:
            segments.append(
                _build_segment_points(coords, cum, a, b, wrap=False, tol=tol)
            )
    else:
        # s=0 位于切割中：首片段 (0, a1) 与尾片段 (bk, L) 属于同一物理段，
        # 跨越首尾连续切割，合并为一个开放折线并排在最前；
        # 若缺口仅单侧抵达首尾点（head xor tail），其中一个片段为空，
        # joined 自然退化为另一片段。
        first = pieces[0]
        last = pieces[-1]
        joined = _build_segment_points(
            coords, cum, last[0], first[1], wrap=True, tol=tol
        )
        segments.append(joined)
        for a, b in pieces[1:-1]:
            segments.append(
                _build_segment_points(coords, cum, a, b, wrap=False, tol=tol)
            )

    # 整圈覆盖的兜底检查（理论上前面已拦截）：没有任何长度合法的切割段
    segments = [seg for seg in segments if len(seg) >= 2]
    if not segments:
        raise _cover_error("留桥合并后补偿轨迹上无切割段")

    return segments
