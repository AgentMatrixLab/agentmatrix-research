import sys
sys.path.insert(0, 'scripts')

from eval_guard.adapter import load_run

def test_load_run():
    job_id = "alpha101-c015efeba388"
    try:
        run = load_run(job_id)
        
        print(f"=== 产物加载结果 ===")
        print(f"job_id: {run.job_id}")
        print(f"status: {run.status}")
        print(f"evaluation 是否加载到: {'是' if run.evaluation else '否'}")
        print(f"proof_report 是否加载到: {'是' if run.proof_report else '否'}")
        print(f"收到 truth_compare 数量: {len(run.truth_compares)}")
        print(f"missing 列表: {run.missing}")
        
        if run.truth_compares:
            print(f"\ntruth_compare 因子列表: {list(run.truth_compares.keys())}")
        
    except Exception as e:
        print(f"加载失败: {e}")

if __name__ == "__main__":
    test_load_run()
