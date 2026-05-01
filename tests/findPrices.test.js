// Run with:
//   jsc lib.js findPrices.js tests/findPrices.test.js

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

function mockPriceEl(opts) {
  return {
    querySelector: function (sel) {
      if (sel === '.a-offscreen') {
        return opts.offscreen != null ? { textContent: opts.offscreen } : null;
      }
      return null;
    },
    closest: function (sel) {
      if (!opts.context) return null;
      if (opts.context === 'cart-total' && (sel.indexOf('sc-subtotal') !== -1 || sel.indexOf('proceed-to-checkout') !== -1)) return {};
      if (opts.context === 'cart' && (sel.indexOf('sc-active-cart') !== -1 || sel.indexOf('activeCartViewForm') !== -1 || sel.indexOf('sc-list-item') !== -1)) return {};
      if (opts.context === 'list' && sel.indexOf('s-search-result') !== -1) return {};
      if (opts.context === 'buy-box' && (sel.indexOf('#buybox') !== -1 || sel.indexOf('corePriceDisplay') !== -1 || sel.indexOf('#ppd') !== -1)) return {};
      return null;
    },
    hasAttribute: function () { return false; },
    setAttribute: function () {},
    appendChild: function () {},
  };
}

function mockRoot(prices) {
  const els = prices.map(mockPriceEl);
  return {
    querySelectorAll: function (sel) {
      if (sel === '.a-price') return els;
      return [];
    },
  };
}

print('findPrices');

const r1 = tcFindPrices(mockRoot([
  { offscreen: '$49.99' },
  { offscreen: '$1,299.00' },
  { offscreen: 'Free' },
  { offscreen: '' },
]));
eq(r1.length, 2, 'finds two valid prices, skips non-numeric and empty');
eq(r1[0].amountInCents, 4999, '$49.99 -> 4999 cents');
eq(r1[1].amountInCents, 129900, '$1,299.00 -> 129900 cents');
eq(r1[0].currency, 'USD', 'currency is USD');

const r2 = tcFindPrices(mockRoot([
  { offscreen: '$10.00', context: 'cart' },
  { offscreen: '$20.00', context: 'list' },
  { offscreen: '$30.00', context: 'buy-box' },
  { offscreen: '$40.00' },
]));
eq(r2.length, 4, 'returns all valid prices');
eq(r2[0].context, 'cart', 'cart context detected');
eq(r2[1].context, 'list', 'list context detected');
eq(r2[2].context, 'buy-box', 'buy-box context detected');
eq(r2[3].context, 'product', 'no closest match -> product default');

const r2b = tcFindPrices(mockRoot([
  { offscreen: '$45.00', context: 'cart-total' },
]));
eq(r2b[0].context, 'cart-total', 'cart subtotal detected separately from cart items');

const r3 = tcFindPrices(mockRoot([
  { offscreen: null },
  { offscreen: '$5.00' },
]));
eq(r3.length, 1, 'skips elements with no offscreen child');
eq(r3[0].amountInCents, 500, 'remaining price parsed correctly');

const r4 = tcFindPrices(null);
eq(r4.length, 0, 'null root returns empty array (jsc has no document)');

print('');
print(passed + ' passed, ' + failed + ' failed');
if (failed > 0) throw new Error('tests failed');
