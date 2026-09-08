// Wishlist and save-for-later aggregation. Detects wishlist pages and the
// save-for-later section of the cart, sums the visible item prices, and shows
// a prominent summary at the top of the container.

const P2TWishlist = {
  WISHLIST_SUMMARY_ID: 'p2t-wishlist-summary',
  SFL_SUMMARY_ID: 'p2t-sfl-summary',

  // Insertion anchors on wishlist page - first match wins.
  WISHLIST_ANCHOR_SELECTORS: [
    '#profile-list-name',
    '#list-page-header',
    '#wishlist-page',
    '.g-item-sortable',    // fallback: before the first item row
  ],

  // Save-for-later section on the cart page
  SFL_SECTION_SELECTORS: [
    '#sc-saved-cart',
    '.sc-saved-cart',
    '[data-name="save-for-later"]',
  ],

  isWishlistPage() {
    return /\/(hz\/wishlist|wishlist|gp\/registry\/wishlist)/.test(window.location.pathname);
  },

  isCartPage() {
    return /\/(gp\/cart|cart)/.test(window.location.pathname);
  },

  render(settings) {
    if (!settings.showWishlistTotal) return;

    if (this.isWishlistPage()) {
      this.renderWishlist(settings);
    }
    if (this.isCartPage()) {
      this.renderSaveForLater(settings);
    }
  },

  renderWishlist(settings) {
    const prices = P2TDetector.findPrices();
    if (prices.length === 0) return;

    // Sum by currency (usually all one currency, but be safe)
    const byCurrency = this.sumByCurrency(prices);
    const primary = this.dominantCurrency(byCurrency);
    if (!primary) return;

    const anchor = this.findAnchor(this.WISHLIST_ANCHOR_SELECTORS);
    if (!anchor) return;

    this.insertSummary(
      this.WISHLIST_SUMMARY_ID,
      anchor,
      'insertBefore',
      `Wishlist total (${prices.length} items)`,
      primary.totalCents,
      primary.symbol,
      settings
    );
  },

  renderSaveForLater(settings) {
    const section = this.findFirst(this.SFL_SECTION_SELECTORS);
    if (!section) return;

    const prices = P2TDetector.findPrices(section);
    if (prices.length === 0) return;

    const byCurrency = this.sumByCurrency(prices);
    const primary = this.dominantCurrency(byCurrency);
    if (!primary) return;

    this.insertSummary(
      this.SFL_SUMMARY_ID,
      section,
      'prepend',
      `Save-for-later total (${prices.length} items)`,
      primary.totalCents,
      primary.symbol,
      settings
    );
  },

  sumByCurrency(prices) {
    const byCurrency = {};
    prices.forEach((p) => {
      const key = p.symbol || '$';
      if (!byCurrency[key]) byCurrency[key] = { totalCents: 0, count: 0, symbol: key };
      byCurrency[key].totalCents += p.amountInCents;
      byCurrency[key].count += 1;
    });
    return byCurrency;
  },

  dominantCurrency(byCurrency) {
    let best = null;
    Object.values(byCurrency).forEach((v) => {
      if (!best || v.count > best.count) best = v;
    });
    return best;
  },

  findFirst(selectors) {
    for (const sel of selectors) {
      try {
        const el = document.querySelector(sel);
        if (el) return el;
      } catch { /* skip bad selector */ }
    }
    return null;
  },

  findAnchor(selectors) {
    return this.findFirst(selectors) || document.body;
  },

  insertSummary(id, anchor, placement, title, totalCents, symbol, settings) {
    const existing = document.getElementById(id);
    if (existing) existing.remove();

    const summary = document.createElement('div');
    summary.id = id;
    summary.className = 'p2t-wishlist-summary';

    const header = document.createElement('div');
    header.className = 'p2t-wishlist-title';
    header.textContent = title;
    summary.appendChild(header);

    const priceLine = document.createElement('div');
    priceLine.className = 'p2t-wishlist-price';
    priceLine.textContent = `${symbol}${(totalCents / 100).toFixed(2)}`;
    summary.appendChild(priceLine);

    const hours = P2TFramings.priceToHours(totalCents, settings, settings.primaryFraming);
    const timeText = P2TFramings.formatTime(hours, settings.primaryFraming);
    const timeLine = document.createElement('div');
    timeLine.className = 'p2t-wishlist-time';
    timeLine.textContent = `${timeText} of your life`;
    summary.appendChild(timeLine);

    if (settings.showInvestment && settings.investmentYears.length > 0) {
      const years = settings.investmentYears[settings.investmentYears.length - 1];
      const future = P2TFramings.investmentGrowth(totalCents, settings.investmentRate, years);
      const invLine = document.createElement('div');
      invLine.className = 'p2t-wishlist-invest';
      invLine.textContent = `Or ${P2TFramings.formatCurrency(future, symbol)} in ${years}yr if invested`;
      summary.appendChild(invLine);
    }

    const refUnit = P2TFramings.getActiveReferenceUnit(settings);
    if (refUnit) {
      const count = P2TFramings.priceToReferenceUnits(totalCents, refUnit);
      if (count != null) {
        const refLine = document.createElement('div');
        refLine.className = 'p2t-wishlist-ref';
        refLine.textContent = `Same as ${P2TFramings.formatReferenceUnit(count, refUnit)}`;
        summary.appendChild(refLine);
      }
    }

    if (placement === 'insertBefore') {
      anchor.parentNode.insertBefore(summary, anchor);
    } else if (placement === 'prepend') {
      anchor.insertBefore(summary, anchor.firstChild);
    } else {
      anchor.appendChild(summary);
    }
  },
};
