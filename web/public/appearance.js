// Apply a saved appearance before the application paints. No inline CSP exception.
try {
  const mode = localStorage.getItem('popcorn-sr-appearance');
  if (['light', 'dark', 'system'].includes(mode)) document.documentElement.dataset.theme = mode;
} catch { /* System appearance remains available without browser storage. */ }
