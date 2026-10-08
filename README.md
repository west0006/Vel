# Vel · 智能AI桌宠

> 一只住在 Windows 桌面上的猫系 AI 陪伴宠物 —— 本地大模型对话、长期记忆、日程提醒、健康管理、联网搜索与附近推荐。
>
> **所有 AI 能力本地运行，用户数据不出本机**；仅联网搜索与位置服务使用已批准的免费层 API（Bing / 高德），并带完整降级链。

---

## 快速开始

### 环境要求

| 项 | 要求 |
|---|---|
| 系统 | Windows 10 / 11 x64（仅桌面端） |
| Python | 3.11 |
| 大模型 | 本地 [Ollama](https://ollama.com/)（需自行启动） |

### 安装

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置密钥（按需，可留空）
cp config/secrets.example.yaml config/secrets.yaml

# 3. 准备本地模型（模型名见 config/settings.yaml 的 llm.model）
ollama pull qwen2.5:7b-instruct-q4_K_M

# 4. 启动
python main.py
```

> **密钥留空也能跑**：`gaode.api_key` 为空 → 位置服务自动禁用；`bing.api_key` 为空 → 搜索直接走 DuckDuckGo 降级链。

---

## 目录结构

```
├─ main.py                    应用入口与装配（启动顺序、服务注册、快捷键）
├─ core/                      事件总线 · 状态机 · 服务注册 · 模型管理 · 统一配置
├─ services/                  LLM · 记忆 · 搜索 · 位置 · OCR · 语音 · 更新
├─ modules/                   业务模块：chat · schedule · health · personality
│                             · diary · memo · habit · pomodoro · greeting · onboarding
├─ ui/                        悬浮窗 · 对话气泡 · 通知气泡 · 设置面板 · 系统托盘
├─ utils/                     日志 · 加密 · 系统信息
├─ tests/                     单元测试（pytest）
├─ config/                    settings.yaml（出厂默认）· secrets.example.yaml（密钥模板）
├─ doc/                       开发档案：权威设计 · 方案 · 调研 · 台账
└─ data/                      运行时数据（pet.db · faiss.index，**不入库**）
```

---

## 配置

配置有两层，**优先级从高到低**：

| 层 | 位置 | 用途 |
|---|---|---|
| 用户修改 | SQLite `app_settings` 表 | 运行时改动（设置面板写入），经 `core/config.py` 读取 |
| 出厂默认 | `config/settings.yaml` | 模型、超时、记忆、健康、日程、搜索、睡眠等默认值 |
| 代码兜底 | 各调用点传入的 `default` | 前两层都缺失时的最后防线 |

统一入口是 `core/config.py` 的 `config` 单例：

```python
from core.config import config
timeout = config.get_int("llm.timeout", 60)      # 点号路径对应 settings.yaml 的嵌套结构
model   = config.get_str("llm.model")
config.set("llm.timeout", 90)                     # 写入 app_settings（用户修改层）
```

> 键名规范为 `settings.yaml` 的嵌套路径（如 `health.drink_target_ml`）。早期 `app_settings` 中的历史键名（`drink_daily_target_ml`、`sleep_start` 等）由 `core/config.py` 内部别名表兼容。

---

## 开发

```bash
# 回归测试（提交前必须全绿）
.venv/Scripts/python.exe -m pytest tests -q

# 打包（PyInstaller）
pyinstaller build.spec
```

**提交约定**：先建基线 → 改动后跑回归 → 全绿才提交 → 小步提交形成可回退节点。
完整规范见 [`AGENTS.md`](AGENTS.md)。

---

## 文档

| 入口 | 内容 |
|---|---|
| [`doc/README.md`](doc/README.md) | 文档仓入口与维护约定 |
| [`doc/CURRENT-STATUS.md`](doc/CURRENT-STATUS.md) | **工作现状快照**（在做什么 / 做到哪 / 有哪些问题） |
| [`doc/reference/`](doc/reference/) | 权威设计文档 |
| [`doc/dev/`](doc/dev/) | 实施方案与计划 |
| [`doc/testing/buglist.md`](doc/testing/buglist.md) | 缺陷台账 |
| [`AGENTS.md`](AGENTS.md) | AI 协作规范（技术栈约束、任务路由、验证与提交） |
