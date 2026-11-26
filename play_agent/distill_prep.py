"""증류 데이터 전처리 (QaArena 쪽) — 학습 목표 thought 앞에 "상황 읽기"를 붙인다.

r1(2026-11-24) 진단: 1.5B 학생이 입력의 퀘스트 진행도(약초 0/3)를 읽지 않고 교사 데이터의 순서(숲 → 마을)를 외워
"3개를 채집했다"고 지어냈다. 숲에 막 들어온 장면과 다 모은 뒤 장면은 겉보기가 비슷하고, 가르는 것은 진행도·퀘스트 상태뿐이다.
→ 목표 thought = "상황: <지역> · <퀘스트> <미완료 목표> <진행도> (<상태>) · <창> → " + 교사 thought
   학생은 먼저 입력에서 값을 옮겨 적고(작은 모델도 잘한다), 그다음 행동을 고르게 된다.

관찰 필드(player.zone, quests[].objectives[].progress, screen.modal)는 플레이 프로토콜 4.5 것이지만 "퀘스트 진행이 판단의 핵심"이라는
것은 이 게임(튜토리얼) 판단이라 SDK 가 아니라 여기 둔다. SDK 에는 함수 이름만 넘긴다 (SDK 는 이 패키지를 import 하지 않는다):

    venv\\Scripts\\python.exe -m btqa_play dataset <기록...> --out distill_out/data/v11 --val-runs 215705-s5 \\
        --correction-weight 3 --prep play_agent.distill_prep:prep_sample
    venv\\Scripts\\python.exe -m btqa_play pairs <교정 기록...> --out distill_out/data/pairs.jsonl --prep play_agent.distill_prep:prep_pair
    venv\\Scripts\\python.exe -m play_agent.distill_prep <train/val 폴더> <출력 폴더>   # 이미 만든 데이터셋에 덧붙이기

접두는 **항상 입력에서 다시 만든다** — 기록의 생각 문장에 접두가 이미 있으면 (학생 제안을 승인한 단계 등) 떼고 다시 붙인다.
학생이 접두를 잘못 옮겨 적은 채 승인돼도 (r8 GPU: 약초 1/3 에 "목표 완료") 정답 데이터에는 입력 그대로의 상황이 들어간다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from btqa_play.actions import action_text


NEAR = 3.0   # QaArena 상호작용 거리 안 (move_to 뒤 거리 2.1~2.3, 교사 기록)


def _near(d: float) -> str:
    return "가까움 %.1f" % d if d <= NEAR else "멂 %.1f" % d


def _act_name(a: Dict[str, Any]) -> str:
    inp = a.get("input") or {}
    obj = inp.get("target") or inp.get("ui_id") or inp.get("item") or ""
    return ("%s %s" % (a.get("tool"), obj)).strip()


def repetition(d: Dict[str, Any]) -> str:
    """입력의 recent_actions + last_action → 반복 읽기 (history 형식일 때만, 없으면 "").

    r13 진단 (2026-11-27): 학생이 직전 행동 하나만 봐서 "등록" 버튼 20번·약초↔포털 왕복을 알아채지 못했다.
    같은 행동 N번 연속 = "같은 행동 N번째", 두 행동을 번갈아 (ABAB) = "번갈아 반복". 상점 구매처럼 반복이 맞는 장면도 있으니
    판단은 교사 라벨이 하고, 여기서는 입력에 있는 사실만 옮긴다."""
    if "recent_actions" not in d:
        return ""
    seq = [x for x in list(d.get("recent_actions") or []) + [d.get("last_action")] if x]
    names = [_act_name(x) for x in seq]
    if not names:
        return ""
    n = 1
    while n < len(names) and names[-1 - n] == names[-1]:
        n += 1
    if n >= 2:
        return "같은 행동 %d번째 (%s)" % (n, names[-1])
    if len(names) >= 4 and names[-1] == names[-3] and names[-2] == names[-4] and names[-1] != names[-2]:
        return "번갈아 반복 (%s ↔ %s)" % (names[-2], names[-1])
    return ""


def situation(user_text: str) -> str:
    d = json.loads(user_text)
    o = d.get("observation") or {}
    p = o.get("player") or {}
    parts: List[str] = [str(p.get("zone") or "?")]
    visible = {e.get("id") for e in o.get("entities") or []}
    dist = {e.get("id"): e.get("distance") for e in o.get("entities") or []}
    buttons = [u for u in (o.get("screen") or {}).get("ui") or []
               if u.get("role") == "button" and u.get("interactable") is not False]
    for q in o.get("quests") or []:
        objs = [x for x in q.get("objectives") or [] if not x.get("done")]
        if q.get("state") == "ready" or not objs:
            parts.append("%s 목표 완료 (ready, 반납)" % q.get("title"))
            tg = [t for x in objs for t in x.get("hint_targets") or []]
        else:
            ob = objs[0]
            prog = ob.get("progress") or [0, 0]
            parts.append("%s: %s %d/%d" % (q.get("title"), ob.get("text"), prog[0], prog[1]))
            tg = list(ob.get("hint_targets") or [])
        if tg:   # r2 진단: 반납 대상이 다른 지역인데 그 id 로 가려 했다 → 대상이 이 지역에 보이는지 읽게 한다
            seen = [t for t in tg if t in visible]
            # r5 진단: 멀리 있는 상인에게 move_to 없이 talk → out_of_range 반복 → 거리(입력 entities[].distance)로 가까움/멂
            seen_txt = ["%s(%s)" % (t, _near(dist.get(t))) if dist.get(t) is not None else t for t in seen[:3]]
            parts.append("대상 %s 보임" % ",".join(seen_txt) if seen else "대상 %s 이 지역에 없음" % ",".join(tg[:2]))
        elif objs:   # r3·r4 진단: 대상 표시 없는 목표("인벤토리에서 물약 등록")에서 버튼 대신 대화 반복 → 목표 글과 같은 글의 버튼
            btn = [u for u in buttons if u.get("text") and str(u["text"]) in str(objs[0].get("text") or "")]
            parts.append("목표 글 '%s' = 버튼 %s" % (btn[0]["text"], btn[0]["id"]) if btn else "대상 표시 없음")
    if not o.get("quests"):
        parts.append("진행 중 퀘스트 없음")
    modal = (o.get("screen") or {}).get("modal")
    if modal:   # r7 진단: 인벤토리에서 "퀵슬롯 등록"이라 생각하고도 직전 버튼(물약 칸)을 반복 → 창 버튼의 글=id (선택 표시 ▶)
        mb = [u for u in buttons if not str(u.get("id", "")).startswith("ui.hud.")]
        parts.append("창 %s [%s]" % (modal, ", ".join(
            "%s=%s" % (str(u.get("text") or "").replace("▶ ", "(선택) "), u["id"]) for u in mb[:6])))
    else:
        parts.append("창 없음")
    la = d.get("last_action")
    if la and (la.get("status") == "failed" or la.get("error")):
        parts.append("직전 실패 %s" % (la.get("reason") or la.get("error")))
    r = repetition(d)
    if r:
        parts.append(r)
    return "상황: " + " · ".join(parts)


def situation_key(user_text: str) -> str:
    """교사 일관성 검사용 "같은 상황" 키 (btqa_play dataset --situation-key 훅).

    입력 글자 전체가 아니라 판단을 가르는 것만: 지역 · 첫 미완료 목표(퀘스트·목표 글·진행도·ready) · 대상 거리 구간(가까움/멂/없음) · 창.
    같은 키에서 교사가 서로 다른 도구를 골랐으면 학생이 흔들린다 (r12 상인 장면: 같은 장면에 talk 와 인벤토리 열기가 섞였다)."""
    d = json.loads(user_text)
    o = d.get("observation") or {}
    dist = {e.get("id"): e.get("distance") for e in o.get("entities") or []}
    parts: List[str] = [str((o.get("player") or {}).get("zone") or "?")]
    for q in o.get("quests") or []:
        objs = [x for x in q.get("objectives") or [] if not x.get("done")]
        if q.get("state") == "ready" or not objs:
            parts.append("%s:ready" % q.get("id"))
            tg = [t for x in objs for t in x.get("hint_targets") or []]
        else:
            prog = objs[0].get("progress") or [0, 0]
            parts.append("%s:%s:%s/%s" % (q.get("id"), objs[0].get("text"), prog[0], prog[1]))
            tg = list(objs[0].get("hint_targets") or [])
        seen_t = sorted(t for t in tg if t in dist)
        parts.append("target:" + ("near" if any((dist.get(t) or 99) <= NEAR for t in seen_t) else "far" if seen_t else "none"))
        break   # 첫 퀘스트만 (튜토리얼은 한 번에 하나)
    # 손 닿는 엔티티 (상호작용 가능 거리) — 같은 목표라도 "포털 앞"과 "촌장 앞"은 다른 장면
    reach = sorted(str(e.get("id")) for e in o.get("entities") or [] if (e.get("distance") or 99) <= NEAR)
    parts.append("reach:" + ",".join(reach[:3]))
    screen = o.get("screen") or {}
    choices = [u for u in screen.get("ui") or [] if u.get("role") == "button" and u.get("interactable") is not False
               and not str(u.get("id", "")).startswith("ui.hud.")]
    parts.append("modal:%s%s" % (screen.get("modal") or "-", "+buttons" if choices else ""))
    la = d.get("last_action") or {}
    lost = any(c.get("cleared") is False for c in la.get("combats") or [])   # 직전 전투 패배 → 포기(finish)도 맞는 장면
    parts.append("last_failed" if (la.get("status") == "failed" or la.get("error")) else "lost" if lost else "")
    r = repetition(d)
    parts.append("rep" if r.startswith("같은") else "alt" if r else "")
    return "|".join(parts)


def _with_situation(user_text: str, action_json: str) -> str:
    a = json.loads(action_json)
    th = a.get("thought") or ""
    if th.startswith("상황:"):
        th = th.split("→", 1)[1].strip() if "→" in th else ""
    return action_text("%s → %s" % (situation(user_text), th), a["tool"], a["input"])


def prep_sample(s: Dict[str, Any]) -> Dict[str, Any]:
    """SFT 샘플 (btqa-play-sft/1) → 목표 thought 앞에 상황 읽기. btqa_play dataset --prep 훅."""
    out = dict(s)
    out["messages"] = s["messages"][:-1] + [{"role": "assistant", "content": _with_situation(s["messages"][1]["content"],
                                                                                              s["messages"][-1]["content"])}]
    return out


def prep_pair(r: Dict[str, Any]) -> Dict[str, Any]:
    """DPO 쌍 (btqa-play-pref/1) → chosen·rejected 모두 같은 형식의 상황 접두 (형식이 다르면 DPO 가 형식 차이를 배운다)."""
    out = dict(r)
    for key in ("chosen", "rejected"):
        out[key] = _with_situation(r["prompt"][1]["content"], r[key])
    return out


def main(argv: List[str]) -> int:
    src, dst = Path(argv[0]), Path(argv[1])
    dst.mkdir(parents=True, exist_ok=True)
    for name in ("train.jsonl", "val.jsonl"):
        rows = [json.loads(x) for x in (src / name).read_text(encoding="utf-8").splitlines() if x.strip()]
        with (dst / name).open("w", encoding="utf-8") as f:
            for s in rows:
                f.write(json.dumps(prep_sample(s), ensure_ascii=False) + "\n")
        print(name, len(rows))
    print(json.loads((dst / "train.jsonl").read_text(encoding="utf-8").splitlines()[6])["messages"][-1]["content"])
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.exit(main(sys.argv[1:]))
