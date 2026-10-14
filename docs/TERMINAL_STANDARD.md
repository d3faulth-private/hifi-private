# D3FAULTH terminal standard

Agreed direction: 2026-10-14. D3FAULTH is the shared brand; HIFI is the product.
Use this standard when building our command-line tools. Each product keeps its
own features and command names. This document does not change other repositories.

## Design

- Black background, readable white/gray text, green selection and cyan status.
- D3FAULTH header with the product name, version and current privilege/demo state.
- Consistent bordered panels and concise labels, without decorative scrolling text.
- Compact numbered main menu, detailed submenus, keyboard navigation and resize guidance.
- `00 Exit` on the main screen; `00 Back` in submenus. Exiting saves state and
  returns cleanly to the shell. Running operations retain their documented stop controls.
- Show command purpose, effects, requirements, editable arguments and a preview.
- Report observed results, actionable errors and what remains unverified.
- Put applicable recovery controls where users can find them.

## HIFI mapping

| Number | Section | Contents |
| --- | --- | --- |
| 01 | Scan Wi-Fi | Direct live discovery, hidden networks, selection, retry, optional settings |
| 02 | Network Adapter | Select, restart, managed-mode restoration, refresh, details, diagnostics |
| 03 | Dashboard | Overview, session scope, guided steps, optional local explanation |
| 04 | Exploit | Selected-network WPA/WPA2 and WPS actions; advanced engine when no network is selected |
| 05 | Manual Commands | Editable diagnostic, interface, cached-network, file and engine profiles |
| 06 | Sessions & Reports | History, notes, exports, resume instructions |
| 07 | Settings & Help | Dependencies, keyboard controls, CLI reference, about |
| 00 | Exit | Save and return to the shell |

Cached networks are not a fresh scan. Manual Commands uses defined command
profiles, not an unrestricted shell. Network recovery operates on a selected
wireless interface and cannot guarantee a connection. These distinctions must
remain visible in the interface and documentation.

## Development workflow

1. Discuss the intended features, screens, navigation, commands and outcomes.
2. Write the concrete proposed workflow and resolve open decisions.
3. Obtain agreement that locks the workflow before implementation.
4. Build the agreed scope and verify the affected behavior.
5. Update the repository, installation instructions and changelog; report any
   publication blocker or unverified hardware behavior accurately.

Reopen discussion for material scope changes. Routine implementation details and
fixes within an agreed workflow do not require repeated confirmation.
