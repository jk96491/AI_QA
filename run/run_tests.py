"""[PyCharm ▶] 전체 테스트 (game / learner / integration / independence)."""
import sys
import unittest

from _bootstrap import ROOT, setup

# ===================== 설정 =====================
PATTERN = "test*.py"     # 특정 파일만: "test_rl.py"
START_DIR = "tests"      # 일부만: "tests/learner"
VERBOSITY = 2
# ================================================

if __name__ == "__main__":
    setup()
    suite = unittest.defaultTestLoader.discover(str(ROOT / START_DIR), pattern=PATTERN, top_level_dir=str(ROOT))
    result = unittest.TextTestRunner(verbosity=VERBOSITY).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
