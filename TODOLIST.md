# TODO List

## Core Architecture

- [ ] Remove remaining legacy helper methods from `src/ai_indexer/core/engine.py` now that discovery, classification, and graph logic live in dedicated modules.
- [ ] Split the rest of `engine.py` into smaller orchestration-focused pieces.
- [x] Introduce an explicit analysis pipeline object with named stages.
- [x] Add a stable internal schema for analysis records instead of passing raw dicts across the stack.

## Analysis Quality

- [x] Improve import resolution for modern Python layouts, namespace packages, and multi-root projects.
- [x] Improve TypeScript/JavaScript import resolution for re-exports, aliases, workspaces, and nested barrels.
- [ ] Expand domain classification beyond keyword heuristics.
- [ ] Calibrate criticality scoring with more signals and clearer precedence.
- [ ] Replace the current complexity proxy with a richer complexity model.
- [ ] Add explainability for file scores and classifications.

## Exporters

- [x] Add snapshot tests for JSON, XML, TOON, Markdown, and HTML outputs.
- [x] Normalize all exporters through a single canonical output adapter.
- [x] Add format-specific schema validation for exported documents.
- [x] Improve the HTML dashboard with filters, search, and graph interactions.
- [x] Expand XML and TOON to expose score explanations and analysis metadata consistently.

## Testing

- [x] Add unit tests for all classification helpers.
- [x] Add unit tests for graph helpers and scoring helpers.
- [x] Add integration fixtures for Python, TypeScript, and mixed-language projects.
- [x] Add end-to-end CLI tests for common commands and flags.
- [x] Add regression tests for cache behavior and invalidation.
- [x] Add contract tests for MCP responses.

## Tooling

- [x] Add CI for Windows, Linux, and macOS.
- [x] Add a build-and-smoke-test workflow for the package.
- [x] Add release automation and changelog generation.
- [ ] Add benchmarks for large repositories.
- [x] Add diagnostics mode for runtime quality and fallback reporting.

## CLI and UX

- [x] Add analysis profiles such as fast, standard, deep, and security.
- [x] Add a summary-only output mode for quick use.
- [x] Add fail-on-warning and fail-on-secret options.
- [x] Add a config validation command.
- [x] Improve error messages for missing optional dependencies.

## MCP

- [x] Add pagination and filters to MCP queries.
- [x] Add subgraph and dependency-chain queries.
- [x] Add score explanation endpoints.
- [x] Add cycle listing and volatility queries.
- [x] Add contract tests for protocol stability.

## Audio Tour

- [x] Clean up the audio tour pipeline and make narration options configurable.
- [x] Add language and voice selection flags.
- [x] Add dedicated tests for tour generation and script output.

## Documentation

- [x] Align the README with the current implementation and mark experimental features clearly.
- [x] Document the analysis pipeline and data model.
- [x] Document how to add parsers, exporters, and custom rules.
- [x] Add developer guidance for fixtures and snapshots.

## Next Backlog

- [ ] Finish removing duplicated scoring and detection helpers still living inside `src/ai_indexer/core/engine.py`.
- [ ] Extract scoring, architecture rules, and context generation out of `engine.py`.
- [ ] Replace keyword-only domain classification with evidence-based classification using imports, symbols, docs, and config overrides.
- [ ] Rework criticality scoring to factor auth, data access, entrypoints, secrets, and graph centrality with explicit precedence.
- [ ] Replace the current complexity proxy with parser-aware branching and nesting signals.
- [ ] Unify score/classification explainability across JSON, Markdown, HTML, and MCP in a single reusable model.
- [ ] Add repeatable benchmark fixtures and performance thresholds for large repositories.
- [ ] Harden the HTML dashboard supply chain by removing or vendoring external CDN runtime dependencies.
