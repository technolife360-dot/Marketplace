#!/usr/bin/env python3
"""Publish already reviewed 96px artwork to the public R2 catalogue prefix.

Dry-run by default. No database updates, original deletions or runtime crawling.
Use --env-file for an ignored local credential file; credentials are never logged.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def validate_image(body):
    from PIL import Image
    if len(body)>24*1024:
        raise ValueError('Thumbnail exceeds 24 KiB')
    with Image.open(io.BytesIO(body)) as image:
        if image.format!='WEBP' or image.size!=(96,96):
            raise ValueError('Expected a 96 by 96 WebP thumbnail')
        image.verify()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir',type=Path,required=True)
    parser.add_argument('--env-file',type=Path)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if args.env_file:
        for line in args.env_file.read_text().splitlines():
            if '=' not in line or line.lstrip().startswith('#'):continue
            key,value=line.split('=',1)
            if not key.strip().startswith('R2_'):continue
            try:value=json.loads(value)
            except ValueError:value=value.strip().strip("\"'")
            os.environ[key.strip()]=str(value).strip()
    import storage_r2
    games=json.loads((ROOT/'data/seller-catalog.json').read_text())['games']
    sources=json.loads((args.source_dir/'sources.json').read_text())
    images=[]
    for game in games:
        key=game['id'];source=sources[key]
        if source['kind']=='needs_review':raise ValueError('Unreviewed image: '+key)
        body=(args.source_dir/(key+'.webp')).read_bytes();validate_image(body)
        digest=hashlib.sha256(body).hexdigest()
        if source['sha256']!=digest:raise ValueError('Image digest mismatch: '+key)
        images.append((key,body,source))
    print(f'Validated {len(images)} thumbnails; {sum(len(body) for _,body,_ in images):,} bytes total',flush=True)
    if not args.apply:return
    if not storage_r2.is_configured():raise ValueError('R2 settings are incomplete')
    manifest_path=ROOT/'data/seller-catalog-images.json'
    checkpoint=args.source_dir/'published.json'
    existing=json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    if checkpoint.exists():existing.update(json.loads(checkpoint.read_text()))
    manifest={}
    storage_r2._client()  # Construct the S3 client once before sharing it with workers.
    def publish(image):
        key,body,source=image
        prior=existing.get(key,{})
        url=prior.get('url') if prior.get('sha256')==source['sha256'] else None
        if not url:url=storage_r2.put_catalog_art(key,body)
        return key,{**source,'url':url}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for n,(key,value) in enumerate(pool.map(publish,images),1):
            manifest[key]=value
            if n%50==0:
                checkpoint.write_text(json.dumps(manifest,ensure_ascii=False))
                print(f'Published {n}/{len(images)}',flush=True)
    temporary=manifest_path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(manifest_path)
    print('Catalogue image manifest saved.',flush=True)


if __name__=='__main__':main()
