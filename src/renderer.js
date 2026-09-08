// Renderer module. Overlay is a block below the price with up to three lines:
//   line 1: time framing (always)
//   line 2: investment growth (optional)
//   line 3: reference unit (optional, e.g. "~2 gym memberships")

const P2TRenderer = {
  OVERLAY_CLASS: 'p2t-overlay',
  PROCESSED_CLASS: 'p2t-processed',
  ID_ATTR: 'data-p2t-id',
  MARKER_ATTR: 'data-p2t-v',
  CURRENT_VERSION: '3',  // bump when overlay structure changes

  render(priceInfo, settings) {
    const { element, amountInCents, symbol } = priceInfo;
    if (!element || !element.parentElement) return;

    const id = this.elementId(element);
    const stale = document.querySelector(`.${this.OVERLAY_CLASS}[data-p2t-for="${id}"]`);
    if (stale) stale.remove();

    const overlay = this.buildOverlay(amountInCents, settings, symbol);
    if (!overlay) return;

    overlay.setAttribute('data-p2t-for', id);
    overlay.setAttribute(this.MARKER_ATTR, this.CURRENT_VERSION);
    element.classList.add(this.PROCESSED_CLASS);
    element.insertAdjacentElement('afterend', overlay);
  },

  elementId(element) {
    if (!element.getAttribute(this.ID_ATTR)) {
      element.setAttribute(this.ID_ATTR, `p2t-${Math.random().toString(36).substr(2, 9)}`);
    }
    return element.getAttribute(this.ID_ATTR);
  },

  buildOverlay(amountInCents, settings, symbol) {
    symbol = symbol || '$';
    const overlay = document.createElement('div');
    overlay.className = this.OVERLAY_CLASS;

    // Line 1: time
    const primaryHours = P2TFramings.priceToHours(amountInCents, settings, settings.primaryFraming);
    const timeText = P2TFramings.formatTime(primaryHours, settings.primaryFraming);
    const timeLine = document.createElement('div');
    timeLine.className = 'p2t-time-line';
    timeLine.textContent = timeText;
    overlay.appendChild(timeLine);

    // Line 2: investment
    if (settings.showInvestment && settings.investmentYears && settings.investmentYears.length > 0) {
      const rate = settings.investmentRate;
      const values = settings.investmentYears.map((years) => {
        const future = P2TFramings.investmentGrowth(amountInCents, rate, years);
        return P2TFramings.formatCurrency(future, symbol);
      });
      const yearsStr = settings.investmentYears.join('/');

      const investLine = document.createElement('div');
      investLine.className = 'p2t-invest-line';
      investLine.appendChild(document.createTextNode('or '));
      const valSpan = document.createElement('span');
      valSpan.className = 'p2t-invest-value';
      valSpan.textContent = values.join(' / ');
      investLine.appendChild(valSpan);
      investLine.appendChild(document.createTextNode(` in ${yearsStr}yr`));
      overlay.appendChild(investLine);
    }

    // Line 3: reference unit
    const refUnit = P2TFramings.getActiveReferenceUnit(settings);
    if (refUnit) {
      const count = P2TFramings.priceToReferenceUnits(amountInCents, refUnit);
      if (count != null) {
        const refLine = document.createElement('div');
        refLine.className = 'p2t-ref-line';
        refLine.textContent = `= ${P2TFramings.formatReferenceUnit(count, refUnit)}`;
        overlay.appendChild(refLine);
      }
    }

    overlay.setAttribute('title', this.buildTooltip(amountInCents, settings, symbol));
    return overlay;
  },

  buildTooltip(amountInCents, settings, symbol) {
    const lines = [];
    const price = (amountInCents / 100).toFixed(2);
    lines.push(`Price: ${symbol}${price}`);
    lines.push('');

    const primaryRate = P2TFramings.effectiveHourlyRate(settings, settings.primaryFraming);
    const primaryHours = P2TFramings.priceToHours(amountInCents, settings, settings.primaryFraming);
    lines.push(`${P2TFramings.framingLabel(settings.primaryFraming)}: ${P2TFramings.formatTime(primaryHours, settings.primaryFraming)}`);
    lines.push(`  at ${symbol}${primaryRate.toFixed(2)}/hr`);

    if (settings.secondaryFraming && settings.secondaryFraming !== 'none' && settings.secondaryFraming !== settings.primaryFraming) {
      const secHours = P2TFramings.priceToHours(amountInCents, settings, settings.secondaryFraming);
      lines.push('');
      lines.push(`Also: ${P2TFramings.formatTime(secHours, settings.secondaryFraming)}`);
      lines.push(`  (${P2TFramings.framingLabel(settings.secondaryFraming)})`);
    }

    if (settings.showInvestment && settings.investmentYears.length > 0) {
      lines.push('');
      const retTypeLabel = settings.returnType === 'nominal' ? 'nominal' : 'real / inflation-adjusted';
      lines.push(`Invested instead at ${(settings.investmentRate * 100).toFixed(1)}% (${retTypeLabel}):`);
      settings.investmentYears.forEach((years) => {
        const future = P2TFramings.investmentGrowth(amountInCents, settings.investmentRate, years);
        const gain = future - amountInCents / 100;
        lines.push(`  ${years}yr: ${symbol}${future.toFixed(2)} (+${symbol}${gain.toFixed(2)})`);
      });
      if (settings.investmentRate > settings.investmentRateWarnThreshold) {
        lines.push('');
        lines.push(`Note: ${(settings.investmentRate * 100).toFixed(1)}% is optimistic historically.`);
      }
    }

    return lines.join('\n');
  },

  cleanOrphans() {
    document.querySelectorAll(`.${this.OVERLAY_CLASS}`).forEach((overlay) => {
      const forId = overlay.getAttribute('data-p2t-for');
      if (!forId) { overlay.remove(); return; }
      const target = document.querySelector(`[${this.ID_ATTR}="${forId}"]`);
      if (!target || !document.body.contains(target)) overlay.remove();
    });
  },

  // Remove any overlay that doesn't match the current version's structure.
  // Uses a version marker attribute so upgrades don't leave visual duplicates.
  removeStaleFormatOverlays() {
    document.querySelectorAll(`.${this.OVERLAY_CLASS}`).forEach((overlay) => {
      const ver = overlay.getAttribute(this.MARKER_ATTR);
      if (ver !== this.CURRENT_VERSION) {
        const forId = overlay.getAttribute('data-p2t-for');
        if (forId) {
          const target = document.querySelector(`[${this.ID_ATTR}="${forId}"]`);
          if (target) target.classList.remove(this.PROCESSED_CLASS);
        }
        overlay.remove();
      }
    });
  },

  clearAll() {
    document.querySelectorAll(`.${this.OVERLAY_CLASS}`).forEach((el) => el.remove());
    document.querySelectorAll(`.${this.PROCESSED_CLASS}`).forEach((el) => el.classList.remove(this.PROCESSED_CLASS));
    document.querySelectorAll(`[${this.ID_ATTR}]`).forEach((el) => el.removeAttribute(this.ID_ATTR));
  },
};
