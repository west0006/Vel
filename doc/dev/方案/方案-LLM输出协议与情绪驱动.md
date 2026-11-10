# 方案 · LLM 输出协议与情绪驱动

> **对应待办**：P3-1 / P3-2 / P3-3（LLM 渗透）· E5（流式对话，代码已有骨架）
> **机制来源**：MeaPet `meapet/conversation/output_protocol.py`（MIT），按 Alpha 版裁剪后改写，**未复制代码文本**
> **状态**：设计完成，**未实施**

---

## 一、要解决的问题

当前 `main.py` 中情绪切换是**硬编码**的：

```python
self._floating_pet.set_emotion("thinking", loop=True)   # 发问时
self._floating_pet.set_emotion("idle")                  # 回复后
```

即：桌宠的表情与"对话内容"完全无关。目标是让**模型自己决定**该用什么情绪与动作。

同时 E5 的流式显示已经具备能力（`chat_manager.generate_stream`、`chat_bubble.stream_begin/append/finish`），缺的是**中间层**：把流式文本里的协议标签解析出来，一路推正文、一路触发情绪。

---

## 二、协议设计

### 2.1 MeaPet 原版（参考）

```
<MEA_PET_SEGMENT>
  <DISPLAY>显示给用户看的文本</DISPLAY>
  <META>{"voice_text":"…","voice_language":"zh-CN","mood":"happy","tts_style":"…"}</META>
</MEA_PET_SEGMENT>
<MEA_PET_DONE/>
```

`ReplySegment` 必填字段：`{display_text, voice_text, voice_language, mood, tts_style}` —— 由 `providers` 声明，`missing_required_fields` 同时判"没给"和"给了空串"。

**VTS 特色**：`FrontendCapabilities`（`renderer` / `supported_moods` / `supported_motions` / `tts_enabled` / `tts_languages`）会被下发给模型，告诉它"你只能从这些里选"。

### 2.2 Vel 裁剪版（本方案）

Alpha 阶段 TTS 不露出（AGENTS §7 裁剪），因此**去掉** `voice_text` / `voice_language` / `tts_style`，只留两个字段：

```
<META>{"mood": "happy", "action": "nuzzle"}</META>
这里是要显示给用户的正文……
```

| 字段 | 约束 |
|---|---|
| `mood` | **必须**是白名单之一：`idle` `wake` `thinking` `sleep` `sad` `happy` `alert` `collapsed`（= `ui/floating_pet.py` 中 `_frames_cache` 的 8 个键，多一个就会切到不存在的帧目录而显示空白） |
| `action` | 可选，小写字母 + 下划线，用于 P2 微动作；缺省为空 |

**关键差异**：MeaPet 检测到字段缺失会**再请求一轮 LLM 修复**；Vel 不这么做 —— Alpha 版回复限定 150 字内，多跑一轮推理不值得，直接补默认值（`mood=idle`）。

---

## 三、必须实现的容错机制（**本方案的核心价值**）

协议一定会被模型写坏。以下 6 条是 MeaPet 的实战经验，逐条对应真实故障：

| # | 机制 | 不做会怎样 |
|---|---|---|
| 1 | **边界回退窗口**（`BOUNDARY_WINDOW = 48`）：每轮扫描从 `len(raw) - 48` 回退重扫 | chunk 把 `<META` 从中间切断 → 该标签**永久漏检**，情绪全程不生效 |
| 2 | **半个闭合标签抑制**（`_without_partial_close_tag`）：尾部若是 `</MET` 这类残片则不推送 | `</MET` 泄漏到气泡里显示给用户 |
| 3 | **惰性扫描**（记录 `_last_scan` / 已发出位置） | 每个 chunk 全量正则扫描 → O(n²)，长回复卡 UI 线程 |
| 4 | **结束只发一次**（`_done_emitted` 标志） | `META_DONE` 重复触发，回复结束逻辑跑多次 |
| 5 | **累积上限**（`MAX_RAW_CHARS`）+ `overflowed` 标志 | 模型跑飞时把内存吃满 |
| 6 | **三级降级**：protocol → legacy（`[mood] 正文`）→ plain 纯文本 | 模型不遵守协议时**整条回复丢失** |

---

## 四、数据流（接入点）

```
LLMService.generate_stream()            # 已存在（services/llm_service.py）
        │  chunk
        ▼
OutputStreamParser.feed(chunk)          # 【新增】modules/chat/output_parser.py
        │
        ├── TextDeltaEvent ──► ChatBubble.stream_append()       # 已存在（ui/chat_bubble.py）
        ├── MetaEvent      ──► FloatingPet.set_emotion(mood)    # 已存在（ui/floating_pet.py）
        └── DoneEvent      ──► 收尾 / 回到 idle
        │
        ▼  （跨线程：一律经 pyqtSignal 切回主线程，AGENTS §4.3）
```

**改动面很小**：新增 1 个纯逻辑模块（约 150 行、可写单测、不依赖 PyQt），`main.py` 装配 3 处（生成开始重置解析器、chunk 回调、生成结束 close）。

---

## 五、提示词侧配套（依据 Open-LLM-VTuber 做法）

参照 `prompts/utils/live2d_expression_prompt.txt` 的成功写法：**明确列出可选关键字 + 给正例 + 明说"不得使用列表外的关键字"**。

```
【输出格式要求】
你的每一次回复都必须以一段元数据开头（标签必须是英文、小写）：
<META>{"mood": "情绪", "action": "动作"}</META>
这里写你要说的话。

规则：
1. mood 只能从这 8 个词中选择：idle（平静）、wake（刚醒来）、thinking（思考）、
   sleep（困倦）、sad（低落）、happy（开心）、alert（警觉）、collapsed（疲惫）。
2. action 可省略，可选：nuzzle（蹭一蹭）、stretch（伸展）。
3. META 标签必须写在正文之前，整条回复只出现一次。
4. 标签之外的内容就是你要说的话，不要再出现任何尖括号标签。

正确示例：
<META>{"mood": "happy"}</META>主人回来啦，喵~ 我等你好久了！
<META>{"mood": "thinking", "action": "nuzzle"}</META>嗯……让我想想，这个日程放下午三点会比较合适。
```

**必须做**：把 mood 白名单写进 system prompt（等价于 MeaPet 的 `FrontendCapabilities` 下发）。不写，模型会编出不存在的情绪值。

---

## 六、验证方式（必做）

最容易出 bug 的是**流式分割**，必须用"逐字符喂入"的方式测：

```python
# tests/unit/test_output_parser.py 思路
def test_protocol_split_by_char():
    parser = OutputStreamParser()
    text = '<META>{"mood": "happy"}</META>你好呀'
    deltas, moods = [], []
    for ch in text:                      # ← 逐字符，模拟最坏切分
        for ev in parser.feed(ch):
            if isinstance(ev, TextDeltaEvent): deltas.append(ev.delta)
            if isinstance(ev, MetaEvent):      moods.append(ev.mood)
    for ev in parser.close():
        if isinstance(ev, TextDeltaEvent): deltas.append(ev.delta)
    assert "".join(deltas) == "你好呀"    # 正文一字不丢、不泄漏协议字符
    assert moods == ["happy"]
```

其他用例：① 模型完全不给 META（应降级 plain 且正文完整）；② 超过 120 字才出现 META（应判为 plain）；③ 未知 mood（应回退 `idle`）；④ META 内 JSON 损坏（不应抛异常）。

---

## 七、风险与边界

| 风险 | 说明 | 处置 |
|---|---|---|
| Qwen2.5:7b 协议遵守率不足 | 小模型可能漏 META 或写错 JSON | 已内置三级降级；必要时把 white-list 收窄到 4 个常用情绪 |
| 情绪频繁抖动 | 模型每条回复都换情绪，视觉上闪 | 可加"同情绪不重复触发"或最短保持时间 |
| 协议字符泄漏 | 流式切断标签 | 由机制 1、2 覆盖，并有单测兜底 |
| 与 TTS 冲突（未来） | 未来启用 TTS 时需 `voice_text` | 届时按 MeaPet 原版扩字段，协议已预留升级位 |

---

## 八、后续扩展（不在本方案范围）

- P3-1 日记 / P3-2 健康贴士 / P3-3 记忆提取：这三处是**一次性生成**（非流式），可直接复用 `parse_full()` 做非流式解析，得到 `(mood, action, clean_text, source_format)`。
- 未来接 TTS 时，参照 `sentence_divider.py` 的**标签状态机**做法扩展分句逻辑，避免切碎标签。
