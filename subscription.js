const tcSubscription = (function () {
  const YEAR_MULT = {
    month: 12,
    week: 52,
  };

  const SNS_SELECTOR = '#snsAccordionRowMiddle, [data-feature-name="snsActionPanel"], #sns-base-price, #snsAccordionRow, #snsCard';

  function detectFrequencyFromText(text) {
    if (!text) return null;
    if (/\/\s*(month|mo|monthly)\b/i.test(text)) return 'month';
    if (/per\s+month\b/i.test(text)) return 'month';
    if (/\/\s*(week|wk|weekly)\b/i.test(text)) return 'week';
    if (/per\s+week\b/i.test(text)) return 'week';
    return null;
  }

  function detectFrequencyFromElement(el) {
    if (!el) return null;
    try {
      if (el.closest && el.closest(SNS_SELECTOR)) return 'month';
      const parent = el.parentElement;
      if (!parent) return null;
      return detectFrequencyFromText(parent.textContent || '');
    } catch (e) {
      return null;
    }
  }

  return {
    YEAR_MULT,
    detectFrequencyFromText,
    detectFrequencyFromElement,
  };
})();
