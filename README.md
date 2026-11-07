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
„następna strona” zostaje tylko na końcu ostatniej dołączonej strony.

### Zarządzanie

**Zarządzaj widżetami Filmy** (menu boczne albo Ustawienia skórki → Menu
główne → Filmy): zmiana nazwy, kolejność, usunięcie ostatniej strony,
usunięcie widżetu. Tam też **Maksymalna liczba widżetów** (1–20).

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
