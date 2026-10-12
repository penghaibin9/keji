(function(){
 if('noModule' in HTMLScriptElement.prototype&&Object.hasOwn&&Array.prototype.at&&window.fetch&&window.Promise)return;
 var message=document.getElementById('browser-compat');
 if(message){message.removeAttribute('hidden');document.body.innerHTML='';document.body.appendChild(message);}
})();
