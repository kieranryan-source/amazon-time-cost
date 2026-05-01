const tcFindPrices = (function () {
  const CART_TOTAL_SELECTOR = '#sc-subtotal-amount-activecart, #sc-subtotal-amount-buybox, [data-feature-id="proceed-to-checkout-action"]';
  const CART_SELECTOR = '[id*="sc-active-cart"], #activeCartViewForm, [data-name="Cart"], .sc-list-item';
  const LIST_SELECTOR = '[data-component-type="s-search-result"]';
  const BUY_BOX_SELECTOR = '#corePriceDisplay_desktop_feature_div, #ppd, #buybox, #addToCart_feature_div';

  function detectContext(el) {
    try {
      if (el.closest && el.closest(CART_TOTAL_SELECTOR)) return 'cart-total';
      if (el.closest && el.closest(CART_SELECTOR)) return 'cart';
      if (el.closest && el.closest(LIST_SELECTOR)) return 'list';
      if (el.closest && el.closest(BUY_BOX_SELECTOR)) return 'buy-box';
      return 'product';
    } catch (e) {
      return 'unknown';
    }
  }

  function findPrices(root) {
    const scope = root && root.querySelectorAll ? root : (typeof document !== 'undefined' ? document : null);
    if (!scope) return [];
    const out = [];
    const els = scope.querySelectorAll('.a-price');
    els.forEach((el) => {
      const offscreen = el.querySelector ? el.querySelector('.a-offscreen') : null;
      if (!offscreen) return;
      const cents = parsePriceToCents(offscreen.textContent);
      if (cents == null) return;
      out.push({
        element: el,
        amountInCents: cents,
        currency: 'USD',
        context: detectContext(el),
      });
    });
    return out;
  }

  return findPrices;
})();
