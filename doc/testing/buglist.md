# 缺陷台账 · buglist

> 一行一条，仅记概要。**新缺陷一律追加到本文件，不新建单文件**（约定见 `doc/README.md` §四 约定 4）。
> 编号规则：`V0001` 起递增。严重度：`P0` 崩溃/数据损坏 → `P1` 功能不可用 → `P2` 体验受损 → `P3` 轻微。
> 状态：`待确认` / `已定性` / `修复中` / `已修复` / `不修复`（须写原因）。

| 编号 | 日期 | 严重度 | 状态 | 概要 | 位置 |
|---|---|---|---|---|---|
| V0001 | 2026-10-08 | P2 | ✅ 已修复 | 动画资源脏目录 `pet_lottie'`（结尾多一个单引号） | `ui/resources/animations/` |
| V0002 | 2026-10-08 | P2 | ✅ 已修复 | 仓库无 `.gitignore`，`venv/` `__pycache__` `pet.db` `build/` 被跟踪（38522 个跟踪文件） | 仓库根目录 |
| V0003 | 2026-10-08 | **P1** | ✅ 已修复 | `config/settings.yaml` 从未被任何代码读取，其中配置实为死配置；且配置源分裂（`app_settings` 生效 / yaml 不生效） | `config/settings.yaml` · `core/config.py` |
| V0004 | 2026-10-08 | — | ✅ 撤回（非缺陷） | `ollama list` 为空：模型存于移动硬盘（未挂载时读不到），**用户已实测对话可用** | 运行环境 |
| V0005 | 2026-10-08 | P3 | ✅ 已修复 | `config/secrets.yaml`（含真实高德 key）被 git 跟踪并入历史 | `config/secrets.yaml` |
| V0006 | 2026-10-08 | P3 | ✅ 已修复 | `cat_1.png`（1024×1024、1.25MB）全仓无引用的孤立素材，占用仓库体积 | `ui/resources/animations/` |
| V0007 | 2026-10-08 | **P1** | ✅ 已修复 | `llm_service` 进入降级模式后**永不恢复** —— Ollama 重启/模型重载后仍走预设回复，直到重启程序 | `services/llm_service.py` |
| V0008 | 2026-10-08 | P2 | ✅ 已修复 | 42 处 `except ...: pass` 静默吞异常（违反 AGENTS.md §4.4），故障无任何线索 | 19 个文件 |
| V0009 | 2026-10-08 | **P1** | ✅ 已修复 | `EventBus.subscribe_ui` 不创建 `UiSignals`：若首次 publish 来自后台线程，Qt 对象绑定到该线程，UI 事件投递到无事件循环的线程 → **回调永不执行** | `core/event_bus.py` |
| V0010 | 2026-10-08 | **P1** | ✅ 已修复 | `core/config.py` 别名表缺 `health.*` 映射：schema 与用户数据中的无前缀键（`drink_interval_min`/`sedentary_threshold_min`/`active_hours_*`）**读不到**且 `set()` 后不更新 | `core/config.py` · `data/db/schema.sql` |
| V0011 | 2026-10-08 | P3 | ✅ 已修复 | `update_service` 版本号双源（方法内硬编码 vs `settings.yaml` 的 `app.version`）+ `__init__` 日志谎称"已注册"（实际从未被接线） | `services/update_service.py` |

---

## 详细说明

### V0001 · 脏目录名 ✅ 已修复（2026-10-08）

- **现象**：`ui/resources/animations/` 下存在名为 `pet_lottie'` 的目录（结尾带单引号），内容为空。
- **处置**：`grep -rn "pet_lottie"` 全仓零引用 → 确认为脚本 bug 产物 → `rmdir` 删除。

### V0002 · 仓库卫生 ✅ 已修复（2026-10-08）

- **现象**：`git ls-files | wc -l` = 38522（`venv/` 38290、`__pycache__` 11714、`build/` 14、`data/pet.db`、`config/secrets.yaml`、`.idea/` 5）。
- **处置**：新增 `.gitignore`（六类规则经 `git check-ignore` 验证）+ `git rm --cached` 解绑 → 跟踪文件 **38522 → 159**；磁盘文件全部保留。

### V0003 · 配置源分裂 ✅ 已修复（2026-10-08）

- **现象（修复前）**：
  - `grep -rn "settings.yaml" --include=*.py` **零命中** —— 代码从未读取 `config/settings.yaml`；
  - 实际生效的是 `main.py:316` 硬编码 `LLMService(model="qwen2.5:7b", timeout=60, max_tokens=512)`；
  - 同时 `app_settings` 表（17 个键）**确实在用**，但只有 `drink_reminder` / `sedentary_monitor` 各自实现了私有的 `_get_setting_int`；
  - **键名两套且不一致**：yaml `health.drink_target_ml` vs 表中 `drink_daily_target_ml`；yaml `sleep.start` vs 表中 `sleep_start`；
  - **模型名四处打架**：`settings.yaml`=`qwen2.5:7b-instruct-q4_K_M`、`main.py`=`qwen2.5:7b`、`llm_service.py` 默认=`gemma4:latest`、嵌入模型 yaml 声明 384 维 vs 代码 768 维。

- **处置**：新增 `core/config.py` 统一配置模块，三层优先级 **`app_settings`（用户修改） > `config/settings.yaml`（出厂默认） > 代码兜底**：
  - 键名规范统一为 yaml 的点号路径；历史键名由 `_DB_KEY_ALIASES` 别名表兼容（写入时同步双写）；
  - 惰性加载 + 全链路容错（yaml 缺失/损坏、db 未绑定、类型转换失败一律回退默认值）；
  - 接入点：`main.py`（LLM 8 个参数 + Memory 路径）、`services/search_service.py`（`bing_timeout`/`bing_monthly_limit`）、`services/location_service.py`（`gaode_daily_limit`/`cache_ttl_location`）、`services/memory_service.py`（ST 回退模型名）、`modules/health/` 两模块（私有读取方法改走统一入口）。
  - 随附：`settings.yaml` 的 `llm.max_tokens` 2048 → **512**（固化待办 O3 的优化决策）、`llm.timeout` 30 → **60**（冷启动首次请求会触发模型加载）。
  - 单测：`tests/unit/test_config.py` 24 项（yaml 读取 / 类型转换 / 覆盖优先级 / 别名兼容 / 异常回退 / 写入）。
  - 回归：`pytest tests -q` → **66 passed**（42 原有 + 24 新增）。

- **遗留（第二批，未接入）**：`schedule.*`（`reminder_offset_min` / `instance_window_months`）、`window.*`（`pet_size*`）、`memory.decay_half_life_days` / `memory.summary_interval` 仍走代码内默认值。

### V0004 · 无可用 LLM 模型 ✅ 撤回（非缺陷，2026-10-08 用户澄清）

- **原判断**：`ollama list` 返回空列表 + 日志 `models path not accessible, using default path=E:\dev\ollama\modals` → 推断"无模型、疑似路径拼写错误"。
- **实际情况（用户澄清）**：模型存放于**移动硬盘**（`E:\dev\ollama\...`），当时未挂载故读不到；**对话功能已由用户实测验证可用**。
- **教训**：`ollama list` 为空 ≠ 功能不可用 —— 模型目录可位于可移动设备。判断"功能不可用"前应以**端到端实测**为准，不能仅凭列表为空下结论。
- **对 V0003 的连带修正**：原本担心的"模型名口径不一致会导致拉不到模型"风险不成立 —— 实际使用的模型以用户硬盘上的为准；`settings.yaml` 的口径仍作为**配置与文档的单一来源**保留。

### V0005 · 密钥入库 ✅ 已修复（2026-10-08）

- **处置**：用户已删除高德 key + `git rm --cached config/secrets.yaml` + 新增 `config/secrets.example.yaml` 模板。
- **⚠️ 残留**：key 文本仍在 git 历史中（含远端历史，若曾推送）；因已失效，风险可接受。

### V0007 · LLM 降级不可恢复 ✅ 已修复（2026-10-08，P1）

- **现象**：`services/llm_service.py` 的 `generate()` 开头为
  ```python
  if self._is_degraded:
      return self._get_fallback_reply()   # 直接返回，不再尝试真实调用
  ```
  → 一旦连续 3 次失败进入降级，**永远不会再请求 Ollama**。
- **影响**：Ollama 重启、模型重载、网络恢复后，桌宠仍持续输出预设回复（"喵…我好像有点卡住了"），**必须重启程序才能恢复**。
- **修法**：新增恢复探测 —— 降级期间每 `_degrade_probe_interval`（默认 5）次生成尝试一次真实调用；成功即退出降级并重置计数，失败则计数器归零、下个周期再试。
- **测试**：`tests/unit/test_llm_service.py::TestRecoveryProbe` 3 项覆盖（探测点前不调用底层 / 探测成功退出降级 / 探测失败保持降级）。

### V0008 · 静默吞异常 ✅ 已修复（2026-10-08，P2）

- **现象**：全仓 **42 处** `except ...: pass`，分布 19 个文件（`ui/settings_window.py` 10 处、`services/location_service.py` 6 处、`modules/greeting.py` 5 处、`services/search_service.py` 4 处 …）。
- **影响**：违反 AGENTS.md §4.4「严禁裸 `except:` 与静默吞异常，最低限度 `logger.exception()`」；天气获取、设置读写、模型探测等失败**全部无日志**，排障无线索。
- **修法**：统一改为 `logger.exception("<函数名> 执行失败")`（保留原 except 子句与缩进，消息含函数名便于定位）；`ui/theme.py` 原缺 logger，补齐 `get_logger` 引入。
- **验证**：`except:pass` 归零 · `compileall` 通过 · **57 个生产模块逐个 import 冒烟 0 失败** · 全量回归 154 passed。

- **现象**：`ui/resources/animations/cat_1.png`（1024×1024 RGBA、1.25MB）全仓无引用（`grep -rn "cat_1"` 零命中），却随仓库分发。
- **处置**：按用户决策采用 **pet.db 同策略** —— `git rm --cached` 解绑 + 加入 `.gitignore`，**磁盘文件保留**（可能是形象素材，将来动画实施可能用得上）。

### V0009 · UI 事件投递可能永久失效 ✅ 已修复（2026-10-08，P1）

- **发现途径**：`tests/integration/test_event_bus_flow.py` 的 UI 投递用例（后台线程 publish → 断言回调在主线程执行）失败。
- **缺陷**：`UiSignals` 是**惰性创建**的（首次 `publish` 时才建）。若第一次发布 UI 事件时正处于后台线程，Qt 对象会绑定到该线程；`QueuedConnection` 便把事件投递到**没有事件循环的后台线程** → UI 回调永远不执行，且无任何报错。
- **实际影响**：正常启动流程中通常先由主线程 `subscribe_ui`（隐患不暴露），但「先 publish 后订阅」或「首次 publish 来自子线程」的时序下会静默失效 —— 属难以排查的偶发问题。
- **修法**：在 `subscribe_ui()` 内即调用 `_get_ui_signals()`，让信号对象在**订阅线程（通常为主线程）**创建，保证线程亲和性正确。

### V0010 · 配置别名缺失导致用户数据读写失效 ✅ 已修复（2026-10-08，P1）

- **发现途径**：`tests/integration/test_database_config.py` 的写入回读用例（`set()` 后检查 db 中的历史键）失败。
- **缺陷**：`_DB_KEY_ALIASES` 只登记了 `health.drink_target_ml`、`sleep.*`、`search.*`，**缺少** `health.drink_interval_min` / `health.sedentary_threshold_min` / `health.active_hours_start` / `health.active_hours_end` 到无前缀键的映射。
- **影响**：`data/db/schema.sql` 与用户实际数据里存的是无前缀键（`drink_interval_min` 等），而代码读的是规范键 → **读不到就静默回退 yaml 默认值**（因两者数值恰好相同，问题长期未暴露）；用户手工改库中的无前缀键也不会生效，`config.set()` 亦不会更新旧键。
- **修法**：补齐 4 条别名映射；`set()` 仍保持「规范键 + 别名双写」。

### V0011 · 更新服务的版本号双源与误导日志 ✅ 已修复（2026-10-08，P3）

- **发现途径**：盘点 Q5 时核实 `services/update_service.py`（48 行占位骨架）。
- **问题 1 · 版本号双源**：`get_current_version()` 兜底硬编码 `"0.1.0-alpha"`，与 `config/settings.yaml` 的 `app.version` 各存一份 → 改一处忘另一处即不一致，且调用方无法判断来源。
  **修法**：统一优先级为「`update_info` 表 > `settings.yaml` 的 `app.version` > `FALLBACK_VERSION` 常量」。
- **问题 2 · 误导日志**：`__init__` 打印"更新服务已注册（暂未启用，阶段6实现）"，但该服务**从未被 `main.py` 注册**（全仓无引用）→ 排障时会误以为已接线。
  **修法**：改为"更新服务已实例化（占位骨架，未接线）"，并在模块 docstring 声明"本服务不会被 main.py 注册"。
- **附带澄清**：本模块**不是"接线遗漏"**，而是设计文档 §4.8 / §9.5 规划的**阶段7功能，目前仅占位**（用户 2026-10-08 决策：暂不实现）。已同步更正 `doc/dev/盘点-质量与生态现状.md` 的 Q5 定性（规模由"中"更正为"大"）。
- **测试**：`tests/unit/test_update_service.py` 11 项，其中 `test_main_does_not_register_update_service` 锁定"未接线"决策 —— 将来若要接线，必须先实现功能并更新该测试与文档。
