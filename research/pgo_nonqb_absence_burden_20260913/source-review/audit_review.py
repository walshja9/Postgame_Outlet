"""Source evidence only: reuse prior audit, inspect actual retained metadata, never fit."""
from collections import Counter
import csv
from datetime import timedelta
import hashlib
import io
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0,str(ROOT))
from research.pgo_nonqb_validation_20260912 import audit_sources as prior
import pyreadr

old = ROOT/'research/pgo_nonqb_validation_20260912/report02'
manifest = json.loads((old/'manifest.json').read_bytes())
for name,pin in manifest['files'].items():
    raw=(old/name).read_bytes()
    assert len(raw)==pin['bytes'] and hashlib.sha256(raw).hexdigest()==pin['sha256']
admission=json.loads((old/'source-admission.json').read_bytes())
old_receipt=json.loads((old/'receipt.json').read_bytes())
assert len(old_receipt['inputs'])==63
historical_sources={}
for name,pin in admission['source_selection'].items():
    raw=Path(pin['path']).read_bytes()
    assert len(raw)==pin['bytes'] and hashlib.sha256(raw).hexdigest()==pin['sha256']
    historical_sources[name]=pin
games=prior.ch._load_games({('schedule_results',None):Path(historical_sources['schedule_results']['path'])})
games_by_id={g['game_id']:g for g in games}
receipts={}
for path in sorted(HERE.glob('*/receipt.json')):
    raw=path.with_name('response.bin').read_bytes(); receipt=json.loads(path.read_bytes())
    assert len(raw)==receipt['bytes'] and hashlib.sha256(raw).hexdigest()==receipt['sha256']
    receipts[path.parent.name]={k:receipt[k] for k in ('requested_url','started_at','completed_at','status','bytes','sha256','error')}
release=json.loads((HERE/'injuries-release/response.bin').read_bytes())
bot=json.loads((HERE/'injurybot-release/response.bin').read_bytes())
assets=[]
for item in bot['assets']:
    if not item['name'].endswith('.rds'): continue
    gid=item['name'][:-4]; game=games_by_id.get(gid)
    row={k:item.get(k) for k in ('id','name','created_at','updated_at','digest','size','browser_download_url')}
    if game:
        cutoff=game['kickoff_dt']-timedelta(minutes=60)
        row.update(kickoff=game['kickoff_dt'].isoformat(),lock_at=cutoff.isoformat(),
                   asset_updated_pre_t60=prior.stamp(item['updated_at'])<cutoff,
                   asset_updated_after_kickoff=prior.stamp(item['updated_at'])>=game['kickoff_dt'])
    else:row['outside_pinned_REG_schedule']=True
    assets.append(row)
csv_raw=(HERE/'injuries-2025-current/response.bin').read_bytes()
reader=csv.DictReader(io.StringIO(csv_raw.decode('utf-8'))); fields=reader.fieldnames; rows=list(reader)
regular=[row for row in rows if row['game_type']=='REG']
samples={}
for name in ('injurybot-sample-early','injurybot-sample-late'):
    frame=next(iter(pyreadr.read_r(str(HERE/name/'response.bin')).values()))
    # Preserve provider missingness as JSON null, not an inferred healthy designation.
    records=frame.astype(object).where(frame.notna(),None).to_dict(orient='records')
    samples[name]=dict(rows=len(frame),columns=list(frame.columns),teams=sorted(frame['team'].unique()),records=records)
result=dict(status='BLOCKED FOR FITTING; HISTORICAL SOURCE ADMISSION NOT ESTABLISHED',
            prior_report_manifest_sha256=hashlib.sha256((old/'manifest.json').read_bytes()).hexdigest(),
            prior_verified_inputs_reused=63,prior_report_members_reverified=4,historical_raw_sources_reverified=14,
            prior_identity_qualification=admission['identity_qualification'],historical_sources=historical_sources,
            prior_season_admission=admission['seasons'],source_receipts=receipts,
            official_release=dict(tag=release['tag_name'],created_at=release['created_at'],published_at=release['published_at'],immutable=release.get('immutable'),
                                  assets=[{k:a.get(k) for k in ('id','name','created_at','updated_at','digest','size','browser_download_url')}
                                          for a in release['assets'] if a['name'].endswith('.csv')]),
            current_2025=dict(bytes=len(csv_raw),sha256=hashlib.sha256(csv_raw).hexdigest(),fields=fields,total_rows=len(rows),
                              regular_rows=len(regular),regular_populations=dict(Counter(prior.population(row) for row in regular)),
                              date_modified_column_present='date_modified' in fields,
                              identity_with_pinned_source=hashlib.sha256(csv_raw).hexdigest()==historical_sources['injury_reports:2025']['sha256']),
            injurybot=dict(release_created_at=bot['created_at'],release_published_at=bot['published_at'],immutable=bot.get('immutable'),
                           assets=len(assets),pinned_REG_assets=sum('kickoff' in a for a in assets),
                           updated_pre_t60=sum(a.get('asset_updated_pre_t60',False) for a in assets),
                           updated_at_or_after_t60=sum('kickoff' in a and not a['asset_updated_pre_t60'] for a in assets),
                           updated_after_kickoff=sum(a.get('asset_updated_after_kickoff',False) for a in assets),
                           asset_metadata=assets,samples=samples),
            newly_admitted_historical_games=0,feature_walks=0,model_fits=0,forecast_writes=0,
            conclusions=['Current standard season releases do not preserve the required pregame source versions.',
                         'The actual 2025 release exists despite stale availability documentation, but has no date_modified column and was released retrospectively in September 2026.',
                         'Some injurybot 2024 per-game assets have pre-T60 repository timestamps; current mutable assets lack historical digest/source receipt and retained revision chain.',
                         'Sample injurybot tables omit stable player IDs, exact dates/update clocks and report-completeness attestations; absent game designations remain unknown.',
                         'A bounded historical subset might be investigated only with independent original-byte publication proof, complete official team reports and stable-identity resolution; it is not admitted by this review.'])
with (HERE/'audit01.json').open('x',encoding='utf-8') as handle:json.dump(result,handle,indent=2,sort_keys=True,allow_nan=False)
print(json.dumps({k:result[k] for k in ('status','prior_verified_inputs_reused','historical_raw_sources_reverified','current_2025','newly_admitted_historical_games')},indent=2))
print('injurybot_counts',json.dumps({k:v for k,v in result['injurybot'].items() if k not in ('asset_metadata','samples')},indent=2))
