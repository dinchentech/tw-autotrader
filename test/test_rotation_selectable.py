"""回歸測試：13:31+ 盤後區塊內必須能觸發全輪替選股（v3.19 修復）

背景（2026-08-31 VM 實盤發現）：全輪替 ROTATE_MODE=5 的自動選股**從未執行過**。
根因：主迴圈 `if (is_weekday and (h == 13) and (m >= 31)):` 區塊內每分鐘
`run_inst_momentum(...)` → `time.sleep(60)` → `continue`，而選股邏輯
（`if ROTATE_MODE_VAL > 0 and is_weekday and h == 13 and 31 <= m <= 35:`）
寫在**同層級、該區塊之後**——13:31~13:35 期間永遠被 continue 擋住，選股區塊不可達。
backups/ 空、rotation_pending.json 從未存在 → 證實從未自動選股過。

修復：把選股邏輯移入 13:31+ 區塊內部（run_inst_momentum 之前）。
"""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _postclose_if_nodes(tree):
    """找 `if (is_weekday and (h == 13) and (m >= 31)):` 節點"""
    found = []

    class Walker(ast.NodeVisitor):
        def visit_If(self, node):
            s = ast.unparse(node.test)
            if 'm >= 31' in s and 'h == 13' in s and 'is_weekday' in s:
                found.append(node)
            self.generic_visit(node)

    Walker().visit(tree)
    return found


class TestRotationSelectableRegression(unittest.TestCase):
    def test_postclose_block_contains_selector(self):
        """回歸：13:31+ 區塊內必須直接（或嵌套）包含選股觸發邏輯"""
        for name in ('live_trader_multi.py', 'plans/live_trader_multi.py'):
            p = ROOT / name
            if not p.exists():
                continue
            src = p.read_text(encoding='utf-8')
            if 'should_rotate_today' not in src:
                continue
            tree = ast.parse(src)
            blocks = _postclose_if_nodes(tree)
            self.assertTrue(blocks, f'{name}: 找不到 13:31+ 盤後區塊')
            for b in blocks:
                subtree = ast.unparse(b)
                self.assertIn('should_rotate_today', subtree,
                              f'{name}: 13:31+ 區塊內必須包含選股邏輯'
                              f'（v3.18 前寫在區塊外被 continue 擋死，自動選股從未執行）')
            return
        self.fail('找不到含 should_rotate_today 的源碼')


if __name__ == '__main__':
    unittest.main()
