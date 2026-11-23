'use strict';

const form = document.querySelector('form[data-edition]');
const feed = document.querySelector('.editorial-feed');
const params = new URLSearchParams(location.search);
const input = form.elements.q;
const source = form.elements.source;
const days = form.elements.days;
input.value = (params.get('q') || '').slice(0, 140);
source.value = params.get('source') || '';
days.value = params.get('days') || 'all';
if (source.selectedIndex < 0) source.value = '';
if (days.selectedIndex < 0) days.value = 'all';

async function showResults() {
  if (!input.value.trim() && !source.value && days.value === 'all') return;
  const heading = feed.querySelector('header');
  try {
    const response = await fetch(new URL('search.json', location.href));
    if (!response.ok) throw new Error('Cannot read news index');
    const articles = await response.json();
    const query = input.value.trim().toLowerCase().replaceAll('ß', 'ss').replaceAll('ς', 'σ');
    const cutoff = days.value === 'all' ? 0 : Date.parse(form.dataset.edition) - Number(days.value) * 86400000;
    const results = articles.filter(article => article.search.includes(query) &&
      (!source.value || article.source === source.value) &&
      (!cutoff || Date.parse(article.publishedAt) >= cutoff));
    document.querySelector('.editorial-spotlight')?.remove();
    feed.replaceChildren(heading);
    heading.querySelector('h2').textContent = '搜索结果';
    heading.querySelector('span').textContent = results.length + ' 条资讯';
    const clear = document.createElement('a');
    clear.className = 'editorial-clear';
    clear.href = form.action;
    clear.textContent = '清除筛选';
    heading.querySelector('div').append(clear);
    if (results.length) {
      feed.insertAdjacentHTML('beforeend', results.map(article => article.html).join(''));
    } else {
      const empty = document.createElement('p');
      empty.className = 'editorial-empty';
      empty.textContent = '当前没有符合条件的资讯。';
      feed.append(empty);
    }
  } catch {
    const error = document.createElement('p');
    error.setAttribute('role', 'status');
    error.textContent = '筛选暂时不可用，仍可浏览本期资讯。';
    feed.prepend(error);
  }
}

showResults();
