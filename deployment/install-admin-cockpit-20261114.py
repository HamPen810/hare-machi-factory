"""Admin Command Deck: layout-only ZIP patch, fail-closed.
All production game / banking / taxes / account operations are unchanged.
No new authenticated APIs or DB mutations. Preserve existing form DOM nodes.
"""
from pathlib import Path
from zipfile import ZipFile
import io,ast,re,collections
p=Path('hare-machi-render.zip')
with ZipFile(p) as z:
    entries=[(info,z.read(info.filename)) for info in z.infolist()]
    comment=z.comment
files={i.filename:b for i,b in entries}

html=files['static/admin.html'].decode('utf8')
assert 'id="tab-overview"' in html
assert 'id="panel-operations"' in html
assert 'id="bulletin-admin-posts"' in html
assert 'id="bulletin-admin-messages"' in html
assert 'id="tab-analysis"' not in html

old_html=html
before=collections.Counter(re.findall(r'\bid="([^"]+)"',html))

def move(pattern,description):
    global html
    match=re.search(pattern,html,re.S)
    if not match:
        raise AssertionError('Current archive markup changed: '+description)
    value=match.group()
    html=html[:match.start()]+html[match.end():]
    return value

# Original announcement form and its handlers are moved, NEVER rebuilt.
announcement=move(r'<details class="an-fold" open><summary>全体へのお知らせ</summary>.*?</form></details>',
                  'announcement details/form')
post_list=move(r'<h3>配信済みのお知らせ</h3>\s*<div id="bulletin-admin-posts"[^>]*></div>',
               'bulletin post list')
message_list=move(r'<h3>プレイヤーからのメッセージ</h3>\s*<div id="bulletin-admin-messages"[^>]*></div>',
                  'player message list')
rulebook=move(r'<details><summary>ルールブックを編集</summary>.*?</details>','rulebook')
extra=move(r'<details id="extra-slots-section"[^>]*>.*?</details>','extra slots')
player=move(r'<form id="player-form"[^>]*>.*?</form>','player administration')

# Split original overview chart block into dedicated Analysis tab.
start=html.index('<div class="an-section-title">')
end=html.index('</section>',start)
analysis_html=html[start:end]
html=html[:start]+'''<div id="overview-brief"></div>
<div class="console-quick-nav">
<button type="button" data-goto="analysis">データ分析を見る</button>
<button type="button" data-goto="messages">メッセージを確認</button>
<button type="button" data-goto="notices">お知らせを管理</button>
</div>
'''+html[end:]
overview_end=html.index('</section>',html.index('<section id="panel-overview"'))
analysis_panel='''<section id="panel-analysis" role="tabpanel" aria-labelledby="tab-analysis" hidden>
<div class="an-title"><div><small class="muted">DEEP ANALYTICS</small><h2>データ分析ラボ</h2></div><span class="console-chip">全プレイヤー統計</span></div>
'''+analysis_html+'''
</section>
'''
html=html[:overview_end+len('</section>')]+analysis_panel+html[overview_end+len('</section>'):]

# Separate management and messages from basic operations without touching
# forms, their names, fields or existing submit handlers.
notices='''<section id="panel-notices" role="tabpanel" aria-labelledby="tab-notices" hidden>
<div class="console-pane-title"><h2>お知らせセンター</h2><span class="console-chip">配信・履歴</span></div>
<div class="console-switcher"><button class="console-compose-tab" data-compose="no" type="button" aria-pressed="true">配信履歴</button>
<button class="console-compose-tab" data-compose="yes" type="button" aria-pressed="false">お知らせを作成</button>
<button id="notice-refresh-proxy" type="button">再読み込み</button></div>
<div id="notice-inbox-area" class="console-inbox">
<div id="notice-inbox" class="console-inbox" style="grid-column:1/-1">
<div id="notice-list" class="console-inbox-list"></div>
<div id="notice-detail" class="console-inbox-detail"></div>
</div>
</div>
<div id="notice-compose-area" class="console-compose" hidden>
'''+announcement+'''
</div>
'''+post_list+'''
</section>'''
messages='''<section id="panel-messages" role="tabpanel" aria-labelledby="tab-messages" hidden>
<div class="console-pane-title"><h2>プレイヤーメッセージ</h2><span class="console-chip">受信トレイ</span></div>
<div id="message-inbox" class="console-inbox">
<div id="message-list" class="console-inbox-list"></div>
<div id="message-detail" class="console-inbox-detail"></div>
</div>
'''+message_list+'''
</section>'''
advanced='''<section id="panel-advanced" role="tabpanel" aria-labelledby="tab-advanced" hidden>
<div class="console-pane-title"><h2>高度な管理</h2><span class="console-chip">設定・アカウント</span></div>
'''+rulebook+extra+player+'''
</section>'''
point=html.index('<section id="panel-operations"')
html=html[:point]+notices+'\n'+messages+'\n'+advanced+'\n'+html[point:]

nav=re.search(r'<nav class="tabs" role="tablist" aria-label="管理画面">.*?</nav>',html,re.S)
assert nav
old_nav=nav.group()
new_nav=old_nav.replace('>分析・概要</button>','>概要</button>',1)
new_nav=new_nav.replace('<button role="tab" id="tab-players"',
  '<button role="tab" id="tab-analysis" data-panel="analysis" aria-controls="panel-analysis" aria-selected="false">データ分析</button>'
  '<button role="tab" id="tab-notices" data-panel="notices" aria-controls="panel-notices" aria-selected="false">お知らせ</button>'
  '<button role="tab" id="tab-messages" data-panel="messages" aria-controls="panel-messages" aria-selected="false">メッセージ</button>'
  '<button role="tab" id="tab-players"',1)
new_nav=new_nav.replace('</nav>',
  '<button role="tab" id="tab-advanced" data-panel="advanced" aria-controls="panel-advanced" aria-selected="false">高度な管理</button></nav>',1)
html=html.replace(old_nav,new_nav,1)
tab_labels=re.findall(r'<button role="tab"[^>]*data-panel="([^"]+)"[^>]*>(.*?)</button>',new_nav,re.S)
assert len(tab_labels)>=14,tab_labels
mobile_select='<select id="admin-mobile-nav" aria-label="管理画面を切り替える">'+''.join(
 '<option value="'+name+'">'+re.sub('<[^>]+>','',label)+'</option>' for name,label in tab_labels)+'</select>'
html=html.replace(new_nav,new_nav+mobile_select,1)

# Modal is read-only; all transaction confirmation elements remain untouched.
modal='''<div id="console-record-dialog" class="console-modal" role="dialog" aria-modal="true" aria-label="一覧項目の詳細" hidden>
<div class="console-modal-card"><div class="console-pane-title"><h3>レコードの詳細</h3>
<button type="button" id="console-record-close">閉じる</button></div>
<div id="console-record-fields" class="console-modal-content"></div></div></div>'''
html=html.replace('</main>',modal+'</main>',1)
html=html.replace('<script src="/admin-ux.js" defer></script>',
                  '<script src="/admin-ux.js" defer></script><script src="/admin-cockpit.js" defer></script>',1)
assert html.count('</style>')==1
style=Path('deployment/admin-cockpit-20261114.css').read_text(encoding='utf8')
# One additional CSS rule for the mobile inbox back action.
style+='''
@media(min-width:741px){body.console-active .console-mobile-back{display:none}}
@media(max-width:740px){body.console-active .console-mobile-back{align-self:flex-start;flex:0 0 auto}}
body.console-active .console-inbox-detail .console-letter-body{margin:0}
body.console-active #panel-notices #notice-inbox-area[hidden],
body.console-active #panel-notices #notice-compose-area[hidden]{display:none!important}
body.console-active #panel-notices #notice-inbox-area{display:grid;flex:1;min-height:0}
body.console-active #panel-notices #notice-inbox{height:100%;min-height:0}
body.console-active .an-chart[hidden]{display:none!important}
body.console-active #panel-advanced>details,body.console-active #panel-advanced>form{flex:1;min-height:0}
'''
html=html.replace('</style>',style+'</style>',1)
after=collections.Counter(re.findall(r'\bid="([^"]+)"',html))
for identifier,count in before.items():
    assert after[identifier]==count,('altered existing control',identifier,count,after[identifier])
assert all(after[name]==1 for name in ['admin-mobile-nav','panel-analysis','panel-notices',
         'panel-messages','panel-advanced','notice-list','message-list','notice-detail','message-detail',
         'console-record-dialog','console-record-fields'])
assert html.count('<form id="announcement-form"')==1
assert html.count('<form id="funds-form"')==1
assert html.count('<form id="bank-config"')==1
files['static/admin.html']=html.encode('utf8')

# Existing read-only dashboard chart renderer listens to the ANALYSIS panel,
# not the landing overview. The computation and metrics remain identical.
ux=files['static/admin-ux.js'].decode('utf8')
old="const shown=$('#panel-overview')&&!$('#panel-overview').hidden;"
new="const shown=$('#panel-analysis')&&!$('#panel-analysis').hidden;"
assert ux.count(old)==1
ux=ux.replace(old,new,1)
# Clicking analysis tab should call the current chart renderer on demand.
old="if(tab.dataset.panel==='overview')renderAnalytics();"
new="if(tab.dataset.panel==='analysis')renderAnalytics();"
assert ux.count(old)==1
ux=ux.replace(old,new,1)
files['static/admin-ux.js']=ux.encode('utf8')

# Hook after successful bulletin rendering, and keep API logic unchanged.
js=files['static/admin.js'].decode('utf8')
old="   box.append(meta,body);messages.append(box);\n  }\n }catch(error)"
new="   box.append(meta,body);messages.append(box);\n  }\n  document.dispatchEvent(new Event('admin-bulletin-ready'));\n }catch(error)"
assert js.count(old)==1,('bulletin completion anchor',js.count(old))
js=js.replace(old,new,1)
files['static/admin.js']=js.encode('utf8')

# Route one more cacheable JS file, no extra API routes or polling.
server=files['server.py'].decode('utf8')
old="'/admin','/admin/','/admin.js','/admin-ux.js'):"
new="'/admin','/admin/','/admin.js','/admin-ux.js','/admin-cockpit.js'):"
assert server.count(old)==1,('server route anchor',server.count(old))
server=server.replace(old,new,1)
old="'/admin.js':'admin.js','/admin-ux.js':'admin-ux.js'}[self.path]"
new="'/admin.js':'admin.js','/admin-ux.js':'admin-ux.js','/admin-cockpit.js':'admin-cockpit.js'}[self.path]"
assert server.count(old)==1,('server mapping anchor',server.count(old))
server=server.replace(old,new,1)
ast.parse(server)
files['server.py']=server.encode('utf8')
files['static/admin-cockpit.js']=Path('deployment/admin-cockpit-20261114.js').read_bytes()

# All existing ZIP members except the admin presentation and route remain identical.
out=io.BytesIO()
with ZipFile(out,'w') as z:
    z.comment=comment
    existing=set()
    for info,data in entries:
        z.writestr(info,files[info.filename]);existing.add(info.filename)
    if 'static/admin-cockpit.js' not in existing:z.writestr('static/admin-cockpit.js',files['static/admin-cockpit.js'])
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    for info,data in entries:
        if info.filename not in ('static/admin.html','static/admin.js','static/admin-ux.js','static/admin-cockpit.js','server.py'):
            assert z.read(info.filename)==data,('unexpected business code change',info.filename)
p.write_bytes(out.getvalue())
print('PASS: Fixed-view admin cockpit, separate overview/analytics/notices/messages/basic/advanced, original forms intact')
