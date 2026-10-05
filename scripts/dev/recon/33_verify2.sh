cd /home/data/agentmatrix_run/agentmatrix
sed -i 's/\r$//' scripts/dev/run_sharded.sh
bash -n scripts/dev/run_sharded.sh && echo "BASH SYNTAX OK"
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
import ast, pathlib
ast.parse(pathlib.Path("/home/data/agentmatrix_run/agentmatrix/scripts/build_factor_values.py").read_text(encoding="utf-8"))
print("PYTHON SYNTAX OK")
PYEOF
grep -c "emit(" scripts/build_factor_values.py
