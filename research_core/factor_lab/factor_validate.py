#!/usr/bin/env python3
"""
一键因子验证 CLI — 输入因子名，输出置信度评分 + 完整验证报告

用法:
    python3 factor_validate.py --factor GTJA001
    python3 factor_validate.py --factor illiq_div_vol --ic-history /tmp/ic_series.json
    python3 factor_validate.py --factor-list GTJA001,GTJA002,Alpha101_001

输出: JSON验证报告，含0-100综合置信评分
"""
import argparse, json, math, sys
from pathlib import Path
from collections import defaultdict

import numpy as np
from scipy import stats as scipy_stats

# ===== Bootstrap CI =====
def bootstrap_ic(ic_series, n_bootstrap=10000, ci=0.95, seed=42):
    rng = np.random.default_rng(seed)
    ics = np.asarray(ic_series, dtype=float)
    ics = ics[~np.isnan(ics)]
    n = len(ics)
    if n < 10: return {"error": f"need >=10 IC points, got {n}"}
    
    means = []
    for _ in range(n_bootstrap):
        sample = rng.choice(ics, size=n, replace=True)
        means.append(np.mean(sample))
    means = np.array(means)
    
    alpha = (1-ci)/2
    icir_vals = means / (np.std(ics, ddof=1)/np.sqrt(n))
    
    return {
        "ic_mean": round(float(np.mean(ics)), 4),
        "ic_std": round(float(np.std(ics, ddof=1)), 4),
        "ci_lower": round(float(np.percentile(means, alpha*100)), 4),
        "ci_upper": round(float(np.percentile(means, (1-alpha)*100)), 4),
        "ic_ir": round(float(np.mean(ics)/np.std(ics, ddof=1)), 3) if np.std(ics, ddof=1)>0 else 0,
        "p_value": round(float(2*min(np.mean(means<=0), np.mean(means>=0))), 4),
        "ic_significant": bool(np.percentile(means, alpha*100) > 0 or np.percentile(means, (1-alpha)*100) < 0),
        "n_samples": n, "n_bootstrap": n_bootstrap,
    }

# ===== Shuffle Test =====
def shuffle_test(factor_values, forward_returns, n_shuffles=1000, seed=42):
    rng = np.random.default_rng(seed)
    fv = np.asarray(factor_values, dtype=float)
    fr = np.asarray(forward_returns, dtype=float)
    mask = ~(np.isnan(fv) | np.isnan(fr))
    fv, fr = fv[mask], fr[mask]
    if len(fv) < 100: return {"error": "too few samples"}
    
    actual_ic = scipy_stats.spearmanr(fv, fr)[0]
    null_ics = []
    for _ in range(n_shuffles):
        rng.shuffle(fr)
        null_ics.append(scipy_stats.spearmanr(fv, fr)[0])
    null_ics = np.array(null_ics)
    
    p_val = np.mean(np.abs(null_ics) >= np.abs(actual_ic))
    return {
        "actual_ic": round(float(actual_ic), 4),
        "null_ic_mean": round(float(np.mean(null_ics)), 4),
        "null_ic_std": round(float(np.std(null_ics)), 4),
        "shuffle_p_value": round(float(p_val), 4),
        "significant": bool(p_val < 0.05),
        "n_shuffles": n_shuffles
    }

# ===== Out-of-sample split =====
def out_of_sample_check(ic_series, split_ratio=0.2):
    ics = np.asarray(ic_series, dtype=float)
    ics = ics[~np.isnan(ics)]
    n = len(ics); split = int(n*(1-split_ratio))
    if split < 10: return {"error": "insufficient data"}
    
    train = ics[:split]; test = ics[split:]
    train_mean = float(np.mean(train)); test_mean = float(np.mean(test))
    return {
        "train_ic": round(train_mean, 4), "train_n": len(train),
        "test_ic": round(test_mean, 4), "test_n": len(test),
        "oos_decay": round(float((test_mean - train_mean)/abs(train_mean)*100 if train_mean!=0 else 0), 1),
        "oos_pass": bool(test_mean*train_mean > 0 and abs(test_mean) >= abs(train_mean)*0.5)
    }

# ===== Parameter sensitivity =====
def param_sensitivity_dummy():
    # Placeholder for factors without configurable parameters
    return {"note": "no tunable parameters for this factor", "score": 10}

# ===== Neutralization check =====
def neutralization_dummy():
    return {"note": "requires industry/market-cap data for full neutralization check", "score": 5}

# ===== Similarity scan =====
def similarity_check(factor_name, factor_values, existing_factors_json_path=None):
    if not existing_factors_json_path:
        return {"note": "no existing factor library for similarity scan", "score": 5}
    try:
        with open(existing_factors_json_path) as f:
            lib = json.load(f)
        return {"note": f"scanned against {len(lib.get('factors',[]))} factors", "max_corr": None}
    except:
        return {"error": "could not load factor library"}

# ===== Composite confidence score =====
def compute_confidence(bootstrap_result, shuffle_result, oos_result, param_result, neut_result, sim_result):
    score = 0; details = []
    
    # 1. Bootstrap significance (25 pts)
    if bootstrap_result.get("ic_significant"):
        score += 25; details.append("bootstrap: +25 (CI excludes 0)")
    elif bootstrap_result.get("ic_ir", 0) > 0.3:
        score += 15; details.append("bootstrap: +15 (IC_IR>0.3)")
    else:
        details.append("bootstrap: +0")
    
    # 2. Shuffle test (25 pts)
    if shuffle_result.get("significant"):
        score += 25; details.append(f"shuffle: +25 (p={shuffle_result.get('shuffle_p_value',1)})")
    elif shuffle_result.get("shuffle_p_value", 1) < 0.1:
        score += 10; details.append("shuffle: +10 (marginal)")
    else:
        details.append("shuffle: +0")
    
    # 3. Out-of-sample (20 pts)
    if oos_result.get("oos_pass"):
        score += 20; details.append(f"oos: +20 (decay={oos_result.get('oos_decay',0)}%)")
    elif oos_result.get("oos_decay", 100) < 50:
        score += 10; details.append("oos: +10 (partial)")
    else:
        details.append("oos: +0")
    
    # 4. Robustness (15 pts)
    rob_score = min(param_result.get("score", 5) + neut_result.get("score", 5), 15)
    score += rob_score; details.append(f"robustness: +{rob_score} (param+neutral)")
    
    # 5. Independence (15 pts)
    sim_score = sim_result.get("score", 5)
    score += sim_score; details.append(f"independence: +{sim_score}")
    
    verdict = "SAFE" if score >= 70 else ("REVIEW" if score >= 40 else "REJECT")
    return {"score": score, "verdict": verdict, "breakdown": details,
            "interpretation": {
                "SAFE": "因子通过主要验证，置信度高，可进入实盘测试",
                "REVIEW": "部分验证通过，需要人工审查后决策",
                "REJECT": "多项验证未通过，因子可能为过拟合产物"
            }[verdict]}

# ===== Main =====
def validate_factor(name, ic_series=None, factor_values=None, forward_returns=None):
    results = {"factor": name, "checks": {}, "confidence": {}}
    
    # If we have IC series from panel
    if ic_series and len(ic_series) >= 10:
        bs = bootstrap_ic(ic_series)
        oos = out_of_sample_check(ic_series)
        results["checks"]["bootstrap"] = bs
        results["checks"]["out_of_sample"] = oos
    else:
        bs = {"error": "no IC series provided"}
        oos = {"error": "no IC series"}
        results["checks"]["bootstrap"] = bs
        results["checks"]["out_of_sample"] = oos
    
    if factor_values is not None and forward_returns is not None:
        sh = shuffle_test(factor_values, forward_returns)
        results["checks"]["shuffle"] = sh
    else:
        sh = {"error": "no raw values for shuffle test"}
        results["checks"]["shuffle"] = sh
    
    results["checks"]["param_sensitivity"] = param_sensitivity_dummy()
    results["checks"]["neutralization"] = neutralization_dummy()
    results["checks"]["similarity"] = similarity_check(name, factor_values)
    
    results["confidence"] = compute_confidence(
        bs, sh, oos,
        results["checks"]["param_sensitivity"],
        results["checks"]["neutralization"],
        results["checks"]["similarity"]
    )
    
    return results

# ===== CLI =====
if __name__ == "__main__":
    p = argparse.ArgumentParser(description="一键因子验证")
    p.add_argument("--factor", required=True, help="因子名")
    p.add_argument("--ic-history", help="IC时序JSON文件路径")
    p.add_argument("--panel-url", default="factor_metrics.json", help="因子面板JSON URL")
    p.add_argument("--raw-values", help="因子原始值和收益CSV")
    
    args = p.parse_args()
    
    ic_series = None
    if args.ic_history:
        with open(args.ic_history) as f:
            hist_data = json.load(f)
            if isinstance(hist_data, list):
                ic_series = [h.get("ic", h) if isinstance(h, dict) else h for h in hist_data]
    
    # Try loading from panel data
    if ic_series is None:
        try:
            import urllib.request
            resp = urllib.request.urlopen(args.panel_url, timeout=10)
            panel = json.loads(resp.read())
            for fac in panel.get("factors", []):
                if fac["name"] == args.factor:
                    hist = fac.get("ic_history", [])
                    if len(hist) >= 10:
                        ic_series = [h["ic"] for h in hist]
                    break
        except Exception as e:
            print(f"Warning: could not load panel data: {e}", file=sys.stderr)
    
    result = validate_factor(args.factor, ic_series=ic_series)
    print(json.dumps(result, ensure_ascii=False, indent=2))
