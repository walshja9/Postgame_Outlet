import copy
from html.parser import HTMLParser
import unittest

import pgo_ats_view as view


def fixture():
    game = dict(game_id='2026_01_SF_LA', home='LAR', away='SF', kickoff='2026-09-11T00:35:00Z',
                lock_at='2026-09-10T23:35:00Z', quote_captured_at='2026-09-10T21:00:00Z',
                issued_at='2026-09-10T21:00:01Z', updated_at='2026-09-10T21:00:01Z',
                pgo_issued_at='2026-09-09T22:26:37Z', pgo_margin=4.266054, model_home_handicap=-4.266054,
                home_handicap=-3.5, away_handicap=3.5, home_edge=.766054, su_pick='LAR', ats_pick='LAR',
                status='CURRENT', source_edition='original <edition>',
                source=dict(href='https://example.test/quote?a=1&b=2',sha256='a'*64),
                win_probability=.6,grade=dict(straight_up_ats='PENDING',ats='PENDING',model_line='PENDING'))
    record=dict(wins=0,losses=0,pushes=0,pending=1)
    return dict(status='READY',checked_at='2026-09-10T21:00:01Z',provider=dict(id='100',name='DraftKings'),
                games=[game],unavailable=[],metrics=dict(ats=dict(record,no_edge=0),straight_up_ats=dict(record,no_pick=0),
                                                       model_line=dict(record,no_pick=0,unavailable=0)))


class ATSViewTests(unittest.TestCase):
    def test_three_records_saved_lines_provenance_and_input_are_preserved(self):
        data=fixture();before=copy.deepcopy(data);page=view.render(data)
        self.assertEqual(data,before)
        for text in ('id="season-ats"','ATS suggestion vs sportsbook line','Winner pick vs sportsbook line',
                     'Winner pick vs PGO projected line','LAR -4.3','LAR -3.5','SF +3.5','DraftKings','LAR -3.5; edge +0.766 NFL points',
                     'Quote captured','ATS selection issued','Prediction lock','Original PGO edition',
                     'original &lt;edition&gt;','a=1&amp;b=2','T-60','Straight-up','No cover probability'):
            self.assertIn(text,page)
        for key in ('quote_captured_at','issued_at','lock_at','pgo_issued_at'):
            self.assertIn(data['games'][0][key],page)
        self.assertNotIn('60.0%',page)
        self.assertNotIn('profit',page.lower())

    def test_away_edge_no_edge_and_push_have_distinct_labels(self):
        data=fixture();game=data['games'][0]
        game.update(pgo_margin=-1.25,model_home_handicap=1.25,home_handicap=3.5,away_handicap=-3.5,
                    home_edge=2.25,su_pick='SF',ats_pick='LAR',grade=dict(straight_up_ats='L',ats='W'))
        page=view.render(data)
        self.assertIn('LAR +1.25',page)  # Precise saved projection in details.
        self.assertIn('LAR +3.5; edge +2.25 NFL points',page)
        self.assertIn('SF: Not covered',page)
        self.assertIn('Covered',page)
        game.update(home_edge=-.25,ats_pick='SF')
        self.assertIn('SF -3.5; edge +0.25 NFL points',view.render(data))
        game.update(home_edge=0.,ats_pick=None,no_edge=True,grade=dict(straight_up_ats='PUSH',ats='NOPICK'))
        data['metrics']['ats'].update(no_edge=1,pending=0)
        page=view.render(data)
        self.assertIn('No projected ATS edge',page)
        self.assertIn('SF: Push',page)
        self.assertIn('No edge',page)
        self.assertIn('Pushes are listed separately',page)

    def test_unavailable_opener_keeps_only_the_real_pgo_projection(self):
        data=fixture();data['games']=[]
        data['unavailable']=[dict(game_id='2026_01_NE_SEA',home='SEA',away='NE',pgo_margin=3.291695,
                                  model_home_handicap=-3.291695,su_pick='SEA',reason='No saved pregame line',
                                  pgo_issued_at='2026-09-09T22:26:37Z',source_edition='original opener',
                                  grade=dict(model_line='L'))]
        page=view.render(data)
        self.assertIn('NE @ SEA',page)
        self.assertIn('SEA -3.3',page)
        self.assertIn('SEA: Below projection',page)
        self.assertIn('SEA -3.291695',page)
        self.assertIn('original opener',page)
        self.assertIn('No saved pregame line',page)
        self.assertIn('Line unavailable',page)
        self.assertNotIn('SEA: Covered',page)
        self.assertNotIn('SEA: Not covered',page)

    def test_own_projection_outcome_is_separate_from_market_cover_and_uses_exact_saved_grade(self):
        data=fixture();game=data['games'][0]
        game['grade']=dict(model_line='L',straight_up_ats='W',ats='W')
        page=view.render(data)
        self.assertIn('LAR: Below projection',page)
        self.assertIn('LAR: Covered',page)
        self.assertIn('full precision',page)
        self.assertIn('one decimal',page)
        self.assertIn('margin error measures closeness',page)
        game['grade']['model_line']='PUSH'
        self.assertIn('LAR: Matched projection',view.render(data))
        game['grade']['model_line']='W'
        self.assertIn('LAR: Exceeded projection',view.render(data))

    def test_stale_escaping_safe_links_and_unique_reading_keys(self):
        data=fixture();game=data['games'][0]
        game.update(status='STALE',stale_reason='Source <script> unavailable',game_id='id"<script>')
        data['provider']['name']='Book <name>'
        page=view.render(data)
        self.assertIn('Stale saved line',page)
        self.assertIn('Source &lt;script&gt; unavailable',page)
        self.assertIn('Book &lt;name&gt;',page)
        self.assertNotIn('<script>',page)
        class Tags(HTMLParser):
            def __init__(self,page):super().__init__();self.items=[];self.feed(page)
            def handle_starttag(self,tag,attrs):self.items.append((tag,dict(attrs)))
        tags=Tags(page).items
        for name in ('id','data-view-key'):
            values=[attrs[name] for _,attrs in tags if name in attrs]
            self.assertEqual(len(values),len(set(values)))
        self.assertTrue(all(attrs.get('data-view-key') for tag,attrs in tags if tag=='details' or 'table-shell' in attrs.get('class','')))
        game['source']['href']='javascript:alert(1)'
        with self.assertRaises(ValueError):view.render(data)

    def test_small_nonzero_values_do_not_round_to_pick_em_and_invalid_values_fail(self):
        data=fixture();game=data['games'][0]
        game.update(pgo_margin=.0004,model_home_handicap=-.0004,home_edge=.0004)
        page=view.render(data)
        self.assertIn('LAR -0.0004',page)
        self.assertIn('edge +0.0004 NFL points',page)
        for value in (float('nan'),float('inf'),True):
            game['model_home_handicap']=value
            with self.subTest(value=value),self.assertRaises(ValueError):view.render(data)
        data=fixture();data['games'].append(copy.deepcopy(data['games'][0]))
        with self.assertRaisesRegex(ValueError,'Duplicate'):view.render(data)


if __name__=='__main__':unittest.main()
