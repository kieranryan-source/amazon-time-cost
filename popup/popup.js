(async function () {
  const s = await P2TSettings.load();

  const framingLabels = {
    pretax: 'Pre-tax',
    posttax: 'Take-home',
    discretionary: 'Discretionary',
    leisure: 'Leisure',
  };

  document.getElementById('enabledToggle').checked = s.enabled;
  document.getElementById('statusLabel').textContent = s.enabled ? 'Enabled' : 'Paused';
  document.getElementById('currentRate').textContent = `$${s.hourlyWage}/hr`;
  document.getElementById('currentFraming').textContent = framingLabels[s.primaryFraming] || s.primaryFraming;

  if (s.showInvestment && s.investmentYears.length > 0) {
    const rate = (s.investmentRate * 100).toFixed(0);
    const years = s.investmentYears.join('/');
    document.getElementById('currentInvestment').textContent = `${rate}% / ${years}yr`;
  } else {
    document.getElementById('currentInvestment').textContent = 'Off';
  }

  document.getElementById('enabledToggle').addEventListener('change', async (e) => {
    await P2TSettings.set({ enabled: e.target.checked });
    document.getElementById('statusLabel').textContent = e.target.checked ? 'Enabled' : 'Paused';
  });

  document.getElementById('openSettings').addEventListener('click', () => {
    chrome.runtime.openOptionsPage();
  });

  // Load session stats
  const stats = await P2TSession.getSessionStats();
  const countEl = document.getElementById('sessionCount');
  const detailEl = document.getElementById('sessionDetail');
  const nudgeEl = document.getElementById('sessionNudge');

  if (stats.count === 0) {
    countEl.textContent = 'No items viewed yet';
    detailEl.textContent = '';
  } else {
    countEl.textContent = stats.count === 1
      ? '1 item viewed'
      : `${stats.count} items viewed`;
    const minutes = Math.round((Date.now() - stats.firstSeen) / 60000);
    const timeLabel = minutes < 60
      ? `${minutes} min`
      : `${(minutes / 60).toFixed(1)} hr`;
    detailEl.textContent = `Over the last ${timeLabel}${stats.totalViews > stats.count ? ` (${stats.totalViews} total views)` : ''}`;
  }

  // Escalating nudges - purely informational, no shame
  if (stats.count >= 30) {
    nudgeEl.textContent = 'That is a lot of browsing. Close the tab and revisit tomorrow?';
    nudgeEl.classList.add('nudge-strong');
  } else if (stats.count >= 15) {
    nudgeEl.textContent = 'Consider stepping away for a bit.';
    nudgeEl.classList.add('nudge-soft');
  }
})();
