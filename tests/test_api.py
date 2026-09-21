"""端到端 API 测试（通过 FastAPI TestClient）。"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.geometry import signed_area
from app.main import app

client = TestClient(app)


def square(cx: float = 5.0, cy: float = 5.0, half: float = 5.0) -> list[dict]:
    return [
        {"x": cx - half, "y": cy - half},
        {"x": cx + half, "y": cy - half},
        {"x": cx + half, "y": cy + half},
        {"x": cx - half, "y": cy + half},
    ]


# ---------- 健康检查 ----------


def test_health() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "laser-kerf-compensation"
    assert "geos_version" in body


# ---------- 基本补偿 ----------


def test_basic_outer_and_hole_offset() -> None:
    # 外轮廓 10x10，孔洞 4x4；刀缝 2 -> 单侧偏移 1
    req = {
        "kerf_width": 2.0,
        "parts": [
            {
                "id": "p1",
                "outer": {"id": "o1", "points": square()},
                "holes": [{"id": "h1", "points": square(5, 5, 2)}],
            }
        ],
    }
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["offset"] == 1.0

    part = body["parts"][0]
    outer = part["outer"]
    hole = part["holes"][0]

    # 外扩 1 -> 12x12；孔洞内缩 1 -> 2x2
    assert outer["area"] == pytest.approx(144.0, abs=1e-6)
    assert hole["area"] == pytest.approx(4.0, abs=1e-6)

    # 绕向规范化：外 CCW，孔 CW
    assert outer["orientation"] == "CCW"
    assert hole["orientation"] == "CW"

    # 返回的是闭合轨迹点列（不重复末点，>=4 点）
    assert len(outer["points"]) == 4
    assert outer["points"][0] != outer["points"][-1]

    # 孔洞归属保持
    assert hole["part_index"] == 0
    assert hole["source_contour_index"] == 0
    assert outer["source_contour_index"] == -1


def test_holes_stay_inside_their_part() -> None:
    req = {
        "kerf_width": 1.0,
        "parts": [
            {
                "id": "A",
                "outer": {"points": square(0, 0, 10)},
                "holes": [
                    {"id": "h-a", "points": [
                        {"x": -8, "y": -8}, {"x": -4, "y": -8},
                        {"x": -4, "y": -4}, {"x": -8, "y": -4},
                    ]},
                ],
            },
            {
                "id": "B",
                "outer": {"points": square(30, 30, 10)},
                "holes": [
                    {"id": "h-b", "points": [
                        {"x": 22, "y": 22}, {"x": 26, "y": 22},
                        {"x": 26, "y": 26}, {"x": 22, "y": 26},
                    ]},
                ],
            },
        ],
    }
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 200, r.text
    parts = r.json()["parts"]
    assert len(parts) == 2
    assert parts[0]["id"] == "A"
    assert parts[0]["holes"][0]["id"] == "h-a"
    assert parts[1]["holes"][0]["id"] == "h-b"


# ---------- 排序 ----------


def test_parts_and_holes_sorted_stably() -> None:
    req = {
        "kerf_width": 1.0,
        "parts": [
            {
                "id": "zeta",
                "outer": {"points": square(0, 0, 10)},
                "holes": [
                    {"id": "z-hole", "points": square(0, 0, 2)},
                    {"id": "a-hole", "points": square(3, 0, 1.5)},
                ],
            },
            {
                "id": "alpha",
                "outer": {"points": square(30, 30, 10)},
                "holes": [],
            },
            {
                # 无 id 的零件按原始下标排到有 id 之后
                "outer": {"points": square(60, 60, 10)},
                "holes": [],
            },
        ],
    }
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 200, r.text
    parts = r.json()["parts"]
    assert [p["id"] for p in parts] == ["alpha", "zeta", None]
    # 原始下标不被排序破坏
    assert [p["part_index"] for p in parts] == [1, 0, 2]
    assert [h["id"] for h in parts[1]["holes"]] == ["a-hole", "z-hole"]


# ---------- 整单拒绝 ----------


def test_self_intersecting_outer_is_rejected_and_located() -> None:
    # 蝴蝶结
    bowtie = [
        {"x": 0, "y": 0}, {"x": 4, "y": 4},
        {"x": 4, "y": 0}, {"x": 0, "y": 4},
    ]
    req = {
        "kerf_width": 1.0,
        "parts": [
            {"id": "good", "outer": {"points": square(30, 30, 10)}, "holes": []},
            {"id": "bad", "outer": {"id": "bow", "points": bowtie}, "holes": []},
        ],
    }
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "SELF_INTERSECTING_CONTOUR"
    loc = err["location"]
    assert loc["part_index"] == 1
    assert loc["contour_index"] == -1
    assert loc["part_id"] == "bad"
    assert loc["contour_id"] == "bow"


def test_self_intersecting_hole_is_located_by_hole_index() -> None:
    bowtie = [
        {"x": 0, "y": 0}, {"x": 2, "y": 2},
        {"x": 2, "y": 0}, {"x": 0, "y": 2},
    ]
    req = {
        "kerf_width": 1.0,
        "parts": [
            {
                "id": "p",
                "outer": {"points": square()},
                "holes": [
                    {"id": "ok-hole", "points": square(5, 5, 1)},
                    {"id": "bow-hole", "points": bowtie},
                ],
            }
        ],
    }
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 422
    loc = r.json()["error"]["location"]
    assert loc["part_index"] == 0
    assert loc["contour_index"] == 1
    assert loc["contour_id"] == "bow-hole"


def test_hole_vanishes_rejects_whole_order() -> None:
    # 1x1 孔洞内缩 0.6*2? -> kerf=1.2 offset=.6，对边距 < 1.2 -> 消失
    req = {
        "kerf_width": 1.2,
        "parts": [
            {
                "id": "p1",
                "outer": {"points": square()},
                "holes": [{"id": "tiny", "points": square(5, 5, 0.5)}],
            },
            {"id": "p2", "outer": {"points": square(30, 30, 10)}, "holes": []},
        ],
    }
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "CONTOUR_VANISHED"
    assert err["location"] == {
        "part_index": 0,
        "contour_index": 0,
        "part_id": "p1",
        "contour_id": "tiny",
    }


def test_narrow_hole_degenerates_and_is_rejected_as_vanished() -> None:
    # 10x2 条带孔洞，内缩 1 后退化为线（空面）-> CONTOUR_VANISHED
    strip = [
        {"x": 2, "y": 8}, {"x": 12, "y": 8},
        {"x": 12, "y": 10}, {"x": 2, "y": 10},
    ]
    req = {
        "kerf_width": 2.0,
        "parts": [
            {
                "id": "p",
                "outer": {"points": square(7, 5, 20)},
                "holes": [{"id": "strip", "points": strip}],
            }
        ],
    }
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "CONTOUR_VANISHED"
    assert err["location"]["contour_id"] == "strip"


def test_hole_splits_rejects_whole_order() -> None:    # 哑铃形孔洞：两个 4x4 凸耳，2 宽通道；内缩 1.1 必然分裂
    dumbbell = [
        (0, 0), (4, 0), (4, 1), (6, 1), (6, 0), (10, 0),
        (10, 4), (6, 4), (6, 3), (4, 3), (4, 4), (0, 4),
    ]
    req = {
        "kerf_width": 2.2,
        "parts": [
            {
                "id": "p",
                "outer": {"points": square(10, 5, 20)},
                "holes": [{"id": "dumb", "points": [{"x": x, "y": y} for x, y in dumbbell]}],
            }
        ],
    }
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "CONTOUR_SPLIT"
    assert err["location"]["contour_index"] == 0
    assert err["location"]["contour_id"] == "dumb"


# ---------- 请求校验 ----------


def test_invalid_kerf_width() -> None:
    req = {"kerf_width": 0, "parts": [{"outer": {"points": square()}}]}
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 422


def test_too_few_points() -> None:
    req = {
        "kerf_width": 1.0,
        "parts": [{"outer": {"points": [{"x": 0, "y": 0}, {"x": 1, "y": 0}]}}],
    }
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 422


def test_consecutive_duplicate_points() -> None:
    pts = square()
    pts[1] = pts[0]
    req = {"kerf_width": 1.0, "parts": [{"outer": {"points": pts}}]}
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 422


def test_implicitly_closed_input_is_accepted() -> None:
    # 不重复末点即可（square() 即如此）
    req = {"kerf_width": 1.0, "parts": [{"outer": {"points": square()}}]}
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 200


def test_extra_field_rejected() -> None:
    req = {
        "kerf_width": 1.0,
        "parts": [{"outer": {"points": square()}, "unexpected": 1}],
    }
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 422


# ---------- 输出闭合性与几何性质 ----------


def test_output_rings_are_simple_closed() -> None:
    from shapely.geometry import LinearRing

    req = {
        "kerf_width": 1.0,
        "parts": [
            {
                "outer": {
                    "points": [
                        {"x": 0, "y": 0}, {"x": 10, "y": 0},
                        {"x": 10, "y": 8}, {"x": 6, "y": 8},
                        {"x": 6, "y": 4}, {"x": 3, "y": 4},
                        {"x": 3, "y": 10}, {"x": 0, "y": 10},
                    ]
                },
                "holes": [{"points": square(2, 2, 1)}],
            }
        ],
    }
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 200, r.text
    part = r.json()["parts"][0]
    for ring_out in [part["outer"], *part["holes"]]:
        coords = [(p["x"], p["y"]) for p in ring_out["points"]]
        ring = LinearRing(coords)  # 不抛异常即说明可闭合
        assert ring.is_valid
        # 面积符号与声明绕向一致
        area = signed_area(coords)
        if ring_out["role"] == "outer":
            assert area > 0
        else:
            assert area < 0


def test_openapi_available() -> None:
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert "/health" in r.json()["paths"]


# ---------- 微连接（留桥） ----------


def test_segments_without_tabs_contain_single_full_ring() -> None:
    req = {
        "kerf_width": 2.0,
        "parts": [
            {
                "id": "p1",
                "outer": {"id": "o1", "points": square()},
                "holes": [{"id": "h1", "points": square(5, 5, 2)}],
            }
        ],
    }
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 200, r.text
    for ring in [r.json()["parts"][0]["outer"], *r.json()["parts"][0]["holes"]]:
        assert len(ring["segments"]) == 1
        # 未配置 tabs：唯一段即完整环，与 points 完全一致
        assert ring["segments"][0]["points"] == ring["points"]
        assert len(ring["segments"][0]["points"]) >= 2


def test_single_tab_cuts_one_open_segment_with_exact_boundaries() -> None:
    # 外轮廓 10x10（居中原点），刀缝 2 -> 外扩成 12x12，周长 48：
    # 顶点弧长 s=0:(-6,-6) 12:(6,-6) 24:(6,6) 36:(-6,6)
    # 在 position=0.25（s=12，顶点）留宽 4 的桥 -> 缺口 [10,14]
    req = {
        "kerf_width": 2.0,
        "parts": [
            {
                "outer": {
                    "points": square(0, 0, 5),
                    "tabs": [{"position": 0.25, "width": 4.0}],
                },
                "holes": [],
            }
        ],
    }
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 200, r.text
    outer = r.json()["parts"][0]["outer"]
    points = {(p["x"], p["y"]) for p in outer["points"]}
    assert points == {(-6.0, -6.0), (6.0, -6.0), (6.0, 6.0), (-6.0, 6.0)}

    # 只有一个开放段，从缺口终点 s=14 跨越首尾切到缺口起点 s=10
    assert len(outer["segments"]) == 1
    seg = outer["segments"][0]["points"]
    assert seg[0] == {"x": 6.0, "y": -4.0}   # s=14 精确边界
    assert seg[-1] == {"x": 4.0, "y": -6.0}  # s=10 精确边界
    # 段内保留未被留桥覆盖的全部原拐点
    for corner in [(6.0, 6.0), (-6.0, 6.0), (-6.0, -6.0)]:
        assert {"x": corner[0], "y": corner[1]} in seg
    # 缺口中的顶点 (6,-6) 被扣除
    assert {"x": 6.0, "y": -6.0} not in seg
    # 开放段：首尾点不同
    assert seg[0] != seg[-1]


def test_tab_boundary_on_vertex_keeps_single_vertex() -> None:
    # 缺口 [12,24]（宽 12，中心 s=18, p=.375），两端边界恰好都是顶点，
    # 不得产生重复点
    req = {
        "kerf_width": 2.0,
        "parts": [
            {
                "outer": {
                    "points": square(0, 0, 5),
                    "tabs": [{"position": 0.375, "width": 12.0}],
                },
                "holes": [],
            }
        ],
    }
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 200, r.text
    seg = r.json()["parts"][0]["outer"]["segments"][0]["points"]
    assert seg[0] == {"x": 6.0, "y": 6.0}    # s=24 顶点
    assert seg[-1] == {"x": 6.0, "y": -6.0}  # s=12 顶点
    # 不在缺口处的两个拐点保留
    assert {"x": -6.0, "y": 6.0} in seg
    assert {"x": -6.0, "y": -6.0} in seg
    # 无连续重复点
    for a, b in zip(seg, seg[1:]):
        assert a != b


def test_tab_on_hole_is_open_and_keeps_vertices() -> None:
    # 孔洞 4x4 内缩 1 -> 2x2（CW），周长 8；
    # s=0:(4,4) 2:(4,6) 4:(6,6) 6:(6,4)；p=.5 w=2 -> 缺口 [3,5]
    req = {
        "kerf_width": 2.0,
        "parts": [
            {
                "id": "p",
                "outer": {"points": square()},
                "holes": [
                    {
                        "id": "h",
                        "points": square(5, 5, 2),
                        "tabs": [{"position": 0.5, "width": 2.0}],
                    }
                ],
            }
        ],
    }
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 200, r.text
    hole = r.json()["parts"][0]["holes"][0]
    assert len(hole["segments"]) == 1
    seg = hole["segments"][0]["points"]
    # 跨越首尾的唯一段：s=5 (6,5) -> ... -> s=3 (5,6)
    assert seg[0] == {"x": 6.0, "y": 5.0}
    assert seg[-1] == {"x": 5.0, "y": 6.0}
    # 三个不在缺口中的顶点 + 两个边界点 = 5
    assert len(seg) == 5
    for corner in [(6.0, 4.0), (4.0, 4.0), (4.0, 6.0)]:
        assert {"x": corner[0], "y": corner[1]} in seg


def test_wraparound_gaps_merge_into_one_tab() -> None:
    # 周长 48：p=1/24(s=2,w=8) -> [-2,6]；p=23/24(s=46,w=8) -> [42,50]
    # 两段缺口跨越首尾，按闭合环合并为 [42,48]∪[0,6]
    req = {
        "kerf_width": 2.0,
        "parts": [
            {
                "outer": {
                    "points": square(0, 0, 5),
                    "tabs": [
                        {"position": 1 / 24, "width": 8.0},
                        {"position": 23 / 24, "width": 8.0},
                    ],
                },
                "holes": [],
            }
        ],
    }
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 200, r.text
    segs = r.json()["parts"][0]["outer"]["segments"]
    # 唯一切割段从 s=6 切到 s=42
    assert len(segs) == 1
    seg = segs[0]["points"]
    assert seg[0] == {"x": 0.0, "y": -6.0}   # s=6
    assert seg[-1] == {"x": -6.0, "y": 0.0}  # s=42
    # s=12/24/36 三个顶点保留；s=0 顶点位于合并缺口中被扣除
    for corner in [(6.0, -6.0), (6.0, 6.0), (-6.0, 6.0)]:
        assert {"x": corner[0], "y": corner[1]} in seg
    assert {"x": -6.0, "y": -6.0} not in seg


def test_overlapping_interior_tabs_merge() -> None:
    # 周长 48：缺口 [2,6] 与 [3.2,7.2] 重叠 -> 合并 [2,7.2]
    req = {
        "kerf_width": 2.0,
        "parts": [
            {
                "outer": {
                    "points": square(0, 0, 5),
                    "tabs": [
                        {"position": 4 / 48, "width": 4.0},
                        {"position": 5.2 / 48, "width": 4.0},
                    ],
                },
                "holes": [],
            }
        ],
    }
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 200, r.text
    segs = r.json()["parts"][0]["outer"]["segments"]
    assert len(segs) == 1
    seg = segs[0]["points"]
    # 首尾不落在缺口：跨首尾的物理段排在最前，s=7.2 -> s=2
    assert seg[0] == {"x": pytest.approx(1.2, abs=1e-9), "y": -6.0}
    assert seg[-1] == {"x": -4.0, "y": -6.0}


def test_two_interior_tabs_yield_two_segments_in_cutting_order() -> None:
    # 周长 48：缺口 [3,7]（p=5/48,w=4）与 [27,31]（p=29/48,w=4）
    req = {
        "kerf_width": 2.0,
        "parts": [
            {
                "outer": {
                    "points": square(0, 0, 5),
                    "tabs": [
                        {"position": 5 / 48, "width": 4.0},
                        {"position": 29 / 48, "width": 4.0},
                    ],
                },
                "holes": [],
            }
        ],
    }
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 200, r.text
    segs = r.json()["parts"][0]["outer"]["segments"]
    # s=0 位于切割中：跨首尾段 (31 -> ... -> 7) 在前，中间段 (7 -> ... -> 27) 在后
    assert len(segs) == 2
    first, second = segs[0]["points"], segs[1]["points"]
    assert first[0] == {"x": -1.0, "y": 6.0}  # s=31
    assert first[-1] == {"x": -3.0, "y": -6.0}  # s=3
    assert second[0] == {"x": 1.0, "y": -6.0}  # s=7
    assert second[-1] == {"x": 3.0, "y": 6.0}  # s=27
    # 中间段保留 s=12、s=24 两个拐点
    assert {"x": 6.0, "y": -6.0} in second
    assert {"x": 6.0, "y": 6.0} in second


def test_tabs_cover_whole_ring_rejects_and_locates_contour() -> None:
    # 外轮廓 10x10，补偿后周长 48：一个宽 48 的桥覆盖整圈
    req = {
        "kerf_width": 2.0,
        "parts": [
            {
                "id": "good",
                "outer": {"points": square(30, 30, 10)},
                "holes": [],
            },
            {
                "id": "bad",
                "outer": {
                    "id": "outer-bad",
                    "points": square(0, 0, 5),
                    "tabs": [{"position": 0.3, "width": 48.0}],
                },
                "holes": [],
            },
        ],
    }
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "TAB_COVERS_RING"
    assert err["location"] == {
        "part_index": 1,
        "contour_index": -1,
        "part_id": "bad",
        "contour_id": "outer-bad",
    }


def test_tabs_together_cover_whole_ring_rejects() -> None:
    # 两个留桥合起来覆盖整圈：周长 48，各宽 24，中心 s=12 / s=36
    req = {
        "kerf_width": 2.0,
        "parts": [
            {
                "id": "p",
                "outer": {
                    "points": square(0, 0, 5),
                    "tabs": [
                        {"position": 0.25, "width": 24.0},
                        {"position": 0.75, "width": 24.0},
                    ],
                },
                "holes": [],
            }
        ],
    }
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "TAB_COVERS_RING"


def test_hole_tab_full_cover_is_located_by_hole_index() -> None:
    req = {
        "kerf_width": 2.0,
        "parts": [
            {
                "id": "p",
                "outer": {"points": square()},
                "holes": [
                    {"id": "ok-hole", "points": square(5, 5, 1.8)},
                    {
                        "id": "big-tab-hole",
                        "points": square(5, 5, 2),
                        "tabs": [{"position": 0.1, "width": 8.0}],  # 补偿后周长 8
                    },
                ],
            }
        ],
    }
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "TAB_COVERS_RING"
    assert err["location"]["contour_index"] == 1
    assert err["location"]["contour_id"] == "big-tab-hole"


def test_tabs_meeting_at_seam_merge_as_closed_ring() -> None:
    # 周长 48：缺口恰止于首尾两侧 —— 尾缺口 [38,48]（p=43/48,w=10），
    # 首缺口 [0,10]（p=5/48,w=10）：在闭合环上它们在首尾点相接，合并为一个留桥
    req = {
        "kerf_width": 2.0,
        "parts": [
            {
                "outer": {
                    "points": square(0, 0, 5),
                    "tabs": [
                        {"position": 43 / 48, "width": 10.0},
                        {"position": 5 / 48, "width": 10.0},
                    ],
                },
                "holes": [],
            }
        ],
    }
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 200, r.text
    segs = r.json()["parts"][0]["outer"]["segments"]
    # 合并后 [38,48]∪[0,10]：唯一切割段 s=10 -> s=38
    assert len(segs) == 1
    seg = segs[0]["points"]
    assert seg[0] == {"x": 4.0, "y": -6.0}   # s=10
    assert seg[-1] == {"x": -6.0, "y": 4.0}  # s=38


def test_adjacent_touching_tabs_merge() -> None:
    # 周长 48：[2,6] 与 [6,10] 在 s=6 处恰好相接 -> 合并
    req = {
        "kerf_width": 2.0,
        "parts": [
            {
                "outer": {
                    "points": square(0, 0, 5),
                    "tabs": [
                        {"position": 4 / 48, "width": 4.0},
                        {"position": 8 / 48, "width": 4.0},
                    ],
                },
                "holes": [],
            }
        ],
    }
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 200, r.text
    segs = r.json()["parts"][0]["outer"]["segments"]
    assert len(segs) == 1  # 合并为一个缺口 -> 一条跨首尾切割段
    seg = segs[0]["points"]
    assert seg[-1] == {"x": -4.0, "y": -6.0}  # s=2
    assert seg[0] == {"x": 4.0, "y": -6.0}    # s=10


def test_wrap_segment_preserves_traversal_order_with_many_vertices() -> None:
    # 非方形凸八边形，两个内部缺口都不接触首尾：跨首尾段必须严格按切割方向
    # （沿环前进）排列，不能按顶点下标打乱顺序
    import math

    pts = []
    for i in range(8):
        a = 2 * math.pi * i / 8
        pts.append({"x": round(10 * math.cos(a), 6), "y": round(10 * math.sin(a), 6)})
    req = {
        "kerf_width": 0.001,
        "parts": [
            {
                "outer": {
                    "points": pts,
                    "tabs": [
                        {"position": 0.3, "width": 1.0},
                        {"position": 0.7, "width": 1.0},
                    ],
                },
                "holes": [],
            }
        ],
    }
    r = client.post("/api/v1/kerf-compensation", json=req)
    assert r.status_code == 200, r.text
    ring = r.json()["parts"][0]["outer"]
    ring_pts = ring["points"]
    n = len(ring_pts)

    def index_of(p):
        for i, q in enumerate(ring_pts):
            if abs(q["x"] - p["x"]) < 1e-6 and abs(q["y"] - p["y"]) < 1e-6:
                return i
        return -1

    # 三个缺口补集片段（含跨首尾段）；若极尖角导致弧长微调而合并，至少有跨首尾段
    assert len(ring["segments"]) >= 2
    wrap_seg = ring["segments"][0]["points"]
    # 跨首尾段中出现的原拐点必须构成两个连续的下标块（按下标线性相邻，
    # 不在接缝处 7->0 视作相邻）：高索引块在前，低索引块在后
    verts = [index_of(p) for p in wrap_seg if index_of(p) >= 0]
    blocks, cur = [], [verts[0]]
    for a, b in zip(verts, verts[1:]):
        if b == a + 1:
            cur.append(b)
        else:
            blocks.append(cur)
            cur = [b]
    blocks.append(cur)
    assert len(blocks) == 2
    assert blocks[0][0] > blocks[1][-1]  # 先沿高索引走到接缝，再从低索引继续


def test_tab_field_validation() -> None:
    base = {
        "kerf_width": 1.0,
        "parts": [{"outer": {"points": square()}}],
    }

    bad_position = json.loads(json.dumps(base))
    bad_position["parts"][0]["outer"]["tabs"] = [
        {"position": 1.0, "width": 1.0}
    ]
    r = client.post("/api/v1/kerf-compensation", json=bad_position)
    assert r.status_code == 422

    negative_position = json.loads(json.dumps(base))
    negative_position["parts"][0]["outer"]["tabs"] = [
        {"position": -0.1, "width": 1.0}
    ]
    r = client.post("/api/v1/kerf-compensation", json=negative_position)
    assert r.status_code == 422

    bad_width = json.loads(json.dumps(base))
    bad_width["parts"][0]["outer"]["tabs"] = [{"position": 0.5, "width": 0.0}]
    r = client.post("/api/v1/kerf-compensation", json=bad_width)
    assert r.status_code == 422

    extra = json.loads(json.dumps(base))
    extra["parts"][0]["outer"]["tabs"] = [
        {"position": 0.5, "width": 1.0, "x": 1}
    ]
    r = client.post("/api/v1/kerf-compensation", json=extra)
    assert r.status_code == 422
