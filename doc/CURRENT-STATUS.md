# 工作现状快照 · CURRENT-STATUS

> **Agent 每轮任务开始前必读本文件。**
> 快照日期：**2026-10-08** ｜ 依据：本仓库代码 + 回归测试（`.venv/Scripts/python.exe -m pytest tests -q` → **42 passed**）
> 本文件描述"现在是什么样"，不是"计划要做什么"。未真机验证的条目已标注。

---

## 一、当前在做什么

**动画路线已定案**：形象固定为**像素猫** → 采用 **SVG 部件分层 + 代码程序驱动**，不引入 Live2D/OpenGL、不做 Lottie。

**配置体系已接线**（2026-10-08）：新增 `core/config.py` 统一入口，优先级 `app_settings`（用户修改）> `config/settings.yaml`（出厂默认）> 代码兜底 —— `settings.yaml` 从此**真正生效**（此前是死配置）。

下一步是 P2 交互增强三件套（随机微动作 / 视线跟随 / 抚摸反馈），它们共用这条动画路线，也是待办里唯一成组的前置依赖。

✅ **无环境阻断**：LLM 对话已由用户实测通过。此前记录的 V0004（"无可用模型"）已**撤回** —— 模型存放于移动硬盘，`ollama list` 为空只是未挂载所致（教训见 `testing/buglist.md` V0004）。

**当前唯一的技术卡点就是动画**（用户 2026-10-08 确认）；其余待办见 `dev/计划-当前待办.md` —— 经代码核实**仅 3 项未完成**。

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
- `chat/`（对话编排 + 人格提示词构建；**流式已完整接线**：`generate_stream` → `set_stream_callback` → `chat_bubble.stream_append`）
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

## 三、待办清单

> **来源**：`dev/计划-当前待办.md`（**已按 2026-10-08 逐项代码核实重写**）
> 原《2.0 冲刺待办清单》15 项经核实 **13 项已实现**，已移入 `归档/`（含失真教训记录）。

### 3.1 真实未完成（3 项）

| 编号 | 项 | 现状 |
|---|---|---|
| **P1-2** | 画像结构化显示（按 category 分组 + 段落） | 未实现：现状为 `[category] 摘要 (重要性)` 逐行列表 |
| **E11-os** | **OS 级**点击穿透 | 未实现：Qt 层已有 alpha 逐像素命中 + `e.ignore()`（`_is_click_on_body`）；代码中无 `WS_EX_TRANSPARENT`。**待决策走哪条路线** |
| **CFG-2** | 第二批配置接入（`schedule.*` / `window.*` / `memory.decay_half_life_days` / `summary_interval`） | 未实现：仍走代码内默认值 |

### 3.2 已完成（原清单项，逐一经代码核实）

| 编号 | 项 | 已实现的证据 |
|---|---|---|
| P1-1 | 隐式特质抽取 | `modules/personality/extractor.py` 三层架构（规则 + LLM 摘要层；`_trigger_llm_summary`，按轮数阈值触发） |
| P2-1 | 随机微动作 | `floating_pet._do_micro_action`（本轮改为 `pet_conf.json` 权重表驱动，4 个动作） |
| P2-2 | 鼠标视线跟随 | `floating_pet._track_mouse` + `compute_track_offset`（本轮修复限幅 bug） |
| P2-3 | 抚摸反馈 | `floating_pet._on_petted`（hover 1.5s → happy + "呼噜呼噜~"） |
| P3-1 | LLM 日记 | `modules/diary.py:32`（优先 LLM，失败回退模板；含 `_llm_diary`） |
| P3-2 | LLM 健康贴士 | `modules/health/meal_engine.py:122/321`（饮食推荐后追加一句健康小贴士） |
| P3-3 | 记忆 LLM 提取 | `modules/chat/chat_manager.py:318`（先让 LLM"用一句简短的话总结这段对话的核心内容"，再 `add_memory`） |
| E5 | 流式对话 | `main.py:545` `set_stream_callback` + `stream_append` / `stream_finish`；`chat_bubble` 有打字机接口 |
| E16 | 冲突检测缓存 | `modules/schedule/schedule_parser.py:67` `_pending_items`（注释："待入库日程，参与冲突检测"）+ `add_pending` / `clear_pending` |
| O1 | FAISS 死向量压缩 | `services/memory_service.py` `_deleted_ids` + 死向量 >30% 触发压缩 + `_rebuild_index` |
| O2 | 对话存档 LRU | `modules/chat/chat_manager.py:36` `_history_cache`（内存缓存最近 100 条） |
| O3 | 上下文 token 控制 | `max_tokens=512`（本轮已从硬编码改为 `settings.yaml` 配置项 `llm.max_tokens`） |
| O4 | 启动加载并行化 | `main.py` 三处守护线程：LLM 预热 / 记忆初始化 / 消息处理 |

**编号含义**：`P1` 个性化 · `P2` 交互 · `P3` LLM 渗透 · `E` 1.1 遗留 · `O` 性能优化 · `CFG` 配置类。

## 四、已知问题（详见 `testing/buglist.md`）

| # | 问题 | 严重度 | 状态 |
|---|---|---|---|
| 1 | 动画资源脏目录 `pet_lottie'` | P2 | ✅ 已修复（删除空目录） |
| 2 | 仓库无 `.gitignore`，38522 个跟踪文件含 `venv/` `__pycache__` `pet.db` `build/` | P2 | ✅ 已修复（→ 159 个跟踪文件，磁盘文件保留） |
| 3 | `config/settings.yaml` 从未被代码读取 + 配置源分裂（`app_settings` 生效 / yaml 不生效 / 键名两套 / 模型名四处不一致） | **P1** | ✅ 已修复（新增 `core/config.py` 统一入口，接入 `main.py` + 4 个 service + 2 个 health 模块） |
| 4 | ~~Ollama 中无任何模型~~ → **撤回**：模型存于移动硬盘（未挂载时 `ollama list` 为空），对话已由用户实测可用 | — | ✅ 非缺陷 |
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
| **动画实现** | **整帧形变 + 程序化特效层 + 交叉淡化**：帧动画层（已有）+ 变换层（呼吸/视线跟随/弹跳）+ 特效层（`QPainter` 绘制 Zzz/爱心/汗滴）+ 交叉淡化平滑 |
| **作废路线** | ❌ Lottie（需 AE 制作 7 个 JSON，无美术时间，见 `dev/方案-Lottie动画迁移.md`）<br>❌ Live2D + `live2d-py`（需二次元人形模型，且引入 OpenGL 透明窗口风险）<br>❌ 骨骼动画（Alpha 版裁剪明确排除）<br>❌ **SVG 部件分层**（2026-10-08 素材核查：帧为连续噪点色的整帧像素画，无部件语义）<br>❌ **像素级插值补帧**（帧间为不同姿态，会重影） |
| **覆盖动作** | 呼吸起伏 · 鼠标视线跟随（P2-2）· 弹跳/抖动 · 情绪特效（P2-1）· 抚摸反馈（P2-3） |
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

### D-003 · 动画实现方式修正（2026-10-08）

| 项 | 结论 |
|---|---|
| **变更原因** | 素材核查发现现有帧是 AI 生成的**整帧像素画**（每帧 1276~2196 个 4×4 rect、连续噪点色、无部件语义），原定"SVG 部件分层"**不可行** |
| **实现方式** | 帧动画层（已有）+ 变换层（呼吸/视线跟随/弹跳）+ 程序化特效层（`QPainter`）+ 交叉淡化平滑 |
| **明确不做** | 像素级插值补帧（帧间为不同姿态，会重影）；部件硬切（位置逐帧漂移，会断裂） |
| **用户决策** | 2026-10-08 选择「整帧形变 + 程序化特效层 + 插值补帧」方向，并接受"以变换插值 + 交叉淡化替代像素插值"的实现修正 |

---

## 七、当前阻塞

**无阻塞。** 此前记录的 V0004 已撤回（模型存于移动硬盘 + 对话已实测可用）。

**唯一的技术卡点是动画**（用户 2026-10-08 确认），路线与实现方式均已定案（见 §六 D-001 / D-003）。其余为 2.0 冲刺清单中的可优化点与后续待办，均可自主推进。
