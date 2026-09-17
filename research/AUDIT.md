# AUDYT RESEARCHU (17.09.2026) — co mamy, czego brakuje, co dalej

## Pokrycie vs plan 30 bloków
| Blok | Status | Wolumen | Uwagi |
|---|---|---|---|
| 01 Reddit | ✅ pełny | 430 wątków, 1458 kom. | Arctic Shift API; comiesięczne Q-thread do stałego scrapa |
| 02 Forum tibia | 🟡 częściowy | board Nevia (6) + 1 wątek | TODO: Gameplay board, Nevia-Trade boardid |
| 03 TibiaQA | 🟡 częściowy | ~15 Q&A | filtry dat; reszta do zebrania tagami hunting/loot (API brak — snippet-harvest) |
| 04 Tibiopedia | 🟡 częściowy | feed update'ów, tabele | forum bot-wall; hunting_places/all do dogrania z sesji przeglądarkowej |
| 05 Rookie | ✅ dla zakresu | metodologia + wzór XP + progi | treści Rook-only (nas nie dotyczy dalej) |
| 06 BR | 🟡 częściowy | newsy 2026 | treści łowieckie stare; forum 403 |
| 07 ES | ✅ mały | Duality/Magazine | odrzucenia udokumentowane |
| 08 Guides | ✅ warstwa kontrolna | Vault63 CSV + MMOKB + Buddy + Pal | pełny scrape Buddy (595) wymaga JS-sesji |
| newsy CipSoft | ✅ feed | events.json działa | — |

## Czego brakuje (priorytet)
1. **Gameplay board tibia.com** — największa dziura community: setki wątków hunting 2026. Metoda: paginacja board + tematy z "hunt/exp/profit".
2. **TibiaQA tag-harvest** — /tag/hunting, /tag/loot, sortowanie po dacie; cel 100+ pytań 2026.
3. **TibiaBuddy Hunt Finder (595)** — JS; opcje: (a) sesja przeglądarkowa użytkownika (export), (b) snippet-harvest per voc (mamy EK/RP/Mage/Monk/Team częściowo), (c) odpuścić (mamy Vault63 + MMOKB jako kontrolę).
4. **Monthly Q-threads Reddit** — comiesięczny dopływ: dopisać do research-crona (osobny workflow?).
5. **Nevia-Trade boardid** — niski priorytet (oferty handlowe, nie hunting).
6. **Tibiopedia hunting_places scrape** — wymaga ominięcia bot-walla (nie priorytet; mamy Vault63).
7. **Drop-rate'y** — floor: progi bestiary (mamy); ceiling: brak publicznego źródła. Nie szukać dalej bez nowego tropu.

## Ryzyka korpusu
- Snippet-harvest: daty z wyszukiwarki bywają datami posta ~modyfikacji; przy roszczeniach liczbowych wymagać pełnego odczytu.
- Poradniki kuratorowane (Buddy/Vault/MMOKB) to NIE sesje — w apce tylko jako fallback z badgem.
- Stare wątki PL (2014–2018) kuszą objętością — zero liczb do apki, tylko klimat/metodologia.
