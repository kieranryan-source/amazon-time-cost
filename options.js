const FIELD_KEYS = [
  'hourlyWage',
  'taxRate',
  'monthlyFixedExpenses',
  'annualLeisureHours',
  'framingPrimary',
  'framingSecondary',
  'showOpportunityCost',
  'investmentReturnRate',
  'showPerUseAmortization',
  'showSubscriptionAnnualizer',
  'showCartAggregation',
  'donationLinkUrl',
];

const PERCENT_KEYS = new Set(['taxRate', 'investmentReturnRate']);

const status = document.getElementById('status');
const donationLink = document.getElementById('donation-link');
const footerCredit = document.getElementById('footer-credit');

let statusTimer = null;

function flashStatus(message, kind) {
  status.textContent = message;
  status.className = 'visible ' + (kind || '');
  if (statusTimer) clearTimeout(statusTimer);
  statusTimer = setTimeout(() => {
    status.classList.remove('visible');
  }, 1500);
}

function getFieldValue(el, key) {
  if (el.type === 'checkbox') return el.checked;
  if (el.tagName === 'SELECT') return el.value || null;
  if (el.type === 'number') {
    if (el.value === '') return null;
    const n = parseFloat(el.value);
    if (isNaN(n)) return null;
    return PERCENT_KEYS.has(key) ? n / 100 : n;
  }
  if (el.type === 'url') return el.value || '';
  return el.value;
}

function setFieldValue(el, key, value) {
  if (el.type === 'checkbox') {
    el.checked = !!value;
    return;
  }
  if (el.tagName === 'SELECT') {
    el.value = value == null ? '' : value;
    return;
  }
  if (el.type === 'number') {
    if (value == null) {
      el.value = '';
      return;
    }
    el.value = PERCENT_KEYS.has(key) ? (value * 100).toString() : value.toString();
    return;
  }
  el.value = value == null ? '' : value;
}

function updateDonationLink(url) {
  if (url && /^https?:\/\//.test(url)) {
    donationLink.href = url;
    footerCredit.classList.remove('hidden');
  } else {
    donationLink.removeAttribute('href');
    footerCredit.classList.add('hidden');
  }
}

(async function init() {
  const settings = await tcSettings.getAll();

  FIELD_KEYS.forEach((key) => {
    const el = document.getElementById(key);
    if (!el) return;
    setFieldValue(el, key, settings[key]);

    el.addEventListener('change', async () => {
      const value = getFieldValue(el, key);
      try {
        await tcSettings.set(key, value);
        flashStatus('Saved', 'ok');
        if (key === 'donationLinkUrl') updateDonationLink(value);
      } catch (e) {
        console.warn('[Amazon Time Cost] failed to save setting', key, e);
        flashStatus('Save failed — see console', 'error');
      }
    });
  });

  updateDonationLink(settings.donationLinkUrl);
})();
