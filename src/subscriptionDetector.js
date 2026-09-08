// Subscription annualizer. Detects recurring pricing patterns and shows the annualized cost.

const P2TSubscription = {
  PERIOD_TO_ANNUAL: {
    day: 365, days: 365,
    week: 52, wk: 52, weeks: 52,
    month: 12, mo: 12, mos: 12, months: 12,
    year: 1, yr: 1, years: 1,
  },

  OVERLAY_CLASS: 'p2t-sub-overlay',

  detect(root = document) {
    const results = [];
    const seen = new WeakSet();

    // Look at any text node that mentions a price followed by a period
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        if (!node.textContent) return NodeFilter.FILTER_SKIP;
        return /\$[\d.,]+\s*\/\s*(day|week|wk|month|mo|year|yr)/i.test(node.textContent)
          ? NodeFilter.FILTER_ACCEPT
          : NodeFilter.FILTER_SKIP;
      },
    });

    let node;
    while ((node = walker.nextNode())) {
      const parent = node.parentElement;
      if (!parent || seen.has(parent)) continue;
      if (parent.classList.contains(this.OVERLAY_CLASS)) continue;

      const match = node.textContent.match(/\$([\d,]+(?:\.\d{1,2})?)\s*\/\s*(day|week|wk|month|mo|mos|year|yr|days|weeks|months|years)/i);
      if (!match) continue;

      const numeric = parseFloat(match[1].replace(/,/g, ''));
      if (isNaN(numeric) || numeric <= 0) continue;

      const period = match[2].toLowerCase();
      const multiplier = this.PERIOD_TO_ANNUAL[period] || 12;

      seen.add(parent);

      // Claim any .a-price elements inside this subscription context so the
      // regular price detector won't double-annotate them.
      parent.querySelectorAll('.a-price').forEach((p) => p.classList.add('p2t-processed'));

      results.push({
        element: parent,
        amountInCents: Math.round(numeric * 100),
        period,
        annualCents: Math.round(numeric * 100 * multiplier),
      });
    }

    return results;
  },

  render(subInfo, settings) {
    if (!settings.showSubscriptionAnnual) return;
    const { element, annualCents } = subInfo;

    // Skip if already annotated
    if (element.querySelector(`.${this.OVERLAY_CLASS}`)) return;
    if (element.nextElementSibling && element.nextElementSibling.classList && element.nextElementSibling.classList.contains(this.OVERLAY_CLASS)) return;

    const annualHours = P2TFramings.priceToHours(annualCents, settings, settings.primaryFraming);
    const timeText = P2TFramings.formatTime(annualHours, settings.primaryFraming);
    const annualDollars = (annualCents / 100).toFixed(2);

    const overlay = document.createElement('span');
    overlay.className = this.OVERLAY_CLASS;
    overlay.textContent = ` (= $${annualDollars}/yr, ${timeText}/yr)`;

    element.insertAdjacentElement('afterend', overlay);
  },

  clearAll() {
    document.querySelectorAll(`.${this.OVERLAY_CLASS}`).forEach((el) => el.remove());
  },
};
