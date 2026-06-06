---
description: Phase 5 — Handoff. Deploy the product, document everything, and plan v2 improvements.
---

# /handoff — Deployment & Documentation

Run this workflow **after Polish** when the product is finished and the user is happy with it. This phase makes the product independent of this conversation.

## Prerequisites
- Product is fully built and polished
- User has approved the final version
- No outstanding bugs or rough edges

## Steps

### 1. Deployment (If Requested)
Ask the user: "Do you want this deployed/online? If so, where?"

Options to present:
- **Vercel** — Best for Next.js/React apps. Free tier, instant deploys.
- **Netlify** — Great for static sites and simple apps. Free tier.
- **GitHub Pages** — Free, good for static sites.
- **Railway / Render** — Good for apps with backends/databases.
- **Self-hosted** — User's own server.

Deployment checklist:
- [ ] Environment variables configured
- [ ] Production build succeeds
- [ ] Custom domain set up (if requested)
- [ ] HTTPS enabled
- [ ] Deployed and accessible

### 2. Create User Documentation
Write a clear `README.md` in the project root covering:

```markdown
# [Product Name]
One-line description

## What It Does
Brief description of the product and its purpose

## Getting Started
Step-by-step instructions to run locally

## How to Use
Guide for end users — what they can do and how

## Project Structure
Brief overview of how the code is organized

## Configuration
Environment variables, settings, and how to change them

## Deployment
How to deploy or redeploy
```

### 3. Create Maintenance Guide
Write a `MAINTENANCE.md` covering:

- **How to make common changes** (update text, add items, change colors)
- **How to add new features** (where to add code, patterns to follow)
- **Dependencies** and how to update them
- **Known limitations** and workarounds
- **Troubleshooting** common issues

### 4. V2 Roadmap
Create a `ROADMAP.md` listing:

- **Deferred features** from Discovery (the "nice to haves")
- **Improvements** you noticed during building
- **User feedback items** — things to watch for after real usage
- **Technical improvements** — performance, scalability, refactoring

Prioritize by impact:
| Priority | Feature | Why |
|----------|---------|-----|
| High | [feature] | [reason] |
| Medium | [feature] | [reason] |
| Low | [feature] | [reason] |

### 5. Final Walkthrough
Do a complete walkthrough with the user:

1. Show the final product running
2. Walk through every feature
3. Show the documentation
4. Explain how to make changes
5. Answer any remaining questions

### 6. Knowledge Transfer
Ensure the user understands:

- [ ] How to run the project locally
- [ ] How to deploy changes
- [ ] Where the code lives and how it's organized
- [ ] How to make simple modifications
- [ ] Where to find help if they get stuck

## Completion Checklist
- [ ] Product is deployed (if requested)
- [ ] README.md is complete
- [ ] MAINTENANCE.md is complete
- [ ] ROADMAP.md is complete
- [ ] User has done a final walkthrough
- [ ] User feels confident they can maintain the product
- [ ] 🎉 Ship it!
