# Contributing

Keep changes focused and explain the user problem, changed behavior and test
evidence. Run `python3 -m unittest discover -s tests -v` before opening a PR.
Prefer standard-library code and small, reviewable command builders.

New integrations need an upstream documentation reference, supported version
assumptions, explicit privilege/side-effect labels, timeouts for bounded profiles, cancellation
behavior and validation tests. Do not label simulated or mocked checks as radio
validation. Include adapter/driver details for hardware results.

The integrated engine intentionally uses native timing and interactive input. Preserve
its argv semantics, the distinction from scoped capture-only profiles, terminal
restoration and summary-report privacy when extending this path.

Never commit real captures, recovered credentials, private logs or identifying
network inventories. Use synthetic fixtures with locally administered addresses.
Use GitHub's private vulnerability reporting when enabled for security issues;
see SECURITY.md before creating a public issue.

Engine changes must preserve upstream attribution and GPL licensing. See CREDITS.md.
