# Architecture

HIFI consists of a terminal workbench and its bundled `hifi.engine` package.
The engine is a pinned source derivative; provenance, license and changes are in
`CREDITS.md` and `hifi/engine/UPSTREAM.json`. Radio and recovery binaries remain
separately installed dependencies. The menu/demo layer uses the standard library;
the engine uses chardet for text detection and Requests for explicit IEEE updates.

| Module | Responsibility |
| --- | --- |
| `cli.py`, `ui.py` | CLI and curses menus, previews, editing and evidence views |
| `backend.py`, `engine_entry.py` | Resolve this installation's engine from source, wheel or zipapp |
| `engine/` | Integrated wireless discovery, workflow orchestration, backend adapters and result files |
| `catalog.py` | Workbench command builders, bounded-profile edit validation and help |
| `runner.py` | Bounded commands, streamed output, timeout and process-group cleanup |
| `terminal.py` | Interactive PTY, keyboard and resize forwarding, terminal restoration |
| `app.py`, `models.py`, `storage.py` | Execution coordination, sessions and private atomic JSON writes |
| `advisor.py`, `reports.py` | Evidence suggestions, optional explanations and exports |

## Entry points

The installed console entry point is `hifi`. With no arguments it opens menus.
`hifi engine ...` dispatches directly to the included engine. `hifi exploit ...`
uses preview/session recording and the PTY relay. Public command records contain
`hifi engine` arguments; execution resolves the current Python interpreter and
absolute bundled launcher path. Inside a zipapp, the child reopens the same archive
with the `engine` subcommand. No external engine executable is searched or run.

Full engine mode preserves its own target selection and timing. Workbench
capture-only modes enforce interface/BSSID/channel, specific disabled methods and
a finite timeout. These contracts are deliberately visible in menus and help.
The engine retains the baseline option surface; this is not a promise that every
legacy placeholder is implemented or every wireless workflow succeeds.

## Execution and cleanup

Workbench commands are parsed as argv, not shell text. The synchronous engine
helper also preserves argv and drains pipes before waiting; a shell is not used
for packet-forging arguments. External tools are not sandboxed by HIFI.

Bounded profiles run with closed stdin, a separate session and C locale. Escape
cancellation escalates SIGINT to SIGTERM and SIGKILL. Full engine mode uses a
controlling pseudoterminal, inherits the environment, and has no HIFI timeout.
The main thread suspends curses while forwarding keys and window-size changes.
Ctrl+C reaches the engine. The relay restores terminal attributes/handlers and
cleans up its child group on completion or failure.

Direct engine execution uses its own cleanup. Argument errors and exceptions
preserve nonzero exit codes. Saved-result viewing does not require radio tools
or root. SIGKILL/crashes cannot run cleanup, detached processes escape group
cleanup, and terminal restoration does not guarantee radio-interface restoration.

## Evidence and privacy

Records retain public argv, status, code, timing and an approximately 512 KiB
output tail. Interactive records include the working directory. The engine's
native output is displayed directly, then sanitized for storage. It can include
sensitive data. HTML exports escape content; summary exports omit commands,
identifiers, workspaces, notes and output.

Schema-1 sessions gain `engine_args` and `engine_workdir` fields. Loading older
sessions maps their prior field names; old records remain historical evidence.
Reopening restores context and files, not a running job or cracking checkpoint.
New directories/files use private permissions; existing workspaces are not
silently re-permissioned. No model-generated text is executed.

## Maintaining the engine

Keep source origin and modification notices. Compare option names and aliases
against `tests/fixtures/engine-options.json`. For a baseline upgrade, review code,
licensing, assets, dependencies and behavior rather than replacing files blindly.
Keep experimental or unsupported paths explicitly documented and retain separate
hardware validation for each adapter/backend combination.
