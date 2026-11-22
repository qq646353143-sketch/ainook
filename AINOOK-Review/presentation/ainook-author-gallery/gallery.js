(() => {
  const main = document.getElementById('main');
  const links = main.querySelectorAll('a[data-house-link]');

  function syncThemeLinks() {
    const theme = new URLSearchParams(location.search).get('theme-preview');
    for (const link of links) {
      const url = new URL(link.href);
      if (theme === 'day' || theme === 'night') url.searchParams.set('theme-preview', theme);
      else url.searchParams.delete('theme-preview');
      link.href = url;
    }
  }

  main.addEventListener('click', (event) => {
    const link = event.target.closest('a[data-house-link]');
    if (!link) return;
    if (link.matches('[data-room-choice][aria-current="page"]')) event.preventDefault();
    syncThemeLinks();
  });
  const observer = new MutationObserver(syncThemeLinks);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  window.addEventListener('pageshow', syncThemeLinks);
  syncThemeLinks();
})();
