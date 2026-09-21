"""请求 / 响应 Pydantic 模型。"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Point(BaseModel):
    x: float
    y: float

    @field_validator("x", "y")
    @classmethod
    def _finite(cls, v: float) -> float:
        # NaN / Infinity 不是合法 JSON 数字，几何上也无意义
        if not math.isfinite(v):
            raise ValueError("坐标必须为有限数字")
        return v


class Tab(BaseModel):
    """微连接（留桥）：在轮廓轨迹上居中留出一段不切割的缺口。

    - ``position``：补偿后轨迹上的归一化周长位置（沿切割方向，0 为轨迹起点，
      不接受 1；区间跨越首尾时按闭合环绕回处理）；
    - ``width``：留桥沿弧长方向的实际宽度（与坐标同单位，必须大于 0）。
    """

    model_config = ConfigDict(extra="forbid")

    position: float = Field(ge=0.0, lt=1.0, description="归一化周长位置，0 ≤ position < 1")
    width: float = Field(gt=0.0, description="留桥实际宽度（弧长方向，与坐标同单位）")

    @field_validator("position", "width")
    @classmethod
    def _finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("留桥参数必须为有限数字")
        return v


class Contour(BaseModel):
    """一条闭合轮廓（外轮廓或孔洞）。

    点按顺序首尾相连，服务端自动闭合（首尾重复与不重复均可）。
    至少需要 3 个点；首尾点以外的连续重复点会被拒绝。
    ``tabs`` 可选，声明该轮廓补偿后轨迹上的微连接（留桥）。
    """

    model_config = ConfigDict(extra="forbid")

    id: str | None = Field(default=None, description="可选轮廓标识，便于定位")
    points: list[Point] = Field(min_length=3)
    tabs: list[Tab] = Field(
        default_factory=list,
        description="微连接（留桥）列表；为空时整条闭合环作为唯一开放段返回",
    )

    @field_validator("points")
    @classmethod
    def _no_consecutive_duplicates(cls, points: list[Point]) -> list[Point]:
        for i in range(1, len(points)):
            if points[i].x == points[i - 1].x and points[i].y == points[i - 1].y:
                raise ValueError("轮廓存在连续重复点")
        # 首尾重复闭合点也视为连续重复（末点与首点）
        if len(points) >= 2:
            first, last = points[0], points[-1]
            if first.x == last.x and first.y == last.y:
                raise ValueError("轮廓首尾点重复，请勿显式重复闭合点")
        return points


class Part(BaseModel):
    """一个零件：一条外轮廓 + 若干孔洞。"""

    model_config = ConfigDict(extra="forbid")

    id: str | None = Field(default=None, description="可选零件标识")
    outer: Contour
    holes: list[Contour] = Field(default_factory=list)


class CompensationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kerf_width: float = Field(
        ...,
        gt=0,
        description="刀缝宽度（与坐标同单位），实际偏移量为其一半",
    )
    parts: list[Part] = Field(min_length=1)


class SegmentOut(BaseModel):
    """一段开放切割轨迹（折线）。

    段内按切割顺序排列：既包含轨迹上的全部原拐点，也精确插入留桥边界点；
    点列开放（首尾不重复），相邻段在留桥边界处分界、不共享端点。
    """

    points: list[Point] = Field(min_length=2)


class RingOut(BaseModel):
    """一条闭合刀具中心轨迹。"""

    id: str | None = None
    role: Literal["outer", "hole"]
    # 所属零件下标（原始请求下标），保持孔洞归属
    part_index: int
    # 该轮廓在所属零件原始请求中的下标：外轮廓恒为 -1；孔洞为 holes 下标
    source_contour_index: int
    points: list[Point]
    orientation: Literal["CCW", "CW"]
    area: float = Field(description="轨迹包围面积（无符号，便于客户端校验）")
    segments: list[SegmentOut] = Field(
        description=(
            "按切割顺序排列的开放切割段；配置 tabs 时为去除留桥后的各段，"
            "未配置 tabs 时仅含一个与完整环一致的段"
        )
    )


class PartOut(BaseModel):
    id: str | None = None
    part_index: int
    outer: RingOut
    holes: list[RingOut]


class CompensationResponse(BaseModel):
    kerf_width: float
    offset: float = Field(description="实际单侧偏移量 = kerf_width / 2")
    parts: list[PartOut]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    geos_version: str
