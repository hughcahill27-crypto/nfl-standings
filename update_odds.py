"""Record observed pregame ESPN odds. Never overwrite older samples."""
import concurrent.futures as cf
import datetime as dt
import json
import math
import pathlib
import re
import urllib.request

BASE='https://site.api.espn.com/apis/site/v2/sports/football/nfl/'
ROOT=pathlib.Path('odds-history')
YEAR=2026

def get(path):
    req=urllib.request.Request(BASE+path, headers={'User-Agent':'Gridiron27/1.0','Accept':'application/json'})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)

def number(x):
    try:
        v=float(x)
        return v if math.isfinite(v) else None
    except (TypeError,ValueError):
        return None

def alias(x):
    return {'LA':'LAR','WSH':'WAS','JAX':'JAC'}.get(x,x)

def competition(e):
    return (e.get('competitions') or [{}])[0]

def state(e):
    return (competition(e).get('status') or e.get('status') or {}).get('type',{}).get('state')

def team(e,loc):
    return next((x.get('team',{}).get('abbreviation','') for x in competition(e).get('competitors',[]) if x.get('homeAway')==loc),'')

def sample(e):
    if state(e)!='pre' or dt.datetime.fromisoformat(e['date'].replace('Z','+00:00')) <= dt.datetime.now(dt.timezone.utc):
        return None
    try:
        d=get('summary?event='+str(e['id']))
    except Exception as exc:
        print('Summary unavailable',e['id'],str(exc)); d={}
    # A game may have started while the summary was loading.
    if dt.datetime.fromisoformat(e['date'].replace('Z','+00:00')) <= dt.datetime.now(dt.timezone.utc):
        return None
    o=(competition(e).get('odds') or d.get('pickcenter') or [{}])[0]
    detail=str(o.get('details') or '').strip()
    a,h=team(e,'away'),team(e,'home')
    m=re.fullmatch(r'([A-Z0-9]+)\s*[-−]\s*(\d+(?:\.\d+)?)',detail,re.I)
    spread=None
    if m and alias(m[1].upper()) in (alias(a),alias(h)):
        spread=float(m[2])*(1 if alias(m[1].upper())==alias(h) else -1)
    elif re.fullmatch(r'PK|PICK.?EM|EVEN',detail,re.I):
        spread=0
    total=number(o.get('overUnder'))
    if total is None or total<=0: total=None
    home=number((d.get('predictor') or {}).get('homeTeam',{}).get('gameProjection'))
    if home is not None and not 0<=home<=100: home=None
    if all(v is None for v in (spread,total,home)): return None
    return str(e['id']), {'away':a,'home':h,'kickoff':e['date']}, {'at':dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),'spread':spread,'total':total,'home':home,'provider':(o.get('provider') or {}).get('name') or 'ESPN feed'}

def main():
    current=get('scoreboard?limit=100')
    if int(current.get('season',{}).get('year',0))!=YEAR: raise SystemExit('No matching season; not writing data')
    w=int(current.get('week',{}).get('number',0))
    if not 1<=w<=18: raise SystemExit('Outside regular season')
    ROOT.mkdir(exist_ok=True)
    for week in range(w,min(18,w+1)+1):
        feed=get(f'scoreboard?dates={YEAR}&seasontype=2&week={week}&limit=100')
        if int(feed.get('season',{}).get('year',0))!=YEAR or int(feed.get('week',{}).get('number',0))!=week: raise RuntimeError('Unexpected ESPN week')
        path=ROOT/f'{YEAR}-week-{week}.json'
        data=json.loads(path.read_text()) if path.exists() else {'season':YEAR,'week':week,'games':{}}
        events=[e for e in feed.get('events',[]) if state(e)=='pre']
        with cf.ThreadPoolExecutor(max_workers=4) as pool:
            samples=list(pool.map(sample,events))
        count=0
        for row in samples:
            if row is None: continue
            game,meta,obs=row
            entry=data['games'].setdefault(game,{**meta,'samples':[]})
            entry['samples'].append(obs); count+=1
        if count:
            temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,separators=(',',':'))+'\n');temp.replace(path)
        print(f'Week {week}: {count} pregame observations recorded')
if __name__=='__main__': main()
