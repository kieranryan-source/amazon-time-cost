# Amazon Time Cost

Chrome extension that shows Amazon prices as hours of your life, the investment growth foregone, and personalized reference units. Zero telemetry, all local.

## Why

Money is abstract. Hours of your life are not. A $200 pair of headphones is 4 hours of pretax work at $50/hr, or $784 in 30 years if invested at 7%, or the same as ~1.3 weeks of groceries. Reframing prices in units that mean something to you grounds purchasing decisions in resources that actually matter.

## What it does

**Every price on Amazon** gets a small block below it with:
- Time equivalent: pre-tax hours, take-home hours, discretionary hours, or leisure days
- Investment growth: what the money becomes at your chosen rate and time horizons
- Reference unit: `= ~2 gym memberships` or `= 1/3 of a week of groceries`

**Cart / checkout pages** show a prominent running total in the same three framings.

**Wishlist and save-for-later pages** show an aggregate summary at the top - what your wishlist is *actually* worth in hours of your life. Plus a "Tracked N days" marker on each item so old wishlist items self-surface as stale.

**Subscribe & Save pricing** ($X/month, $X/week) gets an annualized equivalent shown next to it.

**Order pages** highlight the return-window deadline as a color-coded badge (`5 days left to return`) so it doesn't get buried in Amazon's UI.

**Popup toolbar** shows a session view counter - how many distinct products you've looked at in the last few hours - with a gentle nudge at higher counts.

**Keyboard shortcut**: Alt + Shift + P to toggle the overlay on and off.

## Marketplaces supported

16 Amazon domains: `.com`, `.ca`, `.co.uk`, `.de`, `.fr`, `.it`, `.es`, `.co.jp`, `.com.mx`, `.com.au`, `.in`, `.com.br`, `.nl`, `.se`, `.pl`, `.sg`.

Auto-detects `$`, `£`, `€`, `¥`, `₹`, `R$` and handles both US-style (`$1,234.56`) and EU-style (`1.234,56 €`) number formats. Your wage is applied in whatever currency the current marketplace uses.

## Privacy

Local-only. No telemetry. No analytics. No external network calls. All state lives in `chrome.storage.sync` (settings) and `chrome.storage.local` (session views, wishlist age markers).

## Install (unpacked)

1. Open `chrome://extensions`
2. Turn on Developer mode (top right)
3. Click "Load unpacked" and pick this folder
4. Right-click the toolbar icon and choose Options to configure your wage, tax rate, reference units, and investment assumptions

## Configuration

The options page has six sections:
1. Your earning (wage, tax rate, monthly fixed expenses, work hours per year)
2. Time framing (which of pre-tax / take-home / discretionary / leisure to display)
3. Investment alternative (rate, real vs nominal, up to three time horizons)
4. Reference units (name and cost of things meaningful to you)
5. Marketplace and currency (informational; auto-detected)
6. Where it appears (toggles for cart summary, wishlist, subscriptions, keyboard)

A live "Your rates, right now" panel at the top of settings updates as you type, so you can see immediately what a $100 purchase costs in your current setup.

## File layout

```
amazon-time-cost/
  manifest.json                     Manifest V3, 16 marketplace host_permissions
  src/
    settings.js                     Defaults, chrome.storage.sync layer
    framings.js                     Pure math (time, investment, reference units)
    priceDetector.js                Multi-currency price finding
    renderer.js                     Overlay HTML with version marker
    cartAggregator.js               Cart-page summary block
    subscriptionDetector.js         /month, /week annualization
    wishlistAggregator.js           Wishlist + save-for-later totals
    wishlistAge.js                  Per-item "tracked N ago" markers
    sessionTracker.js               Rolling 4-hour view counter
    returnWindow.js                 Return-deadline surfacing on order pages
    content.js                      Orchestrator, MutationObserver, keyboard toggle
    overlay.css                     All content-script styles
  options/                          Full settings page
  popup/                            Toolbar popup
  icons/                            16 / 48 / 128 png icons
```

## Not included (deliberate)

- No Amazon affiliate links (conflict of interest with the extension's purpose)
- No behavioral friction modals (out of scope; possibly a future opt-in mode)
- No cross-site support beyond Amazon
- No price history, coupon automation, or AI purchase recommendations
- No telemetry, analytics, or external network calls of any kind

## Support

If you find this useful, there is a Buy Me a Coffee link in the settings footer. Currently a placeholder - update `options/options.html` before publishing to point at your own donation URL.

## Version

2.0.0 - Major restructure. Manifest V3. No external dependencies.
