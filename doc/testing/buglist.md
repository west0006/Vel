# 缺陷台账 · buglist

> 一行一条，仅记概要。**新缺陷一律追加到本文件，不新建单文件**（约定见 `doc/README.md` §四 约定 4）。
> 编号规则：`V0001` 起递增。严重度：`P0` 崩溃/数据损坏 → `P1` 功能不可用 → `P2` 体验受损 → `P3` 轻微。
> 状态：`待确认` / `已定性` / `修复中` / `已修复` / `不修复`（须写原因）。

| 编号 | 日期 | 严重度 | 状态 | 概要 | 位置 |
|---|---|---|---|---|---|
| V0001 | 2026-10-08 | P2 | ✅ 已修复 | 动画资源脏目录 `pet_lottie'`（结尾多一个单引号） | `ui/resources/animations/` |
| V0002 | 2026-10-08 | P2 | ✅ 已修复 | 仓库无 `.gitignore`，`venv/` `__pycache__` `pet.db` `build/` 被跟踪（38522 个跟踪文件） | 仓库根目录 |
| V0003 | 2026-10-08 | **P1** | ✅ 已修复 | `config/settings.yaml` 从未被任何代码读取，其中配置实为死配置；且配置源分裂（`app_settings` 生效 / yaml 不生效） | `config/settings.yaml` · `core/config.py` |
| V0004 | 2026-10-08 | **P1** | ⏸ 用户自理 | Ollama 中无任何模型，且 `OLLAMA_MODELS` 指向不存在的路径（`E:\dev\ollama\modals`，疑似 `models` 拼写错误） | 运行环境 |
| V0005 | 2026-10-08 | P3 | ✅ 已修复 | `config/secrets.yaml`（含真实高德 key）被 git 跟踪并入历史 | `config/secrets.yaml` |
| V0006 | 2026-10-08 | P3 | ✅ 已修复 | `cat_1.png`（1024×1024、1.25MB）全仓无引用的孤立素材，占用仓库体积 | `ui/resources/animations/` |

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

### V0004 · 无可用 LLM 模型 ⏸ 用户自理（2026-10-08）

- **现象**：`ollama list` 返回空列表。
- **日志证据**：
  ```
  msg="models path not accessible, using default" path=E:\dev\ollama\modals
  err="GetFileAttributesEx E:\dev\ollama\modals: The system cannot find the path specified."
  ```
- **推断**：`OLLAMA_MODELS` 被设为 `E:\dev\ollama\modals`（疑似 `models` 拼写错误），路径不存在 → 回退默认目录，默认目录中也无模型。
- **影响**：`check_connection()` 失败 → 对话降级为预设回复。
- **处置**：**用户决定自行处理**（2026-10-08："ollama 需手动启动不管"）。修正环境变量后需 `ollama pull qwen2.5:7b-instruct-q4_K_M`（该名称已随 V0003 统一为 `settings.yaml` 的口径）。

### V0005 · 密钥入库 ✅ 已修复（2026-10-08）

- **处置**：用户已删除高德 key + `git rm --cached config/secrets.yaml` + 新增 `config/secrets.example.yaml` 模板。
- **⚠️ 残留**：key 文本仍在 git 历史中（含远端历史，若曾推送）；因已失效，风险可接受。

### V0006 · 孤立素材 cat_1.png ✅ 已修复（2026-10-08）

- **现象**：`ui/resources/animations/cat_1.png`（1024×1024 RGBA、1.25MB）全仓无引用（`grep -rn "cat_1"` 零命中），却随仓库分发。
- **处置**：按用户决策采用 **pet.db 同策略** —— `git rm --cached` 解绑 + 加入 `.gitignore`，**磁盘文件保留**（可能是形象素材，将来动画实施可能用得上）。
