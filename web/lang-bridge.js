// 队友 i18n.js 切语言时派发 medbridge:language，本项目的询盘助手、注册清单、机器人监听 mb:langchange。这里转一下。
// 本项目自己翻译的区域加 data-no-i18n，免得队友的词典再替换一遍。
(() => {
  const mark = () => document.querySelectorAll('#view-registry, [data-view="registry"]').forEach((el) => el.setAttribute('data-no-i18n', ''));
  document.addEventListener('medbridge:language', (e) => {
    mark();
    const lang = String(e.detail || '').startsWith('en') ? 'en' : 'zh';
    document.dispatchEvent(new CustomEvent('mb:langchange', { detail: { lang } }));
  });
  document.addEventListener('DOMContentLoaded', mark);
})();
