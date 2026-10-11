#!/usr/bin/env python3
"""Test fail-closed behavior against deliberately corrupted disposable copies."""
import argparse,hashlib,json,shutil,subprocess,tempfile,sys
from pathlib import Path

def mutate_manifest(base,p,manifest):
 b=(base/p).read_bytes();manifest['site_files'][p]={'size':len(b),'sha256':hashlib.sha256(b).hexdigest()}

def main():
 cli=argparse.ArgumentParser();cli.add_argument('--site',required=True,type=Path);cli.add_argument('--manifest',required=True,type=Path);cli.add_argument('--out',required=True,type=Path);a=cli.parse_args()
 script=Path(__file__).with_name('site_gate.py');summary=[]
 with tempfile.TemporaryDirectory(prefix='gc02-release-neg-') as td:
  for test in ('CSS_BYTE_TAMPER','TENTH_PUBLIC_FILE','BAD_C0_COUNT_MANIFEST_UPDATED','BROKEN_LOCAL_LINK_MANIFEST_UPDATED','VISUAL_FILLED_LIMIT_MANIFEST_UPDATED'):
   site=Path(td)/test;shutil.copytree(a.site,site)
   manifest=json.loads(a.manifest.read_text())
   if test=='CSS_BYTE_TAMPER':
    with (site/'assets/site.css').open('a') as w:w.write('\n/* corrupted */\n')
   elif test=='TENTH_PUBLIC_FILE':(site/'extra.txt').write_text('NOT ALLOWED')
   elif test=='BAD_C0_COUNT_MANIFEST_UPDATED':
    f=site/'assets/site.js';f.write_text(f.read_text().replace("C0:{worker:'true',pool:'true',count:'451 / 451'","C0:{worker:'true',pool:'true',count:'452 / 452'"))
    mutate_manifest(site,'assets/site.js',manifest)
   elif test=='BROKEN_LOCAL_LINK_MANIFEST_UPDATED':
    f=site/'index.html';f.write_text(f.read_text().replace('investigations/higress.html','investigations/missing.html'))
    mutate_manifest(site,'index.html',manifest)
   elif test=='VISUAL_FILLED_LIMIT_MANIFEST_UPDATED':
    f=site/'assets/site.css';f.write_text(f.read_text()+'\nhtml[data-theme="dark"] .limit-object {background:rgb(90,0,0)!important;}\n')
    mutate_manifest(site,'assets/site.css',manifest)
   m=Path(td)/(test+'.json');m.write_text(json.dumps(manifest))
   output=Path(td)/(test+'.result.json')
   runtime='injected' if test.startswith('VISUAL_') else 'skip'
   env=__import__('os').environ.copy()
   # Use the caller's browser selection; on GitHub Runner, Playwright resolves its managed Chromium.
   proc=subprocess.run([sys.executable,str(script),'--site',str(site),'--manifest',str(m),'--runtime',runtime,'--out',str(output)],capture_output=True,text=True,env=env,timeout=90)
   result=json.loads(output.read_text())
   expected_error={'CSS_BYTE_TAMPER':'EXACT_BYTES_FAIL', 'TENTH_PUBLIC_FILE':'PUBLIC_SURFACE_IDENTITY', 'BAD_C0_COUNT_MANIFEST_UPDATED':'EXACT_SCENARIO_COUNT', 'BROKEN_LOCAL_LINK_MANIFEST_UPDATED':'MISSING_INTERNAL_TARGET', 'VISUAL_FILLED_LIMIT_MANIFEST_UPDATED':'VISUAL_SURFACE_FILLED'}[test]
   actual_error=result.get('error',{}).get('message','')
   if proc.returncode==0 or result['status']!='FAIL_CLOSED' or expected_error not in actual_error:
    raise AssertionError(f'Negative did not fail for expected cause: {test}: {proc.returncode} {result}')
   summary.append({'test':test,'result':'PASS_STOP_CONFIRMED','error':result.get('error',{}).get('message')})
 a.out.parent.mkdir(parents=True,exist_ok=True)
 a.out.write_text(json.dumps({'classification':'NEGATIVE_CONTROL_PASS','negative_tests':summary},indent=2)+'\n')
 print(json.dumps({'classification':'NEGATIVE_CONTROL_PASS','count':len(summary)},indent=2));return 0

if __name__=='__main__':sys.exit(main())
