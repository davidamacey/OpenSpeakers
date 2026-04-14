# Contributing to OpenSpeakers

Thank you for your interest in contributing to OpenSpeakers!

OpenSpeakers is developed and maintained by **Attevon LLC** and released under the
[GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0).

---

## Licensing of Contributions

By submitting a pull request or patch to this repository you agree that:

1. Your contribution is your original work (or you have the right to submit it).
2. You license your contribution to Attevon LLC under the same **AGPL-3.0** terms as
   the rest of the project.
3. You understand that Attevon LLC retains the right to re-license the project under
   other terms in the future.

If your employer owns IP you produce, ensure you have permission to contribute before
submitting.

---

## How to Contribute

### Reporting Bugs

- Search [existing issues](../../issues) first to avoid duplicates.
- Use the **Bug Report** issue template.
- Include logs, steps to reproduce, and your OS/GPU/Docker version.

### Suggesting Features

- Open a **Feature Request** issue.
- Describe the use-case and why it belongs in the core project.

### Submitting a Pull Request

1. Fork the repository and create a branch from `main`.
2. Follow the code style (Python: ruff; Frontend: Prettier/svelte-check).
3. Add or update tests for any new backend logic.
4. Run the full test suite before opening your PR:
   ```bash
   docker compose exec backend pytest tests/ -v
   docker compose exec frontend npm run check
   ```
5. Fill out the PR template completely, including the sign-off checkbox.
6. Target the `main` branch.

### Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(tts): add streaming support for Orpheus 3B
fix(worker): prevent VRAM leak after model unload
docs: update model VRAM table in README
```

---

## Development Setup

See the [README](README.md) for full setup instructions. The short version:

```bash
git clone https://github.com/davidamacey/OpenSpeakers.git
cd OpenSpeakers
docker compose up -d
```

---

## Code of Conduct

Be respectful, constructive, and professional in all interactions.
Harassment of any kind will not be tolerated.

---

*Copyright © 2026 Attevon LLC. All rights reserved.*
