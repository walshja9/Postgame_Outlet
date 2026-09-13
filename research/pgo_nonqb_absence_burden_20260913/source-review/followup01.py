"""One bounded follow-up to the retained release/tree metadata."""
from concurrent.futures import ThreadPoolExecutor
import json
import capture

tree = json.loads((capture.OUT/'injurybot-tree/response.bin').read_bytes())['sha']
capture.SOURCES = {
    'injuries-2025-current': 'https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_2025.csv',
    'injurybot-fetch': f'https://raw.githubusercontent.com/nflverse/nflverse-injurybot/{tree}/R/fetch.R',
    'injurybot-game': f'https://raw.githubusercontent.com/nflverse/nflverse-injurybot/{tree}/R/game.R',
    'injurybot-auto': f'https://raw.githubusercontent.com/nflverse/nflverse-injurybot/{tree}/auto/update_injuries.R',
    'injurybot-sample-early': 'https://github.com/nflverse/nflverse-injurybot/releases/download/injuries_2024/2024_12_ARI_SEA.rds',
    'injurybot-sample-late': 'https://github.com/nflverse/nflverse-injurybot/releases/download/injuries_2024/2024_12_DET_IND.rds',
}
with ThreadPoolExecutor(max_workers=3) as pool:
    for result in pool.map(capture.capture,capture.SOURCES): print(json.dumps(result),flush=True)
