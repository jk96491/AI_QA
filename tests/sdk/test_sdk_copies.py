"""BT-QA SDK 참조·사본 검사.

- Python(btqa_game·btqa_play) = 별도 레포 btqa_sdk 를 **직접 참조** (venv 편집 설치, 사용자 결정 2026-11-24). 저장소 루트에 사본이 없어야 한다
- Unity 패키지·계약 문서 = 사본 (unity_game/Packages/com.btqa.game · docs/PROTOCOL.md · docs/PLAY_PROTOCOL.md, run/run_sync_sdk.py)
  — btqa_sdk 가 있으면 사본 == 원본
"""
import json
import runpy
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SYNC = runpy.run_path(str(ROOT / "run" / "run_sync_sdk.py"))
SDK_PY = SYNC["sdk_root"]() / "python"
HINT = "btqa_sdk 를 clone 하고 venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e ./btqa_sdk (requirements.txt)"


class SdkReferenceTest(unittest.TestCase):
    def test_python_uses_sdk_repo(self):
        import btqa_game
        import btqa_play

        for m in (btqa_game, btqa_play):
            self.assertEqual(Path(m.__file__).resolve().parent.parent, SDK_PY.resolve(), "%s 이 btqa_sdk 가 아닌 곳에서 로드됨 — %s" % (m.__name__, HINT))

    def test_no_python_copies_in_repo(self):
        for name in ("btqa_game", "btqa_play"):
            self.assertFalse((ROOT / name).exists(), "루트 %s/ 사본은 두지 않는다 (btqa_sdk 직접 참조)" % name)

    def test_play_agent_uses_play_sdk(self):
        import btqa_play.relay
        from play_agent.relay import PilotRelay

        self.assertTrue(issubclass(PilotRelay, btqa_play.relay.PilotRelay))
        self.assertFalse((ROOT / "play_agent" / "client.py").exists(), "프로토콜 클라이언트는 SDK btqa_play 에만")

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
        # Unity 는 embedded 사본만 쓴다 (빌드가 btqa_sdk 폴더에 의존하지 않게)
        texts = [(ROOT / "unity_game" / "QaTools~" / "compilecheck" / "CompileCheck.csproj").read_text(encoding="utf-8")]
        for t in texts:
            self.assertNotIn("btqa_sdk\\", t)
            self.assertNotIn("./btqa_sdk", t)

    def test_versions_agree(self):
        import btqa_play
        from btqa_game import PROTOCOL_VERSION, __version__

        self.assertEqual(btqa_play.__version__, __version__)
        self.assertIn("v%s" % btqa_play.PROTOCOL_VERSION, (ROOT / "docs" / "PLAY_PROTOCOL.md").read_text(encoding="utf-8").splitlines()[0])

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
