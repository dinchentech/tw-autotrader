#!/usr/bin/env python3
"""
integration_test_user_strategies.py - 完整整合測試

測試用戶自訂策略在 live_trader_multi.py 中的完整流程。
"""

import pandas as pd
import numpy as np
import os
import json

def test_full_integration():
    """測試完整整合流程"""
    print("=" * 60)
    print("用戶自訂策略完整整合測試")
    print("=" * 60)

    # 1. 測試 config_loader 是否正確識別用戶策略參數
    print("\n📋 測試 1: config_loader 參數鍵...")
    from core.config_loader import STRATEGY_PARAM_KEYS

    user_strategies = ['g1_strategy_1', 'g1_strategy_2', 'g2_strategy_1', 'g2_strategy_2']
    all_present = all(s in STRATEGY_PARAM_KEYS for s in user_strategies)

    if all_present:
        print("✅ 所有用戶策略參數鍵已註冊")
        for s in user_strategies:
            print(f"   {s}: {STRATEGY_PARAM_KEYS[s]}")
    else:
        print("❌ 缺少用戶策略參數鍵")
        return False

    # 2. 測試用戶策略載入
    print("\n📋 測試 2: 用戶策略載入...")
    try:
        from user_strategies import USER_STRATEGY_MAP
        print(f"✅ 成功載入 {len(USER_STRATEGY_MAP)} 個用戶策略")
    except ImportError as e:
        print(f"❌ 載入失敗: {e}")
        return False

    # 3. 測試 STRATEGY_FUNCS 整合
    print("\n📋 測試 3: STRATEGY_FUNCS 整合...")
    STRATEGY_FUNCS = {
        "vwap": lambda df, **kw: pd.DataFrame({'signal': pd.Series(0, index=df.index)}),
        "ma_cross": lambda df, **kw: pd.DataFrame({'signal': pd.Series(0, index=df.index)}),
        "bollinger": lambda df, **kw: pd.DataFrame({'signal': pd.Series(0, index=df.index)}),
        "breakout": lambda df, **kw: pd.DataFrame({'signal': pd.Series(0, index=df.index)}),
        "keep_wait": lambda df, **kw: pd.DataFrame({'signal': pd.Series(0, index=df.index)}),
    }

    try:
        from user_strategies import USER_STRATEGY_MAP
        STRATEGY_FUNCS.update(USER_STRATEGY_MAP)
        print(f"✅ STRATEGY_FUNCS 已更新，現有 {len(STRATEGY_FUNCS)} 個策略")

        # 檢查用戶策略是否已加入
        for s in user_strategies:
            if s in STRATEGY_FUNCS:
                print(f"   ✓ {s} 已註冊")
            else:
                print(f"   ✗ {s} 未註冊")
                return False
    except Exception as e:
        print(f"❌ 整合失敗: {e}")
        return False

    # 4. 測試參數傳遞
    print("\n📋 測試 4: 參數傳遞...")
    from core.config_loader import get_strategy_params

    test_cfg = {
        "strategy": "g1_strategy_1",
        "fast_period": 10,
        "slow_period": 20,
        "extra_param": "should_be_filtered"
    }

    params = get_strategy_params(test_cfg, "g1_strategy_1")
    print(f"   原始設定: {test_cfg}")
    print(f"   過濾後參數: {params}")

    expected_keys = {'fast_period', 'slow_period'}
    actual_keys = set(params.keys())

    if actual_keys == expected_keys:
        print("✅ 參數過濾正確")
    else:
        print(f"❌ 參數過濾錯誤: 期望 {expected_keys}, 實際 {actual_keys}")
        return False

    # 5. 測試完整執行流程
    print("\n📋 測試 5: 完整執行流程...")

    # 產生測試資料
    np.random.seed(42)
    dates = pd.date_range('2025-01-01', periods=100, freq='D')
    data = {
        'open': np.random.randn(100).cumsum() + 100,
        'high': np.random.randn(100).cumsum() + 102,
        'low': np.random.randn(100).cumsum() + 98,
        'close': np.random.randn(100).cumsum() + 100,
        'volume': np.random.randint(1000, 10000, 100)
    }
    df = pd.DataFrame(data, index=dates)

    # 模擬 live_trader_multi.py 中的執行流程
    symbol = "2330"
    cfg = {
        "strategy": "g1_strategy_1",
        "fast_period": 5,
        "slow_period": 15,
        "position_amount": 10000
    }

    print(f"   模擬股票: {symbol}")
    print(f"   策略: {cfg['strategy']}")
    print(f"   參數: {get_strategy_params(cfg, cfg['strategy'])}")

    # 取得策略函式
    strat_func = STRATEGY_FUNCS[cfg['strategy']]
    strat_params = get_strategy_params(cfg, cfg['strategy'])

    # 執行策略
    try:
        result = strat_func(df, **strat_params)
        signal = result['signal'].iloc[-1]

        print(f"   最新訊號: {signal} (1=BUY, -1=SELL, 0=HOLD)")
        print("✅ 完整執行流程成功")
    except Exception as e:
        print(f"❌ 執行失敗: {e}")
        return False

    print("\n" + "=" * 60)
    print("✅ 所有測試通過！用戶自訂策略已正確整合。")
    print("=" * 60)

    print("\n📝 使用方式:")
    print("1. 在 .env 中設定:")
    print('   PC_2330={"strategy":"g1_strategy_1","alloc":20,"fast_period":5,"slow_period":15}')
    print("2. 啟動系統:")
    print("   python live_trader_multi.py")

    return True


if __name__ == "__main__":
    test_full_integration()