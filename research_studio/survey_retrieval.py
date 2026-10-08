"""Bounded host-only scholarly retrieval. Model sandboxes remain network-free.

Provider documentation: arXiv API user manual and Crossref REST API. Only the
listed official endpoints are fetched; publisher links remain metadata. Every
response preserves its original bytes separately from any extracted text.
"""
from __future__ import annotations
import ipaddress
import json
import re
import selectors
import os
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from .util import require, PMRSError, sha, now

MAX_QUERIES=4
MAX_RESULTS=10
MAX_BYTES=16*1024*1024
MAX_METADATA_BYTES=2*1024*1024
TIMEOUT=15
MAX_RETRIES=1
USER_AGENT='Pure-Math-Research-Studio/4.1 (bounded scholarly literature survey)'
_ARXIV_ID=re.compile(r'(?:\d{4}\.\d{4,5}|[a-z][a-z.\-]+/\d{7})(?:v[1-9]\d*)?\Z')
_lock=threading.Lock()
_last_request={}


def validate_url(url, *, resolve=True):
    require(isinstance(url,str) and len(url)<=4096,'SURVEY_ADDRESS_REJECTED','Bounded official provider URL required')
    parsed=urllib.parse.urlsplit(url)
    require(parsed.scheme=='https' and not parsed.username and not parsed.password and parsed.port in (None,443)
            and not parsed.fragment,'SURVEY_ADDRESS_REJECTED','HTTPS without credentials, custom ports or fragments is required')
    host=parsed.hostname
    require(host in {'export.arxiv.org','arxiv.org','api.crossref.org'},'SURVEY_ADDRESS_REJECTED','Only configured scholarly provider hosts are permitted')
    path=urllib.parse.unquote(parsed.path)
    allowed=(host=='api.crossref.org' and path=='/works' or host in {'export.arxiv.org','arxiv.org'} and path=='/api/query')
    if host in {'arxiv.org','export.arxiv.org'} and path.startswith('/pdf/'):
        key=path[5:];key=key[:-4] if key.endswith('.pdf') else key
        allowed=bool(_ARXIV_ID.fullmatch(key)) and not parsed.query
    require(allowed and '..' not in path and '\\' not in path,'SURVEY_ADDRESS_REJECTED','Endpoint or document identifier is outside the provider contract')
    if resolve:
        proxy_ranges=(ipaddress.ip_network('198.18.0.0/15'),ipaddress.ip_network('2001:2::/48'))
        def permitted(address):
            value=ipaddress.ip_address(address)
            # System fake-IP resolvers are common with a transparent HTTPS
            # proxy. Only the exact official hostname is allowed, and normal
            # TLS hostname/certificate validation remains mandatory.
            return value.is_global or any(value.version==net.version and value in net for net in proxy_ranges)
        addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
        require(bool(addresses) and all(permitted(row[4][0]) for row in addresses),
                'SURVEY_ADDRESS_REJECTED','Provider address resolves to a non-public network')
    return url


class _Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        hops=getattr(req,'survey_redirects',0)+1
        require(hops<=3,'SURVEY_ADDRESS_REJECTED','Redirect limit exceeded')
        validate_url(newurl)
        target=super().redirect_request(req,fp,code,msg,headers,newurl)
        if target is not None:target.survey_redirects=hops
        return target


def fetch(url, *, maximum=MAX_METADATA_BYTES, accepted_types=()):
    attempts=[]
    for attempt in range(MAX_RETRIES+1):
        started=now()
        try:
            validate_url(url)
            host=urllib.parse.urlsplit(url).hostname
            if host in {'arxiv.org','export.arxiv.org'}:host='arxiv.org'
            with _lock:
                # arXiv asks clients to leave at least three seconds between calls.
                delay=(3.1 if 'arxiv.org' in host else 0.25)-(time.monotonic()-_last_request.get(host,0))
                if delay>0:time.sleep(delay)
                _last_request[host]=time.monotonic()
            request=urllib.request.Request(url,headers={'User-Agent':USER_AGENT,'Accept-Encoding':'identity'})
            with urllib.request.build_opener(_Redirects).open(request,timeout=TIMEOUT) as response:
                final=validate_url(response.geturl());content_type=response.headers.get_content_type()
                require(not accepted_types or content_type in accepted_types,'SURVEY_MEDIA_REJECTED','Unexpected provider content type')
                size=response.headers.get('Content-Length')
                require(size is None or int(size)<=maximum,'SURVEY_SIZE_LIMIT','Response exceeds the download bound')
                chunks=[];total=0;deadline=time.monotonic()+TIMEOUT
                while True:
                    require(time.monotonic()<=deadline,'SURVEY_TIMEOUT','Response exceeded the bounded read time')
                    block=response.read1(min(65536,maximum+1-total))
                    if not block:break
                    chunks.append(block);total+=len(block)
                    require(total<=maximum,'SURVEY_SIZE_LIMIT','Response exceeds the download bound')
                data=b''.join(chunks)
            attempts.append({'at':started,'outcome':'SUCCESS','bytes':len(data)})
            return {'status':'SUCCESS','url':final,'requested_url':url,'content_type':content_type,'raw':data,'sha256':sha(data),'attempts':attempts}
        except urllib.error.HTTPError as exc:
            status='RATE_LIMITED' if exc.code==429 else 'FETCH_FAILED'
            attempts.append({'at':started,'outcome':status,'http_status':exc.code})
            if exc.code not in {429,500,502,503,504} or attempt==MAX_RETRIES:break
        except (PMRSError,ValueError,OSError,urllib.error.URLError) as exc:
            status='FETCH_FAILED';attempts.append({'at':started,'outcome':status,'reason':getattr(exc,'code',type(exc).__name__)})
            # Security and size failures cannot be retried as a transport error.
            if isinstance(exc,PMRSError) or attempt==MAX_RETRIES:break
        time.sleep(0.5)
    return {'status':status,'url':url,'raw':None,'attempts':attempts,'reason':attempts[-1]}


def extract_pdf(raw):
    require(raw.startswith(b'%PDF-'),'SURVEY_MEDIA_REJECTED','PDF signature is missing')
    try:
        with tempfile.TemporaryDirectory(prefix='pmrs-survey-pdf-') as folder:
            original=Path(folder)/'source.pdf';original.write_bytes(raw)
            process=subprocess.Popen(['pdftotext','-layout',str(original),'-'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            parts=[];sizes={'stdout':0,'stderr':0};deadline=time.monotonic()+30
            try:
                with selectors.DefaultSelector() as poll:
                    poll.register(process.stdout,selectors.EVENT_READ,'stdout');poll.register(process.stderr,selectors.EVENT_READ,'stderr')
                    while poll.get_map():
                        require(time.monotonic()<deadline,'SURVEY_EXTRACTION_FAILED','PDF extraction exceeded 30 seconds')
                        for key,_ in poll.select(timeout=min(0.2,max(0,deadline-time.monotonic()))):
                            data=os.read(key.fileobj.fileno(),65536)
                            if not data:poll.unregister(key.fileobj);continue
                            sizes[key.data]+=len(data)
                            require(sizes[key.data]<=(MAX_BYTES if key.data=='stdout' else 65536),'SURVEY_EXTRACTION_FAILED','PDF extraction output exceeded the bounded stream limit')
                            if key.data=='stdout':parts.append(data)
                process.wait(timeout=max(0.01,deadline-time.monotonic()))
                require(process.returncode==0,'SURVEY_EXTRACTION_FAILED','PDF text extraction failed')
            finally:
                if process.poll() is None:process.kill();process.wait()
                process.stdout.close();process.stderr.close()
            text=b''.join(parts).decode('utf-8');require(bool(text.strip()),'SURVEY_EXTRACTION_FAILED','No readable text was extracted')
            return {'status':'TEXT_EXTRACTED','text':text.encode('utf-8'),'text_sha256':sha(text.encode('utf-8')),
                    'original_sha256':sha(raw),'method':'pdftotext-layout','limitation':'Extracted text is a derivative; verify original page and formula layout when needed.'}
    except (OSError,subprocess.TimeoutExpired,UnicodeError,PMRSError) as exc:
        return {'status':'EXTRACTION_FAILED','text':None,'original_sha256':sha(raw),'reason':getattr(exc,'code',type(exc).__name__)}


class ArxivProvider:
    name='arxiv'
    def search(self,query,limit=5):
        require(isinstance(query,str) and 0<len(query.strip())<=1500 and type(limit) is int and 1<=limit<=MAX_RESULTS,
                'SURVEY_QUERY_INVALID','A bounded nonempty query and result count are required')
        url='https://export.arxiv.org/api/query?'+urllib.parse.urlencode({'search_query':query,'start':0,'max_results':limit,'sortBy':'relevance'})
        result=fetch(url,accepted_types=('application/atom+xml','application/xml','text/xml'))
        result['candidates']=[]
        if result['status']!='SUCCESS':return result
        try:
            require(b'<!DOCTYPE' not in result['raw'].upper() and b'<!ENTITY' not in result['raw'].upper(),'SURVEY_PROVIDER_INVALID','XML entity declarations are forbidden')
            tree=ET.fromstring(result['raw']);ns={'a':'http://www.w3.org/2005/Atom'}
            for entry in tree.findall('a:entry',ns)[:limit]:
                uri=entry.findtext('a:id','',ns);identifier=urllib.parse.urlsplit(uri).path.removeprefix('/abs/')
                require(bool(_ARXIV_ID.fullmatch(identifier)),'SURVEY_PROVIDER_INVALID','Invalid arXiv result identifier')
                result['candidates'].append({'candidate_id':identifier,'title':entry.findtext('a:title','',ns).strip(),
                    'authors':[v.findtext('a:name','',ns) for v in entry.findall('a:author',ns)],
                    'version':identifier,'url':'https://arxiv.org/abs/'+identifier,'download_url':'https://arxiv.org/pdf/'+identifier,
                    'abstract':entry.findtext('a:summary','',ns).strip(),'publication_status':'PREPRINT',
                    'access_status':'METADATA_ONLY','provider':'arxiv'})
        except (ET.ParseError,PMRSError) as exc:
            result.update(status='PROVIDER_RESPONSE_INVALID',reason=getattr(exc,'code',type(exc).__name__),candidates=[])
        return result

    def acquire(self,candidate):
        identifier=candidate.get('candidate_id','')
        require(bool(_ARXIV_ID.fullmatch(identifier)),'SURVEY_ADDRESS_REJECTED','An exact provider candidate is required')
        result=fetch('https://arxiv.org/pdf/'+identifier,maximum=MAX_BYTES,accepted_types=('application/pdf','application/octet-stream'))
        if result['status']=='SUCCESS':
            if not result['raw'].startswith(b'%PDF-'):result.update(status='MEDIA_REJECTED',reason='PDF signature is missing')
            else:result['extraction']=extract_pdf(result['raw'])
        return result


class CrossrefProvider:
    name='crossref'
    def search(self,query,limit=5):
        require(isinstance(query,str) and 0<len(query.strip())<=1500 and type(limit) is int and 1<=limit<=MAX_RESULTS,
                'SURVEY_QUERY_INVALID','A bounded nonempty query and result count are required')
        url='https://api.crossref.org/works?'+urllib.parse.urlencode({'query.bibliographic':query,'rows':limit})
        result=fetch(url,accepted_types=('application/json',));result['candidates']=[]
        if result['status']!='SUCCESS':return result
        try:
            records=json.loads(result['raw'])['message']['items']
            for item in records[:limit]:
                doi=item['DOI']
                result['candidates'].append({'candidate_id':doi,'title':' '.join(item.get('title',[])),
                    'authors':[' '.join((a.get('given',''),a.get('family',''))).strip() for a in item.get('author',[])],
                    'version':'crossref-metadata:'+str(item.get('indexed',{}).get('date-time','unspecified')),
                    'url':'https://doi.org/'+urllib.parse.quote(doi,safe='/'),'download_url':None,
                    'abstract':item.get('abstract',''),'publication_status':item.get('type','UNVERIFIED'),
                    'access_status':'METADATA_ONLY','provider':'crossref'})
        except (ValueError,KeyError,TypeError) as exc:result.update(status='PROVIDER_RESPONSE_INVALID',reason=type(exc).__name__,candidates=[])
        return result
    def acquire(self,candidate):
        return {'status':'FULL_TEXT_UNAVAILABLE','url':candidate.get('url'),'raw':None,'attempts':[],
                'reason':'Crossref supplies bibliographic metadata. Publisher URLs are not fetched by this provider.'}


class MockProvider:
    """Deterministic test provider; admission rejects it in real projects."""
    name='mock'
    def __init__(self,responses=None,materials=None):self.responses=responses or {};self.materials=materials or {};self.calls=[]
    def search(self,query,limit=5):
        from copy import deepcopy
        self.calls.append(('search',query));row=deepcopy(self.responses.get(query,{'status':'SUCCESS','candidates':[]}))
        row.setdefault('raw',json.dumps(row,sort_keys=True).encode());row.setdefault('url','https://example.invalid/synthetic-query');row.setdefault('attempts',[{'outcome':row['status']}]);row['synthetic_test_only']=True
        return row
    def acquire(self,candidate):
        from copy import deepcopy
        self.calls.append(('acquire',candidate['candidate_id']))
        return deepcopy(self.materials.get(candidate['candidate_id'],{'status':'FULL_TEXT_UNAVAILABLE','raw':None,'attempts':[],'reason':'Explicit synthetic fixture has no full text.'}))


def provider(name):
    require(name in {'arxiv','crossref'},'SURVEY_PROVIDER_UNKNOWN','Choose arxiv or crossref')
    return {'arxiv':ArxivProvider,'crossref':CrossrefProvider}[name]()
