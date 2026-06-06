---
description: Phase 3 — Building. Develop the product in visible stages with check-ins, testing, and transparent problem-solving.
---

# /building — Product Development

Run this workflow **after Planning** when the user has approved the build plan. This is where the product gets built — incrementally, transparently, and with quality.

## Prerequisites
- Planning is complete and user has approved the build plan
- Tech stack and v1 scope are locked in
- All required decisions have been made

## Core Rules During Building

1. **Build in visible stages.** Every stage should produce something the user can see, react to, and approve before moving on.
2. **Explain as you go.** The user wants to learn. Briefly explain what you're doing and why.
3. **Test before moving on.** Don't stack untested features. Verify each piece works before building the next.
4. **Check in at decision points.** Whenever there's a design choice, UX decision, or fork in the road — stop and ask.
5. **Surface problems as options.** If you hit a blocker, present 2-3 options with pros/cons. Don't silently pick one.

## Steps

### 1. Set Up the Foundation
// turbo
- Initialize the project with the agreed tech stack
- Set up the design system (colors, typography, spacing, components)
- Create the core layout/structure
- Verify it runs cleanly

> **Check-in**: Show the user the blank canvas with the design system applied. "Here's our foundation — does the overall look/feel work for you?"

### 2. Build Core Features (Iteratively)
For each feature in the build plan:

1. **Announce** what you're building next and why
2. **Build** the feature
3. **Test** it works correctly
4. **Show** the user the result
5. **Get approval** before moving on

> Use this pattern for every feature. Don't batch multiple features without check-ins.

### 3. Connect Everything
- Wire up data flow between components
- Ensure state management works correctly
- Test end-to-end user flows
- Handle loading states and transitions

### 4. Handle Edge Cases
- Empty states (no data, first-time user)
- Error states (network failures, invalid input)
- Boundary conditions (very long text, large numbers, etc.)
- Permission/access issues if relevant

### 5. Progress Tracking
Maintain a running checklist in the task artifact:

```markdown
## Build Progress
- [x] Foundation — project setup, design system ✅
- [x] Feature: [name] ✅
- [/] Feature: [name] — in progress
- [ ] Feature: [name]
- [ ] Integration & data flow
- [ ] Edge cases & error handling
```

## Problem-Solving Protocol
When you encounter a problem:

1. **Explain** what happened in plain language
2. **Present options** (usually 2-3):
   - Option A: [description] — Pros: ... / Cons: ...
   - Option B: [description] — Pros: ... / Cons: ...
3. **Recommend** one, but let the user decide
4. **Implement** the user's choice

> Never silently work around a problem. Transparency builds trust.

## Quality Gates
Before moving to Polish, verify:
- [ ] All v1 features are implemented
- [ ] Each feature has been tested
- [ ] User has approved each feature
- [ ] End-to-end flows work correctly
- [ ] No known bugs or broken interactions

## When to Move On
Move to `/polish` when:
- [x] All core features are built and tested
- [x] User has seen and approved each stage
- [x] End-to-end product flow works
