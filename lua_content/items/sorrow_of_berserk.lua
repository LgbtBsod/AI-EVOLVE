-- Sorrow of Berserk
-- Lost My Self below 40% HP; Blood Price attacks; Last Will shield (5 s iframe, 30 s cooldown, +5 s per kill).
-- Сгенерировано CAS Item Builder (effect-schema v1) : 2026-09-24 07:00:03

return {
  name = "Sorrow of Berserk",
  description = "Lost My Self below 40% HP; Blood Price attacks; Last Will shield (5 s iframe, 30 s cooldown, +5 s per kill).",
  effects = {
{
      id = "lost_my_self",
      tags = {
        "berserk",
        "passive",
      },
      trigger = { kind = "condition", when = function(ctx) return (ctx.hp_pct < 40) end },
      meta = {
        name = "Lost My Self",
        description = "Below 40% HP: berserk power scaling with missing HP; at exactly 1 HP every bonus x2 per missing 10%.",
        amplify = { when = "ctx.hp <= 1", factor = 2, every = 10, of = "hp_missing_below_40" }
      },
      ops = {
        -- op: mod self strength add
        { kind = "mod", target = "self", stat = "strength", op = "add", value = { pct = 20 } },
        -- op: mod self stamina add
        { kind = "mod", target = "self", stat = "stamina", op = "add", value = { pct = 10 } },
        -- op: mod self crit_chance add
        {
          kind = "mod",
          target = "self",
          stat = "crit_chance",
          op = "add",
          value = { flat = 5 },
          scale = { every = 10, of = "hp_missing_below_40", factor = 1, value = { flat = 5 } }
        },
        -- op: mod self crit_dmg add
        {
          kind = "mod",
          target = "self",
          stat = "crit_dmg",
          op = "add",
          value = { flat = 10 },
          scale = { every = 10, of = "hp_missing_below_40", factor = 1, value = { flat = 10 } }
        },
        -- op: mod self aspd add
        {
          kind = "mod",
          target = "self",
          stat = "aspd",
          op = "add",
          value = { pct = 5 },
          scale = { every = 10, of = "hp_missing_below_40", factor = 1, value = { pct = 10 } }
        },
        -- op: mod self hp_regen add
        {
          kind = "mod",
          target = "self",
          stat = "hp_regen",
          op = "add",
          value = { flat = 0 },
          scale = { every = 10, of = "hp_missing_below_40", factor = 1, value = { flat = 20 } }
        },
        -- op: mod self lifesteal add
        {
          kind = "mod",
          target = "self",
          stat = "lifesteal",
          op = "add",
          value = { flat = 0 },
          scale = { every = 10, of = "hp_missing_below_40", factor = 1, value = { flat = 5 } }
        }
      },
    },
{
      id = "lost_my_self.attack",
      tags = {
        "berserk",
        "on_attack",
      },
      trigger = { kind = "event", event = "attack", owner_has = "lost_my_self" },
      meta = {
        name = "Blood Price",
        description = "Each attack costs 0.5% max HP and deals 1.5% max HP true damage; +0.5%/+1.5% per 10% HP below 40."
      },
      ops = {
        -- op: drain self hp sub
        {
          kind = "drain",
          target = "self",
          stat = "hp",
          op = "sub",
          value = { pct = 0.5, of = "max_hp" },
          scale = { every = 10, of = "hp_missing_below_40", factor = 1, value = { pct = 0.5, of = "max_hp" } },
          fail = {
          {
            kind = "set",
            target = "self",
            stat = "hp",
            op = "set",
            value = { flat = 1 },
          },
          {
            kind = "buff",
            target = "self",
            duration = { flat = 5 },
            cooldown = { flat = 30 },
            extend = { on = "kill", flat = 5 },
            buff_id = "last_will",
            flags = {
              "iframe",
            },
          },
          }
        },
        -- op: deal enemy hp sub
        {
          kind = "deal",
          target = "enemy",
          stat = "hp",
          op = "sub",
          value = { pct = 1.5, of = "max_hp" },
          scale = { every = 10, of = "hp_missing_below_40", factor = 1, value = { pct = 1.5, of = "max_hp" } }
        }
      },
    },
  },
}
