"""QaArena 보상 (RFT/GRPO 채점기) — "무엇이 진척인가"는 게임 판단이라 SDK 가 아니라 여기.

reward(obs_before, tool, input, out):
  -1.0  오류·실패 (형식 오류는 SDK 가 따로 -1)          예: blocked_by_modal, not_visible, unknown_target
  +1.0  퀘스트 진척 사건 (quest_accepted·quest_progress·quest_completed) 또는 전투 승리
  +0.5  진행 중 미완료 목표의 대상(hint_targets)에게 간/상호작용한 행동이 성공
  +0.3  행동 뒤 목표 대상이 새로 보이게 됨 (맞는 지역으로 이동)
  +0.2  창이 열린 상태에서 그 창의 버튼을 눌러 진행 (ui_click 성공)
  finish: 진행 중 퀘스트가 없으면 +1, 남아 있으면 -0.5
  그 밖의 성공 0
"""
from __future__ import annotations

from typing import Any, Mapping, Set

PROGRESS_EVENTS = ("quest_accepted", "quest_progress", "quest_completed")


def _targets(obs: Mapping[str, Any]) -> Set[str]:
    out: Set[str] = set()
    for q in obs.get("quests") or []:
        if q.get("state") == "ready":
            out |= {t for ob in q.get("objectives") or [] if not ob.get("done") for t in ob.get("hint_targets") or []}
            continue
        for ob in q.get("objectives") or []:
            if not ob.get("done"):
                out |= set(ob.get("hint_targets") or [])
                break   # 첫 미완료 목표만
    return out


def _visible(obs: Mapping[str, Any]) -> Set[str]:
    return {e.get("id") for e in obs.get("entities") or []}


def reward(obs_before: Mapping[str, Any], tool: str, inp: Mapping[str, Any], out: Mapping[str, Any]) -> float:
    if tool == "finish":
        return 1.0 if not obs_before.get("quests") else -0.5
    if out.get("error") or out.get("status") == "failed":
        return -1.0
    after = out.get("observation") or {}
    kinds = {e[1] for e in after.get("events") or [] if isinstance(e, list) and len(e) > 1}
    if kinds & set(PROGRESS_EVENTS) or any(c.get("cleared") for c in out.get("combats") or []):
        return 1.0
    tg = _targets(obs_before)
    r = 0.0
    if inp.get("target") in tg:
        r = max(r, 0.5)
    if tg and not (tg & _visible(obs_before)) and (tg & _visible(after)):
        r = max(r, 0.3)
    if tool == "ui_click" and ((obs_before.get("screen") or {}).get("modal")):
        r = max(r, 0.2)
    return r


__all__ = ["reward"]
