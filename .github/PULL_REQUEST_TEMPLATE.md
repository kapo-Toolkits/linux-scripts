## What and why
<!-- One topic. What problem does this solve? -->

## How it was checked
<!-- What you ran (commands) and what you did NOT run (real hardware, real pkexec, real distribution …). -->

## Checklist
- [ ] Offline tests added or updated; none needs hardware, root or the network
- [ ] `ruff check .` and `shellcheck -S warning` on touched shell scripts are clean
- [ ] Every new text exists in English **and** Georgian; the tool's README (and the main README table, if a tool was added) is updated
- [ ] No `shell=True` / shell strings from input; privileged commands only through `pkexec` with a preview
- [ ] Downloads are verified (SHA-256) before use; nothing overwrites or removes files this toolkit did not create
- [ ] `CHANGELOG.md` updated if behaviour changed
- [ ] Security-relevant change? Describe the protection added or changed:
