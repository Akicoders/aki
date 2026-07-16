# Submission Checklist

## Required Assets

- [ ] Public repository link is ready and accessible.
- [ ] Written summary is ready in English.
- [ ] Demo video is between 1 and 3 minutes.
- [x] Architecture diagram is prepared.
- [ ] Proof of Alibaba Cloud deployment is captured.

## Recommended Repo Link

- [ ] Confirm `https://github.com/Akicoders/aki` is public at submission time.

## Demo Checklist

- [ ] Show that Aki runs through MCP.
- [ ] Show one memory being saved.
- [ ] Show one follow-up question where the answer changes because memory was retrieved.
- [ ] Keep the demo centered on the MemoryAgent story, not only on CLI features.
- [ ] If time allows, add a fast glimpse of Qwen extraction from prose.

## Architecture Diagram Guidance

Files created:
- `architecture.svg` — standalone SVG, open in any browser or image viewer
- `diagram.html` — dark-themed viewer with the diagram centered

Use these boxes:

1. `AI Coding Host`
2. `Aki MCP Server`
3. `Memory Tool Layer`
4. `Memory Store: SQLite + ChromaDB`
5. `Qwen Cloud`
6. `Optional Operator Views: Cockpit / Audit / Project Registry`

Use these arrows:

1. `AI Coding Host -> Aki MCP Server`
Label: `MCP over stdio`

2. `Aki MCP Server -> Memory Tool Layer`
Label: `memory_context, memory_search, memory_save, memory_extract, memory_explain`

3. `Memory Tool Layer -> Memory Store`
Label: `facts, decisions, procedures, retrieval`

4. `Memory Tool Layer -> Qwen Cloud`
Label: `structured extraction and explanation`

5. `Cockpit / Audit / Registry -> Memory Store`
Label: `read-only project visibility and operations`

Add these callout bullets next to the diagram:

- Local-first project memory.
- Project-scoped retrieval for coding agents.
- Qwen-powered extraction from unstructured text.
- Core memory tools (`memory_context`, `memory_search`, `memory_save`) still work without Qwen credentials — extraction and explanation degrade gracefully instead of crashing. Note: the conversational agent (`aki chat` / Cockpit chat) itself requires Qwen, since it's the model doing the reasoning.
- Alibaba Cloud deployment used for submission proof.

## Proof-of-Deployment Screenshot Guidance

Capture one clean screenshot, or two if needed.

Best option:

1. Alibaba Cloud console page showing the running resource.
2. Terminal on the instance showing the running Aki container or process.

Include as many of these as possible in the frame:

- Alibaba Cloud account console header.
- ECS instance name or instance ID.
- Region.
- Running container or process name.
- Project or image name related to Aki.
- Current date or recent timestamp if visible.

Useful terminal evidence to show on the server:

```bash
docker ps
docker compose -f docker-compose.prod.yml ps
```

If you want one stronger proof image, show split screen:

- Left: Alibaba Cloud ECS console.
- Right: terminal with the running Aki service or container.

## Manual Assets Still Needed

- The final public repo URL confirmation.
- The actual recorded demo video file.
- [x] The final architecture diagram image. (`docs/submission/architecture.svg`)
- The actual Alibaba Cloud deployment screenshot.
