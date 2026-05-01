const tcFraming = (function () {
  const MONTHLY_HOURS = 173;

  const LABELS = {
    'pre-tax-hours': 'pre-tax work',
    'take-home-hours': 'take-home work',
    'discretionary-hours': 'discretionary work',
    'leisure-days': 'leisure days',
  };

  function discretionaryHourly(settings) {
    if (!settings.hourlyWage || settings.hourlyWage <= 0) return null;
    if (settings.monthlyFixedExpenses == null) return null;
    const taxRate = settings.taxRate || 0;
    const takeHomeHourly = settings.hourlyWage * (1 - taxRate);
    if (takeHomeHourly <= 0) return null;
    const discMonthly = takeHomeHourly * MONTHLY_HOURS - settings.monthlyFixedExpenses;
    if (discMonthly <= 0) return null;
    return discMonthly / MONTHLY_HOURS;
  }

  function computeFraming(priceDollars, framing, settings) {
    if (priceDollars == null || priceDollars < 0) return null;
    if (!settings.hourlyWage || settings.hourlyWage <= 0) return null;
    if (!framing) return null;

    const taxRate = settings.taxRate || 0;
    const takeHomeHourly = settings.hourlyWage * (1 - taxRate);

    switch (framing) {
      case 'pre-tax-hours':
        return { type: 'hours', value: priceDollars / settings.hourlyWage };

      case 'take-home-hours':
        if (takeHomeHourly <= 0) return null;
        return { type: 'hours', value: priceDollars / takeHomeHourly };

      case 'discretionary-hours': {
        const dh = discretionaryHourly(settings);
        if (dh == null) return null;
        return { type: 'hours', value: priceDollars / dh };
      }

      case 'leisure-days': {
        if (!settings.annualLeisureHours || settings.annualLeisureHours <= 0) return null;
        const dh = discretionaryHourly(settings);
        if (dh == null) return null;
        const dailyLeisure = settings.annualLeisureHours / 365;
        if (dailyLeisure <= 0) return null;
        return { type: 'days', value: (priceDollars / dh) / dailyLeisure };
      }

      default:
        return null;
    }
  }

  function formatFramingResult(result) {
    if (!result) return '';
    if (result.type === 'days') {
      const d = result.value;
      if (d < 1) return formatTime(d * 24);
      if (d >= 100) return `${Math.round(d)}d`;
      return `${d.toFixed(1)}d`;
    }
    return formatTime(result.value);
  }

  function framingLabel(framing) {
    return LABELS[framing] || '';
  }

  function computeOpportunityCost(priceDollars, rate, years) {
    if (priceDollars == null || priceDollars <= 0) return null;
    if (rate == null || rate < 0) return null;
    if (years == null || years <= 0) return null;
    return priceDollars * Math.pow(1 + rate, years);
  }

  function formatDollars(amount) {
    if (amount == null) return '';
    if (amount >= 1000000) return '$' + (amount / 1000000).toFixed(1) + 'M';
    if (amount >= 10000) return '$' + Math.round(amount / 1000) + 'k';
    if (amount >= 1000) return '$' + (amount / 1000).toFixed(1) + 'k';
    return '$' + Math.round(amount);
  }

  function buildBadgePayload(priceDollars, settings) {
    const primaryRes = computeFraming(priceDollars, settings.framingPrimary, settings);
    if (!primaryRes) return null;
    let primaryText = formatFramingResult(primaryRes);
    if (!primaryText) return null;

    const ocEnabled = !!settings.showOpportunityCost && settings.investmentReturnRate != null;
    if (ocEnabled) {
      const fv30 = computeOpportunityCost(priceDollars, settings.investmentReturnRate, 30);
      if (fv30 != null) {
        primaryText += ` · ${formatDollars(fv30)} in 30y`;
      }
    }

    const secondaryParts = [];

    if (settings.framingSecondary && settings.framingSecondary !== settings.framingPrimary) {
      const secRes = computeFraming(priceDollars, settings.framingSecondary, settings);
      if (secRes) {
        const secText = formatFramingResult(secRes);
        if (secText) {
          secondaryParts.push(`${secText} (${framingLabel(settings.framingSecondary)})`);
        }
      }
    }

    if (ocEnabled) {
      const fv10 = computeOpportunityCost(priceDollars, settings.investmentReturnRate, 10);
      const fv30 = computeOpportunityCost(priceDollars, settings.investmentReturnRate, 30);
      if (fv10 != null && fv30 != null) {
        const ratePct = (settings.investmentReturnRate * 100).toFixed(1);
        secondaryParts.push(`${formatDollars(fv10)} in 10y · ${formatDollars(fv30)} in 30y at ${ratePct}%`);
      }
    }

    const secondary = secondaryParts.length > 0 ? secondaryParts.join('\n') : null;
    return secondary ? { primary: primaryText, secondary } : primaryText;
  }

  return {
    MONTHLY_HOURS,
    discretionaryHourly,
    computeFraming,
    formatFramingResult,
    framingLabel,
    computeOpportunityCost,
    formatDollars,
    buildBadgePayload,
  };
})();
