const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.join(__dirname,'..');
function runtime(saved={}){
 const context={window:{},localStorage:{getItem:key=>saved[key]??null}};vm.createContext(context);
 for(const name of ['locales.js','community-locales.js','community-i18n.js'])vm.runInContext(fs.readFileSync(path.join(root,'static',name),'utf8'),context);
 return context.window;
}
test('community uses the same account, region and legacy language priority as home',()=>{
 const w=runtime({'sentryloot-region-v1':JSON.stringify({language:'uz'}),'bozor-language':'ru'});
 assert.equal(w.CommunityI18n.language(),'uz');assert.equal(w.CommunityI18n.language({language:'en'}),'en');
 assert.equal(runtime({'bozor-language':'uz'}).CommunityI18n.language(),'uz');
 assert.equal(runtime().CommunityI18n.language(),'en');
});
test('Uzbek backend errors are English on English pages and Uzbek on Uzbek pages',()=>{
 const {CommunityI18n:t}=runtime();
 assert.equal(t.translate('Ichki xatolik yuz berdi.','en'),'An internal error occurred. Please try again.');
 assert.equal(t.translate('Ichki xatolik yuz berdi.','uz'),'Ichki xatolik yuz berdi.');
 assert.equal(t.translate('Choose a game.','uz'),'O‘yinni tanlang.');
 assert.equal(t.translate('Choose a game.','en'),'Choose a game.');
 assert.equal(t.translate('Use between 3 and 24 characters.','uz'),'3–24 ta belgi kiriting.');
 assert.equal(t.translate('Use between 3 and 24 characters.','ru'),'Введите от 3 до 24 символов.');
});
test('all literal community UI translations are covered in Uzbek and Russian',()=>{
 const w=runtime(),source=fs.readFileSync(path.join(root,'static/community.js'),'utf8');
 const keys=[...source.matchAll(/\bt\(('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")/g)].map(m=>vm.runInNewContext(m[1]));
 const literal="('(?:[^'\\\\]|\\\\.)*'|\"(?:[^\"\\\\]|\\\\.)*\")";
 for(const name of ['heading','button','field','select','modal','empty'])for(const m of source.matchAll(new RegExp('\\b'+name+'\\('+literal,'g')))keys.push(vm.runInNewContext(m[1]));
 for(const m of source.matchAll(new RegExp('\\b(?:heading|empty)\\('+literal+',\\s*'+literal,'g')))keys.push(vm.runInNewContext(m[2]));
 for(const m of source.matchAll(new RegExp('\\blink\\([^,\\n]+,\\s*'+literal,'g')))keys.push(vm.runInNewContext(m[1]));

 for(const language of ['uz','ru']){
  const missing=[...new Set(keys)].filter(key=>!w.CommunityCopy[language][key]);assert.deepEqual(missing,[],language+' missing UI copy');
 }
});
test('community validation and media-service errors have translated equivalents',()=>{
 const w=runtime(),keys=new Set();
 for(const filename of ['community.py','community_safety.py','community_video.py','video_evidence.py']){
  const source=fs.readFileSync(path.join(root,filename),'utf8');
  for(const m of source.matchAll(/(?:fail\(core,\s*\d+\s*,\s*|raise (?:Unavailable|InvalidVideo|VideoUnavailable)\()'([^']+)'/g))keys.add(m[1]);
 }
 for(const language of ['uz','ru'])assert.deepEqual([...keys].filter(key=>!w.CommunityCopy[language][key]),[],language+' missing server errors');
});

test('notification copy covers every supported language and translates stored system events', () => {
 const data = JSON.parse(fs.readFileSync(path.join(root, 'static/regional-languages.json'), 'utf8'));
 const context = vm.createContext({
  window: { SENTRYLOOT_LANGUAGE_DATA: data, addEventListener() {} },
  document: { createElement: () => ({ setAttribute() {}, addEventListener() {} }), body: { append() {} }, addEventListener() {} },
 });
 vm.runInContext(fs.readFileSync(path.join(root, 'static/notification-panel.js'), 'utf8'), context);
 const panel = context.window.NotificationPanel;
 const keys = Object.keys(data.notificationMessages.uz).sort();
 for (const { code } of data.languages) {
  if (code !== 'en') {
   const dictionary = data.notificationMessages[code];
   const regional = data.messages[code];
   assert.deepEqual(Object.keys({ ...regional, ...dictionary }).filter(key => keys.includes(key)).sort(), keys, code);
   for (const [key, value] of Object.entries(dictionary)) {
    assert.ok(value.trim(), `${code}: ${key}`);
    assert.deepEqual((value.match(/\{\w+\}/g) ?? []).sort(), (key.match(/\{\w+\}/g) ?? []).sort(), `${code}: ${key}`);
   }
  }
  const order = panel.marketplaceCopy({ kind: 'order', title: 'Yangi buyurtma', body: 'BG-ABCDEF01 bo‘yicha to‘lov tasdiqlandi.' }, code);
  assert.equal(order.title, panel.translate('New order', code));
  assert.equal(order.body, panel.translate('Payment for {reference} was confirmed.', code, { reference: 'BG-ABCDEF01' }));
  const message = panel.marketplaceCopy({ kind: 'message', title: 'Yangi xabar', body: 'Suhbatda yangi xabar bor.', href: '/messages' }, code);
  assert.equal(message.body, 'Suhbatda yangi xabar bor.', 'messages written by people keep their original text');
  assert.equal(panel.communityCopy({ kind: 'comment', display_name: 'Sam' }, code), panel.translate('{player} commented on your post.', code, { player: 'Sam' }));
  assert.equal(panel.timestamp(new Date().toISOString(), code).time, panel.translate('Just now', code));
 }
 assert.equal(panel.copy('uz').title, 'Bildirishnomalar');
 assert.equal(panel.timestamp(new Date(Date.now() - 150000).toISOString(), 'uz').time, '2 daqiqa oldin');
 assert.equal(panel.copy('de').settings, 'Benachrichtigungseinstellungen');
 assert.equal(panel.communityCopy({ kind: 'follow', display_name: 'Sam' }, 'zh'), 'Sam 开始关注你了。');
 assert.equal(panel.marketplaceCopy({ kind: 'moderation', title: 'Moderatsiya natijasi', body: 'E’loningiz holati: published. Please update the title.' }, 'uz').body, 'E’loningiz chop etildi. Please update the title.');
});
