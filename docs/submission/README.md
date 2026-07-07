# Qwen Cloud Hackathon Submission Pack

This folder contains submission-facing materials for the Qwen Cloud hackathon entry for `aki`.

## Files

- `summary.md` - concise written summary for the submission form or README excerpt.
- `video-script.md` - 1 to 3 minute English video script with short, subtitle-friendly lines.
- `checklist.md` - submission checklist, architecture diagram guidance, and deployment proof guidance.

## Core Demo Angle

Show one clear behavior change.
Save a project decision in Aki.
Then ask the coding agent a question that depends on that decision.
The answer changes because the agent reads durable project memory first.

Recommended example:

1. Save: "We use pnpm in this project."
2. Ask: "How should I install dependencies for this repo?"
3. Show that the answer uses `pnpm` because memory was retrieved.

This is the strongest proof of the MemoryAgent story.
