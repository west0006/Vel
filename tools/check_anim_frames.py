"""动画帧素材体检工具。

用途：重新生成帧序列后，用它检验是否满足《规格-重做动画帧序列》的一致性要求
（阈值定义见 `doc/dev/规格-重做动画帧序列.md` §2.2）。

用法::

    python -m tools.check_anim_frames              # 检查全部情绪
    python -m tools.check_anim_frames idle sleep   # 只检查指定情绪

输出每帧主题的包围盒指标与离散度，并给出 PASS/FAIL 判定。
"""

from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# 允许直接以脚本方式运行（python tools/check_anim_frames.py）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtCore import Qt                      # noqa: E402
from PyQt5.QtGui import QImage, QPainter, QPixmap  # noqa: E402
from PyQt5.QtSvg import QSvgRenderer             # noqa: E402
from PyQt5.QtWidgets import QApplication         # noqa: E402

from ui.floating_pet import FRAME_RENDER_SIZE, KNOWN_EMOTIONS  # noqa: E402

#: 一致性阈值（与规格文档 §2.2 保持一致）
THRESHOLDS = {
    "height_spread": 0.05,   # 主题高度极差 / 均值
    "area_spread": 0.15,     # 主题面积极差 / 均值
    "bottom_spread": 3.0,    # 底边极差（像素，预渲染坐标系）
    "center_spread": 5.0,    # 水平重心极差（像素）
}
#: 每情绪最少帧数（帧数不足会导致循环生硬）
MIN_FRAMES = 8


def render_frame(path: str) -> Optional[QPixmap]:
    """把单帧 SVG 渲染为位图（不归一化，用于测量原始素材）。"""
    try:
        pix = QPixmap(FRAME_RENDER_SIZE, FRAME_RENDER_SIZE)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing, False)
        QSvgRenderer(path).render(painter)
        painter.end()
        return pix
    except Exception as exc:                      # noqa: BLE001 - 体检工具需容错继续
        print(f"  [WARN] 渲染失败 {path}: {exc}")
        return None


def measure(pix: QPixmap, threshold: int = 30) -> Optional[Dict[str, float]]:
    """测量单帧主题的包围盒指标。"""
    try:
        import numpy as np

        img = pix.toImage().convertToFormat(QImage.Format_ARGB32)
        width, height = img.width(), img.height()
        ptr = img.constBits()
        ptr.setsize(img.byteCount())
        alpha = np.frombuffer(ptr, np.uint8).reshape(height, width, 4)[:, :, 3]
        mask = alpha > threshold
        if not mask.any():
            return None
        ys, xs = np.where(mask)
        w = float(xs.max() - xs.min() + 1)
        h = float(ys.max() - ys.min() + 1)
        return {
            "width": w,
            "height": h,
            "area": w * h,
            "bottom": float(ys.max()),
            "center_x": float((xs.min() + xs.max()) / 2.0),
        }
    except Exception:                              # noqa: BLE001
        return None


def check_emotion(folder: str) -> bool:
    """检查单个情绪目录，返回是否全部达标。"""
    name = os.path.basename(folder)
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith((".svg", ".png")))
    if not files:
        print(f"{name:11s} [FAIL] 目录为空")
        return False

    metrics: List[Dict[str, float]] = []
    for fname in files:
        pix = render_frame(os.path.join(folder, fname))
        if pix is None:
            continue
        item = measure(pix)
        if item:
            metrics.append(item)
    if not metrics:
        print(f"{name:11s} [FAIL] 无有效帧")
        return False

    def spread(key: str) -> float:
        values = [m[key] for m in metrics]
        return max(values) - min(values)

    def ratio(key: str) -> float:
        values = [m[key] for m in metrics]
        mean = sum(values) / len(values)
        return spread(key) / mean if mean else 0.0

    height_r = ratio("height")
    area_r = ratio("area")
    bottom_s = spread("bottom")
    center_s = spread("center_x")

    problems = []
    if len(files) < MIN_FRAMES:
        problems.append(f"帧数 {len(files)} < {MIN_FRAMES}")
    if height_r > THRESHOLDS["height_spread"]:
        problems.append(f"高度离散度 {height_r:.1%} > {THRESHOLDS['height_spread']:.0%}")
    if area_r > THRESHOLDS["area_spread"]:
        problems.append(f"面积离散度 {area_r:.1%} > {THRESHOLDS['area_spread']:.0%}")
    if bottom_s > THRESHOLDS["bottom_spread"]:
        problems.append(f"底边跳动 {bottom_s:.0f}px > {THRESHOLDS['bottom_spread']:.0f}px")
    if center_s > THRESHOLDS["center_spread"]:
        problems.append(f"重心跳动 {center_s:.0f}px > {THRESHOLDS['center_spread']:.0f}px")

    status = "PASS" if not problems else "FAIL"
    print(f"{name:11s} [{status}] {len(files):2d} 帧  "
          f"高离散 {height_r:5.1%}  面积离散 {area_r:5.1%}  "
          f"底边极差 {bottom_s:5.1f}px  重心极差 {center_s:5.1f}px")
    for item in problems:
        print(f"{'':11s}        └─ {item}")
    return not problems


def main(argv: List[str]) -> int:
    """入口：检查指定（或全部）情绪目录。"""
    # Windows 控制台默认 GBK，中文输出可能抛 UnicodeEncodeError；此处强制 UTF-8 并容错
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:                                    # noqa: BLE001
        pass

    QApplication.instance() or QApplication([])

    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "ui", "resources", "animations", "pet_svg")
    targets = argv[1:] or list(KNOWN_EMOTIONS)
    if not os.path.isdir(base):
        print(f"[ERROR] 素材目录不存在: {base}")
        return 2

    print(f"素材目录: {base}")
    print(f"阈值: 高度离散 ≤ {THRESHOLDS['height_spread']:.0%} · "
          f"面积离散 ≤ {THRESHOLDS['area_spread']:.0%} · "
          f"底边极差 ≤ {THRESHOLDS['bottom_spread']:.0f}px · "
          f"重心极差 ≤ {THRESHOLDS['center_spread']:.0f}px · "
          f"帧数 ≥ {MIN_FRAMES}\n")

    passed = 0
    checked = 0
    for name in targets:
        folder = os.path.join(base, name)
        if not os.path.isdir(folder):
            print(f"{name:11s} [SKIP] 目录不存在")
            continue
        checked += 1
        if check_emotion(folder):
            passed += 1

    print(f"\n结果: {passed}/{checked} 个情绪达标")
    return 0 if passed == checked else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
