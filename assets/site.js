"use strict";
(function(){
 const toggle=document.querySelector('[data-nav-toggle]');
 const nav=document.getElementById('site-nav');
 if(toggle && nav){
  toggle.addEventListener('click',()=>{const opened=toggle.getAttribute('aria-expanded')==='true';toggle.setAttribute('aria-expanded',String(!opened));nav.classList.toggle('open',!opened);});
 }
 const cases={
  C0:{worker:'true',pool:'true',count:'451 / 451',note:'Both switches enabled'},
  C1:{worker:'false',pool:'true',count:'451 / 451',note:'Worker group disabled'},
  C2:{worker:'true',pool:'false',count:'451 / 451',note:'Pooled allocator disabled'}
 };
 const buttons=[...document.querySelectorAll('[data-scenario]')];
 const container=document.querySelector('.scenario-data');
 if(buttons.length && container){
   function choose(code){const data=cases[code];if(!data)return;
     buttons.forEach(btn=>{let isSelected=btn.dataset.scenario===code;btn.setAttribute('aria-pressed',String(isSelected));btn.classList.toggle('selected',isSelected)});
     for(const key of ['worker','pool','count','note']){let elem=container.querySelector('[data-field="'+key+'"]');if(elem)elem.textContent=data[key]}
   }
   buttons.forEach(btn=>btn.addEventListener('click',()=>choose(btn.dataset.scenario)));
   choose('C0');
 }
 // Appearance switch: dark is the default; preference is held in this browser.
 const root=document.documentElement;
 const themeControl=document.querySelector('[data-theme-toggle]');
 const themeLabel=document.querySelector('[data-theme-label]');
 function setTheme(theme){
   const dark=theme!=='light';
   root.dataset.theme=dark?'dark':'light';
   if(themeControl){
     themeControl.setAttribute('aria-label',dark?'Switch to light appearance':'Switch to dark appearance');
     themeControl.setAttribute('aria-pressed',String(dark));
   }
   if(themeLabel) themeLabel.textContent=dark?'Light':'Dark';
 }
 let chosen='dark';
 try {const previous=localStorage.getItem('fieldwork-theme-preference');if(previous==='light'||previous==='dark')chosen=previous;}catch(_){}
 setTheme(chosen);
 if(themeControl) themeControl.addEventListener('click',()=>{
   const next=root.dataset.theme==='dark'?'light':'dark';
   setTheme(next);
   try{localStorage.setItem('fieldwork-theme-preference',next);}catch(_){}
 });
 // Navigation state is derived from ONE reading position, never from an eager
 // click highlight or from a special end-of-page override.
 // Instant fragment jumps avoid showing transient tabs during smooth scrolling.
 const sections=['work','method','scope'].map(id=>document.getElementById(id)).filter(Boolean);
 if(sections.length===3 && nav){
   const links=sections.map(section=>nav.querySelector('a[href="#'+section.id+'"]'));
   function highlight(id){
     links.forEach((link,i)=>{
       if(!link)return;
       if(sections[i].id===id)link.setAttribute('aria-current','location');
       else link.removeAttribute('aria-current');
     });
   }
   function readPosition(){
     const header=document.querySelector('.site-header');
     const headerHeight=header?header.getBoundingClientRect().height:68;
     // 46% down the viewport follows what the reader is actually inspecting.
     // This also allows the final (short) Scope section to become active at
     // the page bottom without forcing an unrelated selection.
     const readingLine=Math.max(headerHeight+16, window.innerHeight*0.46);
     let active=sections[0].id;
     for(const section of sections){
       if(section.getBoundingClientRect().top<=readingLine) active=section.id;
     }
     highlight(active);
   }
   let framePending=false;
   function schedule(){
     if(framePending)return;
     framePending=true;
     requestAnimationFrame(()=>{framePending=false;readPosition();});
   }
   window.addEventListener('scroll',schedule,{passive:true});
   window.addEventListener('resize',schedule);
   window.addEventListener('hashchange',schedule);
   window.addEventListener('pageshow',schedule);
   links.forEach(link=>{
     if(!link)return;
     link.addEventListener('click',()=>{
       // A collapsed mobile menu must not remain above the target anchor.
       if(toggle&&nav.classList.contains('open')){
         nav.classList.remove('open');
         toggle.setAttribute('aria-expanded','false');
       }
       // Native same-document fragment navigation moves instantly; scroll
       // and hashchange then compute the one consistent active link.
       requestAnimationFrame(schedule);
     });
   });
   schedule();
 }
})();
