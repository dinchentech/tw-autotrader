"""
core/config_loader.py — 共用設定載入器（V1.11）

從 PC_<代號> 環境變數載入個股策略設定 (JSON 格式)，
供 live_trader_multi.py 及所有回測檔案共用。
"""
import os
import json

# 各策略函式可接受的參數名稱（用於從 per-stock config 過濾）
STRATEGY_PARAM_KEYS = {
    "bollinger": ["window", "std_dev", "rsi_period", "rsi_low", "rsi_high"],
    "vwap": ["sigma_mult", "rsi_period", "rsi_low", "rsi_high"],
    "ma_cross": ["fast_period", "slow_period", "atr_period", "atr_threshold"],
    "breakout": ["lookback", "atr_period", "atr_threshold"],
    "keep_wait": [],
    # 用戶自訂策略
    "g1_strategy_1": ["buy_price", "sell_price"],
    "g1_strategy_2": ["rsi_period", "oversold", "overbought"],
    "g2_strategy_1": ["lookback", "threshold"],
    "g2_strategy_2": ["ma_period", "volume_ma_period", "volume_mult"],
}

# keep_wait DCA 參數名稱（用於 simulate_portfolio.py 等）
KEEP_WAIT_PARAM_KEYS = [
    "initial_buy_pct", "initial_shares", "add_drop_pct", "add_shares", "max_additions",
    "tp_trigger_pct", "tp_sell_ratio", "cooldown_days",
]


def load_portfolio_config() -> dict:
    """
    掃描環境變數中所有 PC_ 開頭的變數，解析 JSON 設定。
    回傳 { 股票代號: config_dict }
    """
    config = {}
    for key, val in os.environ.items():
        if key.startswith("PC_"):
            symbol = key[3:]  # 去掉 PC_ 前綴
            try:
                parsed = json.loads(val)
                if "strategy" not in parsed:
                    print(f"⚠️  {symbol} 設定缺少 strategy 欄位，跳過")
                    continue
                config[symbol] = parsed
            except json.JSONDecodeError:
                print(f"⚠️  {symbol} 設定不是有效的 JSON，跳過: {val[:60]}...")
                continue
    return config


def get_strategy_params(cfg: dict, strategy: str) -> dict:
    """從 per-stock config 提取該策略認識的參數"""
    keys = STRATEGY_PARAM_KEYS.get(strategy, [])
    return {k: cfg[k] for k in keys if k in cfg}


def get_keep_wait_params(cfg: dict) -> dict:
    """從 per-stock config 提取 keep_wait DCA 參數"""
    return {k: cfg[k] for k in KEEP_WAIT_PARAM_KEYS if k in cfg}


def build_portfolio_from_env(fallback: bool = True) -> dict:
    """
    從 PC_ 環境變數建立投資組合設定，回傳格式：
    { symbol: { "strategy": ..., "params": {...}, "alloc": ..., ... } }
    
    若無 PC_ 設定且 fallback=True，回退到舊 PORTFOLIO 格式。
    """
    config = load_portfolio_config()
    if config:
        return config

    if fallback:
        raw = os.getenv("PORTFOLIO")
        if raw:
            fallback_config = {}
            for pair in raw.split(","):
                pair = pair.strip()
                if ":" not in pair:
                    continue
                symbol, strategy = pair.split(":", 1)
                fallback_config[symbol.strip()] = {"strategy": strategy.strip().lower()}
            return fallback_config

    return {}
