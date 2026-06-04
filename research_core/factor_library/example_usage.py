# ============================================================
# Factor Library - Smoke Test / Example Usage
# ============================================================

import numpy as np
import pandas as pd
try:
    from .wq101_alpha_1_10 import compute_all_alphas as compute_wq101
    from .gtja191_alpha_1_10 import compute_all_alphas as compute_gtja191
    from .batch_compute import batch_compute_factors
    from .ai_factor_mining import mine_and_validate_factors
except ImportError:
    from research_core.factor_library.wq101_alpha_1_10 import compute_all_alphas as compute_wq101
    from research_core.factor_library.gtja191_alpha_1_10 import compute_all_alphas as compute_gtja191
    from research_core.factor_library.batch_compute import batch_compute_factors
    from research_core.factor_library.ai_factor_mining import mine_and_validate_factors


def generate_mock_data(n_dates=30, n_codes=5):
    """生成模拟数据，不依赖任何外部数据源"""
    np.random.seed(42)
    dates = pd.date_range('2020-01-01', periods=n_dates, freq='B')
    codes = [f'STOCK_{i:02d}' for i in range(n_codes)]
    
    records = []
    for code in codes:
        base_price = np.random.uniform(10, 50)
        for date in dates:
            close = base_price * (1 + np.random.normal(0, 0.02))
            open_ = close * (1 + np.random.normal(0, 0.005))
            high = max(open_, close) * (1 + abs(np.random.normal(0, 0.01)))
            low = min(open_, close) * (1 - abs(np.random.normal(0, 0.01)))
            volume = np.random.randint(100000, 10000000)
            amount = volume * (open_ + high + low + close) / 4
            records.append({
                'date': date, 'code': code,
                'open': open_, 'high': high, 'low': low,
                'close': close, 'volume': volume, 'amount': amount
            })
            base_price = close
    
    return pd.DataFrame(records)


def main():
    print("=== Factor Library Smoke Test ===\n")
    
    # 生成模拟数据
    print("1. Generating mock data...")
    df = generate_mock_data(n_dates=60, n_codes=3)
    print(f"   Data shape: {df.shape}")
    
    # 测试 WQ101
    print("\n2. Computing WQ101 factors...")
    try:
        wq101_result = compute_wq101(df)
        print(f"   Success! Result shape: {wq101_result.shape}")
        non_null_rates = wq101_result.iloc[:, 2:].notna().mean()
        print(f"   Average non-null rate: {non_null_rates.mean():.1%}")
    except Exception as e:
        print(f"   Error: {e}")
        raise
    
    # 测试 GTJA191
    print("\n3. Computing GTJA191 factors...")
    try:
        gtja191_result = compute_gtja191(df)
        print(f"   Success! Result shape: {gtja191_result.shape}")
        non_null_rates = gtja191_result.iloc[:, 2:].notna().mean()
        print(f"   Average non-null rate: {non_null_rates.mean():.1%}")
    except Exception as e:
        print(f"   Error: {e}")
        raise
    
    # 测试批量计算
    print("\n4. Testing batch compute...")
    try:
        batch_result = batch_compute_factors(df, factor_sets=['wq101', 'gtja191'])
        print(f"   Success! Result shape: {batch_result.shape}")
    except Exception as e:
        print(f"   Error: {e}")
        raise

    print("\n5. Testing AI factor mining prototype...")
    try:
        _, _, mining_summary = mine_and_validate_factors(df, forward_periods=5)
        print("   Success! Top candidate factors:")
        print(mining_summary.head(5).to_string(index=False))
    except Exception as e:
        print(f"   Error: {e}")
        raise
    
    print("\n✅ All tests passed!")


if __name__ == '__main__':
    main()
