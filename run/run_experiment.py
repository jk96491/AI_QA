"""[PyCharm ▶] 가설 검증 실험 E0~E7 (설계 문서 10장)."""
from _bootstrap import opt, run_module

# ===================== 설정 =====================
EXPERIMENT = "e1_tuning_bias"
#   e0_sanity          프로토콜 적합성·처리량·기본값 매트릭스·필요 표본 수
#   e1_tuning_bias     H1 손 튜닝 vs 동일 예산 최적화
#   e2_effect_size     H2 파라미터 효과 vs 패치 효과
#   e3_patch_drift     H3 패치별 최적 파라미터 이동
#   e4_balance_break   H4 범위 내 최속 조합 탐색
#   e5_persona_matrix  H5 페르소나 × 직업 매트릭스
#   e6_convergence     H6 무작위 탐색 vs CMA-ES
#   e7_trigger_policy  H7 판당 1회 vs 트리거 정책 (ES / IMPALA)
QUICK = True              # True: 축소 실행(동작 확인용), False: 본 실행
EXTRA_ARGS = []           # 실험별 추가 인자 예: ["--persona", "aggressive"], ["--classes", "warrior"]

GAME = None               # Unity 등 접속: "127.0.0.1:7777,..."
WORKERS = 4
SEED = 0
# ================================================

if __name__ == "__main__":
    argv = ["--workers", str(WORKERS), "--seed", str(SEED)] + opt("--game", GAME) + list(EXTRA_ARGS)
    if QUICK:
        argv.append("--quick")
    run_module("experiments." + EXPERIMENT, argv)
