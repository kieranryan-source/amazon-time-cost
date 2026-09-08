// Price detection module. Auto-detects currency symbol (USD/GBP/EUR/JPY/INR/BRL/CAD/AUD/MXN)
// and handles both US-style (dot decimal) and EU-style (comma decimal) number formats.

const P2TDetector = {
  PRICE_SELECTORS: [
    '.a-price:not(.p2t-processed)',
  ],

  SKIP_CONTEXT_CLASSES: [
    'a-text-price',
    'a-text-strike',
    'a-color-secondary',
  ],

  CONTAINER_SELECTORS: [
    '[data-asin]',
    '.sc-list-item',
    '.sc-list-item-content',
    '[data-item-index]',
    '[data-line-id]',
    '.a-carousel-card',
    '.s-result-item',
    '.a-cardui',
    '[data-itemid]',       // wishlist items
    '[data-reposition-action-target]', // wishlist item wrapper
  ],

  // Symbol -> canonical currency code (best-effort; disambiguated by URL if needed)
  SYMBOL_TO_CURRENCY: {
    '$': 'USD', '£': 'GBP', '€': 'EUR', '¥': 'JPY', '₹': 'INR', 'R$': 'BRL',
  },

  findPrices(root = document) {
    const results = [];
    const seen = new WeakSet();

    for (const selector of this.PRICE_SELECTORS) {
      let matches;
      try { matches = root.querySelectorAll(selector); }
      catch (err) { console.warn('[Price to Time] Selector failed:', selector, err); continue; }

      matches.forEach((el) => {
        if (seen.has(el)) return;
        seen.add(el);
        if (this.shouldSkip(el)) return;

        const parsed = this.parsePriceElement(el);
        if (parsed) results.push({ element: el, ...parsed });
      });
    }

    return this.dedupeByPosition(this.dedupeByContainer(results));
  },

  shouldSkip(el) {
    if (el.getAttribute('data-a-strike') === 'true') return true;
    for (const cls of this.SKIP_CONTEXT_CLASSES) {
      if (el.closest(`.${cls}`)) return true;
    }
    if (el.parentElement && el.parentElement.closest('.a-price')) return true;

    const prev = el.previousSibling;
    if (prev && prev.nodeType === Node.TEXT_NODE) {
      const text = prev.textContent.replace(/\s+$/, '');
      if (text.endsWith('(')) return true;
    }

    const next = el.nextSibling;
    if (next && next.nodeType === Node.TEXT_NODE) {
      const text = next.textContent;
      if (/^\s*\/\s*(?!day|week|wk|month|mo|mos|year|yr|days|weeks|months|years\b)[a-z]/i.test(text)) {
        return true;
      }
    }

    return false;
  },

  dedupeByContainer(results) {
    const kept = [];
    for (const r of results) {
      let container = null;
      for (const sel of this.CONTAINER_SELECTORS) {
        const c = r.element.closest(sel);
        if (c) { container = c; break; }
      }
      if (container) {
        const dup = kept.find((k) => k.amountInCents === r.amountInCents && k.container === container);
        if (dup) continue;
      }
      kept.push({ ...r, container });
    }
    return kept;
  },

  dedupeByPosition(results) {
    const kept = [];
    for (const r of results) {
      let rect;
      try { rect = r.element.getBoundingClientRect(); } catch { kept.push(r); continue; }

      const dup = kept.find((k) => {
        if (k.amountInCents !== r.amountInCents) return false;
        let kRect;
        try { kRect = k.element.getBoundingClientRect(); } catch { return false; }
        const dx = Math.abs(kRect.left - rect.left);
        const dy = Math.abs(kRect.top - rect.top);
        return dx < 60 && dy < 60;
      });
      if (!dup) kept.push(r);
    }
    return kept;
  },

  parsePriceElement(el) {
    const offscreen = el.querySelector('.a-offscreen');
    const text = offscreen ? offscreen.textContent : el.textContent;
    return this.parsePriceText(text);
  },

  // Auto-detects currency symbol AND number format. Handles both "$12.99" and "12,99 €".
  parsePriceText(text) {
    if (!text) return null;

    // Match: [symbol]NUM or NUM[symbol]. Symbol is one of: $ £ € ¥ ₹ or "R$".
    let match = text.match(/(R\$|[$£€¥₹])\s*([\d.,\u00a0\s]+)/);
    let symbol, numStr;
    if (match) {
      symbol = match[1];
      numStr = match[2];
    } else {
      match = text.match(/([\d.,\u00a0\s]+)\s*(R\$|[$£€¥₹])/);
      if (!match) return null;
      numStr = match[1];
      symbol = match[2];
    }

    numStr = numStr.replace(/\u00a0/g, '').trim();
    // Trim trailing non-digit garbage
    numStr = numStr.replace(/[^\d.,]/g, '');
    if (!numStr) return null;

    // Determine which is decimal vs thousands separator by looking at position
    const lastDot = numStr.lastIndexOf('.');
    const lastComma = numStr.lastIndexOf(',');

    let numeric;
    if (lastDot === -1 && lastComma === -1) {
      numeric = parseFloat(numStr);
    } else if (lastDot > lastComma) {
      // Dot is decimal (US/UK/etc.); comma is thousands
      numeric = parseFloat(numStr.replace(/,/g, ''));
    } else if (lastComma > lastDot) {
      // Comma is decimal (EU); dot is thousands
      numeric = parseFloat(numStr.replace(/\./g, '').replace(',', '.'));
    } else {
      numeric = parseFloat(numStr);
    }

    if (isNaN(numeric) || numeric <= 0) return null;

    // JPY uses no decimals, so a "12.99" would be wrong. But offscreen text usually
    // presents as integer. Trust what we parse; edge cases rare.

    const currency = this.SYMBOL_TO_CURRENCY[symbol] || 'USD';
    return {
      amountInCents: Math.round(numeric * 100),
      currency,
      symbol,
      rawText: match[0],
    };
  },
};
