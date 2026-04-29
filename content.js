const PROCESSED_ATTR = 'data-tc-processed';
const BADGE_CLASS = 'tc-time-badge';
const HIDE_BODY_CLASS = 'tc-hide-prices';

let hourlyWage = null;
let observer = null;

function annotatePrices(root) {
  if (!hourlyWage || hourlyWage <= 0) return;
  const scope = root && root.querySelectorAll ? root : document;
  const priceEls = scope.querySelectorAll('.a-price:not([' + PROCESSED_ATTR + '])');
  priceEls.forEach((el) => {
    const offscreen = el.querySelector('.a-offscreen');
    if (!offscreen) return;
    const price = parsePrice(offscreen.textContent);
    if (price == null) return;
    const hours = priceToHours(price, hourlyWage);
    const formatted = formatTime(hours);
    if (!formatted) return;

    const badge = document.createElement('span');
    badge.className = BADGE_CLASS;
    badge.textContent = formatted;
    el.appendChild(badge);
    el.setAttribute(PROCESSED_ATTR, '1');
  });
}

function clearAnnotations() {
  document.querySelectorAll('[' + PROCESSED_ATTR + ']').forEach((el) => {
    el.removeAttribute(PROCESSED_ATTR);
    el.querySelectorAll('.' + BADGE_CLASS).forEach((b) => b.remove());
  });
}

function startObserver() {
  if (observer) return;
  observer = new MutationObserver((mutations) => {
    for (const m of mutations) {
      m.addedNodes.forEach((node) => {
        if (node.nodeType === Node.ELEMENT_NODE) {
          annotatePrices(node);
        }
      });
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
}

function applyHidePrices(hide) {
  document.body.classList.toggle(HIDE_BODY_CLASS, !!hide);
}

function init() {
  chrome.storage.local.get(['hourlyWage', 'hidePrices'], (result) => {
    hourlyWage = result.hourlyWage || null;
    applyHidePrices(result.hidePrices);
    if (!hourlyWage) {
      console.log('[Amazon Time Cost] No hourly wage set. Click the extension icon to set one.');
      return;
    }
    annotatePrices();
    startObserver();
  });

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== 'local') return;
    if (changes.hidePrices) {
      applyHidePrices(changes.hidePrices.newValue);
    }
    if (changes.hourlyWage) {
      hourlyWage = changes.hourlyWage.newValue || null;
      clearAnnotations();
      if (hourlyWage) {
        annotatePrices();
        startObserver();
      }
    }
  });
}

init();
