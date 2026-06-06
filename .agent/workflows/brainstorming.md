---
description: Brainstorm and design an idea before implementation
---

> **🔗 Linked Skill:** This workflow is permanently coupled with `skills/brainstorming/SKILL.md`.
> Invoking **either** this workflow **or** the skill activates **both**.
> Step 1 below is mandatory and non-skippable.

# Brainstorming Workflow

Use this workflow to turn a vague or complex idea into a clear, validated design *before writing any code*.

## Steps

1. **⚠️ MANDATORY — Read the skill** — Use `view_file` on `skills/brainstorming/SKILL.md` and follow its instructions exactly. This step cannot be skipped. The skill and this workflow are a unified system.

2. **Understand context** — Review existing files, docs, and prior decisions relevant to the idea before asking anything.

3. **Clarify the idea** — Ask one question at a time (prefer multiple-choice). Cover: purpose, users, constraints, success criteria, non-goals.

4. **Clarify non-functional requirements** — Explicitly address performance, scale, security, reliability, and ownership. Propose reasonable defaults if the user is unsure and mark them as assumptions.

5. **Understanding Lock** — Before any design, present a 5–7 bullet summary of what is being built, why, for whom, key constraints, and non-goals. List all assumptions and open questions. Ask:
   > "Does this accurately reflect your intent? Please confirm or correct before we move to design."
   **Do not proceed until the user explicitly confirms.**

6. **Propose design approaches** — Offer 2–3 viable options. Lead with the recommended one. Explain trade-offs (complexity, extensibility, risk, maintenance). Apply YAGNI ruthlessly.

7. **Present design incrementally** — Deliver the design in 200–300 word sections. After each section ask: *"Does this look right so far?"*

8. **Maintain Decision Log** — For every decision record: what was decided, alternatives considered, and why this option was chosen.

9. **Write documentation** — Once the design is validated, save a Markdown document containing: understanding summary, assumptions, decision log, and final design.

10. **Implementation handoff (optional)** — Ask: *"Ready to set up for implementation?"* If yes, create an implementation plan and proceed incrementally.

## Exit Criteria
Only exit brainstorming when **all** of the following are true:
- Understanding Lock confirmed by the user
- At least one design approach explicitly accepted
- Major assumptions documented
- Key risks acknowledged
- Decision Log complete
