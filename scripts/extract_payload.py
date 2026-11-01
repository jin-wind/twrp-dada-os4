"""Extract this phone's full OTA to verified raw images; never contacts a device."""
import bz2, concurrent.futures, hashlib, json, lzma, pathlib, re, struct, threading, time, zipfile

import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--package', type=pathlib.Path, required=True)
parser.add_argument('--output', type=pathlib.Path, required=True)
parser.add_argument('--expected', type=pathlib.Path, required=True)
args = parser.parse_args()
PACKAGE = args.package
OUT = args.output
IMAGES = OUT / 'images'
IMAGES.mkdir(parents=True, exist_ok=True)
expected = json.loads(args.expected.read_text())

def varint(data,pos):
 value=0
 for shift in range(0,70,7):
  b=data[pos];pos+=1;value|=(b&127)<<shift
  if b<128:return value,pos
 raise ValueError('Invalid protobuf')
def fields(data):
 pos=0
 while pos<len(data):
  tag,pos=varint(data,pos);field=tag>>3;wire=tag&7
  if wire==0:value,pos=varint(data,pos)
  elif wire==2:
   n,pos=varint(data,pos);value=data[pos:pos+n];pos+=n
   if len(value)!=n:raise ValueError('Truncated protobuf')
  elif wire in (1,5):
   n=8 if wire==1 else 4;value=data[pos:pos+n];pos+=n
  else:raise ValueError('Unsupported wire type')
  yield field,value

with zipfile.ZipFile(PACKAGE) as z:
 meta=dict(line.split('=',1) for line in z.read('META-INF/com/android/metadata').decode().splitlines() if '=' in line)
 assert meta['pre-device']=='dada' and '/dada_global/' in meta['post-build'] and meta['post-sdk-level']=='37'
 info=z.getinfo('payload.bin');assert info.compress_type==zipfile.ZIP_STORED
 with PACKAGE.open('rb') as f:
  f.seek(info.header_offset);local=f.read(30);assert local[:4]==b'PK\x03\x04'
  name_len,extra_len=struct.unpack_from('<HH',local,26)
  payload_offset=info.header_offset+30+name_len+extra_len
  f.seek(payload_offset);header=f.read(24);magic,major,mlen,slen=struct.unpack('>4sQQI',header)
  assert magic==b'CrAU' and major==2 and mlen<2**20
  manifest=f.read(mlen)
mf=list(fields(manifest));block_size=next((v for k,v in mf if k==3),4096)
assert next((v for k,v in mf if k==12),0)==0
assert not next((v for k,v in mf if k==16),False)
data_start=payload_offset+24+mlen+slen
parts=[];groups=[]
for key,value in mf:
 if key==15:
  for gk,gv in fields(value):
   if gk!=1:continue
   gf=list(fields(gv));groups.append({'name':next(v.decode() for k,v in gf if k==1),'maximum_size':next((v for k,v in gf if k==2),0),'partitions':[v.decode() for k,v in gf if k==3]})
 if key!=13:continue
 pf=list(fields(value));name=next(v.decode() for k,v in pf if k==1)
 assert re.fullmatch(r'[a-z][a-z0-9_-]*',name) and not name.endswith(('_a','_b'))
 assert not any(k==6 for k,v in pf)
 pi=dict(fields(next(v for k,v in pf if k==7)))
 operations=[];cursor=0
 for k,v in pf:
  if k!=8:continue
  opf=list(fields(v));od=dict((k,v) for k,v in opf if k!=6)
  typ=od[1];assert typ in (0,1,8),str(typ)
  extents=[dict(fields(v)) for k,v in opf if k==6]
  length=0
  for extent in extents:
   assert extent[1]*block_size==cursor,(name,cursor,extent)
   n=extent[2]*block_size;cursor+=n;length+=n
  assert 0<length<=32*2**20 and 0<od[3]<=32*2**20
  assert 0<=od.get(2,0) and 24+mlen+slen+od.get(2,0)+od[3]<=info.file_size
  operations.append({'type':typ,'offset':od.get(2,0),'length':od[3],'decoded_length':length,'data_hash':od.get(8)})
 assert cursor==pi[1],(name,cursor,pi[1])
 parts.append({'name':name,'size':pi[1],'sha256':pi[2].hex(),'operations':operations})
parts = [p for p in parts if p['name'] in expected]
assert {p['name'] for p in parts} == set(expected), 'Missing selected payload images'
for part in parts:
 assert part['size'] == expected[part['name']]['size'], part['name'] + ' unexpected size'
 assert part['sha256'] == expected[part['name']]['sha256'], part['name'] + ' unexpected hash'
logical={name for group in groups for name in group['partitions']}
inventory={'package':str(PACKAGE),'version':'OS4.0.0.11.XOCMIXM','device':'dada','target_slot':'b','block_size':block_size,'groups':groups,'total_image_bytes':sum(p['size'] for p in parts),'logical_image_bytes':sum(p['size'] for p in parts if p['name'] in logical),'partitions':[{k:v for k,v in p.items() if k!='operations'}|{'logical':p['name'] in logical,'path':str(IMAGES/(p['name']+'.img'))} for p in parts]}
(OUT/'manifest.json').write_text(json.dumps(inventory,indent=2),encoding='utf-8')
print(json.dumps({'images':str(IMAGES),'partitions':len(parts),'image_bytes':inventory['total_image_bytes'],'logical_image_bytes':inventory['logical_image_bytes'],'groups':groups}),flush=True)
lock=threading.Lock();stop=threading.Event();progress=[0];completed=[];start=time.monotonic()
def extract(part):
 target=IMAGES/(part['name']+'.img');temp=IMAGES/(part['name']+'.img.partial')
 if target.exists():
  digest=hashlib.sha256()
  with target.open('rb') as f:
   for chunk in iter(lambda:f.read(4*2**20),b''):digest.update(chunk)
  if target.stat().st_size!=part['size'] or digest.hexdigest()!=part['sha256']:
   raise RuntimeError('Existing image mismatch: '+part['name'])
  with lock:progress[0]+=part['size']
  return part['name']
 digest=hashlib.sha256()
 with PACKAGE.open('rb') as source,temp.open('wb') as dest:
  for op in part['operations']:
   if stop.is_set():raise RuntimeError('Extraction stopped')
   source.seek(data_start+op['offset']);raw=source.read(op['length'])
   assert len(raw)==op['length']
   if op['data_hash'] is not None:assert hashlib.sha256(raw).digest()==op['data_hash'],part['name']+' compressed data hash'
   decoded=raw if op['type']==0 else bz2.decompress(raw) if op['type']==1 else lzma.decompress(raw)
   assert len(decoded)==op['decoded_length'],part['name']+' decoded length'
   dest.write(decoded);digest.update(decoded)
   with lock:progress[0]+=len(decoded)
  assert dest.tell()==part['size']
 assert digest.hexdigest()==part['sha256'],part['name']+' image hash'
 temp.rename(target)
 return part['name']
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 pending={pool.submit(extract,p) for p in parts}
 last_report=0
 while pending:
  done,pending=concurrent.futures.wait(pending,timeout=5,return_when=concurrent.futures.FIRST_COMPLETED)
  for future in done:
   try:completed.append(future.result())
   except Exception:
    stop.set()
    for other in pending:other.cancel()
    raise
  now=time.monotonic()
  if now-last_report>=10 or not pending:
   with lock:n=progress[0]
   print(json.dumps({'completed_images':len(completed),'percent':round(n/inventory['total_image_bytes']*100,1),'MiB_per_s':round(n/2**20/max(now-start,.1),1),'elapsed_seconds':round(now-start)}),flush=True)
   last_report=now
inventory['extraction_complete']=True;inventory['all_image_hashes_match_payload']=True
(OUT/'manifest.json').write_text(json.dumps(inventory,indent=2),encoding='utf-8')
print('EXTRACTION_COMPLETE: all image hashes match the OTA payload manifest',flush=True)
