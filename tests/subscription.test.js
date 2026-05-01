// Run with:
//   jsc subscription.js tests/subscription.test.js

let passed = 0;
let failed = 0;

function eq(actual, expected, label) {
  if (actual === expected) {
    passed++;
    print('  ok   ' + label);
  } else {
    failed++;
    print('  FAIL ' + label + '  expected=' + expected + '  got=' + actual);
  }
}

print('detectFrequencyFromText');
eq(tcSubscription.detectFrequencyFromText('$12.99 /month'), 'month', 'slash-month');
eq(tcSubscription.detectFrequencyFromText('$12.99/mo'), 'month', 'slash-mo');
eq(tcSubscription.detectFrequencyFromText('$12.99 / Month'), 'month', 'capitalized Month');
eq(tcSubscription.detectFrequencyFromText('$12.99 per month'), 'month', 'per month');
eq(tcSubscription.detectFrequencyFromText('$2.49/week'), 'week', 'slash-week');
eq(tcSubscription.detectFrequencyFromText('$2.49 per week'), 'week', 'per week');
eq(tcSubscription.detectFrequencyFromText('$2.49 weekly'), null, 'bare weekly does not trigger');
eq(tcSubscription.detectFrequencyFromText('$49.99 one-time purchase'), null, 'one-time returns null');
eq(tcSubscription.detectFrequencyFromText(''), null, 'empty returns null');
eq(tcSubscription.detectFrequencyFromText(null), null, 'null returns null');
eq(tcSubscription.detectFrequencyFromText('Buy 12 months supply for $99'), null, 'months supply does not false-positive');

print('YEAR_MULT');
eq(tcSubscription.YEAR_MULT.month, 12, 'month is x12');
eq(tcSubscription.YEAR_MULT.week, 52, 'week is x52');

print('detectFrequencyFromElement (no DOM)');
eq(tcSubscription.detectFrequencyFromElement(null), null, 'null element returns null');
eq(tcSubscription.detectFrequencyFromElement({}), null, 'element without parent returns null');

const mockEl = {
  closest: function () { return null; },
  parentElement: { textContent: 'Subscribe & Save $12.99/month' },
};
eq(tcSubscription.detectFrequencyFromElement(mockEl), 'month', 'parent text drives detection');

const mockSnsEl = {
  closest: function (sel) { return sel.indexOf('snsAccordionRow') !== -1 ? {} : null; },
  parentElement: { textContent: '$12.99' },
};
eq(tcSubscription.detectFrequencyFromElement(mockSnsEl), 'month', 'SnS container implies monthly');

print('');
print(passed + ' passed, ' + failed + ' failed');
if (failed > 0) throw new Error('tests failed');
