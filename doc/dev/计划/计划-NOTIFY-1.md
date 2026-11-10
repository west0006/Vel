# 计划-NOTIFY-1 · 提醒可见性与重启恢复

> **状态**：🚧 进行中 ｜ **最后核对**：2026-11-10
> **来源**：`计划-当前待办.md` 的 NOTIFY-1，加上 2026-11-10 只读探索发现的 N1 / N2 / N3
> **范围约定**：本计划只改 `doc/dev/` 内文档；`doc/README.md`、`doc/CURRENT-STATUS.md`、`doc/testing/buglist.md` 等 dev 外文档由其他会话处理，本任务不碰。

---

## 一、目标

让「习惯 / 备忘录 / 番茄钟」的提醒真正到达用户，并保证重启后仍然有效。

具体三件事：

1. **通知可见**：`HABIT_REMINDER`、`MEMO_REMINDER`、`POMODORO_END` 在 `main.py` 中被订阅，转成 `NotificationManager` 气泡。
2. **重启可恢复**：`HabitManager` / `MemoManager` 启动时从数据库重注册已有提醒（N1）。
3. **事件可审计**：相关事件在 `core/event_bus.py` 登记为常量，不再字符串直写（N3）。

## 二、非目标

- 不做 EMO-1（情绪 → 表情通道）。
- 不做 P1-2、E11-os、CFG-2、G1~G4。
- 不改动画、搜索、位置、记忆服务。
- 不重构 `NotificationManager` 的队列算法；只修“通知 id 永久去重”带来的实际吞提醒问题。
- 不做 `POMODORO_PAUSE / RESUME / CANCEL` 的用户提示（用户主动操作，弹窗反而打扰）。
- 不做 `HABIT_COMPLETED / HABIT_BROKEN` 的独立通知（打卡反馈由按钮回调内的 `show_tip` 承担）。

## 三、验收标准

- [ ] `HabitManager.restore_reminders()` 能为所有 `enabled=1` 的习惯重注册每日 cron；重复调用不会产生重复 job（`replace_existing=True`）。
- [ ] `MemoManager.restore_reminders()` 能为 `status='active'` 且 `remind_at` 在未来的备忘录重注册一次性 job；过期项跳过并记录日志。
- [ ] `main.py` 启动时调用两个 restore，且注册顺序在 `ReminderScheduler` 之后。
- [ ] `main.py` 订阅 `HABIT_REMINDER` / `MEMO_REMINDER` / `POMODORO_END`，使用 `subscribe_ui`（主线程）。
- [ ] 三个通知的 `id` 每次触发唯一：习惯按日期、备忘录按 `memo_id + timestamp`、番茄钟按 `stage + 时间戳`。
- [ ] 习惯通知的「打卡」按钮调用 `HabitManager.check_in()`；备忘录通知的「完成」按钮调用 `MemoManager.mark_done()`；番茄钟「开始专注」调用 `PomodoroTimer.start()`。
- [ ] 现有 `schedule_alert` 的 `advance` / `due` 不再因同一个 `schedule_id` 被去重吞掉（N2，同批小修）。
- [ ] 新增单测覆盖 restore / 通知 payload / id 唯一 / 按钮回调。
- [ ] `venv/Scripts/python.exe -m pytest tests -q` 全绿（预计 297 + 新增）。
- [ ] `python -m tools.audit_events` 中，上述三个提醒事件不再出现在“发布无订阅”。

## 四、分步执行

### P1 · 事件契约（N3）
- 在 `core/event_bus.py` 登记：
  `EVENT_HABIT_REMINDER`、`EVENT_HABIT_COMPLETED`、`EVENT_HABIT_BROKEN`、
  `EVENT_MEMO_REMINDER`、`EVENT_POMODORO_START`、`EVENT_POMODORO_END`、
  `EVENT_POMODORO_PAUSE`、`EVENT_POMODORO_RESUME`、`EVENT_POMODORO_CANCEL`。
- 把 `modules/habit.py`、`modules/memo.py`、`modules/pomodoro.py`、`modules/health/sedentary_monitor.py` 中的字符串直写替换为常量；事件值保持不变，兼容既有订阅者。

### P2 · 重启恢复（N1）
- `HabitManager.restore_reminders() -> int`：遍历 `list_all()`，对 `enabled` 项调用 `_schedule_reminder`。
- `MemoManager.restore_reminders() -> int`：遍历 `get_active()`，解析 `remind_at`，只注册未来项；过期项 `logger.warning` 后跳过。
- `main.py` 在注册 `memo_manager` / `habit_manager` 后立即调用 restore，并记录恢复数量。

### P3 · 通知接线
- `main.py` 的 `_init_event_listeners` 增加三条 `subscribe_ui`。
- 新增 `_on_habit_reminder` / `_on_memo_reminder` / `_on_pomodoro_end`，复用 `_on_health_reminder` 的 push 模式。
- 通知按钮：
  - 习惯：`✅ 打卡` / `稍后`；
  - 备忘录：`✅ 完成` / `知道了`；
  - 番茄钟：`focus_end` 只提示休息；`break_end` 提供 `开始专注`。
- `ui/notification_bubble.py` 增加 `pomodoro` 类型（边框色 + 图标）。

### P4 · N2 同批小修
- `schedule_alert` 通知 id 由 `sid` 改为 `schedule_{sid}_{stage}`，避免“提前预警显示过后，到期强提醒被 `_shown_ids` 吞掉”。
- 保留 `_shown_ids` 的去重语义，不做全量重构；新增通知一律遵守唯一 id 规则。

### P5 · 测试
- `tests/unit/test_reminder_restore.py`：habit/memo 恢复、过期跳过、重复注册使用 replace_existing。
- `tests/unit/test_notify_wiring.py`：三个 handler 的 payload、id 唯一性、按钮回调。
- 如需要，补 `tests/integration/test_notify_flow.py` 验证 `subscribe_ui` 投递；若 Qt 环境不稳定则只保留单元级。

### P6 · 验证与收尾
- 全量回归；事件审计；`git diff --check`。
- 真机 `python main.py` 启动一次，确认无异常、通知可弹出（若环境不可用则标注“未执行”）。
- 更新本计划状态与 `计划-当前待办.md` 的 NOTIFY-1 行；不提交，等用户确认。

## 五、风险与回滚

| 风险 | 处置 |
|---|---|
| 重启恢复时重复注册 job | `replace_existing=True`；restore 幂等 |
| 通知 id 冲突导致吞提醒 | 按日期/时间戳生成；测试断言两次触发 id 不同 |
| 主线程执行 `check_in` / `mark_done` 阻塞 UI | 均为单条 UPDATE + commit，毫秒级；不引入异步 |
| 多个事件订阅者（`POMODORO_END` 已有 sedentary_monitor） | EventBus 支持多订阅者；UI 订阅独立 |
| 事件常量替换漏改 | 全仓 grep 字符串；审计工具比对 |
| 回滚 | 按 P1~P5 分步提交，每步可独立回退；restore 与订阅互不依赖 |

## 六、待确认（不阻塞本次）

1. `HABIT_COMPLETED` / `HABIT_BROKEN` 是否要单独弹通知？本计划默认只用 `show_tip` 反馈。
2. `POMODORO_PAUSE / RESUME / CANCEL` 是否要提示？本计划默认不提示。
3. 现有 `drink_summary_{current_ml}` 等 id 的去重问题属健康提醒路径，本计划不动，单独记录。
