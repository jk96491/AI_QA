"""BT-QA Game SDK 사본 검사.

이 저장소는 SDK 원본(별도 레포 btqa_sdk)을 참조하지 않고 사본만 쓴다:
  btqa_game/  ·  unity_game/Packages/com.btqa.game  ·  docs/PROTOCOL.md   (run/run_sync_sdk.py 로 복사)

- 사본이 실제로 쓰이는지 (설치본·외부 경로가 끼어들지 않는지) — 항상 검사
- 원본과 같은지 — 원본(btqa_sdk/ 또는 환경변수 BTQA_SDK)이 있을 때만. 다르면 run/run_sync_sdk.py 실행
"""
import json
import runpy
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SYNC = runpy.run_path(str(ROOT / "run" / "run_sync_sdk.py"))


class SdkCopiesUsedTest(unittest.TestCase):
    def test_python_uses_repo_copy(self):
        import btqa_game

        self.assertEqual(Path(btqa_game.__file__).resolve().parent, ROOT / "btqa_game",
                         "btqa_game 이 저장소 사본이 아닌 곳에서 로드됨 (pip 로 설치된 btqa-game 을 지울 것)")

    def test_game_sim_uses_sdk(self):
        from btqa_game import EpisodeHost, QaGameServer
        from game_sim.server.server import GameServer
        from game_sim.server.session import GameSimHost

        self.assertTrue(issubclass(GameServer, QaGameServer))
        self.assertTrue(issubclass(GameSimHost, EpisodeHost))

    def test_unity_uses_embedded_copy(self):
        manifest = (ROOT / "unity_game" / "Packages" / "manifest.json").read_text(encoding="utf-8")
        self.assertNotIn("com.btqa.game", manifest, "embedded 패키지는 manifest 항목 없이 Packages/ 에서 읽힌다")
        self.assertNotIn("btqa_sdk", manifest)
        lock = json.loads((ROOT / "unity_game" / "Packages" / "packages-lock.json").read_text(encoding="utf-8"))
        entry = lock["dependencies"].get("com.btqa.game")
        if entry is not None:   # Unity 가 한 번이라도 해석했으면
            self.assertEqual(entry["source"], "embedded")

    def test_no_runtime_reference_to_sdk_repo(self):
        texts = [(ROOT / "requirements.txt").read_text(encoding="utf-8"),
                 (ROOT / "unity_game" / "QaTools~" / "compilecheck" / "CompileCheck.csproj").read_text(encoding="utf-8")]
        for t in texts:
            self.assertNotIn("btqa_sdk\\", t)
            self.assertNotIn("./btqa_sdk", t)

    def test_versions_agree(self):
        from btqa_game import PROTOCOL_VERSION, __version__

        pkg = json.loads((ROOT / "unity_game" / "Packages" / "com.btqa.game" / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(pkg["version"], __version__)
        self.assertIn("v%s" % PROTOCOL_VERSION, (ROOT / "docs" / "PROTOCOL.md").read_text(encoding="utf-8").splitlines()[0])


class SdkCopiesMatchOriginalTest(unittest.TestCase):
    def test_copies_match_sdk_original(self):
        sdk = SYNC["sdk_root"]()
        if not (sdk / "python" / "btqa_game").exists():
            self.skipTest("SDK 원본 없음 (%s) — 별도 레포를 btqa_sdk/ 에 clone 하거나 BTQA_SDK 지정" % sdk)
        self.assertEqual(SYNC["differences"](sdk), [], "run/run_sync_sdk.py 로 동기화 필요")


if __name__ == "__main__":
    unittest.main()
