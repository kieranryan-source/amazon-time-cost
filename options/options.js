// Options page controller.

(async function () {
  const s = await P2TSettings.load();
  const $ = (id) => document.getElementById(id);

  // Populate primitives
  $('hourlyWage').value = s.hourlyWage;
  $('taxRate').value = Math.round(s.taxRate * 100);
  $('monthlyFixedExpenses').value = s.monthlyFixedExpenses;
  $('workHoursPerYear').value = s.workHoursPerYear;
  $('primaryFraming').value = s.primaryFraming;
  $('secondaryFraming').value = s.secondaryFraming;
  $('showInvestment').checked = s.showInvestment;
  $('investmentRate').value = (s.investmentRate * 100).toFixed(1);
  $('returnType').value = s.returnType;
  $('enabled').checked = s.enabled;
  $('showCartTotal').checked = s.showCartTotal;
  $('showWishlistTotal').checked = s.showWishlistTotal;
  $('showSubscriptionAnnual').checked = s.showSubscriptionAnnual;
  $('enableKeyboardToggle').checked = s.enableKeyboardToggle;
  $('showReferenceUnit').checked = s.showReferenceUnit;

  const horizons = Array.isArray(s.investmentYears) ? s.investmentYears : [20];
  $('horizon1').value = horizons[0] || '';
  $('horizon2').value = horizons[1] || '';
  $('horizon3').value = horizons[2] || '';

  // --- Reference units UI: dynamic list of rows ---
  let refUnits = Array.isArray(s.referenceUnits) ? s.referenceUnits.slice() : [];
  let activeRefId = s.activeReferenceUnitId;

  function renderRefUnitsList() {
    const container = $('refUnitsList');
    container.innerHTML = '';
    refUnits.forEach((u, i) => {
      const row = document.createElement('div');
      row.className = 'ref-unit-row';
      row.innerHTML = `
        <input type="text" class="ref-name" placeholder="e.g. gym membership" value="${escapeHtml(u.name)}">
        <div class="input-wrap ref-cost-wrap">
          <span class="input-prefix">$</span>
          <input type="number" class="ref-cost" min="0" step="0.5" value="${Number(u.cost) || 0}">
        </div>
        <button type="button" class="ref-remove" data-idx="${i}" aria-label="Remove">&times;</button>
      `;
      container.appendChild(row);

      row.querySelector('.ref-name').addEventListener('input', (e) => {
        refUnits[i].name = e.target.value;
        refreshActiveSelect();
      });
      row.querySelector('.ref-cost').addEventListener('input', (e) => {
        refUnits[i].cost = parseFloat(e.target.value) || 0;
        updateDerivedPanel();
      });
      row.querySelector('.ref-remove').addEventListener('click', () => {
        refUnits.splice(i, 1);
        renderRefUnitsList();
        refreshActiveSelect();
      });
    });
    if (refUnits.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'ref-empty';
      empty.textContent = 'No reference units configured. Add one to see prices in units of something meaningful to you.';
      container.appendChild(empty);
    }
  }

  function refreshActiveSelect() {
    const select = $('activeReferenceUnitId');
    const prev = activeRefId;
    select.innerHTML = '';
    refUnits.forEach((u) => {
      const opt = document.createElement('option');
      opt.value = u.id;
      opt.textContent = u.name || '(unnamed)';
      select.appendChild(opt);
    });
    if (refUnits.length === 0) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = '(none configured)';
      select.appendChild(opt);
      activeRefId = '';
    } else {
      if (!refUnits.find((u) => u.id === prev)) {
        activeRefId = refUnits[0].id;
      }
      select.value = activeRefId;
    }
    updateDerivedPanel();
  }

  $('activeReferenceUnitId').addEventListener('change', (e) => {
    activeRefId = e.target.value;
    updateDerivedPanel();
  });

  $('addRefUnit').addEventListener('click', () => {
    const id = `ref_${Math.random().toString(36).substr(2, 6)}`;
    refUnits.push({ id, name: '', cost: 0 });
    renderRefUnitsList();
    refreshActiveSelect();
  });

  renderRefUnitsList();
  refreshActiveSelect();
  if (activeRefId) $('activeReferenceUnitId').value = activeRefId;

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  // --- Read form into a settings snapshot ---
  function readForm() {
    const horizonInputs = [
      parseInt($('horizon1').value, 10),
      parseInt($('horizon2').value, 10),
      parseInt($('horizon3').value, 10),
    ].filter((v) => Number.isFinite(v) && v >= 1 && v <= 50);

    // Clean up reference units - drop empty names and zero costs
    const cleanRefs = refUnits
      .filter((u) => u.name && u.name.trim() && u.cost > 0)
      .map((u) => ({ id: u.id, name: u.name.trim(), cost: Number(u.cost) }));

    return {
      hourlyWage: parseFloat($('hourlyWage').value) || 0,
      taxRate: (parseFloat($('taxRate').value) || 0) / 100,
      monthlyFixedExpenses: parseFloat($('monthlyFixedExpenses').value) || 0,
      workHoursPerYear: parseInt($('workHoursPerYear').value, 10) || 2000,
      primaryFraming: $('primaryFraming').value,
      secondaryFraming: $('secondaryFraming').value,
      showInvestment: $('showInvestment').checked,
      investmentRate: (parseFloat($('investmentRate').value) || 0) / 100,
      returnType: $('returnType').value,
      investmentYears: horizonInputs.length > 0 ? horizonInputs : [20],
      referenceUnits: cleanRefs,
      activeReferenceUnitId: cleanRefs.find((u) => u.id === activeRefId) ? activeRefId : (cleanRefs[0] ? cleanRefs[0].id : null),
      showReferenceUnit: $('showReferenceUnit').checked,
      enabled: $('enabled').checked,
      showCartTotal: $('showCartTotal').checked,
      showWishlistTotal: $('showWishlistTotal').checked,
      showSubscriptionAnnual: $('showSubscriptionAnnual').checked,
      enableKeyboardToggle: $('enableKeyboardToggle').checked,
      investmentRateWarnThreshold: 0.20,
    };
  }

  // --- Live derived panel ---
  function updateDerivedPanel() {
    const draft = readForm();
    const pretax = P2TFramings.effectiveHourlyRate(draft, 'pretax');
    const posttax = P2TFramings.effectiveHourlyRate(draft, 'posttax');
    const discretionary = P2TFramings.effectiveHourlyRate(draft, 'discretionary');

    $('rate-pretax').textContent = `$${pretax.toFixed(2)}/hr`;
    $('rate-posttax').textContent = `$${posttax.toFixed(2)}/hr`;
    $('rate-discretionary').textContent = `$${discretionary.toFixed(2)}/hr`;

    const exampleCents = 10000;
    const hours = P2TFramings.priceToHours(exampleCents, draft, draft.primaryFraming);
    $('example-hours').textContent = P2TFramings.formatTime(hours, draft.primaryFraming);

    const years = draft.investmentYears[0] || 20;
    const future = P2TFramings.investmentGrowth(exampleCents, draft.investmentRate, years);
    $('example-rate').textContent = `${(draft.investmentRate * 100).toFixed(1)}%`;
    $('example-years').textContent = years;
    $('example-future').textContent = `$${future.toFixed(2)}`;
  }

  updateDerivedPanel();

  document.querySelectorAll('input, select').forEach((el) => {
    el.addEventListener('input', updateDerivedPanel);
    el.addEventListener('change', updateDerivedPanel);
  });

  $('save').addEventListener('click', async () => {
    const settings = readForm();
    await P2TSettings.set(settings);
    const status = $('saveStatus');
    status.textContent = 'Saved. Refresh Amazon tabs to see changes.';
    status.classList.add('visible');
    setTimeout(() => status.classList.remove('visible'), 2500);
  });
})();
