# Competitive Landscape: AI Screen Context (March 2026)

## Summary

Nobody is building a permissions layer for screen access. The space is fragmented, privacy-sensitive, and consolidating. Our positioning: local, open-source, privacy-first API that gives AI controlled access to your screen -- the trusted gatekeeper, not the surveillance tool.

## Key Players

### Rewind.ai / Limitless -- DEAD

- Meta acquired Limitless (formerly Rewind.ai) in December 2025
- Desktop app shut down December 19, 2025
- Only the Pendant hardware device continues with limited support
- The app recorded screen + audio locally with AI search
- Market lesson: the approach worked but couldn't survive independently

### Microsoft Recall -- LAUNCHED, TRUST ISSUES

- Finally launched November 2025 on Copilot+ PCs
- Captures screenshots every few seconds, stores locally
- Had severe privacy backlash -- shifted from opt-out to opt-in
- Encrypted locally, requires Windows Hello auth
- Windows only, specific hardware required
- Market lesson: continuous recording triggers privacy fears even from Microsoft

### Screenpipe -- MAIN OPEN SOURCE COMPETITOR

- Full local + private operation
- Records screen and audio continuously
- Searchable AI memory of everything you see/hear
- $400 one-time for desktop app, MIT-licensed core
- Implements MCP for AI tool integration
- Works on macOS, Windows, Linux
- Weakness: continuous recording (heavy), no permission model, expensive app

### Apple Intelligence / Siri

- Building "onscreen awareness" for Siri via App Intents framework
- Delayed from iOS 18.2 to 18.4 (spring 2025)
- Requires each app to opt in and expose content
- Visual Intelligence for camera/screenshot understanding
- Vision Framework available to developers for OCR
- Weakness: requires app cooperation, Siri-only, slow rollout

### Claude / Anthropic

- Co-Work: office productivity tool (Excel, PowerPoint add-ins, Google Drive)
- Computer Use: on-demand screenshots, not ambient
- Hidden "Echo" project found in Claude Desktop code (ambient monitoring research)
- No shipped ambient screen watching capability
- MCP is their protocol for tool integration

### Other Open Source

- **AI Cowork**: free, open-source screen-aware assistant (Ollama/OpenAI/Claude backends)
- **Familiar**: turns screen + clipboard into AI context, offline-first
- **Screenhand**: MCP server for desktop automation + screenshots
- None has achieved significant adoption

## The Gap: No Permissions Layer

Nobody is building the "OAuth for screen access":

| Product | Screen Access | Permission Model |
|---------|--------------|-----------------|
| Apple App Intents | App opts in to Siri only | One-directional, Apple-controlled |
| Microsoft Recall | Captures everything | All or nothing, no per-tool control |
| Screenpipe | Records everything | Open MCP, no access control |
| Claude computer use | On-demand screenshots | Binary: can or can't |

Missing: a trusted local layer where AI tools REQUEST access, users GRANT/REVOKE per-tool, and the layer CONTROLS what gets shared (full screen, specific app, redacted). Local and auditable.

## Our Positioning

- Lightweight: look when asked, not continuous recording
- Local: everything on-device, nothing leaves the machine
- Open source: trust through transparency
- API-first: HTTP + MCP, any AI tool can integrate
- Privacy layer: the gatekeeper between your screen and AI
- Permission model: future differentiation (per-tool access control)

## Market Signals

- Rewind's death + Meta acquisition = big tech wants to own this
- Recall's privacy backlash = users care deeply about control
- Screenpipe's $400 price point = willingness to pay exists
- MCP adoption growing = standard protocol for AI tool integration
- Apple's slow rollout = opportunity window for indie tools
