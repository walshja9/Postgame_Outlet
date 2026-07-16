# Launch package — two paste-ready articles + admin walkthrough

Everything below is grounded in the published Preseason 2026 board (snapshot
7/16). Byline both articles Sean McCabe unless he wants otherwise. Blog:
**poweratings**. Save as **Draft** (visibility Hidden) — they go live at
cutover with everything else.

---

## Article 1 — tag `nfl, power-ratings`

**Title:** The Preseason 2026 Power Ratings are live

**Excerpt/deck (metafield custom.deck):** All 32 teams, one number each:
points above or below a league-average team on a neutral field. Here's how
the board opens the season.

**Body:**

The full Postgame Outlet NFL Power Ratings board is now live — all 32 teams,
each carrying a single number: how many points better or worse than a
league-average team they'd be on a neutral field. Every rating is the
straight sum of a quarterback value, a non-QB offense value, and a defense
value, so you can always see exactly where a number comes from. The full
methodology is on the [methodology page](/pages/methodology-preview).

**The top of the board.** The Rams open at +7.5, the league's best. Matthew
Stafford's +5.5 is the second-highest QB value on the board, and an offseason
that added Myles Garrett to the defense did the rest. Buffalo sits right
behind at +7.0 on the strength of the board's top QB value — Josh Allen at
+6.5 — and a big skill add in DJ Moore. Seattle at +6.0 is the interesting
one: Sam Darnold carries a modest +2.0, but the roster around him grades as
one of the most complete in football.

**The bottom.** The Jets open last at -5.5, and it's not the defense — that
unit added Minkah Fitzpatrick and Demario Davis and grades well. It's a thin
skill group and a -2.0 QB value for Geno Smith. Miami (-4.5) is one spot up
after an offseason that gutted the receiver room.

**Where the board disagrees with the market.** That's the point of
publishing it. Every edition is dated, snapshotted, and preserved — this one
is labeled Preseason 2026 — so when the season starts scoring our numbers,
the receipts are already on the table. Our correction and accountability
rules are [here](/pages/accountability-preview).

Ratings update through the season as injuries, trades, and actual games move
the numbers. [See the full board.](/pages/power-ratings)

---

## Article 2 — tag `nfl, dynasty`

**Title:** What the preseason board says about dynasty QBs

**Excerpt/deck:** Reading the Power Ratings QB values through a dynasty
lens: where the points and the birthdays point in different directions.

**Body:**

Our Power Ratings assign every starting quarterback a value in points versus
an average starter. That's a win-now number — but crossed with age, it's a
dynasty map. A few things stand out on the Preseason 2026 board.

**The prime-age tier is stacked.** Josh Allen leads the board at +6.5 at age
30, with Joe Burrow (+5.0, 30), Lamar Jackson (+4.5, 29), and Patrick
Mahomes (+4.5, 31) right behind. Elite production, but in dynasty terms
you're paying peak price for the back half of a prime.

**The value is one tier down.** Drake Maye (+3.0 at 24, entering year three)
and Caleb Williams (+3.0 at 25) already grade within striking distance of
the elites at ages where the arrow still points up. Jayden Daniels (+2.0 at
26) is in the same conversation. If the board is right about them, these are
the QB values that appreciate.

**The other direction.** Matthew Stafford's +5.5 is the second-best QB value
in football — at 38, in year seventeen. For the Rams' 2026 win total, that's
gold; for a dynasty roster, it's a number with a countdown attached. Aaron
Rodgers (-1.0) and Kirk Cousins (-2.5) show where that road ends.

The full 32-QB table is on the [ratings board](/pages/power-ratings) under
the QB Ratings tab, with methodology and accountability rules linked from
there. These values will move all season — that's the point of tracking them
in public.

---

## Admin walkthrough (Shopify, ~15 min)

### A. Metafield definitions (Settings → Custom data → Blog posts → Add definition)
Create 9, none marked required. Namespace/key must match exactly:

| Name | Namespace and key | Type |
|---|---|---|
| Deck | `custom.deck` | Single line text |
| Byline | `custom.byline` | Single line text |
| Updated at | `custom.updated_at` | Date and time |
| Model version | `custom.model_version` | Single line text |
| Key takeaway | `custom.key_takeaway` | Multi-line text |
| Sources | `custom.sources` | Multi-line text |
| Methodology | `custom.methodology` | Single line text |
| Correction history | `custom.correction_history` | Multi-line text |
| Related product | `custom.related_product` | Product |

### B. Supporting pages (Content → Pages)
Paste the three copies from `2026-07-16-supporting-page-copy.md` into
methodology-preview / accountability-preview / authors-preview. Plain rich
text is fine (no iframes here). **Leave visibility Hidden.** Authors page
still needs Sean's 1–2 sentence bio.

### C. Articles (Content → Blog posts → Add, blog = poweratings)
Paste the two articles above. Tags exactly as listed (`nfl, power-ratings`
and `nfl, dynasty` — lowercase). Set byline metafield to Sean McCabe, deck
metafield to the excerpt line. **Save as Hidden/Draft.**

At cutover the -preview links inside the article bodies get swapped with the
rest of the URL ledger.
