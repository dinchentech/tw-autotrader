"""回歸測試：live_trader_multi.py 的 _rot_day_buys 必須無條件初始化（v3.10 修復）

背景（2026-08-18 VM 錯誤：`❌ 3653 錯誤: cannot access local variable '_rot_day_buys'`）：
_rot_day_buys 原只寫在 `if (daily_symbol_trades_date != today_str):` 區塊內（每日初始化）。
但程式啟動時 load_daily_trades() 若讀到「今天的」紀錄（當天重啟），daily_symbol_trades_date
已 == today → 該區塊被跳過 → 買入迴圈 `if symbol in _rot_day_buys:` 拋 UnboundLocalError，
導致當天 4 檔全輪替持股的買入判斷全部失敗。

修復：_rot_day_buys = set() 移至迴圈層級（無條件，每輪初始化）。
"""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _is_rot_day_buys_target(t):
    if isinstance(t, ast.Name):
        return t.id == '_rot_day_buys'
    if isinstance(t, ast.Tuple):
        return any(isinstance(e, ast.Name) and e.id == '_rot_day_buys' for e in t.elts)
    return False


def _rot_day_buys_assign_nodes(tree):
    found = []

    class Walker(ast.NodeVisitor):
        def visit_Assign(self, node):
            if any(_is_rot_day_buys_target(t) for t in node.targets):
                found.append(node)
            self.generic_visit(node)

    Walker().visit(tree)
    return found


def _is_unconditional_in_loop(node, tree):
    """Assign 是否位於 while 迴圈本體、且未嵌套在任何 if/for/try/with 條件內。"""
    parent_map = {child: parent for parent in ast.walk(tree)
                  for child in ast.iter_child_nodes(parent)}
    cur = node
    while cur in parent_map:
        cur = parent_map[cur]
        if isinstance(cur, ast.While):
            return True
        if isinstance(cur, (ast.If, ast.For, ast.Try, ast.With)):
            return False
    return False


class TestRotDayBuysRegression(unittest.TestCase):
    def test_helper_detects_buggy_nesting(self):
        buggy = "while True:\n    if x != y:\n        _rot_day_buys = set()\n    print(_rot_day_buys)\n"
        tree = ast.parse(buggy)
        assigns = _rot_day_buys_assign_nodes(tree)
        self.assertTrue(assigns, 'helper 應找得到 Assign 節點')
        self.assertFalse(any(_is_unconditional_in_loop(a, tree) for a in assigns),
                         '寫在 if 區塊內應被判為非無條件')

    def test_helper_accepts_loop_level_init(self):
        fixed = "while True:\n    if x != y:\n        pass\n    _rot_day_buys = set()\n    print(_rot_day_buys)\n"
        tree = ast.parse(fixed)
        assigns = _rot_day_buys_assign_nodes(tree)
        self.assertTrue(any(_is_unconditional_in_loop(a, tree) for a in assigns),
                        '迴圈層級的初始化應被判為無條件')

    def test_rot_day_buys_unconditional_init(self):
        for name in ('live_trader_multi.py', 'plans/live_trader_multi.py'):
            p = ROOT / name
            if not p.exists():
                continue
            src = p.read_text(encoding='utf-8')
            if '_rot_day_buys' not in src:
                continue
            tree = ast.parse(src)
            assigns = _rot_day_buys_assign_nodes(tree)
            self.assertTrue(assigns, f'{name}: 找不到 _rot_day_buys 初始化')
            self.assertTrue(any(_is_unconditional_in_loop(a, tree) for a in assigns),
                            f'{name}: _rot_day_buys 初始化必須在迴圈層級無條件執行'
                            f'（不可只寫在 if 區塊內，否則當天重啟會 UnboundLocalError）')
            return
        self.fail('找不到含 _rot_day_buys 的源碼（live_trader_multi.py 或 plans/live_trader_multi.py）')


if __name__ == '__main__':
    unittest.main()
