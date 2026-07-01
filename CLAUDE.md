# CLAUDE.md

Project guidance for Claude Code. The canonical rules and skills live in `.ai/`
and are shared with Cursor via symlinks: skills at `.claude/skills` and
`.cursor/skills` → `../.ai/skills`, and rules at `.cursor/rules` → `../.ai/rules`.
Edit files under `.ai/`; both tools see them.

## Always-on rules

@.ai/rules/repo-overview.mdc

## Skills (load on demand)

Detailed, task-scoped guides live under `.ai/skills/` and are auto-discovered as
on-demand Agent Skills by **both** Claude Code (`.claude/skills/` → `.ai/skills/`)
and Cursor (`.cursor/skills/` → `.ai/skills/`). The agent loads one by its
`description` when a task matches; you can also invoke a skill manually with `/`.

- **auth-system** (`.ai/skills/auth-system/SKILL.md`) — JWT login/refresh/logout,
  web-cookie vs mobile-body token delivery, social sign-in, the custom user model.
- **running-the-app** (`.ai/skills/running-the-app/SKILL.md`) — environments,
  Docker containers, start/stop scripts, migrations and management commands.
