#!/usr/bin/env python3
"""GC02 / Fieldwork LAB project-native, exact-payload release QA candidate.

No network calls and no git writes. Nonzero exit on failed controls. The web
browser launches only against a run-scoped local HTTP server or injected bytes.
This is a *project-local fixture*, not a GC common-kernel implementation.
"""
import argparse
import functools
import hashlib
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
from urllib.parse import urlparse, unquote

HTML = ('index.html', 'notes.html', 'investigations/higress.html',
        'investigations/rocketmq.html', 'evidence/higress-4788.html',
        'evidence/rocketmq-10911.html')
PUBLIC_REMOTE_HOSTS = {'github.com'}
BANNED_TAGS = {'form', 'iframe', 'object', 'embed'}
BANNED_LOCAL_TERMS = ('OFFLINE STUDY', 'LOCAL-ONLY PROTOTYPE', 'C:\\USERS\\',
                      '/HOME/NATURE/', 'INTERNAL GOVERNANCE ZIP')


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.attrs = []
        self.ids = set()
        self.tags = []
        self.headings = []
        self.html_lang = None
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append(tag)
        self.attrs.append((tag, a))
        if tag == 'html': self.html_lang = a.get('lang')
        if tag == 'h1': self.headings.append(tag)
        if a.get('id'): self.ids.add(a['id'])


def sha(b): return hashlib.sha256(b).hexdigest()


def check_static(site, manifest, checks):
    approved = manifest['site_files']
    actual = {p.relative_to(site).as_posix() for p in site.rglob('*') if p.is_file()}
    expected = set(approved)
    if actual != expected:
        raise AssertionError(f'PUBLIC_SURFACE_IDENTITY extra={sorted(actual-expected)} missing={sorted(expected-actual)}')
    for rel, info in approved.items():
        b=(site/rel).read_bytes()
        if len(b)!=info['size'] or sha(b)!=info['sha256']:
            raise AssertionError('EXACT_BYTES_FAIL '+rel)
    if (site/'.nojekyll').stat().st_size!=0: raise AssertionError('NOJEKYLL_NOT_EMPTY')
    checks.append({'gate':'EXACT_NINE_PUBLIC_FILES','result':'PASS', 'objects':len(expected)})

    pages={}
    for rel in HTML:
        t=(site/rel).read_text(encoding='utf-8')
        p=PageParser();p.feed(t);pages[rel]=p
        if p.html_lang!='en' or p.tags.count('main')!=1 or p.tags.count('nav')!=1 or len(p.headings)!=1:
            raise AssertionError('HTML_SEMANTICS '+rel)
        if any(tag in BANNED_TAGS for tag in p.tags): raise AssertionError('UNAUTHORIZED_ACTIVE_ELEMENT '+rel)
        for banned in BANNED_LOCAL_TERMS:
            if banned in t.upper(): raise AssertionError(f'LEAK_OR_STALE_LABEL {rel}: {banned}')
        if 'Cannot prove' not in t and 'cannot prove' not in t.lower() and rel.startswith('evidence/'):
            raise AssertionError('EVIDENCE_BOUNDARY_ABSENT '+rel)
        if rel.startswith('investigations/') and 'What this does not prove' not in t:
            raise AssertionError('CASE_BOUNDARY_ABSENT '+rel)
    checks.append({'gate':'SIX_PAGE_SEMANTICS_AND_BOUNDARIES','result':'PASS','pages':len(HTML)})

    local_refs=0; external=0
    for rel,p in pages.items():
        for tag,a in p.attrs:
            for key in ('href','src'):
                if key not in a:continue
                value=a[key].strip()
                if value.startswith(('javascript:', 'data:', 'http:','//')):raise AssertionError('UNSAFE_REFERENCE '+rel+':'+value)
                parsed=urlparse(value)
                if parsed.scheme=='https':
                    if parsed.hostname not in PUBLIC_REMOTE_HOSTS:raise AssertionError('EXTERNAL_HOST_NOT_ALLOWED '+value)
                    if tag=='script': raise AssertionError('THIRD_PARTY_SCRIPT '+rel)
                    if a.get('target')=='_blank' and not {'noopener','noreferrer'}.issubset(set(a.get('rel','').split())):
                        raise AssertionError('UNSAFE_EXTERNAL_LINK '+rel+':'+value)
                    external+=1;continue
                if parsed.scheme: raise AssertionError('INVALID_SCHEME '+rel+':'+value)
                target_rel=unquote(parsed.path)
                target=(site/rel).parent/target_rel if target_rel else (site/rel)
                target=target.resolve()
                if not target.is_relative_to(site.resolve()) or not target.is_file():
                    raise AssertionError('MISSING_INTERNAL_TARGET '+rel+':'+value)
                if parsed.fragment:
                    dest=target.relative_to(site).as_posix()
                    if dest.endswith('.html') and unquote(parsed.fragment) not in pages[dest].ids:
                        raise AssertionError('MISSING_ANCHOR '+rel+':'+value)
                local_refs+=1
    checks.append({'gate':'INTERNAL_AND_APPROVED_EXTERNAL_REFERENCES','result':'PASS','local_refs':local_refs,'external_refs':external})

    urls='\n'.join((site/p).read_text(encoding='utf-8') for p in HTML)
    for u in manifest['approved_public_sources']:
        if u not in urls: raise AssertionError('PUBLIC_PROVENANCE_MISSING '+u)
    checks.append({'gate':'EXACT_PUBLIC_SOURCE_POINTERS','result':'PASS','sources':len(manifest['approved_public_sources'])})
    j=(site/'assets/site.js').read_text(encoding='utf-8')
    for code in ('C0','C1','C2'):
        if not re.search(r'\b'+code+r':\{[^}]*count:\'451 / 451\'',j):
            raise AssertionError('EXACT_SCENARIO_COUNT '+code)
    if '452 / 452' in j: raise AssertionError('KNOWN_AUDIT_NARRATIVE_CONFLICT')
    node=subprocess.run(['node','--check',str(site/'assets/site.js')],capture_output=True,text=True)
    if node.returncode:raise AssertionError('JS_SYNTAX '+node.stderr[:200])
    checks.append({'gate':'SOURCE_CONSISTENCY_AND_JS_SYNTAX','result':'PASS','C0_C1_C2':'451/451'})


def runtime_checks(site, mode, checks):
    try: from playwright.sync_api import sync_playwright
    except ImportError as e: raise AssertionError('PLAYWRIGHT_REQUIRED '+str(e))
    css=(site/'assets/site.css').read_text(encoding='utf-8')
    js=(site/'assets/site.js').read_text(encoding='utf-8')
    httpd=None
    if mode=='http':
        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self,*_):pass
        h=functools.partial(QuietHandler,directory=str(site))
        httpd=ThreadingHTTPServer(('127.0.0.1',0),h)
        threading.Thread(target=httpd.serve_forever,daemon=True).start()
    rendered=0
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True, executable_path=os.environ.get('FIELDWORK_CHROMIUM_EXECUTABLE') or None, args=['--no-sandbox','--disable-dev-shm-usage'])
            try:
                for rel in HTML:
                    for width,height in ((1440,900),(768,900),(390,780)):
                        context=browser.new_context(viewport={'width':width,'height':height}, color_scheme='dark')
                        page=context.new_page();errs=[]
                        page.on('pageerror',lambda err:errs.append(str(err)))
                        if mode=='http':
                            url=f'http://127.0.0.1:{httpd.server_port}/{rel}'
                            response=page.goto(url,wait_until='load',timeout=12000)
                            if not response or response.status!=200:raise AssertionError('LOCAL_HTTP_BAD_STATUS '+rel)
                        else:
                            html=(site/rel).read_text(encoding='utf-8')
                            html=re.sub(r'<link rel="stylesheet" href="[^"]+">','',html)
                            html=re.sub(r'<script defer src="[^"]+"></script>','',html)
                            page.set_content(html,wait_until='domcontentloaded')
                            page.add_style_tag(content=css)
                            page.add_script_tag(content=js)
                        page.evaluate('()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
                        def ensure_layout():
                            if not page.evaluate('document.documentElement.scrollWidth <= innerWidth+1'):
                                raise AssertionError(f'HORIZONTAL_OVERFLOW {rel} {width}')
                            if errs:raise AssertionError(f'RUNTIME_JS_ERROR {rel} {errs}')
                        ensure_layout()
                        # Color or state must not obscure semantic limits.
                        s='.primary-action' if rel=='index.html' else '.limit-object' if rel.startswith('investigations/') else '.proof-object.cannot' if rel.startswith('evidence/') else '.note-boundary'
                        loc=page.locator(s)
                        if loc.count():
                            bg=loc.first.evaluate('e=>getComputedStyle(e).backgroundColor')
                            if bg not in ('rgba(0, 0, 0, 0)','transparent'):
                                raise AssertionError(f'VISUAL_SURFACE_FILLED {rel} {s}: {bg}')
                        if rel=='investigations/rocketmq.html':
                            for code,wk,pl in [('C0','true','true'),('C1','false','true'),('C2','true','false')]:
                                page.locator('[data-scenario="'+code+'"]').click()
                                if page.locator('[data-field="worker"]').inner_text()!=wk or page.locator('[data-field="pool"]').inner_text()!=pl or page.locator('[data-field="count"]').inner_text().strip()!='451 / 451':
                                    raise AssertionError('SCENARIO_DATA_MISMATCH '+code)
                                if page.locator('[data-scenario][aria-pressed="true"]').count()!=1:
                                    raise AssertionError('SCENARIO_ARIA_STATE '+code)
                        if rel=='index.html':
                            # Stable, single active nav owner; forward and reverse samples.
                            sections=['work','method','scope'];ordered=[]
                            max_y=page.evaluate('document.documentElement.scrollHeight-innerHeight')
                            for y in list(range(0,max(0,max_y)+1, max(30,int(max_y/15) or 30)))+[max(0,max_y)]:
                                page.evaluate('(v)=>scrollTo(0,v)',y)
                                page.evaluate('()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
                                active=page.locator('nav a[aria-current="location"]')
                                if active.count()!=1:raise AssertionError(f'NAV_UNIQUE_FAIL forward {width} {y}')
                                text=active.first.inner_text().strip().lower()
                                if text not in sections:raise AssertionError('NAV_UNKNOWN '+text)
                                if text != (ordered[-1] if ordered else ''):ordered.append(text)
                            if ordered != sections: raise AssertionError(f'NAV_FORWARD_ORDER {width}: {ordered}')
                            reversed_order=[]
                            for y in list(range(max(0,max_y),-1,-max(30,int(max_y/15) or 30)))+[0]:
                                page.evaluate('(v)=>scrollTo(0,v)',y)
                                page.evaluate('()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
                                active=page.locator('nav a[aria-current="location"]')
                                if active.count()!=1:raise AssertionError(f'NAV_UNIQUE_FAIL reverse {width} {y}')
                                text=active.first.inner_text().strip().lower()
                                if text != (reversed_order[-1] if reversed_order else ''):reversed_order.append(text)
                            if reversed_order != list(reversed(sections)):
                                raise AssertionError(f'NAV_REVERSE_ORDER {width}: {reversed_order}')
                            # Header height unchanged when active links change.
                            heights=page.evaluate('()=>[...document.querySelectorAll(".site-header")].map(x=>x.getBoundingClientRect().height)')
                            if len(heights)!=1 or not 0<heights[0]<200:raise AssertionError('HEADER_GEOMETRY_FAIL')
                        # Theme toggle works, and semantic backgrounds remain unfilled in both modes.
                        theme=page.locator('[data-theme-toggle]')
                        if theme.count()!=1:raise AssertionError('THEME_CONTROL_MISSING')
                        theme.click()
                        if page.evaluate('document.documentElement.dataset.theme')!='light':raise AssertionError('LIGHT_THEME_FAILED')
                        if loc.count():
                            bg=loc.first.evaluate('e=>getComputedStyle(e).backgroundColor')
                            if bg not in ('rgba(0, 0, 0, 0)','transparent'):raise AssertionError(f'LIGHT_THEME_FILLED {rel} {s}: {bg}')
                        theme.click()
                        if page.evaluate('document.documentElement.dataset.theme')!='dark':raise AssertionError('DARK_THEME_FAILED')
                        ensure_layout()
                        rendered+=2
                        context.close()
                checks.append({'gate':'BROWSER_RUNTIME_SEMANTICS','result':'PASS','rendered_theme_cases':rendered,'viewports':['1440x900','768x900','390x780'],'source_mode':mode})
            finally:browser.close()
    finally:
        if httpd:
            httpd.shutdown();httpd.server_close()


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--site',required=True,type=Path)
    ap.add_argument('--manifest',required=True,type=Path)
    ap.add_argument('--runtime',choices=('injected','http','skip'),default='http')
    ap.add_argument('--out',required=True,type=Path)
    opts=ap.parse_args();opts.out.parent.mkdir(parents=True,exist_ok=True)
    checks=[];result={'gate_id':'GC02-FIELDWORK-RC2-EXACT-BYTES-AND-E2E','runtime_mode':opts.runtime,'status':'FAIL_CLOSED','checks':checks}
    try:
        site=opts.site.resolve();manifest=json.loads(opts.manifest.read_text())
        check_static(site,manifest,checks)
        if opts.runtime=='skip':
            result['status']='STATIC_ONLY_NOT_RELEASE_ACCEPTANCE'
        else:
            runtime_checks(site,opts.runtime,checks)
            result['status']='PASS_BOUNDED' if opts.runtime=='injected' else 'PASS_HTTP_RUNTIME'
    except Exception as e:
        result['error']={'type':type(e).__name__,'message':str(e)}
    finally:
        opts.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['status'].startswith('PASS_') else 2


if __name__=='__main__':sys.exit(main())
