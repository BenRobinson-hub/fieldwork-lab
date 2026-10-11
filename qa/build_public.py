#!/usr/bin/env python3
"""Copy only the exact approved nine public files into a clean release directory.

No GitHub/network access and no change to source. Fail-closed on any hash drift.
"""
import argparse,hashlib,json,shutil,sys
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True)
    p.add_argument('--dest',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True)
    a=p.parse_args(); src=a.source.resolve();dest=a.dest.resolve()
    if dest==src or src in dest.parents: # dest inside src allowed if ignored? no: fail
        raise ValueError('STAGING_DESTINATION_MUST_BE_SEPARATE_FROM_SOURCE')
    approved=json.loads(a.manifest.read_text())['site_files'];allow=set(approved)
    if len(allow)!=9:raise ValueError('PUBLIC_FILE_COUNT_MUST_BE_NINE')
    # Repository working tree may contain .github and qa, but public payload must be exactly the allowlist.
    for rel,info in approved.items():
        f=(src/rel).resolve()
        if not f.is_relative_to(src) or not f.is_file() or f.is_symlink():raise ValueError('SOURCE_FILE_INVALID '+rel)
        buf=f.read_bytes()
        if len(buf)!=info['size'] or hashlib.sha256(buf).hexdigest()!=info['sha256']:
            raise ValueError('SOURCE_FILE_IDENTITY_INVALID '+rel)
    if dest.exists():shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for rel in sorted(allow):
        output=dest/rel;output.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src/rel,output)
    if len([f for f in dest.rglob('*') if f.is_file()])!=9:raise AssertionError('STAGING_PUBLIC_COUNT_FAIL')
    print(json.dumps({'status':'PUBLIC_STAGING_EXACT_NINE_PASS','source':str(src),'dest':str(dest),'files':sorted(allow)}))
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except Exception as e:
        print(json.dumps({'status':'STOP_PUBLIC_STAGING_FAILED','error':str(e)}),file=sys.stderr)
        sys.exit(2)
