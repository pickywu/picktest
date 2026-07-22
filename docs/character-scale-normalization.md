# Character scale normalization report

## Outcome

Character art stays in its original PNG files.  The game now normalizes scale at
draw time from reviewed idle-body landmarks, using one uniform X/Y scale per
identity.  Legacy attack poses inherit the idle scale; standardized hurt/block
poses use the shared 900 px reaction reference.  Every pose aligns its own
alpha bottom to the same ground line.

## Audit summary

- Player identities reviewed: 40/40 (sex × race × job).
- Every one of the 40 player identities has idle, attack, hurt, and block art.
  The 80 reaction sprites use a standardized 1024×1024 RGBA canvas.
- Legacy idle/attack source canvases remain mixed and untouched.
- Every one of the 18 monster identities (six ranks × three kinds) has the
  same four poses.  Idle/attack continue to share the reviewed idle alpha-box
  scale; hurt/block preserve that displayed size from the standardized canvas.
- The clearer male-orc-warrior block revision is the canonical `warrior.png`;
  `warrior_v1.png` and `warrior_v2.png` remain comparison backups and are
  excluded from runtime identity enumeration.

The reviewed player target body heights on the 1024 reference frame are elf
900, orc 873, human 837, and dwarf 702, with reference foot Y 968.  At runtime
the equivalent formula is:

```text
display scale = max elf body height × race factor ÷ source idle body height
```

Race factors are elf 1.00, orc 0.97, human 0.93, and dwarf 0.78.  Reference
canvas size is reporting metadata only and is not an extra runtime divisor.
Standardized hurt/block art uses a 900 px visible-body reference height, so a
1024 reaction canvas never makes a character larger or smaller than its idle
identity.  Dwarves therefore stay uniformly short and broad across all jobs
and all four poses.

## Weapon-safe behavior

Player scale never uses full alpha width or a width cap.  Long staffs, axes,
shields, magic effects, and trailing fabric therefore cannot make a character's
body smaller.  Reviewed `body_left_x` and `body_right_x` remain QA diagnostics;
only idle body height determines player scale.  Each pose has its own mass-based
horizontal anchor so wide weapons do not pull the body away from its logical X.

Monsters use the paired idle full alpha box as requested.  An idle-only width
safety guard allows up to 1.05× the layout slot width; attack width never
changes the paired scale.

## Files

- Runtime manifest: `assets/characters/body_landmarks.json`
- Runtime helpers: `character_scale.py`
- Drawing integration: `rpg_drawing.py`
- Re-runnable audit tool: `scripts/normalize_character_scale.py`
- Reaction-asset audit: `scripts/audit_reaction_assets.py`
- Regression tests: `tests/test_character_scale.py`
- QA outputs: `tmp/character_scale_audit_reactions/` and
  `tmp/reaction_asset_audit/`

The audit tool does not resample or overwrite any PNG.  It writes CSV/JSON/QA
contact sheets and only promotes a manifest when `--write-manifest` is passed.

## Verification

- Python compilation passed for the runtime, drawing integration, audit tool,
  and character-scale tests.
- Character-scale and combat-reaction regression tests passed by direct
  execution.
- The repository's unittest-compatible suite ran 48 passing tests; two test
  modules could not import because `pytest` is not installed in the local venv.
