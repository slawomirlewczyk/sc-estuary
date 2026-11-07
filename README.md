# SC Estuary

Skórka Estuary z Kodi 22 (Piers) z jednym dodatkiem: **dowolny folder z dodatku
(np. FanFilm → Filmy → Na czasie) można przypiąć jako wiersz plakatów pod
„Filmy” na ekranie głównym**. Maksymalnie 3 widżety.

## Instalacja w Kodi

1. Ustawienia → System → Dodatki → włącz **Nieznane źródła**.
2. Ustawienia → Menedżer plików → **Dodaj źródło** →
   `https://slawomirlewczyk.github.io/sc-estuary/`
3. Dodatki → **Zainstaluj z pliku ZIP** → `repository.sc-x.y.z.zip`.
4. Dodatki → **Instaluj z repozytorium** → SC Repository → Skórka → **SC Estuary**.

## Dodanie widżetu

1. Wejdź do folderu w dodatku (np. FanFilm → Filmy → Na czasie).
2. Naciśnij **strzałkę w lewo**, żeby otworzyć menu boczne.
3. W sekcji **Widżety SC** wybierz **Dodaj do widżetów Filmy**.

W tym samym menu są przyciski **Usuń z widżetów Filmy** (gdy jesteś w już
przypiętym folderze) oraz **Wyczyść widżety Filmy**.

## Budowanie

```
python3 build.py
```

Pakuje `repository.sc/` i `skin.sc.estuary/` do `docs/` (publikowanego przez
GitHub Pages) i generuje `addons.xml`, `addons.xml.md5` i `index.html`.
Przed wydaniem nowej wersji podbij `version` w `skin.sc.estuary/addon.xml`;
Kodi zaktualizuje skórkę automatycznie.

## Licencja

Na podstawie Estuary (phil65, Ichabod Fletchman, Team Kodi) –
CC BY-SA 4.0 / GPL-2.0. Zobacz `skin.sc.estuary/LICENSE.txt`.
