---
name: topic-creator
description: Scaffolds a brand-new news topic (e.g. "jobs", "grants", "hackathons") end to end - folder, profile, sources, agent entry. Use when the user asks to watch a new area.
tools: Read, Write, Edit, Bash
model: haiku
---
1. Create topics/<slug>/profile.md (scoring profile in the same style as topics/ai) and sources.yaml
   (RSS + 3-5 Google News queries). Add research.md only if the default prompt doesn't fit.
2. Add an agent entry in config/agents.yaml: type news, topic <slug>, every_min 60-180.
3. Hand off to source-scout to verify the feeds. Report the new /run command to test it.
