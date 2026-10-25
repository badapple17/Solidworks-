# Image or Drawing to SolidWorks Part

Use this guide when the source is one or more screenshots, photos, sketches, or engineering drawing views.

## 1. Normalize the Inputs

- Inspect all views together. A feature hidden in one view may define depth in another.
- Correct mentally for perspective: parallel model edges can converge in a photo.
- Identify the likely front, top, right, and isometric views.
- Record the source of each dimension as `explicit`, `derived`, or `estimated`.
- Prefer a repeated or functional dimension such as a shaft diameter, mounting-hole pitch, or standard fastener size as the scale anchor.

Use a table like this in working notes:

| Parameter | Value | Source | Confidence |
| --- | ---: | --- | --- |
| Overall length | 174 mm | Explicit drawing dimension | High |
| Base width | 90 mm | Ratio from top view | Medium |
| Rib thickness | 16 mm | Estimated from isometric view | Low |

When approximate geometry is allowed, choose a coherent set of rounded values rather than false precision. Keep mating diameters, hole spacing, concentricity, and symmetry more faithful than decorative radii.

## 2. Establish Axes and Origin

Choose an origin that makes the model stable under parameter changes:

- Put symmetric parts on the origin and use mid-plane extrudes.
- Put a shaft or bore axis on a principal axis.
- Put the base mid-plane or a mounting face on a default reference plane.
- Document axis meanings in the generator, for example `X = overall length`, `Y = height`, and `Z = depth`.

Do not infer plane orientation from screen appearance alone. Confirm it from the resulting body box after the first feature.

## 3. Decompose by Manufacturing Intent

Select features that match the likely construction:

| Visible geometry | Preferred SolidWorks feature |
| --- | --- |
| Plate, bracket, prismatic housing | Boss extrude |
| Shaft, pulley, turned collar | Revolve |
| Uniform bore or pocket | Cut extrude |
| Radial or linear repetition | Circular or linear pattern |
| Constant profile following a route | Sweep |
| Changing sections | Loft |
| Thin reinforcement | Rib or thin boss extrude |
| Rounded manufactured edge | Fillet, added last |

Build in this order unless the geometry strongly suggests otherwise:

1. Primary envelope or base.
2. Main load-bearing body.
3. Bosses, collars, webs, and ribs.
4. Functional bores, pockets, and mounting holes.
5. Repeated features and mirrors.
6. Fillets, chamfers, and minor cosmetic details.

This order produces a useful editable part even if a late cosmetic API operation fails.

## 4. Parameterize for Regeneration

- Group dimensions in one block near the top of the script.
- Store values in descriptive names, not scattered literals.
- Derive dependent dimensions mathematically, for example `mount_half_x = hole_pitch_x / 2`.
- Keep clearances positive and assert impossible combinations before launching SolidWorks.
- Use non-conflicting output names so reruns do not overwrite a user's inspected model.

Recommended structure:

```python
MM = 0.001

BASE_LENGTH = 174 * MM
BASE_WIDTH = 90 * MM
BASE_THICKNESS = 15 * MM
SHAFT_BORE_DIA = 28 * MM

assert SHAFT_BORE_DIA < BODY_OUTER_DIA
```

## 5. Make COM Automation Recoverable

- Raise a specific error immediately when a sketch entity, feature, rebuild, or save fails.
- Print the name of each completed feature so a failed run identifies its stopping point.
- Close only the unsaved model created by the current failed attempt; do not close the user's unrelated documents.
- Release COM references in `finally` and leave the successfully generated document open.
- Expect direction and localization differences. Prefer topology-independent selection and validate orientation numerically.

If a boss or cut goes the wrong way, use this recovery sequence:

1. Complete a first attempt.
2. Read solid-body count and body box.
3. Compare minimum/maximum coordinates and envelope dimensions with expectations.
4. Close that unsaved attempt.
5. Rebuild once with the suspect direction reversed.

## 6. Validate Geometry, Not Just File Creation

Minimum validation for a native part:

- Expected number of solid bodies.
- Envelope dimensions within a stated tolerance.
- Critical named features present.
- No failed rebuild.
- Successful native save and an existing output file.

For a dimensioned drawing, use a typical envelope tolerance of the larger of `0.1 mm` or `0.2%` unless the drawing states another tolerance. For a perspective image, select tolerances that reflect the uncertainty, often `2%` to `5%`.

Visual inspection still matters. Show isometric zoom-to-fit and check that:

- the model is not blank;
- principal axes and proportions match the references;
- bores are open and concentric where expected;
- ribs and bosses join the main body;
- no feature unexpectedly created a second body.

## 7. Handoff

Report:

- native model path;
- generator path;
- overall validated dimensions;
- body count;
- major assumptions and inferred dimensions;
- omitted details, if any;
- requested exports and their paths.

Keep the explanation concise. The editable model and grouped parameters are the main handoff.
