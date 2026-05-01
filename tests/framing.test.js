// Run with:
//   jsc lib.js framing.js tests/framing.test.js

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

function near(actual, expected, tol, label) {
  if (Math.abs(actual - expected) <= tol) {
    passed++;
    print('  ok   ' + label);
  } else {
    failed++;
    print('  FAIL ' + label + '  expected~=' + expected + '  got=' + actual);
  }
}

const baseSettings = {
  hourlyWage: 25,
  taxRate: 0.25,
  monthlyFixedExpenses: 2000,
  annualLeisureHours: 1500,
  framingPrimary: 'pre-tax-hours',
  framingSecondary: null,
};

print('computeFraming pre-tax-hours');
eq(tcFraming.computeFraming(50, 'pre-tax-hours', baseSettings).value, 2, '$50 / $25 = 2 hours');
eq(tcFraming.computeFraming(0, 'pre-tax-hours', baseSettings).value, 0, '$0 = 0 hours');
eq(tcFraming.computeFraming(100, 'pre-tax-hours', { hourlyWage: null }), null, 'no wage = null');

print('computeFraming take-home-hours');
near(tcFraming.computeFraming(50, 'take-home-hours', baseSettings).value, 2.6667, 0.001, '$50 / $18.75 ~= 2.67h');

print('computeFraming discretionary-hours');
const disc = tcFraming.computeFraming(200, 'discretionary-hours', baseSettings);
near(disc.value, 27.82, 0.05, '$200 / discretionary hourly ~= 27.82h');
eq(tcFraming.computeFraming(200, 'discretionary-hours', { ...baseSettings, monthlyFixedExpenses: null }), null, 'missing expenses = null');
eq(tcFraming.computeFraming(200, 'discretionary-hours', { ...baseSettings, monthlyFixedExpenses: 100000 }), null, 'expenses exceed income = null');

print('computeFraming leisure-days');
const leis = tcFraming.computeFraming(200, 'leisure-days', baseSettings);
near(leis.value, 6.77, 0.05, '$200 leisure days ~= 6.77');
eq(tcFraming.computeFraming(200, 'leisure-days', { ...baseSettings, annualLeisureHours: null }), null, 'missing leisure hours = null');
eq(tcFraming.computeFraming(200, 'leisure-days', { ...baseSettings, monthlyFixedExpenses: null }), null, 'leisure also needs expenses');

print('formatFramingResult');
eq(tcFraming.formatFramingResult({ type: 'hours', value: 2 }), '2h', 'plain hours');
eq(tcFraming.formatFramingResult({ type: 'hours', value: 2.5 }), '2h 30m', 'mixed hours/min');
eq(tcFraming.formatFramingResult({ type: 'days', value: 6.77 }), '6.8d', 'days with one decimal');
eq(tcFraming.formatFramingResult({ type: 'days', value: 0.5 }), '12h', 'sub-day shows hours');
eq(tcFraming.formatFramingResult({ type: 'days', value: 150 }), '150d', '100+ days rounded');
eq(tcFraming.formatFramingResult(null), '', 'null = empty');

print('buildBadgePayload');
const p1 = tcFraming.buildBadgePayload(50, baseSettings);
eq(p1, '2h', 'primary-only returns string');
const p2 = tcFraming.buildBadgePayload(50, { ...baseSettings, framingSecondary: 'take-home-hours' });
eq(p2.primary, '2h', 'with secondary, primary key set');
eq(typeof p2.secondary, 'string', 'with secondary, secondary key set');
eq(p2.secondary.indexOf('take-home') >= 0, true, 'secondary includes label');
const p3 = tcFraming.buildBadgePayload(50, { ...baseSettings, framingSecondary: 'pre-tax-hours' });
eq(p3, '2h', 'secondary same as primary collapses to string');
const p4 = tcFraming.buildBadgePayload(50, { hourlyWage: null, framingPrimary: 'pre-tax-hours' });
eq(p4, null, 'no wage = null payload');
const p5 = tcFraming.buildBadgePayload(200, { ...baseSettings, framingPrimary: 'discretionary-hours', framingSecondary: 'pre-tax-hours' });
eq(p5.primary.indexOf('h') >= 0, true, 'discretionary primary renders hours');
eq(p5.secondary.indexOf('pre-tax') >= 0, true, 'pre-tax secondary label correct');

print('');
print(passed + ' passed, ' + failed + ' failed');
if (failed > 0) throw new Error('tests failed');
