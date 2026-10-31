# AndroidWorld oracle audit

Audit target: all 116 registered tasks in AndroidWorld `ANDROID_WORLD_FAMILY` at revision `55ddaf5edc6f6c25673aed343907d5b9dca66f84`.

The audit imports task classes and inspects the `is_successful` implementation and source file. It does **not** start an emulator, invoke an evaluator against app state, run an agent, or establish QA fault cases. Counts are task templates, not distinct apps, bugs, or validated benchmark instances.

## Source-audited evaluator types

| Evaluator source family | Templates | What the existing evaluator can check | QA adaptation still needed |
|---|---:|---|---|
| Structured SQLite | 30 | Rows added/removed against generated target and noise rows | Invert into hidden control/fault criteria; add exact protected-row and discoverability assertions |
| Seeded-state retrieval | 25 | Agent answer matched against task-proto expected answer after deterministic app-state setup | Build inspect-only prompts, independently retain target state, and prevent answer/expected value leakage |
| Filesystem and media files | 20 | File presence, move/delete, note-related file state, or media artifact presence | Add content/hash/side-effect assertions where the source evaluator only checks existence |
| Provider state | 7 | Contacts or SMS provider records | Use synthetic records, local-only messaging, exact before/after and collateral-state checks |
| Android system state | 14 | Settings values, launcher/activity state, clipboard state | Add matched negative state and protected-setting assertions |
| App-specific state | 10 | Task-specific stored state in maps/media/drawing apps | Review each predicate for exactness and whether it supports inspection rather than just completion |
| Composite state | 3 | Two or more component task evaluators | Split and preserve each component oracle; add cross-component side-effect checks |
| UI state | 7 | Accessibility-tree/activity state, including Clock state and Browser success sentinel | Does not currently assert layout overlap, clipping, or visual correctness; add geometry criteria and reviewed faulty screens |
| **Total** | **116** | Every registered template has an executable `is_successful` implementation in source | None of these counts means a QA fault pair is already admitted |

The first seven non-UI categories total **109** task templates with state/API-backed oracle patterns; **7** templates use UI/activity-state predicates. This is a source-level classification. It does not mean all 109 use equally strong exact predicates: the 25 retrieval tasks judge an answer against a task-proto target, filesystem tasks can be existence-only, and custom app evaluators need individual source review.

## What this establishes

- There are enough deterministic state hooks to start building much more than record-value cases: CRUD, file operations, contacts, SMS, settings, media, and app-specific state are represented.
- Many AndroidWorld tasks already carry generated target and distractor values. These can become correct/fault pairs by seeding a correct state and applying one confirmed mutation before presenting an inspection-only instruction.
- A deterministic final-state evaluator is not a navigation oracle. To score navigation, add a required transition sequence or state graph, then independently assert it from activity/tree snapshots and final state.
- Screen variation is not a visual-defect set. Bounds can be evaluated geometrically, but overlap/clipping labels and harmfulness need explicit predicates, faulted layouts, and screenshot review.
- AndroidWorld has no paired deceptive-success-message cases or membership/login corpus. Those need a controlled app hook/patched APK and a synthetic account service, respectively.

## Reproduce the audit

```sh
/path/to/android_world/.venv/bin/python apps/research_ui/scripts/audit_androidworld_oracles.py \
  --androidworld-root /path/to/android_world \
  --out-dir apps/research_ui/datasets/androidworld/oracle_inventory
```

The JSONL and CSV contain one row per registered task, including its metadata, task source, evaluator method, evaluator source, inferred oracle family, and QA reuse note. The summary file records the revision and category counts. Lists are JSON-encoded inside CSV cells.
