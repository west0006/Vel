"""事件总线静态审计工具。

用途：对比代码中所有 ``bus.publish*`` 与 ``bus.subscribe*`` 的实际事件名，找出两类断链：

* **发布但无人订阅** —— 功能"安静地失效"：代码跑通、无异常，但用户看不到任何反馈
  （实例：V0017 彩蛋触发后界面空白；`EVENT_MOOD_DETECTED` 发布后表情永不变化）。
* **订阅但无人发布** —— 处理器永远不会被触发（死代码）。

用法::

    python -m tools.audit_events                # 全量审计（跳过 tests/）
    python -m tools.audit_events --include-tests # 连测试里的事件一起统计
    python -m tools.audit_events --strict       # 发现断链时以非零码退出（可用于 CI）

为什么必须用 AST 而不是 grep
-------------------------
订阅侧存在三种写法，纯文本匹配会漏掉后两种（曾据此得出"11 个事件只有 1 个订阅者"
的错误结论）：

1. ``bus.subscribe_ui("CONTEXT_HINT", ...)``          —— 字符串
2. ``bus.subscribe_sync("POMODORO_START", ...)``      —— 方法名不同
3. ``bus.subscribe_ui(EVENT_HEALTH_REMINDER, ...)``   —— 用**常量**传参

本工具解析 ``core/event_bus.py`` 的常量定义，把第 3 种展开成实际事件名后再比对。
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EVENT_BUS_PATH = PROJECT_ROOT / "core" / "event_bus.py"

#: 扫描时跳过的目录
SKIP_DIRS = {"venv", ".venv", "build", "dist", "__pycache__", ".git", ".idea"}


def load_event_constants() -> Dict[str, str]:
    """从 ``core/event_bus.py`` 解析 ``EVENT_X = "value"`` 形式的常量。

    Returns:
        常量名 → 实际事件名。
    """
    source = EVENT_BUS_PATH.read_text(encoding="utf-8", errors="replace")
    return dict(re.findall(r'^([A-Z][A-Z0-9_]+)\s*=\s*"([^"]+)"', source, re.M))


def _resolve_event_name(arg: ast.expr, constants: Dict[str, str]) -> str:
    """把 publish/subscribe 的第一个实参解析成实际事件名。

    Args:
        arg: AST 实参节点。
        constants: 事件常量映射。

    Returns:
        事件名字符串；无法解析时返回 ``"<unresolved>"``。
    """
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if isinstance(arg, ast.Name):
        return constants.get(arg.id, f"<未解析常量:{arg.id}>")
    return "<非字面量>"


def scan_calls(include_tests: bool = False) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
    """扫描全仓库，收集发布与订阅的事件。

    Args:
        include_tests: 是否把 ``tests/`` 下的调用也统计进来。

    Returns:
        ``(published, subscribed)``，均为 ``事件名 → 出现文件集合``。
    """
    constants = load_event_constants()
    published: Dict[str, Set[str]] = {}
    subscribed: Dict[str, Set[str]] = {}

    for path in PROJECT_ROOT.rglob("*.py"):
        parts = set(path.parts)
        if parts & SKIP_DIRS:
            continue
        if not include_tests and "tests" in path.relative_to(PROJECT_ROOT).parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue

        rel = str(path.relative_to(PROJECT_ROOT))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            if not func.attr.startswith(("publish", "subscribe")) or not node.args:
                continue
            event = _resolve_event_name(node.args[0], constants)
            bucket = published if func.attr.startswith("publish") else subscribed
            bucket.setdefault(event, set()).add(rel)

    return published, subscribed


def audit(include_tests: bool = False) -> int:
    """执行审计并打印结果。

    Args:
        include_tests: 是否包含 tests/ 目录。

    Returns:
        断链数量（发布无订阅 + 订阅无发布）。
    """
    published, subscribed = scan_calls(include_tests)
    print(f"事件常量 {len(load_event_constants())} 个 | "
          f"发布 {len(published)} 种 | 订阅 {len(subscribed)} 种\n")

    unsubscribed = sorted(set(published) - set(subscribed))
    unpublished = sorted(set(subscribed) - set(published))

    print("=== 发布但无订阅（用户看不到反馈）===")
    if unsubscribed:
        for event in unsubscribed:
            print(f"  {event:26s} ← {sorted(published[event])[0]}")
    else:
        print("  （无）")

    print("\n=== 订阅但无发布（处理器永不触发）===")
    if unpublished:
        for event in unpublished:
            print(f"  {event:26s} ← {sorted(subscribed[event])[0]}")
    else:
        print("  （无）")

    if unsubscribed or unpublished:
        print("\n提示：断链本身不一定都是缺陷 —— 有些事件是内部信号（如 memory_created），"
              "设计上就无人订阅。请逐条确认，确认无害的记入 "
              "doc/dev/计划-当前待办.md 或 buglist 说明。")

    return len(unsubscribed) + len(unpublished)


def main(argv: List[str]) -> int:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="事件发布/订阅断链审计")
    parser.add_argument("--include-tests", action="store_true",
                        help="把 tests/ 下的事件也统计进来")
    parser.add_argument("--strict", action="store_true",
                        help="发现断链时返回非零退出码")
    args = parser.parse_args(argv[1:])

    count = audit(include_tests=args.include_tests)
    if args.strict and count:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
