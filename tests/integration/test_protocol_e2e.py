"""통합 테스트: 게임 대역 서버(스레드) ↔ 학습 플랫폼 클라이언트.

테스트에서만 두 패키지를 함께 import 한다 (패키지 코드는 서로 import 하지 않음).
"""
import unittest

from balance_qa.control.param_source import StaticParamSource
from balance_qa.game_api.client import EpisodeRequest, GameClient
from balance_qa.game_api.conformance import ConformanceChecker
from balance_qa.game_api.launcher import LocalSimLauncher
from balance_qa.session import QASession
from game_sim.server.server import GameServer


class ProtocolE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servers = [GameServer(port=0) for _ in range(2)]
        for s in cls.servers:
            s.start_in_thread()
        cls.endpoints = [s.address for s in cls.servers]

    @classmethod
    def tearDownClass(cls):
        for s in cls.servers:
            s.stop()

    def test_conformance_passes(self):
        client = GameClient(*self.endpoints[0])
        try:
            checker = ConformanceChecker(client)
            results = checker.run()
            self.assertTrue(checker.passed, "\n".join(r.line() for r in results))
        finally:
            client.close()

    def test_session_evaluate_and_optimize(self):
        with QASession(endpoints=self.endpoints) as s:
            self.assertEqual(s.pool.size, 2)
            self.assertIn("mage", s.class_names())
            base = s.evaluate("mage", "stable", n=8)
            self.assertEqual(base.n_valid, 8)
            out = s.optimize("mage", "stable", budget=60, k=2, popsize=6, eval_n=6, verbose=False)
            self.assertEqual(out.training.episodes_used, 60)
            self.assertEqual(set(out.params) >= {"w_burst", "survival_hp_threshold"}, True)
            self.assertEqual(out.params["survival_hp_threshold"], 0.8)  # 페르소나 값 유지

    def test_session_policy_uses_triggers(self):
        with QASession(endpoints=self.endpoints) as s:
            out = s.train_policy("warrior", "stable", budget=32, k=2, popsize=4, eval_n=4, verbose=False)
            self.assertEqual(out.training.episodes_used, 32)
            self.assertTrue(all(h.invalid_ratio == 0 for h in out.training.history))

    def test_session_impala_end_to_end(self):
        """스레드 액터 2개(게임 2개) 비동기 + V-trace 학습기 + 결정론적 평가."""
        with QASession(endpoints=self.endpoints) as s:
            self.assertTrue(s.game.supports_segment_rewards)
            out = s.train_impala("warrior", "stable", budget=48, batch_size=8, hidden=(16,), eval_n=4,
                                 log_every=2, actors="threads", verbose=False)
            self.assertEqual(out.training.episodes_used, 48)
            self.assertEqual(out.method, "impala")
            self.assertIsNotNone(out.model)
            self.assertGreaterEqual(len(out.training.history), 1)
            self.assertTrue(all(h.invalid_ratio == 0 for h in out.training.history))
            self.assertEqual(out.evaluation.n_valid, 4)
            # 평가 정책은 결정론적: 같은 seed 두 번 → 같은 결과
            a = s.evaluator.run("warrior", "base", out.source, [7])[0].to_dict()
            b = s.evaluator.run("warrior", "base", out.source, [7])[0].to_dict()
            self.assertEqual(a, b)
            self.assertEqual(a["triggers_fired"], 4)

    def test_impala_local_actor_processes(self):
        """processes 모드: 게임마다 액터 프로세스 1개, 학습 중 세션 연결을 넘겼다가 평가 때 복구."""
        with QASession(endpoints=self.endpoints) as s:
            out = s.train_impala("warrior", "stable", budget=40, batch_size=8, hidden=(16,), eval_n=4,
                                 log_every=2, actors="processes", verbose=False)
            self.assertEqual(out.training.episodes_used, 40)
            self.assertEqual(out.evaluation.n_valid, 4)        # 평가 = 세션 연결 복구 확인
            self.assertTrue(all(c.connected for c in s.pool.clients))

    def test_impala_external_actor(self):
        """external 모드: 학습기는 대기, 액터(RemoteActor)는 따로 접속. 토큰이 틀리면 거부."""
        import threading

        from balance_qa.game_api.launcher import free_port
        from balance_qa.rl.remote_actor import ActorConfigError, RemoteActor

        port = free_port()
        box = {}
        with QASession(endpoints=[self.endpoints[0]]) as s:
            def learner():
                box["out"] = s.train_impala("mage", "stable", budget=24, batch_size=8, hidden=(16,), eval_n=2,
                                            log_every=1, actors="external", listen=("127.0.0.1", port),
                                            token="tok", idle_timeout=60, verbose=False)
            t = threading.Thread(target=learner)
            t.start()
            with self.assertRaises(ActorConfigError):
                RemoteActor(("127.0.0.1", port), GameClient(*self.endpoints[1]), "bad", token="nope").run()
            client = GameClient(*self.endpoints[1])
            try:
                stats = RemoteActor(("127.0.0.1", port), client, "good", token="tok").run()
            finally:
                client.close()
            t.join(timeout=120)
            self.assertGreaterEqual(stats["episodes"], 24)
            self.assertEqual(box["out"].training.episodes_used, 24)

    def test_pool_results_match_single_client(self):
        """병렬 풀과 단일 연결의 결과가 같아야 함 (게임 결정성 + 순서 보존)."""
        src = StaticParamSource({})
        with QASession(endpoints=self.endpoints) as s:
            pooled = s.evaluator.run("archer", "base", src, [11, 12, 13, 14])
        client = GameClient(*self.endpoints[0]).connect()
        try:
            single = [client.run_episode(EpisodeRequest("archer", seed), src) for seed in [11, 12, 13, 14]]
        finally:
            client.close()
        self.assertEqual([r.to_dict() for r in pooled], [r.to_dict() for r in single])


class LauncherTest(unittest.TestCase):
    def test_local_sim_launcher_subprocess(self):
        with LocalSimLauncher(1) as launcher:
            client = GameClient(*launcher.endpoints[0]).connect()
            try:
                self.assertEqual(client.hello_info["game"], "game_sim")
            finally:
                client.close()


if __name__ == "__main__":
    unittest.main()
