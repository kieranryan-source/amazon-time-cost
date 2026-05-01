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

  function buildBadgePayload(priceDollars, settings) {
    const primaryRes = computeFraming(priceDollars, settings.framingPrimary, settings);
    if (!primaryRes) return null;
    const primaryText = formatFramingResult(primaryRes);
    if (!primaryText) return null;

    let secondary = null;
    if (settings.framingSecondary && settings.framingSecondary !== settings.framingPrimary) {
      const secRes = computeFraming(priceDollars, settings.framingSecondary, settings);
      if (secRes) {
        const secText = formatFramingResult(secRes);
        if (secText) {
          secondary = `${secText} (${framingLabel(settings.framingSecondary)})`;
        }
      }
    }

    return secondary ? { primary: primaryText, secondary } : primaryText;
  }

  return {
    MONTHLY_HOURS,
    discretionaryHourly,
    computeFraming,
    formatFramingResult,
    framingLabel,
    buildBadgePayload,
  };
})();
