## Lottie 动画迁移方案

### 技术栈

```
After Effects → Bodymovin 导出 JSON → rlottie-python 渲染 → QPixmap → FloatingPet.paintEvent
```

---

### 第一步：安装 rlottie

```bash
pip install rlottie-python
```

`rlottie-python` 是 Samsung rlottie 库的 Python 绑定，C++ 渲染引擎，速度极快。

---

### 第二步：制作动画（每个情绪一个 JSON）

每个情绪状态（idle/wake/thinking/sad/happy/alert/sleep）单独做一个 Lottie 文件，放到 `ui/resources/animations/pet_lottie/`。

| 文件 | 内容 | 时长 |
|------|------|------|
| `idle.json` | 呼吸起伏 + 耳朵偶尔动 + 尾巴慢摇 | 4s 循环 |
| `wake.json` | 起身 + 伸懒腰 + 眨眼 | 2s 一次 |
| `thinking.json` | 歪头 + 耳朵转向 + 尾巴摇 | 3s 循环 |
| `happy.json` | 蹦跳 + 尾巴快摇 + 眼睛弯 | 1.5s 一次 |
| `sad.json` | 低头 + 耳朵下垂 | 3s 循环 |
| `alert.json` | 竖耳 + 身体绷直 | 1s 循环 |
| `sleep.json` | 蜷缩 + 慢呼吸 | 4s 循环 |

---

### 第三步：改造 `floating_pet.py`

**`_load_frames` → `_load_lottie`**：

```python
from rlottie_python import LottieAnimation

LOTTIE_DIR = os.path.join(os.path.dirname(__file__), "resources", "animations", "pet_lottie")

def _load_lottie(emotion: str):
    path = os.path.join(LOTTIE_DIR, f"{emotion}.json")
    if not os.path.exists(path):
        return None
    anim = LottieAnimation()
    anim.load(path)
    size = anim.size()  # (width, height)
    return anim
```

**`FloatingPet.__init__` 改为加载 Lottie**：

```python
self._lottie = {}
for state in ("idle", "wake", "thinking", "sleep",
              "sad", "happy", "alert"):
    anim = _load_lottie(state)
    if anim:
        self._lottie[state] = anim
```

**`_tick` 改 Lottie 帧驱动**：

```python
def _tick(self) -> None:
    if not self.isVisible():
        return
    anim = self._lottie.get(self._emotion)
    if anim is None:
        return
    # 推进帧
    total = anim.total_frame()
    current = anim.frame() + 1
    if current >= total:
        if self._loop:
            current = 0
        else:
            self.set_emotion(self._after, loop=True)
            return
    anim.render_sync(current)
    self.update()
```

**`paintEvent` 改 Lottie 渲染**：

```python
def paintEvent(self, event) -> None:
    anim = self._lottie.get(self._emotion)
    p = QPainter(self)
    if anim is None:
        p.drawText(self.rect(), Qt.AlignCenter, "🐱")
        p.end()
        return

    buf = anim.buffer()
    w, h = anim.size()
    img = QImage(buf, w, h, QImage.Format_ARGB32)
    pix = QPixmap.fromImage(img)

    scale = self._display_size / max(w, h)
    sw, sh = int(w * scale), int(h * scale)
    scaled = pix.scaled(sw, sh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    px = (self._display_size - sw) // 2
    py = (self._display_size - sh) // 2
    p.drawPixmap(px, py, scaled)
    p.end()
```

---

### 第四步：清理

删除 `_load_frames`、`_compute_body_center`、`_BODY_HEX_PREFIXES`、`import xml.etree.ElementTree`。删除 `ui/resources/animations/pet_svg/` 整个目录。删除 `_mouse_track_offset` 和 `_track_mouse` 逻辑（Lottie 用 layer transform 自己做，不需要 Python 偏移）。

---

### 工作量

| 步骤 | 谁做 | 耗时 |
|------|------|------|
| 装 rlottie-python | 你 | 1 分钟 |
| 改 floating_pet.py | 我 | 15 分钟 |
| 制作 7 个 Lottie JSON | 你（或动画师） | 2-3 天 |

**核心瓶颈在第二步**——你需要会 After Effects 或者找动画师。如果你没有 AE 技能，这条路走不通。要不要换方案 A（SVG 2x 预渲染，5 分钟搞定）？