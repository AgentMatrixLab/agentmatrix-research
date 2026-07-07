from research_core.data_loader.quant_api_client import QuantApiClient

client = QuantApiClient()
print("配置:", client.config)

try:
    status = client.status(check_remote=True)
    print("状态:", status)
except Exception as e:
    print("错误:", e)

try:
    factors = client.factor_monthly_factors()
    print("可用因子:", factors)
except Exception as e:
    print("获取因子列表错误:", e)