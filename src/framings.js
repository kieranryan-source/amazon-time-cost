// Framings module. Pure functions for time, investment, and reference-unit math.
// Also owns currency parsing/formatting helpers used by the detector and renderer.

const P2TFramings = {
  effectiveHourlyRate(settings, framing) {
    const wage = Number(settings.hourlyWage) || 0;
    const tax = Number(settings.taxRate) || 0;
    const fixed = Number(settings.monthlyFixedExpenses) || 0;
    const yearHours = Number(settings.workHoursPerYear) || 2000;

    switch (framing) {
      case 'pretax': return wage;
      case 'posttax': return wage * (1 - tax);
      case 'discretionary':
      case 'leisure': {
        const posttax = wage * (1 - tax);
        const monthlyIncome = posttax * (yearHours / 12);
        if (fixed >= monthlyIncome) return 0.01;
        const discretionaryMonthly = monthlyIncome - fixed;
        return discretionaryMonthly / (yearHours / 12);
      }
      default: return wage;
    }
  },

  priceToHours(priceCents, settings, framing) {
    const rate = this.effectiveHourlyRate(settings, framing);
    if (!isFinite(rate) || rate <= 0) return Infinity;
    return (priceCents / 100) / rate;
  },

  formatTime(hours, framing) {
    if (!isFinite(hours)) return 'unaffordable';

    if (framing === 'leisure') {
      const days = hours / 16;
      if (days < 1 / 24) return `${Math.round(hours * 60)} min leisure`;
      if (days < 1) return `${hours.toFixed(1)} hr leisure`;
      return `${days.toFixed(1)} days leisure`;
    }

    if (hours < 1 / 60) return `${Math.round(hours * 3600)} sec`;
    if (hours < 1) return `${Math.round(hours * 60)} min`;
    if (hours < 8) return `${hours.toFixed(1)} hr`;
    const days = hours / 8;
    if (days < 20) return `${days.toFixed(1)} workdays`;
    const months = days / 20;
    if (months < 12) return `${months.toFixed(1)} work months`;
    const years = months / 12;
    return `${years.toFixed(1)} work years`;
  },

  investmentGrowth(priceCents, rate, years) {
    return (priceCents / 100) * Math.pow(1 + rate, years);
  },

  formatCurrency(amount, symbol) {
    symbol = symbol || '$';
    if (!isFinite(amount)) return '-';
    if (amount >= 1000000) return `${symbol}${(amount / 1000000).toFixed(1)}M`;
    if (amount >= 10000) return `${symbol}${(amount / 1000).toFixed(1)}k`;
    if (amount >= 100) return `${symbol}${Math.round(amount).toLocaleString()}`;
    return `${symbol}${amount.toFixed(2)}`;
  },

  framingLabel(framing) {
    return {
      pretax: 'work hours (pre-tax)',
      posttax: 'work hours (take-home)',
      discretionary: 'discretionary hours',
      leisure: 'leisure equivalent',
    }[framing] || 'work hours';
  },

  // Reference-unit math ("this costs the same as 2 gym memberships")
  priceToReferenceUnits(priceCents, refUnit) {
    if (!refUnit || !refUnit.cost || refUnit.cost <= 0) return null;
    return (priceCents / 100) / refUnit.cost;
  },

  formatReferenceUnit(count, refUnit) {
    if (count == null || !refUnit) return '';
    const name = refUnit.name;

    if (count < 0.05) {
      // Very small fraction: show as percentage
      return `${(count * 100).toFixed(1)}% of a ${name}`;
    }
    if (count < 0.5) {
      // Show as simple fraction of the unit
      const denom = Math.round(1 / count);
      return `~1/${denom} of a ${name}`;
    }
    if (count < 1.5) {
      // Around one unit
      if (count > 0.9 && count < 1.1) return `~1 ${name}`;
      return `${count.toFixed(1)} ${name}s`;
    }
    if (count < 10) return `${count.toFixed(1)} ${name}s`;
    return `${Math.round(count)} ${name}s`;
  },

  getActiveReferenceUnit(settings) {
    if (!settings.showReferenceUnit) return null;
    if (!Array.isArray(settings.referenceUnits) || settings.referenceUnits.length === 0) return null;
    const active = settings.referenceUnits.find((u) => u.id === settings.activeReferenceUnitId);
    return active || settings.referenceUnits[0];
  },
};
