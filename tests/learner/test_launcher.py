"""게임 실행기: 화면(창) 모드 명령 만들기, 실행 파일 경로 처리 (프로세스 실행 없이)."""
import unittest
from pathlib import Path

from balance_qa.game_api.launcher import PROJECT_ROOT, CommandLauncher, view_command_from

UNITY = ["unity_game/Build/QaArena.exe", "-batchmode", "-nographics", "-qaPort", "{port}"]


class LauncherTest(unittest.TestCase):
    def test_view_command_drops_headless_flags_and_adds_window(self):
        v = view_command_from(UNITY)
        self.assertNotIn("-batchmode", v)
        self.assertNotIn("-nographics", v)
        self.assertEqual(v[:3], ["unity_game/Build/QaArena.exe", "-qaPort", "{port}"])
        self.assertIn("-screen-fullscreen", v)
        self.assertIn("-qaFollow", v)

    def test_first_n_instances_are_windowed(self):
        lc = CommandLauncher(UNITY, 3, ports=[7001, 7002, 7003], view=1)
        windowed = lc._cmd(7001, 0)
        headless = lc._cmd(7002, 1)
        self.assertNotIn("-batchmode", windowed)
        self.assertIn("-batchmode", headless)
        self.assertIn("7001", windowed)
        self.assertEqual(lc.view_endpoints, [("127.0.0.1", 7001)])

    def test_view_clamped_and_custom_view_command(self):
        lc = CommandLauncher(UNITY, 2, ports=[1, 2], view=5, view_command=["Viewer.exe", "-p", "{port}"])
        self.assertEqual(lc.view, 2)
        self.assertEqual(Path(lc._cmd(1, 0)[0]).name, "Viewer.exe")

    def test_relative_executable_resolved_from_project_root(self):
        exe = "run/run_tests.py"  # 실제로 있는 파일로 경로 처리만 확인
        lc = CommandLauncher([exe, "{port}"], 1, ports=[9])
        self.assertEqual(Path(lc._cmd(9)[0]), (PROJECT_ROOT / exe).resolve())


if __name__ == "__main__":
    unittest.main()
