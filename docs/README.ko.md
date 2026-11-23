# BT 파라미터 최적화 — 밸런스 QA 프로토타입 (한국어 안내, 영어 README 는 저장소 루트)

게임과 학습 플랫폼을 분리해, **실제 게임과 주고받는 방식**으로 다음을 확인합니다.

- 같은 BT에 **숫자(가중치·임계값)만 학습**해서 직업 간 공정 비교가 가능한가
- 페르소나(공격형·안정형·효율형)별 최적 파라미터와 클리어 시간 매트릭스
- 판당 1회 결정(CMA-ES)과 결정 트리거 정책(MLP + OpenAI-ES, **IMPALA**)의 차이

> 수치는 장난감 게임(`game_sim`)의 값입니다. **경향과 크기 비교**에만 사용하세요.

## 구성

```
game_sim/     게임 대역 (BT·전투·데이터·TCP 서버)   ← 추후 Unity 빌드로 교체
balance_qa/   학습 플랫폼 (최적화·정책·IMPALA — torch CPU, 보상·평가·리포트)
docs/PROTOCOL.md   둘 사이의 계약 (TCP JSON Lines v1.2)
qa_specs/     페르소나 (퍼블리셔 정의)
experiments/  E0~E7 가설 검증
run/          PyCharm ▶ 실행 스크립트 (설정값만 고쳐서 실행)
unity_game/   실제 테스트 게임 (Unity 프로젝트) — 제작 규칙: unity_game/AGENT_GUIDE.md
tests/        game / learner / integration / independence
```

## 설치

```bash
pip install -r requirements.txt   # numpy + PyTorch CPU (Python 3.8+)
```

## 빠른 시작

```bash
python -m unittest discover -s tests -t .       # 테스트
python -m balance_qa check-game                 # 게임 대역 프로토콜 적합성 검사

# 게임 대역 4개를 자동으로 띄우고 학습
python -m balance_qa --workers 4 evaluate --cls warrior mage archer --persona stable -n 200
python -m balance_qa --workers 4 optimize --cls mage --persona stable --budget 3000
python -m balance_qa --workers 4 policy   --cls warrior --persona stable --budget 6000 \
    --init-params reports/<run_id>/params.json
python -m balance_qa --workers 4 sensitivity --cls archer --persona stable -n 100

# IMPALA (로컬 액터 프로세스 = 게임 인스턴스 수, V-trace 학습기)
python -m balance_qa --workers 8 impala --cls warrior --persona stable --budget 8000 \
    --init-params reports/<run_id>/params.json

# 클라우드 구조 미리 보기: 학습기는 대기, 액터는 따로 접속 (docs/DISTRIBUTED.md)
python -m balance_qa --workers 1 impala --cls warrior --persona stable --actors external --listen 127.0.0.1:7000 --token abc
python -m balance_qa actor --learner 127.0.0.1:7000 --token abc
```

## PyCharm 에서 실행

`run/` 폴더 스크립트의 맨 위 설정값만 고치고 ▶ Run. 상단 실행 목록 `QA` 폴더에도 등록되어 있습니다 (01 테스트 ~ 10 게임 대역 서버).
자세한 표는 [run/README.md](../run/README.md). 인터프리터는 `venv\Scripts\python.exe`.

## 화면으로 보기 (Unity 전투 뷰어)

```bash
# Unity 4개 중 1개를 창으로: 학습 판 표본이 재생된다 (창에서 '학습 판 자동 따라보기' 켜기)
python -m balance_qa --workers 4 --game-cmd "unity_game/Build/QaArena.exe -batchmode -nographics -qaPort {port}" --view 1 impala --cls warrior --persona stable
```
PyCharm: `00b 전체 사이클 (Unity 화면)` — 사이클 점검 후 같은 seed 로 손 튜닝 → CMA-ES → IMPALA 판을 창에 차례로 재생.

## 실제 게임(Unity) 연결

1. Unity 쪽에서 [docs/PROTOCOL.md](PROTOCOL.md) 를 구현 (부록 A에 C# 뼈대)
2. 빌드를 포트 인자와 함께 실행 → `python -m balance_qa check-game --game 127.0.0.1:7777` 통과 확인
3. 학습 명령에 연결 정보만 바꿔서 실행

```bash
# 이미 떠 있는 인스턴스들
python -m balance_qa --game 127.0.0.1:7777,127.0.0.1:7778 optimize --cls mage --persona stable
# 명령 템플릿으로 N개 실행
python -m balance_qa --workers 8 --game-cmd "Build/Game.exe -batchmode -nographics -qaPort {port}" optimize ...
```

게임 대역만 따로 띄울 수도 있습니다: `python -m game_sim serve --port 7777`

## 실험 (설계 문서 10장)

| 스크립트 | 가설 | 내용 |
|---|---|---|
| `experiments.e0_sanity` | — | 프로토콜 적합성, 처리량, 기본값 매트릭스, 필요 표본 수 |
| `experiments.e1_tuning_bias` | H1 | 손 튜닝 vs 동일 예산 최적화의 직업 순위·격차 |
| `experiments.e2_effect_size` | H2 | 파라미터 효과(OAT) vs 패치 효과 |
| `experiments.e3_patch_drift` | H3 | 패치 시나리오별 최적 파라미터 이동 |
| `experiments.e4_balance_break` | H4 | 정의서 범위 안 최속 조합 탐색 |
| `experiments.e5_persona_matrix` | H5 | 페르소나 × 직업 매트릭스 |
| `experiments.e6_convergence` | H6 | 무작위 탐색 vs CMA-ES 예산별 성능 |
| `experiments.e7_trigger_policy` | H7 | 판당 1회 vs 트리거 정책 (ES / IMPALA) |

```bash
python -m experiments.e1_tuning_bias --workers 4 [--quick] [--game host:port,...]
```

자세한 구조는 [docs/ARCHITECTURE.md](ARCHITECTURE.md).
