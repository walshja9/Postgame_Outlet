"""Current starter evidence cannot enter the original T-60 workflow."""
import copy
import json
import unittest
from unittest.mock import patch
import tests.test_pgo_expected_starters as expected_fixture
import tests.test_pgo_starter_capture as capture_fixture

class CurrentStarterTests(unittest.TestCase):
 def setUp(self):
  self.f = expected_fixture.ExpectedStarterTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
  self.api = self.f.api
  self.current = self.f.root / 'current-announcements.json'
  p=patch.object(self.api,'CURRENT_CONFIG',self.current,create=True);p.start();self.addCleanup(p.stop)
 def save_current(self):
  self.f.envelope['purpose']='current_projection'
  self.f.envelope.update(started_at='2026-09-13T16:10:00+00:00',captured_at='2026-09-13T16:10:01+00:00',reviewed_at='2026-09-13T16:11:00+00:00')
  ref=self.f.save();self.current.write_bytes(self.f.config.read_bytes());self.f.config.unlink();return ref
 def test_verified_current_starter_after_lock_resolves_without_mutating_locked_inputs(self):
  self.assertTrue(callable(getattr(self.api,'apply_current',None)), 'Separate current starter resolver required')
  ref=self.save_current();before=copy.deepcopy((self.f.selected,self.f.roster,self.f.game))
  chosen,notes=self.api.apply_current(self.f.selected,self.f.roster,[self.f.game],self.f.root,'2026-09-13T16:12:00+00:00')
  self.assertEqual(chosen['ATL'],self.f.player);self.assertEqual(notes[self.f.game['game_id']][0]['source'],ref)
  self.assertEqual((self.f.selected,self.f.roster,self.f.game),before)
 def test_late_current_evidence_is_rejected_by_locked_replay(self):
  ref=self.save_current()
  with self.assertRaises(ValueError):self.api._announcement(self.f.game,ref,self.f.root,'2026-09-13T16:12:00+00:00')
 def test_current_replay_rejects_wrong_purpose_future_identity_and_duplicate_rules(self):
  self.assertTrue(callable(getattr(self.api,'apply_current',None)), 'Separate current starter resolver required')
  self.save_current();config=json.loads(self.current.read_bytes());config['announcements']*=2;self.current.write_text(json.dumps(config))
  with self.assertRaises(ValueError):self.api.apply_current(self.f.selected,self.f.roster,[self.f.game],self.f.root,'2026-09-13T16:12:00+00:00')
  self.save_current();self.f.roster[-1]['status']='RES'
  with self.assertRaises(ValueError):self.api.apply_current(self.f.selected,self.f.roster,[self.f.game],self.f.root,'2026-09-13T16:12:00+00:00')
 def test_current_source_publication_after_kickoff_is_rejected(self):
  self.assertTrue(callable(getattr(self.api,'apply_current',None)), 'Separate current starter resolver required')
  self.save_current();self.f.article['dateModified']='2026-09-13T17:01:00+00:00';self.f.envelope['modified_at']=self.f.article['dateModified'];self.f.body(self.f.envelope,self.f.article)
  self.save_current()
  with self.assertRaises(ValueError):self.api.apply_current(self.f.selected,self.f.roster,[self.f.game],self.f.root,'2026-09-13T17:12:00+00:00')

class CurrentCaptureTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):capture_fixture.StarterCaptureTests.setUpClass()
 def setUp(self):
  self.f=capture_fixture.StarterCaptureTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
  self.api=self.f.api;self.current=self.f.config.with_name('pgo_current_starter_announcements.json')
 def test_late_capture_review_activation_has_separate_purpose_and_configuration(self):
  self.assertIn('purpose',__import__('inspect').signature(self.api.capture).parameters, 'Separate current capture purpose required')
  draft=self.api.capture(capture_fixture.URL,self.f.game['game_id'],'ATL',self.f.player['gsis_id'],self.f.statement,root=self.f.root,fetch=lambda url:self.f.response(),clock=capture_fixture.Clock('2026-09-13T16:10:00+00:00','2026-09-13T16:10:01+00:00'),purpose='current_projection')
  saved=json.loads(draft.read_bytes());self.assertTrue(saved['successful']);self.assertEqual(saved['purpose'],'current_projection')
  with self.assertRaises(ValueError):self.f.review(draft,when='2026-09-13T16:11:00+00:00')
  reviewed=self.api.review(draft,root=self.f.root,config=self.current,clock=capture_fixture.Clock('2026-09-13T16:11:00+00:00'),purpose='current_projection')
  self.api.activate(reviewed,root=self.f.root,config=self.current,clock=capture_fixture.Clock('2026-09-13T16:12:00+00:00','2026-09-13T16:12:01+00:00'),purpose='current_projection')
  self.assertFalse(self.f.config.exists());self.assertTrue(self.current.exists())
  for action in ('capture-current','review-current','activate-current'):
   self.assertIn(action,self.api._parser().format_help())

if __name__=='__main__':unittest.main()
