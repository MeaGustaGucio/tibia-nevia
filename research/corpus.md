# KORPUS WIEDZY — destylat z researchu (v1, 17.09.2026)
# Zasada: tylko fakty z data + zrodlem. Konflikty: nowsze wygrywa + adnotacja.
# Surowe dane: research/blocks/<nn>_<blok>/{posts.jsonl,comments.jsonl,urls.txt,NOTES.md,claims.jsonl}

## 1. MECHANIKA (twarde, 2026)
- Share EXP po rebalansie VI.2026: duo 2 voc **35%** (bylo 30), trio 3 voc **70%** (bylo 60); solo/team x4 bez zmian. [TibiaQA 20.06.2026] → POPRAWIONE na stronie.
- Formuła: exp/głowę = baza × bonus_voc / graczy (× stamina/prey osobno). Duo ED+EK: potwor 1000 → 675/głowę.
- Stamina: 42:00–39:00 premium +50%; <14:00 50% exp + brak loota; regen 3:1 + 10 min opoznienia. [Wiki/TibiaPlan]
- RED w markecie = systemowy warning: sell ≥ +25% sredniej serwera, buy ≤ −25% (manual Tibii). [manual + weryfikacja]
- Hazard Gnomprona: loot-bonus z hazard level USUNIĘTY 07.09.2026 (exp bez zmian). [newsy]
- Nerf golda 07.09.2026: Vexclaw −11%, Hellflayer/Grimeleech −12%, Rotten Blood −7…−17% i in. [newsy]
- Powerful imbue = 250k fee + ~350k itemy ≈ 600k/20h; scroll ~700k; intricate MANA minimalnie lepszy zł/% (250k/5% vs 450k/8%). [reddit 2026]
- x2 Intricate vs Powerful Void (ED200, 550k dmg/h): intricate minimalnie lepszy bilans. [reddit]
- RP najdroższa w supplies (strzały ~130 gp/szt); EK/ED/MS potrafią ~0 potów. [reddit]
- Bez imbu T3 (mana/life leech) spawny 100+ praktycznie nieosiągalne. [reddit, wielokrotnie]
- CipSoft mierzy też top graczy per przedział (solo balance). [reddit]

## 2. SPOTY — liczby graczy 2026 (do konfrontacji z rankingami apki)
- Iksupan 50–120: 400k–1,2kk raw + 150–450k profit; 52 ED: 600–800k + 150–300k. [reddit ×2]
- Mutated Tigers EK73: 57 min, 160+90 killi, 328k exp + 148k profit. [reddit]
- Carlin Cults RP: 1,2kk raw solo → 1,5kk z diamentami; Werehyenas N (226): 2–2,1kk raw. [reddit]
- Edron Heroes -2/-3 (EK136): 1,4–1,5kk raw + 150k profit (crown stuff, blood priests). [reddit]
- EK365: Grims Yala 3,1kk; Wreckoning 2,35kk (profit); Banuta -4 2,7kk. [reddit]
- Summer Court 315 ED: 4,5kk raw + 400–600k. [reddit]
- Nagas 344 ED: 5,1kk raw peak + 300k (bez charm/prey). [reddit]
- Duo ED-EK: 150–250 Werehyena/Gazer/Lava → 250+ Burster → 300+ Werelion/Ripper; ED206+EK250: Werehyena N/S 1,7kk + 480k total. [reddit ×2]
- Team x4 ~200–360: Cathedral -8 7kk (150%), Cobra 6,6kk, Azzilon 6,8kk. [reddit]
- High: Norcferatu E 11,5kk + 1,8kk (1050 EK); Cobras 11,5kk + 2,5kk; Rosha West 660 RP 9kk 0-supply. [reddit]
- Renegade Quaras (EK274): 2,1kk/h + 200k (BEZ delivery items!). [reddit]
- Wreckoning/Medusa/Banuta i in. — pełna lista w blokach.

## 3. EKONOMIA / MANIPULACJE
- Nevia: dominando trzymają tanio fusion-items, drogo resztę (13.09.2026, board Nevia). [forum tibia]
- Uzasadnia: red-filter, capy per item, podejrzenie cienkich rynków (niski depth = łatwa manipulacja).
- Delivery tasks pompuja ceny (osobny dataset w apce: delivery_items 451 + TibiaPal 964).
- Imbu-mat Dell: teeth→Vampirism, belt→Void (25×) — popyt strukturalny. [Wiki]

## 4. SPORNE / DO WERYFIKACJI
- Liczby TibiaPal/YT vs real graczy (853 RP nie dobija do filmów) — kalibrować, nie ufać ślepo.
- "Serwery 200 vs 800 online" — contestacja zmienia realne exp/h; brak danych per serwer.
- Monk w TH: mieszane głosy ("Are monks not wanted in TH?" — do doczytania).

## 5. KOLEJKA BLOKÓW (status)
- ✅ 01 reddit (430 wątków, 1458 kom., NOTEs+claims)
- 🟡 02 forum tibia (Nevia board + 1 wątek; TODO: Gameplay board, Nevia-Trade boardid)
- ✅ 03 TibiaQA (dyscyplina dat; 2026-zweryfikowane + ponadczasowe z adnotacją)
- ✅ 04 Tibiopedia (feed update'ów z % balansu! tabele hunting_places do scrapa w fazie C)
- ✅ 05 Rookie (Rook-only treściowo; metodologia + wzór XP + progi bestiary loot!)
- ⬜ 06 BR (PortalTibia/TibiaBR/TibiaLife), 07 ES (Duality/Magazine), 08+ guides (Buddy/Vault/MMOKB/Pal/Monk/Route)

## 6. DELTA v2 (17.09.2026, bloki 03–05)
- Wzór XP: bonusy ADDYTYWNE do bazy, mnoży tylko stamina ×1,5 (Rookie + TibiaQA 2020, ponadczasowe). → POPRAWIONE na stronie.
- W double EXP: prey na DMG > prey na EXP (więcej killi skaluje się z eventem).
- Drop-rate'y (rzadkość!): Gloom Wolf ~8%, Amazon charm ~5%, Culty rope belt 5–10%, maska 10% enlightened. [TibiaQA 2025]
- Bestiary progi: >25% / 5–25% / 1–5% / 0,5–1% / <0,5% → przyszłe boundy modelu dropu.
- Delivery: +produkty Soul War/Rotten Blood (05.2026) — watchlista delivery do rozszerzenia!
- Stare wątki PL (2014–2018) odrzucane liczbowo; metodologia Rookie (3 runy, R²) jako wzorzec raportowania.
