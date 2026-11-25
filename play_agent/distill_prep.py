"""증류 데이터 전처리 (QaArena 쪽) — 학습 목표 thought 앞에 "상황 읽기"를 붙인다.

r1(2026-11-24) 진단: 1.5B 학생이 입력의 퀘스트 진행도(약초 0/3)를 읽지 않고 교사 데이터의 순서(숲 → 마을)를 외워
"3개를 채집했다"고 지어냈다. 숲에 막 들어온 장면과 다 모은 뒤 장면은 겉보기가 비슷하고, 가르는 것은 진행도·퀘스트 상태뿐이다.
→ 목표 thought = "상황: <지역> · <퀘스트> <미완료 목표> <진행도> (<상태>) · <창> → " + 교사 thought
   학생은 먼저 입력에서 값을 옮겨 적고(작은 모델도 잘한다), 그다음 행동을 고르게 된다.

관찰 필드(player.zone, quests[].objectives[].progress, screen.modal)는 플레이 프로토콜 4.5 것이지만 "퀘스트 진행이 판단의 핵심"이라는
것은 이 게임(튜토리얼) 판단이라 SDK 가 아니라 여기 둔다.

    venv\\Scripts\\python.exe -m play_agent.distill_prep distill_out/data/v2 distill_out/data/v3
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
    return "상황: " + " · ".join(parts)


def prep_sample(s: Dict[str, Any]) -> Dict[str, Any]:
    target = json.loads(s["messages"][-1]["content"])
    th = target.get("thought") or ""
    if not th.startswith("상황:"):
        th = "%s → %s" % (situation(s["messages"][1]["content"]), th)
    out = dict(s)
    out["messages"] = s["messages"][:-1] + [{"role": "assistant", "content": action_text(th, target["tool"], target["input"])}]
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
