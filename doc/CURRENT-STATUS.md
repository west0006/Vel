# 工作现状快照 · CURRENT-STATUS

> **快照日期：2026-11-10** ｜ 依据：本仓库代码 + 全量回归
> （`venv/Scripts/python.exe -m pytest tests -q` → **297 passed / 8 warnings**）
>
> 本文件描述"现在是什么样"，不是"计划要做什么"。未真机验证的条目已标注。
> 上一版快照停留在 2026-10-08，其中动画路线、回归数、集成测试与待办数量已失真；
> 本次修正明细见 §八（保留修正记录，便于下次判断"这份快照可信到什么程度"）。

---

## 一、当前在做什么

**动画表现力 P1~P4 已落地（2026-11-10）**：帧素材改为「单图程序化生成」
（`ui/resources/animations/pet_png/`，9 个情绪目录 / 31 帧），并完成逐帧时长（P1）、
特效时长对齐（P2）、squash & stretch（P3）、拖拽反馈（P4）。
P5（补姿态图）视 P1~P3 的观感再定，**未开工**。
> ⚠️ P1~P4 有单测与渲染诊断支撑，**尚无"真机肉眼验收通过"的记录**。

**当前优先处理两个"静默失效"**（AST 审计 + 代码核实，详见 `dev/计划/计划-当前待办.md`）：

- **EMO-1**：情绪信号无出口 —— `EVENT_MOOD_DETECTED`（`mood_detected`）有**两个**发布方
  （`chat_manager._analyze_mood`、`mood_logger.analyze`），**零订阅者**；
  彩蛋 `match()` 返回的 `emotion` 被 `process_message` 丢弃。
- **NOTIFY-1**：习惯 / 备忘录 / 番茄钟的提醒只 `bus.publish`，
  `HABIT_*` / `MEMO_REMINDER` / `POMODORO_PAUSE|RESUME|CANCEL` 均无订阅者，
  用户完全看不到提醒（`POMODORO_END` 的订阅方只恢复久坐计时）。

**环境**：无阻断。LLM 对话已由用户实测可用（V0004 已撤回）。
"LLM 输出特别慢"已定位为模型反复重载（V0016），已用 `keep_alive="30m"` +
固定 `num_ctx=4096` 缓解（V0016 遗留：跨客户端 `num_ctx` 不一致仍会触发重载）。

---

## 二、已就绪的能力（2026-11-10 代码快照）

### 2.1 骨架层

| 能力 | 位置 | 状态 |
|---|---|---|
| 事件总线（sync/async/UI 线程安全） | `core/event_bus.py` | ✅ 有单测 + 集成测试 |
| 统一配置（`app_settings` > `settings.yaml` > 兜底） | `core/config.py` | ✅ 有单测 |
| 状态机 / 服务注册表 / 模型管理器 | `core/state_manager.py` · `service_registry.py` · `model_manager.py` | ✅ |
| 日志 / 加密 / 系统信息 | `utils/` | ✅ |
| 应用装配（启动顺序、服务注册、快捷键） | `main.py` | ✅ |

### 2.2 服务层

| 服务 | 状态 |
|---|---|
| `llm_service`（Ollama） | ✅ 降级可恢复；`keep_alive` / `num_ctx` 已接配置（V0016） |
| `memory_service`（FAISS + sentence-transformers） | ✅ 后台初始化，含死向量压缩 |
| `search_service`（Bing → ddgs → 旧包 → API） | ✅ 库通道已修复（V0012） |
| `location_service`（高德免费层） | ✅ 无 key 时自动禁用 |
| `tool_executor` | ✅ 已注册 |
| `update_service` | 📋 占位骨架，**未接线**（设计阶段 7，V0011） |
| `ocr_service` / `stt_service` / `tts_service` | 📋 Alpha 仅留接口，**未注册** |

### 2.3 业务模块

- `chat/`：对话编排 + 人格提示词；**流式已完整接线**（`generate_stream` →
  `set_stream_callback` → `chat_bubble.stream_append`）；彩蛋主动推送 + `_worker` 兜底（V0017）。
- `schedule/`：解析 · 重复规则 · 调度 · 存储（解析器有单测）。
- `health/`：`drink_reminder` · `meal_engine` · `sedentary_monitor` · `sleep_tracker` 由 `main.py` 注册；
  `mood_logger` 已实现但**未注册**（V0018，待确认），对话情绪分析实际走
  `chat_manager._fallback_mood_analyze` 关键词兜底。
- `personality/`：`extractor` · `profile_manager` 已注册；
  `ForgettingEngine`（遗忘曲线）**全仓无调用、未接线**（V0019，待确认是否本阶段范围）。
- 单文件模块：`diary` · `memo` · `habit` · `pomodoro` · `greeting` · `easter_egg`。
- `onboarding/wizard.py`：首次运行引导。

### 2.4 UI 层

- `floating_pet`：`pet_png/` 优先（9 情绪 / 31 帧），`pet_svg/`（35 个 `.svg`）回退；
  呼吸形变 · 视线跟随 · 微动作（`pet_conf.json` 4 个动作）· 拖拽 · 贴边隐藏 · 程序化特效层。
- `chat_bubble`：打字机流式接口 `stream_begin / stream_append / stream_finish`。
- `notification_bubble`：含 `NotificationManager` 优先级排队。
- `mini_schedule` · `settings_window` · `system_tray` · `about_dialog` · `theme` · `pet_fx`。

### 2.5 测试

- `tests/unit/`：17 个测试文件；`tests/integration/`：3 个（对话主链 / DB 配置 / 事件总线线程语义）。
- 全量：**297 passed / 8 warnings**（warnings 为 sip 弃用等，未发现失败）。
- 未覆盖：GUI 真机交互、Ollama 端到端、搜索/位置网络链路、OCR/语音。

---

## 三、待办清单（9 项）

> **唯一来源**：`dev/计划/计划-当前待办.md`（本表仅同步摘要，改动请先改该文件）。

| 编号 | 项 | 规模 |
|---|---|---|
| **EMO-1** | 情绪信号驱动表情（复用现有 `EVENT_MOOD_DETECTED`，覆盖彩蛋与对话两个来源） | 小 |
| **NOTIFY-1** | 习惯 / 备忘录 / 番茄钟提醒对用户可见 | 中 |
| **P1-2** | 画像结构化显示（按 `category` 分组 + 段落） | 小 |
| **E11-os** | OS 级点击穿透（路线待决策） | 中 |
| **CFG-2** | 第二批配置接入（`schedule.*` / `window.*` / `memory.decay_half_life_days` / `summary_interval`） | 小 |
| **G1** | 健康看板 UI | 小 |
| **G2** | 用眼保护（连续 75 分钟检测） | 中 |
| **G3** | 缺失动画动作（提醒敲屏幕 / 背身偷看） | 中 |
| **G4** | 喂食与养成系统（**是否在范围内待确认**） | 大 |

**编号含义**：`P1` 个性化 · `P2` 交互 · `P3` LLM 渗透 · `E` 1.1 遗留 · `O` 性能优化 · `CFG` 配置类 · `G` 功能深度差距。

---

## 四、已知问题

> 完整台账见 `testing/buglist.md`（V0001~V0019）。

| # | 问题 | 严重度 | 状态 |
|---|---|---|---|
| V0018 | `mood_logger` 未被 `registry.register`，`chat_manager` 取不到 → 情绪分析走关键词兜底；`MoodLogger` 的 DB 记录 / 连续负面计数 / 每日缓存均不生效 | P2 | **待确认**（代码静态核实） |
| V0019 | `ForgettingEngine` 全仓无调用，遗忘曲线未接线（设计是否要求本阶段生效待确认） | P3 | **待确认** |
| V0005 | 历史提交中的高德 key 仍存在（已失效，风险可接受） | P3 | ✅ 已处置 |
| V0016 | 若其它客户端用不同 `num_ctx` 连同一 Ollama，仍会互相触发重载 | P3 | 遗留（非本项目单方可解） |
| V0001~V0017 | 均已修复/撤回（含 V0002 仓库卫生、V0007 降级可恢复、V0009 UI 投递、V0012 搜索库、V0013 流式接口、V0014/V0015 全屏检测、V0017 彩蛋无输出） | — | ✅ 详见台账 |

> `tests/integration/` **已非空**（3 个用例），上一版快照"空"的记录已失效。

---

## 五、待决策事项（需用户拍板）

1. **点击穿透实现路线（E11-os）**：整窗穿透 + 右键守卫（约 1h）／ `WM_NCHITTEST`
   逐像素命中（约 1 天）。分析见 `dev/方案/方案-点击穿透E11.md`。
2. **第二批配置接入范围（CFG-2）**：`schedule.*` / `window.*` / `memory.*` 是否随下一个模块一并接入。
3. **P5 姿态图**是否投入：P1~P3 观感达标则不做。

---

## 六、决策记录（已定案，不再重议）

### D-001 · 桌宠形象与动画路线（2026-10-08 定案）

| 项 | 结论 |
|---|---|
| **形象** | **固定为像素猫**（不做二次元人形，不做 3D） |
| **动画实现** | 帧动画层 + 变换层（呼吸/视线跟随/弹跳）+ 程序化特效层（`QPainter`）+ 交叉淡化 |
| **作废路线** | ❌ Lottie ❌ Live2D / OpenGL ❌ 骨骼动画 ❌ SVG 部件分层 ❌ 像素级插值补帧 |
| **覆盖动作** | 呼吸 · 视线跟随 · 弹跳/抖动 · 情绪特效 · 抚摸反馈 |

### D-002 · 配置体系接线（2026-10-08 定案）

| 项 | 结论 |
|---|---|
| **统一入口** | `core/config.py` 的 `config` 单例 |
| **优先级** | `app_settings` > `config/settings.yaml` > 调用方兜底 |
| **键名规范** | yaml 点号路径；历史键名由 `_DB_KEY_ALIASES` 兼容 |
| **写入落点** | 仅 `app_settings`（`config.set()` 同步双写规范键与别名） |
| **模型口径** | `config/settings.yaml` 的 `qwen2.5:7b`。2026-11-10 由 `qwen2.5:7b-instruct-q4_K_M` 变更：本地实际可用的是默认 tag，指定 `q4_K_M` 会令 `/api/chat` 返回 404 |
| **验收（当时基线）** | 新增 `tests/unit/test_config.py` 24 项；当时全量 66 passed（**当前基线 297 passed**） |

### D-003 · 动画实现方式修正（2026-10-08 定案 → 2026-11-10 落地）

| 项 | 结论 |
|---|---|
| **变更原因** | 旧素材是 AI 逐帧独立生成的整帧像素画，平移对齐后残余差异 75~98% |
| **实现方式** | 帧动画层 + 变换层 + 程序化特效层 + 交叉淡化；**2026-11-10 进一步改为单图程序化生成帧序列**（`tools/gen_pet_frames.py` → `pet_png/`） |
| **明确不做** | 像素级插值补帧；部件硬切 |
| **回退** | `_load_frames` 优先 `pet_png/`，回退 `pet_svg/`（35 个 `.svg` 帧） |

---

## 七、当前阻塞

**无阻塞。** 环境、模型、依赖均已就绪；剩余为功能缺口与待决策项（§五）。

---

## 八、2026-11-10 快照修正记录

上一版快照（2026-10-08）经代码与回归核实，修正如下（保留记录，避免再次失真）：

1. **动画路线**：§一 原写"SVG 部件分层 + 代码程序驱动"，与 §六 D-001/D-003 已否决该路线矛盾 → 更正为"单图程序化生成 + 整帧形变"。
2. **回归数**：42 / 66 → **297 passed**（`pytest tests -q` 实测）。
3. **集成测试**：原"`tests/integration/` 为空" → 实际有 3 个用例。
4. **待办数量**：原"仅 3 项未完成" → 计划文件核为 **9 项**（含 EMO-1 / NOTIFY-1 / G1~G4）。
5. **情绪事件**：原 EMO-1 结论"`event_bus.py` 现无情绪事件，需新增"**错误** —— `EVENT_MOOD_DETECTED` 自首次提交即存在，且有两个发布方；缺的是订阅者与 UI 通道。
6. **新增待确认缺陷**：V0018（`mood_logger` 未注册）、V0019（`ForgettingEngine` 未接线）。
7. **测试解释器**：`.venv-py311/` 已损坏；可用解释器为 `venv/Scripts/python.exe`（Python 3.10.11）。
