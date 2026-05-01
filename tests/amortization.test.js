// Run with:
//   jsc amortization.js tests/amortization.test.js

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

print('detectCategoryFromText');
eq(tcAmortization.detectCategoryFromText('Home & Kitchen › Kitchen & Dining › Cookware'), 'kitchen', 'kitchen breadcrumb');
eq(tcAmortization.detectCategoryFromText('Tools & Home Improvement › Power Tools'), 'tools', 'tools breadcrumb');
eq(tcAmortization.detectCategoryFromText('Electronics › Headphones'), 'electronics', 'electronics breadcrumb');
eq(tcAmortization.detectCategoryFromText('Furniture › Bedroom Furniture'), 'furniture', 'furniture breadcrumb');
eq(tcAmortization.detectCategoryFromText('Appliances › Large Appliances'), 'appliances', 'appliances breadcrumb');
eq(tcAmortization.detectCategoryFromText('Books › Fiction › Mystery'), null, 'non-durable returns null');
eq(tcAmortization.detectCategoryFromText('Clothing, Shoes & Jewelry'), null, 'apparel returns null');
eq(tcAmortization.detectCategoryFromText(''), null, 'empty returns null');
eq(tcAmortization.detectCategoryFromText(null), null, 'null returns null');

print('formatPerUse');
eq(tcAmortization.formatPerUse(0.40), '$0.40', 'sub-dollar two decimals');
eq(tcAmortization.formatPerUse(0.005), '<$0.01', 'tiny clamps to <$0.01');
eq(tcAmortization.formatPerUse(3.50), '$4', 'low integer rounds');
eq(tcAmortization.formatPerUse(125), '$125', 'large integer');
eq(tcAmortization.formatPerUse(null), '', 'null returns empty');

print('DEFAULT_USES sanity');
eq(typeof tcAmortization.DEFAULT_USES.kitchen, 'number', 'kitchen has default');
eq(tcAmortization.DEFAULT_USES.electronics > 0, true, 'electronics positive');

print('detectPageUses respects settings');
eq(tcAmortization.detectPageUses({ showPerUseAmortization: false }), null, 'feature off returns null');
eq(tcAmortization.detectPageUses(null), null, 'null settings returns null');
// detectPageUses with feature on but no document returns null in jsc since document is undefined
eq(tcAmortization.detectPageUses({ showPerUseAmortization: true }), null, 'no document returns null');

print('');
print(passed + ' passed, ' + failed + ' failed');
if (failed > 0) throw new Error('tests failed');
