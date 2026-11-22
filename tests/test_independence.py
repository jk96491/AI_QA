"""게임(game_sim) 과 학습 플랫폼(balance_qa) 의 독립성 검사.

- game_sim 은 balance_qa, torch 를 import 하지 않는다 (Unity 로 교체될 쪽)
- balance_qa 는 game_sim 을 import 하지 않는다 (프로세스·포트로만 연결)
- play_agent 는 game_sim · balance_qa · torch 를 import 하지 않는다 (학습 결과 파일만 읽고 게임과는 TCP 로만)
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
        self.assert_no_import("game_sim", ["balance_qa", "torch"])

    def test_learner_does_not_import_game(self):
        self.assert_no_import("balance_qa", ["game_sim"])

    def test_play_agent_imports_only_files_and_tcp(self):
        self.assert_no_import("play_agent", ["game_sim", "balance_qa", "torch"])


if __name__ == "__main__":
    unittest.main()
