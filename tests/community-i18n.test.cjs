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
