# 缺陷台账 · buglist

> 一行一条，仅记概要。**新缺陷一律追加到本文件，不新建单文件**（约定见 `doc/README.md` §四 约定 4）。
> 编号规则：`V0001` 起递增。严重度：`P0` 崩溃/数据损坏 → `P1` 功能不可用 → `P2` 体验受损 → `P3` 轻微。
> 状态：`待确认` / `已定性` / `修复中` / `已修复` / `不修复`（须写原因）。

| 编号 | 日期 | 严重度 | 状态 | 概要 | 位置 |
|---|---|---|---|---|---|
| V0001 | 2026-10-08 | P2 | ✅ 已修复 | 动画资源脏目录 `pet_lottie'`（结尾多一个单引号） | `ui/resources/animations/` |
| V0002 | 2026-10-08 | P2 | ✅ 已修复 | 仓库无 `.gitignore`，`venv/` `__pycache__` `pet.db` `build/` 被跟踪（38522 个跟踪文件） | 仓库根目录 |
| V0003 | 2026-10-08 | **P1** | ⚠️ 待确认 | **`config/settings.yaml` 从未被任何代码读取**，其中全部配置（模型/超时/记忆/健康/日程/搜索/睡眠）实为死配置 | `config/settings.yaml` + `main.py:316` |
| V0004 | 2026-10-08 | **P1** | ⚠️ 待确认 | Ollama 中**无任何模型**，且 `OLLAMA_MODELS` 指向不存在的路径（`E:\dev\ollama\modals`，疑似 `models` 拼写错误） | 运行环境 |
| V0005 | 2026-10-08 | P3 | ✅ 已修复 | `config/secrets.yaml`（含真实高德 key）被 git 跟踪并入历史 | `config/secrets.yaml` |

---

## 详细说明

### V0001 · 脏目录名 ✅ 已修复（2026-10-08）

- **现象**：`ui/resources/animations/` 下存在名为 `pet_lottie'` 的目录（结尾带单引号），内容为空。
- **处置**：`grep -rn "pet_lottie"` 全仓零引用 → 确认为脚本 bug 产物 → `rmdir` 删除。
- **遗留**：`animations/` 下孤立的 `cat_1.png` 仍在，待动画实施时一并整理。

### V0002 · 仓库卫生 ✅ 已修复（2026-10-08）

- **现象**：`git ls-files | wc -l` = 38522，其中 `venv/` 占 38290、`__pycache__` 11714（含 venv 内）、`build/` 14、`data/pet.db`、`config/secrets.yaml`、`.idea/` 5。
- **处置**：
  1. 新增 `.gitignore`（54 行，六类规则经 `git check-ignore` 验证）；
  2. `git rm --cached` 解绑全部运行时产物 → 跟踪文件 **38522 → 158**；
  3. 磁盘文件全部保留（`venv/`、`build/`、`pet.db`、`secrets.yaml` 均在原处）。
- **影响**：此后运行程序不再产生噪音 diff；`pet.db` 与密钥不再入库。

### V0003 · 配置文件从未生效 ⚠️ 待确认（**P1**）

- **现象**：`grep -rn "settings.yaml" --include=*.py` **零命中** —— 项目代码从未读取 `config/settings.yaml`。
- **实际生效值**：`main.py:316` 硬编码
  ```python
  self._llm_service = LLMService(model="qwen2.5:7b", timeout=60, max_tokens=512)
  ```
- **不一致点**：

  | 配置项 | `config/settings.yaml` | `main.py` 实际生效 |
  |---|---|---|
  | 模型 | `qwen2.5:7b-instruct-q4_K_M` | `qwen2.5:7b` |
  | 超时 | `30` | `60` |
  | max_tokens | `2048` | `512` |

- **影响**：用户改配置**不会产生任何效果**；记忆参数（`decay_half_life_days` / `summary_interval`）、健康间隔、日程偏移、搜索缓存、睡眠时段等全部走代码内默认值。
- **待确认**：是"配置加载器尚未实现"，还是曾实现后被移除？
- **方向**：需要一个配置加载模块（读 yaml → 供各 service 注入），属**功能开发**，非卫生清理，需单独排期。
- **附带修正**：待办 `O3`（上下文 token 控制）实际**已在 `main.py` 以硬编码形式部分实现**（`max_tokens=512`），原状态"未开始"有误。

### V0004 · 无可用 LLM 模型 ⚠️ 待确认（**P1**，环境问题）

- **现象**：`ollama list` 返回空列表（仅表头 `NAME ID SIZE MODIFIED`）。
- **日志证据**：
  ```
  msg="models path not accessible, using default" path=E:\dev\ollama\modals
  err="GetFileAttributesEx E:\dev\ollama\modals: The system cannot find the path specified."
  ```
- **推断**：环境变量 `OLLAMA_MODELS` 被设为 `E:\dev\ollama\modals`（**`modals` 疑似 `models` 拼写错误**），该路径不存在 → Ollama 回退默认目录，而默认目录中也没有模型。
- **影响**：`LLMService.check_connection()` 会失败 → 对话降级为预设回复（`llm_service` 中 `_fallback_replies`）。**即当前 LLM 功能实际不可用。**
- **方向**：修正环境变量路径后 `ollama pull qwen2.5:7b-instruct-q4_K_M`；随后需统一 V0003 的模型名口径。
- **注**：Ollama 版本 0.24.0，检测到有新版 0.40.1。

### V0005 · 密钥入库 ✅ 已修复（2026-10-08）

- **现象**：`config/secrets.yaml` 含真实高德 key（32 位十六进制），已在 `first commit` 中；远端为 `github.com/west0006/Vel.git`。
- **处置**：① 用户已在控制台删除该高德 key；② `git rm --cached config/secrets.yaml` 解绑；③ 新增 `config/secrets.example.yaml` 模板。
- **⚠️ 残留风险**：该 key 文本**仍存在于 git 历史**（含远端历史，若曾推送）。因 key 已失效，风险降为可接受。**Bing key 为中文占位符（含"你的"），非真实密钥**，代码会自动降级到 DuckDuckGo。
- **验证**：`services/location_service._load_api_key()` 与 `services/search_service._load_config()` 均为 `try/except` 容错，文件缺失只降级不崩溃。
