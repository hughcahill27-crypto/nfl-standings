"""Gridiron 27 independent archive and Jets data updater.
Historical game results and box scores can be backfilled; dated projections cannot.
"""
import concurrent.futures as cf
import datetime as dt
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen
from bs4 import BeautifulSoup

BASE='https://site.api.espn.com/apis/site/v2/sports/football/nfl/'
ROOT=Path('gridiron-archive')
NOW=dt.datetime.now(dt.timezone.utc)
STAMP=NOW.isoformat()

def fetch(url):
    with urlopen(Request(url,headers={'User-Agent':'Gridiron27/1.0 (personal NFL statistics dashboard)','Accept':'*/*'}),timeout=45) as r:
        return r.read()

def get(url): return json.loads(fetch(url))

def write(path,data):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n');tmp.replace(p)

def read(path,default=None):
    p=Path(path)
    return json.loads(p.read_text()) if p.exists() else default

def final(e):
    t=e.get('status',{}).get('type',{})
    return bool(t.get('completed')) and t.get('state')=='post' and len(e.get('competitions',[{}])[0].get('competitors',[]))==2

def sides(e):return e['competitions'][0]['competitors']

def record(games):
    out={}
    for e in games:
        a,b=sides(e)
        for x,y in ((a,b),(b,a)):
            k=x['team']['abbreviation'];r=out.setdefault(k,{'wins':0,'losses':0,'ties':0,'points_for':0,'points_against':0})
            p,q=int(x['score']),int(y['score']);r['wins' if p>q else 'losses' if p<q else 'ties']+=1;r['points_for']+=p;r['points_against']+=q
    return out

def week(year,w):
    d=get(BASE+f'scoreboard?dates={year}&seasontype=2&week={w}&limit=100')
    if d.get('season',{}).get('year')!=year or d['season'].get('type')!=2 or d.get('week',{}).get('number')!=w:raise ValueError(f'Wrong season/week: {year}/{w}')
    es=d.get('events',[])
    return [e for e in es if e.get('season',{}).get('year',year)==year and e.get('season',{}).get('type',2)==2 and e.get('week',{}).get('number',w)==w]

def box(e):
    p=ROOT/'boxscores'/f'{e["id"]}.json'
    if p.exists():return str(p)
    d=get(BASE+f'summary?event={e["id"]}')
    b=d.get('boxscore',{})
    if len(b.get('teams',[]))!=2 or not b.get('players'):raise ValueError(f'Incomplete box score {e["id"]}')
    write(p,{'event':e['id'],'retrieved':STAMP,'boxscore':b,'leaders':d.get('leaders',[]),'scoringPlays':d.get('scoringPlays',[])})
    return str(p)

def capture_projections(year):
    latest=read(ROOT/'projection-index.json',{'entries':[]})
    payload={k:read(k) for k in ['draft-data.json','playoff-data.json'] if Path(k).exists()}
    if not payload:return
    last=latest['entries'][-1] if latest['entries'] else None
    if last and read(last['path'],{}).get('data')==payload:return
    p=ROOT/str(year)/'projections'/(NOW.strftime('%Y%m%dT%H%M%SZ')+'.json')
    write(p,{'season':year,'retrieved':STAMP,'data':payload})
    latest['entries'].append({'season':year,'retrieved':STAMP,'path':str(p)})
    write(ROOT/'projection-index.json',latest)

def archive():
    d=get(BASE+'scoreboard?limit=100');year=int(d['season']['year']);capture_projections(year)
    index=read(ROOT/'index.json',{'entries':[]});existing={(x['season'],x['week']):x for x in index['entries']}
    accum=[]
    for w in range(1,19):
        key=(year,w)
        if key in existing:
            old=read(existing[key]['path']);accum.extend(old['games']);continue
        es=week(year,w)
        if not es or not all(final(e) for e in es):break
        with cf.ThreadPoolExecutor(max_workers=4) as pool:paths=list(pool.map(box,es))
        accum.extend(es);p=ROOT/str(year)/f'week-{w:02}.json'
        write(p,{'season':year,'week':w,'retrieved':STAMP,'source':'ESPN','games':es,'records':record(accum),'boxscores':paths,'note':'Reconstructed from final scores; historical projections stored separately only from actual retrieval dates.'})
        existing[key]={'season':year,'week':w,'path':str(p),'retrieved':STAMP}
        index['entries']=sorted(existing.values(),key=lambda x:(x['season'],x['week']),reverse=True);write(ROOT/'index.json',index)
    if not (ROOT/'index.json').exists():write(ROOT/'index.json',index)
    # postseason snapshots, only when all games in that round have finished
    for r in range(1,6):
        p=ROOT/str(year)/f'postseason-{r}.json'
        if p.exists():continue
        try:
            a=get(BASE+f'scoreboard?dates={year}&seasontype=3&week={r}&limit=100')
            es=a.get('events',[])
            if a.get('season',{}).get('year')!=year or a.get('season',{}).get('type')!=3 or a.get('week',{}).get('number')!=r or not es or not all(final(e) for e in es):continue
            write(p,{'season':year,'round':r,'games':es,'retrieved':STAMP})
        except Exception as ex:print('Postseason:',ex)

def finance():
    url='https://overthecap.com/salary-cap/new-york-jets'
    soup=BeautifulSoup(fetch(url),'html.parser'); candidates=[]
    for t in soup.find_all('table'):
        head=t.find('thead');cells=head.find_all('th') if head else []
        headers=[c.get_text(' ',strip=True) for c in cells]
        cap=next((i for i,h in enumerate(headers) if h.lower() in ('cap number','cap hit','cap charge')),None)
        if cap is None:continue
        rows=[]
        for tr in t.select('tbody tr'):
            cs=tr.find_all('td',recursive=False)
            if len(cs)<=cap:continue
            player=cs[0].get_text(' ',strip=True);value=cs[cap].get_text(' ',strip=True)
            if not player or not re.fullmatch(r'\$[\d,]+',value):continue
            rows.append((int(re.sub(r'\D','',value)),[player,value]))
        if len(rows)>=10:candidates.append(rows)
    if not candidates:raise ValueError('Could not validate Over the Cap table')
    rows=sorted(candidates[0],key=lambda x:x[0],reverse=True)
    write('gridiron-jets-finance.json',{'source':url,'retrieved':STAMP,'headers':['Player','Current listed cap number'],'rows':[r for _,r in rows]})

def history():
    url='https://www.pro-football-reference.com/teams/nyj/'
    soup=BeautifulSoup(fetch(url),'html.parser'); rows=[]
    for tr in soup.select('tr'):
        def val(k):
            x=tr.find(attrs={'data-stat':k});return x.get_text(' ',strip=True) if x else ''
        y=val('year_id')
        if not re.fullmatch(r'\d{4}',y):continue
        w,l,t=val('wins'),val('losses'),val('ties')
        if not w.isdigit() or not l.isdigit():continue
        rows.append([int(y),w,l,t or '0',val('playoff_result'),val('coaches')])
    if len(set(r[0] for r in rows))<60:raise ValueError('Historical records incomplete')
    write('gridiron-jets-history.json',{'source':url,'retrieved':STAMP,'headers':['Season','W','L','T','Playoffs','Coach'],'rows':sorted(rows,reverse=True)})

if __name__=='__main__':
    errors=[]
    for fn in (archive,finance,history):
        try:fn()
        except Exception as e:errors.append(f'{fn.__name__}: {e}');print('WARNING:',errors[-1])
    if errors:print('Some sources unavailable; existing successful snapshots retained:',*errors,sep='\n')
    if not (ROOT/'index.json').exists():raise SystemExit('No archive index created; inspect source errors')
