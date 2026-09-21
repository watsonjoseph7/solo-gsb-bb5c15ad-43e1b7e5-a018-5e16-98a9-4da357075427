# 激光切割刀缝补偿 API

基于 **Python + FastAPI + Shapely (GEOS)** 的刀缝（kerf）补偿服务。

给定由**一条外轮廓 + 若干孔洞**组成的零件与刀缝宽度，服务计算闭合的**刀具中心轨迹**：

- 外轮廓向 **外** 偏移 `kerf_width / 2`；
- 孔洞向 **内** 偏移 `kerf_width / 2`（切出的孔尺寸与设计一致）；
- 输出保持**孔洞归属**（孔洞始终嵌在所属零件下），并对零件与轮廓**稳定排序**；
- 每条轮廓可选配置**微连接（留桥 tabs）**：在补偿轨迹上按归一化周长位置居中留出缺口，
  响应按切割顺序返回开放切割段；
- 任一原始轮廓**自交**，偏移导致轮廓**消失 / 分裂**，或留桥合并后**覆盖整圈**时，
  **整单拒绝**并定位到原始零件与轮廓，**绝不返回部分轨迹**。

---

## 单条命令启动（Docker Compose）

```bash
docker compose up --build -d
```

依赖（FastAPI、Shapely、uvicorn 及内置 GEOS）全部构建进镜像，无需在宿主机安装任何 Python 包。

- 默认访问地址：<http://localhost:8000>
- 健康检查：<http://localhost:8000/health>
- 接口文档（Swagger UI）：<http://localhost:8000/docs>
- OpenAPI JSON：<http://localhost:8000/openapi.json>

停止：

```bash
docker compose down
```

> 不用 Compose 时也可直接运行（等价）：
> `docker build -t laser-kerf-compensation . && docker run --rm -p 8000:8000 laser-kerf-compensation`

---

## 必要配置（均有默认值，零配置即可运行）

通过环境变量或 `.env` 文件配置（可复制 `.env.example` 为 `.env`）：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `KERF_API_PORT` | `8000` | 宿主机映射端口，容器内固定监听 8000 |
| `UVICORN_WORKERS` | `1` | uvicorn worker 进程数，CPU 密集可按核数调整 |

例：以 9000 端口、4 个 worker 启动：

```bash
KERF_API_PORT=9000 UVICORN_WORKERS=4 docker compose up --build -d
```

---

## API

### `GET /health`

健康检查，返回服务状态与 GEOS 版本：

```json
{ "status": "ok", "service": "laser-kerf-compensation", "geos_version": "3.12.1-CAPI-1.18.1" }
```

### `POST /api/v1/kerf-compensation`

**请求体**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `kerf_width` | number, `> 0` | 刀缝宽度，实际单侧偏移量为其一半 |
| `parts[]` | array, 至少 1 个 | 零件列表 |
| `parts[].id` | string? | 可选零件标识 |
| `parts[].outer` | object | 外轮廓 |
| `parts[].holes[]` | object[] | 孔洞列表（可为空） |
| 轮廓 `.id` | string? | 可选轮廓标识，出错时原样回传以便定位 |
| 轮廓 `.points[]` | array | 闭合点列，至少 3 个点；按顺序首尾相连，**不要**重复末点 |
| 轮廓 `.tabs[]` | object[]? | 可选微连接（留桥）列表；缺省 / 为空表示整条环连续切割 |
| 留桥 `.position` | number | 归一化周长位置，`0 ≤ position < 1`（沿切割方向，0 为补偿轨迹起点） |
| 留桥 `.width` | number, `> 0` | 留桥沿弧长方向的实际宽度（与坐标同单位） |
| 点 `.x` / `.y` | number | 有限数字（不接受 NaN / Infinity） |

示例：

```bash
curl -sS http://localhost:8000/api/v1/kerf-compensation \
  -H 'Content-Type: application/json' \
  --data @examples/request.json
```

**响应要点**

- `offset`：实际单侧偏移量（`kerf_width / 2`）；
- `parts[].outer`：外扩后的闭合刀具轨迹；
- `parts[].holes[]`：内缩后的孔洞轨迹，嵌套在所属零件下，保持归属；
- 每条轨迹含 `role`（`outer`/`hole`）、`orientation`（外轮廓 `CCW`、孔洞 `CW`）、
  `part_index`、`source_contour_index`（外轮廓为 `-1`，孔洞为其在原始 `holes` 中的下标）；
- 点列闭合但不重复末点；起点旋转到距原始轮廓首点最近的点，便于与输入对照；
- 每条轨迹含 `segments[]`：按切割顺序排列的**开放切割段**，每段为一个折线 `points`，
  段内保留环上全部原拐点并精确插入留桥边界点；未配置 `tabs` 时 `segments` 仅含一个
  与完整环一致的段。

### 微连接（留桥 tabs）

处理顺序：**先按既有规则生成补偿轨迹，再沿其弧长留空**。

- 补偿轨迹周长记为 `L`，切割方向即响应 `points` 的前进方向，起点 `points[0]` 对应弧长 0；
- 每个 tab 以弧长 `s = position · L` 为中心，居中留出宽度 `width` 的缺口
  `[s − width/2, s + width/2]`（边界落在直线边上时线性插值，位置精确）；
- 缺口**跨越首尾**（s=0）时按闭合环拆合并；互相**重叠或首尾相接**的缺口自动合并
  （含从两侧抵达首尾点的缺口）；
- 合并后缺口**覆盖整圈**（无任何切割段）时整单返回 `422`，错误码 `TAB_COVERS_RING`，
  `location` 定位到配置该轮廓的原始零件 / 轮廓；
- `segments[]` 为缺口补集：按从 `s=0` 出发的切割顺序排列；当 `s=0` 本身位于切割段中时，
  跨越首尾的那一物理段作为一个连续开放折线排在最前；段为开放折线（首尾点不重复），
  相邻段在留桥边界处分界、不共享端点；
- `points`、排序规则与绕向规范化不因 tabs 改变，旧客户端可忽略 `segments` 字段。

示意（10×10 方环，在右边中部留一个宽 2 的桥）：

```json
{
  "outer": {
    "points": [[0,0], [10,0], [10,10], [0,10]],
    "tabs": [{"position": 0.375, "width": 2.0}]
  }
}
```

周长 40、中心 s=15，缺口 `[14,16]`；`segments` 返回唯一开放段
`(10,6) → (10,10) → (0,10) → (0,0) → (10,0) → (10,4)`，原拐点全部保留。

### 排序规则（确定性输出）

- 零件：有 `id` 的按 `id` 字典序在前，无 `id` 的按原始请求顺序在后；`id` 相同则按原始下标；
- 零件内孔洞：同样按孔洞 `id` 字典序、再按原始下标。
- 无论如何排序，响应中的 `part_index` / `source_contour_index` 始终指向**原始请求下标**。

---

## 错误处理：整单拒绝 + 定位原轮廓

出现下列情况时返回 `HTTP 422`，响应只包含错误信息与定位，**不返回任何轨迹**：

| `error.code` | 触发条件 |
| --- | --- |
| `SELF_INTERSECTING_CONTOUR` | 原始轮廓自交（含自切、蝴蝶结等非简单环） |
| `CONTOUR_VANISHED` | 孔洞相对刀缝过小，内缩后轮廓消失（或退化为线/点） |
| `CONTOUR_SPLIT` | 偏移后轮廓分裂为多个闭合环（典型：哑铃形细腰孔洞内缩） |
| `TAB_COVERS_RING` | 留桥（合并后）覆盖补偿轨迹整圈，无任何切割段 |

`error.location` 给出原始位置：

```json
{
  "error": {
    "code": "CONTOUR_SPLIT",
    "message": "刀缝偏移后轮廓分裂为多个闭合环，整单拒绝: 偏移结果类型为 MultiPolygon，不是唯一闭合轮廓",
    "location": {
      "part_index": 0,
      "contour_index": 0,
      "part_id": "bracket",
      "contour_id": "slot"
    }
  }
}
```

- `part_index`：零件在请求 `parts[]` 中的下标；
- `contour_index`：外轮廓固定为 `-1`；孔洞为其在该零件 `holes[]` 中的下标；
- `part_id` / `contour_id`：请求中提供了则原样回传，否则为 `null`。

请求体本身的字段校验失败（如刀缝宽度 ≤ 0、点数不足、连续重复点、
`position` 越界（须 `0 ≤ position < 1`）、留桥 `width ≤ 0`、多余字段等）同样返回 `422`。

---

## 几何约定与说明

- 坐标单位任意但需自洽（`kerf_width` 与坐标同单位）；假定为数学坐标系（y 向上）。
- 轮廓按简单环（simple ring）处理，不要求输入绕向，服务统一规范化输出绕向。
- 尖角连接采用 GEOS 的 **mitre（斜接）** 方式，斜接上限为 2；圆弧分段精度 `quad_segs = 16`。
- 留桥作用在**补偿并规范化之后**的轨迹上：`position` 的弧长零点是响应 `points` 的起点
  （即距原轮廓首点最近的偏移点），方向与 `points` 前进方向一致；缺口合并与整圈判定
  使用相对周长缩放的浮点容差（`1e-9 · L`）。
- 服务不做孔与外轮廓的包含关系校验：调用方需保证孔洞确实位于所属零件外轮廓内部
  且孔洞之间互不重叠（与常规 CAM 输入约定一致）。

---

## 本地开发（不用 Docker）

需要 Python 3.11+：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt

uvicorn app.main:app --reload --port 8000
pytest
```

测试通过 FastAPI TestClient 覆盖：健康检查、外扩/内缩数值、孔洞归属、
稳定排序、自交/消失/分裂三类整单拒绝与定位、请求校验、
留桥（精确边界、拐点保留、跨首尾合并、重叠合并、覆盖整圈拒绝、切割顺序）等。

## 项目结构

```
app/
  main.py        # FastAPI 路由、异常处理、排序
  geometry.py    # Shapely 偏移核心与整单拒绝逻辑
  tabs.py        # 微连接（留桥）缺口合并与开放切割段生成
  schemas.py     # 请求/响应模型
  errors.py      # 错误码与带定位的补偿异常
tests/           # pytest 测试
examples/        # 请求示例
Dockerfile
docker-compose.yml
requirements.txt
```
