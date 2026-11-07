# SC Estuary

Skórka Estuary z Kodi 22 (Piers) z jednym dodatkiem: **dowolny folder z dodatku
(np. FanFilm → Filmy → Na czasie) można przypiąć jako wiersz plakatów pod
„Filmy” na ekranie głównym**. Do 20 widżetów, kilka stron listy można połączyć
w jeden widżet.

## Instalacja w Kodi

1. Ustawienia → System → Dodatki → włącz **Nieznane źródła**.
2. Ustawienia → Menedżer plików → **Dodaj źródło** →
   `https://slawomirlewczyk.github.io/sc-estuary/`
   (strona tylko do instalacji z ZIP; samo repozytorium czyta pliki z
   raw.githubusercontent.com, bo Kodi nie odczytuje `.md5` z GitHub Pages)
3. Dodatki → **Zainstaluj z pliku ZIP** → `repository.sc-x.y.z.zip`.
4. Dodatki → **Instaluj z repozytorium** → SC Repository → Skórka → **SC Estuary**.

## Dodanie widżetu

1. Wejdź do folderu w dodatku (np. FanFilm → Filmy → Na czasie).
2. Naciśnij **strzałkę w lewo**, żeby otworzyć menu boczne.
3. W sekcji **Widżety SC** wybierz **Dodaj do widżetów Filmy** →
   **Nowy widżet** i wpisz nazwę (np. „Na czasie”).

### Łączenie stron

Przejdź na stronę 2 tej samej listy i znowu wybierz **Dodaj do widżetów
Filmy** → **Dołącz do: Na czasie**. Obie strony tworzą jeden wiersz, a kafelek
„następna strona” zostaje tylko jeden – na końcu wiersza.

### Ukrywanie zdublowanych filmów

Ustawienia skórki → Menu główne → Filmy → **Ukrywaj zdublowane filmy**.
Film pokazany w widżecie wyżej nie pojawi się w żadnym widżecie niżej
(pierwszeństwo ma kolejność widżetów). Filmy są rozpoznawane po IMDb/TMDb,
a gdy ich brak, po tytule i roku.

### Ukrywanie obejrzanych filmów

Ustawienia skórki → Menu główne → Filmy → **Ukrywaj obejrzane filmy**.
Opcja Kodi „Ukryj obejrzane” działa tylko w oknie listy, nie w widżetach,
dlatego skórka ma własną. Korzysta z oznaczeń dodatku (FanFilm: lokalnie
albo z Trakt).

### Szybkie ładowanie

Widżet od razu pokazuje listę zapamiętaną poprzednio, a nową pobiera w tle
(gdy zapamiętana ma ponad 2 minuty, po obejrzeniu filmu, po powrocie z listy
dodatku na ekran główny, po „Odśwież widżety”). Widżety przeładowują się tylko
wtedy, gdy coś się zmieniło. W menu kontekstowym filmu w widżecie są pozycje
**Oznacz jako obejrzane / nieobejrzane (FanFilm)**.

### Oceny z Filmweb

Ustawienia skórki → Menu główne → Filmy → **Oceny z Filmweb (zapasowo IMDb)**,
a w Ustawieniach skórki → Ogólne → ocena na kafelku ustaw na **Ocena**.
Kafelek pokazuje ocenę Filmweb, a gdy filmu nie da się pewnie dopasować –
ocenę IMDb, a gdy i jej brak – ocenę z dodatku (TMDb).

- Filmweb: nieoficjalne endpointy JSON strony (`/api/v1/live/search`,
  `/film/<id>/info`, `/film/<id>/rating`), 1 zapytanie/s, tylko w tle,
  dopasowanie po tytule i roku (±1); wynik zapamiętany, oceny odświeżane co
  tydzień. Endpointy mogą się zmienić – wtedy zostaje IMDb.
- IMDb: oficjalny zbiór `title.ratings.tsv.gz` (użytek prywatny), czytany w
  locie raz w tygodniu; zapisywane są tylko filmy z widżetów.
- Dane: `userdata/addon_data/script.sc.widgets/ratings.json`.

### Sortowanie po ocenie

Ustawienia skórki → Menu główne → Filmy → **Sortuj widżety od najwyższej
oceny**. Kolejność: ocena Filmweb, a gdy jej brak – IMDb, a potem ocena z
dodatku. Filmy bez oceny trafiają na koniec, kafelek „następna strona” zawsze
jest ostatni. Z włączonymi ocenami Filmweb kolejność ustala się w miarę, jak
oceny dochodzą w tle.

### Zarządzanie

**Zarządzaj widżetami Filmy** (menu boczne albo Ustawienia skórki → Menu
główne → Filmy): zmiana nazwy, kolejność, usunięcie ostatniej strony,
usunięcie widżetu, a na górze listy **Odśwież widżety** (czyści pamięć
FanFilm i przeładowuje widżety bez restartu Kodi). W ustawieniach skórki jest
też **Maksymalna liczba widżetów** (1–20).

Logika widżetów jest w dodatku `script.sc.widgets` (instaluje się razem ze
skórką). Lista widżetów: `userdata/addon_data/script.sc.widgets/widgets.json`.

## Budowanie

```
python3 build.py
```

Pakuje `repository.sc/`, `script.sc.widgets/` i `skin.sc.estuary/` do `docs/` (publikowanego przez
GitHub Pages) i generuje `addons.xml`, `addons.xml.md5` i `index.html`.
Przed wydaniem nowej wersji podbij `version` w `skin.sc.estuary/addon.xml`;
Kodi zaktualizuje skórkę automatycznie.

## Licencja

Na podstawie Estuary (phil65, Ichabod Fletchman, Team Kodi) –
CC BY-SA 4.0 / GPL-2.0. Zobacz `skin.sc.estuary/LICENSE.txt`.
