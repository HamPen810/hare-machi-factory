(() => {
  function init() {
    const page=document.getElementById('tp-page-rules');
    const standard=document.getElementById('rulebook-default');
    const custom=document.getElementById('rulebook-custom');
    const tabs=standard?.querySelector('.rb-tabs');
    const contents=standard?.querySelector('.rb-content');
    if(!page||!standard||!custom||!tabs||!contents||page.dataset.customTabsReady) return;
    page.dataset.customTabsReady='1';
    // The existing navigation lived inside a node hidden by app.js
    // whenever the administrator supplied custom rules.
    page.insertBefore(tabs,standard);
    page.insertBefore(contents,standard);
    const buttons=[...tabs.querySelectorAll('[role="tab"]')];
    const panels=[...contents.querySelectorAll('[role="tabpanel"]')];
    const map=Object.fromEntries(panels.map(p=>[p.id.replace('rb-panel-',''),p]));
    const extra=document.createElement('button');
    extra.type='button'; extra.className='rb-tab'; extra.id='rb-tab-full';
    extra.setAttribute('role','tab');extra.setAttribute('aria-controls','rb-panel-full');
    extra.textContent='全文';
    const full=document.createElement('section');
    full.id='rb-panel-full';full.className='rb-panel';
    full.setAttribute('role','tabpanel');full.setAttribute('aria-labelledby',extra.id);
    contents.append(full); tabs.append(extra);
    buttons.push(extra);panels.push(full);
    let selected='start';
    function activate(key) {
      selected=key;
      for(const b of buttons) {
        const active=b.id==='rb-tab-'+key;
        b.setAttribute('aria-selected',String(active));b.tabIndex=active?0:-1;
      }
      for(const p of panels) p.hidden=p.id!=='rb-panel-'+key;
    }
    for(const b of buttons) b.addEventListener('click',()=>activate(b.id.slice(7)));
    tabs.addEventListener('keydown',event=>{
      if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
      const visible=buttons.filter(b=>!b.hidden);
      const i=visible.indexOf(document.activeElement);if(i<0)return;
      event.preventDefault();
      const j=event.key==='Home'?0:event.key==='End'?visible.length-1:
        (i+(event.key==='ArrowRight'?1:-1)+visible.length)%visible.length;
      visible[j].click();visible[j].focus();
    });
    const words=[
      ['tax',/税|課税|徴収|税率|税額/],
      ['market',/市場|売買|出荷|購入|販売|価格|売り手|銀行|借入|借金|預け|払入|返済|満期/],
      ['factory',/製造|工場|強化|タップ|作業|レア|図鑑|生産|自動/],
      ['ranking',/勝|順位|ランキング|部門|純利益|集計|クラス/]
    ];
    function classify(s) {
      const scores=words.map(([key,pattern])=>[key,(s.match(new RegExp(pattern.source,'g'))||[]).length]);
      scores.sort((a,b)=>b[1]-a[1]);return scores[0][1]>0?scores[0][0]:'start';
    }
    let last='';
    function refresh() {
      const raw=custom.textContent||'';
      if(raw===last)return;
      last=raw;
      const isCustom=!!raw.trim();
      page.classList.toggle('rb-custom-active',isCustom);
      extra.hidden=!isCustom;
      for(const p of panels)p.querySelectorAll('.rb-custom-text').forEach(node=>node.remove());
      if(isCustom) {
        const pieces=raw.match(/[^。！？!?\n]+[。！？!?]?|\n+/gu)||[raw];
        const grouped={start:[],ranking:[],factory:[],market:[],tax:[]};
        for(const piece of pieces)if(piece.trim())grouped[classify(piece)].push(piece.trim());
        function block(text) {
          const el=document.createElement('article');el.className='rb-custom-text';
          el.textContent=text;return el;
        }
        for(const [key,parts] of Object.entries(grouped)) {
          let buffer='';
          for(const text of parts) {
            if(buffer.length>250){map[key].append(block(buffer));buffer='';}
            buffer+=text;
          }
          if(buffer)map[key].append(block(buffer));
        }
        full.append(block(raw));
      }
      activate(selected==='full'&&!isCustom?'start':selected);
    }
    // Custom rules arrive asynchronously after the initial page load.
    new MutationObserver(refresh).observe(custom,{childList:true,characterData:true,subtree:true});
    page.classList.add('rb-custom-tabs-ready');
    last=null;refresh();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();