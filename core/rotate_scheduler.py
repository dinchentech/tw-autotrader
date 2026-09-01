"""
core/rotate_scheduler.py — 全輪替排程邏輯與 .env 產出
"""
import json
import os
import shutil
import subprocess
from datetime import datetime, date
from pathlib import Path

# 全輪替策略常數
ROTATE_TOP_N = int(os.getenv('ROTATE_TOP_N', '4'))
ROTATE_MODE = int(os.getenv('ROTATE_MODE', '0'))
ROTATE_CAPITAL_PCT = float(os.getenv('ROTATE_CAPITAL_PCT', '50'))
ROTATE_STRATEGY = 'keep_wait'
ROTATE_MAX_ENTRY = -1
ROTATE_BUY_PCT = 1.0


def calc_rotation_alloc(rotate_mode, top_n, capital_pct=50.0):
    """全輪替每檔 alloc（v3.26）：capital_pct（全輪替總資金佔 TOTAL_CAPITAL 比例）
    平分給排程數（雙排程 4/5 = 2，其餘 = 1），再除以 top_n。

    相容性：capital_pct=100 時與舊行為一致（雙排程 50/top_n、單排程 100/top_n）。
    """
    num_schedules = 2 if int(rotate_mode) in (4, 5) else 1
    return round(float(capital_pct) / num_schedules / int(top_n), 2)


ROTATE_ALLOC = calc_rotation_alloc(ROTATE_MODE, ROTATE_TOP_N, ROTATE_CAPITAL_PCT)

ROTATE_QMAP = {
    1: {'months': (1, 4, 7, 10), 'label': 'A', 'is_dual': False},
    2: {'months': (2, 5, 8, 11), 'label': 'A', 'is_dual': False},
    3: {'months': (3, 6, 9, 12), 'label': 'A', 'is_dual': False},
    4: {'schedules': {'A': (1, 4, 7, 10), 'B': (2, 5, 8, 11)}, 'is_dual': True},
    5: {'schedules': {'A': (2, 5, 8, 11), 'B': (3, 6, 9, 12)}, 'is_dual': True},
}


def get_rotate_months(rotate_mode):
    if rotate_mode == 0:
        return {}
    cfg = ROTATE_QMAP.get(rotate_mode)
    if cfg is None:
        return {}
    if cfg.get('is_dual'):
        return cfg['schedules'].copy()
    return {cfg['label']: cfg['months']}


def should_rotate_today(today, rotate_mode, calendar, nth_trading_day=-1):
    """是否為選股日。nth_trading_day=-1 = 每月最後交易日（預設，2026-08-18 起）。"""
    from core.trading_calendar import TradingCalendar
    if rotate_mode == 0:
        return None
    if not calendar.is_trading_day(today):
        return None
    months_map = get_rotate_months(rotate_mode)
    if not months_map:
        return None
    for label, months in months_map.items():
        if today.month in months:
            target_td = calendar.get_nth_trading_day(today.year, today.month, nth_trading_day)
            if target_td and today.year == target_td.year and today.month == target_td.month and today.day == target_td.day:
                return label
    return None


def backup_env(env_path, backup_dir):
    src = Path(env_path)
    if not src.exists():
        return None
    dst_dir = Path(backup_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    dst = dst_dir / f'.env.{ts}'
    shutil.copy2(src, dst)
    return str(dst)


def _make_pc_entry(symbol, alloc=None):
    if alloc is None:
        alloc = ROTATE_ALLOC
    cfg = {
        'strategy': ROTATE_STRATEGY,
        'alloc': alloc,
        'max_entry_price': ROTATE_MAX_ENTRY,
        'initial_buy_pct': ROTATE_BUY_PCT,
    }
    return f"PC_{symbol}={json.dumps(cfg, separators=(',', ':'))}"


def update_env_section(env_path, schedule_label, pc_entries):
    p = Path(env_path)
    if not p.exists():
        new_lines = [f'# ── 排程 {schedule_label} ──\n'] + [e + '\n' for e in pc_entries] + ['\n']
        p.write_text(''.join(new_lines), encoding='utf-8')
        return

    lines = p.read_text(encoding='utf-8').splitlines(True)
    section_start = f'# ── 排程 {schedule_label}'

    new_lines = []
    replaced = False
    i = 0

    while i < len(lines):
        stripped = lines[i].strip()

        if not replaced and stripped.startswith(section_start):
            new_lines.append(lines[i])
            for entry in pc_entries:
                new_lines.append(entry + '\n')
            new_lines.append('\n')
            replaced = True
            i += 1
            while i < len(lines):
                s = lines[i].strip()
                if s.startswith('# ── 排程 '):
                    break
                i += 1
            continue

        new_lines.append(lines[i])
        i += 1

    p.write_text(''.join(new_lines), encoding='utf-8')


def remove_monitored_only_entries(env_path, selected_symbols, holdings=None):
    """全輪替選股完成後清理：選入的標的若被其他策略僅監控（有非全輪替 PC_ 條目
    且未持有）→ 移除該監控條目並回報 [(symbol, 原條目行)]，供 TG 通知。

    判定「其他策略」：PC_ 條目的 strategy != keep_wait 或 max_entry_price != -1
    （全輪替管理的條目特徵 = keep_wait + max_entry_price=-1，不會被移除 —
    撞股時由 config_loader 的 alloc 加倍處理）。已持有（holdings > 0）不移除，
    由買入端 should_skip_rotation_overlap 防護跳過。
    """
    p = Path(env_path)
    if not p.exists() or not selected_symbols:
        return []
    holdings = holdings or {}
    wanted = set(selected_symbols)
    removed = []
    kept = []
    for line in p.read_text(encoding='utf-8').splitlines(True):
        stripped = line.strip()
        if stripped.startswith('PC_') and '=' in stripped:
            sym = stripped[3:].split('=', 1)[0].strip()
            if sym in wanted and int(holdings.get(sym, 0) or 0) <= 0:
                try:
                    cfg = json.loads(stripped.split('=', 1)[1])
                except (json.JSONDecodeError, IndexError):
                    cfg = {}
                is_rotation = (cfg.get('strategy') == 'keep_wait'
                               and float(cfg.get('max_entry_price', 0)) == -1)
                if not is_rotation:
                    removed.append((sym, stripped))
                    continue
        kept.append(line)
    if removed:
        p.write_text(''.join(kept), encoding='utf-8')
    return removed


def run_rotation_selection(rotate_mode, schedule_label, env_path='.env', backup_dir='backups', top_n=4):
    result = subprocess.run(
        ['python', 'scripts/stock_selector_grid.py', '--recommend', '--output-env',
         '--schedule-label', schedule_label, '--top-n', str(top_n)],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(f'selector exited with {result.returncode}: {result.stderr[:500]}')

    raw_lines = result.stdout.strip().split('\n')
    # selector 在雙排程模式會重複印 PC_ 兩次（單排程路徑 1185 行 + 雙排程路徑 1592 行）——
    # 保序去重，避免 .env 寫入重複條目（2026-08-31 手動補救時發現）
    pc_lines = []
    seen = set()
    for l in raw_lines:
        l = l.strip()
        if l.startswith('PC_') and l not in seen:
            pc_lines.append(l)
            seen.add(l)

    if not pc_lines:
        raise RuntimeError('selector returned no PC_ entries')

    backup_env(env_path, backup_dir)
    update_env_section(env_path, schedule_label, pc_lines)

    stocks = []
    for line in pc_lines:
        sym = line.split('=')[0].replace('PC_', '')
        stocks.append(sym)

    return stocks
