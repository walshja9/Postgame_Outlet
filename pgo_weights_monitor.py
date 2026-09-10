"""Immutable prospective comparisons for fixed weights and probability variants.

The caller supplies a verified season state. This module never fetches sources,
fits models, replaces main picks, or allocates confidence points.
"""
import copy
from datetime import timedelta
import hashlib
import json
import math
from pathlib import Path
import re

import pgo_forecast_corrected as scoring
import pgo_season_model as model
import pgo_sources
from research.pgo_weights_candidate_20260910 import candidate as research

ROOT = Path(__file__).resolve().parent
PACKAGE_DIR = ROOT/'research/pgo_weights_candidate_20260910/run-attempt01'
PACKAGE_MANIFEST_SHA256 = '481d64fec1512934da21066c5a5c40b3f43dc4ad45ef7295d243948deba9e814'
IDENTITY = 'pgo-weights-shadow-2026'
SOURCE_HREF = 'https://github.com/walshja9/Postgame_Outlet/blob/main/research/pgo_weights_candidate_20260910/README.md'
MUTABLE = {'grade','result'}


def _require(condition,message):
    if not condition: raise ValueError(message)


def _package(path,pin):
    manifest=research.verified(path,pin); path=Path(path)
    fits=json.loads((path/'final-fits.json').read_bytes())
    calibration=json.loads((path/'final-calibrations.json').read_bytes())
    margin=json.loads((path/'margin-metrics.json').read_bytes())
    probability=json.loads((path/'probability-metrics.json').read_bytes())
    baseline=model._read_pinned(model.SOURCE_DIR/'final-fit.json',model.FIT_SHA256)
    _require(fits.get('postseason')==baseline and set(fits)==set(research.ARMS), 'Weights control fit differs')
    for arm,dropped in research.DROPS.items():
        _require(set(fits[arm]['preprocessor']['feature_names'])==set(baseline['preprocessor']['feature_names'])-set(dropped),
                 'Weights feature inventory differs')
    expected={f'{arm}_{curve}' for arm in research.ARMS for curve in research.CURVES}
    _require(set(calibration['curves'])==expected and len(calibration['training_game_ids'])==2127
             and calibration['evaluation_season'] is None and not calibration['validation_game_ids'], 'Final probability calibration differs')
    _require(manifest['pins']['charter_sha256']==research.CHARTER_SHA, 'Weights experiment charter differs')
    historical=dict(status='EXPERIMENTAL / HOLD',source_vintage='REVIEW REQUIRED',margin_arms={},probability_curves={})
    for arm in research.ARMS:
        view=margin['metrics'][arm]['overall']
        historical['margin_arms'][arm]=dict(n=view.get('games',view.get('count')),mae=view['mae'],
            screen=margin['screens'].get(arm,{'result':'CONTROL'}))
        for curve in research.CURVES:
            key=f'{arm}_{curve}'; view=probability['metrics'][key]['overall']
            historical['probability_curves'][key]=dict(n=view['count'],log_loss=view['log_loss'],brier=view['brier'],
                favorite_disagreements=view['favorite_disagreements'],screen=probability['screens'].get(key,{'result':'CONTROL'}))
    return fits,calibration['curves'],historical


def _source_proof(state,rankings,checked):
    """Bind original seed features or retain already verified current source refs."""
    refs=rankings.get('source_captures') or state.get('edition_sources',{}).get(rankings['edition'])
    if refs:
        for ref in refs:
            _require(re.fullmatch('[0-9a-f]{64}',ref.get('sha256','')) is not None
                     and type(ref.get('bytes')) is int and ref['bytes']>0
                     and research.utc(ref['captured_at'])<=research.utc(rankings['inputs_as_of'])<=checked,
                     'Ranking source reference or clock differs')
        return dict(kind='verified_season_source_references',captures=copy.deepcopy(refs),
                    verification='Caller load_current verifies captured raw hashes before this calculation.')
    from pgo_season import initial_snapshot
    original=initial_snapshot()
    _require(rankings['completed_week']==0 and rankings['edition']==original['edition']
             and research.utc(rankings['inputs_as_of'])==research.utc(original['inputs_as_of'])
             and research.utc(rankings['generated_at'])==research.utc(original['generated_at']),
             'Ranking features have no verified source evidence')
    saved={r['team']:r for r in original['teams']}
    for row in rankings['teams']:
        _require(all(row[k]==saved[row['team']][k] for k in ('features','qb_name','qb_gsis_id')), 'Original ranking features or QB changed')
    raw=(model.SOURCE_DIR/'manifest.json').read_bytes()
    return dict(kind='verified_original_snapshot',edition=original['edition'],
                manifest_path=(model.SOURCE_DIR/'manifest.json').relative_to(ROOT).as_posix(),
                manifest_sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))


def _grade(games,results,checked):
    finals={r['game_id']:r for r in results}
    _require(len(finals)==len(results), 'Duplicate weights final result')
    updated=copy.deepcopy(games)
    for game in updated:
        result=finals.get(game['game_id'])
        if result is None:
            _require(game.get('result') is None, 'Previously accepted weights final is missing')
            continue
        _require(result['home_team']==game['home'] and result['away_team']==game['away']
                 and all(result[k]==game[k] for k in ('season','week','game_type'))
                 and research.utc(result['kickoff'])==research.utc(game['kickoff'])
                 and research.utc(game['kickoff'])<research.utc(result['finalized_at'])<=checked,
                 'Weights final identity or time differs')
        _require(all(type(result[k]) is int and result[k]>=0 for k in ('home_score','away_score')), 'Invalid weights final scores')
        actual=result['home_score']-result['away_score']
        _require(result['actual_margin']==actual, 'Weights final margin differs')
        saved={k:result[k] for k in ('home_score','away_score','actual_margin','finalized_at')}
        _require(game.get('result') in (None,saved), 'Previously accepted weights final changed')
        winner=game['home'] if actual>0 else game['away'] if actual<0 else None
        def grade(selected): return 'NO_PICK' if selected is None else 'T' if winner is None else 'W' if selected==winner else 'L'
        game['result']=saved
        game['grade']=dict(margins={arm:grade(game['home'] if value>0 else game['away'] if value<0 else None)
                                   for arm,value in game['margins'].items()},
                           probabilities={key:grade(value['selected_team']) for key,value in game['probabilities'].items()})
    return updated


def _metrics(games):
    paired=[g for g in games if g.get('result') is not None]
    out=dict(paired_games=len(paired),paired_weeks=len({g['week'] for g in paired}),margin_arms={},probability_curves={},
             guidance='Fixed prospective comparisons on identical saved games. Interim results are descriptive; no automatic refitting or promotion.')
    for arm in research.ARMS:
        errors=[g['margins'][arm]-g['result']['actual_margin'] for g in paired]
        out['margin_arms'][arm]=dict(n=len(paired),mae=math.fsum(abs(v) for v in errors)/len(errors) if errors else None,
            **{name:sum(g['grade']['margins'][arm]==code for g in paired)
               for name,code in (('wins','W'),('losses','L'),('ties','T'),('no_pick','NO_PICK'))})
        for curve in research.CURVES:
            key=f'{arm}_{curve}'
            rows=[dict(game_id=g['game_id'],season=g['season'],week=g['week'],actual_margin=g['result']['actual_margin'],
                       margin=g['margins'][arm],p=[g['probabilities'][key]['probabilities'][side] for side in ('home','away','tie')]) for g in paired]
            out['probability_curves'][key]=(dict(n=len(rows),**research.probability_metrics(rows,'p','margin')) if rows
                                            else dict(n=0,log_loss=None,brier=None))
    return out


def refresh_shadow(state,previous,checked_at,*,package_path=PACKAGE_DIR,package_manifest_sha256=None):
    """Return detached weights_shadow; preserve original pairs on errors or revisions."""
    old=(previous or {}).get('weights_shadow',{})
    pin=package_manifest_sha256 or PACKAGE_MANIFEST_SHA256
    payload=dict(identity=IDENTITY,status='READY',blocked_reason=None,checked_at=checked_at,source_href=SOURCE_HREF,
                 package_manifest_sha256=old.get('package_manifest_sha256') or pin,
                 games=copy.deepcopy(old.get('games',[])),excluded=copy.deepcopy(old.get('excluded',[])),
                 historical=copy.deepcopy(old.get('historical',{})))
    try:
        checked=research.utc(checked_at)
        payload['games']=_grade(payload['games'],state['results'],checked)
        _require(not old.get('package_manifest_sha256') or old['package_manifest_sha256']==pin, 'Weights package changed after issuance')
        fits,calibrations,historical=_package(package_path,pin); payload['historical']=historical
        _require(state.get('status')=='READY', 'Main season state is not READY: '+str(state.get('blocked_reason')))
        rankings=state['rankings']; teams={r['team']:r for r in rankings['teams']}
        _require(len(teams)==len(rankings['teams'])==32 and set(teams)==set(pgo_sources.CURRENT_TEAMS), 'Weights ranking team inventory differs')
        proof=_source_proof(state,rankings,checked)
        issued={g['game_id'] for g in payload['games']}; excluded={r['game_id']:r for r in payload['excluded']}
        _require(len(issued)==len(payload['games']), 'Duplicate saved weights pair')
        all_games=[g for week in state['weeks'] for g in week['games']]
        _require(len({g['game_id'] for g in all_games})==len(all_games), 'Duplicate primary game')
        final_ids={r['game_id'] for r in state['results']}
        for game in all_games:
            key=game['game_id']
            if key in issued: continue
            cutoff=research.utc(game['kickoff'])-timedelta(minutes=60)
            if checked>=cutoff or key in final_ids:
                excluded[key]=dict(game_id=key,reason='Not issued before the real T-60 cutoff');continue
            if game.get('blocked_reason') or game.get('margin') is None:
                excluded[key]=dict(game_id=key,reason='Primary forecast is withheld or unavailable');continue
            try:
                _require(game['season']==2026 and game['game_type']=='REG' and game['week']==rankings['completed_week']+1,
                         'Weights game is outside the current ranking week')
                _require(game['source_edition']==rankings['edition'] and research.utc(game['inputs_as_of'])==research.utc(rankings['inputs_as_of'])
                         and research.utc(game['inputs_as_of'])<=research.utc(game['issued_at'])<=checked
                         and research.utc(rankings['inputs_as_of'])<=research.utc(rankings['generated_at'])<=checked,
                         'Weights game and ranking edition or clocks differ')
                selected={team:teams[team] for team in (game['home'],game['away'])}
                _require(game['expected_qbs']=={team:row['qb_name'] for team,row in selected.items()}
                         and all(row.get('qb_gsis_id') for row in selected.values()), 'Weights expected QB identity differs')
                vector=model.ch._matchup_features(selected[game['home']]['features'],selected[game['away']]['features'],
                                                 dict(game,neutral=game['location']=='Neutral'))
                _require(set(vector)==set(fits['postseason']['preprocessor']['feature_names']), 'Weights matchup feature inventory differs')
                margins={arm:scoring.score(vector,fits[arm]) for arm in research.ARMS}
                _require(type(game['margin']) in (int,float) and math.isfinite(game['margin'])
                         and abs(margins['postseason']-game['margin'])<=1e-8, 'Weights matched-control margin differs')
                probabilities={}
                for arm in research.ARMS:
                    for curve in research.CURVES:
                        curve_key=f'{arm}_{curve}'; p=research.probabilities(margins[arm],calibrations[curve_key])
                        side='home' if p[0]>p[1] else 'away' if p[1]>p[0] else None
                        probabilities[curve_key]=dict(probabilities=dict(zip(('home','away','tie'),p)),
                            selected_team=game[side] if side else None,selected_probability=max(p[:2]) if side else None)
                pair={k:game[k] for k in model.GAME_IDENTITY}
                pair.update(issued_at=checked_at,inputs_as_of=game['inputs_as_of'],lock_at=cutoff.isoformat(),
                    ranking_edition=rankings['edition'],ranking_generated_at=rankings['generated_at'],history_through=rankings['history_through'],
                    source_edition=game['source_edition'],source_proof=copy.deepcopy(proof),matchup_features=vector,
                    expected_qbs=copy.deepcopy(game['expected_qbs']),qb_gsis_ids={team:row['qb_gsis_id'] for team,row in selected.items()},
                    package_manifest_sha256=pin,margins=margins,probabilities=probabilities,
                    grade=dict(margins={arm:'PENDING' for arm in research.ARMS},probabilities={key:'PENDING' for key in probabilities}),result=None)
                payload['games'].append(pair);issued.add(key);excluded.pop(key,None)
            except (ValueError,KeyError,TypeError,OverflowError) as error:
                payload.update(status='BLOCKED',blocked_reason=str(error));excluded[key]=dict(game_id=key,reason=str(error))
        payload['excluded']=list(excluded.values())
    except (ValueError,KeyError,TypeError,OSError,OverflowError,ImportError) as error:
        payload.update(status='BLOCKED',blocked_reason=str(error))
    payload['metrics']=_metrics(payload['games'])
    return payload


def check_durable_shadow(state,previous,durable):
    old=(previous or {}).get('weights_shadow',{}).get('games',[])
    current=state.get('weights_shadow',{}).get('games',[])
    before={g['game_id']:g for g in old}; after={g['game_id']:g for g in current}
    _require(len(before)==len(old) and len(after)==len(current), 'Duplicate immutable weights game')
    _require(set(before)<=set(after), 'An immutable weights forecast was removed')
    for key,game in after.items():
        if key in before:
            _require({k:v for k,v in game.items() if k not in MUTABLE}=={k:v for k,v in before[key].items() if k not in MUTABLE},
                     'An immutable weights forecast changed')
        else:
            cutoff=research.utc(game['kickoff'])-timedelta(minutes=60)
            _require(research.utc(game['inputs_as_of'])<=research.utc(game['issued_at'])<=research.utc(durable)<cutoff
                     and research.utc(game['lock_at'])==cutoff, 'Weights durable-write deadline crossed')
            _require(set(game['margins'])==set(research.ARMS) and all(type(v) in (int,float) and math.isfinite(v) for v in game['margins'].values()),
                     'Weights margins are missing or nonfinite')
            _require(set(game['probabilities'])=={f'{arm}_{curve}' for arm in research.ARMS for curve in research.CURVES}, 'Weights curves are missing')
            for value in game['probabilities'].values():
                p=value['probabilities']
                _require(set(p)=={'home','away','tie'} and all(type(v) in (int,float) and math.isfinite(v) and 0<=v<=1 for v in p.values())
                         and abs(math.fsum(p.values())-1)<=1e-12, 'Weights probabilities are invalid')
