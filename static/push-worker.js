/* This worker never caches authenticated pages or API responses. */
self.addEventListener('push',event=>{
 let value;try{value=event.data?.json()}catch{return}
 if(!value)return;
 const language=(self.navigator.language||'en').slice(0,2);
 event.waitUntil(self.registration.showNotification('SentryLoot',{body:value.body?.[language]||value.body?.en||'You have a new account notification.',icon:'https://images.gamestorehub.com/site-assets/sentryloot-app-icon.png',tag:String(value.tag||'account-update').slice(0,100),data:{path:'/#notifications'}}));
});
self.addEventListener('notificationclick',event=>{
 event.notification.close();
 event.waitUntil((async()=>{const windows=await self.clients.matchAll({type:'window',includeUncontrolled:true});for(const client of windows){if(new URL(client.url).origin===self.location.origin){await client.navigate('/#notifications');await client.focus();return}}await self.clients.openWindow('/#notifications')})());
});
