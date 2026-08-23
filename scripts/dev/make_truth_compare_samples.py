"""从演示真值构造"用户上传"样本，用于测试真值对照器的分支。

逻辑：标准真值是我们自己生成的，所以从真值里抽一列当"用户提交值"，
理论上必须 100% 对上（自洽性测试）；扰动版必须对不上（失败分支）。
"""
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # 项目根目录（本文件在 scripts/dev/ 下）
TRUTH = ROOT / "data" / "factor_lab" / "alpha101_truth_template_101f_60d_5c_s29.csv"
OUT = ROOT / "data" / "factor_lab" / "samples"
OUT.mkdir(parents=True, exist_ok=True)

truth = pd.read_csv(TRUTH)

# 宽表转长表：取 alpha1 一列，改成上传契约的列名 date / symbol / factor_value
base = truth[["date", "code", "alpha1"]].rename(
    columns={"code": "symbol", "alpha1": "factor_value"}
).dropna(subset=["factor_value"])  # 丢掉窗口预热期的空值行

# 样本1：原样抽取 → 对照结果必须是 passed（exact_match_ratio = 1.0）
base.to_csv(OUT / "factor_values_alpha1_pass.csv", index=False)

# 样本2：整体扰动（×1.5 + 0.001，远超 1e-8 容差）→ 必须是 failed
perturbed = base.copy()
perturbed["factor_value"] = perturbed["factor_value"] * 1.5 + 0.001
perturbed.to_csv(OUT / "factor_values_alpha1_perturbed.csv", index=False)

print("truth rows:", len(truth), "| alpha1 non-null rows:", len(base))
print("date range:", base["date"].min(), "~", base["date"].max())
print("files written to:", OUT)