function parsePrice(text) {
  if (!text) return null;
  const match = text.match(/[\d,]+\.?\d*/);
  if (!match) return null;
  const cleaned = match[0].replace(/,/g, '');
  const value = parseFloat(cleaned);
  if (isNaN(value) || value <= 0) return null;
  return value;
}

function priceToHours(price, hourlyWage) {
  if (!hourlyWage || hourlyWage <= 0) return null;
  if (price == null || price < 0) return null;
  return price / hourlyWage;
}

function formatTime(hours) {
  if (hours == null || hours < 0) return '';
  const totalMinutes = Math.round(hours * 60);
  if (totalMinutes < 1) return '<1m';
  const h = Math.floor(totalMinutes / 60);
  const m = totalMinutes % 60;
  if (h === 0) return `${m}m`;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

function parsePriceToCents(text) {
  const dollars = parsePrice(text);
  return dollars == null ? null : Math.round(dollars * 100);
}
