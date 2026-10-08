# 工作现状快照 · CURRENT-STATUS

> **Agent 每轮任务开始前必读本文件。**
> 快照日期：**2026-10-08** ｜ 依据：本仓库代码 + 回归测试（`.venv/Scripts/python.exe -m pytest tests -q` → **42 passed**）
> 本文件描述"现在是什么样"，不是"计划要做什么"。未真机验证的条目已标注。

---

## 一、当前在做什么

**动画与交互是当前最大卡点**，其次是把 LLM 能力渗透进各业务模块。

- 现状：桌宠动画是**逐帧 SVG 序列**（`ui/floating_pet.py`，8 个情绪状态目录），由 `QTimer` 驱动切换；情绪切换目前**只在 `main.py` 中硬编码**（对话时切 `thinking`，结束回 `idle`）。
- 卡点：动画**不可控**（AI 生图产出的帧不稳定），且**没有美术时间投入**，`dev/方案-Lottie动画迁移.md` 要求的 AE 制作路径走不通。
- 结论与候选路线见 → `dev/方案-动画与气泡系统设计笔记.md`（**路线未最终选定，待决策**）。

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
| P1-1 | 隐式特质抽取（每 5 轮 LLM 抽取） | 未开始 |
| P1-2 | 画像结构化按类分组显示 | 未开始 |
| **P2-1** | **idle 随机微动作** | **未开始（动画卡点的一部分）** |
| P2-2 | 鼠标视线跟随 | 未开始 |
| P2-3 | 抚摸反馈（hover > 2s → happy） | 未开始 |
| P3-1 | LLM 生成日记 | 未开始 |
| P3-2 | LLM 健康贴士 | 未开始 |
| P3-3 | 记忆存储前 LLM 提取关键信息 | 未开始 |
| E5 | 流式对话输出 | ⚠️ **代码已含流式骨架**，待真机确认是否已达"≤200ms 首字" |
| E11 | 点击穿透 | 未开始（代码中无 `setMask` / `WS_EX_TRANSPARENT`） |
| E16 | 冲突检测缓存（待确认日程参与计算） | 未开始 |
| O1 | FAISS 死向量压缩 | 未开始 |
| O2 | 对话存档 LRU 缓存 | 未开始 |
| O3 | 上下文 token 控制（回复降 max_tokens） | 未开始 |
| O4 | 启动加载并行化 | 未开始 |

**编号含义**：`P1` 个性化 · `P2` 交互 · `P3` LLM 渗透 · `E` 1.1 遗留 · `O` 性能优化。

---

## 四、已知问题

| # | 问题 | 影响 | 处置建议 |
|---|---|---|---|
| 1 | **仓库无 `.gitignore`**，`git ls-files` 达 38516 个文件，`__pycache__/*.pyc`、`data/pet.db`(含 `-wal`/`-shm`)、`dist/Vel.exe` 均被跟踪 | 仓库臃肿、每次运行都产生噪音 diff、`pet.db` 可能含隐私数据 | 补 `.gitignore`；已跟踪的垃圾文件需 `git rm --cached` 清理（**尚未执行，待确认**） |
| 2 | 目录名 `ui/resources/animations/pet_lottie'`（**结尾带单引号**） | 疑似脚本 bug 产物的脏目录，Lottie 迁移时必须清理 | 确认无引用后删除 |
| 3 | `ui/resources/animations/pet_lottie'/` 与 `pet_svg/` 并存，`animations/` 下还有孤立的 `cat_1.png` | 资源归属不清 | 随动画路线决策一并整理 |
| 4 | 情绪切换硬编码在 `main.py`（`set_emotion("thinking")` / `"idle"`） | 桌宠表情与对话内容无关 | 按 `dev/方案-LLM输出协议与情绪驱动.md` 接入协议解析器 |
| 5 | `tests/integration/` 为空 | 核心场景无集成保障 | 随模块推进补齐 |
| 6 | `llm_service.py` 内默认 `model` 与 `config/settings.yaml` 不一致 | 易误判实际模型 | 以 `settings.yaml` 为准；代码默认值仅兜底 |

---

## 五、待决策事项（**需用户拍板**）

1. **动画路线**：Live2D（`live2d-py` + 现成模型）／ SVG 部件化程序动画／维持逐帧 SVG。取舍分析见 `dev/方案-动画与气泡系统设计笔记.md`。
2. **点击穿透实现路线**：整窗穿透 + 右键守卫（快）／ `WM_NCHITTEST` 逐像素命中（工业标准）。见 `dev/方案-点击穿透E11.md`。
3. **仓库卫生清理范围**：是否执行 `git rm --cached` 移除已跟踪的 `.pyc` / `pet.db` / `dist/`。

---

## 六、当前阻塞

**无外部阻塞。** 全部待办均可自主推进；动画路线决策与穿透路线决策是推进 P2 / E11 的前置。
