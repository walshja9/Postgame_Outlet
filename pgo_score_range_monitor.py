"""Future-only score errors from original durable forecasts; no fitting or ranges."""
from collections import Counter, defaultdict
import copy
import json
import math
from pathlib import Path
import re

import pgo_season as season
from pgo_season import canonical, require, sha, utc
from pgo_season_rollover import index, load_archive, source_bytes

ROOT = Path(__file__).resolve().parent
CHARTER = ROOT/'research/pgo_score_ranges_20260912_collection/charter.md'
IDENTITY = 'pgo-score-error-collection-v1'
FIELDS = (*season.IDENTITY, 'lock_at','issued_at','inputs_as_of','source_edition',
          'margin','total','home_points','away_points','expected_qbs','starter_announcements','blocked_reason')
STORED = ('observations','selections','collection_witnesses','results','schedules')


def _forecast(game):
    require(game.get('game_type') == 'REG' and type(game.get('season')) is int
            and type(game.get('week')) is int and 1 <= game['week'] <= 18,
            'Invalid collection game period')
    match=re.fullmatch(r'(\d{4})_(\d{2})_([A-Z]{2,3})_([A-Z]{2,3})',str(game.get('game_id','')))
    require(match is not None and int(match[1])==game['season'] and int(match[2])==game['week']
            and game['home'] in season.pgo_sources.CURRENT_TEAMS and game['away'] in season.pgo_sources.CURRENT_TEAMS
            and game['home'] != game['away'] and season.pgo_sources.normalize_team(match[3])==game['away']
            and season.pgo_sources.normalize_team(match[4])==game['home'],
            'Invalid collection game identity')
    cutoff = utc(game['kickoff'])-season.timedelta(minutes=60)
    require(utc(game['lock_at']) == cutoff, 'Collection lock is not T-60')
    require(utc(game['inputs_as_of']) <= utc(game['issued_at']) < cutoff, 'Missing or invalid original forecast clocks')
    require(str(game['source_edition']).startswith(f"pgo-postseason-{game['season']}-"), 'Unsupported forecast recipe')
    require(not game.get('blocked_reason'), 'Primary forecast is unavailable')
    for key in ('margin','total','home_points','away_points'):
        require(type(game.get(key)) in (int,float) and math.isfinite(game[key]), 'Missing or invalid forecast '+key)
    require(game['total'] >= 0 and math.isclose(game['home_points']+game['away_points'],game['total'],abs_tol=1e-9,rel_tol=0)
            and math.isclose(game['home_points']-game['away_points'],game['margin'],abs_tol=1e-9,rel_tol=0),
            'Forecast score averages do not reconcile')
    return {key:copy.deepcopy(game.get(key)) for key in FIELDS}


def _model():
    import pgo_season_model as model
    pins=[]
    for path, expected in ((model.SEED_PATH,model.SEED_SHA256),
            (model.SOURCE_DIR/'final-fit.json',model.FIT_SHA256),
            (model.SOURCE_DIR/'scoring-rates.json',model.SCORING_SHA256)):
        raw=path.read_bytes();require(sha(raw)==expected,'Frozen score collection model pin differs')
        pins.append(dict(path=path.relative_to(ROOT).as_posix(),sha256=expected,bytes=len(raw)))
    # Direct score/feature helpers, including the score splitter and shared
    # identity/constants. These are collection-time bytes, not an execution log.
    dependencies=[]
    for relative in ('pgo_season_model.py','pgo_current_strength.py','pgo_forecast_corrected.py',
            'pgo_forecast_snapshot.py','pgo_sources.py','pgo_model.py',
            'research/pgo_input_audit/audit_model.py',
            'research/pgo_postseason_candidate/pinned_challenger.py'):
        raw=(ROOT/relative).read_bytes()
        dependencies.append(dict(path=relative,sha256=sha(raw),bytes=len(raw)))
    return dict(model_inputs=pins,
                collection_time_model_code_sha256=dependencies[0]['sha256'],
                collection_time_executable_dependencies=dependencies,
                model_code_time_basis='Dependency bytes checked at collection, not proof of original execution',
                margin_recipe='Frozen postseason weekly margin',total_recipe='Frozen prior-season REG+POST PF/PA',
                residual_recipe_context='Symmetric 80-percent absolute residuals; two full prior seasons and 500 games')


def _archive(root,pointer,cache):
    key=(pointer['path'],pointer['manifest_sha256'])
    if key not in cache:cache[key]=load_archive(root,pointer)
    return cache[key]


def _schedule(archived,root,clock):
    games=index(archived.get('schedule',[])); rows=list(games.values())
    require(all(type(g['season']) is int and g['season']==archived['season'] and g['game_type']=='REG' for g in rows),
            'Collection schedule season differs')
    periods=[(g['week'],g[side]) for g in rows for side in ('home','away')]
    require(len(set(periods))==len(periods),'Duplicate schedule team/week')
    expected={key:{k:g[k] for k in season.IDENTITY} for key,g in games.items()}
    full=False;ref=None
    refs=[r for r in archived.get('source_captures',[]) if r.get('url')==season.URLS['schedule']]
    require(len(refs)<=1,'Ambiguous schedule source')
    if refs:
        ref=refs[0]
        parsed=season.parse_schedule(source_bytes(root,ref,clock),archived['season'])
        require(expected=={g['game_id']:{k:g[k] for k in season.IDENTITY} for g in parsed},'Archived schedule differs from source')
        full=(len(expected)==272 and {g['week'] for g in rows}==set(range(1,19))
              and set(Counter(g[side] for g in rows for side in ('home','away')).values())=={17})
    record=dict(season=archived['season'],games=expected,source=copy.deepcopy(ref),complete_schedule=full)
    return sha(canonical(record)),record


def _observation(game,archived,manifest,pointer,root,clock,schedule_id,model):
    forecast=_forecast(game)
    require(utc(forecast['issued_at']) <= utc(archived['checked_at']) <= utc(manifest['created_at']) <= utc(clock)
            < utc(forecast['lock_at']),'Original archive or collection clock is late')
    refs=archived.get('edition_sources',{}).get(forecast['source_edition'])
    require(isinstance(refs,list) and refs,'Original forecast edition sources are missing')
    for ref in refs:source_bytes(root,ref,forecast['inputs_as_of'])
    availability=game.get('availability') or {}
    if availability.get('source_archive'):
        from pgo_season_availability import load_availability
        path=availability['source_archive']
        require(re.fullmatch(r'availability(?:-v2)?/\d{8}T\d{12}Z',path) is not None,'Invalid availability archive path')
        replay=load_availability(Path(root)/path)
        require(replay['games'][game['game_id']]=={k:v for k,v in availability.items() if k!='source_archive'},
                'Forecast availability differs from original evidence')
        require(utc(availability['checked_at'])<=utc(clock),'Availability observation follows collection')
    recipe=dict(model,producer_code_sha256=manifest['code_sha256'],collection_version=IDENTITY)
    recipe_id=sha(canonical(recipe))
    row=dict(forecast=forecast,forecast_sha256=sha(canonical(forecast)),forecast_archive=copy.deepcopy(pointer),
             forecast_durable_at=manifest['created_at'],sources=copy.deepcopy(refs),schedule_id=schedule_id,
             collected_at=clock,collection_clock_basis='Actual season refresh check clock; actual durability checked separately',
             collector_code_sha256=sha(Path(__file__).read_bytes()),recipe=recipe,recipe_id=recipe_id)
    return dict(row,id=sha(canonical(row)))


def _verify_observation(row,root,cache):
    require(row['id']==sha(canonical({k:v for k,v in row.items() if k!='id'})),'Collection observation changed')
    require(row['recipe_id']==sha(canonical(row['recipe'])),'Collection recipe identity changed')
    archived,manifest=_archive(root,row['forecast_archive'],cache)
    game=index([g for w in archived['weeks'] for g in w['games']])[row['forecast']['game_id']]
    rebuilt=_observation(game,archived,manifest,row['forecast_archive'],root,row['collected_at'],row['schedule_id'],
                         {k:v for k,v in row['recipe'].items() if k not in ('producer_code_sha256','collection_version')})
    # Executable hashes describe each actual collection, not the later verifier.
    rebuilt['collector_code_sha256']=row['collector_code_sha256']
    rebuilt['id']=sha(canonical({k:v for k,v in rebuilt.items() if k!='id'}))
    require(rebuilt==row,'Original forecast/source receipt differs')
    for ref in row['recipe']['model_inputs']:
        path=ROOT/ref['path']
        require(path.resolve().is_relative_to(ROOT/'docs/evidence') and not path.is_symlink(),'Invalid model input path')
        raw=path.read_bytes();require(sha(raw)==ref['sha256'] and len(raw)==ref['bytes'],'Model input pin differs')


def _witness(row,pointer,root,cache):
    seen=set()
    while pointer:
        key=(pointer['path'],pointer['manifest_sha256'])
        require(key not in seen,'Cyclic collection archive history');seen.add(key)
        archived,manifest=_archive(root,pointer,cache)
        if archived['checked_at']==row['collected_at']:
            saved=(archived.get('score_range_collection') or {}).get('observations',[])
            require(row in saved,'Original collection archive lacks observation')
            require(utc(row['collected_at'])<=utc(manifest['created_at'])<utc(row['forecast']['lock_at']),
                    'Collection was not durably saved before T-60')
            return copy.deepcopy(pointer)
        require(utc(archived['checked_at'])>=utc(row['collected_at']),'Original collection witness is missing')
        pointer=manifest.get('previous')
    raise ValueError('Original collection witness is missing')


def _final(result,forecast,schedule,root,checked):
    require(all(result.get(key)==forecast[key] for key in ('game_id','season','week','game_type','kickoff'))
            and result['home_team']==forecast['home'] and result['away_team']==forecast['away'],'Final game identity differs')
    ref=result['source'];raw=source_bytes(root,ref,checked)
    require(ref['url']==season.SCOREBOARD.format(season=forecast['season'],week=forecast['week']),'Invalid final source URL')
    parsed=index(season.parse_scoreboard(json.loads(raw),schedule,ref['captured_at'])['results']).get(forecast['game_id'])
    require(parsed is not None and all(result.get(k)==v for k,v in parsed.items()),'Final differs from original explicit provider FINAL')
    margin=forecast['margin']-result['actual_margin'];total=forecast['total']-result['home_score']-result['away_score']
    return dict(result=copy.deepcopy(result),margin_error=margin,total_error=total,
                absolute_margin_error=abs(margin),absolute_total_error=abs(total))


def _metrics(payload):
    rows={r['id']:r for r in payload['observations']};groups=defaultdict(list)
    for key,selected in payload['selections'].items():
        if selected is None:continue
        row=rows[selected]
        require(row['forecast']['game_id']==key,'Selected observation game differs')
        groups[row['recipe_id'],row['forecast']['season']].append(row)
    seasons=[]
    for (recipe,year),observations in sorted(groups.items()):
        schedules=[payload['schedules'][r['schedule_id']] for r in observations]
        inventories=[set(s['games']) for s in schedules]
        consistent=all(keys==inventories[0] for keys in inventories)
        eligible={r['forecast']['game_id'] for r in observations if r['id'] in payload['collection_witnesses']}
        finalized=eligible & set(payload['results'])
        complete=consistent and all(s['complete_schedule'] for s in schedules) and finalized==inventories[0]
        seasons.append(dict(recipe_id=recipe,season=year,recorded_games=len(observations),eligible_games=len(eligible),
            finalized_games=len(finalized),expected_games=len(inventories[0]) if consistent else None,
            complete_calibration_season=complete,status='COMPLETE' if complete else 'PARTIAL'))
    complete=Counter(s['recipe_id'] for s in seasons if s['complete_calibration_season'])
    minimum=any(n>=2 and sum(s['finalized_games'] for s in seasons if s['recipe_id']==recipe and s['complete_calibration_season'])>=500
                for recipe,n in complete.items())
    return dict(recorded_observations=len(rows),selected_games=sum(s['recorded_games'] for s in seasons),
        eligible_games=sum(s['eligible_games'] for s in seasons),finalized_games=sum(s['finalized_games'] for s in seasons),
        awaiting_durable_receipt=sum(s['recorded_games']-s['eligible_games'] for s in seasons),
        complete_calibration_seasons=sum(complete.values()),partial_calibration_seasons=sum(not s['complete_calibration_season'] for s in seasons),
        calibration_minimum_met=minimum,eligible_for_ranges=False,seasons=seasons)


def refresh_shadow(state,previous,root,checked_at):
    old=copy.deepcopy((previous or {}).get('score_range_collection') or {})
    defaults=dict(observations=[],selections={},collection_witnesses={},results={},schedules={})
    payload=dict(identity=IDENTITY,schema_version=1,status='READY',blocked_reason=None,checked_at=checked_at,
        charter_sha256=sha(CHARTER.read_bytes()),forecast_adjustment=None,predictive_status='UNAVAILABLE',ranges=None,
        **{key:old.get(key,value) for key,value in defaults.items()},excluded=[])
    try:
        checked=utc(checked_at);require(utc(state['checked_at'])==checked,'Collection must use actual season check clock')
        require(not old or old.get('identity',IDENTITY)==IDENTITY,'Unknown collection identity')
        games=index([g for w in state['weeks'] for g in w['games']]);finals=index(state.get('results',[]))
        require(not old.get('charter_sha256') or old['charter_sha256']==payload['charter_sha256'],'Collection charter changed')
        if previous is None or not (Path(root)/'current.json').exists():
            payload['excluded']=[dict(game_id=key,reason='NO_DURABLE_FORECAST_ARCHIVE') for key in games]
        else:
            pointer=season.read_json(Path(root)/'current.json');cache={}
            archived,manifest=_archive(root,pointer,cache)
            require(archived==previous,'Previous state does not match current durable archive')
            require(utc(manifest['created_at'])<=checked,'Original durable archive is from the future')
            original=index([g for w in archived['weeks'] for g in w['games']])
            observations={r['id']:r for r in payload['observations']}
            require(len(observations)==len(payload['observations']),'Duplicate collection observation')
            for row in observations.values():
                _verify_observation(row,root,cache)
                witness=payload['collection_witnesses'].get(row['id']) or pointer
                verified=_witness(row,witness,root,cache)
                payload['collection_witnesses'][row['id']]=verified
            for key,accepted in payload['results'].items():
                require(finals.get(key)==accepted['result'],'Accepted collection final changed or disappeared')
            schedule_id,schedule=_schedule(archived,root,checked_at)
            model=None
            for key,game in games.items():
                cutoff=utc(game['kickoff'])-season.timedelta(minutes=60)
                if checked>=cutoff:
                    if key not in payload['selections']:
                        payload['excluded'].append(dict(game_id=key,reason='FIRST_COLLECTION_AT_OR_AFTER_T60'))
                    elif payload['selections'][key] is None:
                        payload['excluded'].append(dict(game_id=key,reason='PRIMARY_FORECAST_UNAVAILABLE'))
                    continue
                if state['status']!='READY' or game.get('blocked_reason') or game.get('margin') is None:
                    if key in payload['selections']:payload['selections'][key]=None
                    payload['excluded'].append(dict(game_id=key,reason='PRIMARY_FORECAST_UNAVAILABLE'));continue
                forecast=_forecast(game)
                if key not in original or original[key].get('blocked_reason') or forecast!=_forecast(original[key]):
                    payload['excluded'].append(dict(game_id=key,reason='AWAITING_DURABLE_FORECAST'));continue
                existing=next((r for r in reversed(payload['observations']) if r['forecast']==forecast),None)
                if existing is None:
                    model=model or _model()
                    existing=_observation(original[key],archived,manifest,pointer,root,checked_at,schedule_id,model)
                    payload['observations'].append(existing);payload['schedules'][schedule_id]=schedule
                payload['selections'][key]=existing['id']
            observations={r['id']:r for r in payload['observations']}
            for key,selected in payload['selections'].items():
                if selected is None or key not in finals or selected not in payload['collection_witnesses']:continue
                forecast=observations[selected]['forecast']
                target=_final(finals[key],forecast,state['schedule'],root,checked_at)
                if key in payload['results']:require(target==payload['results'][key],'Saved score errors changed')
                payload['results'][key]=target
        payload['metrics']=_metrics(payload)
    except (ValueError,KeyError,TypeError,OSError,OverflowError) as error:
        payload.update({key:copy.deepcopy(old.get(key,value)) for key,value in defaults.items()})
        payload.update(status='BLOCKED',blocked_reason=str(error),metrics=copy.deepcopy(old.get('metrics',_metrics(dict(defaults)))))
    return payload


def check_durable_shadow(state,previous,durable_at):
    old=(previous or {}).get('score_range_collection') or {};new=state.get('score_range_collection') or {}
    defaults=dict(observations=[],selections={},collection_witnesses={},results={},schedules={})
    if new.get('status')=='BLOCKED':
        require(all(new.get(k,v)==old.get(k,v) for k,v in defaults.items()),'Blocked collection changed retained evidence')
        return
    before={r['id']:r for r in old.get('observations',[])};after={r['id']:r for r in new.get('observations',[])}
    require(len(after)==len(new.get('observations',[])) and set(before)<=set(after),'Collection observation removed or duplicated')
    clock=utc(durable_at)
    for key,row in after.items():
        require(row['id']==sha(canonical({k:v for k,v in row.items() if k!='id'})),'Collection observation changed')
        if key in before:require(row==before[key],'Collection observation changed')
        else:
            require(utc(row['collected_at'])<=clock<utc(row['forecast']['lock_at']),'Collection durable-write lock crossed')
    for key,value in old.get('selections',{}).items():
        require(key in new.get('selections',{}),'Collection selection removed')
        if new['selections'][key]!=value:
            row=before[value] if value else after[new['selections'][key]]
            require(clock<utc(row['forecast']['lock_at']),'Collection selection changed after durable lock')
    for key,value in new.get('selections',{}).items():
        require(value is None or value in after and after[value]['forecast']['game_id']==key,'Invalid collection selection')
        if key not in old.get('selections',{}) and value:
            require(clock<utc(after[value]['forecast']['lock_at']),'First collection selection crossed durable lock')
    for field in ('collection_witnesses','results','schedules'):
        for key,value in old.get(field,{}).items():
            require(new.get(field,{}).get(key)==value,'Saved collection '+field+' changed')
