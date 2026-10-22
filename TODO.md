# To do

Tick a box with `[x]` and move the line to Done when finished.

## Open

- [ ] **1. Correctness check.** Audit the parsing and the budget arithmetic sector by sector.
  - [x] Find out why some sectors have missing budget (available minus funded). Not a parsing error: funded sums match the rows exactly, and the money is split in two pools (under-40, ordinary) that cannot be combined. Every leftover is below the smallest possible project (1.0 M EUR, the minimum funded contribution in the data) in its pool, or the pool has no eligible project left (SH4: 1.50 M EUR, no unfunded under-40 project; LS6: only 5 projects ranked, all funded). Report now states the unfunded total, the 16 sectors below the smallest contribution, and LS6.
  - [x] Check the remaining sectors for parsing errors like the LS6 under-40 one. Independent check on all 19 Tabella A PDFs: ranks consecutive, scores non-increasing, no duplicate codes, funded set equals Tabella B, PI surnames match Tabella B, and a pixel scan of the rendered pages finds the same 51 under-40 rows as the parser (240 of 240 rows seen, no misses). The scan script is not in the repo.
- [ ] **2. More fact sheets**, like the Siena one.
  - [x] Tied to the author's past: Basilicata, Pisa, Scuola Normale Superiore.
  - [x] Tied to the author's funded project: Padova, Brescia, Bolzano, Basilicata, Torino. Built as `report/factsheets.pdf` from `data/factsheets.txt`; the workflow rebuilds it.
- [ ] **3. Deeper analysis by GSD within chemistry**, especially PE5 and PE4 (PE4 not yet published).
  - [x] Write it generally, so it extends to any sector: `focus.py`, driven by the code prefixes of `data/focus.txt`.
  - [x] Produce results only for the chemistry sectors: `report/focus.pdf`, one page per GSD CHEM-01 to CHEM-07 (the GSD is that of the unit leaders only; no per-GSD staff data exist).
  - [ ] PE4: nothing to do until it is published (the workflow rebuilds `focus.pdf`).
  - [ ] Decide whether per-GSD analyses of the team (not only the leaders) are wanted: needs the GSD of every team member, which the tables do not give.
- [ ] **4. A posteriori "dream team" analysis.** Which team composition (institutions, career levels, gender, GSD mix, under-40 PI) goes with being funded?
  - [ ] Chemistry first.
  - [ ] Written so it extends to any sector.

## Watch

- [ ] When the next sector is published, check the under-40 count in the PR text (a new Tabella A layout could misparse).
- [ ] PR email never arrived (every run was triggered by the owner; probably needs "Include your own updates" in GitHub notification settings).
- [ ] Institutions like INGV (national research bodies) cannot be guessed by `complete_tables()`: classify by hand.

- [ ] GSD lookup of the 64 LS5 leaders: the MUR portal answered 403 (CloudFront block) on 2026-10-22, from GitHub and from here. Retry `python3 gsd.py` later; if the block lasts, find another way. The `GSD_CACHE` secret is older than the local cache (726 against 752 rows): refresh it after the lookup.

## Done

- [x] Under-40 detection when only the PI name is green (LS6, SH5).
