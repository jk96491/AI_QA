"""게임(game_sim) 과 학습 플랫폼(balance_qa) 의 독립성 검사.

- game_sim 은 balance_qa, torch 를 import 하지 않는다 (Unity 로 교체될 쪽)
- balance_qa 는 game_sim 을 import 하지 않는다 (프로세스·포트로만 연결)
- play_agent 는 game_sim · balance_qa · torch · btqa_distill 을 import 하지 않는다 (학습 결과 파일만 읽고 게임과는 TCP 로만).
  증류에서 게임 고유 처리(전처리·보상·판 준비)는 함수로만 두고 SDK 명령에 '모듈:함수' 이름으로 넘긴다 (학습은 venv_distill 의 SDK)
- SDK(btqa_game·btqa_play)는 별도 레포 btqa_sdk 를 직접 참조한다 — SDK 자체의 독립성은 그 레포 테스트가 검사
- 학습 쪽(balance_qa, play_agent) 은 게임 쪽 SDK 를 import 하지 않는다 (계약은 프로토콜 문서뿐).
  play_agent 는 클라이언트 쪽 SDK btqa_play 위에 로드아웃·응답기를 얹는다
"""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def imported_modules(package: str):
    for path in (ROOT / package).rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    yield path, a.name
            elif isinstance(node, ast.ImportFrom) and node.module:
                yield path, node.module


class IndependenceTest(unittest.TestCase):
    def assert_no_import(self, package, forbidden):
        bad = [
            "%s: %s" % (p.relative_to(ROOT), m)
            for p, m in imported_modules(package)
            if any(m == f or m.startswith(f + ".") for f in forbidden)
        ]
        self.assertEqual(bad, [], "금지된 import 발견")

    def test_game_does_not_import_learner_or_torch(self):
        self.assert_no_import("game_sim", ["balance_qa", "torch", "btqa_play", "play_agent"])

    def test_learner_does_not_import_game(self):
        self.assert_no_import("balance_qa", ["game_sim", "btqa_game", "btqa_play", "play_agent"])

    def test_play_agent_imports_only_files_and_tcp(self):
        self.assert_no_import("play_agent", ["game_sim", "balance_qa", "torch", "btqa_game", "btqa_distill",
                                             "transformers", "peft"])


if __name__ == "__main__":
    unittest.main()
