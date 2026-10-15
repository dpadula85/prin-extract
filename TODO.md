# To do

Tick a box with `[x]` and move the line to Done when finished.

## Open

- [ ] **1. Correctness check.** Audit the parsing and the budget arithmetic sector by sector.
  - [x] Find out why some sectors have missing budget (available minus funded). Not a parsing error: funded sums match the rows exactly, and the money is split in two pools (under-40, ordinary) that cannot be combined. Every leftover is below the smallest possible project (1.0 M EUR, the minimum funded contribution in the data) in its pool, or the pool has no eligible project left (SH4: 1.50 M EUR, no unfunded under-40 project; LS6: only 5 projects ranked, all funded). Still to do: add this note to the report next to the available-vs-funded figure.
  - [ ] Check the remaining sectors for parsing errors like the LS6 under-40 one.
- [ ] **2. More fact sheets**, like the Siena one.
  - [ ] Tied to the author's past: Basilicata, Pisa, Scuola Normale Superiore.
  - [ ] Tied to the author's funded project: Padova, Brescia, Bolzano, Basilicata, Torino.
- [ ] **3. Deeper analysis by GSD within chemistry**, especially PE5 and PE4 (PE4 not yet published).
  - [ ] Write it generally, so it extends to any sector.
  - [ ] Produce results only for the chemistry sectors.
- [ ] **4. A posteriori "dream team" analysis.** Which team composition (institutions, career levels, gender, GSD mix, under-40 PI) goes with being funded?
  - [ ] Chemistry first.
  - [ ] Written so it extends to any sector.

## Watch

- [ ] When the next sector is published, check the under-40 count in the PR text (a new Tabella A layout could misparse).
- [ ] PR email never arrived (every run was triggered by the owner; probably needs "Include your own updates" in GitHub notification settings).
- [ ] Institutions like INGV (national research bodies) cannot be guessed by `complete_tables()`: classify by hand.

## Done

- [x] Under-40 detection when only the PI name is green (LS6, SH5).
