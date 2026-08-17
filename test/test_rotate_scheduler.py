import unittest
import json
import os
import shutil
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch


class TestTradingCalendar(unittest.TestCase):
    def setUp(self):
        from core.trading_calendar import TradingCalendar
        self.TradingCalendar = TradingCalendar
        self.calendar = TradingCalendar()

    def test_weekday_is_trading_day(self):
        d = date(2026, 8, 3)
        self.assertTrue(self.calendar.is_trading_day(d),
                        f'{d} (Mon) should be a trading day')

    def test_weekend_not_trading(self):
        self.assertFalse(self.calendar.is_trading_day(date(2026, 8, 1)),
                         'Saturday should not be a trading day')
        self.assertFalse(self.calendar.is_trading_day(date(2026, 8, 2)),
                         'Sunday should not be a trading day')

    def test_known_holiday_not_trading(self):
        self.assertFalse(self.calendar.is_trading_day(date(2026, 1, 1)),
                         'New Year Day should not be a trading day')
        self.assertFalse(self.calendar.is_trading_day(date(2026, 2, 17)),
                         'Lunar New Year should not be a trading day')

    def test_get_first_trading_day_august_2026(self):
        result = self.calendar.get_first_trading_day(2026, 8)
        self.assertEqual(str(result), '2026-08-03',
                         'First trading day of Aug 2026 should be 8/3 (Mon)')

    def test_get_nth_trading_day(self):
        r2 = self.calendar.get_nth_trading_day(2026, 8, 2)
        self.assertEqual(str(r2), '2026-08-04',
                         '2nd trading day of Aug 2026 should be 8/4 (Tue)')
        r3 = self.calendar.get_nth_trading_day(2026, 8, 3)
        self.assertEqual(str(r3), '2026-08-05',
                         '3rd trading day of Aug 2026 should be 8/5 (Wed)')

    def test_cache_works(self):
        r1 = self.calendar.is_trading_day(date(2026, 8, 3))
        r2 = self.calendar.is_trading_day(date(2026, 8, 3))
        self.assertEqual(r1, r2, 'Cached result should equal original')

    def test_makeup_workday_is_trading(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                'holidays': [],
                'makeup_workdays': ['2026-02-14']
            }, f)
            tmp_path = f.name
        try:
            tc = self.TradingCalendar(holidays_file=tmp_path)
            result = tc.is_trading_day(date(2026, 2, 14))
            self.assertTrue(result, 'Makeup workday Saturday should be a trading day')
        finally:
            os.unlink(tmp_path)

    def test_get_nth_trading_day_nonexistent(self):
        result = self.calendar.get_nth_trading_day(2026, 2, 20)
        self.assertIsNone(result, 'Month with fewer than 20 trading days should return None')

    def test_get_last_trading_day_month_end(self):
        r = self.calendar.get_nth_trading_day(2026, 8, -1)
        self.assertEqual(str(r), '2026-08-31',
                         'n=-1 should return the last trading day of the month')
        r9 = self.calendar.get_nth_trading_day(2026, 9, -1)
        self.assertEqual(str(r9), '2026-09-30',
                         'Sep 2026 last trading day should be 9/30 (holidays 9/25, 9/28)')


if __name__ == '__main__':
    unittest.main()


class TestRotateScheduler(unittest.TestCase):
    def setUp(self):
        from core.rotate_scheduler import (
            get_rotate_months, should_rotate_today, backup_env,
            update_env_section, _make_pc_entry
        )
        from core.trading_calendar import TradingCalendar
        self.get_rotate_months = get_rotate_months
        self.should_rotate_today = should_rotate_today
        self.backup_env = backup_env
        self.update_env_section = update_env_section
        self._make_pc_entry = _make_pc_entry
        self.calendar = TradingCalendar()

    def test_get_rotate_months_mode_0(self):
        result = self.get_rotate_months(0)
        self.assertEqual(result, {}, 'ROTATE_MODE=0 should return empty dict')

    def test_get_rotate_months_mode_1(self):
        result = self.get_rotate_months(1)
        self.assertEqual(result, {'A': (1, 4, 7, 10)})

    def test_get_rotate_months_mode_2(self):
        result = self.get_rotate_months(2)
        self.assertEqual(result, {'A': (2, 5, 8, 11)})

    def test_get_rotate_months_mode_3(self):
        result = self.get_rotate_months(3)
        self.assertEqual(result, {'A': (3, 6, 9, 12)})

    def test_get_rotate_months_mode_5(self):
        result = self.get_rotate_months(5)
        self.assertEqual(result, {'A': (2, 5, 8, 11), 'B': (3, 6, 9, 12)})

    def test_should_rotate_mode5_august_first_trading_day(self):
        result = self.should_rotate_today(date(2026, 8, 3), 5, self.calendar, nth_trading_day=1)
        self.assertEqual(result, 'A',
                         'Aug 3 2026 should be 1st trading day, ROTATE_MODE=5 schedule A')

    def test_should_rotate_nth_trading_day_2(self):
        result = self.should_rotate_today(date(2026, 8, 4), 5, self.calendar, nth_trading_day=2)
        self.assertEqual(result, 'A',
                         'Aug 4 2026 should be 2nd trading day, ROTATE_MODE=5 schedule A')

    def test_should_rotate_nth_trading_day_5(self):
        result = self.should_rotate_today(date(2026, 8, 7), 5, self.calendar, nth_trading_day=5)
        self.assertEqual(result, 'A',
                         'Aug 7 2026 should be 5th trading day (Mon-Fri week), schedule A')

    def test_should_rotate_nth_trading_day_wrong_day(self):
        result = self.should_rotate_today(date(2026, 8, 3), 5, self.calendar, nth_trading_day=2)
        self.assertIsNone(result,
                          'Aug 3 is 1st trading day, not 2nd — should not trigger for N=2')

    def test_should_rotate_nth_trading_day_default_is_month_end(self):
        result = self.should_rotate_today(date(2026, 8, 4), 5, self.calendar)
        self.assertIsNone(result,
                          'Default N=-1 means only last trading day triggers, not 2nd trading day')
        result = self.should_rotate_today(date(2026, 8, 31), 5, self.calendar)
        self.assertEqual(result, 'A',
                         'Default N=-1 should trigger on the last trading day of Aug 2026 (8/31)')

    def test_should_rotate_mode5_september_first_trading_day(self):
        result = self.should_rotate_today(date(2026, 9, 1), 5, self.calendar, nth_trading_day=1)
        self.assertEqual(result, 'B',
                         'Sep 1 2026 should be 1st trading day, ROTATE_MODE=5 schedule B')

    def test_should_rotate_not_first_trading_day(self):
        result = self.should_rotate_today(date(2026, 8, 4), 5, self.calendar)
        self.assertIsNone(result, '2nd trading day should not trigger rotation')

    def test_should_rotate_wrong_month(self):
        result = self.should_rotate_today(date(2026, 7, 1), 5, self.calendar)
        self.assertIsNone(result, 'July is not in any ROTATE_MODE=5 schedule')

    def test_should_rotate_mode_0_never(self):
        result = self.should_rotate_today(date(2026, 8, 3), 0, self.calendar)
        self.assertIsNone(result, 'ROTATE_MODE=0 should never trigger')

    def test_update_env_section_preserves_other_pc(self):
        tmpdir = tempfile.mkdtemp()
        try:
            test_env = ('# =====\nTOTAL_CAPITAL=500000\n'
                        '# ── 排程 A (2/5/8/11月)\n'
                        'PC_OLD1={"strategy":"keep_wait"}\n\n'
                        '# ── 排程 B (3/6/9/12月)\n'
                        'PC_OTHER={"strategy":"bollinger"}\n')
            env_path = os.path.join(tmpdir, '.env')
            with open(env_path, 'w') as f:
                f.write(test_env)
            new_entries = ['PC_NEW={"strategy":"keep_wait","alloc":12.5}']
            self.update_env_section(env_path, 'A', new_entries)
            with open(env_path) as f:
                updated = f.read()
            self.assertIn('PC_OTHER', updated, 'Schedule B entries preserved')
            self.assertNotIn('PC_OLD1', updated, 'Old schedule A entries removed')
            self.assertIn('PC_NEW', updated, 'New schedule A entries added')
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_backup_env_creates_file(self):
        tmpdir = tempfile.mkdtemp()
        try:
            env_path = os.path.join(tmpdir, '.env')
            with open(env_path, 'w') as f:
                f.write('TEST_BACKUP=1\n')
            backup_path = self.backup_env(env_path, os.path.join(tmpdir, 'backups'))
            self.assertIsNotNone(backup_path, 'backup_env should return a path')
            self.assertTrue(os.path.exists(backup_path), 'Backup file should exist')
            with open(backup_path) as f:
                self.assertEqual(f.read(), 'TEST_BACKUP=1\n',
                                 'Backup content should match original')
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_update_env_section_new_file(self):
        tmpdir = tempfile.mkdtemp()
        try:
            env_path = os.path.join(tmpdir, '.env_new')
            new_entries = ['PC_TEST={"strategy":"keep_wait","alloc":25.0}']
            self.update_env_section(env_path, 'A', new_entries)
            self.assertTrue(os.path.exists(env_path),
                            'New .env file should be created')
            with open(env_path) as f:
                content = f.read()
            self.assertIn('PC_TEST', content)
            self.assertIn('排程 A', content)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
