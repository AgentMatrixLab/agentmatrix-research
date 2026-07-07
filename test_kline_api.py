import os
os.environ["QUANT_API_TOKEN"] = "sk-upload-wj28IRgJB5fbbUEFUuZfiIr06TE"
os.environ["QUANT_API_BASE_URL"] = "http://115.159.73.134:8765"

from research_core.data_loader.quant_api_client import QuantApiClient
import json

client = QuantApiClient()

print("测试 kline_1d 接口...")
try:
    data = client.kline_1d({"symbol": "000001.SZ", "order": "asc", "limit": 10})
    print("返回:", json.dumps(data, ensure_ascii=False, indent=2))
except Exception as e:
    print("错误:", e)

print("\n测试 factor_monthly 接口...")
try:
    data = client.factor_monthly({"factor": "rsi_14", "limit": 5})
    print("返回:", json.dumps(data, ensure_ascii=False, indent=2))
except Exception as e:
    print("错误:", e)