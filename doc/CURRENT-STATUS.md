# 工作现状快照 · CURRENT-STATUS

> **Agent 每轮任务开始前必读本文件。**
> 快照日期：**2026-10-08** ｜ 依据：本仓库代码 + 回归测试（`.venv/Scripts/python.exe -m pytest tests -q` → **42 passed**）
> 本文件描述"现在是什么样"，不是"计划要做什么"。未真机验证的条目已标注。

---

## 一、当前在做什么

**动画路线已定案**：形象固定为**像素猫** → 采用 **SVG 部件分层 + 代码程序驱动**，不引入 Live2D/OpenGL、不做 Lottie。

**配置体系已接线**（2026-10-08）：新增 `core/config.py` 统一入口，优先级 `app_settings`（用户修改）> `config/settings.yaml`（出厂默认）> 代码兜底 —— `settings.yaml` 从此**真正生效**（此前是死配置）。

下一步是 P2 交互增强三件套（随机微动作 / 视线跟随 / 抚摸反馈），它们共用这条动画路线，也是待办里唯一成组的前置依赖。

⚠️ **仍有一个 P1 阻断**（见 §四 V0004）：Ollama 中没有模型 → **LLM 对话实际不可用**。该问题已由用户认领自行处理（修正环境变量 + pull 模型）；开工 P3 系列（LLM 渗透）前需先解决。

---

## 二、已就绪的能力（代码快照）

### 2.1 骨架层

| 能力 | 位置 | 状态 |
|---|---|---|
| 事件总线（sync/async/UI 线程安全） | `core/event_bus.py` | ✅ 有单测 |
| 状态机（用户状态 / 桌宠模式） | `core/state_manager.py` | ✅ 有单测 |
| 服务注册表 | `core/service_registry.py` | ✅ |
| 模型管理器（VRAM 预算、加载/卸载） | `core/model_manager.py` | ✅ |
| 日志 / 加密 / 系统信息 | `utils/` | ✅ |
| 应用装配（启动顺序、服务注册、快捷键） | `main.py` | ✅ |

### 2.2 服务层

`services/`：`llm_service`（Ollama）· `memory_service`（FAISS + 嵌入）· `search_service`（降级链）· `location_service`（高德）· `ocr_service` · `stt_service` · `tts_service` · `tool_executor` · `update_service`

### 2.3 业务模块

`modules/`：
- `chat/`（对话编排 + 人格提示词构建，**已含流式生成骨架** `generate_stream` / `set_stream_callback`）
- `schedule/`（解析 · 重复规则 · 调度 · 存储，解析器有单测）
- `health/`（饮水 · 久坐 · 用餐 · 睡眠 · 情绪记录，情绪有单测）
- `personality/`（抽取 · 遗忘曲线 · 档案管理）
- 单文件模块：`diary` · `memo` · `habit` · `pomodoro` · `greeting` · `easter_egg`
- `onboarding/wizard.py`（引导向导）

### 2.4 UI 层

`ui/`：`floating_pet`（悬浮窗 · SVG 帧动画 · 拖拽 · 贴边隐藏）· `chat_bubble`（气泡 · **打字机流式接口 `stream_begin/append/finish`**）· `notification_bubble`（含 `NotificationManager` 优先级排队）· `mini_schedule` · `settings_window` · `system_tray` · `about_dialog` · `theme`

### 2.5 测试

`tests/unit/`：`test_event_bus` · `test_state_manager` · `test_schedule_parser` · `test_mood_logger` → **42 passed / 1 warning（sip 弃用，无害）**
`tests/integration/`：⚠️ **空**，尚无集成场景用例。

---

## 三、待办清单（来源：`dev/计划-2.0冲刺待办清单.md`）

| 编号 | 项 | 现状判定 |
|---|---|---|
| P1-1 | 隐式特质抽取（每 5 轮 LLM 抽取） | 未开始（依赖 V0004 修好） |
| P1-2 | 画像结构化按类分组显示 | 未开始 |
| **P2-1** | **idle 随机微动作** | **未开始 — 路线已定，可开工** |
| P2-2 | 鼠标视线跟随 | 未开始 — 路线已定，可开工 |
| P2-3 | 抚摸反馈（hover > 2s → happy） | 未开始 — 路线已定，可开工 |
| P3-1 | LLM 生成日记 | 未开始（依赖 V0004） |
| P3-2 | LLM 健康贴士 | 未开始（依赖 V0004） |
| P3-3 | 记忆存储前 LLM 提取关键信息 | 未开始（依赖 V0004） |
| E5 | 流式对话输出 | ⚠️ **代码已含流式骨架**，待真机确认是否已达"≤200ms 首字" |
| E11 | 点击穿透 | 未开始（无 `setMask` / `WS_EX_TRANSPARENT`）；方案见 `dev/方案-点击穿透E11.md` |
| E16 | 冲突检测缓存（待确认日程参与计算） | 未开始 |
| O1 | FAISS 死向量压缩 | 未开始 |
| O2 | 对话存档 LRU 缓存 | 未开始 |
| **O3** | 上下文 token 控制 | ⚠️ **已部分实现**：`main.py:316` 硬编码 `max_tokens=512`（原清单标"未开始"有误） |
| O4 | 启动加载并行化 | 未开始 |

**编号含义**：`P1` 个性化 · `P2` 交互 · `P3` LLM 渗透 · `E` 1.1 遗留 · `O` 性能优化。

---

## 四、已知问题（详见 `testing/buglist.md`）

| # | 问题 | 严重度 | 状态 |
|---|---|---|---|
| 1 | 动画资源脏目录 `pet_lottie'` | P2 | ✅ 已修复（删除空目录） |
| 2 | 仓库无 `.gitignore`，38522 个跟踪文件含 `venv/` `__pycache__` `pet.db` `build/` | P2 | ✅ 已修复（→ 159 个跟踪文件，磁盘文件保留） |
| 3 | `config/settings.yaml` 从未被代码读取 + 配置源分裂（`app_settings` 生效 / yaml 不生效 / 键名两套 / 模型名四处不一致） | **P1** | ✅ 已修复（新增 `core/config.py` 统一入口，接入 `main.py` + 4 个 service + 2 个 health 模块） |
| 4 | **Ollama 中无任何模型**；`OLLAMA_MODELS` 指向不存在的 `E:\dev\ollama\modals`（疑为 `models` 拼写错误）→ LLM 对话实际不可用 | **P1** | ⏸ 用户自理（修正环境变量 + pull 模型） |
| 5 | `config/secrets.yaml` 真实 key 曾入库 | P3 | ✅ 已修复（用户已删 key + 已解绑 + 新增模板） |
| 6 | `cat_1.png`（1.25MB 孤立素材）入库 | P3 | ✅ 已修复（解绑 + `.gitignore`，磁盘保留） |
| 7 | `tests/integration/` 为空 | — | 待补齐 |
| 8 | `llm_service.py` 默认模型名与配置口径不一 | P3 | ✅ 已修复（`main.py` 改读 `llm.model`，口径统一到 `settings.yaml`） |
| 9 | `schedule.*` / `window.*` / `memory.decay_half_life_days` / `memory.summary_interval` 尚未接入统一配置 | P3 | 待第二批接入 |

---

## 五、待决策事项（**需用户拍板**）

1. **点击穿透实现路线**：整窗穿透 + 右键守卫（约 1 小时）／ `WM_NCHITTEST` 逐像素命中（约 1 天，工业标准）。分析见 `dev/方案-点击穿透E11.md`。
2. **第二批配置接入范围**：`schedule.*` / `window.*` / `memory.decay_half_life_days` / `memory.summary_interval` 是否随下一个模块一并接入。（配置体系本身已定案，见 §六 D-002）

---

## 六、决策记录（已定案，不再重议）

### D-001 · 桌宠形象与动画路线（2026-10-08 定案）

| 项 | 结论 |
|---|---|
| **形象** | **固定为像素猫**（不做二次元人形，不做 3D） |
| **动画路线** | **SVG 部件分层 + 代码程序驱动**（`body / ears / tail / eyes` 四层 + `QPropertyAnimation` + `QTimer`） |
| **作废路线** | ❌ Lottie（需 AE 制作 7 个 JSON，无美术时间，见 `dev/方案-Lottie动画迁移.md`）<br>❌ Live2D + `live2d-py`（需二次元人形模型，且引入 OpenGL 透明窗口风险）<br>❌ 骨骼动画（Alpha 版裁剪明确排除） |
| **覆盖动作** | 呼吸起伏 · 眨眼 · 尾巴摆动 · 耳朵抖动（P2-1）· 鼠标视线跟随（P2-2）· 抚摸反馈（P2-3） |
| **决策依据** | 形象约束为猫；无美术时间投入；不引入新依赖；当天可出效果 |

> 完整的路线对比与实施要点见 `dev/方案-动画与气泡系统设计笔记.md`。

### D-002 · 配置体系接线（2026-10-08 定案）

| 项 | 结论 |
|---|---|
| **统一入口** | `core/config.py` 的 `config` 单例 |
| **优先级** | `app_settings` 表（用户修改） > `config/settings.yaml`（出厂默认） > 调用方传入的兜底值 |
| **键名规范** | yaml 的点号路径（`llm.timeout`、`health.drink_target_ml`）；历史键名由 `_DB_KEY_ALIASES` 别名表兼容 |
| **写入落点** | 仅 `app_settings`（`config.set()` 同步双写规范键与别名） |
| **随附决策** | `llm.max_tokens` 固化 **512**（待办 O3：回复限 150 字内，提速约 40%）；`llm.timeout` 放宽至 **60**（冷启动首次请求会触发模型加载） |
| **模型口径** | 统一到 `settings.yaml` 的 `qwen2.5:7b-instruct-q4_K_M`（`main.py` 不再硬编码） |
| **决策依据** | 用户选择"实现配置加载模块"而非删除配置文件；`settings.yaml` 是设计文档声明的权威默认值来源 |
| **验收** | 新增 `tests/unit/test_config.py` 24 项；全量 `pytest tests -q` → 66 passed |

---

## 七、当前阻塞

**一个 P1 阻断（需用户处置，非 Agent 可自行解决）**：

1. **V0004**：环境变量 `OLLAMA_MODELS` 路径错误 + 无模型 → LLM 不可用。用户已声明自行处理（修正环境变量并 `ollama pull qwen2.5:7b-instruct-q4_K_M`）。

**可自主推进的**：全部 P2 动画/交互项（路线已定）、E11 点击穿透（方案已出）、O1/O2/O4 性能项、第二批配置接入。
