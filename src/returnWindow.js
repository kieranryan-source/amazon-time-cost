// Return window awareness. On order pages, surfaces the return deadline
// prominently. Amazon shows this info but often buries it; we just re-emphasize.

const P2TReturns = {
  // Text patterns like "Return window closes Sep 30, 2025" or "Return by 09/30/2025".
  DATE_PATTERNS: [
    /return\s+(?:window\s+closes?\s+(?:on\s+)?|by\s+|through\s+|eligible\s+through\s+)([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})/gi,
    /return\s+(?:window\s+closes?\s+(?:on\s+)?|by\s+|through\s+)(\d{1,2}\/\d{1,2}\/\d{2,4})/gi,
    /returnable\s+(?:until|through|by)\s+([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})/gi,
  ],

  BADGE_CLASS: 'p2t-return-badge',

  isOrderPage() {
    const p = window.location.pathname;
    return /\/(gp\/your-account\/order|gp\/css\/order-history|your-orders|orders|gp\/legacy-order)/.test(p);
  },

  render() {
    if (!this.isOrderPage()) return;

    // Walk text nodes looking for return-window language
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        if (!node.textContent) return NodeFilter.FILTER_SKIP;
        return /return/i.test(node.textContent) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
      },
    });

    const annotated = new WeakSet();
    let node;
    while ((node = walker.nextNode())) {
      const text = node.textContent;
      const parent = node.parentElement;
      if (!parent || annotated.has(parent)) continue;

      let match = null;
      for (const pattern of this.DATE_PATTERNS) {
        pattern.lastIndex = 0;
        match = pattern.exec(text);
        if (match) break;
      }
      if (!match) continue;

      const returnDate = new Date(match[1]);
      if (isNaN(returnDate.getTime())) continue;

      annotated.add(parent);
      this.annotate(this.findAnchor(parent), returnDate);
    }
  },

  // Walk up to find a sensible container (order card) to attach the badge to
  findAnchor(el) {
    let cur = el;
    for (let i = 0; i < 6 && cur && cur.parentElement; i++) {
      const tag = cur.tagName.toLowerCase();
      const cls = cur.className || '';
      if (typeof cls === 'string' && /order-card|shipment|order-info|a-box/i.test(cls)) return cur;
      if (tag === 'article' || tag === 'section') return cur;
      cur = cur.parentElement;
    }
    return el;
  },

  annotate(container, returnDate) {
    if (!container || container.querySelector(`.${this.BADGE_CLASS}`)) return;

    const now = new Date();
    const msLeft = returnDate.getTime() - now.getTime();
    const daysLeft = Math.ceil(msLeft / (24 * 60 * 60 * 1000));

    // Skip if already past
    if (daysLeft < 0) return;

    const badge = document.createElement('div');
    badge.className = this.BADGE_CLASS;
    if (daysLeft <= 3) badge.classList.add('p2t-return-urgent');
    else if (daysLeft <= 7) badge.classList.add('p2t-return-soon');

    let text;
    if (daysLeft === 0) text = 'Return window closes today';
    else if (daysLeft === 1) text = '1 day left to return';
    else text = `${daysLeft} days left to return`;

    badge.textContent = text;
    badge.setAttribute('title', `Return by ${returnDate.toLocaleDateString()}`);

    container.appendChild(badge);
  },
};
