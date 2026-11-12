(()=> {
  function init() {
    const section = document.getElementById('tp-page-rules');
    const original = document.getElementById('rulebook-default');
    if (!section || !original || original.dataset.tabsReady) return;
    original.dataset.tabsReady = 'true';
    const definitions = [
      ['start','はじめに','ゲームの概要・開催期間'],
      ['ranking','勝ち方','目標・攻略・順位'],
      ['factory','工場・図鑑','製造・強化・レア坊主'],
      ['market','市場・銀行','出荷・購入・資金運用'],
      ['tax','税金','売上税・総資産税']
    ];
    const groups = new Map();
    const bar = document.createElement('div');
    bar.className = 'rb-tabs';
    bar.setAttribute('role','tablist');
    bar.setAttribute('aria-label','ルールブックのジャンル');
    const content = document.createElement('div');
    content.className = 'rb-content';
    for (const [key,label,description] of definitions) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'rb-tab';
      button.id = 'rb-tab-' + key;
      button.setAttribute('role','tab');
      button.setAttribute('aria-controls','rb-panel-' + key);
      button.setAttribute('aria-selected',key === 'start' ? 'true':'false');
      button.tabIndex = key === 'start' ? 0:-1;
      button.textContent = label;
      bar.append(button);
      const panel = document.createElement('div');
      panel.className = 'rb-panel';
      panel.id = 'rb-panel-' + key;
      panel.setAttribute('role','tabpanel');
      panel.setAttribute('aria-labelledby',button.id);
      panel.hidden = key !== 'start';
      const heading = document.createElement('p');
      heading.className = 'rb-description';
      heading.textContent = description;
      panel.append(heading);
      content.append(panel);
      groups.set(key,panel);
      button.addEventListener('click',()=>activate(key));
    }
    function activate(key) {
      for (const [name,panel] of groups) {
        const active = name === key;
        panel.hidden = !active;
        const tab = document.getElementById('rb-tab-' + name);
        tab.setAttribute('aria-selected',String(active));
        tab.tabIndex = active ? 0:-1;
      }
    }
    const tabs = [...bar.querySelectorAll('.rb-tab')];
    bar.addEventListener('keydown',event=>{
      const i = tabs.indexOf(document.activeElement);
      if (i < 0 || !['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length-1 : (i+(event.key === 'ArrowRight'?1:-1)+tabs.length)%tabs.length;
      tabs[next].click();
      tabs[next].focus();
      tabs[next].scrollIntoView({block:'nearest',inline:'nearest'});
    });
    const intro = [...section.children].filter(el=>el.tagName==='DETAILS');
    const entries = [...intro,...original.querySelectorAll(':scope > details')];
    function category(title) {
      if (/税|課税/.test(title)) return 'tax';
      if (/市場|銀行|購入|出荷|販売/.test(title)) return 'market';
      if (/製造|つくる|強化|レア|図鑑|工場/.test(title)) return 'factory';
      if (/勝|順位|データ|ランキング|コツ/.test(title)) return 'ranking';
      return 'start';
    }
    for (const details of entries) {
      const title = details.querySelector('summary')?.textContent || '';
      details.removeAttribute('name');
      groups.get(category(title)).append(details);
    }
    original.prepend(bar,content);
    original.classList.add('rb-organized');
    for (const [,panel] of groups) {
      if (panel.querySelector('details') === null) panel.hidden = true;
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();