const wageInput = document.getElementById('wage');
const hideCheckbox = document.getElementById('hide-prices');
const enabledToggle = document.getElementById('enabled');
const form = document.getElementById('wage-form');
const status = document.getElementById('status');

function flashStatus(message, kind) {
  status.textContent = message;
  status.className = kind || '';
}

(async () => {
  const s = await tcSettings.getAll();
  if (s.hourlyWage) wageInput.value = s.hourlyWage;
  hideCheckbox.checked = !!s.hidePrices;
  enabledToggle.checked = s.enabled !== false;
})();

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const value = parseFloat(wageInput.value);
  if (isNaN(value) || value <= 0) {
    flashStatus('Please enter a valid wage greater than 0.', 'error');
    return;
  }
  await tcSettings.set('hourlyWage', value);
  flashStatus('Saved.', 'ok');
});

hideCheckbox.addEventListener('change', async () => {
  await tcSettings.set('hidePrices', hideCheckbox.checked);
  flashStatus(
    hideCheckbox.checked ? 'Dollar prices hidden — time only.' : 'Showing both price and time.',
    'ok'
  );
});

enabledToggle.addEventListener('change', async () => {
  await tcSettings.set('enabled', enabledToggle.checked);
  flashStatus(
    enabledToggle.checked ? 'Time effect on.' : 'Time effect off.',
    'ok'
  );
});

document.getElementById('open-options').addEventListener('click', (e) => {
  e.preventDefault();
  chrome.runtime.openOptionsPage();
});
