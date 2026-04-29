const wageInput = document.getElementById('wage');
const hideCheckbox = document.getElementById('hide-prices');
const form = document.getElementById('wage-form');
const status = document.getElementById('status');

function flashStatus(message, kind) {
  status.textContent = message;
  status.className = kind || '';
}

chrome.storage.local.get(['hourlyWage', 'hidePrices'], (result) => {
  if (result.hourlyWage) {
    wageInput.value = result.hourlyWage;
  }
  hideCheckbox.checked = !!result.hidePrices;
});

form.addEventListener('submit', (e) => {
  e.preventDefault();
  const value = parseFloat(wageInput.value);
  if (isNaN(value) || value <= 0) {
    flashStatus('Please enter a valid wage greater than 0.', 'error');
    return;
  }
  chrome.storage.local.set({ hourlyWage: value }, () => {
    flashStatus('Saved. Refresh any open Amazon tabs to see updated times.', 'ok');
  });
});

hideCheckbox.addEventListener('change', () => {
  chrome.storage.local.set({ hidePrices: hideCheckbox.checked }, () => {
    flashStatus(
      hideCheckbox.checked
        ? 'Dollar prices hidden — time only.'
        : 'Showing both price and time.',
      'ok'
    );
  });
});
