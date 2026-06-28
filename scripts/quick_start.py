#!/usr/bin/env python3
"""
快速开始 — 跑一个示例因子，体验完整的 mine→reproduce→validate 流程
"""
import json, math
from research_core.factor_lab.factor_validate import validate_factor

print("🧪 AgentMatrix Research — 快速开始")
print("=" * 50)

# 1. 定义一个因子
print("\n1️⃣ 定义因子: 成交量加速度")
print("   公式: vol_accel = volume的2阶差分")
print("   假设: 成交量加速度大的股票短期会涨")

# 2. 模拟IC时序（实际应该从Compute Lab跑出）
ic_series = [0.03, -0.01, 0.02, 0.04, 0.01, 0.02, -0.02, 0.03, 0.01, 0.02,
             0.01, 0.03, -0.01, 0.02, 0.01, 0.03, 0.00, 0.02, 0.01, 0.02] * 3
print(f"\n2️⃣ IC时序: {len(ic_series)}个月")

# 3. 验证因子
result = validate_factor('VolAccel', ic_series=ic_series)
c = result['confidence']
print(f"\n3️⃣ 验证结果:")
print(f"   综合评分: {c['score']}/100")
print(f"   评级: {c['verdict']}")
print(f"   解读: {c['interpretation']}")

# 4. 提交因子
print(f"\n4️⃣ 提交因子的步骤:")
print("   ① 把因子代码放到 research_core/factor_lab/ 或 submissions/")
print("   ② 跑 factor_validate.py 拿到验证评分")
print("   ③ 如果评分>=70，开PR到 feat/ 分支")
print("   ④ CI会自动跑验证并在PR中评论")
print("   ⑤ 评分>=70、reviewer通过后合并到main")

print(f"\n✅ 流程演示完成。因子评分: {c['score']} / {c['verdict']}")
