# Vel 智能AI桌宠 — AI 工作规范

> 本文件是 Agent 每次任务开始时的**唯一入口**。规范冲突时，以更具体、更新的条目为准。
> 最后更新：2026-10-08（对齐 doc/ 文档工作区与"验证后提交节点"工作流）

---

## 〇、开始任何任务前（必读顺序）

1. 读 `doc/README.md` —— 文档入口与维护约定（含目录结构、命名规范、归档规则）。
2. 读 `doc/CURRENT-STATUS.md` —— **工作现状快照**：在做什么 / 做到哪 / 有哪些问题。
3. 需要设计依据时读 `doc/reference/设计-项目详细设计-Vel v1.1.md`（**唯一权威设计文档**）。
4. 需要动动画/交互前读 `doc/reference/设计-像素猫动画规格-v2.1.md`；动 UI 前读 `doc/reference/设计-UI交互补充规格.md`。
5. **不要凭记忆或历史对话猜测项目现状** —— 现状只以本仓库的代码与 `doc/` 为准。

> 历史设计文档中记录的"计划要做"不等于"已经做了"。动手前用代码核实。

---

## 一、项目定位与硬性约束

### 1.1 定位

Windows 10/11 x64 单人内测的拟人化猫系 AI 桌宠。提供长期记忆对话、日程提醒、健康管理、联网搜索、LBS 推荐。**不做公开发行、不做跨端、不做云端。**

### 1.2 技术栈（不可变更）

| 层级 | 绑定技术 | 现状落地位置 |
|---|---|---|
| 桌面框架 | PyQt5 5.15.x | `ui/`、`main.py` |
| 大语言模型 | Ollama + Qwen2.5:7b-instruct-q4_K_M | `services/llm_service.py` |
| 数据库 | SQLite 3（WAL 模式） | `data/pet.db`、`data/db/schema.sql` |
| 向量记忆 | FAISS + sentence-transformers（384 维） | `services/memory_service.py` |
| 事件系统 | 自研 EventBus（sync/async/UI 线程安全） | `core/event_bus.py` |
| 调度 | APScheduler（QtScheduler） | `main.py`、`modules/schedule/` |
| 加密 | AES（应用层）+ DPAPI（密钥保护） | `utils/crypto.py` |
| 语音识别/合成 | faster-whisper / TTS（**Alpha 仅留接口，UI 不露出**） | `services/stt_service.py`、`services/tts_service.py` |
| OCR | PaddleOCR（GPU）+ Tesseract 备用 | `services/ocr_service.py` |
| 位置 / 搜索 | 高德 API（免费层）/ Bing → SearXNG → DuckDuckGo 降级链 | `services/location_service.py`、`services/search_service.py` |
| 打包 | PyInstaller + 启动器式更新 | `build.spec`、`services/update_service.py` |
| 桌宠形象/动画 | **像素猫** + SVG 部件分层程序动画（**不引入 Live2D/OpenGL，不做 Lottie、不做骨骼动画**） | `ui/floating_pet.py`、`ui/resources/animations/pet_svg/` |

模型名以 `config/settings.yaml` 为准；代码内默认值（如 `llm_service.py` 的 `model` 参数）**只是兜底，不得作为依据**。

### 1.3 禁止引入

- ❌ 任何云 AI 服务（OpenAI / Claude / 百度 AI 等）—— 唯一例外是已批准的 Bing 搜索与高德地图免费层。
- ❌ Electron / CEF / Tauri / Godot 等非 PyQt5 UI 框架。
- ❌ 付费商业库或 API。
- ❌ 未在本节列出的新依赖 —— 需用户明确同意后方可引入。
- ❌ 把用户数据（含日志）发送到任何远程服务器。

---

## 二、任务路由表（改哪里）

| 要做的任务 | 首选位置 |
|---|---|
| 应用装配、启动顺序、服务注册、全局快捷键 | `main.py` |
| 事件定义、发布订阅、跨线程 UI 投递 | `core/event_bus.py`、`core/state_manager.py` |
| 服务注册与查找 | `core/service_registry.py` |
| 模型加载/卸载/显存预算 | `core/model_manager.py` |
| 对话编排、上下文窗口、流式回调 | `modules/chat/chat_manager.py` |
| 人格提示词、记忆注入、输出协议 | `modules/chat/prompt_builder.py` |
| 日程解析/重复规则/调度/存储 | `modules/schedule/` |
| 健康提醒（饮水/久坐/用餐/睡眠/情绪） | `modules/health/` |
| 用户画像抽取、遗忘曲线、档案管理 | `modules/personality/` |
| 引导向导 | `modules/onboarding/wizard.py` |
| 日记 / 备忘录 / 习惯 / 番茄钟 / 问候 / 彩蛋 | `modules/*.py` |
| LLM / 记忆 / 搜索 / 位置 / OCR / 语音 / 更新 服务 | `services/*.py` |
| 工具调用编排 | `services/tool_executor.py` |
| 桌宠窗口、帧动画、拖拽、贴边、交互 | `ui/floating_pet.py` |
| 对话气泡、流式打字机显示 | `ui/chat_bubble.py` |
| 通知气泡与优先级排队 | `ui/notification_bubble.py` |
| 设置面板 / 托盘 / 主题 / 字体 | `ui/settings_window.py`、`ui/system_tray.py`、`ui/theme.py` |
| 日志、加密、系统信息 | `utils/` |
| 数据库表结构变更 | 必须新增 `data/db/migrations/` SQL 脚本，并同步 `data/db/schema.sql` |
| 单元测试 | `tests/unit/`（每完成一个模块必须同步补） |

---

## 三、分层与依赖边界

依赖只允许**向下**流动：

```
ui/  ──►  modules/  ──►  services/  ──►  core/  ──►  utils/
 ▲                                          │
 └──────────────  EventBus (发布/订阅)  ─────┘
```

- `core/`、`utils/` 不得依赖 `ui/`、`modules/`、`services/`。
- `services/` 不得依赖 `ui/`、`modules/`（服务层是被编排者，不是编排者）。
- 模块之间**禁止直接互相 import 调用**，一律通过 `core.event_bus.bus` 通信。
- 禁止在根目录堆砌脚本；新模块必须按上述结构放置。
- 新事件必须在 `core/event_bus.py` 登记（含 `UiSignals` 中所需的 `pyqtSignal`），并在 `doc/reference/` 中记录生产者与订阅者。

---

## 四、编码规范

1. **PEP8**，4 空格缩进；函数参数与返回值**尽量标注类型**；类与公有方法必须有中文 docstring。
2. **日志**一律走 `utils.logger.get_logger(__name__)`；生产代码禁止 `print()`。
3. **线程与 UI 安全（最高优先级）**：
   - 任何非主线程**绝对不可**直接操作 UI 控件；
   - 跨线程更新 UI 必须经 `EventBus.subscribe_ui` 或 `QMetaObject.invokeMethod` 或信号槽；
   - 耗时操作（模型推理、HTTP 请求、OCR）必须异步化；
   - UI 线程单次阻塞不得超过 200ms。
4. **错误处理**：
   - 所有外部调用（Ollama、requests、OCR 等）必须 `try...except` 并记录；
   - 严禁裸 `except:` 与静默吞异常，最低限度 `logger.exception()`；
   - 遵循降级原则：LLM 失败 → 预设回复；搜索失败 → 降级链；模型加载超时 → 跳过。
5. **数据库**：
   - 统一 WAL 模式连接；
   - 敏感字段（`user_profile.value`、`episodic_memory.summary`）读写必须经 `utils/crypto.py`；
   - 表结构变更必须留 migration SQL。
6. **配置**：默认值放 `config/`；用户修改写 `app_settings` 表；密钥放 `config/secrets.yaml`（**绝不进 git**，首次配置从 `config/secrets.example.yaml` 复制）。缺少 `secrets.yaml` 时相关服务自动降级（位置服务不可用 / 搜索走 DuckDuckGo），**不会崩溃**。

---

## 五、验证与提交（**每个任务必须遵守**）

> 目的：让任何一次改动都可回退，避免"改崩了没有节点可退"。

1. **改动前建基线**：` .venv/Scripts/python.exe -m pytest tests -q `，确认当前是绿的（记录通过数）。
2. **改动后跑回归**：重新执行同一命令。
3. **必须全绿才提交**：
   - 通过 → `git add -A && git commit`，形成存档节点；
   - 不通过 → 修好或回滚，**严禁提交红状态**。
4. **小步提交**：一个可独立回退的改动一个节点，不要攒一大批一起提交。
5. **提交信息格式**：`<类型>: <做了什么>`，类型取 `feat` / `fix` / `refactor` / `docs` / `test` / `chore`。示例：
   - `docs: z.document 更名 doc 并重构文档工作区规范`
   - `feat: 桌宠输出协议解析器接入流式对话`
6. **改到 UI / 线程 / DB 时**，除单元测试外必须真机跑一次 `python main.py` 肉眼确认。
7. **不再使用"只读磁盘"约定** —— Agent 可直接修改本仓库文件，但必须满足本节 1~4 条；改动完成后在回复中报告：改了什么、跑了什么命令、结果如何。

---

## 六、文档工作区规范（`doc/`）

完整约定见 `doc/README.md`。要点：

- **doc/ 与代码同仓管理**（`z.document/` 已更名 `doc/`，git 历史保留）。
- 分层：`reference/`（长期结论，最可信）、`dev/`（拿来干活的：方案/计划/日志）、`knowledge/`（按日期累积的调研）、`testing/`、`历史对话/`、`归档/`（被取代的旧文档，标注"不要据以开发"）。
- **`doc/README.md` 是文档入口**，`doc/CURRENT-STATUS.md` 是现状快照，两者必须随重大改动同步更新。
- 命名：`设计-*` / `方案-*` / `计划-*` / `调研-*` / `审核报告-*` / 日志与调研按 `YYYY-MM-DD.md`；同日同类追加同一文件，不新建。
- **被新文档取代的旧文档必须移入 `归档/`**，并在归档说明中写清版本链与取代关系，禁止悄悄删除。

---

## 七、功能边界（不要过度设计）

- 设计文档标记为"可选""后续扩展"的，当前阶段**不得实现**。
- 不得添加文档未提及的新功能模块；新增需求必须由用户明确确认。
- Alpha 版裁剪（保持）：
  - 语音识别、TTS 仅保留接口，UI 不露出；
  - OCR 仅用灰度化 + 缩放，高级预处理默认关闭；
  - 个性化引擎先用规则 + SQLite 键值对，暂不启用高级检索；
  - 桌宠形象固定为**像素猫**；动画采用 **SVG 部件分层 + 代码程序驱动**（`body/ears/tail/eyes` 四层 + `QPropertyAnimation` + `QTimer`），**不引入 Live2D/OpenGL**、不做 Lottie、不做骨骼动画。详见 `doc/CURRENT-STATUS.md` §六 决策记录 D-001。

---

## 八、禁止行为清单

- 🚫 在非 UI 线程直接操作 UI 控件。
- 🚫 忽略异常或使用裸 `except:` 而不记录日志。
- 🚫 引入未列在 §1.2 的新依赖（未经用户同意）。
- 🚫 使用付费 API 或闭源模型。
- 🚫 将用户数据（含日志）发送到远程服务器。
- 🚫 添加超出当前阶段范围的功能。
- 🚫 提交未通过回归验证的状态。
- 🚫 把密钥、`pet.db`、模型权重、`__pycache__` 等运行时产物提交进仓库。
- 🚫 擅自修改 `doc/reference/` 中的权威设计文档而不留修订记录 —— 设计变更须先与用户确认。
