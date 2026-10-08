# 缺陷台账 · buglist

> 一行一条，仅记概要。**新缺陷一律追加到本文件，不新建单文件**（约定见 `doc/README.md` §四 约定 4）。
> 编号规则：`V0001` 起递增。严重度：`P0` 崩溃/数据损坏 → `P1` 功能不可用 → `P2` 体验受损 → `P3` 轻微。
> 状态：`待确认` / `已定性` / `修复中` / `已修复` / `不修复`（须写原因）。

| 编号 | 日期 | 严重度 | 状态 | 概要 | 位置 |
|---|---|---|---|---|---|
| V0001 | 2026-10-08 | P2 | 待确认 | 动画资源目录名 `pet_lottie'` 结尾多一个单引号，疑似脚本 bug 产物 | `ui/resources/animations/` |
| V0002 | 2026-10-08 | P2 | 待确认 | 仓库无 `.gitignore`，`__pycache__` / `pet.db` / `dist` 被 git 跟踪（38516 个跟踪文件） | 仓库根目录 |
| V0003 | 2026-10-08 | P3 | 待确认 | `llm_service.py` 内默认模型名与 `config/settings.yaml` 不一致，易误判实际模型 | `services/llm_service.py` |

---

## 详细说明

### V0001 · 脏目录名

- **现象**：`ui/resources/animations/` 下存在名为 `pet_lottie'` 的目录（结尾带单引号），且为空。
- **影响**：Lottie 迁移时若按约定路径 `pet_lottie/` 写入，会与脏目录并存；打包时可能被一起收进去。
- **待确认**：是否有代码/脚本引用该名称（含快照、`build.spec`）。
- **方向**：确认无引用后删除；同时整理 `animations/` 下孤立的 `cat_1.png`。

### V0002 · 仓库卫生

- **现象**：`git ls-files | wc -l` = 38516，其中包含 `core/__pycache__/*.pyc`、`modules/**/__pycache__/*.pyc`、`data/pet.db`、`data/pet.db-wal`、`data/pet.db-shm`、`dist/Vel.exe`。
- **影响**：① 每次运行程序都产生噪音 diff；② `pet.db` 含用户对话与画像数据，不应入库；③ 仓库体积虚高。
- **方向**：补 `.gitignore` + `git rm --cached` 清理已跟踪的运行时产物（**需用户确认后执行**，见 `CURRENT-STATUS.md` §五 待决策 3）。

### V0003 · 模型名不一致

- **现象**：`config/settings.yaml` 为 `qwen2.5:7b-instruct-q4_K_M`，而 `services/llm_service.py` 的构造参数默认值为另一模型名。
- **影响**：排障时容易误判"实际用的是哪个模型"。
- **方向**：以 `config/settings.yaml` 为准；把代码默认值改为与配置一致，或标注"仅兜底"。
