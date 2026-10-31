# Evaluation packaging basis

We reviewed the task and release conventions used by AndroidWorld, OSWorld, and Terminal-Bench and applied their strongest relevant pieces to Android QA.

| Benchmark | Packaging/evaluation practice | Applied here |
|---|---|---|
| AndroidWorld | Parameterized natural-language tasks; explicit initialization, state-based success evaluator, teardown; 116 templates over 20 apps | Reuse its task data and oracle source; freeze parameters/seeds and record the exact upstream revision |
| OSWorld | Self-contained task JSON with `id`, `instruction`, `source`, `related_apps`, setup `config` array, and an execution evaluator with result/expected values | Export one task record per control/fault variant in that shape; attach pair IDs and keep setup/evaluator hidden from the agent |
| Terminal-Bench | Isolated environment, instruction, tests that inspect final state, reference solution; task correctness review and oracle/no-op checks | Admit cases only after both labels are confirmed, no-op/fault checks hold, reset is reproducible, instruction and oracle align, and reviewers inspect it |

The benchmark unit differs from an ordinary task-completion benchmark: it is a matched **control/fault pair** with one shared inspection prompt. The agent's `PASS` or `FAIL` is compared to a hidden independent state oracle. Screenshots and accessibility trees record what was available to the agent; they are not substituted for durable-state truth.

## Sources

- OSWorld, task format and paper: <https://timothyxxx.github.io/OSWorld/user_guides/task_example_explanation.html>, <https://arxiv.org/abs/2404.07972>
- AndroidWorld paper and repository: <https://arxiv.org/abs/2405.14573>, <https://github.com/google-research/android_world/tree/55ddaf5edc6f6c25673aed343907d5b9dca66f84>
- Terminal-Bench paper and contributor/verifier conventions: <https://arxiv.org/abs/2601.11868>, <https://github.com/harbor-framework/terminal-bench/blob/main/CONTRIBUTING.md>
- Android functional bug study: <https://doi.org/10.1145/3597926.3598138>
- MDroid+ mutation operators: <https://doi.org/10.1145/3106237.3106275>
- Stoat state/transition exploration: <https://doi.org/10.1145/3106237.3106298>
- DDLDroid lifecycle/persistence bugs: <https://doi.org/10.1145/3597926.3598089>
- Nighthawk visual issue detection: <https://doi.org/10.1109/TSE.2022.3150876>

This packaging review borrows the task-unit and verifier structure. The use of matched app-state controls/faults and a separately measured success signal is our research design; these cited systems do not provide that exact Android QA benchmark.
