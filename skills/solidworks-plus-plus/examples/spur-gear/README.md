# Native Involute Spur Gear Case

This is a compact, validated modeling case distilled from a successful SolidWorks 2023 run. It is supporting material for `solidworks-plus-plus`; it does not change the skill entrypoint.

## Result

- Native editable part: one SolidWorks solid body
- Geometry: 24 sampled involute teeth, central bore, and a wider hub
- Validation: SolidWorks B-Rep body box and cylindrical-face measurements
- Review: isometric, front, top, and right previews; observed review result `pass`, score `100`
- Original validated native model SHA-256: `ED7D978EC6DB1AD33D133558DF40F53E5B347E0B64E565FFACEAD43F5D1FA00C`

The native model and bitmap previews are deliberately not stored in the skill so the example remains small. The measured result is preserved in `validated-result.json`.

## Parameters

| Parameter | Validated value |
| --- | ---: |
| Teeth | 24 |
| Module | 2.5 mm |
| Pressure angle | 20 deg |
| Pitch diameter | 60 mm |
| Outside diameter | 65 mm |
| Root diameter | 53.75 mm |
| Gear face width | 12 mm |
| Hub | 36 mm diameter x 20 mm width |
| Bore diameter | 20 mm |

## Modeling Pattern

1. Group all editable dimensions at the top of the generator.
2. Derive pitch, base, outside, and root radii from tooth count and module.
3. Sample both sides of each involute tooth and join adjacent teeth along the root circle.
4. Create the bore in the same sketch as the gear outline, then mid-plane extrude the gear body.
5. Add a concentric annular hub with a second mid-plane boss; merging produces one solid body.
6. Validate body count, overall envelope, and bore radius from the SolidWorks B-Rep.
7. Save the native part and produce four review views.

This direct-outline method is appropriate for an editable visual/mechanical gear model. It does not replace a standards-based gear-design calculation when backlash, profile shift, root fillet, tolerance class, heat treatment, or strength rating matters.

## Reuse

Copy `build_spur_gear.py` into the task workspace, edit the parameter block, and run it from that workspace. The script also works when invoked by absolute path because outputs are written to the current working directory.

```powershell
py -3.12 <skill>\examples\spur-gear\build_spur_gear.py
```

The script locates `solidworks-plus-plus` as a sibling installed skill. Override discovery only when needed:

```powershell
$env:SOLIDWORKS_PLUS_PLUS_SKILL_DIR = '<skill 实际安装目录>'  # 仅当自动发现失败时
python .\build_spur_gear.py
```

旧安装目录或旧环境变量 `SOLIDWORKS_MODELING_SKILL_DIR` 仍作为回退被识别。

The preflight call uses `allow_install=False`; running the case never installs Python packages.
