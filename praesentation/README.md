# Abbildungen für die Abschlusspräsentation

Erzeugt von `figuren_praesentation.py`. Jede Abbildung liegt in `hell/`
(für Beamer und Ausdruck) und `dunkel/` (passend zum Aussehen der
Anwendung), je als PNG (200 dpi) und PDF (Vektor).

Neu erzeugen:

    .venv/bin/python figuren_praesentation.py          # alle
    .venv/bin/python figuren_praesentation.py B2 B3    # einzelne

**Einheitliche Verarbeitung für alle Bedingungen:** Hochpass 1 Hz + Notch
50 Hz nullphasig (`sosfiltfilt`), Fenster −200 bis 2000 ms, erste 10
Impulse verworfen, robuste Ausreißerabweisung `mad_k=3.5`, ROI Fz+Cz+Pz.

## A — System und Methode

| Datei | Kernaussage |
|---|---|
| `A1_verarbeitungskette` | Vier Schritte vom Rohsignal zum ERP. Der Gleichanteil liegt bei ~10⁵ µV, die gesuchte Antwort bei ~5 µV — ohne Filterung und Mittelung ist sie unsichtbar. |
| `A2_filter_kausal_vs_nullphasig` | Offline wird zweimal gefiltert, vorwärts und rückwärts. Der sichtbare Zeitversatz der Live-Kurve ist die Laufzeit des kausalen Filters — genau das, was offline entfällt. |
| `A3_triggerauswahl` | Jede Epoche mit Begründung: Einlaufphase verworfen, Ausreißer robust abgewiesen. Die Grenze kommt aus dem Median dieser Aufnahme, nicht aus einem festen µV-Wert. |
| `A4_mittelungsgewinn` | Gegenprobe mit zufällig gesetzten Triggern in derselben Aufnahme. Bei n=5 findet die Gipfelsuche auch dort 7 µV, wo nichts ist. Unter ~30 Epochen ist eine Amplitudenangabe ohne Kontrolle nicht belastbar. |
| `A5_kanaluebersicht` | Alle acht Kanäle. Die Antwort ist zentral (Fz/Cz/Pz), nicht überall — das rechtfertigt die ROI. |

## B — Messreihe 09.09. (Reizkopf und Körperstelle)

| Datei | Kernaussage |
|---|---|
| `B1_serie_uebersicht` | Alle fünf Bedingungen. Nach etwa 500 ms ist nichts mehr da — das lange Fenster war die richtige Prüfung, das Ergebnis ist ein sauberes Nein. |
| `B2_koerperstelle_oberschenkel_wade` | **Oberschenkel → Wade: +45 ms** [−72, +141], p = 0.60; Kreuzkorrelation −5 ms [−37, +47]. Kein Cluster mit p < 0.05. Die beiden Maße widersprechen sich im Vorzeichen. |
| `B3_reproduzierbarkeit` | **Die wichtigste Abbildung.** Wade/normaler Kopf zweimal gemessen, 11 Minuten auseinander: **107 ms** Latenzunterschied, wo per Aufbau keiner sein kann. Der gesuchte Effekt (45 ms) ist kleiner als die Wiederholbarkeit. |
| `B4_akustisch_vs_hautreiz` | Der Hautreiz unterscheidet sich von der **Kontrolle** bei **121–161 ms** (p = 0.048) — bei in beiden Bedingungen gedämpfter Akustik. Die Antwort ist also somatosensorisch, nicht akustisch. |
| `B5_nachweisgrenze` | Künstlich verschobene Kopien der eigenen Daten zurückgemessen. Der Betrag stimmt, aber der Vertrauensbereich ist ~±90 ms breit. |
| `B6_tfr_gitter`, `B6b_tfr_differenz` | Zeit-Frequenz, gemeinsame Farbskala. Achtung: das tiefe Band ist durch das 1000-ms-Fenster um ±500 ms verschmiert und taugt nicht als Latenzangabe. |

Epochenzahlen: Kontrolle 49 · Oberschenkel L 45 · Wade L 25 · Wade K (1) 29 · Wade K (2) 21.

**Die ganze Septemberreihe lief mit Noise-Cancelling.** `163744` ist damit
keine Reizton-Bedingung, sondern die **Kontrolle**: kein Hautreiz bei
gedämpfter Akustik, das Gegenstück zu `keinReiz` vom 13.08. Die Daten
bestätigen es — keine frühe Negativität (+3,8 µV gegen −6,4 µV bei der
ungedämpften Bedingung). Eine ungedämpfte Bedingung gibt es in dieser
Reihe nicht; der Akustikvergleich ist nur mit der Augustreihe möglich.

## D — Applikatorvergleich: **zurückgezogen**

Die Abbildungen D1 und D2 sind entfernt. Sie verglichen Linse gegen
normalen Reizkopf und stützten sich auf die Aufnahmen `170018` und
`171102` — bei denen das Stoßwellengerät Probleme machte. Der Vergleich
hätte das Gerät gemessen, nicht den Applikator. Der Code bleibt in
`figuren_praesentation.py` erhalten, falls die Messung sauber wiederholt
wird.

Mit ihnen entfällt auch die daraus abgeleitete Rauschgrenze von 107 ms.
Ersatz siehe Abschnitt E: zwei Kontrollaufnahmen von Messtagen drei Wochen
auseinander, sowie Hälften derselben Reizbedingung.

## E — Die drei tragfähigen Vergleiche

| Datei | Kernaussage |
|---|---|
| `E1_akustische_daempfung` | **Referenz, und das stärkste Ergebnis.** Drei Bedingungen ohne Hautreiz. Die ungedämpfte weicht von der Kontrolle des 13.08. bei **8–60 ms ab (p = 0.009)** und von der des 09.09. bei **0–72 ms (p = 0.011)** — zweimal dasselbe Fenster, an verschiedenen Messtagen. Die beiden gedämpften Kontrollen unterscheiden sich untereinander **nicht** (bestes p = 0.72). Die Dämpfung wirkt, und die Verarbeitungskette ist über Tage reproduzierbar. |
| `E2_koerperstellen_beide_tage` | Proximal gegen distal an beiden Tagen, gleiche y-Skala. Tag 1 (normaler Kopf, ~1,10 m): Latenz **+32 ms** [−11, +55]. Tag 2 (Linse, ~0,45 m): **−2 ms** [−39, +54]. Kein Cluster mit p < 0.05. |
| `E3_uebersicht_amplitude_latenz` | Alle Vergleiche gegen ihre eigene Nachweisgrenze. Amplitude in zwei Fenstern (früh/spät), **rauschbereinigt**; Latenz mit den Erwartungen für Aδ (Schmerz) und Aβ (Berührung) eingezeichnet. |

**Warum zwei Amplitudenfenster.** Der akustische Anteil liegt vor 100 ms,
die Antwort auf den Hautreiz danach. Je Vergleich das passende Fenster zu
wählen wäre Rosinenpickerei — deshalb wird jede Zeile in beiden bewertet.

**Warum rauschbereinigt.** Der rohe RMS des Mittelwerts enthält noch
σ²/n an Rauschen. Zwei Bedingungen mit gleichem n, aber unterschiedlich
unruhigen Einzeltrials unterscheiden sich darin schon ohne jeden
Signalunterschied. Mit `evoked_rms` fällt zum Beispiel
„Wade − Kontrolle Tag 2“ von scheinbar +1,4 µV (p = 0.05) auf
+0,9 µV mit einem Bereich, der die Null einschließt.

**Was die Latenzspalte zeigt.** Bei Tag 1 (~1,10 m Wegunterschied) liegt
die Messung [−11, +55] ms auf der Aβ-Erwartung (+22 ms) und **unterhalb
der Aδ-Erwartung** (+73 bis +110 ms). Die Daten sind also nicht mit einer
langsamen nozizeptiven Leitung vereinbar, wohl aber mit schneller
Berührungsleitung. Bei Tag 2 (~0,45 m) liegen beide Erwartungen im
Vertrauensbereich — dieser Vergleich kann nicht unterscheiden.

**Einordnung mit dem subjektiven Bericht.** Bei der Linse war kaum Schmerz
spürbar. Dazu passt beides: die rauschbereinigten Amplituden der
Tag-2-Bedingungen heben sich kaum von der Kontrolle ab, und die Latenz
zeigt keine Aδ-Signatur. Eine Antwort im EEG ist ohnehin kein Nachweis von
Schmerz — ein Gerät, das mechanisch Kontakt hat, erzeugt auch ohne
Schmerzempfindung eine Berührungsantwort.

## C — Messreihe 13.08. (Fuß, Oberarm, Akustikkontrolle)

**Versuchsaufbau — zwei Faktoren, nicht einer.** Alle vier Bedingungen
unterscheiden sich in **Hautreiz** (ja/nein) und **Akustik**
(gedämpft/ungedämpft, d. h. Noise-Cancelling-Kopfhörer an oder aus):

| Bedingung in der Abbildung | Hautreiz | Akustik |
|---|---|---|
| Fuß · Akustik gedämpft | Fuß | gedämpft |
| Oberarm · Akustik gedämpft | Oberarm | gedämpft |
| kein Hautreiz · Akustik gedämpft | — | gedämpft |
| kein Hautreiz · Akustik ungedämpft | — | ungedämpft |

Entscheidend: **die beiden Reizbedingungen liefen bereits mit
Kopfhörern.** Der akustische Anteil ist dort also schon unterdrückt —
die ungedämpfte Bedingung misst nicht eine Störung in den Messdaten,
sondern **was die Dämpfung entfernt.**

| Datei | Kernaussage |
|---|---|
| `C1_fuss_vs_oberarm` | Größter Abstandsunterschied im Datensatz, beide mit Dämpfung. **+16 ms** [−39, +108], p = 0.79; Kreuzkorrelation +15 ms [−18, +47]. Erwartet bei Aδ-Leitung wären +70 bis +110 ms — das schließt das Intervall aus. |
| `C2_akustisch_vs_kontrolle` | **Was das Noise-Cancelling entfernt.** Beide Bedingungen ohne Hautreiz, nur die Dämpfung unterscheidet sich: Cluster **8–52 ms, p = 0.021**, rund −6 µV. Ein Anteil in der Größenordnung der somatosensorischen Antwort — den die Kopfhörer wegnehmen. |
| `C3_energie_nach_zeitfenster` | Die zeitliche Trennung: der von der Dämpfung betroffene Anteil liegt **vor 150 ms**, die Antwort auf den Hautreiz **danach**. Die Kopfhörer greifen genau dort, wo die Störung sitzt, ohne die Antwort anzutasten. |

**Epochenzahl angeglichen.** Die Kontrolle hat 68 Trigger gegen 40 bei der
ungedämpften Bedingung; nach `drop_first=10` wären das 58 gegen 29
gewesen. Deshalb zusätzlich `last=29` (`PARAM_AUG13`), sodass alle vier
bei n = 26–29 liegen. Das ist keine Kosmetik — der Mittelwert der
Kontrolle wäre sonst allein wegen der doppelten Epochenzahl glatter.

**Das Ergebnis hängt an der Auswahl.** Derselbe Vergleich:

| Auswahl | n (unged. / ged.) | Cluster |
|---|---|---|
| `last=40` | 37 / 40 | 12–77 ms, p = 0.006 |
| `drop_first=10` allein | 29 / **58** | keiner, bestes p = 0.100 |
| `drop_first=10, last=29` | 28 / 29 | 8–52 ms, p = 0.021 |

Bei ungleichem n fällt der Befund durch; bei angeglichenem n hält er,
mit etwas engerem Fenster. Beim Vortragen dazusagen.

## Was die Zahlen tragen

Eine Person, je 21–49 Epochen, Bedingungen **nacheinander** aufgenommen.
Aussagen gelten für diese Messungen, nicht allgemein. Die
Reproduzierbarkeitsmessung (B3) ist der Maßstab: Unterschiede unter etwa
100 ms sind mit diesem Aufbau nicht deutbar.

Der größte Hebel für die nächste Messung: **Bedingungen innerhalb einer
Aufnahme abwechseln.** Dann trägt jede Bedingung dieselbe Drift, und der
Unterschied bleibt als Unterschied stehen.
