// Wishlist age markers. Timestamps each wishlist item the first time we see
// it, then displays "Tracked N ago" alongside the item on subsequent visits.
// The number is honest: it's how long WE've been tracking it, not the actual
// wishlist add date (which Amazon doesn't expose to extensions).

const P2TWishlistAge = {
  STORAGE_KEY: 'p2t_wishlist_seen',
  MARKER_CLASS: 'p2t-wishlist-age',

  // Selectors used to find individual items on the wishlist page
  ITEM_SELECTORS: [
    '[data-itemid]',
    '[data-reposition-action-target]',
    '.g-item-sortable',
  ],

  async annotateItems() {
    if (!this.isWishlistPage()) return;

    return new Promise((resolve) => {
      chrome.storage.local.get({ [this.STORAGE_KEY]: {} }, (result) => {
        const seen = result[this.STORAGE_KEY] || {};
        const now = Date.now();
        let changed = false;

        const items = this.findItems();
        items.forEach((item) => {
          const key = this.itemKey(item);
          if (!key) return;

          if (!seen[key]) {
            seen[key] = now;
            changed = true;
          }
          this.addMarker(item, seen[key], now);
        });

        if (changed) {
          chrome.storage.local.set({ [this.STORAGE_KEY]: seen }, resolve);
        } else {
          resolve();
        }
      });
    });
  },

  isWishlistPage() {
    return /\/(hz\/wishlist|wishlist|gp\/registry\/wishlist)/.test(window.location.pathname);
  },

  findItems() {
    const items = [];
    const seen = new WeakSet();
    for (const sel of this.ITEM_SELECTORS) {
      try {
        document.querySelectorAll(sel).forEach((el) => {
          if (!seen.has(el)) { seen.add(el); items.push(el); }
        });
      } catch { /* ignore bad selector */ }
    }
    return items;
  },

  itemKey(item) {
    return item.getAttribute('data-itemid')
        || item.getAttribute('data-asin')
        || item.querySelector('[data-asin]')?.getAttribute('data-asin')
        || null;
  },

  addMarker(item, firstSeen, now) {
    if (item.querySelector(`.${this.MARKER_CLASS}`)) return;

    const ageMs = now - firstSeen;
    const days = Math.floor(ageMs / (24 * 60 * 60 * 1000));

    let text;
    if (days === 0) text = 'Tracked since today';
    else if (days === 1) text = 'Tracked 1 day';
    else if (days < 30) text = `Tracked ${days} days`;
    else if (days < 365) {
      const months = Math.round(days / 30);
      text = months === 1 ? 'Tracked 1 month' : `Tracked ${months} months`;
    } else {
      const years = (days / 365).toFixed(1);
      text = `Tracked ${years} years`;
    }

    const marker = document.createElement('div');
    marker.className = this.MARKER_CLASS;
    marker.textContent = text;
    // Older items get a subtle color shift as a visual cue
    if (days >= 90) marker.classList.add('p2t-wishlist-age-old');
    if (days >= 180) marker.classList.add('p2t-wishlist-age-stale');

    // Try to place near the title area of the item; fall back to append
    const anchor = item.querySelector('h2, h3, .a-link-normal, [class*="title"]');
    if (anchor && anchor.parentElement) {
      anchor.parentElement.insertBefore(marker, anchor.nextSibling);
    } else {
      item.insertBefore(marker, item.firstChild);
    }
  },
};
