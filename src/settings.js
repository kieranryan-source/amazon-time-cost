// Settings module. Holds defaults, loads from chrome.storage.sync, exposes cached access.

const P2T_DEFAULT_SETTINGS = {
  // Earning
  hourlyWage: 50,
  taxRate: 0.34,
  monthlyFixedExpenses: 200,
  workHoursPerYear: 2000,

  // Time framing display
  primaryFraming: 'pretax',
  secondaryFraming: 'none',

  // Investment
  showInvestment: true,
  investmentRate: 0.07,
  investmentYears: [5, 10, 20],
  returnType: 'real',
  investmentRateWarnThreshold: 0.20,

  // Reference-unit framing: user-defined units (e.g. "gym membership" = $35).
  // referenceUnits: [{id, name, cost}]
  referenceUnits: [
    { id: 'ref1', name: 'week of groceries', cost: 150 },
  ],
  activeReferenceUnitId: 'ref1',
  showReferenceUnit: true,

  // Where the overlay appears
  showCartTotal: true,
  showAmortization: false,
  showSubscriptionAnnual: true,
  showWishlistTotal: true,

  // Keyboard toggle
  enableKeyboardToggle: true,

  // Master switch
  enabled: true,
};

const P2TSettings = {
  cache: null,

  async load() {
    return new Promise((resolve) => {
      chrome.storage.sync.get(P2T_DEFAULT_SETTINGS, (items) => {
        // Sanitize
        if (!Array.isArray(items.investmentYears) || items.investmentYears.length === 0) {
          items.investmentYears = P2T_DEFAULT_SETTINGS.investmentYears;
        }
        items.investmentYears = items.investmentYears
          .map((y) => parseInt(y, 10))
          .filter((y) => y >= 1 && y <= 50)
          .slice(0, 3);
        if (items.investmentYears.length === 0) items.investmentYears = [20];

        if (!Array.isArray(items.referenceUnits)) items.referenceUnits = [];
        items.referenceUnits = items.referenceUnits
          .filter((u) => u && typeof u.name === 'string' && u.name.trim() && Number(u.cost) > 0)
          .map((u) => ({
            id: u.id || `ref_${Math.random().toString(36).substr(2, 6)}`,
            name: String(u.name).trim(),
            cost: Number(u.cost),
          }))
          .slice(0, 6);

        this.cache = items;
        resolve(items);
      });
    });
  },

  get() { return this.cache || P2T_DEFAULT_SETTINGS; },

  async set(updates) {
    return new Promise((resolve) => {
      chrome.storage.sync.set(updates, () => {
        this.cache = { ...this.cache, ...updates };
        resolve();
      });
    });
  },

  onChanged(callback) {
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area !== 'sync') return;
      Object.keys(changes).forEach((key) => {
        if (this.cache) this.cache[key] = changes[key].newValue;
      });
      callback(changes);
    });
  },
};
