const tcAmortization = (function () {
  const DEFAULT_USES = {
    kitchen: 500,
    tools: 100,
    electronics: 1000,
    furniture: 3000,
    appliances: 3000,
  };

  const KEYWORDS = {
    kitchen: ['Kitchen & Dining', 'Cookware', 'Bakeware', 'Kitchen Utensils', 'Coffee, Tea & Espresso', 'Dining & Entertaining'],
    tools: ['Tools & Home Improvement', 'Power & Hand Tools', 'Power Tools', 'Hand Tools', 'Hardware'],
    electronics: ['Electronics', 'Computers & Accessories', 'Cell Phones & Accessories', 'Headphones', 'Camera & Photo', 'Wearable Technology', 'Video Games'],
    furniture: ['Furniture', 'Bedroom Furniture', 'Living Room Furniture', 'Office Furniture', 'Home Office Furniture'],
    appliances: ['Appliances', 'Large Appliances', 'Small Appliances'],
  };

  function detectCategoryFromText(text) {
    if (!text) return null;
    for (const cat in KEYWORDS) {
      const list = KEYWORDS[cat];
      for (let i = 0; i < list.length; i++) {
        if (text.indexOf(list[i]) !== -1) return cat;
      }
    }
    return null;
  }

  function detectCategoryFromDocument() {
    if (typeof document === 'undefined') return null;
    try {
      const el = document.querySelector('#wayfinding-breadcrumbs_feature_div');
      if (!el) return null;
      return detectCategoryFromText(el.textContent || '');
    } catch (e) {
      return null;
    }
  }

  function detectPageUses(settings) {
    if (!settings || !settings.showPerUseAmortization) return null;
    try {
      const category = detectCategoryFromDocument();
      if (!category) return null;
      const overrides = settings.perCategoryUses || {};
      const uses = overrides[category] != null ? overrides[category] : DEFAULT_USES[category];
      if (!uses || uses <= 0) return null;
      return { category, uses };
    } catch (e) {
      console.warn('[Amazon Time Cost] amortization detection failed', e);
      return null;
    }
  }

  function formatPerUse(amount) {
    if (amount == null || amount < 0) return '';
    if (amount < 0.01) return '<$0.01';
    if (amount < 1) return '$' + amount.toFixed(2);
    return '$' + Math.round(amount);
  }

  return {
    DEFAULT_USES,
    KEYWORDS,
    detectCategoryFromText,
    detectCategoryFromDocument,
    detectPageUses,
    formatPerUse,
  };
})();
