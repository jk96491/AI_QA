// 스킬별 연출. 판 로직 이벤트(skill = 사용 시작, dmg = 피해 적용)를 받아 효과만 만든다.
//   전사: 평타(흰 베기) 강타(주황 대형 베기+불꽃) 돌진(잔상 돌격) 방패 막기(푸른 돔) 칼날폭풍(회전 칼날)
//   마법사: 마력탄(보라 구) 화염구(지팡이에 불 모음→큰 불덩이→폭발) 보호막(룬 마법진) 점멸(양쪽 섬광) 메테오(보스 밑 마법진→운석)
//   궁수: 기본 사격(포물선 화살) 조준 사격(조준선→빛나는 화살) 회피(공중제비+바람 고리) 속사(화살 연사)
using System;
using Qa.Data;
using UnityEngine;

namespace Qa.Presentation
{
    public sealed partial class BattleViewer
    {
        float _flipT = 99f;        // 궁수 회피 공중제비
        float _drawT = 99f;        // 궁수 시위 당김
        float _thrustT = 99f;      // 마법사 지팡이 찌르기
        float _swingDir = 1f;      // 전사 베기 방향 번갈아

        static readonly Color CWhite = new Color(1f, 1f, 1f, 0.75f);
        static readonly Color COrange = new Color(1f, 0.55f, 0.15f, 0.85f);
        static readonly Color CSteel = new Color(0.75f, 0.85f, 1f, 0.8f);
        static readonly Color CPurple = new Color(0.75f, 0.4f, 1f, 0.8f);
        static readonly Color CFire = new Color(1f, 0.45f, 0.1f, 0.85f);
        static readonly Color CGreen = new Color(0.55f, 1f, 0.45f, 0.8f);
        static readonly Color CWind = new Color(0.8f, 1f, 0.85f, 0.6f);

        Vector3 PlayerPos() => _player.Root.position;
        Vector3 PlayerChest() => _player.Root.position + Vector3.up * 1.3f;
        Vector3 TipPos() => _player.Tip != null ? _player.Tip.position : PlayerChest();
        Quaternion PlayerFacing() => _player.Root.rotation;
        Vector3 BossPos() => _boss.Root.position;
        Vector3 BossHitPoint()
        {
            var toP = _player.Root.position - _boss.Root.position;
            toP.y = 0;
            return BossChest() + (toP.sqrMagnitude > 1e-4f ? toP.normalized * 1.3f : Vector3.zero);
        }

        // ------------------------------------------------------------------ 사용 시작 (skill 이벤트)
        void SkillStartFx(SkillDef sd)
        {
            float cast = (float)sd.CastTime;
            switch (sd.Name)
            {
                // ----- 전사 -----
                case "basic_attack":
                case "strike":
                    _swingT = 0f;
                    _swingDir = -_swingDir;
                    break;
                case "charge":
                {
                    // 돌진: 지나온 길에 잔상 + 도착 충격
                    var a = _playerFrom; var b = _playerTo;
                    for (int i = 0; i < 4; i++)
                        _fx.Ghost(Vector3.Lerp(a, b, i / 4f), _player.Root.rotation, new Color(0.5f, 0.7f, 1f, 0.45f), 0.35f + i * 0.08f);
                    _fx.Shockwave(b, 0.4f, 3f, new Color(0.9f, 0.85f, 0.7f, 0.7f), 0.45f);
                    _fx.Sparks(b + Vector3.up * 0.3f, new Color(0.9f, 0.8f, 0.6f), 8, 4f, 0.5f);
                    _shake = Mathf.Max(_shake, 0.25f);
                    break;
                }
                case "shield_block":
                    _fx.Burst(PlayerChest(), new Color(0.4f, 0.7f, 1f, 0.6f), 3.2f, 0.35f);
                    _fx.Shockwave(PlayerPos(), 0.5f, 2.2f, new Color(0.5f, 0.8f, 1f, 0.8f), 0.4f);
                    break;
                case "bladestorm":
                    _fx.Orbit(PlayerPos, 3, 1.9f, CSteel, cast + 0.2f);
                    _fx.Shockwave(PlayerPos(), 0.5f, 3.5f, new Color(0.8f, 0.9f, 1f, 0.5f), cast);
                    break;

                // ----- 마법사 -----
                case "magic_bolt":
                    _thrustT = 0f;
                    break;
                case "fireball":
                    _fx.Gather(TipPos, CFire, 0.9f, cast, 10);
                    _fx.Burst(TipPos(), new Color(1f, 0.5f, 0.1f, 0.5f), 0.9f, cast);
                    break;
                case "barrier":
                    _fx.MagicCircle(PlayerPos, 1.9f, new Color(0.8f, 0.5f, 1f, 0.75f), (float)Math.Max(1.0, sd.EffectDuration));
                    _fx.Burst(PlayerChest(), new Color(0.8f, 0.5f, 1f, 0.5f), 3.2f, 0.4f);
                    break;
                case "blink":
                    _fx.Burst(_playerFrom + Vector3.up, new Color(0.8f, 0.5f, 1f, 0.8f), 2.2f, 0.35f);
                    _fx.Ghost(_playerFrom, _player.Root.rotation, new Color(0.75f, 0.45f, 1f, 0.55f), 0.5f);
                    _fx.Burst(_playerTo + Vector3.up, new Color(0.9f, 0.7f, 1f, 0.8f), 2.2f, 0.35f);
                    _fx.Sparks(_playerTo + Vector3.up, new Color(0.85f, 0.6f, 1f), 10, 3f, 0.5f);
                    break;
                case "meteor":
                    _fx.MagicCircle(BossPos, 4.2f, new Color(1f, 0.35f, 0.1f, 0.8f), cast + 0.4f);
                    _fx.Gather(TipPos, CFire, 1.2f, cast, 14);
                    break;

                // ----- 궁수 -----
                case "basic_shot":
                    _drawT = 0f;
                    break;
                case "aimed_shot":
                    _drawT = -cast;   // 시전 동안 당긴 채 유지
                    _fx.Beam(TipPos, BossHitPoint, new Color(0.6f, 1f, 0.5f, 0.5f), 0.04f, cast);
                    _fx.Gather(TipPos, CGreen, 0.5f, cast, 6);
                    break;
                case "evade":
                    _flipT = 0f;
                    _fx.Ghost(_playerFrom, _player.Root.rotation, new Color(0.5f, 0.9f, 0.5f, 0.5f), 0.5f);
                    _fx.Shockwave(_playerFrom, 0.3f, 2.5f, CWind, 0.4f, 0.7f);
                    _fx.Shockwave(_playerTo, 0.3f, 2.0f, CWind, 0.5f, 0.7f);
                    break;
                case "rapid_fire":
                {
                    _drawT = -cast;
                    // 시전 내내 화살 연사 (시각 효과 — 피해는 시전 완료 시 한 번에 적용됨)
                    int n = Mathf.Max(6, Mathf.RoundToInt(cast * 6f));
                    for (int i = 0; i < n; i++)
                    {
                        float delay = cast * i / n;
                        _fx.Delay(delay, () =>
                        {
                            if (_player == null) return;
                            _fx.Shot(FxSystem.Arrow(new Color(0.6f, 1f, 0.5f), 0.7f), TipPos(), () => BossHitPoint() + UnityEngine.Random.insideUnitSphere * 0.6f,
                                     0.22f, 0.3f, new Color(0.6f, 1f, 0.5f, 0.35f), 0.25f,
                                     () => _fx.Sparks(BossHitPoint(), new Color(0.7f, 1f, 0.5f), 2, 3f, 0.3f));
                        });
                    }
                    break;
                }
            }
        }

        // ------------------------------------------------------------------ 피해 적용 (dmg 이벤트)
        /// <summary>스킬 피해 연출. 맞는 순간 land() 를 불러 숫자를 띄운다.</summary>
        void SkillHitFx(SkillDef sd, bool crit, Action land)
        {
            Color critC = new Color(1f, 0.85f, 0.3f, 0.9f);
            switch (sd.Name)
            {
                // ----- 전사 -----
                case "basic_attack":
                    _fx.Slash(() => PlayerPos() + Vector3.up * 1.2f, PlayerFacing, 2.6f, 120f, 20f * _swingDir, crit ? critC : CWhite, 0.3f, _swingDir < 0);
                    land();
                    break;
                case "strike":
                    _fx.Slash(() => PlayerPos() + Vector3.up * 1.4f, PlayerFacing, 3.4f, 160f, -55f, crit ? critC : COrange, 0.4f);
                    _fx.Sparks(BossHitPoint(), new Color(1f, 0.6f, 0.2f), 12, 6f, 0.5f);
                    _shake = Mathf.Max(_shake, 0.2f);
                    land();
                    break;
                case "charge":
                    _fx.Burst(BossHitPoint(), new Color(0.9f, 0.85f, 0.7f, 0.7f), 1.8f, 0.3f);
                    land();
                    break;
                case "bladestorm":
                    _fx.Shockwave(PlayerPos(), 0.5f, 5f, CSteel, 0.5f, 0.75f);
                    for (int i = 0; i < 3; i++)
                    {
                        float yaw = i * 120f;   // 클로저가 루프 변수를 공유하지 않도록 복사
                        _fx.Slash(() => PlayerPos() + Vector3.up * 1.1f, () => PlayerFacing() * Quaternion.Euler(0, yaw, 0), 3.2f, 150f, 0, CSteel, 0.35f + i * 0.05f);
                    }
                    _fx.Sparks(BossHitPoint(), new Color(0.8f, 0.9f, 1f), 16, 7f, 0.6f);
                    _shake = Mathf.Max(_shake, 0.4f);
                    land();
                    break;

                // ----- 마법사 -----
                case "magic_bolt":
                    _fx.Shot(FxSystem.Orb(new Color(0.75f, 0.45f, 1f), 0.3f), TipPos(), BossHitPoint, 0.28f, 0.3f, new Color(0.75f, 0.45f, 1f, 0.45f), 0.25f, () =>
                    {
                        _fx.Burst(BossHitPoint(), new Color(0.8f, 0.5f, 1f, 0.7f), 1.2f, 0.25f);
                        land();
                    });
                    break;
                case "fireball":
                    _thrustT = 0f;
                    _fx.Shot(FxSystem.Orb(new Color(1f, 0.45f, 0.1f), 0.75f, 5f), TipPos(), BossHitPoint, 0.4f, 0.6f, new Color(1f, 0.5f, 0.1f, 0.55f), 0.55f, () =>
                    {
                        _fx.Burst(BossHitPoint(), new Color(1f, 0.5f, 0.1f, 0.85f), 3.2f, 0.45f);
                        _fx.Sparks(BossHitPoint(), new Color(1f, 0.6f, 0.2f), 14, 6f, 0.6f);
                        _shake = Mathf.Max(_shake, 0.25f);
                        land();
                    });
                    break;
                case "meteor":
                    _thrustT = 0f;
                    _fx.Meteor(BossPos, 0.5f, () =>
                    {
                        _fx.Shockwave(BossPos(), 1f, 9f, new Color(1f, 0.45f, 0.1f, 0.9f), 0.7f, 0.7f);
                        _fx.Burst(BossPos() + Vector3.up * 1.5f, new Color(1f, 0.6f, 0.2f, 0.9f), 7f, 0.6f);
                        _fx.Sparks(BossPos() + Vector3.up, new Color(1f, 0.5f, 0.1f), 24, 9f, 0.9f);
                        _fx.Pillar(BossPos(), new Color(1f, 0.4f, 0.1f, 0.6f), 10f, 3f, 0.6f);
                        _shake = 0.8f;
                        land();
                    });
                    break;

                // ----- 궁수 -----
                case "basic_shot":
                    _drawT = 0.15f;
                    _fx.Shot(FxSystem.Arrow(new Color(0.85f, 0.75f, 0.5f)), TipPos(), BossHitPoint, 0.3f, 0.9f, Color.clear, 0f, () =>
                    {
                        _fx.Sparks(BossHitPoint(), new Color(1f, 0.95f, 0.7f), 4, 3f, 0.3f);
                        land();
                    });
                    break;
                case "aimed_shot":
                    _drawT = 0.15f;
                    _fx.Shot(FxSystem.Arrow(new Color(0.6f, 1f, 0.5f), 1.1f), TipPos(), BossHitPoint, 0.16f, 0.05f, new Color(0.6f, 1f, 0.5f, 0.6f), 0.35f, () =>
                    {
                        _fx.Burst(BossHitPoint(), new Color(0.6f, 1f, 0.5f, 0.8f), 1.8f, 0.3f);
                        _fx.Sparks(BossHitPoint(), new Color(0.7f, 1f, 0.5f), 10, 5f, 0.45f);
                        land();
                    });
                    break;
                case "rapid_fire":
                    _drawT = 0.15f;
                    _fx.Burst(BossHitPoint(), new Color(0.6f, 1f, 0.5f, 0.8f), 2.6f, 0.35f);
                    _fx.Sparks(BossHitPoint(), new Color(0.7f, 1f, 0.5f), 16, 6f, 0.5f);
                    land();
                    break;

                default:
                    _fx.Burst(BossHitPoint(), crit ? critC : CWhite, 1.2f, 0.25f);
                    land();
                    break;
            }
        }

        // ------------------------------------------------------------------ 직업별 몸 동작 (매 프레임)
        void AnimateClass(float vdt, float dt, float time, bool dead, bool casting, float moveSpeed)
        {
            _flipT += vdt; _drawT += vdt; _thrustT += vdt;
            var r = _player;

            // 다리: 이동 속도에 비례해 흔들기
            if (r.LegL != null)
            {
                float stride = dead ? 0f : Mathf.Clamp01(moveSpeed / 4f);
                float ang = Mathf.Sin(time * (_playerClass == "archer" ? 14f : 10f)) * 35f * stride;
                r.LegL.localRotation = Quaternion.Euler(ang, 0, 0);
                r.LegR.localRotation = Quaternion.Euler(-ang, 0, 0);
            }
            // 망토 펄럭임
            if (r.Cape != null)
                r.Cape.localRotation = Quaternion.Euler(8f + Mathf.Sin(time * 3.1f) * 4f + Mathf.Clamp01(moveSpeed / 4f) * 25f, 0, 0);
            // 마법사: 떠 있기 + 발밑 마법진 회전
            if (r.Hover && !dead)
                r.Body.localPosition = new Vector3(0, 0.35f + Mathf.Sin(time * 2f) * 0.12f, 0);
            if (r.Halo != null)
            {
                r.Halo.gameObject.SetActive(!dead);
                r.Halo.Rotate(0, (casting ? 160f : 35f) * dt, 0);
                r.Halo.localScale = Vector3.one * (casting ? 1.35f + Mathf.Sin(time * 10f) * 0.08f : 1f);
            }

            switch (_playerClass)
            {
                case "warrior":
                {
                    float s = _swingT < 0.3f ? Mathf.Sin(_swingT / 0.3f * Mathf.PI) : 0f;
                    float spin = casting && _sim.PlayerState.Casting?.Name == "bladestorm" ? time * 1440f : 0f;
                    r.Weapon.localRotation = Quaternion.Euler(-30f - s * 120f, 0, s * 40f * _swingDir);
                    r.Off.localRotation = Quaternion.Euler(0, _sim.PlayerState.Shield > 0 ? -60f : -15f, 0);   // 방패 앞으로
                    r.Body.localRotation = dead ? r.Body.localRotation : Quaternion.Euler(s * 10f, spin, 0);
                    break;
                }
                case "mage":
                {
                    float th = _thrustT < 0.35f ? Mathf.Sin(_thrustT / 0.35f * Mathf.PI) : 0f;
                    r.Weapon.localRotation = Quaternion.Euler(-10f - (casting ? 35f : 0f) - th * 50f, 0, 0);
                    break;
                }
                case "archer":
                {
                    // 활을 앞으로 들고, 시위 손을 뒤로 당김
                    float draw = _drawT < 0f ? 1f : _drawT < 0.15f ? 1f - _drawT / 0.15f : 0f;
                    bool aiming = casting || draw > 0;
                    r.Bow.localRotation = Quaternion.Euler(0, aiming ? -10f : 25f, aiming ? 0f : -35f);
                    r.Weapon.localPosition = new Vector3(0.2f, 1.35f, 0.25f - draw * 0.5f);
                    // 회피: 뒤로 공중제비
                    if (_flipT < 0.45f && !dead)
                    {
                        float k = _flipT / 0.45f;
                        r.Body.localRotation = Quaternion.Euler(-360f * k, 0, 0);
                        r.Body.localPosition = new Vector3(0, Mathf.Sin(k * Mathf.PI) * 1.2f, 0);
                    }
                    break;
                }
            }
        }
    }
}
