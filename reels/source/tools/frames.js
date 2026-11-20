const {chromium}=require('playwright');
(async()=>{const [,,dir,out,fps,total,w,nw]=process.argv;
 const b=await chromium.launch(); const p=await b.newPage({viewport:{width:1080,height:1920}});
 p.on('pageerror',e=>console.log('ERR',e.message));
 await p.goto('file://'+dir+'/index.html'); await p.evaluate(()=>document.fonts.ready);
 for(let i=+w;i<+total;i+=+nw){const t=i/(+fps); await p.evaluate(t=>render(t),t);
   await p.screenshot({path:`${out}/${String(i).padStart(5,'0')}.jpg`,type:'jpeg',quality:94});}
 await b.close();})();
