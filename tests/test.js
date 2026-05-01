// Run with: jsc lib.js tests/test.js
// (jsc is at /System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc on macOS)

let passed = 0;
let failed = 0;

function eq(actual, expected, label) {
  const ok = actual === expected;
  if (ok) {
    passed++;
    print('  ok   ' + label);
  } else {
    failed++;
    print('  FAIL ' + label + '  expected=' + expected + '  got=' + actual);
  }
}

print('parsePrice');
eq(parsePrice('$49.99'), 49.99, 'simple price');
eq(parsePrice('$1,299.00'), 1299, 'price with comma');
eq(parsePrice('  $12.50  '), 12.5, 'whitespace');
eq(parsePrice('$10.00 - $20.00'), 10, 'price range takes lower bound');
eq(parsePrice('Free'), null, 'non-numeric returns null');
eq(parsePrice(''), null, 'empty returns null');
eq(parsePrice(null), null, 'null returns null');

print('priceToHours');
eq(priceToHours(50, 25), 2, 'basic division');
eq(priceToHours(100, 20), 5, 'whole hours');
eq(priceToHours(50, 0), null, 'zero wage returns null');
eq(priceToHours(50, null), null, 'null wage returns null');

print('parsePriceToCents');
eq(parsePriceToCents('$49.99'), 4999, 'simple price in cents');
eq(parsePriceToCents('$1,299.00'), 129900, 'comma-separated in cents');
eq(parsePriceToCents('  $12.50  '), 1250, 'whitespace');
eq(parsePriceToCents('Free'), null, 'non-numeric returns null');
eq(parsePriceToCents(''), null, 'empty returns null');

print('formatTime');
eq(formatTime(2.5), '2h 30m', 'hours and minutes');
eq(formatTime(3), '3h', 'whole hours only');
eq(formatTime(0.5), '30m', 'minutes only');
eq(formatTime(0.005), '<1m', 'very small');
eq(formatTime(120), '120h', 'many hours');
eq(formatTime(0), '<1m', 'zero hours');
eq(formatTime(null), '', 'null returns empty string');

print('');
print(passed + ' passed, ' + failed + ' failed');
if (failed > 0) {
  throw new Error('tests failed');
}
