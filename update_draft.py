import json,re,urllib.request
from datetime import datetime, timezone
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
text = ' '.join(s.stripped_strings)
match = re.search(r'(?:Last\s+)?Updated\s*:?\s*((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}(?:\s*[·|–-]?\s*\d{1,2}:\d{2}\s*(?:AM|PM)?\s*(?:[ECMP][SD]?T)?)?)', text, re.I)
retrieved = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
updated = 'Updated ' + match.group(1).strip() if match else 'Source date unavailable; retrieved ' + retrieved
print(f'Validated {len(rows)} picks. {updated}')
Path('draft-data.json').write_text(json.dumps({'updated':updated,'retrieved_at':retrieved,'rows':rows},indent=2))
