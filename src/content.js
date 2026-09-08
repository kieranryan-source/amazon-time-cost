// Main content script. Orchestrates detection/rendering, DOM observation,
// keyboard shortcut, and full clearing when toggled off.

(async function () {
  await P2TSettings.load();

  // Wipe any pre-existing overlays or processed markers from a prior extension version.
  P2TRenderer.clearAll();

  let renderTimeout = null;
  const RENDER_DEBOUNCE_MS = 150;

  function renderAll() {
    const settings = P2TSettings.get();
    if (!settings.enabled) {
      // If disabled, ensure the page is clean
      P2TRenderer.clearAll();
      const cs = document.getElementById(P2TCart.SUMMARY_ID);
      if (cs) cs.remove();
      const ws = document.getElementById(P2TWishlist.WISHLIST_SUMMARY_ID);
      if (ws) ws.remove();
      const sfl = document.getElementById(P2TWishlist.SFL_SUMMARY_ID);
      if (sfl) sfl.remove();
      P2TSubscription.clearAll();
      return;
    }

    const t0 = performance.now();

    // 0. Prune orphans and stale-format overlays first
    try {
      P2TRenderer.cleanOrphans();
      P2TRenderer.removeStaleFormatOverlays();
    } catch (err) { console.warn('[Price to Time] Cleanup error:', err); }

    // 1. Subscription pricing (claims contained .a-price so we don't double-annotate)
    try {
      const subs = P2TSubscription.detect();
      subs.forEach((sub) => P2TSubscription.render(sub, settings));
    } catch (err) { console.warn('[Price to Time] Subscription error:', err); }

    // 2. Standard prices
    try {
      const prices = P2TDetector.findPrices();
      prices.forEach((p) => {
        try { P2TRenderer.render(p, settings); }
        catch (err) { console.warn('[Price to Time] Render error:', err); }
      });
    } catch (err) { console.warn('[Price to Time] Detection error:', err); }

    // 3. Cart summary
    try { P2TCart.render(settings); }
    catch (err) { console.warn('[Price to Time] Cart error:', err); }

    // 4. Wishlist / save-for-later summary
    try { P2TWishlist.render(settings); }
    catch (err) { console.warn('[Price to Time] Wishlist error:', err); }

    // 5. Wishlist age markers (per-item "tracked N ago")
    try { P2TWishlistAge.annotateItems(); }
    catch (err) { console.warn('[Price to Time] Wishlist age error:', err); }

    // 6. Return-window awareness (on order pages)
    try { P2TReturns.render(); }
    catch (err) { console.warn('[Price to Time] Return window error:', err); }

    const elapsed = performance.now() - t0;
    if (elapsed > 200) console.warn(`[Price to Time] Render took ${elapsed.toFixed(0)}ms`);
  }

  function scheduleRender() {
    if (renderTimeout) clearTimeout(renderTimeout);
    renderTimeout = setTimeout(renderAll, RENDER_DEBOUNCE_MS);
  }

  // Track this page in the session counter (fires once at load)
  try { P2TSession.trackCurrentPage(); }
  catch (err) { console.warn('[Price to Time] Session tracker error:', err); }

  scheduleRender();

  // Observe DOM changes
  const observer = new MutationObserver((mutations) => {
    const hasAdditions = mutations.some((m) =>
      Array.from(m.addedNodes).some((n) => n.nodeType === 1)
    );
    if (hasAdditions) scheduleRender();
  });
  observer.observe(document.body, { childList: true, subtree: true });

  // Settings changes: wipe and re-render
  P2TSettings.onChanged(() => {
    P2TRenderer.clearAll();
    P2TSubscription.clearAll();
    ['p2t-cart-summary', P2TWishlist.WISHLIST_SUMMARY_ID, P2TWishlist.SFL_SUMMARY_ID].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.remove();
    });
    scheduleRender();
  });

  // Keyboard toggle. Default: Alt+Shift+P.
  // Uses capture phase to run before Amazon's own handlers.
  document.addEventListener('keydown', (e) => {
    const settings = P2TSettings.get();
    if (!settings.enableKeyboardToggle) return;
    // Match Alt+Shift+P (case-insensitive on the key)
    if (e.altKey && e.shiftKey && !e.ctrlKey && !e.metaKey && (e.key === 'P' || e.key === 'p')) {
      e.preventDefault();
      e.stopPropagation();
      const newVal = !settings.enabled;
      P2TSettings.set({ enabled: newVal });
      // Brief visual confirmation
      showFlashMessage(newVal ? 'Price to Time: ON' : 'Price to Time: OFF');
    }
  }, true);

  function showFlashMessage(text) {
    const existing = document.getElementById('p2t-flash');
    if (existing) existing.remove();
    const flash = document.createElement('div');
    flash.id = 'p2t-flash';
    flash.textContent = text;
    document.body.appendChild(flash);
    setTimeout(() => flash.classList.add('p2t-flash-fade'), 50);
    setTimeout(() => flash.remove(), 1600);
  }
})();
