# Third-Party Notices

SolidWorks++ is a derivative work that incorporates material from the
following MIT-licensed projects. Their notices are reproduced here as
required by the MIT License.

## 1. solidworks-automation-skill

- Repository: https://github.com/wzyn20051216/solidworks-automation-skill
- License: MIT
- Copyright: Copyright (c) 2026 SolidWorks Automation Skill Contributors
- What was used:
  - Version-compatibility records for SolidWorks 2024 / 2026, recorded as
    `upstream_verified_versions` in `capabilities.yaml`. These versions have
    **not** been retested in this repository; only SolidWorks 2023 SP0.1 is
    locally verified.
  - Workflow and capability organization ideas that informed the structure of
    this skill.
- The full MIT text is reproduced in the root `LICENSE` file.

## 2. text-to-cad

- Repository: https://github.com/earthtojake/text-to-cad
- License: MIT
- Copyright: Copyright (c) 2026 Thompson Labs LLC
- What was used:
  - Methodology only, primarily from `skills/engineering-drawing` and
    `skills/cad`: drawing-as-a-derived-document discipline, evidence and
    inspection rules, snapshot policy, repair loop, reproduce-vs-inspiration
    guidance, conflict resolution for dimension sources, and
    search-before-placeholder rules for purchasable parts.
  - No runtime code (build123d / OCCT / cadgen) was copied. SolidWorks++ uses
    its own COM-based scripts.
- The full MIT text is reproduced in the root `LICENSE` file.

## 3. Standards and documentation

- GB/T drawing standards and mechanical design handbooks are referenced for
  dimensioning, tolerance and standard-part values. They are cited as
  references, not redistributed.
- SolidWorks is a registered trademark of Dassault Systèmes. This project is
  unofficial and is not affiliated with, sponsored by, or endorsed by
  Dassault Systèmes.
