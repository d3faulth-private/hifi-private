# Security policy

HIFI 0.3.x is an early release. Keep the operating system and separately installed
packet-processing tools updated. Prefer unprivileged file analysis; live radio
profiles require elevated privileges in this version.

If the repository has GitHub private vulnerability reporting enabled, use its
Security tab to report execution, scope-validation, persistence or disclosure
issues. Otherwise open a minimal issue asking for a private contact channel;
do not post secrets, real captures or exploit details publicly.

Full reports and session records may contain sensitive information. They are
local files, not encrypted vaults. Summary exports omit raw evidence by default.

Full HIFI Exploit uses the bundled engine for native arguments and target selection.
Its radio actions are not constrained by HIFI capture-profile scope or duration.
Native terminal output is displayed directly; saved transcript text is sanitized.
