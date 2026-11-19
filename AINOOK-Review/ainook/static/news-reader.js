(() => {
  document.querySelectorAll('[data-news-preview]').forEach((title) => {
    const panel = document.getElementById('news-' + title.dataset.newsPreview);
    if (!panel) return;
    title.setAttribute('aria-controls', panel.id);
    title.setAttribute('aria-expanded', 'false');
    let pending = false;
    let loaded = false;

    title.addEventListener('click', async (event) => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      panel.hidden = !panel.hidden;
      title.setAttribute('aria-expanded', String(!panel.hidden));
      if (panel.hidden || loaded || pending) return;
      pending = true;
      const status = document.createElement('p');
      status.className = 'news-load-status';
      status.setAttribute('role', 'status');
      status.textContent = '正在加载正文…';
      panel.replaceChildren(status);
      try {
        const response = await fetch(title.href + '?inline=1', {mode: 'same-origin', redirect: 'error'});
        if (!response.ok) throw new Error('Article unavailable');
        panel.innerHTML = await response.text();
        loaded = true;
      } catch {
        const link = document.createElement('a');
        link.href = title.href;
        link.textContent = '打开正文页';
        status.replaceChildren('暂时无法展开。', link);
      } finally {
        pending = false;
      }
    });
  });
})();
