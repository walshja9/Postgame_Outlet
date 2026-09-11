import copy
from contextlib import redirect_stderr
import csv
from datetime import UTC, datetime
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import generate_site
import pgo_forecast_lab


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "docs/evidence/forecast-lab-2026"
LOCK = ARCHIVE / "prospective_lock.json"
PREDICTIONS = ARCHIVE / "prospective_predictions.csv"
ATTESTATION = ROOT / "research/pgo_stability_blend/prospective_attestation.json"


class ForecastLabTests(unittest.TestCase):
    def setUp(self):
        # These fixtures exercise archived/weekly Lab inputs; the real additive
        # packages and shared grading feed are covered in test_pgo_model_updates.
        self.enterContext(patch("pgo_model_updates.render_current_updates", return_value=""))

    @unittest.skipUnless(shutil.which("node"), "Node is required for the fragment behavior check")
    def test_shared_fragment_script_activates_owning_tab_after_handlers_bind(self):
        script = pgo_forecast_lab.FORECAST_DISPLAY_SCRIPT.removeprefix('<script>').removesuffix('</script>')
        harness = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const events = {};
const freshness = [
  {dataset:{freshnessAt:new Date(Date.now()-46*60000).toISOString(),freshnessMinutes:'45'},textContent:''},
  {dataset:{freshnessAt:new Date().toISOString(),freshnessMinutes:'30'},textContent:''},
  {dataset:{freshnessAt:'2020-01-01T00:00:00Z',freshnessMinutes:'30',freshnessUntil:'2020-01-02T00:00:00Z'},textContent:''},
  {dataset:{freshnessAt:'2020-01-01T00:00:00Z',freshnessMinutes:'10',freshnessUntil:'2020-01-02T00:00:00Z',freshnessEndedLabel:'Kickoff reached; final list status shown above'},textContent:''}
];
const panel = {hidden:true, getAttribute(name) {return name === 'aria-labelledby' ? 'tab-comparison' : null;}};
const detail = {tagName:'DETAILS', open:false, parentElement:null};
let scrolls = 0, handlerReady = false, clicks = 0, seasonPoll;
const tab = {click() {clicks++; if (handlerReady) panel.hidden = false;}};
const target = {tagName:'DIV', parentElement:detail,
  closest(selector) {return selector === '[role="tabpanel"]' ? panel : null;},
  scrollIntoView() {scrolls++;}};
const document = {
  readyState:'loading',
  getElementById(id) {return {'reason':target, 'tab-comparison':tab}[id] || null;},
  querySelectorAll(selector) {return selector==='[data-freshness-at]' ? freshness : [];}, querySelector() {return null;},
  addEventListener(name, callback) {events[name] = callback;}
};
const location = {hash:'#reason', href:'https://example.test/index.html?release=test#reason', origin:'https://example.test'};
let pendingTimers = new Map(), timerID = 0;
const window = {scrollX:0,scrollY:420, scrollTo(x,y) {this.scrollX=x;this.scrollY=y;},
  addEventListener(name, callback) {events[name] = callback;}};
const context = {document, window, location, Date, URL,
  setTimeout(callback) {pendingTimers.set(++timerID,callback);return timerID;},
  clearTimeout(id) {pendingTimers.delete(id);},
  setInterval(callback, delay) {assert.equal(delay,60000); seasonPoll=callback;}};
vm.createContext(context);
vm.runInContext(SCRIPT, context);
assert.equal(freshness[0].textContent,'Update overdue');
assert.equal(freshness[0].dataset.overdue,'true');
assert.equal(freshness[1].textContent,'Recently checked');
assert.equal(freshness[2].textContent,'Updates closed at lock');
assert.equal(freshness[3].textContent,'Kickoff reached; final list status shown above');
// The script runs inside the PGO panel, before the page binds tab handlers.
handlerReady = true;
if (events.DOMContentLoaded) events.DOMContentLoaded();
assert.equal(panel.hidden, false, 'cold deep link must activate PGO tab after its handler binds');
assert.equal(detail.open, true);
assert.ok(scrolls > 0);
assert.equal(location.hash, '#reason');
// Later hash navigation and native anchor clicks use the same owning-tab path.
panel.hidden = true; detail.open = false;
events.hashchange();
assert.equal(panel.hidden, false); assert.equal(detail.open, true);
panel.hidden = true;
events.click({target:{closest() {return {hash:'#reason'};}}});
assert.equal(panel.hidden, false);
// Standalone Lab targets have no tabpanel and still open their disclosures.
target.closest = () => null; detail.open = false;
const before = clicks;
events.hashchange();
assert.equal(detail.open, true); assert.equal(clicks, before);
location.hash = '#missing'; events.hashchange();
(async () => {
  let reloads=0, replacements=0, requests=0, latest='2026-09-09T11:00:00Z', ok=true, releaseFetch;
  location.reload=() => reloads++;
  const fantasy={value:'custom scoring',focused:false};
  function keyed(key,tag,extra={}) {
    const node={dataset:{viewKey:key},tagName:tag,type:'',attributes:[],children:[],scrollLeft:0,scrollTop:0,
      ...extra, focus(options) {assert.equal(options.preventScroll,true);document.activeElement=this;},
      closest() {return this.dataset.viewKey ? this : this.parentElement;},
      getAttribute(name) {return name==='href' ? this.href || null : null;},
      querySelector(selector) {return selector==='summary' ? this.children[0] : null;}};
    if(tag==='DETAILS') {
      const summary={tagName:'SUMMARY',parentElement:node,children:[],attributes:[],
        closest:()=>node,getAttribute:()=>null,focus:node.focus};node.children=[summary];
    }
    return node;
  }
  function section(stamp) {
    const nodes=[keyed('penalty','DETAILS',{open:false}),keyed('week-1','DETAILS',{open:true}),
      keyed('columns','INPUT',{type:'checkbox',checked:false}),keyed('weekly-table','DIV'),
      keyed('new-section','DETAILS',{open:true})];
    const lock={dataset:{weeklyCutoff:'2020-01-01T00:00:00Z'},textContent:'Draft'};
    return {id:'pgo-season',dataset:{seasonCheckedAt:stamp},nodes,children:nodes,lock,unsafe:false,
      closest:()=>panel, contains(node) {return nodes.includes(node)||nodes.some(n=>n.children.includes(node));},
      querySelectorAll(selector) {if(selector==='[data-view-key]')return nodes;
        if(selector==='[data-weekly-cutoff]')return [lock];return nodes;},
      querySelector() {return this.unsafe ? {} : null;},
      replaceWith(next) {assert.equal(next.nodes[0].open,true,'restore open disclosure before insertion');
        assert.equal(next.nodes[1].open,false,'restore explicit closed default before insertion');
        next.nodes.forEach(node=>{node.scrollLeft=0;node.scrollTop=0;});
        replacements++;current=next;}};
  }
  let current=section('2026-09-09T12:00:00Z'), next=section('2026-09-09T12:15:00Z'), parsedCount=1;
  current.nodes[0].open=true;current.nodes[1].open=false;current.nodes[2].checked=true;
  current.nodes[3].scrollLeft=143;current.nodes[3].scrollTop=7;
  document.activeElement=current.nodes[0].children[0];
  document.querySelector=()=>current;
  document.querySelectorAll=selector=>selector==='[data-weekly-cutoff]' ? [current.lock] : [];
  document.hidden=false;panel.hidden=false;
  context.DOMParser=class {parseFromString() {return {querySelectorAll:()=>Array(parsedCount).fill(next)};}};
  let htmlOK=true, finalURL=location.href;
  context.fetch=async(url,options)=>{
    requests++;assert.equal(options.cache,'no-store');
    if(url==='evidence/season-2026/current.json')return {ok,json:async()=>({checked_at:latest})};
    assert.equal(new URL(url).origin,location.origin);
    if(releaseFetch)await new Promise(resolve=>{releaseFetch.resolve=resolve;});
    return {ok:htmlOK,url:finalURL,text:async()=>'<html>fixture</html>'};
  };
  const startScrolls=scrolls,startHash=location.hash;
  async function waitForHTML() {
    for(let turn=0;turn<20 && !releaseFetch.resolve;turn++)await Promise.resolve();
    assert.ok(releaseFetch.resolve,'poll must fetch new HTML');
  }
  await seasonPoll();assert.equal(replacements,0);
  latest='2026-09-09T12:00:00Z';await seasonPoll();assert.equal(replacements,0);
  latest='2026-09-09T12:15:00Z';document.hidden=true;await seasonPoll();assert.equal(replacements,0);
  document.hidden=false;panel.hidden=true;await seasonPoll();assert.equal(replacements,0);
  panel.hidden=false;ok=false;await seasonPoll();assert.equal(replacements,0);ok=true;
  next.dataset.seasonCheckedAt='2026-09-09T12:05:00Z';await seasonPoll();assert.equal(replacements,0,'HTML behind advertised pointer');
  assert.equal(reloads,0,'a refresh must never reload the page');
  next.dataset.seasonCheckedAt=latest;next.unsafe=true;await seasonPoll();assert.equal(replacements,0);next.unsafe=false;
  next.nodes[0].attributes=[{name:'onclick',value:'bad()'}];await seasonPoll();assert.equal(replacements,0);next.nodes[0].attributes=[];
  next.dataset.seasonCheckedAt='invalid';await seasonPoll();assert.equal(replacements,0);next.dataset.seasonCheckedAt=latest;
  parsedCount=0;await seasonPoll();assert.equal(replacements,0);
  parsedCount=2;await seasonPoll();assert.equal(replacements,0);parsedCount=1;
  next.nodes[1].dataset.viewKey='penalty';await seasonPoll();assert.equal(replacements,0);next.nodes[1].dataset.viewKey='week-1';
  htmlOK=false;await seasonPoll();assert.equal(replacements,0);htmlOK=true;
  finalURL='https://other.test/index.html';await seasonPoll();assert.equal(replacements,0);finalURL=location.href;
  // Switch tabs while HTML is loading; a concurrent tick must not start another fetch.
  releaseFetch={};const pending=seasonPoll();
  await waitForHTML();
  const busyRequests=requests;await seasonPoll();assert.equal(requests,busyRequests);
  panel.hidden=true;releaseFetch.resolve();await pending;assert.equal(replacements,0);panel.hidden=false;releaseFetch=null;
  releaseFetch={};const hidden=seasonPoll();await waitForHTML();
  document.hidden=true;releaseFetch.resolve();await hidden;assert.equal(replacements,0);document.hidden=false;releaseFetch=null;
  releaseFetch={};const stale=seasonPoll();await waitForHTML();
  const saved=current;current=section(latest);releaseFetch.resolve();await stale;assert.equal(replacements,0);current=saved;releaseFetch=null;
  // User changes controls during fetch: preserve their latest state, not an early snapshot.
  releaseFetch={};const changed=seasonPoll();await waitForHTML();
  current.nodes[3].scrollLeft=201;releaseFetch.resolve();await changed;releaseFetch=null;
  assert.equal(replacements,1,'new verified section must replace only season content');
  assert.equal(current.nodes[0].open,true);assert.equal(current.nodes[1].open,false);
  assert.equal(current.nodes[2].checked,true);assert.equal(current.nodes[3].scrollLeft,201);
  assert.equal(current.nodes[3].scrollTop,7);assert.equal(current.nodes[4].open,true);
  assert.equal(document.activeElement,current.nodes[0].children[0]);
  assert.equal(current.lock.textContent,'Locked');assert.equal(pendingTimers.size,1);
  assert.equal(window.scrollY,420);assert.equal(scrolls,startScrolls);assert.equal(location.hash,startHash);
  assert.equal(reloads,0);assert.equal(fantasy.value,'custom scoring');
  // A later update neither steals focus from Fantasy nor creates another cutoff timer.
  document.activeElement=fantasy;latest='2026-09-09T12:30:00Z';next=section(latest);
  await seasonPoll();assert.equal(replacements,2);assert.equal(document.activeElement,fantasy);
  assert.equal(pendingTimers.size,1);
  // Standalone Lab refresh preserves checkbox focus without requiring a tabpanel.
  current.closest=()=>null;document.activeElement=current.nodes[2];
  latest='2026-09-09T12:45:00Z';next=section(latest);
  await seasonPoll();assert.equal(replacements,3);assert.equal(document.activeElement,current.nodes[2]);
  assert.equal(document.activeElement.checked,true);assert.equal(pendingTimers.size,1);
  console.log('fragment behavior PASS; in-place reading continuity and race guards PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
""".replace('SCRIPT', json.dumps(script))
        result = subprocess.run([shutil.which('node')], input=harness, text=True,
                                capture_output=True, check=False, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('fragment behavior PASS', result.stdout)

    def test_latest_corrected_revision_drives_the_input_panel_after_refresh(self):
        weekly_root = Path('docs/evidence/forecast-lab-2026/weekly').resolve()
        weekly = {'revisions': [dict(source_edition='pgo-corrected-week1-2026-09-08',
            source_directory='../september-08-corrected'),
            dict(source_edition='pgo-corrected-week1-2026-09-08', source_directory='../september-09-refresh')]}
        with patch('pgo_forecast_corrected.load_snapshot', return_value={}) as load, \
                patch.object(Path, 'read_bytes', return_value=b'verified manifest'):
            data, directory = pgo_forecast_lab._load_corrected(None, weekly, weekly_root)
        self.assertEqual(directory, weekly_root.parent / 'september-09-refresh')
        load.assert_called_once_with(directory)
        self.assertIn('september-09-refresh/snapshot.json', data['_download_url'])
        self.assertEqual(data['_manifest_sha256'], hashlib.sha256(b'verified manifest').hexdigest())

    def test_corrected_panel_distinguishes_scale_and_unpriced_absences(self):
        corrected = {'generated_at': '2026-09-08T16:00:00Z', 'inputs_as_of': '2026-09-08T15:00:00Z',
            'teams': [{'team': 'NE', 'rank': 1, 'rating': 2.0, 'qb_name': '<Maye>',
                'features': {'pgo_v0': 4.0}, 'contributions': {'pgo_v0': 2.0},
                'coverage': {'status': 'UNKNOWN', 'source_kind': 'no_formal_report',
                    'notes': ['Final report pending <review>'],
                    'known_unavailable': [{'gsis_id': 'brown', 'player_name': 'Ben Brown', 'report_position': 'OL', 'game_status': 'Out'}],
                    'observations': [{'gsis_id': 'brown', 'player_name': 'Ben Brown', 'report_position': 'OL', 'game_status': 'Out'}]}}]}
        panel = pgo_forecast_lab._corrected_section(corrected)
        for text in ('corrected-rating-NE', '&lt;Maye&gt;', '&lt;review&gt;',
                     'Injuries beyond the quarterback are not included', 'model units', 'Raw input',
                     'Fitted contribution', 'HOLD', '+2.000', 'PGO Corrected',
                     'Model construction', 'Snapshot generated', '2025 regular season',
                     'id="model-editions"', 'July 21', 'September 7'):
            self.assertIn(text, panel)
        self.assertNotIn('<Maye>', panel)
        self.assertEqual(panel.count('Ben Brown (OL): Out'), 1)
        team = panel.split('id="corrected-rating-NE">', 1)[1]
        reader, technical = team.split('<details class="technical-details">', 1)
        self.assertIn('recent game results', reader)
        self.assertIn('current edge-rusher and linebacker depth', reader)
        self.assertIn('not a complete assessment of the current roster', reader)
        self.assertIn('docs/model-depth-audit-2026-09-09.md', panel)
        self.assertIn('current edge-rusher and linebacker depth', panel.split('Choose a team below')[0])
        self.assertIn('not proof', reader)
        self.assertNotIn('Fitted contribution', reader)
        self.assertNotIn('model units', reader)
        self.assertIn('Fitted contribution', technical)
        self.assertNotIn('<details class="technical-details" open', panel)
        corrected['teams'][0]['rank'] = 3
        moved = pgo_forecast_lab._corrected_section(corrected)
        self.assertIn('Why does New England rank #3?', moved)
        self.assertNotIn('First place in this calculation', moved)
        corrected['teams'][0]['contributions']['pgo_v0'] = 3.0
        with self.assertRaises(ValueError):
            pgo_forecast_lab._corrected_section(corrected)

    def test_mixed_weekly_sources_keep_their_own_total_and_incumbent_baselines(self):
        snapshot = self.synthetic_snapshot()
        games = [dict(game) for game in snapshot['games'][:2]]
        games[0].update(league_mean_total=40, incumbent_margin=3)
        games[1].update(league_mean_total=60, incumbent_margin=-3)
        snapshot['games'] = games
        results = [dict(game_id=game['game_id'], actual_margin=0, home_score=25, away_score=25)
                   for game in games]
        metrics = pgo_forecast_lab.snapshot_interim_metrics(snapshot, results)
        self.assertEqual(metrics['baselines']['league_mean_venue']['total']['mae'], 10)
        self.assertEqual(metrics['baselines']['incumbent']['margin']['mae'], 3)

    def test_current_strength_summary_uses_verified_results_and_stays_hold(self):
        study = pgo_forecast_lab.load_strength_study(pgo_forecast_lab.STRENGTH_STUDY_DIR)
        sensitivity = {'teams': [], 'completed_at': 'old run', 'mccabe_as_of': 'McCabe',
            'snapshot_generated_at': 'September', 'depth_as_of': 'depth',
            'source_captures': [], 'manifest_sha256': 'old manifest'}
        panel = pgo_forecast_lab._model_sensitivity(sensitivity, study)
        for expected in ('10.1937', '10.1193', '10.1198', '10.1318', '1377/2119',
                         'Current-strength study', 'All four arms remain HOLD',
                         'recorded actual starters', 'not verified pregame/T-60',
                         'Offensive-line and defensive player quality remain unavailable'):
            self.assertIn(expected, panel)
        self.assertEqual(panel.count('id="model-sensitivity"'), 1)
        self.assertIn('six-variant opponent-adjustment experiment above', panel)
        self.assertIn('availability-20260908/scenario-report.md', panel)
        self.assertIn('11 formal player-report rows', panel)
        self.assertIn('other 30 teams remain unknown', panel)
        self.assertIn('<table class="study-table">', panel)
        page = pgo_forecast_lab.render_lab(self.synthetic_lock(), [], [])
        self.assertIn('.study-table{table-layout:fixed}', page)
        self.assertIn('.study-table th,.study-table td{white-space:normal;overflow-wrap:anywhere}', page)
        self.assertIn('.study-table th:first-child{width:42%}', page)

    def test_current_strength_summary_fails_closed_on_changed_receipts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('manifest.json', 'metrics.json', 'run-receipt.json'):
                (root / name).write_bytes((pgo_forecast_lab.STRENGTH_STUDY_DIR / name).read_bytes())
            pgo_forecast_lab.load_strength_study(root)
            (root / 'metrics.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'hash|bytes'):
                pgo_forecast_lab.load_strength_study(root)
            (root / 'manifest.json').unlink()
            with self.assertRaises(OSError):
                pgo_forecast_lab.load_strength_study(root)
        with patch.object(pgo_forecast_lab, 'STRENGTH_STUDY_MANIFEST_SHA256', '0' * 64):
            with self.assertRaisesRegex(ValueError, 'manifest hash'):
                pgo_forecast_lab.load_strength_study(pgo_forecast_lab.STRENGTH_STUDY_DIR)

    def sensitivity_fixture(self, root, mutation=None):
        snapshot = self.synthetic_snapshot()
        rows = []
        for team in snapshot['teams']:
            row = {'team': team['team']}
            for arm in ('raw', 'team_epa', 'team_qb_epa'):
                for carry in ('unchanged', '0.5'):
                    key = f'{arm}__offseason_{carry}'
                    row[key + '_rank'] = team['rank'] if carry == 'unchanged' else 33 - team['rank']
                    row[key + '_rating'] = team['rating'] if carry == 'unchanged' else team['rating'] - 2
            rows.append(row)
        if mutation:
            mutation(rows)
        raw = io.StringIO(newline='')
        writer = csv.DictWriter(raw, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        files = {
            'ratings.csv': raw.getvalue().encode(),
            'run-receipt.json': json.dumps({'status': 'EXPLORATORY_RETROSPECTIVE_RESEARCH',
                'completed_at': '2026-09-08T01:39:57Z'}).encode(),
            'metrics.json': json.dumps({'leakage_verdict': 'REVIEW REQUIRED', 'screening': {
                arm: {'merits_further_prospective_study': False}
                for arm in ('team_epa', 'team_qb_epa')}}).encode(),
        }
        manifest = {'identity': 'pgo-opponent-epa-retrospective-20260907', 'files': {}}
        for name, value in files.items():
            (root / name).write_bytes(value)
            manifest['files'][name] = {'sha256': hashlib.sha256(value).hexdigest(), 'bytes': len(value)}
        (root / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        return snapshot

    def test_model_sensitivity_has_signed_rank_gap_and_no_calibrated_interval(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            snapshot = self.sensitivity_fixture(root)
            with patch('pgo_forecast_lab.pgo_comparison.mccabe_source_timestamp', return_value='2026-09-07T12:00:00Z'):
                sensitivity = pgo_forecast_lab.load_model_sensitivity(root, snapshot)
            page = pgo_forecast_lab.render_lab(self.synthetic_lock(), [], [],
                snapshot=snapshot, sensitivity=sensitivity)
        self.assertIn('<details class="lab-detail" id="model-sensitivity">', page)
        self.assertIn('Calibrated uncertainty: unavailable', page)
        self.assertIn('not a confidence or prediction interval', page)
        self.assertIn('Historical publication vintage: REVIEW REQUIRED', page)
        self.assertEqual(page.count('class="sensitivity-team"'), 32)
        first = sensitivity['teams'][0]
        self.assertEqual(first['rank_gap'], first['pgo_rank'] - first['mccabe_rank'])
        self.assertEqual(first['rating_span'], [7.0, 9.0])
        self.assertEqual(first['rank_span'], [1, 32])
        self.assertIn('2026-09-08T01:39:57Z', page)
        self.assertEqual(page, pgo_forecast_lab.render_lab(self.synthetic_lock(), [], [],
            snapshot=snapshot, sensitivity=sensitivity))
        sensitivity['depth_as_of'] = '<script>alert(1)</script>'
        escaped = pgo_forecast_lab._model_sensitivity(sensitivity)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', escaped)
        self.assertNotIn('<script>', escaped)

    def test_model_sensitivity_rejects_bad_rows_hashes_and_baseline_drift(self):
        changes = (
            lambda rows: rows.pop(),
            lambda rows: rows.__setitem__(1, dict(rows[0])),
            lambda rows: rows[0].__setitem__('team_epa__offseason_0.5_rating', 'nan'),
            lambda rows: rows[0].__setitem__('team_qb_epa__offseason_unchanged_rank', 2),
            lambda rows: rows[0].__setitem__('raw__offseason_unchanged_rating', 999),
        )
        for change in changes:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                snapshot = self.sensitivity_fixture(root, change)
                with self.assertRaises(ValueError):
                    pgo_forecast_lab.load_model_sensitivity(root, snapshot)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            snapshot = self.sensitivity_fixture(root)
            (root / 'ratings.csv').write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'hash|bytes'):
                pgo_forecast_lab.load_model_sensitivity(root, snapshot)
            (root / 'manifest.json').unlink()
            with self.assertRaises(OSError):
                pgo_forecast_lab.load_model_sensitivity(root, snapshot)

    def test_real_sensitivity_verifies_pinned_research_and_preserves_snapshot(self):
        path = ARCHIVE / 'september-07/snapshot.json'
        raw = path.read_bytes()
        snapshot = json.loads(raw)
        before = copy.deepcopy(snapshot)
        sensitivity = pgo_forecast_lab.load_model_sensitivity(pgo_forecast_lab.SENSITIVITY_DIR, snapshot)
        self.assertEqual(len(sensitivity['teams']), 32)
        self.assertEqual(sensitivity['manifest_sha256'], pgo_forecast_lab.SENSITIVITY_MANIFEST_SHA256)
        self.assertEqual(snapshot, before)
        self.assertEqual(path.read_bytes(), raw)
        with patch.object(pgo_forecast_lab, 'SENSITIVITY_MANIFEST_SHA256', '0' * 64):
            with self.assertRaisesRegex(ValueError, 'manifest hash'):
                pgo_forecast_lab.load_model_sensitivity(pgo_forecast_lab.SENSITIVITY_DIR, snapshot)

    def synthetic_lock(self):
        return {
            "as_of": "2026-07-21T12:00:00-04:00",
            "candidate": {
                "as_of": "2026-08-26T14:29:26-04:00",
                "formula": "0.75*pgo_v0_prediction+0.25*challenger_prediction",
            },
            "games": [
                {
                    "game_id": "g1", "season": 2026, "week": 1,
                    "kickoff": "2026-09-10T00:20:00+00:00",
                    "home": "SEA", "away": "NE", "game_type": "REG",
                    "location": "Home", "candidate_prediction": 1.0,
                    "pgo_v0_prediction": 2.0, "challenger_prediction": -2.0,
                    "challenger_full_strength_prediction": -1.0,
                },
                {
                    "game_id": "g2", "season": 2026, "week": 1,
                    "kickoff": "2026-09-11T00:35:00+00:00",
                    "home": "LAR", "away": "SF", "game_type": "REG",
                    "location": "Neutral", "candidate_prediction": -4.0,
                    "pgo_v0_prediction": -1.0, "challenger_prediction": -13.0,
                    "challenger_full_strength_prediction": -12.0,
                },
            ],
        }

    def synthetic_snapshot(self):
        teams = []
        for rank, team in enumerate(
                sorted(pgo_forecast_lab.pgo_prospective.pgo_model.CURRENT_TEAMS), 1):
            teams.append({
                "rank": rank,
                "team": team,
                "rating": 10.0 - rank,
                "qb_name": f"{team} QB1",
                "qb_gsis_id": f"{team}-QB1",
                "old_selector_qb_name": f"{team} old QB",
                "old_selector_rating": 9.5 - rank,
                "features": {},
                "contributions": {"pgo_v0": 10.0 - rank},
            })
        return {
            "generated_at": "2026-09-07T22:00:00Z",
            "fit": {"preprocessor": {"feature_names": ["pgo_v0"], "missing_features": []}},
            "league_mean_total": 46.0,
            "teams": teams,
            "games": [
                {
                    "game_id": "s1", "season": 2026, "week": 1,
                    "kickoff": "2026-09-10T00:20:00+00:00",
                    "home": "SEA", "away": "NE", "game_type": "REG",
                    "location": "Home", "home_rest": 7.0, "away_rest": 7.0,
                    "margin": 2.5, "total": 45.0,
                    "home_points": 23.75, "away_points": 21.25,
                    "pgo_v0_margin": 1.0, "legacy_margin": 0.5,
                    "old_selector_margin": 2.0,
                },
                {
                    "game_id": "s2", "season": 2026, "week": 18,
                    "kickoff": "2027-01-04T01:20:00+00:00",
                    "home": "LAR", "away": "SF", "game_type": "REG",
                    "location": "Home", "home_rest": 7.0, "away_rest": 7.0,
                    "margin": -3.0, "total": 44.0,
                    "home_points": 20.5, "away_points": 23.5,
                    "pgo_v0_margin": -1.0, "legacy_margin": -2.0,
                    "old_selector_margin": -2.5,
                },
            ],
            "lock": {
                "as_of": "2026-09-07T22:00:00+00:00",
                "games": [
                    {
                        "game_id": "s1", "season": 2026, "week": 1,
                        "kickoff": "2026-09-10T00:20:00+00:00",
                        "home": "SEA", "away": "NE", "game_type": "REG",
                        "location": "Home", "candidate_prediction": 2.5,
                    },
                    {
                        "game_id": "s2", "season": 2026, "week": 18,
                        "kickoff": "2027-01-04T01:20:00+00:00",
                        "home": "LAR", "away": "SF", "game_type": "REG",
                        "location": "Home", "candidate_prediction": -3.0,
                    },
                ],
            },
            "method": {
                "name": "Active-roster preseason scenario",
                "status": "EXPERIMENTAL — HOLD",
                "roster_policy": "ACT-only roster captured September 7.",
                "injury_coverage": "No comprehensive injury or inactive adjustment.",
                "history": "Performance features use games through 2025.",
                "totals": "Prior-season PF/PA mean.",
                "fit_recovery": "Public fit reproduced exactly.",
                "evaluation": "New inference policy is not historically validated.",
                "schedule": "Week 18 times are provisional.",
            },
            "sources": [],
        }

    def result_rows(self):
        return [
            {
                "game_id": "g1", "season": "2026", "week": "1",
                "kickoff": "2026-09-10T00:20:00+00:00", "game_type": "REG",
                "home_team": "SEA", "away_team": "NE",
                "home_score": "24", "away_score": "21",
                "finalized_at": "2026-09-10T03:30:00+00:00",
            },
            {
                "game_id": "g2", "season": "2026", "week": "1",
                "kickoff": "2026-09-11T00:35:00+00:00", "game_type": "REG",
                "home_team": "LAR", "away_team": "SF",
                "home_score": "17", "away_score": "19",
                "finalized_at": "2026-09-11T04:00:00+00:00",
            },
        ]

    def csv_bytes(self, rows):
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=pgo_forecast_lab.RESULT_COLUMNS,
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue().encode("utf-8")

    def write_capture(self, root, name, rows, *, captured_at=None,
                      source_url="https://example.com/results.csv"):
        directory = root / name
        directory.mkdir(parents=True)
        payload = self.csv_bytes(rows)
        (directory / "results.csv").write_bytes(payload)
        metadata = {
            "schema_version": 1,
            "kind": "pgo_forecast_lab_result_transcription",
            "captured_at": captured_at or name.replace(
                name, f"{name[:4]}-{name[4:6]}-{name[6:8]}T{name[9:11]}:{name[11:13]}:{name[13:15]}Z"
            ),
            "source_url": source_url,
            "results_file": "results.csv",
            "results_file_sha256": hashlib.sha256(payload).hexdigest(),
            "rows": len(rows),
        }
        (directory / "capture.json").write_text(
            json.dumps(metadata, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8", newline="",
        )

    def test_load_archive_verifies_real_272_game_artifacts(self):
        lock = pgo_forecast_lab.load_archive(LOCK, PREDICTIONS, ATTESTATION)

        self.assertEqual(len(lock["games"]), 272)
        self.assertEqual(lock["candidate"]["pgo_v1_weight"], 0.25)
        self.assertEqual(
            hashlib.sha256(LOCK.read_bytes()).hexdigest(),
            "d6ebf73188c41046f945a54653bdb89eadc2dc18d917276a47c0166b9ada98e9",
        )
        self.assertEqual(
            hashlib.sha256(PREDICTIONS.read_bytes()).hexdigest(),
            "8b17ab8c4744586e5386a7755ceaf63ccf8a8438533e8c904de68b5bc25dca6f",
        )

    def test_load_archive_rejects_tampered_csv(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            lock_path = root / "lock.json"
            csv_path = root / "predictions.csv"
            attestation_path = root / "attestation.json"
            lock_path.write_bytes(LOCK.read_bytes())
            csv_path.write_bytes(PREDICTIONS.read_bytes() + b"tampered")
            attestation_path.write_bytes(ATTESTATION.read_bytes())

            with self.assertRaisesRegex(ValueError, "prediction CSV"):
                pgo_forecast_lab.load_archive(lock_path, csv_path, attestation_path)

    def test_load_archive_requires_exact_published_attestation_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            changed = Path(temp) / "attestation.json"
            changed.write_bytes(ATTESTATION.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "published attestation"):
                pgo_forecast_lab.load_archive(LOCK, PREDICTIONS, changed)

    def test_load_archive_runs_internal_lock_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            lock = json.loads(LOCK.read_bytes())
            lock["games"][0]["candidate_prediction"] += 100
            lock["prediction_integrity_sha256"] = (
                pgo_forecast_lab.pgo_prospective._prediction_integrity_hash(
                    lock["games"], include_candidate=True
                )
            )
            lock["artifact_sha256"] = (
                pgo_forecast_lab.pgo_prospective._artifact_hash(lock)
            )
            lock_bytes = (
                pgo_forecast_lab.pgo_prospective._canonical(lock) + "\n"
            ).encode("utf-8")
            predictions = pgo_forecast_lab.pgo_prospective._prediction_csv(
                lock
            ).encode("utf-8")
            attestation = copy.deepcopy(json.loads(ATTESTATION.read_bytes()))
            attestation["derived"].update({
                "lock_artifact_sha256": lock["artifact_sha256"],
                "lock_file_sha256": hashlib.sha256(lock_bytes).hexdigest(),
                "prediction_integrity_sha256": lock["prediction_integrity_sha256"],
                "predictions_file_sha256": hashlib.sha256(predictions).hexdigest(),
            })
            attestation["artifact_sha256"] = (
                pgo_forecast_lab.pgo_prospective._artifact_hash(attestation)
            )
            attestation_bytes = (
                pgo_forecast_lab.pgo_prospective._canonical(attestation) + "\n"
            ).encode("utf-8")
            paths = root / "lock.json", root / "predictions.csv", root / "attestation.json"
            paths[0].write_bytes(lock_bytes)
            paths[1].write_bytes(predictions)
            paths[2].write_bytes(attestation_bytes)

            with patch.object(
                    pgo_forecast_lab, "EXPECTED_ATTESTATION_SHA256",
                    hashlib.sha256(attestation_bytes).hexdigest()), \
                    self.assertRaisesRegex(ValueError, "candidate prediction"):
                pgo_forecast_lab.load_archive(*paths)

    def test_load_results_merges_incremental_captures_and_metrics(self):
        rows = self.result_rows()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_capture(root, "20260910T040000Z", rows[:1])
            self.write_capture(root, "20260911T050000Z", rows[1:])

            loaded, provenance = pgo_forecast_lab.load_results(
                root, self.synthetic_lock()
            )
            metrics = pgo_forecast_lab.interim_metrics(
                self.synthetic_lock(), loaded
            )

        self.assertEqual([row["game_id"] for row in loaded], ["g1", "g2"])
        self.assertEqual(len(provenance), 2)
        self.assertEqual(metrics["blend"]["mae"], 2.0)
        self.assertEqual(metrics["blend"]["rmse"], 2.0)
        self.assertEqual(metrics["pgo_v0"]["mae"], 1.0)
        self.assertEqual(metrics["zero"]["mae"], 2.5)
        self.assertAlmostEqual(metrics["zero"]["rmse"], math.sqrt(6.5))
        self.assertEqual(metrics["venue"]["mae"], 1.25)
        self.assertEqual(metrics["blend"]["winner"], {
            "correct": 2, "denominator": 2, "accuracy": 1.0,
        })

    def test_load_results_rejects_duplicate_or_invalid_rows(self):
        rows = self.result_rows()
        cases = {
            "duplicate": (rows[:1], rows[:1], "duplicate result"),
            "identity": ([{**rows[0], "home_team": "SF"}], None, "locked home team"),
            "fractional": ([{**rows[0], "home_score": "24.5"}], None, "integer scores"),
            "late-capture": (rows[:1], None, "after capture"),
        }
        for name, (first, second, error) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                captured = (
                    "2026-09-10T02:00:00Z" if name == "late-capture"
                    else "2026-09-10T04:00:00Z"
                )
                directory_name = (
                    "20260910T020000Z" if name == "late-capture"
                    else "20260910T040000Z"
                )
                self.write_capture(root, directory_name, first,
                                   captured_at=captured)
                if second:
                    self.write_capture(root, "20260911T050000Z", second,
                                       captured_at="2026-09-11T05:00:00Z")
                with self.assertRaisesRegex(ValueError, error):
                    pgo_forecast_lab.load_results(root, self.synthetic_lock())

    def test_load_results_rejects_tampered_hash_and_non_https_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_capture(root, "20260910T040000Z", self.result_rows()[:1])
            metadata_path = root / "20260910T040000Z/capture.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["source_url"] = "http://example.com/results.csv"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                pgo_forecast_lab.load_results(root, self.synthetic_lock())

            metadata["source_url"] = "https://example.com/results.csv"
            metadata["results_file_sha256"] = "0" * 64
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash"):
                pgo_forecast_lab.load_results(root, self.synthetic_lock())

    def test_result_parser_rejects_duplicate_or_wrong_field_counts(self):
        rows = self.result_rows()[:1]
        valid = self.csv_bytes(rows).decode("utf-8").splitlines()
        cases = {
            "duplicate": (
                valid[0] + ",home_score\n" + valid[1] + ",999\n",
                "duplicate result CSV columns",
            ),
            "surplus": (valid[0] + "\n" + valid[1] + ",oops\n", "field count"),
            "incomplete": (valid[0] + "\n" + valid[1].rsplit(",", 1)[0] + "\n", "field count"),
        }
        for name, (payload, error) in cases.items():
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, error):
                pgo_forecast_lab._accepted_results(
                    payload.encode("utf-8"), self.synthetic_lock(),
                    "2026-09-10T04:00:00Z", name,
                )

    def test_record_results_is_utf8_exact_and_append_only(self):
        rows = self.result_rows()[:1]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "reviewed.csv"
            payload = self.csv_bytes(rows)
            source.write_bytes(payload)
            capture_root = root / "captures"

            frozen_now = datetime(2026, 9, 10, 4, tzinfo=UTC)
            with patch.object(pgo_forecast_lab, "_current_utc",
                              return_value=frozen_now):
                path = pgo_forecast_lab.record_results(
                    source, "https://example.com/results.csv", capture_root,
                    self.synthetic_lock(),
                )
            self.assertEqual((path / "results.csv").read_bytes(), payload)
            with patch.object(pgo_forecast_lab, "_current_utc",
                              return_value=frozen_now), \
                    self.assertRaisesRegex(ValueError, "already exists"):
                pgo_forecast_lab.record_results(
                    source, "https://example.com/results.csv", capture_root,
                    self.synthetic_lock(),
                )

            source.write_bytes(b"\xff")
            with patch.object(
                    pgo_forecast_lab, "_current_utc",
                    return_value=datetime(2026, 9, 11, 5, tzinfo=UTC)), \
                    self.assertRaisesRegex(ValueError, "UTF-8"):
                pgo_forecast_lab.record_results(
                    source, "https://example.com/results.csv", capture_root,
                    self.synthetic_lock(),
                )

    def test_cli_has_no_historical_capture_time_override(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            pgo_forecast_lab.main(["--captured-at", "2026-09-10T04:00:00Z"])

    def test_cli_refuses_output_that_can_overwrite_archive_inputs(self):
        outputs = [LOCK, ARCHIVE / "alternate.html", ARCHIVE / "results/page.html"]
        for output in outputs:
            with self.subTest(output=output), \
                    patch.object(pgo_forecast_lab, "load_archive") as load, \
                    patch.object(pgo_forecast_lab, "atomic_write_text") as write, \
                    redirect_stderr(io.StringIO()):
                self.assertEqual(
                    pgo_forecast_lab.main(["--output", str(output)]), 1
                )
                load.assert_not_called()
                write.assert_not_called()

    def test_result_capture_paths_preserve_exact_bytes_in_git(self):
        attributes = [
            "docs/evidence/forecast-lab-2026/results/20260910T040000Z/results.csv",
            "docs/evidence/forecast-lab-2026/results/20260910T040000Z/capture.json",
        ]
        payload = b"a,b\r\n1,2\r\n"
        raw = subprocess.check_output(
            ["git", "hash-object", "--no-filters", "--stdin"], input=payload,
        )
        for path in attributes:
            with self.subTest(path=path):
                attr = subprocess.check_output(
                    ["git", "check-attr", "text", "--", path], text=True,
                )
                filtered = subprocess.check_output(
                    ["git", "hash-object", f"--path={path}", "--stdin"],
                    input=payload,
                )
                self.assertIn("text: unset", attr)
                self.assertEqual(filtered, raw)

    def test_render_lab_is_standalone_honest_and_escaped(self):
        lock = pgo_forecast_lab.load_archive(LOCK, PREDICTIONS, ATTESTATION)
        html = pgo_forecast_lab.render_lab(lock, [], [])

        self.assertIn("PGO Forecast Lab", html)
        self.assertIn("Can PGO predict football?", html)
        self.assertIn("Experimental", html)
        self.assertIn("Interim tracking", html)
        self.assertIn("0 of 272", html)
        self.assertIn("positive favors the home team", html)
        self.assertIn("negative favors the away team", html)
        self.assertIn("theoretical 50%", html)
        self.assertIn("Staff Picks", html)
        self.assertIn("No editorial picks are published", html)
        self.assertIn("McCabe Ratings", html)
        self.assertNotIn("McCabe rating gap", html)
        self.assertNotIn("PGO-minus-McCabe", html)
        self.assertNotIn("win probability", html.lower())
        self.assertEqual(html.count('data-game-id="'), 272)
        self.assertIn('<details class="forecast-week" open>', html)
        self.assertLess(html.index("Original forecast favors"),
                        html.index("Frozen kickoff"))
        self.assertIn("prospective_lock.json", html)
        self.assertIn("prospective_predictions.csv", html)
        self.assertIn("July 21, 2026 at 12:00 PM EDT", html)
        self.assertIn("August 26, 2026 at 4:07 PM EDT", html)
        self.assertIn(
            '<time datetime="2026-09-10T00:20:00+00:00">'
            "September 10, 2026 at 12:20 AM UTC</time>",
            html,
        )
        self.assertIn(
            '</style><link rel="stylesheet" href="pgo-theme.css?v=20260911-cleanup">', html
        )

        escaped = pgo_forecast_lab.render_lab(
            self.synthetic_lock(), [], [{"source_url": "https://example.com/?x=<tag>"}]
        )
        self.assertNotIn("<tag>", escaped)
        self.assertIn("&lt;tag&gt;", escaped)
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            pgo_forecast_lab.render_lab(
                self.synthetic_lock(), [],
                [{"source_url": "javascript:alert(1)"}],
            )

    def test_render_lab_fails_when_shared_style_markers_change(self):
        with patch.object(generate_site, "TEMPLATE", "<html></html>"), \
                self.assertRaisesRegex(ValueError, "style"):
            pgo_forecast_lab.render_lab(self.synthetic_lock(), [], [])

    def test_rating_explanations_reconcile_all_32_saved_outputs_and_show_close_gaps(self):
        snapshot = json.loads((ARCHIVE / "september-07/snapshot.json").read_text(encoding="utf-8"))
        rendered = pgo_forecast_lab._rating_explanations(snapshot)
        self.assertEqual(rendered.count('class="lab-detail rating-explanation"'), 32)
        self.assertIn("0.287 below", rendered)  # LAR trails NE, despite rounded headline ratings.
        self.assertIn("0.062 below #4 BAL", rendered)
        self.assertIn("0.684 above #6 BUF", rendered)
        self.assertIn("not independent football grades", rendered)
        self.assertIn("All 55 fitted terms", rendered)
        self.assertIn("Returning offensive snap share", rendered)
        expected_labels = ["Results history", "Team passing efficiency", "Other team efficiency",
                           "QB history", "Roster composition", "Coaching", "Other adjustments",
                           "Total model rating"]
        expected_ne = [3.864, 2.084, 0.470, 1.013, 0.461, -0.672, 0.000, 7.219]
        expected_lar = [4.610, 1.582, 0.527, 0.198, -0.014, 0.029, 0.000, 6.932]
        full_labels = None
        for team in snapshot["teams"]:
            detail = rendered.split(f'id="rating-{team["team"]}"', 1)[1].split("</details>", 1)[0]
            summary = detail.split('<table class="rating-summary">', 1)[1].split("</table>", 1)[0]
            self.assertEqual(re.findall(r'<th scope="row">([^<]+)</th>', summary), expected_labels)
            values = [float(value) for value in re.findall(r"<td>([+-]\d+\.\d{3})</td>", summary)]
            self.assertAlmostEqual(values[-1], team["rating"], delta=0.00051)
            self.assertAlmostEqual(sum(values[:-1]), values[-1], delta=0.0051)
            if team["team"] in ("NE", "LAR"):
                self.assertEqual(values, expected_ne if team["team"] == "NE" else expected_lar)
            full = detail.split('<table class="rating-terms">', 1)[1].split("</table>", 1)[0]
            labels = re.findall(r'<th scope="row">([^<]+)</th>', full)
            self.assertEqual(len(labels), 55)
            if full_labels is None:
                full_labels = labels
            self.assertEqual(labels, full_labels)
            values = [float(value) for value in re.findall(r"<td>([+-]\d+\.\d{3})</td>", full)]
            pp = snapshot["fit"]["preprocessor"]
            names = pp["feature_names"] + [name + "_missing" for name in pp["missing_features"]]
            self.assertEqual(values, [round(team["contributions"][name], 3) for name in names])
        ne = rendered.split('id="rating-NE"', 1)[1].split("</details>", 1)[0]
        self.assertIn("+3.864", ne)
        self.assertIn("+2.084", ne)
        self.assertIn("+0.635", ne)
        snapshot["teams"][0]["contributions"]["pgo_v0"] += 1
        with self.assertRaisesRegex(ValueError, "contributions"):
            pgo_forecast_lab._rating_explanations(snapshot)

    def test_team_takeaways_precede_tables_and_separate_editions(self):
        snapshot = json.loads((ARCHIVE / 'september-07/snapshot.json').read_text(encoding='utf-8'))
        before = copy.deepcopy(snapshot)
        page = pgo_forecast_lab._rating_explanations(snapshot)
        self.assertEqual(page.count('class="rating-takeaway"'), 32)
        self.assertIn('<details class="lab-detail" id="rating-glossary">', page)
        self.assertIn('Archived July comparison', page)
        self.assertIn('Unadopted research', page)
        for team, expected in {'NE': ('+3.864', '+2.084', 'Drake Maye', '+0.692'),
                               'JAX': ('+4.134', '+1.128', 'Trevor Lawrence', '-0.406')}.items():
            card = page.split(f'id="rating-{team}"', 1)[1].split('<table', 1)[0]
            self.assertIn('Issued September 7 snapshot', card)
            for text in expected:
                self.assertIn(text, card)
        self.assertIn('already selects Lawrence', page)
        self.assertEqual(snapshot, before)

    def test_weekly_process_covers_every_matchup_and_future_version_boundary(self):
        weekly = {'games': [], 'revisions': []}
        page = pgo_forecast_lab._weekly_section(weekly, self.synthetic_snapshot(), [], [])
        self.assertIn('href="#forecast-process"', page)
        self.assertIn('<details class="lab-detail" id="forecast-process">', page)
        for label in ('Review sources', 'Save a revision', 'Lock each matchup',
                      'Grade every issued matchup', 'Compare benchmarks', 'Test future versions'):
            self.assertIn(f'<strong>{label}</strong>', page)

    def test_snapshot_interim_metrics_use_separate_margin_total_and_score_targets(self):
        snapshot = self.synthetic_snapshot()
        results = [{
            "game_id": "s1", "home_score": 24, "away_score": 21,
            "actual_margin": 3,
        }]

        metrics = pgo_forecast_lab.snapshot_interim_metrics(snapshot, results)

        self.assertEqual(metrics["count"], 1)
        self.assertEqual(metrics["margin"]["mae"], 0.5)
        self.assertEqual(metrics["total"]["mae"], 0.0)
        self.assertEqual(metrics["score"]["count"], 2)
        self.assertEqual(metrics["score"]["mae"], 0.25)
        self.assertEqual(metrics["winner"], {
            "correct": 1, "denominator": 1, "accuracy": 1.0,
        })
        self.assertEqual(metrics["baselines"]["pgo_v0"]["margin"]["mae"], 2.0)
        self.assertEqual(metrics["baselines"]["legacy"]["margin"]["mae"], 2.5)
        self.assertEqual(metrics["baselines"]["zero"]["margin"]["mae"], 3.0)
        combined = metrics["baselines"]["league_mean_venue"]
        self.assertEqual(combined["margin"]["mae"], 0.5)
        self.assertEqual(combined["total"]["mae"], 1.0)
        self.assertEqual(combined["score"]["mae"], 0.5)
        cards = pgo_forecast_lab._snapshot_metric_cards(metrics)
        reader, technical = cards.split('<details class="technical-details">', 1)
        self.assertIn('Average miss <strong>0.500 points', reader)
        self.assertNotIn('RMSE', reader)
        self.assertIn('<th>RMSE</th>', technical)
        self.assertNotIn('<details class="technical-details" open', cards)
        self.assertIn("Original archive margin", cards)
        self.assertIn("League mean + venue", cards)
        self.assertIn("Unavailable", cards)
        self.assertEqual(metrics["ties"], {"actual": 0, "forecast": 0})
        snapshot["games"][0]["margin"] = 0.0
        tied = pgo_forecast_lab.snapshot_interim_metrics(snapshot, results)
        self.assertEqual(tied["ties"], {"actual": 0, "forecast": 1})
        self.assertIsNone(tied["winner"]["accuracy"])

    def test_render_snapshot_is_primary_and_preserves_the_original_archive(self):
        archive = self.synthetic_lock()
        snapshot = self.synthetic_snapshot()

        page = pgo_forecast_lab.render_lab(
            archive, [], [], snapshot=snapshot,
            snapshot_results=[], snapshot_provenance=[{
                "captured_at": "2026-09-11T05:00:00Z",
                "source_url": "https://example.com/results.csv",
                "rows": 1,
                "results_file_sha256": "a" * 64,
            }],
        )

        self.assertLess(page.index("September 7 preseason snapshot"),
                        page.index("Original July/August archive"))
        self.assertIn("Active-roster preseason scenario", page)
        self.assertIn("ACT is an administrative roster status", page)
        self.assertIn("same September 7 state", page)
        self.assertIn("SEA by 2.5 points", page)
        self.assertIn("SF by 3.0 points", page)
        self.assertIn("NE 21.3, SEA 23.8", page)
        self.assertIn("SF 23.5, LAR 20.5", page)
        self.assertIn("45.0", page)
        self.assertIn("44.0", page)
        self.assertIn(
            '<time datetime="2026-09-10T00:20:00+00:00">'
            "September 9, 2026 at 8:20 PM EDT</time>", page,
        )
        self.assertIn(
            "Score summaries use whole-number rounded averages; model averages and combined points use one decimal. "
            "Evaluation uses the original unrounded projections.", page,
        )
        self.assertIn(
            "<th>Combined points</th><th>Scheduled kickoff</th><th>Final score</th>", page,
        )
        self.assertIn("Week 18", page)
        self.assertIn("Week 18 times are provisional", page)
        self.assertIn("September results provenance", page)
        self.assertIn("https://example.com/results.csv", page)
        self.assertEqual(page.count('class="snapshot-team"'), 32)
        self.assertEqual(page.count('class="pgo-rating-bar" role="img"'), 32)
        self.assertEqual(page.count('class="pgo-team-marker"'), 32)
        for team in snapshot["teams"]:
            row = page.split(f'data-pgo-team="{team["team"]}"', 1)[1].split('</tr>', 1)[0]
            self.assertIn(f'data-value="{team["rating"]}"', row)
            self.assertIn(f'>{pgo_forecast_lab._signed(team["rating"])}</td>', row)
        self.assertIn('class="pgo-snapshot-table"', page)
        self.assertIn('class="pgo-essential"', page)
        self.assertIn('class="pgo-detail"', page)
        self.assertIn("prospective_lock.json", page)
        self.assertIn("Frozen 25% stability blend", page)
        self.assertNotIn("win probability", page.lower())
        self.assertNotIn("League mean + venue", page)
        for margin, expected in ((0.0, 'No projected edge'),
                                 (0.0009, 'SEA by less than 0.1 point'),
                                 (-0.0179, 'NE by less than 0.1 point')):
            self.assertEqual(
                pgo_forecast_lab._spread({**snapshot["games"][0], "margin": margin}),
                expected,
            )

    def test_why_forecast_uses_only_matching_saved_corrected_inputs(self):
        saved = json.loads((pgo_forecast_lab.CORRECTED_DIR / 'snapshot.json').read_bytes())
        saved['_manifest_sha256'] = hashlib.sha256(
            (pgo_forecast_lab.CORRECTED_DIR / 'manifest.json').read_bytes()).hexdigest()
        game = {**saved['games'][0], 'source_edition': saved['edition'],
                'source_generated_at': saved['generated_at'],
                'source_manifest_sha256': saved['_manifest_sha256'],
                'lock_at': '2026-09-09T23:20:00Z'}
        before = copy.deepcopy((game, saved))
        rendered = pgo_forecast_lab._forecast_weeks([game], [], weekly=True, corrected=saved)
        for text in ('Why this forecast', 'NE by 1.2 points', 'adds 1.6 points for SEA',
                     'same rest', 'SEA by 0.4 points', 'Drake Maye', 'Sam Darnold',
                     '28.82', '18.82', '28.41', '17.18', '46.62',
                     '23.53', '23.09', '#corrected-rating-NE', '#nonqb-availability',
                     'the quality of their backups are not rated separately'):
            self.assertIn(text, rendered)
        self.assertEqual((game, saved), before)
        reason = pgo_forecast_lab._forecast_reason(game, saved)
        reader, calculation = reason.split('<details class="forecast-reason-block forecast-reason-calculation">', 1)
        self.assertEqual(reader.count('<h3>'), 4)
        self.assertNotIn('Home = (combined points', reader)
        self.assertIn('<summary>Full calculation and saved version</summary>', calculation)
        self.assertIn('Home = (combined points', calculation)
        self.assertIn('Saved edition:', calculation)
        neutral = {**game, **next(g for g in saved['games'] if g['location'] == 'Neutral')}
        self.assertIn('neutral site adds no home advantage',
                      pgo_forecast_lab._forecast_reason(neutral, saved))
        for key, value in (('source_manifest_sha256', 'old'), ('source_edition', 'old'),
                           ('source_generated_at', 'old'), ('home_rest', 10),
                           ('location', 'Neutral'), ('margin', 99), ('total', 99),
                           ('home_points', 99), ('away_points', 99), ('kickoff', 'old')):
            with self.subTest(field=key):
                fallback = pgo_forecast_lab._forecast_reason({**game, key: value}, saved)
                self.assertIn('Saved score calculation', fallback)
                self.assertNotIn('Before the venue adjustment', fallback)
                self.assertNotIn('Drake Maye', fallback)
        for section in ('fit', 'scoring_rates', 'teams'):
            altered = copy.deepcopy(saved)
            if section == 'fit':
                altered['fit']['coefficients'][5] += 1
            elif section == 'scoring_rates':
                altered['scoring_rates']['NE']['pf'] += 1
            else:
                altered['teams'][0]['rating'] += 1
            self.assertNotIn('Before the venue adjustment',
                             pgo_forecast_lab._forecast_reason(game, altered))
        archive = pgo_forecast_lab._forecast_weeks([game], [], corrected=saved)
        self.assertIn('Saved score calculation', archive)
        self.assertNotIn('Before the venue adjustment', archive)
        self.assertNotIn('Drake Maye', archive)

    def test_forecast_reasons_have_their_own_full_width_row_for_each_game(self):
        saved = json.loads((pgo_forecast_lab.CORRECTED_DIR / 'snapshot.json').read_bytes())
        saved['_manifest_sha256'] = hashlib.sha256(
            (pgo_forecast_lab.CORRECTED_DIR / 'manifest.json').read_bytes()).hexdigest()
        games = [{**game, 'source_edition': saved['edition'],
                  'source_generated_at': saved['generated_at'],
                  'source_manifest_sha256': saved['_manifest_sha256'],
                  'lock_at': '2026-09-09T23:20:00Z'} for game in saved['games'][:2]]
        before = copy.deepcopy((games, saved))
        for weekly, kind, columns in ((True, 'weekly', 7), (False, 'snapshot', 6)):
            rendered = pgo_forecast_lab._forecast_weeks(games, [], weekly=weekly, corrected=saved)
            rows = re.findall(r'<tr([^>]*)>(.*?)</tr>', rendered, re.S)[1:]
            self.assertEqual(len(rows), 2 * len(games))
            self.assertIn('Week 1 <span>2 games</span>', rendered)
            for index, game in enumerate(games):
                primary_attrs, primary = rows[index * 2]
                reason_attrs, reason = rows[index * 2 + 1]
                self.assertIn(f'data-{kind}-game-id="{game["game_id"]}"', primary_attrs)
                self.assertEqual(rendered.count(f'data-{kind}-game-id="{game["game_id"]}"'), 1)
                self.assertNotIn('Why this forecast', primary)
                self.assertIn(pgo_forecast_lab._spread(game), primary)
                self.assertIn('Model averages', primary)
                self.assertIn('class="forecast-reason-row"', reason_attrs)
                self.assertIn(f'<td colspan="{columns}">', reason)
                self.assertIn(pgo_forecast_lab._forecast_reason(game, saved if weekly else None), reason)
                self.assertNotIn('<details class="forecast-reason" open', reason)
                self.assertNotIn(f'data-{kind}-game-id', reason_attrs)
        self.assertEqual((games, saved), before)

    def test_whole_score_summaries_keep_decimal_averages_and_unrounded_favorite(self):
        saved = json.loads((pgo_forecast_lab.CORRECTED_DIR / 'snapshot.json').read_bytes())
        game = next(game for game in saved['games'] if game['game_id'] == '2026_01_BAL_IND')
        before = copy.deepcopy(game)
        self.assertEqual(round(game['away_points']), round(game['home_points']))
        rendered = pgo_forecast_lab._forecast_weeks([game], [])
        self.assertIn('About 25 points each<details><summary>Model averages</summary>', rendered)
        self.assertNotIn('BAL 25, IND 25', rendered)
        self.assertIn('BAL 25.2, IND 24.8', rendered)
        self.assertIn('BAL by 0.4 points', rendered)
        self.assertIn('<th>Who PGO favors</th>', rendered)
        self.assertIn('<th>Estimated score</th>', rendered)
        self.assertEqual(game, before)
        self.assertEqual(pgo_forecast_lab._projected_score(25.25), '25.3')
        patriots = next(game for game in saved['games'] if game['game_id'] == '2026_01_NE_SEA')
        before = copy.deepcopy(patriots)
        rendered = pgo_forecast_lab._forecast_weeks([patriots], [])
        self.assertIn('NE 23, SEA 24<details><summary>Model averages</summary>', rendered)
        self.assertIn('NE 23.1, SEA 23.5', rendered)
        self.assertIn('SEA by 0.4 points', rendered)
        self.assertEqual(patriots, before)
        for away, home, summary, favorite in (
                (25.5, 25.5, 'About 26 points each', 'No projected edge'),
                (25.49, 25.5, 'BAL 25, IND 26', 'IND by less than 0.1 point')):
            boundary = {**game, 'away_points': away, 'home_points': home,
                        'margin': home - away, 'total': home + away}
            before = copy.deepcopy(boundary)
            rendered = pgo_forecast_lab._forecast_weeks([boundary], [])
            self.assertIn(summary + '<details><summary>Model averages</summary>', rendered)
            self.assertIn(favorite, rendered)
            self.assertEqual(boundary, before)

    def test_original_archive_keeps_tiny_edges_and_exact_zero_without_mutation(self):
        lock = self.synthetic_lock()
        lock['games'].append({**lock['games'][0], 'game_id': 'g3'})
        for game, margin in zip(lock['games'], (0.01, -0.01, 0.0)):
            for key in ('candidate_prediction', 'pgo_v0_prediction',
                        'challenger_prediction', 'challenger_full_strength_prediction'):
                game[key] = margin
        before = copy.deepcopy(lock)
        rendered = pgo_forecast_lab.render_lab(lock, [], [])
        for game, expected in zip(lock['games'], ('SEA by less than 0.1 point',
                                                  'SF by less than 0.1 point', 'No projected edge')):
            row = rendered.split(f'data-game-id="{game["game_id"]}"', 1)[1].split('</tr>', 1)[0]
            self.assertEqual(row.count(expected), 2)
        self.assertNotIn('<td>+0.0</td>', rendered)
        self.assertNotIn('<td>-0.0</td>', rendered)
        self.assertEqual(lock, before)

    def test_render_snapshot_rejects_a_post_kickoff_generation_time(self):
        snapshot = self.synthetic_snapshot()
        snapshot["generated_at"] = snapshot["games"][0]["kickoff"]

        with self.assertRaisesRegex(ValueError, "before every kickoff"):
            pgo_forecast_lab.render_lab(
                self.synthetic_lock(), [], [], snapshot=snapshot,
                snapshot_results=[], snapshot_provenance=[],
            )

    @patch('pgo_forecast_lab.load_model_sensitivity', return_value=None)
    def test_cli_loads_a_present_snapshot_and_renders_it_as_primary(self, _sensitivity):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            snapshot_dir = root / "snapshot"
            snapshot_dir.mkdir()
            output = root / "lab.html"
            with patch.object(pgo_forecast_lab, "load_archive",
                              return_value=self.synthetic_lock()), \
                    patch.object(pgo_forecast_lab, "_load_snapshot",
                                 return_value=self.synthetic_snapshot()) as load, \
                    patch.object(pgo_forecast_lab, "_load_corrected", return_value=(None, root / "corrected")), \
                    patch.object(pgo_forecast_lab, "load_results",
                                 side_effect=[([], []), ([], []), ([], [])]), \
                    patch.object(pgo_forecast_lab, "atomic_write_text") as write:
                status = pgo_forecast_lab.main([
                    "--snapshot", str(snapshot_dir),
                    "--weekly", str(root / "weekly"),
                    "--output", str(output),
                ])

            self.assertEqual(status, 0)
            load.assert_called_once_with(snapshot_dir)
            self.assertIn("September 7 preseason snapshot", write.call_args.args[1])

    def test_cli_fails_closed_when_a_present_snapshot_is_damaged(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            snapshot_dir = root / "snapshot"
            snapshot_dir.mkdir()
            output = root / "lab.html"
            with patch.object(pgo_forecast_lab, "load_archive",
                              return_value=self.synthetic_lock()), \
                    patch.object(pgo_forecast_lab.pgo_forecast_snapshot,
                                 "load_snapshot", side_effect=ValueError("damaged")), \
                    patch.object(pgo_forecast_lab, "atomic_write_text") as write, \
                    redirect_stderr(io.StringIO()):
                status = pgo_forecast_lab.main([
                    "--snapshot", str(snapshot_dir),
                    "--output", str(output),
                ])

            self.assertEqual(status, 1)
            write.assert_not_called()

    def test_default_snapshot_requires_the_pinned_manifest_and_presence(self):
        with tempfile.TemporaryDirectory() as temp:
            default = Path(temp) / "missing"
            with patch.object(pgo_forecast_lab, "SNAPSHOT_DIR", default), \
                    patch.object(pgo_forecast_lab,
                                 "EXPECTED_SNAPSHOT_MANIFEST_SHA256", "a" * 64):
                with self.assertRaisesRegex(ValueError, "default snapshot is missing"):
                    pgo_forecast_lab._load_snapshot(default)

            default.mkdir()
            (default / "manifest.json").write_bytes(b"changed\n")
            with patch.object(pgo_forecast_lab, "SNAPSHOT_DIR", default), \
                    patch.object(pgo_forecast_lab,
                                 "EXPECTED_SNAPSHOT_MANIFEST_SHA256", "a" * 64), \
                    patch.object(pgo_forecast_lab.pgo_forecast_snapshot,
                                 "load_snapshot") as load:
                with self.assertRaisesRegex(ValueError, "manifest hash"):
                    pgo_forecast_lab._load_snapshot(default)
                load.assert_not_called()

    @patch('pgo_forecast_lab.load_model_sensitivity', return_value=None)
    def test_cli_records_results_against_the_verified_snapshot_series(self, _sensitivity):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            snapshot_dir = root / "snapshot"
            snapshot_dir.mkdir()
            reviewed = root / "reviewed.csv"
            reviewed.write_bytes(self.csv_bytes([{
                "game_id": "s1", "season": "2026", "week": "1",
                "kickoff": "2026-09-10T00:20:00+00:00", "game_type": "REG",
                "home_team": "SEA", "away_team": "NE",
                "home_score": "24", "away_score": "21",
                "finalized_at": "2026-09-10T03:30:00+00:00",
            }]))
            output = root / "lab.html"
            captured = datetime(2026, 9, 10, 4, tzinfo=UTC)
            with patch.object(pgo_forecast_lab, "load_archive",
                              return_value=self.synthetic_lock()), \
                    patch.object(pgo_forecast_lab, "_load_snapshot",
                                 return_value=self.synthetic_snapshot()), \
                    patch.object(pgo_forecast_lab, "_load_corrected", return_value=(None, root / "corrected")), \
                    patch.object(pgo_forecast_lab, "_current_utc",
                                 return_value=captured):
                status = pgo_forecast_lab.main([
                    "--snapshot", str(snapshot_dir),
                    "--weekly", str(root / "weekly"),
                    "--captures", str(root / "old-results"),
                    "--record-snapshot-results", str(reviewed),
                    "--source-url", "https://example.com/results.csv",
                    "--output", str(output),
                ])

            self.assertEqual(status, 0)
            capture = snapshot_dir / "results/20260910T040000Z"
            self.assertTrue((capture / "results.csv").is_file())
            self.assertIn("1 of 2 finalized results recorded", output.read_text(encoding="utf-8"))

    def test_cli_result_recording_targets_are_mutually_exclusive(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit):
            pgo_forecast_lab.main([
                "--record-results", "old.csv",
                "--record-snapshot-results", "new.csv",
            ])
        self.assertIn("not allowed with argument", stderr.getvalue())

    def test_weekly_cutoff_is_per_matchup_and_preseason_stays_separate(self):
        snapshot = self.synthetic_snapshot()
        weekly = {"games": [
            {**snapshot["games"][0], "lock_at": "2026-09-09T23:20:00Z",
             "registered_at": "2026-09-07T22:10:00Z",
             "source_generated_at": snapshot["generated_at"]},
            {**snapshot["games"][1], "lock_at": "2027-01-04T00:20:00Z",
             "registered_at": "2026-09-07T22:10:00Z",
             "source_generated_at": snapshot["generated_at"]},
        ], "revisions": []}
        with patch.object(pgo_forecast_lab, "_current_utc",
                          return_value=datetime(2026, 9, 9, 23, 20, tzinfo=UTC)):
            page = pgo_forecast_lab.render_lab(
                self.synthetic_lock(), [], [], snapshot=snapshot, weekly=weekly,
            )
        self.assertEqual(page.count('data-weekly-game-id="'), 2)
        self.assertIn('data-weekly-cutoff="2026-09-09T23:20:00Z">Locked</span>', page)
        self.assertIn('data-weekly-cutoff="2027-01-04T00:20:00Z">Draft</span>', page)
        self.assertIn("September 9, 2026 at 7:20 PM EDT", page)
        self.assertIn("60 minutes before kickoff", page)
        self.assertIn("SEA by 2.5 points", page)
        self.assertLess(page.index("Weekly game forecasts"),
                        page.index("September 7 preseason baseline"))
        self.assertIn('<details class="preseason-archive" id="preseason-baseline">', page)
        self.assertIn('data-snapshot-game-id="s1"', page)
        self.assertIn("Original July/August archive", page)

    @patch('pgo_forecast_lab.load_model_sensitivity', return_value=None)
    def test_weekly_results_use_their_own_verified_forecast_series(self, _sensitivity):
        snapshot = self.synthetic_snapshot()
        weekly = {"games": [{**snapshot["games"][0],
            "lock_at": "2026-09-09T23:20:00Z",
            "registered_at": "2026-09-07T22:10:00Z",
            "source_generated_at": snapshot["generated_at"],
        }], "revisions": []}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reviewed = root / "reviewed.csv"
            reviewed.write_bytes(self.csv_bytes([{
                "game_id": "s1", "season": "2026", "week": "1",
                "kickoff": "2026-09-10T00:20:00+00:00", "game_type": "REG",
                "home_team": "SEA", "away_team": "NE",
                "home_score": "24", "away_score": "21",
                "finalized_at": "2026-09-10T03:30:00+00:00",
            }]))
            weekly_root = root / "weekly"
            with patch.object(pgo_forecast_lab, "load_archive",
                              return_value=self.synthetic_lock()), \
                    patch.object(pgo_forecast_lab, "_load_snapshot",
                                 return_value=snapshot), \
                    patch.object(pgo_forecast_lab, "_load_corrected", return_value=(None, root / "corrected")), \
                    patch.object(pgo_forecast_lab.pgo_forecast_weekly, "load_weekly",
                                 return_value=weekly), \
                    patch.object(pgo_forecast_lab, "_current_utc",
                                 return_value=datetime(2026, 9, 10, 4, tzinfo=UTC)):
                self.assertEqual(pgo_forecast_lab.main([
                    "--snapshot", str(root / "preseason"),
                    "--weekly", str(weekly_root),
                    "--captures", str(root / "legacy"),
                    "--record-weekly-results", str(reviewed),
                    "--source-url", "https://example.com/results.csv",
                    "--output", str(root / "lab.html"),
                ]), 0)
            self.assertTrue((weekly_root / "results/20260910T040000Z/results.csv").is_file())
            self.assertFalse((root / "preseason/results").exists())
            self.assertFalse((root / "legacy").exists())
            page = (root / "lab.html").read_text(encoding="utf-8")
            self.assertIn("1 of 1 saved weekly forecasts have final results", page)
            self.assertIn("0 of 2 finalized results recorded", page)


if __name__ == "__main__":
    unittest.main()
