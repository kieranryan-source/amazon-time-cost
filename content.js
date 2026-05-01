let cachedSettings = null;
let observer = null;

function appendPerUse(payload, suffix) {
  if (typeof payload === 'string') return payload + suffix;
  return { primary: payload.primary + suffix, secondary: payload.secondary };
}

function computePayload(price) {
  if (!cachedSettings) return null;
  const dollars = price.amountInCents / 100;
  const payload = tcFraming.buildBadgePayload(dollars, cachedSettings);
  if (!payload) return null;

  if (price.context === 'buy-box' && cachedSettings.showPerUseAmortization) {
    const am = tcAmortization.detectPageUses(cachedSettings);
    if (am && am.uses > 0) {
      const perUse = dollars / am.uses;
      const formatted = tcAmortization.formatPerUse(perUse);
      if (formatted) return appendPerUse(payload, ` · ~${formatted}/use`);
    }
  }

  return payload;
}

function annotate(root) {
  if (!cachedSettings || !cachedSettings.enabled || !cachedSettings.hourlyWage) return;
  const prices = tcFindPrices(root);
  prices.forEach((p) => {
    if (p.context === 'cart-total' && !cachedSettings.showCartAggregation) return;
    const payload = computePayload(p);
    if (payload) tcRender.appendBadge(p.element, payload);
  });
}

function startObserver() {
  if (observer || !document.body) return;
  observer = new MutationObserver((mutations) => {
    for (const m of mutations) {
      m.addedNodes.forEach((node) => {
        if (node.nodeType === Node.ELEMENT_NODE) {
          annotate(node);
        }
      });
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
}

function stopObserver() {
  if (observer) {
    observer.disconnect();
    observer = null;
  }
}

function render() {
  if (!cachedSettings) return;
  tcRender.applyHidePrices(cachedSettings.enabled && cachedSettings.hidePrices);
  if (cachedSettings.enabled && cachedSettings.hourlyWage) {
    annotate();
    startObserver();
  } else {
    tcRender.clearBadges();
    stopObserver();
  }
}

(async function init() {
  cachedSettings = await tcSettings.getAll();
  if (!cachedSettings.hourlyWage) {
    console.log('[Amazon Time Cost] No hourly wage set. Click the extension icon to set one.');
  }
  render();

  tcSettings.subscribe((changes) => {
    cachedSettings = Object.assign({}, cachedSettings, changes);
    tcRender.clearBadges();
    render();
  });
})();
