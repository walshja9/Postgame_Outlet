"""Exclusive bounded HTTP evidence capture for this source review only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import http.client
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request

OUT = Path(__file__).resolve().parent
SOURCES = {
    'dictionary': 'https://nflreadr.nflverse.com/articles/dictionary_injuries.html',
    'availability': 'https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html',
    'loader': 'https://raw.githubusercontent.com/nflverse/nflreadr/main/R/load_injuries.R',
    'injuries-release': 'https://api.github.com/repos/nflverse/nflverse-data/releases/tags/injuries',
    'injurybot-release': 'https://api.github.com/repos/nflverse/nflverse-injurybot/releases/tags/injuries_2024',
    'injurybot-tree': 'https://api.github.com/repos/nflverse/nflverse-injurybot/git/trees/main?recursive=1',
}
def now(): return datetime.now(timezone.utc).isoformat()
def capture(name):
    target = OUT/name; target.mkdir(exist_ok=False)
    url = SOURCES[name]; body = bytearray()
    receipt = dict(requested_url=url,started_at=now(),status=None,headers=[],redirects=[],error=None)
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            receipt['redirects'].append(dict(url=req.full_url,status=code,headers=list(headers.items()),target=newurl))
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    try:
        req = urllib.request.Request(url,headers={'User-Agent':'PGO-source-admission-review/1.0','Accept-Encoding':'identity'})
        try: response = urllib.request.build_opener(Redirect()).open(req,timeout=30)
        except urllib.error.HTTPError as error: response = error
        with response:
            receipt.update(status=response.status,headers=list(response.headers.items()),final_url=response.url)
            while True:
                try: chunk=response.read(1024*1024)
                except http.client.IncompleteRead as error: body.extend(error.partial); raise
                if not chunk: break
                body.extend(chunk)
    except Exception as error: receipt['error']=dict(type=type(error).__name__,message=str(error))
    receipt.update(completed_at=now(),bytes=len(body),sha256=hashlib.sha256(body).hexdigest())
    with (target/'response.bin').open('xb') as handle: handle.write(body)
    with (target/'receipt.json').open('x',encoding='utf-8') as handle: json.dump(receipt,handle,indent=2)
    return {k:receipt[k] for k in ('requested_url','started_at','completed_at','status','bytes','sha256','error')}
if __name__ == '__main__':
    with ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(capture,sys.argv[1:] or SOURCES): print(json.dumps(result),flush=True)
