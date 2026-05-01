const tcSettings = (function () {
  const DEFAULTS = {
    enabled: true,
    hourlyWage: null,
    hidePrices: false,

    taxRate: 0.25,
    monthlyFixedExpenses: null,
    annualLeisureHours: null,

    framingPrimary: 'pre-tax-hours',
    framingSecondary: null,

    showOpportunityCost: false,
    investmentReturnRate: 0.07,

    showPerUseAmortization: false,
    perCategoryUses: null,

    showSubscriptionAnnualizer: true,
    showCartAggregation: true,

    donationLinkUrl: '',
  };

  let cache = null;
  let migrationDone = false;
  const listeners = [];
  let listenerInstalled = false;

  function syncStore() {
    return chrome.storage && chrome.storage.sync ? chrome.storage.sync : chrome.storage.local;
  }

  function localStore() {
    return chrome.storage.local;
  }

  function readKeys(store, keys) {
    return new Promise((resolve) => store.get(keys, (v) => resolve(v || {})));
  }

  function writeKeys(store, values) {
    return new Promise((resolve) => store.set(values, resolve));
  }

  async function migrateFromLocalIfNeeded() {
    if (migrationDone) return;
    migrationDone = true;
    const sync = syncStore();
    if (sync === localStore()) return;
    const keys = Object.keys(DEFAULTS);
    const fromSync = await readKeys(sync, keys);
    const syncIsEmpty = keys.every((k) => fromSync[k] === undefined);
    if (!syncIsEmpty) return;
    const fromLocal = await readKeys(localStore(), keys);
    const localHasSomething = keys.some((k) => fromLocal[k] !== undefined);
    if (localHasSomething) {
      await writeKeys(sync, fromLocal);
    }
  }

  async function getAll() {
    if (cache) return cache;
    await migrateFromLocalIfNeeded();
    const stored = await readKeys(syncStore(), Object.keys(DEFAULTS));
    cache = Object.assign({}, DEFAULTS);
    for (const k in stored) {
      if (stored[k] !== undefined) cache[k] = stored[k];
    }
    installChangeListener();
    return cache;
  }

  async function get(key) {
    const all = await getAll();
    return all[key];
  }

  function setMany(values) {
    return new Promise((resolve) => {
      syncStore().set(values, () => {
        if (cache) Object.assign(cache, values);
        resolve();
      });
    });
  }

  function set(key, value) {
    return setMany({ [key]: value });
  }

  function installChangeListener() {
    if (listenerInstalled) return;
    listenerInstalled = true;
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area !== 'sync' && area !== 'local') return;
      const reduced = {};
      for (const k in changes) {
        if (DEFAULTS[k] === undefined && k !== 'hourlyWage') continue;
        reduced[k] = changes[k].newValue;
        if (cache) cache[k] = changes[k].newValue;
      }
      if (Object.keys(reduced).length > 0) {
        listeners.forEach((cb) => {
          try { cb(reduced); } catch (e) { console.warn('[Amazon Time Cost] settings listener error', e); }
        });
      }
    });
  }

  function subscribe(callback) {
    listeners.push(callback);
    installChangeListener();
  }

  return { DEFAULTS, getAll, get, set, setMany, subscribe };
})();
