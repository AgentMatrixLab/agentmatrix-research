#!/bin/bash
# agentmatrix-research 一键安装
# 用法: bash setup.sh

set -e
echo "🚀 AgentMatrix Research — 一键安装"
echo ""

# 1. Python 环境
echo "[1/4] 检查 Python..."
python3 --version || { echo "需要 Python 3.10+"; exit 1; }

# 2. 安装依赖
echo "[2/4] 安装 Python 依赖..."
pip install numpy pandas scipy flask flask-cors pytest -q
[ -f requirements-factor-lab.txt ] && pip install -r requirements-factor-lab.txt -q

# 3. 冒烟测试
echo "[3/4] 运行冒烟测试..."
python3 -c "
from research_core.factor_lab.factor_validate import validate_factor
r = validate_factor('smoke_test', ic_series=[0.02, -0.01, 0.03, 0.01, 0.02]*10)
print(f'  验证框架: score={r[\"confidence\"][\"score\"]} {r[\"confidence\"][\"verdict\"]}')
" && echo "  ✅ 核心功能正常" || echo "  ⚠️ 验证框架加载失败（非关键）"

# 4. 文档
echo "[4/4] 文档索引..."
echo "  README:          仓库总览"
echo "  CONTRIBUTING.md: 贡献指南"
echo "  docs/templates/: 因子提交模板"
echo ""
echo "✅ 安装完成！"
echo "下一步：python3 scripts/quick_start.py 跑一个示例因子"
