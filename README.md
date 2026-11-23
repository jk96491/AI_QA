# BT-QA — Reinforcement learning for game balance QA, decoupled from the game

**Designers own the behavior tree. RL learns only the weights they declare — and hands them back.**

The game exposes its combat behavior tree (BT) and declares which block weights may be learned. A learning platform
(CMA-ES, IMPALA) tunes only those weights per player persona, over a plain TCP protocol, on CPU.
The same contract works for a Unity game and a Python simulator, and the learned weights drive the real game's combat
when an agent plays it from the first village.

![Same seed, three behavior trees: hand-tuned (fails at 10:00) vs CMA-ES (clears in 348 s) vs IMPALA (clears in 357 s)](docs/media/compare.gif)

*Unity build, same boss fight and same seed, replayed side by side (16×): hand-tuned defaults · CMA-ES · IMPALA policy.*

---

## Why this direction

I have worked on reinforcement learning for game balance QA for a long time. Two problems kept coming back:

- **RL is welded to the game.** Observation and action spaces are game-specific, so every game — often every patch —
  means rebuilding the agent. The result is a black-box policy that designers cannot read or adjust.
- **LLM agents are a poor fit for combat.** Letting the model make every decision costs a call (latency and money) per
  decision, while a combat BT decides every 0.3 s. Fine-tuning the model costs time and GPUs instead.

This project tries a different split:

| Decision | Who makes it | How often |
|---|---|---|
| Behavior structure (blocks, need functions) | Designers, in the game's BT | Design time |
| Block weights `w` in `score = N(situation) × w` | **RL — the only thing it learns** | Once per fight, or at trigger points (boss HP 75/50/25 %) |
| Moment-to-moment combat actions | The BT itself | Every 0.3 s |
| Non-combat play (talk, shop, travel) | An LLM pilot (optional) | Rarely |

Small, declared learning targets keep the policy interpretable (a handful of named weights), cheap to train, and
reusable across games: the learning side never sees skills, stats or game code — only the declared parameters.

## How it works

```
┌──────────── Game (Unity or Python) ────────────┐                 ┌──────────── Learning platform ────────────┐
│ combat sim + behavior tree (deterministic, seed)│                 │ balance_qa (PyTorch CPU)                   │
│ IEpisodeHost: declare() / run_episode()         │ ◀── TCP JSON ──▶ │   learnable space = declared block weights │
│ BT-QA Game SDK: server, validation, triggers    │    Lines 1.3     │   personas = non-weight settings + rewards │
└─────────────────────────────────────────────────┘                 │   CMA-ES · IMPALA (V-trace, remote actors) │
                                                                    └────────────────────────────────────────────┘
```

- **Weights-only, enforced.** The game declares `blocks: [{name, weight}]`. The SDK refuses to start if anything else is
  marked learnable, and the learner rejects any other learning target. Non-weight values (potion threshold, resource
  reserve…) stay at the designers' defaults or come from a persona.
- **Personas** (aggressive / stable / efficient) set need-function thresholds and reward coefficients
  (`R = −minutes − λ_death·deaths − λ_consumable·items − penalty·[fail]`); each gets its own optimal weights.
- **Two learners on one interface:** CMA-ES picks static weights per fight; IMPALA (Beta actor-critic, V-trace) changes
  weights at trigger points from the fight state. Actors are separate processes, one per game instance, so the same
  code can run local or remote actors.
- **Determinism is part of the contract:** same class, scenario, seed, params and trigger replies → byte-identical
  result. A conformance checker verifies this, along with the message formats, error codes and trigger round-trips.
- **Play mode:** the game can also be played from the start (village → field → boss). Non-combat actions come from
  an LLM pilot or a script; when a fight starts, the learned weights take over, and the outcome matches the
  balance-mode episode exactly.

![Play mode: village quests, forest, and the wolf king fought by the learned BT](docs/media/play_mode.gif)

*Play mode from the first village: tutorial quests by a scripted pilot, the wolf king fought by the IMPALA-tuned BT.*

## Results

Unity build `qa_arena 0.7.0`, persona *stable*, 200–300 evaluation episodes on held-out seeds, mean [95 % CI].
Only the three block weights are learned.

| Class / fight | Hand-tuned defaults | CMA-ES (3,000 episodes) | IMPALA |
|---|---|---|---|
| Warrior vs arena boss | clear 62 % · deaths 1.01 | clear **100 %** · deaths 0.52 · 362 s | clear 99 % · deaths 0.49 · 405 s (8,000 ep.) |
| Mage vs arena boss | clear 62 % · deaths 2.75 | clear **89 %** · deaths 2.06 · 434 s | — |
| Warrior vs wolf king (field boss) | clear 60 % · deaths 2.06 | clear **100 %** · deaths 1.26 · 351 s | clear 99 % · deaths 1.22 · 341 s (3,000 ep.) |

- **Cost:** one episode takes 1–2 ms in the headless Unity build. The full measurement above — baselines for 3 classes ×
  2 personas, two CMA-ES runs and one IMPALA run — took **about 20 seconds** on CPU with 4 game instances.
- **Same seed, different outcome:** the GIF at the top is evaluation seed 1000003. The hand-tuned BT times out at
  10:00 with the boss at 0.2 %; both learned BTs clear it.

### What the platform surfaced along the way

The measurement history across builds (see `docs/STATUS.md`, in Korean) is where the tool earned its keep:

- **Revive used as a heal.** In build 0.3.0 the learned weights cleared 94–98 % of fights but died 2–3 times per run.
  Dying and reviving was cheaper than defending. This led to revive and regen changes in the game (0.4.0).
- **A persona that learned to give up.** Without a failure penalty, the *stable* warrior learned to survive until the
  timer ran out (0 % clears). We added an explicit failure term to the reward. It is a deliberate deviation from the
  original proposal and is documented as such.
- **A class that died too much.** Hand-tuned warrior cleared 55 % with about 3 deaths per run, and even optimized weights
  still died about twice per run. That pointed to the class itself, so we sent a balance request to the game side. The
  armor change in 0.5.0 brought hand-tuned to 62 % with 1.01 deaths per run, about a third of before.
- **Open:** hand-tuned mage reportedly clears 0 % against the wolf king. The next step is telling a parameter problem
  from a boss-design problem.

## Repository layout

```
balance_qa/     learning platform: protocol client, CMA-ES / ES / IMPALA (PyTorch CPU), rewards, evaluation, reports
play_agent/     play-mode client: loadout from learned results, numpy policy runner, optional LLM pilot (Claude API)
game_sim/       Python reference game (BT, combat sim) — test double and reference implementation
btqa_game/      Game SDK, Python (copy — the original lives in a separate repository, see below)
unity_game/     QaArena, the Unity test game (Unity 6000.0); SDK as embedded package Packages/com.btqa.game
qa_specs/       personas
experiments/    hypothesis experiments E0–E7
run/            one-click run scripts (also registered as PyCharm run configurations)
docs/           protocol (contract), play protocol, architecture, status — mostly Korean
```

The Game SDK (Unity package + Python package + protocol) is maintained separately at
**[jk96491/btqa_sdk](https://github.com/jk96491/btqa_sdk)**. This repository vendors identical copies
(`run/run_sync_sdk.py`); a test checks they match.

## Quick start

Requirements: Python 3.8+, `numpy`, `torch` (CPU). The Unity build is optional — the Python game runs everything.

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -t .                  # tests
python -m balance_qa check-game                            # protocol conformance (Python game)
python -m balance_qa --workers 4 optimize --cls warrior --persona stable --budget 3000          # CMA-ES
python -m balance_qa --workers 4 impala   --cls warrior --persona stable --budget 8000 \
    --init-params reports/<run_id>/params.json                                                  # IMPALA
```

With the Unity build (`unity_game/Build/QaArena.exe`, built with `unity_game/QaTools~/build.ps1`):

```bash
python run/run_full_cycle.py      # conformance → baseline → CMA-ES → IMPALA → report (set GAME_CMD = UNITY)
python run/run_watch.py           # replay saved results side by side in Unity windows (top GIF)
python run/run_watch_play.py      # play mode from the village, combat by the learned BT (second GIF)
```

To connect your own game, implement `IEpisodeHost` with the SDK and pass `python -m btqa_game check --game host:port`.

## Limitations

- **Toy environment.** 1-vs-1 boss fights on a one-dimensional distance axis, three classes. Read the numbers as trends
  and relative sizes, not as claims about a real game.
- **Integration prerequisite.** The game must run its combat headless, deterministically and fast (milliseconds per
  episode). Separating combat logic from rendering is the main cost of adopting this. In QaArena, the game-specific
  glue is one ~100-line class.
- **Few learning targets by design.** With three weights a grid search is a fair baseline, and IMPALA's trigger-time
  policy is not yet clearly better than CMA-ES's static weights here. Showing where state-dependent weights matter
  (experiment E7) is open work. Scaling all weights by the same factor doesn't change behavior; this redundancy is left
  as is.
- **Not yet done:** a live run of the LLM pilot (implemented, tested against a fake API), full-scale runs of
  experiments E1–E7, and a cost comparison against an LLM-only player.

## Background

This continues my article series on applying RL to games,
[「実録・ゲーム強化学習適用記」 (Qiita, Japanese)](https://qiita.com/raptorjung/items/0be8fb02181c83735bf5).
The previous part moved execution to rule-based behavior and kept RL for judgment. It ended with an open question: how
to fine-tune fixed rule-based actions without losing stability. This project answers it, and also removes RL's
dependence on any single game.

*Code identifiers and this README are in English. Internal docs and code comments are in Korean
(Korean overview: [docs/README.ko.md](docs/README.ko.md)).*
