Replace this paragraph with the natural-language acceptance criterion.
Use exactly the same instruction for the correct and faulty tasks.

Use the android MCP tools to inspect and operate the app.
Use observe_screen for screenshots and screen text.
Use the device-condition tools when the test requires them.

Finish with one submit_verdict call:

- DEFECT: include flag_step for the recorded screen that shows the defect.
- NO_DEFECT: the app meets the acceptance criterion.
- INCONCLUSIVE: the available observations do not establish the outcome.
