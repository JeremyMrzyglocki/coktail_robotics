(() => {
"use strict";
const preference=matchMedia('(prefers-reduced-motion: reduce)');
const compact=matchMedia('(max-width:760px)');
let activeBand=0;
const C={bg:'#f4f3ed',brand:'#ff5b21'};
const FONT='Archivo, Arial, sans-serif';
const rows=[...document.querySelectorAll('.layer-row')];
function cl(v){return v<0?0:v>1?1:v;}
function e(v){v=cl(v);return v*v*(3-2*v);}
function eo(v){v=cl(v);return 1-Math.pow(1-v,3);}
function rr(x,X,Y,w,h,r){x.beginPath();x.moveTo(X+r,Y);x.arcTo(X+w,Y,X+w,Y+h,r);x.arcTo(X+w,Y+h,X,Y+h,r);x.arcTo(X,Y+h,X,Y,r);x.arcTo(X,Y,X+w,Y,r);x.closePath();}
function font(x,w,sz){x.font=w+" "+sz+"px "+FONT;}
function fit(x,s,w,sz,max){font(x,w,sz);var m=x.measureText(s).width;if(m>max){sz=sz*max/m;font(x,w,sz);}return sz;}
function shuffle(n,seed,skip){var a=[],i;for(i=0;i<n;i++)if(!skip||skip.indexOf(i)<0)a.push(i);for(i=a.length-1;i>0;i--){seed=(seed*9301+49297)%233280;var j=Math.floor(seed/233280*(i+1)),t=a[i];a[i]=a[j];a[j]=t;}return a;}

function drawCompact(x,W,H,progress){
 const pad=3, base=H-pad, height=H-2*pad, half=(W-2*pad)/2, center=W/2;
 for(let band=0;band<3;band++){
  const a=band/3,b=(band+1)/3;
  x.beginPath();x.moveTo(center-half*(1-a),base-height*a);
  x.lineTo(center+half*(1-a),base-height*a);
  x.lineTo(center+half*(1-b),base-height*b);
  x.lineTo(center-half*(1-b),base-height*b);x.closePath();
  x.fillStyle=['#b8b7b0','#d0cfc9','#deddd7'][band];x.fill();
  if(band===activeBand){x.save();x.clip();x.fillStyle=C.brand;x.globalAlpha=.35+.65*progress;x.fillRect(0,0,W,H);x.restore();}
 }
 x.strokeStyle=C.bg;x.lineWidth=3;
 [1/3,2/3].forEach(f=>{x.beginPath();x.moveTo(center-half*(1-f)-1,base-height*f);x.lineTo(center+half*(1-f)+1,base-height*f);x.stroke();});
}
function stage(id,END,draw,opt){
 const cv=document.getElementById(id),x=cv.getContext('2d'),button=document.getElementById('pyramid-toggle');
 let W=0,H=0,elapsed=0,last=null,raf=0,visible=false,paused=false,manual=false;
 function render(){if(!W)return;if(compact.matches){x.clearRect(0,0,W,H);drawCompact(x,W,H,preference.matches?1:e(elapsed/.45));return;}const t=preference.matches&&!manual?9.8:Math.min(elapsed,END);x.clearRect(0,0,W,H);x.save();x.globalAlpha=elapsed>END+1?1-e((elapsed-END-1)/.7):1;draw(x,W,H,t);x.restore();if(opt.tick)opt.tick(t);}
 function sync(){const stopped=paused||(preference.matches&&!manual);button.setAttribute('aria-label',(stopped?'Play':'Pause')+' pyramid animation');button.querySelector('use').setAttribute('href',stopped?'#play':'#pause');}
 function canRun(){return visible&&!document.hidden&&(compact.matches?elapsed<.45&&!preference.matches:!paused&&(!preference.matches||manual));}
 function frame(ms){raf=0;if(!canRun()){last=null;return;}if(last!==null)elapsed+=Math.min((ms-last)/1000,.1)*(opt.speed||1);last=ms;if(elapsed>END+1.7)elapsed=0;render();raf=requestAnimationFrame(frame);}
 function update(){cancelAnimationFrame(raf);raf=0;last=null;sync();render();if(canRun())raf=requestAnimationFrame(frame);}
 function size(){const r=cv.getBoundingClientRect(),d=Math.min(devicePixelRatio||1,2);W=r.width;H=r.height;cv.width=Math.round(W*d);cv.height=Math.round(H*d);x.setTransform(d,0,0,d,0,0);render();}
 new ResizeObserver(size).observe(cv);
 new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;update();},{threshold:0}).observe(cv);
 button.addEventListener('click',()=>{if(preference.matches&&!manual){manual=true;paused=false;elapsed=0;}else paused=!paused;update();});
 preference.addEventListener('change',()=>{manual=false;update();});
 document.addEventListener('layerchange',event=>{activeBand=event.detail.band;if(compact.matches){elapsed=0;update();}});
 compact.addEventListener('change',()=>{elapsed=0;size();update();});
 document.addEventListener('visibilitychange',update);size();sync();
}
var BANDS=[{a:0,b:1/3,g:"#e2e1dc",f:"#b8b7b0",s:.6,e:1.8},{a:1/3,b:2/3,g:"#dcdbd6",f:"#a6a59e",s:2.0,e:3.2},{a:2/3,b:1,g:"#d6d5cf",f:"#94938c",s:3.4,e:4.6}];
var T_UP=5.6,T_UPE=7.8,T_SIDE=8.6,T_MORPH=10.4,T_FILL=10.8,T_FULL=16.2,END_L=17.2,ordCache={},NL=1;
function upP(t){return e((t-T_UP)/(T_UPE-T_UP));}
function startAt(k,n){return T_FILL+(T_FULL-T_FILL-.6)*Math.pow(k/n,.55);}
stage("cv-learn",END_L,function(x,W,H,t){
  var B=Math.min(W,H*1.2),lw=Math.max(2.5,B/170),x0=lw/2+1,cx=x0+B/2,yb=H,i;
  if(x0+B>W)B=W-x0*2,cx=x0+B/2;
  var m=e((t-T_MORPH)/1.6);
  function hw(f){return B/2*(1-f)+B/2*m*f;}function y(f){return yb-H*f;}
  for(i=0;i<3;i++){var q=BANDS[i];x.save();x.beginPath();x.moveTo(cx-hw(q.a),y(q.a));x.lineTo(cx+hw(q.a),y(q.a));x.lineTo(cx+hw(q.b),y(q.b));x.lineTo(cx-hw(q.b),y(q.b));x.closePath();x.fillStyle=q.g;x.fill();x.clip();
    var p=e((t-q.s)/(q.e-q.s));if(p>0){var top=y(q.a)-(y(q.a)-y(q.b))*p;x.fillStyle=q.f;x.fillRect(0,top,W,y(q.a)-top);}x.restore();}
  var N=Math.max(140,Math.min(420,Math.round(B/1.5)));NL=N;if(!ordCache[N])ordCache[N]=shuffle(N,7,[Math.round(N*.5)]);var ord=ordCache[N],cw=B/N;
  x.save();x.beginPath();x.moveTo(cx-hw(0),y(0));x.lineTo(cx+hw(0),y(0));x.lineTo(cx+hw(1),y(1)-.01);x.lineTo(cx-hw(1),y(1)-.01);x.closePath();x.clip();
  x.fillStyle=C.brand;var up=upP(t);
  if(up>0)x.fillRect(cx-lw/2,yb-H*up,lw,H*up);
  for(var k=0;k<ord.length;k++){var q2=e((t-startAt(k,ord.length))/.5);if(q2>0)x.fillRect(x0+cw*ord[k],yb-H*q2,cw*.62,H*q2);}
  var ov=e((t-T_FULL)/.9);if(ov>0){x.globalAlpha=ov;x.fillRect(x0,0,B,H);x.globalAlpha=1;}
  x.restore();
  var sep=1-e((t-T_MORPH+.4)/1);if(sep>0){x.globalAlpha=sep;x.strokeStyle=C.bg;x.lineWidth=4;[1/3,2/3].forEach(function(f){x.beginPath();x.moveTo(cx-hw(f)-3,y(f));x.lineTo(cx+hw(f)+3,y(f));x.stroke();});x.globalAlpha=1;}
  if(up>0&&up<1){x.fillStyle=C.brand;x.beginPath();x.arc(cx,yb-H*up,lw*1.9,0,7);x.fill();}
  var L1=e((t-T_SIDE)/1.1),L2=e((t-T_SIDE-.5)/1.1);x.strokeStyle=C.brand;x.lineWidth=lw;x.lineCap="round";
  if(L1>0){x.beginPath();x.moveTo(cx-hw(0),y(0));x.lineTo(cx-hw(L1),y(L1));x.stroke();}
  if(L2>0){x.beginPath();x.moveTo(cx+hw(0),y(0));x.lineTo(cx+hw(L2),y(L2));x.stroke();}
  if(W-B>40){x.lineWidth=1.5;x.lineCap="butt";
    for(i=0;i<3;i++){var f=(i+.5)/3,a=e((t-BANDS[i].e+.4)/.6);if(a<=0)continue;var sx=cx+hw(f)+10;x.strokeStyle=up>=f?C.brand:"#bdbcb5";x.beginPath();x.moveTo(sx,y(f));x.lineTo(sx+(W-sx)*a,y(f));x.stroke();}}
},{speed:1.2,tick:function(t){
  var up=upP(t);
  rows.forEach(function(r){var i=+r.dataset.band;r.classList.toggle("on",t>=BANDS[i].s+.5);r.classList.toggle("hit",up>=(i+.5)/3);});

}});
})();
