"""从**单张静态图**生成桌宠帧序列（解决 AI 逐帧生图的帧间不一致）。

背景
----
现有 `pet_svg/` 素材是 AI **逐帧独立生成**的：诊断显示相邻帧平移对齐后内容差异仍
残留 75~98%，尺寸跳变最高近 2 倍、底边跳动 36px —— 这是"动画效果差"的根因，
代码侧归一化只能缓解。

本工具改用另一种思路（借鉴 `zhizhiji-shimeji/gen_frames.py` 的做法）：
**同一张图 + 小幅程序化变换** 生成每一帧，因此帧间差异天然为 0。

用法::

    python -m tools.gen_pet_frames                      # 用默认源图生成全部情绪
    python -m tools.gen_pet_frames --source 某图.png    # 指定源图
    python -m tools.gen_pet_frames --emotions idle happy

输出
----
`ui/resources/animations/pet_png/<情绪>/<情绪>_NN.png`，画布 512×512（与
`ui/floating_pet.py` 的 `FRAME_RENDER_SIZE` 一致），主体底部对齐到画布
`FRAME_BOTTOM_RATIO`（0.96）位置 —— 与绘制逻辑 `compute_frame_rect` 的假设对齐。

若源图背景是纯色或规则棋盘格，会自动从四角泛洪填充抠除（猫身内部的浅色区域
被轮廓包围，不会被误删）。
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import deque
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image

# 与 ui/floating_pet.py 保持一致的画布与对齐参数
CANVAS = 512
BOTTOM_RATIO = 0.96
SUBJECT_HEIGHT = int(CANVAS * 0.78)      # 主体高度
# 说明：从 0.86 降到 0.78 是为 squash & stretch 留出**向上**空间 ——
# 起跳帧同时要「拉长 1.10 倍」+「上移 34px」，主体 440 时会超出画布顶部被裁切。
# 512 画布、底部基线 491 前提下，主体 400 时最极端帧顶部约 25px，安全。

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SOURCE = os.path.join(PROJECT_ROOT, "ui", "resources", "animations", "cat_1.png")
OUT_ROOT = os.path.join(PROJECT_ROOT, "ui", "resources", "animations", "pet_png")

#: 情绪 → 帧变换规则。
#: dy: 垂直偏移（负=上移，模拟跳跃/呼吸）；scale_y: 纵向缩放（1.0 不变）；
#: angle: 旋转角度（度）；每项对应一帧。
EMOTION_RULES: Dict[str, List[Dict[str, float]]] = {
    # 平静：呼吸起伏 + 极轻微纵向形变（吸气时略高）
    "idle": [{"dy": 0}, {"dy": -3, "scale_y": 1.01}, {"dy": -6, "scale_y": 1.02},
             {"dy": -3, "scale_y": 1.01}],
    # 刚醒：先缩一下再舒展拉长（伸懒腰的挤压拉伸）
    "wake": [{"dy": 0, "scale_y": 0.95}, {"dy": -8, "scale_y": 1.06},
             {"dy": -15, "scale_y": 1.10}, {"dy": -5, "scale_y": 1.03}],
    # 思考：歪头
    "thinking": [{"dy": 0}, {"dy": -3, "angle": -6}, {"dy": -5, "angle": -11}],
    # 困倦：极慢极小的呼吸
    "sleep": [{"dy": 0, "scale_y": 0.99}, {"dy": -3, "scale_y": 1.01},
              {"dy": -6, "scale_y": 1.02}, {"dy": -3, "scale_y": 1.01}],
    # 低落：整体被压矮 + 低头
    "sad": [{"dy": 0, "scale_y": 0.97},
            {"dy": 5, "scale_y": 0.96, "angle": 4},
            {"dy": 9, "scale_y": 0.94, "angle": 7}],
    # 开心：蓄力压扁 → 起跳拉长 → 滞空 → 落地再压（体积守恒的 squash & stretch）
    "happy": [{"dy": 0, "scale_y": 0.90, "scale_x": 1.07},
              {"dy": -34, "scale_y": 1.08, "scale_x": 0.94},
              {"dy": -52, "scale_y": 1.00, "scale_x": 1.00},
              {"dy": -8, "scale_y": 0.93, "scale_x": 1.05}],
    # 警觉：突然竖起来（纵向拉长、横向收窄）
    "alert": [{"dy": 0, "scale_y": 1.0},
              {"dy": -8, "scale_y": 1.06, "scale_x": 0.97},
              {"dy": -6, "scale_y": 1.03}],
    # 疲惫：瘫软压扁 + 横向摊开
    "collapsed": [{"dy": 0, "scale_y": 1.0},
                  {"dy": 12, "scale_y": 0.93, "scale_x": 1.03},
                  {"dy": 18, "scale_y": 0.90, "scale_x": 1.05}],
    # 被拎起：左右晃动 + 轻微拉长（"悬空"感）。循环播放 = 被拎着晃。
    "drag": [{"dy": -2, "angle": 6, "scale_y": 1.03},
             {"dy": 0, "angle": 0, "scale_y": 1.00},
             {"dy": -2, "angle": -6, "scale_y": 1.03}],
}


def remove_connected_background(img: Image.Image, tolerance: int = 26) -> Image.Image:
    """从四角泛洪填充，抠掉与边缘连通的纯色/棋盘格背景。

    只有**与图像边缘连通**的背景色会被置为透明，因此主体内部相近的浅色
    （如猫的米白肚皮，被深色轮廓包围）不会被误删。
    """
    rgba = np.array(img.convert("RGBA"))
    height, width = rgba.shape[:2]
    rgb = rgba[:, :, :3].astype(np.int16)
    visited = np.zeros((height, width), dtype=bool)

    seeds = [(0, 0), (0, width - 1), (height - 1, 0), (height - 1, width - 1)]
    bg_colors = [rgb[y, x] for y, x in seeds]
    queue = deque()
    for y, x in seeds:
        visited[y, x] = True
        queue.append((y, x))

    while queue:
        y, x = queue.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if ny < 0 or ny >= height or nx < 0 or nx >= width or visited[ny, nx]:
                continue
            pixel = rgb[ny, nx]
            if any(np.abs(pixel - color).max() <= tolerance for color in bg_colors):
                visited[ny, nx] = True
                queue.append((ny, nx))

    rgba[:, :, 3] = np.where(visited, 0, rgba[:, :, 3])
    return Image.fromarray(rgba, "RGBA")


def autocrop(img: Image.Image, padding: int = 4) -> Image.Image:
    """裁掉四周全透明的边距。"""
    bbox = img.getbbox()
    if bbox is None:
        return img
    left, top, right, bottom = bbox
    return img.crop((max(0, left - padding), max(0, top - padding),
                     min(img.width, right + padding), min(img.height, bottom + padding)))


def normalize_subject(img: Image.Image) -> Image.Image:
    """把主体等比缩放到统一高度（使用 NEAREST 保持像素风格锐利）。"""
    scale = SUBJECT_HEIGHT / img.height
    target = (max(1, int(round(img.width * scale))), SUBJECT_HEIGHT)
    return img.resize(target, Image.NEAREST)


def transform(subject: Image.Image, rule: Dict[str, float]) -> Image.Image:
    """对主体应用单帧变换（非均匀缩放 / 旋转），返回变换后的图像。

    支持 ``scale_x`` / ``scale_y`` / ``angle``。**两者同时给**即构成
    squash & stretch（挤压拉伸）：压扁时横向变宽、拉长时横向变窄，
    保持视觉体积大致守恒 —— 这是让"跳跃"看起来有重量感的关键，
    单纯的纵向平移看起来只是"整体上下移动"。
    """
    frame = subject
    scale_x = float(rule.get("scale_x", 1.0))
    scale_y = float(rule.get("scale_y", 1.0))
    if abs(scale_x - 1.0) > 1e-6 or abs(scale_y - 1.0) > 1e-6:
        new_w = max(1, int(round(frame.width * scale_x)))
        new_h = max(1, int(round(frame.height * scale_y)))
        frame = frame.resize((new_w, new_h), Image.NEAREST)
    angle = float(rule.get("angle", 0.0))
    if abs(angle) > 1e-6:
        # expand=False + 底部对齐可避免旋转后凭空长高
        frame = frame.rotate(angle, resample=Image.NEAREST, expand=False)
    return frame


def place_on_canvas(subject: Image.Image, dy: float = 0.0) -> Image.Image:
    """贴到统一画布：水平居中 + 底部对齐（+ 垂直偏移）。"""
    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    x = (CANVAS - subject.width) // 2
    baseline = int(CANVAS * BOTTOM_RATIO)
    y = baseline - subject.height + int(round(dy))
    canvas.paste(subject, (x, y), subject)
    return canvas


def generate(source: str, emotions: List[str], out_root: str = OUT_ROOT) -> int:
    """生成指定情绪的帧序列，返回写出文件数。"""
    raw = Image.open(source)
    cut = remove_connected_background(raw)
    alpha = np.array(cut)[:, :, 3]
    background_ratio = float((alpha == 0).mean())
    print(f"源图 {os.path.basename(source)}: {raw.size[0]}x{raw.size[1]}，"
          f"抠除背景 {background_ratio:.1%}")

    subject = normalize_subject(autocrop(cut))
    print(f"主体归一化: {subject.width}x{subject.height}")

    written = 0
    for emotion in emotions:
        rules = EMOTION_RULES.get(emotion)
        if not rules:
            print(f"  [跳过] 未知情绪 {emotion}")
            continue
        folder = os.path.join(out_root, emotion)
        os.makedirs(folder, exist_ok=True)
        # 清理该情绪下的旧帧，避免帧数变化后残留
        for name in os.listdir(folder):
            if name.lower().endswith(".png"):
                os.remove(os.path.join(folder, name))

        for index, rule in enumerate(rules, start=1):
            frame = place_on_canvas(transform(subject, rule), dy=rule.get("dy", 0.0))
            path = os.path.join(folder, f"{emotion}_{index:02d}.png")
            frame.save(path)
            written += 1
        print(f"  {emotion:10s} {len(rules)} 帧")
    return written


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="从单张静态图生成桌宠帧序列")
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="源图路径")
    parser.add_argument("--emotions", nargs="*", default=list(EMOTION_RULES),
                        help="要生成的情绪（默认全部）")
    parser.add_argument("--out", default=OUT_ROOT, help="输出根目录")
    args = parser.parse_args(argv[1:])

    if not os.path.exists(args.source):
        print(f"[ERROR] 源图不存在: {args.source}")
        return 2

    total = generate(args.source, args.emotions, args.out)
    print(f"\n共输出 {total} 帧 → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
