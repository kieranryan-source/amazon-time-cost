// Cart aggregation. Shows a prominent time + investment summary on cart/checkout pages.

const P2TCart = {
  CART_TOTAL_SELECTORS: [
    '#sc-subtotal-amount-buybox .a-price',
    '#sc-subtotal-amount-activecart .a-price',
    '#sc-subtotal-amount-buybox',
    '#sc-subtotal-amount-activecart',
    '.grand-total-price',
  ],
  SUMMARY_ID: 'p2t-cart-summary',

  isCartPage() {
    return /\/(gp\/cart|cart|checkout|gp\/buy)/.test(window.location.pathname);
  },

  render(settings) {
    if (!settings.showCartTotal || !this.isCartPage()) return;

    for (const selector of this.CART_TOTAL_SELECTORS) {
      let el;
      try { el = document.querySelector(selector); }
      catch { continue; }
      if (!el) continue;

      const parsed = P2TDetector.parsePriceText(el.textContent);
      if (parsed) {
        this.insertSummary(el, parsed.amountInCents, parsed.symbol, settings);
        return;
      }
    }
    console.warn('[Price to Time] Cart total not found on cart page. Amazon DOM may have changed.');
  },

  insertSummary(nearElement, totalCents, symbol, settings) {
    const existing = document.getElementById(this.SUMMARY_ID);
    if (existing) existing.remove();

    symbol = symbol || '$';
    const summary = document.createElement('div');
    summary.id = this.SUMMARY_ID;
    summary.className = 'p2t-cart-summary';

    const hours = P2TFramings.priceToHours(totalCents, settings, settings.primaryFraming);
    const timeText = P2TFramings.formatTime(hours, settings.primaryFraming);

    const timeLine = document.createElement('div');
    timeLine.className = 'p2t-cart-line-primary';
    timeLine.textContent = `${timeText} of your life`;
    summary.appendChild(timeLine);

    if (settings.showInvestment && settings.investmentYears.length > 0) {
      const years = settings.investmentYears[settings.investmentYears.length - 1];
      const future = P2TFramings.investmentGrowth(totalCents, settings.investmentRate, years);
      const gain = future - totalCents / 100;
      const invLine = document.createElement('div');
      invLine.className = 'p2t-cart-line-secondary';
      invLine.textContent = `Or ${P2TFramings.formatCurrency(future, symbol)} in ${years}yr if invested at ${(settings.investmentRate * 100).toFixed(0)}% (gain of ${symbol}${gain.toFixed(2)})`;
      summary.appendChild(invLine);
    }

    const refUnit = P2TFramings.getActiveReferenceUnit(settings);
    if (refUnit) {
      const count = P2TFramings.priceToReferenceUnits(totalCents, refUnit);
      if (count != null) {
        const refLine = document.createElement('div');
        refLine.className = 'p2t-cart-line-secondary';
        refLine.textContent = `Same as ${P2TFramings.formatReferenceUnit(count, refUnit)}`;
        summary.appendChild(refLine);
      }
    }

    const container = nearElement.closest('#sc-subtotal-block, .sc-subtotal, #activeCartViewForm') || nearElement.parentElement;
    if (container) container.appendChild(summary);
  },
};
