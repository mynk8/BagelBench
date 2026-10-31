# Codebase structure

Bagel provides Android QA benchmark infrastructure for external agent harnesses.
Harbor owns agent execution. Bagel owns the device interface and private evaluation.

## Domains and transports

```text
bagel/
├── benchmark/             Policy, private slots, records, grading and scoring
├── device/
│   ├── context.py         Device clients and controller caches
│   ├── actions.py         Actuator capabilities
│   ├── results.py         Action and observation results
│   ├── conditions.py      Fixed device-condition commands
│   ├── factory.py         Construct actuators and controllers
│   ├── observation.py     Capture screenshots and index visible UI elements
│   ├── recording.py       Device video utilities
│   ├── actuators/         ADB and mock implementations
│   ├── clients/           Accessibility and hierarchy clients
│   ├── controllers/       Device controller implementations
│   ├── drivers/           Android and mock drivers
│   └── perception/        Screen geometry and UI presentation
├── integrations/
│   └── harbor.py          Android contract for native Harbor tasks
├── transports/
│   ├── mcp/benchmark.py   Recorded benchmark tools
│   ├── mcp/specs.py       Device tool schemas
│   └── http/benchmark.py  Task endpoints and protected verifier access
├── interfaces/cli/        Benchmark and device commands
├── diagnostics/           Host and device checks
├── runtime/               Device locks, endpoints and helper lifecycle
├── config/                Device settings and host paths
├── data_engine/           Legacy SQLite readers for retained XML search tools
├── platform/              Host operating-system support
├── toolchain/             Android tooling discovery
└── utils/                 Python compatibility utilities

templates/android-harbor/  Native Harbor task template
scripts/androidworld/     Dataset preparation and audit tools
third_party/mobile_use/   Retained vendored device implementations
apps/research_ui/datasets/ Historical datasets; no browser code
```

The browser, web backend, Flash runner, log analyzer, agent SDK, model providers, and transcript memory have been removed.
Bagel no longer configures or calls models.

## Dependency rules

Benchmark rules use the Python standard library. They do not import device drivers, MCP, HTTP, Harbor, or model clients.
Device operations do not import transport adapters or Harbor.
Diagnostics use device factories directly.

MCP and HTTP adapters call domain operations and translate protocol messages.
The Harbor integration reads native task directories and validates Android-specific metadata.
There is no second task format or export step.

The root package exports the version without initializing device services.
Architecture tests enforce the domain boundaries.

## Tasks and evidence

Each task contains a public natural-language instruction and private setup and verifier files.
The same instruction applies to both builds of a verified correct/faulty pair.
Build labels, symptom signatures, and setup commands stay outside agent inputs.

The recorder owns numbered steps, screenshots, and the submitted verdict.
Private HTTP endpoints expose records and computed rewards only to the authenticated verifier.
The grader uses this harness-owned record rather than model explanations.

The current signature grader remains in `benchmark/grading.py`.
A framework for navigation, layout, screenshot, and data checks is subsequent work.
The [capture journal and evaluator plan](capture-journal-evaluation-plan.md) describes that work and the open questions for each bucket.

## Commands

```text
bagel bench serve
bagel bench validate-tasks
bagel bench grade
bagel bench score
bagel doctor
bagel helper
```

Agents run through `harbor run`.
The former `bagel run`, `run-reference`, Python agent SDK, and web server entry points have been removed.

The legacy stdio ADB and XML-search servers remain under `transports/mcp/`, as requested.
They are outside the benchmark tool policy. Native task templates use the recorded benchmark server.
XML search retains its SQLite reader for historical image records.

## Verification

The default test suite covers benchmark rules, native task validation, MCP/HTTP behavior, and architecture boundaries.
Explicit device tests live in `tests/integration/`.
`pyright-core.json` lists existing benchmark, device, integration, and transport modules.

Frozen datasets and historical research documents retain their contents.
`AGENTS.md` remains unchanged. The owner's Android QA benchmark direction governs this cleanup.
