---
description: Phase 2 — Planning. Define exactly what v1 will be, the tech approach, complexity, and what the user needs to decide or set up.
---

# /planning — Product Planning

Run this workflow **after Discovery** when the user has agreed on what they're building. This phase turns the idea into a concrete build plan.

## Prerequisites
- Discovery is complete and the user has a clear v1 feature list
- Must-haves vs. nice-to-haves are agreed upon

## Steps

### 1. Define the V1 Scope
Write a clear, specific description of exactly what will be built:

- List every feature with a one-line description of what it does
- Specify what's NOT included (to set expectations)
- Confirm with user: "This is what I'm going to build. Anything to add or remove?"

### 2. Propose the Technical Approach
Explain the tech stack and architecture in **plain language**:

- **What technologies** will be used and why (in simple terms)
- **How things connect** — a simple diagram or description of the system
- **Why this approach** — what alternatives exist and why this is the best fit
- **Any tradeoffs** the user should know about

> Example: "I'll use Next.js because it handles both the frontend and backend in one project, which means less complexity and faster development."

### 3. Estimate Complexity
Rate the overall build and explain what that means:

| Level | What It Means | Typical Timeline |
|-------|---------------|-----------------|
| **Simple** | Straightforward, well-understood patterns. Few moving parts. | Hours to a day |
| **Medium** | Some complexity — multiple features, integrations, or design work. | 1-3 sessions |
| **Ambitious** | Significant scope — many features, external services, complex logic. | Multiple sessions, possible scope cuts |

### 4. Identify Requirements
List anything the user needs to provide, set up, or decide:

- **Accounts/Services**: API keys, hosting accounts, domain names, etc.
- **Decisions Needed**: Design preferences, business logic choices, content
- **Assets**: Logos, images, copy, brand colors
- **Access**: Databases, third-party services, deployment targets

### 5. Show a Rough Product Outline
Create a visual or structured outline of the finished product:

- **For web apps**: List of pages/screens with brief descriptions
- **For tools/utilities**: Input → Process → Output flow
- **For APIs**: Endpoints and what they do

> Use Stitch or mockup descriptions to give the user a preview of the finished feel.

### 6. Create the Build Plan
Break the build into **stages** that the user can see and react to:

```
Stage 1: Foundation — Project setup, core structure, design system
Stage 2: Core Features — [list the must-have features]
Stage 3: Integration — Connect everything, data flow, state management
Stage 4: Polish — Professional finish, responsiveness, animations
Stage 5: Testing & Launch — Verify everything works, deploy
```

> Each stage should produce something visible/demonstrable.

### 7. Get User Approval
Present the full plan and ask:
- "Does this scope feel right?"
- "Any concerns about the tech approach?"
- "Ready to start building?"

> Do NOT proceed to building until the user explicitly approves.

## When to Move On
Move to `/building` when:
- [x] User approves the v1 scope
- [x] Tech approach is agreed upon
- [x] All required decisions are made
- [x] Build stages are defined
