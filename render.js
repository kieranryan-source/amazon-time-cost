const tcRender = (function () {
  const PROCESSED_ATTR = 'data-tc-processed';
  const BADGE_CLASS = 'tc-time-badge';
  const HIDE_BODY_CLASS = 'tc-hide-prices';

  function appendBadge(priceEl, payload) {
    if (!priceEl || priceEl.hasAttribute(PROCESSED_ATTR)) return;

    let primary = '';
    let secondary = null;

    if (typeof payload === 'string') {
      primary = payload;
    } else if (payload && typeof payload === 'object') {
      primary = payload.primary || '';
      secondary = payload.secondary || null;
    }

    if (!primary) return;

    const badge = document.createElement('span');
    badge.className = BADGE_CLASS;
    badge.textContent = primary;
    if (secondary) badge.title = secondary;

    priceEl.appendChild(badge);
    priceEl.setAttribute(PROCESSED_ATTR, '1');
  }

  function clearBadges(root) {
    const scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll('[' + PROCESSED_ATTR + ']').forEach((el) => {
      el.removeAttribute(PROCESSED_ATTR);
      el.querySelectorAll('.' + BADGE_CLASS).forEach((b) => b.remove());
    });
  }

  function applyHidePrices(hide) {
    if (document.body) {
      document.body.classList.toggle(HIDE_BODY_CLASS, !!hide);
    }
  }

  return { appendBadge, clearBadges, applyHidePrices };
})();
