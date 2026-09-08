// Session view tracker. Records distinct ASINs the user has viewed within a
// rolling 4-hour window. Purely local (chrome.storage.local), no telemetry.
// The count is exposed via the popup as a mirror of browsing activity.

const P2TSession = {
  STORAGE_KEY: 'p2t_session_views',
  SESSION_TIMEOUT_MS: 4 * 60 * 60 * 1000, // 4 hours

  extractAsin() {
    const urlMatch = window.location.pathname.match(/\/(?:dp|gp\/product|product|gp\/aw\/d)\/([A-Z0-9]{10})/i);
    if (urlMatch) return urlMatch[1].toUpperCase();
    const el = document.querySelector('[data-asin]:not([data-asin=""])');
    if (el) return el.getAttribute('data-asin').toUpperCase();
    return null;
  },

  async recordView(asin) {
    if (!asin) return;
    return new Promise((resolve) => {
      chrome.storage.local.get({ [this.STORAGE_KEY]: {} }, (result) => {
        const views = result[this.STORAGE_KEY] || {};
        const now = Date.now();

        // Purge entries older than the session window
        Object.keys(views).forEach((k) => {
          if (now - views[k].lastSeen > this.SESSION_TIMEOUT_MS) delete views[k];
        });

        if (views[asin]) {
          views[asin].lastSeen = now;
          views[asin].viewCount = (views[asin].viewCount || 1) + 1;
        } else {
          views[asin] = { firstSeen: now, lastSeen: now, viewCount: 1 };
        }

        chrome.storage.local.set({ [this.STORAGE_KEY]: views }, resolve);
      });
    });
  },

  async getSessionStats() {
    return new Promise((resolve) => {
      chrome.storage.local.get({ [this.STORAGE_KEY]: {} }, (result) => {
        const views = result[this.STORAGE_KEY] || {};
        const now = Date.now();
        const active = Object.entries(views).filter(([, v]) => now - v.lastSeen < this.SESSION_TIMEOUT_MS);
        if (active.length === 0) {
          resolve({ count: 0, firstSeen: null, totalViews: 0 });
          return;
        }
        const firstSeen = Math.min(...active.map(([, v]) => v.firstSeen));
        const totalViews = active.reduce((sum, [, v]) => sum + (v.viewCount || 1), 0);
        resolve({ count: active.length, firstSeen, totalViews });
      });
    });
  },

  async trackCurrentPage() {
    const asin = this.extractAsin();
    if (asin) await this.recordView(asin);
  },

  async reset() {
    return new Promise((resolve) => {
      chrome.storage.local.remove(this.STORAGE_KEY, resolve);
    });
  },
};
