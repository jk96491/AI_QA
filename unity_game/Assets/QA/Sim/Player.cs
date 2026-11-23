// 플레이어 엔티티 (game_sim/sim/player.py 대응).
using System;
using Qa.Data;

namespace Qa.Sim
{
    public sealed class Player
    {
        const double Eps = SimConst.Eps;

        public readonly ClassSpec Spec;
        readonly double _gcdDuration;
        public readonly double MaxHp;
        public double Hp;
        public readonly double MaxResource;
        public double Resource;
        public readonly double[] Cooldowns;   // SkillDef.Index
        public double Gcd;
        public int Potions;
        public double PotionCd;
        public double Shield;
        public double ShieldTime;
        public double EvadeTime;
        public SkillDef Casting;
        public double CastRemaining;
        public bool Dead;
        public double ReviveTimer;
        public double SinceHit;
        // 0.8.1 Setup 버프
        public double DamageBuff, DamageBuffTime;   // 주는 피해 × (1 + DamageBuff)
        public double RegenMult = 1.0, RegenTime;   // 자원 재생 배율
        public double DamageMult => DamageBuffTime > Eps ? 1.0 + DamageBuff : 1.0;

        public Player(ClassSpec spec, double gcd)
        {
            var s = spec.Stats;
            Spec = spec;
            _gcdDuration = gcd;
            MaxHp = s.MaxHp;
            Hp = s.MaxHp;
            MaxResource = s.MaxResource;
            Resource = s.StartResource;
            Cooldowns = new double[spec.Skills.Count];
            Potions = s.Potions;
        }

        // ----- 상태 -----
        public double HpRatio => Math.Max(0.0, Hp / MaxHp);
        public double ResourceRatio => MaxResource <= 0 ? 0.0 : Resource / MaxResource;
        public bool GcdReady => Gcd <= Eps && Casting == null;

        /// <summary>쿨·자원 기준 (GCD 무시).</summary>
        public bool Available(SkillDef skill) => Cooldowns[skill.Index] <= Eps && Resource + Eps >= skill.Cost;
        public bool CanUse(SkillDef skill) => !Dead && GcdReady && Available(skill);
        public bool PotionReady => Potions > 0 && PotionCd <= Eps;

        // ----- 시간 경과 -----
        public void Tick(double dt)
        {
            for (int i = 0; i < Cooldowns.Length; i++)
                if (Cooldowns[i] > 0) Cooldowns[i] = Math.Max(0.0, Cooldowns[i] - dt);
            Gcd = Math.Max(0.0, Gcd - dt);
            PotionCd = Math.Max(0.0, PotionCd - dt);
            if (ShieldTime > 0)
            {
                ShieldTime -= dt;
                if (ShieldTime <= Eps) { Shield = 0.0; ShieldTime = 0.0; }
            }
            EvadeTime = Math.Max(0.0, EvadeTime - dt);
            if (DamageBuffTime > 0) { DamageBuffTime -= dt; if (DamageBuffTime <= Eps) { DamageBuffTime = 0; DamageBuff = 0; } }
            if (RegenTime > 0) { RegenTime -= dt; if (RegenTime <= Eps) { RegenTime = 0; RegenMult = 1.0; } }
            if (!Dead)
            {
                var s = Spec.Stats;
                Resource = Math.Min(MaxResource, Resource + s.ResourceRegen * RegenMult * dt);
                SinceHit += dt;
                if (SinceHit >= s.RegenDelay) Hp = Math.Min(MaxHp, Hp + MaxHp * s.HpRegenRatio * dt);
            }
        }

        // ----- 행동 -----
        public void StartSkill(SkillDef skill)
        {
            Resource -= skill.Cost;
            Cooldowns[skill.Index] = skill.Cooldown;
            Gcd = Math.Max(_gcdDuration, skill.CastTime);
            if (skill.Shield > 0) { Shield = skill.Shield; ShieldTime = skill.EffectDuration; }
            if (skill.Evade > 0) EvadeTime = skill.Evade;
            if (skill.ResourceOnUse > 0) GainResource(skill.ResourceOnUse);
            if (skill.BuffDamage != 0) { DamageBuff = skill.BuffDamage; DamageBuffTime = skill.EffectDuration; }
            if (skill.RegenMult != 1.0) { RegenMult = skill.RegenMult; RegenTime = skill.EffectDuration; }
            if (skill.CastTime > 0) { Casting = skill; CastRemaining = skill.CastTime; }
        }

        public void GainResource(double amount) => Resource = Math.Min(MaxResource, Resource + amount);

        public double DrinkPotion()
        {
            Potions -= 1;
            PotionCd = Spec.Stats.PotionCooldown;
            double before = Hp;
            Hp = Math.Min(MaxHp, Hp + MaxHp * Spec.Stats.PotionHealRatio);
            return Hp - before;
        }

        public double ReceiveDamage(double raw, bool ignoreMitigation)
        {
            if (Dead || EvadeTime > Eps) return 0.0;
            double dmg = raw;
            if (!ignoreMitigation) dmg *= (1.0 - Spec.Stats.Armor) * (1.0 - Shield);
            Hp -= dmg;
            SinceHit = 0.0;
            return dmg;
        }

        public void Interrupt() { Casting = null; CastRemaining = 0.0; }

        public void Die(double reviveDelay)
        {
            Dead = true;
            Hp = 0.0;
            ReviveTimer = reviveDelay;
            Interrupt();
            Shield = ShieldTime = EvadeTime = 0.0;
            DamageBuff = DamageBuffTime = RegenTime = 0.0;
            RegenMult = 1.0;
        }

        public void Revive(double hpRatio)
        {
            Dead = false;
            Hp = MaxHp * hpRatio;
            Gcd = 0.0;
            SinceHit = 0.0;
        }
    }
}
