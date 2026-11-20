const {chromium}=require('playwright');
(async()=>{const [,,dir,out,...ts]=process.argv;
 const b=await chromium.launch(); const p=await b.newPage({viewport:{width:1080,height:1920}});
 p.on('pageerror',e=>console.log('ERR',e.message)); p.on('console',m=>console.log('LOG',m.text()));
 await p.goto('file://'+dir+'/index.html'); await p.evaluate(()=>document.fonts.ready);
 for(const t of ts){await p.evaluate(t=>render(+t),t); await p.screenshot({path:`${out}/f_${t}.jpg`,type:'jpeg',quality:80});}
 await b.close();})();
