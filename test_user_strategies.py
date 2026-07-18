#!/usr/bin/env python3
"""
test_user_strategies.py - 驗證用戶自訂策略載入是否正常

執行此腳本以確保 user_strategies.py 中的策略可以正確載入並執行。
"""

import pandas as pd
import numpy as np

def test_strategy_load():
    """測試策略載入"""
    print("🧪 測試 1: 載入 user_strategies.py...")
    try:
        from user_strategies import USER_STRATEGY_MAP
        print(f"✅ 成功載入，找到 {len(USER_STRATEGY_MAP)} 個策略：")
        for name in USER_STRATEGY_MAP.keys():
            print(f"   - {name}")
        return True
    except ImportError as e:
        print(f"❌ 載入失敗: {e}")
        return False


def test_strategy_execution(strategy_name, strategy_func):
    """測試策略執行"""
    print(f"\n🧪 測試策略: {strategy_name}")

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

    # 執行策略
    try:
        result = strategy_func(df)
        print(f"   ✅ 執行成功")
        print(f"   - 輸入形狀: {df.shape}")
        print(f"   - 輸出形狀: {result.shape}")
        print(f"   - 訊號欄位: {result.columns.tolist()}")
        if 'signal' in result.columns:
            signals = result['signal'].value_counts().to_dict()
            print(f"   - 訊號統計: BUY={signals.get(1,0)}, SELL={signals.get(-1,0)}, HOLD={signals.get(0,0)}")
        return True
    except Exception as e:
        print(f"   ❌ 執行失敗: {e}")
        return False


def test_all_strategies():
    """測試所有策略"""
    print("=" * 60)
    print("用戶自訂策略驗證工具")
    print("=" * 60)

    if not test_strategy_load():
        return

    from user_strategies import USER_STRATEGY_MAP

    passed = 0
    failed = 0

    for name, func in USER_STRATEGY_MAP.items():
        if test_strategy_execution(name, func):
            passed += 1
        else:
            failed += 1

    print("\n" + "=" * 60)
    print(f"測試結果: {passed} 通過, {failed} 失敗")
    print("=" * 60)

    if failed == 0:
        print("\n✅ 所有策略測試通過！可以在 .env 中使用這些策略。")
        print("\n使用範例:")
        print('  PC_2330={"strategy":"g1_strategy_1","alloc":20}')
    else:
        print("\n⚠️  有策略測試失敗，請檢查 user_strategies.py")


def test_live_trader_integration():
    """測試與 live_trader_multi.py 的整合"""
    print("\n" + "=" * 60)
    print("測試與 live_trader_multi.py 整合")
    print("=" * 60)

    try:
        from user_strategies import USER_STRATEGY_MAP
        from core.config_loader import STRATEGY_PARAM_KEYS

        # 更新 config_loader 中的參數鍵
        new_keys = {
            'g1_strategy_1': ['fast_period', 'slow_period'],
            'g1_strategy_2': ['k_period', 'k_threshold'],
            'g2_strategy_1': ['lookback', 'threshold'],
            'g2_strategy_2': ['ma_period', 'volume_ma_period', 'volume_mult'],
        }

        # 顯示需要的更新
        print("\n⚠️  請在 core/config_loader.py 的 STRATEGY_PARAM_KEYS 中添加:")
        for k, v in new_keys.items():
            print(f'    "{k}": {v},')

        print("\n📝 請在 live_trader_multi.py 中添加以下程式碼以載入用戶策略:")
        print("""
    # 載入用戶自訂策略
    try:
        from user_strategies import USER_STRATEGY_MAP
        STRATEGY_FUNCS.update(USER_STRATEGY_MAP)
        print(f"✅ 已載入 {len(USER_STRATEGY_MAP)} 個用戶自訂策略")
    except ImportError:
        print("ℹ️  未找到 user_strategies.py，僅使用內建策略")
""")

    except Exception as e:
        print(f"❌ 整合測試失敗: {e}")


if __name__ == "__main__":
    test_all_strategies()
    test_live_trader_integration()