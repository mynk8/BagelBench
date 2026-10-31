# QA pilot iteration contract

Adapted from Karpathy's autoresearch workflow. This is an engineering/research workflow, not an engine embedded in the product.

Keep the frozen task manifest and published scoring definitions fixed during model or condition comparisons. Change one implementation issue or experimental condition per iteration. Run relevant acceptance checks, inspect failures, and record keep/discard with evidence. Do not optimize scores by altering exclusions, task wording, truth, or admission after viewing model outcomes. A revised protocol requires a new suite ID and a separate comparison.

Required before claiming live pilot success: one matched device pair with confirmed correct state and confirmed fault, discoverability review, matching test prompts, stable protected state, saved verdicts and state reads, and offline score replay. Required before ranking: all 60 trials admitted per model/condition/repeat. Until then, generation and software-check results are the only demonstrated numbers.

Do not reset the user's working tree or commit unrelated pending changes. Record experimental artifacts and use file-level diffs for reversible changes. Device and API absence must remain explicit.
