from __future__ import annotations

import argparse
import json
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def fetch_json(url: str) -> object:
    with urlopen(url, timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f"{url} returned HTTP {response.status}")
        return json.load(response)


def verify(base_url: str, *, require_strategy: bool, expected_status: str | None) -> dict:
    base = base_url.rstrip("/")
    health = fetch_json(f"{base}/healthz")
    strategies = fetch_json(f"{base}/api/strategy-dashboard/strategies")
    operating_status = fetch_json(f"{base}/api/strategy-dashboard/status")
    if not isinstance(health, dict) or health.get("status") != "ok":
        raise RuntimeError("health contract is not healthy")
    if not isinstance(strategies, list):
        raise RuntimeError("strategy-list contract is not an array")
    if health.get("strategies") != len(strategies):
        raise RuntimeError("health strategy count differs from strategy-list length")
    if require_strategy and not strategies:
        raise RuntimeError("strategy library is empty")
    if expected_status:
        mismatched = [item.get("id") for item in strategies if item.get("publication_status") != expected_status]
        if mismatched:
            raise RuntimeError(f"unexpected publication status for: {', '.join(map(str, mismatched))}")
    return {
        "status": "passed",
        "base_url": base,
        "strategies": len(strategies),
        "publication_status": expected_status,
        "data_version": (operating_status.get("data") or {}).get("data_version"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a deployed strategy dashboard")
    parser.add_argument("--base-url", default="http://127.0.0.1:8813")
    parser.add_argument("--require-strategy", action="store_true")
    parser.add_argument("--expected-publication-status", choices=["published", "review"])
    args = parser.parse_args()
    try:
        result = verify(
            args.base_url,
            require_strategy=args.require_strategy,
            expected_status=args.expected_publication_status,
        )
    except (HTTPError, URLError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
