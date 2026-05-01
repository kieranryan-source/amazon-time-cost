let cachedSettings = null;
let observer = null;

function appendSuffix(payload, suffix) {
  if (typeof payload === 'string') return payload + suffix;
  return { primary: payload.primary + suffix, secondary: payload.secondary };
}

function maybeAppendPerUse(payload, price, dollars) {
  if (price.context !== 'buy-box') return payload;
  if (!cachedSettings.showPerUseAmortization) return payload;
  const am = tcAmortization.detectPageUses(cachedSettings);
  if (!am || am.uses <= 0) return payload;
  const perUse = dollars / am.uses;
  const formatted = tcAmortization.formatPerUse(perUse);
  if (!formatted) return payload;
  return appendSuffix(payload, ` · ~${formatted}/use`);
}

function maybeAppendAnnualized(payload, price, dollars) {
  if (!cachedSettings.showSubscriptionAnnualizer) return payload;
  const freq = tcSubscription.detectFrequencyFromElement(price.element);
  if (!freq) return payload;
  const multiplier = tcSubscription.YEAR_MULT[freq];
  if (!multiplier) return payload;
  const annualDollars = dollars * multiplier;
  const annualResult = tcFraming.computeFraming(annualDollars, cachedSettings.framingPrimary, cachedSettings);
  const annualText = tcFraming.formatFramingResult(annualResult);
  if (!annualText) return payload;
  return appendSuffix(payload, ` · ${annualText}/yr`);
}

function computePayload(price) {
  if (!cachedSettings) return null;
  const dollars = price.amountInCents / 100;
  let payload = tcFraming.buildBadgePayload(dollars, cachedSettings);
  if (!payload) return null;
  payload = maybeAppendPerUse(payload, price, dollars);
  payload = maybeAppendAnnualized(payload, price, dollars);
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
