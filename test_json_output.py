import urllib.request
import json

url = "http://127.0.0.1:8012/api/agents/factor-lab/quant-api/research"
body = json.dumps({
    "factors": ["ret_1m", "roe_ttm"],
    "symbols": ["000001.SZ", "000002.SZ"],
    "start_date": "2023-01-01",
    "end_date": "2024-01-01",
    "factor_set": "quant_api"
}).encode("utf-8")

req = urllib.request.Request(url, data=body, method="POST")
req.add_header("Content-Type", "application/json")

with urllib.request.urlopen(req, timeout=60) as response:
    raw = response.read().decode("utf-8")
    print("Raw response:")
    print(raw)
    print()
    try:
        parsed = json.loads(raw)
        print("Parsed successfully!")
        print("Job ID:", parsed.get("job_id"))
    except json.JSONDecodeError as e:
        print("JSON parse error:", e)