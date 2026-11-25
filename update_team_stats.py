"""Collect regular-season team statistics, with conservative source validation."""
import json, re, urllib.request, concurrent.futures
from pathlib import Path
from datetime import datetime, timezone
from bs4 import BeautifulSoup
YEAR=2026
CODES='ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LV LAC LA MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WSH'.split()
IDS=dict(zip(CODES,[22,1,33,2,29,3,4,5,6,7,8,9,34,11,30,12,13,24,14,15,16,17,18,19,20,21,23,26,25,27,10,28]))
CITIES='Arizona|Atlanta|Baltimore|Buffalo|Carolina|Chicago|Cincinnati|Cleveland|Dallas|Denver|Detroit|Green Bay|Houston|Indianapolis|Jacksonville|Kansas City|Las Vegas|L.A. Chargers|L.A. Rams|Miami|Minnesota|New England|New Orleans|N.Y. Giants|N.Y. Jets|Philadelphia|Pittsburgh|Seattle|San Francisco|Tampa Bay|Tennessee|Washington'.split('|')
def key(s): return re.sub(r'[^a-z0-9]','',str(s).lower())
CITY={key(c):k for c,k in zip(CITIES,CODES)}
CITY.update({'losangeleschargers':'LAC','losangelesrams':'LA','newyorkgiants':'NYG','newyorkjets':'NYJ'})
def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; Gridiron27 stats collector)','Accept':'application/json,text/html,*/*'}),timeout=25) as r: return r.read()
def number(v):
    try:
        n=float(str(v).replace(',','').strip());return n if 0<=n<1e7 else None
    except (ValueError,TypeError):return None
# Only explicitly named team metrics; never substitute fumbles lost/recovered for forced.
ALIASES={'ff':{'fumblesforced','forcedfumbles'},'kr':{'yardsperkickreturn','yardsperkickoffreturn','avgkickreturnyards','avgkickoffreturnyards','kickreturnyardsperreturn','kickoffreturnyardsperreturn'},'pr':{'yardsperpuntreturn','avgpuntreturnyards','puntreturnyardsperreturn'}}
def espn(k):
    url=f'https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/{YEAR}/types/2/teams/{IDS[k]}/statistics'
    d=json.loads(fetch(url));cats=d.get('splits',{}).get('categories',[])
    gps=set(); candidates={m:set() for m in ALIASES}
    for cat in cats:
        group=key(cat.get('name',''))
        if any(x in group for x in ['opponent','against','allowed']):continue
        for stat in cat.get('stats',[]):
            name=key(stat.get('name','')); v=number(stat.get('value'))
            if v is None:continue
            if name=='gamesplayed' and v.is_integer() and 0<v<=17:gps.add(int(v))
            for m,aliases in ALIASES.items():
                if name in aliases:candidates[m].add(v)
    if len(gps)!=1:return {}
    gp=gps.pop()
    return {m:{'value':next(iter(vals)),'gp':gp,'source':'ESPN season statistics'} for m,vals in candidates.items() if len(vals)==1 and (m!='ff' or next(iter(vals)).is_integer())}
def cbs(slug,metric,col):
    url=f'https://www.cbssports.com/nfl/stats/team/team/{slug}/nfl/regular/'
    soup=BeautifulSoup(fetch(url),'html.parser')
    if not soup.title or not re.search(r'2026(?:\s*[-–]\s*27)?',soup.title.get_text()):raise ValueError('CBS season not confirmed')
    for table in soup.find_all('table'):
        rows={}
        for tr in table.select('tr'):
            cells=tr.find_all('td',recursive=False)
            if len(cells)<=col:continue
            a=cells[0].find('a'); name=key(a.get_text(' ',strip=True) if a else cells[0].get_text(' ',strip=True)); k=CITY.get(name)
            if not k:continue
            gp=number(cells[1].get_text(strip=True));v=number(cells[col].get_text(strip=True))
            if gp is None or not gp.is_integer() or not 0<gp<=17 or v is None:continue
            if metric=='ff' and not v.is_integer():continue
            rows[k]={'value':v,'gp':int(gp),'source':'CBS Sports season statistics'}
        if len(rows)>=28:return rows
    raise ValueError('CBS table incomplete or changed')
def main():
    teams={k:{} for k in CODES}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        jobs={ex.submit(espn,k):k for k in CODES}
        for f in concurrent.futures.as_completed(jobs):
            k=jobs[f]
            try:
                for m,v in f.result().items():teams[k].setdefault(m,[]).append(v)
            except Exception as e: print('ESPN',k,str(e))
    for slug,m,col in [('turnovers','ff',2),('kick-returns','kr',4),('punt-returns','pr',4)]:
        try:
            for k,v in cbs(slug,m,col).items():teams[k].setdefault(m,[]).append(v)
        except Exception as e:print('CBS',m,str(e))
    path=Path('team-season-stats.json')
    coverage={m:sum(bool(t.get(m)) for t in teams.values()) for m in ALIASES};print('Coverage:',coverage)
    if not any(coverage.values()):raise RuntimeError('No verified statistics; retaining previous file')
    # Preserve previously fetched sources when a provider temporarily fails, with GP validation at display time.
    old=json.loads(path.read_text()) if path.exists() else {}
    if old.get('season')==YEAR:
        for k,t in teams.items():
            for m in ALIASES:
                prev=old.get('teams',{}).get(k,{}).get(m,[])
                existing={x['source'] for x in t.get(m,[])}
                t.setdefault(m,[]).extend(x for x in prev if x.get('source') not in existing)
                t[m].sort(key=lambda x:0 if x['source'].startswith('ESPN') else 1)
    data={'season':YEAR,'seasonType':2,'retrieved':datetime.now(timezone.utc).isoformat(),'teams':teams}
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,separators=(',',':')));tmp.replace(path)
if __name__=='__main__':main()
