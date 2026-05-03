# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

## Project-Specific Notes: Amazon Time Cost

A Chrome extension (Manifest V3) that rewrites Amazon prices as hours of work based on the user's hourly wage.

### Architecture

Content scripts load in this order (see `manifest.json`) and rely on globals attached to `window`:

1. `lib.js` — pure helpers: price parsing, hour math, time formatting
2. `settings.js` — wage and toggle state from `chrome.storage`
3. `findPrices.js` — DOM walker that locates prices on amazon.com
4. `framing.js` — selects the framing copy ("2h 30m of work")
5. `amortization.js` — multi-use item time-cost spreading
6. `subscription.js` — recurring price detection
7. `render.js` — injects badges, hides dollar amounts when toggled
8. `content.js` — entry point; sets up the `MutationObserver`

`popup.{html,js,css}` and `options.{html,js,css}` are separate UI surfaces backed by `chrome.storage`.

### Constraints

- amazon.com only. Do not silently extend host matches in `manifest.json` to other regions — currency conversion is out of scope.
- No build step, no bundler, no npm. Plain ES module-free scripts loaded by Chrome in declared order.
- No new runtime dependencies. The extension ships exactly the files in this repo.
- Permissions are intentionally minimal (`storage` + `*://*.amazon.com/*`). Do not add permissions without explicit instruction.

### Testing

Pure logic in `lib.js`, `findPrices.js`, `framing.js`, `amortization.js`, `subscription.js` is unit-tested. Run via Apple's built-in JavaScriptCore:

```
/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc lib.js tests/test.js
```

Individual test files (`tests/*.test.js`) follow the same `jsc <module> tests/<module>.test.js` pattern.

When fixing bugs or adding logic, add a failing test first (per §4), then make it pass. DOM-touching code (`render.js`, `content.js`) is not unit-tested — verify by loading the unpacked extension on a real amazon.com page.

### Style

- Match the existing plain-function, no-class style in `lib.js` and friends.
- Globals are attached deliberately (e.g. `window.AmazonTimeCost = ...`); don't introduce module systems.
- Keep DOM mutations idempotent — the `MutationObserver` will re-invoke render on every Amazon SPA update.
