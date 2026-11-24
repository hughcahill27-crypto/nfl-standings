import json, re, datetime, urllib.request
from zoneinfo import ZoneInfo
from pathlib import Path
from bs4 import BeautifulSoup
URL='https://www.sports-king.com/nfl-playoff-odds.php'
TEAMS=dict(zip('BUF SF JAX KC CIN DEN DET MIN CHI NYG PIT NE SEA CAR CLE LA TB GB HOU DAL WSH ATL LV NO BAL PHI NYJ IND MIA TEN LAC ARI'.split(),'Bills 49ers Jaguars Chiefs Bengals Broncos Lions Vikings Bears Giants Steelers Patriots Seahawks Panthers Browns Rams Buccaneers Packers Texans Cowboys Commanders Falcons Raiders Saints Ravens Eagles Jets Colts Dolphins Titans Chargers Cardinals'.split()))
def parse(html):
    soup=BeautifulSoup(html,'html.parser')
    for table in soup.find_all('table'):
        rows=[[c.get_text(' ',strip=True) for c in r.find_all(['th','td'])] for r in table.find_all('tr')]
        if not rows: continue
        headers=[x.lower() for x in rows[0]]
        if not all(x in headers for x in ['team','playoffs','division','no. 1 seed']): continue
        out={}
        for row in rows[1:]:
            if len(row)!=len(headers): continue
            name=row[headers.index('team')]
            key=next((k for k,v in TEAMS.items() if name.endswith(v)),None)
            if not key: continue
            vals=[row[headers.index(x)] for x in ['playoffs','division','no. 1 seed']]
            if not all(re.fullmatch(r'[<>]?\d+(?:\.\d+)?%',v) and 0<=float(v.strip('<>%'))<=100 for v in vals): raise ValueError('Invalid probability')
            out[key]=dict(zip(['playoff','division','bye'],vals))
        if len(out)==32: return out, (re.search(r'Updated\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})',soup.get_text(' ',strip=True)) or [None,None])[1]
    raise ValueError('Complete 32-team probability table not found')
def update_archive(data):
    # Use the provider publication date, not the date a stale file was downloaded.
    # The weekly bucket runs Tuesday through Monday (NFL regular season).
    season=2026
    et=ZoneInfo('America/New_York')
    if not data.get('source_date'):
        print('No published date; leaving historical archive unchanged')
        return
    date=datetime.datetime.strptime(data['source_date'],'%B %d, %Y').date()
    now=datetime.datetime.now(et).date()
    if date>now:
        raise ValueError('Projection date is in the future')
    url=f'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={season}&seasontype=2&week=1&limit=100'
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 NFL dashboard'})
    with urllib.request.urlopen(req,timeout=40) as r: week1=json.load(r)
    if int(week1.get('season',{}).get('year',0))!=season or int(week1.get('season',{}).get('type',0))!=2 or int(week1.get('week',{}).get('number',0))!=1:
        raise ValueError('Incorrect season schedule')
    first=min(datetime.datetime.fromisoformat(e['date'].replace('Z','+00:00')).astimezone(et).date() for e in week1['events'])
    start=first-datetime.timedelta(days=(first.weekday()-1)%7)
    week=(date-start).days//7+1
    if not 1<=week<=18:
        print('Projection is outside the regular season; not archiving')
        return
    path=Path('playoff-history.json')
    old=json.loads(path.read_text()) if path.exists() else {'season':season,'source':URL,'weeks':{}}
    if old.get('season')!=season: raise ValueError('Archive belongs to another season')
    prior=old['weeks'].get(str(week),{})
    if prior.get('date','')>date.isoformat(): return
    old['weeks'][str(week)]={'date':date.isoformat(),'retrieved':data['retrieved'],'teams':data['teams']}
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(old,indent=2)+'\n');tmp.replace(path)
    print(f'Archived week {week}, published {date}')

def main():
    path=Path('playoff-data.json')
    req=urllib.request.Request(URL,headers={'User-Agent':'Mozilla/5.0 NFL dashboard'})
    with urllib.request.urlopen(req,timeout=40) as r: teams,date=parse(r.read())
    old=json.loads(path.read_text()) if path.exists() else {}
    previous=old.get('previous',{}) if old.get('teams')==teams else old.get('teams',{})
    data={'source':URL,'source_date':date,'retrieved':datetime.datetime.now(datetime.timezone.utc).isoformat(),'teams':teams,'previous':previous}
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2)+'\n');tmp.replace(path)
    try: update_archive(data)
    except Exception as exc: print('Weekly archive not updated:', exc)
if __name__=='__main__': main()
