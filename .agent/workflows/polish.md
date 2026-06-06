---
description: Phase 4 — Polish. Make the product professional, handle edge cases, optimize performance, and add finishing touches.
---

# /polish — Professional Finishing

Run this workflow **after Building** when all core features work. This phase transforms a working product into a **polished, professional** product.

## Prerequisites
- All v1 features are built and tested
- User has approved the core product
- End-to-end flows work correctly

## Steps

### 1. Visual Polish
Make it look like a product, not a project:

- **Typography**: Consistent font sizes, weights, and spacing
- **Color consistency**: Unified palette, proper contrast ratios (WCAG AA)
- **Spacing & alignment**: Consistent padding, margins, grid alignment
- **Icons & imagery**: Professional, cohesive iconography
- **Dark mode**: If relevant, ensure it works beautifully

### 2. Micro-Interactions & Animations
Add life to the interface:

- **Hover effects**: Buttons, cards, links respond to hover
- **Transitions**: Smooth page/component transitions (200-300ms)
- **Loading states**: Skeleton screens or elegant spinners, not blank screens
- **Feedback**: Visual confirmation for user actions (saves, deletes, submits)
- **Scroll effects**: Subtle parallax or reveal animations where appropriate

> Keep animations subtle and purposeful. They should enhance, not distract.

### 3. Responsive Design
Ensure it works everywhere:

- **Mobile** (360px+): Touch-friendly, readable, no horizontal scrolling
- **Tablet** (768px+): Optimal layout for medium screens
- **Desktop** (1024px+): Full experience with proper use of space
- **Large screens** (1440px+): Content doesn't stretch awkwardly

> Test each breakpoint. Don't just shrink the desktop — design for each size.

### 4. Error Handling & Edge Cases
Handle things gracefully:

- **Form validation**: Inline errors, clear messages, prevent bad submissions
- **Network errors**: Friendly messages, retry options
- **Empty states**: Helpful guidance when there's no data yet
- **404 / Not Found**: Custom, branded error pages
- **Rate limiting / timeouts**: User-friendly feedback

### 5. Performance Optimization
Make it fast:

- **Images**: Optimized sizes, lazy loading, modern formats (WebP)
- **Code splitting**: Load only what's needed for each page
- **Caching**: Cache static assets and API responses where appropriate
- **Lighthouse audit**: Aim for 90+ on Performance, Accessibility, Best Practices
- **First paint**: Target under 1.5 seconds

### 6. Accessibility
Ensure it's usable by everyone:

- **Keyboard navigation**: All interactive elements reachable via keyboard
- **Screen readers**: Proper ARIA labels and semantic HTML
- **Color contrast**: Meets WCAG AA standards (4.5:1 for text)
- **Focus indicators**: Visible focus states for keyboard users

### 7. Final Details
The small things that make it feel finished:

- **Favicon**: Custom, branded favicon
- **Page titles**: Descriptive titles for each page/view
- **Meta tags**: Open Graph tags for social sharing
- **Loading screen**: Branded initial load if needed
- **Copyright / footer**: Professional footer with appropriate info
- **Console**: No errors or warnings in the browser console

### 8. Polish Review
Present the polished product to the user:

- Show before/after comparisons where meaningful
- Walk through the full user journey
- Highlight the details that make it feel professional
- Ask: "Does this feel finished to you? Anything that still feels rough?"

## When to Move On
Move to `/handoff` when:
- [x] User says "this feels finished"
- [x] No visual or functional rough edges remain
- [x] Performance is acceptable
- [x] Responsive design works across devices
