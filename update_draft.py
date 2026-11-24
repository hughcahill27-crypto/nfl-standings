import json,re,urllib.request
from bs4 import BeautifulSoup
from pathlib import Path
url='https://thesportswire.net/nfl/draft-order/2027/'
req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
s=BeautifulSoup(urllib.request.urlopen(req,timeout=40).read(),'html.parser')
rows=[]
for tr in s.select('tr'):
 c=[' '.join(x.stripped_strings) for x in tr.find_all('td',recursive=False)]
 if len(c)!=8 or not c[0].isdigit():continue
 m=re.search(r'Projected pick\s*(\d+)',c[3],re.I); t=re.match(r'([A-Z]{2,3})\s+([\w ]+?)(?:\s*Held by|$)',c[1]);
 if not m or not t:continue
 rows.append([int(c[0]),int(m[1]),t[1],float(c[4]),*c[5:8]])
assert len(rows)==32 and len({r[1] for r in rows})==32 and len({r[2] for r in rows})==32, 'Incomplete source; keeping previous data'
updated=next((x.strip() for x in s.stripped_strings if x.strip().startswith('Updated ')), '')
assert updated,'Missing source timestamp'
Path('draft-data.json').write_text(json.dumps({'updated':updated,'rows':rows},indent=2))
