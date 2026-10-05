#!/usr/bin/env python
"""figuren_praesentation.py — Abbildungssatz für die Abschlusspräsentation.

Erzeugt alle Abbildungen in `praesentation/hell/` und `praesentation/dunkel/`,
je als PNG (200 dpi, für Folien) und PDF (Vektor, scharf bei jeder
Projektorauflösung).

    .venv/bin/python figuren_praesentation.py            # alles
    .venv/bin/python figuren_praesentation.py A1 B3      # nur einzelne

Gliederung:
  A  System und Methode  — wie die Verarbeitungskette arbeitet
  B  Messreihe 09.09.    — Reizkopf (Linse / normaler Kopf) und Körperstelle
  C  Messreihe 13.08.    — Fuß / Oberarm und der akustische Störanteil

Alle Bedingungen werden mit **identischen** Parametern gerechnet (PARAM):
gleiche Filterkette, gleiches Fenster, gleiche Auswahlregel. Sobald man an
einer Bedingung anders dreht als an einer anderen, zeigt der Vergleich die
Verarbeitung statt der Daten.
"""

import sys
import pathlib
import warnings

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from offline import (load_session, OfflineFilter, replay, epoch_stats,
                     evoked_rms,
                     select_triggers, use_app_style, plot_compare,
                     plot_cluster_test, plot_selection, plot_tfr_grid,
                     plot_erp_grid, tfr_difference)
from offline.measures import (peak_latency, bootstrap_difference,
                              bootstrap_shift, cluster_permutation_test,
                              matched_subsample)
from offline.plots import (CONDITION_COLORS, CHANNEL_COLORS,
                           TEXT_PRIMARY)

warnings.filterwarnings("ignore", category=RuntimeWarning)

# ── Daten und Parameter ──────────────────────────────────────────────
SEP9 = {
    "akustisch":      "recordings/ERP_20260909_163744.csv",
    "Oberschenkel L": "recordings/ERP_20260909_164514.csv",
    "Wade L":         "recordings/ERP_20260909_165220.csv",
    "Wade K (1)":     "recordings/ERP_20260909_170018.csv",
    "Wade K (2)":     "recordings/ERP_20260909_171102.csv",
}
AUG13 = {
    "Fuß":      "recordings/ERP_20260813_131731_stimulationFuss.csv",
    "Oberarm":  "recordings/ERP_20260813_125428_stimulationOberarm.csv",
    "akustisch": "recordings/ERP_20260813_122235_nurAkustisch.csv",
    "kein Reiz": "recordings/ERP_20260813_122821_keinReiz.csv",
}

# "Erste 10 Impulse immer weg" — Einlaufphase der Messung.
PARAM = dict(pre_ms=200, post_ms=2000, drop_first=10, mad_k=3.5,
             threshold=None, tfr_pre_ms=1500, tfr_post_ms=3500,
             tfr_roi=(0, 2, 4))

# Die Augustreihe hat sehr ungleiche Triggerzahlen (Kontrolle 68 gegen 40
# bei der ungedaempften Bedingung). Nach drop_first=10 blieben 58 gegen 29 —
# der Mittelwert der Kontrolle waere dann allein wegen der doppelten
# Epochenzahl glatter, und der Vergleich zeigte teils nur noch n. Deshalb
# zusaetzlich auf die kleinste Bedingung gedeckelt.
PARAM_AUG13 = dict(PARAM, last=29)
ROI = ["Fz", "Cz", "Pz"]          # dieselbe ROI wie die TFR der Anwendung
FARBEN = {"akustisch": "#7d8794", "kein Reiz": "#7d8794",
          "Oberschenkel L": "#4a9eff", "Wade L": "#3ddc84",
          "Wade K (1)": "#f97b8b", "Wade K (2)": "#8b7cf6",
          "Fuß": "#4a9eff", "Oberarm": "#ffa726"}

# Interne Schluessel bleiben kurz und stabil; was in der Abbildung steht,
# steht hier. Beide Versuchsfaktoren gehoeren in die Beschriftung —
# **Hautreiz** und **Akustik** —, sonst liest man "kein Reiz" gegen
# "akustisch" als Reiz-gegen-Kontrolle, obwohl in beiden Bedingungen gar
# kein Hautreiz gesetzt wurde und sich nur die Daempfung unterscheidet.
ANZEIGE_AUG13 = {
    "Fuß":       "Fuß \u00b7 Akustik ged\u00e4mpft",
    "Oberarm":   "Oberarm \u00b7 Akustik ged\u00e4mpft",
    "kein Reiz": "kein Hautreiz \u00b7 Akustik ged\u00e4mpft",
    "akustisch": "kein Hautreiz \u00b7 Akustik unged\u00e4mpft",
}
ANZEIGE_SEP9 = {
    "akustisch":      "kein Hautreiz \u00b7 Akustik ged\u00e4mpft",
    "Oberschenkel L": "Oberschenkel \u00b7 Linse",
    "Wade L":         "Wade \u00b7 Linse",
    "Wade K (1)":     "Wade \u00b7 normaler Kopf (1)",
    "Wade K (2)":     "Wade \u00b7 normaler Kopf (2)",
}
FUSSNOTE_NC = ("ged\u00e4mpft = Noise-Cancelling-Kopfh\u00f6rer aktiv")


def zeige(roi, keys, anzeige):
    """Auswahl mit Anzeigenamen und passenden Farben."""
    d = {anzeige.get(k, k): roi[k] for k in keys}
    f = {anzeige.get(k, k): FARBEN[k] for k in keys if k in FARBEN}
    return d, f


def fussnote(fig, text=None):
    """Erklaert den Begriff unter der Abbildung, damit die Legende kurz
    bleiben kann."""
    fig.text(0.005, -0.015, text or FUSSNOTE_NC, fontsize=10,
             style="italic", va="top", ha="left", alpha=0.85)

OUT = ROOT / "praesentation"


# ── Hilfen ───────────────────────────────────────────────────────────
class RoiView:
    """Sicht auf das ROI-Mittel, damit Abbildung und Statistik dieselbe
    Kurve sehen."""

    def __init__(self, r, roi=ROI):
        self._r, self._i = r, [r.ch(c) for c in roi]
        self.time_axis, self.label = r.time_axis, r.label
        self.n_accepted, self.ch_labels = r.n_accepted, ["ROI"]

    def ch(self, name):
        return 0

    def trace(self, _=None):
        return self._r.erp_mean[:, self._i].mean(1)

    def epoch_traces(self, _=None):
        return self._r.epochs[:, :, self._i].mean(2)


def lade(dateien, with_tfr=False, param=None):
    param = param or PARAM
    out = {}
    for name, p in dateien.items():
        s = load_session(ROOT / p)
        eeg = OfflineFilter(fs=s.fs).highpass(1.0).notch(50.0)(s.raw)
        out[name] = replay(eeg, s.trigger_idx, fs=s.fs, ch_labels=s.ch_labels,
                           label=name, with_tfr=with_tfr, **param)
    return out


def sichern(fig, name):
    """PNG für die Folien, PDF als Vektor — scharf bei jeder Skalierung."""
    d = OUT / AKTUELLER_STIL
    d.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(d / f"{name}.{ext}", bbox_inches="tight")
    plt.close(fig)
    print(f"    {AKTUELLER_STIL}/{name}.png + .pdf")


def _stern(p):
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


def infokasten(ax, text):
    """Kennzahlen unten in die Abbildung setzen — und vorher unten Platz
    schaffen, sonst liegt der Kasten auf den Kurven oder wird beschnitten."""
    lo, hi = ax.get_ylim()
    ax.set_ylim(lo - 0.22 * (hi - lo), hi)
    ax.text(0.015, 0.02, text, transform=ax.transAxes, fontsize=11,
            va="bottom", ha="left",
            bbox=dict(boxstyle="round,pad=0.45", fc="white", ec="gray",
                      alpha=0.85 if AKTUELLER_STIL == "hell" else 0.0))


# ════════════════════════════════════════════════════════════════════
#  A — System und Methode
# ════════════════════════════════════════════════════════════════════
def A1_verarbeitungskette():
    """Vom Rohsignal zum evozierten Potential — die vier Schritte, und
    was jeder davon am Signal-Rausch-Verhältnis ändert."""
    s = load_session(ROOT / SEP9["Oberschenkel L"])
    eeg = OfflineFilter(fs=s.fs).highpass(1.0).notch(50.0)(s.raw)
    r = replay(eeg, s.trigger_idx, fs=s.fs, ch_labels=s.ch_labels,
               label="Oberschenkel L", with_tfr=False, **PARAM)
    cz = s.ch_labels.index("Cz")
    t = r.time_axis

    fig, ax = plt.subplots(4, 1, figsize=(11, 11))

    sl = slice(int(30 * s.fs), int(40 * s.fs))
    ax[0].plot(s.t[sl], s.raw[sl, cz] / 1000, lw=0.8, color=CHANNEL_COLORS[0])
    ax[0].set_ylabel("mV")
    ax[0].set_title("1 — Rohsignal (Cz): Gleichanteil und Drift überdecken alles")

    ax[1].plot(s.t[sl], eeg[sl, cz], lw=0.8, color=CHANNEL_COLORS[1])
    for tt in s.t[s.trigger_idx]:
        if s.t[sl][0] <= tt <= s.t[sl][-1]:
            ax[1].axvline(tt, color="k", lw=1, ls="--", alpha=0.45)
    ax[1].set_ylabel("µV")
    ax[1].set_title("2 — Hochpass 1 Hz + Notch 50 Hz, nullphasig "
                    "(gestrichelt: Reize)")
    for a in ax[:2]:
        a.set_xlabel("Zeit [s]")
        a.grid(alpha=0.3)

    ep = r.epoch_traces("Cz")
    for e in ep:
        ax[2].plot(t, e, lw=0.5, alpha=0.35, color=CHANNEL_COLORS[2])
    ax[2].set_title(f"3 — {len(ep)} Einzelepochen: die Antwort ist im "
                    "Einzelversuch nicht zu sehen")

    m = ep.mean(0)
    sem = ep.std(0, ddof=1) / np.sqrt(len(ep))
    ax[3].plot(t, m, lw=2.2, color=CHANNEL_COLORS[3])
    ax[3].fill_between(t, m - sem, m + sem, color=CHANNEL_COLORS[3],
                       alpha=0.25, lw=0)
    ax[3].set_title(f"4 — Mittelwert über {len(ep)} Epochen: "
                    f"das Rauschen sinkt mit √n, die Antwort bleibt")
    for a in ax[2:]:
        a.set_xlim(-200, 800)
        a.axvline(0, color="k", lw=1.2, ls="--", alpha=0.6)
        a.axhline(0, lw=0.8, alpha=0.3, color="k")
        a.set_xlabel("Zeit [ms]")
        a.set_ylabel("µV")
        a.grid(alpha=0.3)
    ax[2].set_ylim(-60, 60)

    fig.tight_layout()
    sichern(fig, "A1_verarbeitungskette")


def A2_filter():
    """Warum offline anders gefiltert wird als im Betrieb."""
    s = load_session(ROOT / SEP9["Oberschenkel L"])
    flt = OfflineFilter(fs=s.fs).highpass(1.0).notch(50.0)
    eeg = flt(s.raw)
    cz = s.ch_labels.index("Cz")

    fig, ax = plt.subplots(2, 1, figsize=(11, 7))

    f, db = flt.frequency_response()
    ax[0].plot(f, db, lw=2, color=CONDITION_COLORS[0])
    ax[0].axhline(-3, ls="--", lw=1, alpha=0.6, color="k")
    ax[0].set_xlim(0, 60)
    ax[0].set_ylim(-60, 5)
    ax[0].set_xlabel("Frequenz [Hz]")
    ax[0].set_ylabel("Dämpfung [dB]")
    ax[0].set_title("Filterkette: Hochpass 1 Hz + Notch 50 Hz "
                    "(zweifach durchlaufen)")
    ax[0].grid(alpha=0.3)

    sl = slice(int(40 * s.fs), int(43 * s.fs))
    ax[1].plot(s.t[sl], s.flt[sl, cz], lw=1.4, alpha=0.85,
               color=CONDITION_COLORS[1], label="live: sosfilt, kausal")
    ax[1].plot(s.t[sl], eeg[sl, cz], lw=1.8,
               color=CONDITION_COLORS[0], label="offline: sosfiltfilt, nullphasig")
    ax[1].set_xlabel("Zeit [s]")
    ax[1].set_ylabel("µV")
    ax[1].set_title("Derselbe Abschnitt, beide Filterwege — der Zeitversatz "
                    "ist die Laufzeit des kausalen Filters")
    ax[1].legend()
    ax[1].grid(alpha=0.3)

    fig.tight_layout()
    sichern(fig, "A2_filter_kausal_vs_nullphasig")


def A3_triggerauswahl():
    """Welche Epoche aus welchem Grund in die Mittelung geht."""
    s = load_session(ROOT / SEP9["Wade K (1)"])
    eeg = OfflineFilter(fs=s.fs).highpass(1.0).notch(50.0)(s.raw)
    r = replay(eeg, s.trigger_idx, fs=s.fs, ch_labels=s.ch_labels,
               label="Wade, normaler Kopf (1)", with_tfr=False, **PARAM)

    fig, ax = plt.subplots(figsize=(11, 4.5))
    plot_selection(r, ax=ax)
    ax.set_title("Trigger-Auswahl: Einlaufphase verworfen, Ausreißer robust "
                 "abgewiesen\n(Grenze aus dem Median dieser Aufnahme, nicht fest in µV)")
    fig.tight_layout()
    sichern(fig, "A3_triggerauswahl")


def A4_mittelungsgewinn():
    """Wie viele Epochen braucht man — und warum wenige Epochen täuschen.

    Gegenprobe im selben Datensatz: dieselbe Aufnahme, aber mit zufällig
    gesetzten Triggern. Da ist per Konstruktion keine Antwort. Was die
    Gipfelsuche dort trotzdem findet, ist der Betrag, den man bei dieser
    Epochenzahl auch ohne jeden Reiz bekommt."""
    s = load_session(ROOT / SEP9["Oberschenkel L"])
    eeg = OfflineFilter(fs=s.fs).highpass(1.0).notch(50.0)(s.raw)
    r = replay(eeg, s.trigger_idx, fs=s.fs, ch_labels=s.ch_labels,
               with_tfr=False, **PARAM)

    rng = np.random.default_rng(0)
    lo, hi = int(0.3 * s.fs) + 500, len(eeg) - int(2.2 * s.fs)
    schein = np.sort(rng.choice(np.arange(lo, hi), len(s.trigger_idx),
                                replace=False))
    r0 = replay(eeg, schein, fs=s.fs, ch_labels=s.ch_labels,
                with_tfr=False, **PARAM)

    t = r.time_axis
    P2 = lambda ep: peak_latency(ep.mean(0), t, (150, 450), "max")["amplitude_µV"]
    ns = [5, 10, 15, 20, 30, 40]

    fig, ax = plt.subplots(1, 2, figsize=(13, 4.6))
    for k, (res, name, col) in enumerate([
            (r,  "echte Reize",            CONDITION_COLORS[0]),
            (r0, "zufällige Trigger",      "#7d8794")]):
        ep = res.epochs[:, :, [res.ch(c) for c in ROI]].mean(2)
        mu, sd = [], []
        for n in ns:
            if n > len(ep):
                mu.append(np.nan); sd.append(np.nan); continue
            v = [P2(ep[rng.choice(len(ep), n, replace=False)]) for _ in range(300)]
            mu.append(np.mean(v)); sd.append(np.std(v))
        mu, sd = np.array(mu), np.array(sd)
        ax[0].errorbar(ns, mu, yerr=sd, marker="o", lw=2, capsize=4,
                       color=col, label=name)
        ax[1].plot(t, ep.mean(0), lw=2, color=col, label=f"{name} (n={len(ep)})")

    ax[0].set_xlabel("Zahl der gemittelten Epochen")
    ax[0].set_ylabel("gefundene P2-Amplitude [µV]")
    ax[0].set_title("Gipfelsuche findet auch dort etwas,\nwo nichts ist — "
                    "umso mehr, je weniger gemittelt wird")
    ax[0].legend()
    ax[0].grid(alpha=0.3)

    ax[1].set_xlim(-200, 800)
    ax[1].axvline(0, color="k", lw=1.2, ls="--", alpha=0.6)
    ax[1].axhline(0, lw=0.8, alpha=0.3, color="k")
    ax[1].set_xlabel("Zeit [ms]")
    ax[1].set_ylabel("µV")
    ax[1].set_title("Vollständige Mittelung: Reiz gegen Zufall")
    ax[1].legend()
    ax[1].grid(alpha=0.3)

    fig.tight_layout()
    sichern(fig, "A4_mittelungsgewinn")


def A5_kanaluebersicht():
    """Alle acht Kanäle — die Antwort ist zentral, nicht überall."""
    s = load_session(ROOT / SEP9["Oberschenkel L"])
    eeg = OfflineFilter(fs=s.fs).highpass(1.0).notch(50.0)(s.raw)
    r = replay(eeg, s.trigger_idx, fs=s.fs, ch_labels=s.ch_labels,
               label="Oberschenkel, Linse", with_tfr=False, **PARAM)
    fig, axes = plot_erp_grid(r, sem=True, ncols=2)
    for row in axes:
        for a in row:
            a.set_xlim(-200, 800)
    fig.tight_layout()
    sichern(fig, "A5_kanaluebersicht")


# ════════════════════════════════════════════════════════════════════
#  B — Messreihe 09.09.
# ════════════════════════════════════════════════════════════════════
def B1_serie_uebersicht(res=None):
    """Alle Bedingungen der Reihe in einem Bild."""
    res = res or lade(SEP9)
    roi = {k: RoiView(v) for k, v in res.items()}

    d, f = zeige(roi, list(roi), ANZEIGE_SEP9)
    fig, ax = plt.subplots(2, 1, figsize=(12, 9))
    plot_compare(d, "ROI", ax=ax[0], xlim=(-150, 800), colors=f,
                 title="Messreihe 09.09. — ROI Fz+Cz+Pz, Band: Standardfehler")
    plot_compare(d, "ROI", ax=ax[1], xlim=(-200, 2000), sem=False, colors=f,
                 title="Ganzes Fenster — nach etwa 500 ms ist nichts mehr da")
    fig.tight_layout()
    fussnote(fig, "Messreihe 09.09. \u00b7 " + FUSSNOTE_NC)
    sichern(fig, "B1_serie_uebersicht")


def B2_koerperstelle(res=None):
    """Oberschenkel gegen Wade, gleicher Reizkopf — die Leitungsfrage."""
    res = res or lade(SEP9)
    roi = {k: RoiView(v) for k, v in res.items()}
    t = res["Wade L"].time_axis
    E = lambda n: roi[n].epoch_traces()

    test = cluster_permutation_test(E("Wade L"), E("Oberschenkel L"), t,
                                    window=(0, 800), n_perm=3000)
    P2 = lambda x, tt: peak_latency(x, tt, (150, 450), "max")["latenz_ms"]
    lat = bootstrap_difference(E("Oberschenkel L"), E("Wade L"), t, P2,
                               n_boot=2000, n_perm=2000)
    xk = bootstrap_shift(E("Oberschenkel L"), E("Wade L"), t,
                         window=(100, 600), max_lag_ms=150, n_boot=1500)

    fig, ax = plt.subplots(2, 1, figsize=(12, 8),
                           gridspec_kw={"height_ratios": [2, 1]})
    d, f = zeige(roi, ["Oberschenkel L", "Wade L"], ANZEIGE_SEP9)
    plot_compare(d, "ROI", ax=ax[0], xlim=(-150, 800), clusters=test, colors=f,
                 title="K\u00f6rperstelle bei gleichem Reizkopf (Linse)")
    infokasten(ax[0],
               f"P2-Latenz Wade − Oberschenkel:  {lat['differenz']:+.0f} ms "
               f"[{lat['lo']:+.0f}, {lat['hi']:+.0f}],  {_stern(lat['p'])}\n"
               f"Kreuzkorrelation:  {xk['verschiebung_ms']:+.0f} ms "
               f"[{xk['lo']:+.0f}, {xk['hi']:+.0f}]",)
    plot_cluster_test(test, ax=ax[1])
    ax[1].set_xlim(-150, 800)
    fig.tight_layout()
    sichern(fig, "B2_koerperstelle_oberschenkel_wade")


def B3_reproduzierbarkeit(res=None):
    """Zweimal dieselbe Bedingung — die wichtigste Abbildung der Arbeit.

    Wade, normaler Kopf, zweimal hintereinander gemessen. Hier liegt per
    Versuchsaufbau KEIN Unterschied vor. Was hier trotzdem herauskommt, ist
    die Auflösungsgrenze des Verfahrens — und jeder Bedingungsunterschied,
    der kleiner ist, lässt sich nicht deuten."""
    res = res or lade(SEP9)
    roi = {k: RoiView(v) for k, v in res.items()}
    t = res["Wade K (1)"].time_axis
    E = lambda n: roi[n].epoch_traces()

    P2 = lambda x, tt: peak_latency(x, tt, (150, 450), "max")["latenz_ms"]
    lat = bootstrap_difference(E("Wade K (1)"), E("Wade K (2)"), t, P2,
                               n_boot=2000, n_perm=2000)
    xk = bootstrap_shift(E("Wade K (1)"), E("Wade K (2)"), t,
                         window=(100, 600), max_lag_ms=150, n_boot=1500)
    # zum Vergleich der gesuchte Effekt
    lat_eff = bootstrap_difference(E("Oberschenkel L"), E("Wade L"), t, P2,
                                   n_boot=2000, n_perm=2000)

    fig, ax = plt.subplots(2, 1, figsize=(12, 8.5),
                           gridspec_kw={"height_ratios": [2.2, 1]})
    d, f = zeige(roi, ["Wade K (1)", "Wade K (2)"], ANZEIGE_SEP9)
    plot_compare(d, "ROI", ax=ax[0], xlim=(-150, 800), colors=f,
                 title="Dieselbe Bedingung, zweimal gemessen — "
                       "hier gibt es nichts zu finden")
    infokasten(ax[0],
               f"P2-Latenz zwischen zwei Wiederholungen:  "
               f"{lat['differenz']:+.0f} ms  ·  Kreuzkorrelation: "
               f"{xk['verschiebung_ms']:+.0f} ms",)

    werte = [abs(lat_eff["differenz"]), abs(lat["differenz"])]
    namen = ["gesuchter Effekt\nOberschenkel → Wade",
             "Messunsicherheit\nWiederholung derselben Bedingung"]
    ax[1].barh(namen, werte, color=[CONDITION_COLORS[0], "#f97b8b"], height=0.5)
    for y, v in enumerate(werte):
        ax[1].text(v + 3, y, f"{v:.0f} ms", va="center", fontsize=13)
    ax[1].set_xlabel("Latenzunterschied [ms]")
    ax[1].set_xlim(0, max(werte) * 1.28)
    ax[1].set_title("Der gesuchte Effekt ist kleiner als die "
                    "Wiederholbarkeit der Messung")
    ax[1].grid(alpha=0.3, axis="x")
    fig.tight_layout()
    sichern(fig, "B3_reproduzierbarkeit")


def B4_akustisch(res=None):
    """Hebt sich der Hautreiz von der Kontrolle ab — und ab wann?"""
    res = res or lade(SEP9)
    roi = {k: RoiView(v) for k, v in res.items()}
    t = res["akustisch"].time_axis
    E = lambda n: roi[n].epoch_traces()

    test = cluster_permutation_test(E("Oberschenkel L"), E("akustisch"), t,
                                    window=(0, 800), n_perm=3000)

    fig, ax = plt.subplots(2, 1, figsize=(12, 8),
                           gridspec_kw={"height_ratios": [2, 1]})
    d, f = zeige(roi, ["akustisch", "Oberschenkel L", "Wade L"], ANZEIGE_SEP9)
    plot_compare(d, "ROI", ax=ax[0], xlim=(-150, 800), clusters=test, colors=f,
                 title="Hautreiz gegen Kontrolle, alle mit Noise-Cancelling\n"
                       "gr\u00fcn: Oberschenkel unterscheidet sich von der "
                       "Kontrolle (p < 0.05)")
    plot_cluster_test(test, ax=ax[1])
    ax[1].set_xlim(-150, 800)
    ax[1].set_title("Oberschenkel gegen Kontrolle, punktweise")
    fig.tight_layout()
    fussnote(fig, "Messreihe 09.09. \u00b7 " + FUSSNOTE_NC)
    sichern(fig, "B4_akustisch_vs_hautreiz")


def B5_nachweisgrenze(res=None):
    """Was das Latenzmaß überhaupt auflösen kann.

    Eine Kopie der eigenen Daten wird künstlich verschoben und
    zurückgemessen. Die Steigung sagt, ob der Betrag stimmt; die Breite
    der Vertrauensbereiche sagt, ab wann eine Verschiebung nachweisbar
    wäre."""
    res = res or lade(SEP9)
    roi = {k: RoiView(v) for k, v in res.items()}
    t = res["Oberschenkel L"].time_axis
    ep = roi["Oberschenkel L"].epoch_traces()
    h = len(ep) // 2
    dt = t[1] - t[0]

    soll = np.array([0, 20, 40, 60, 80, 120])
    mess, lo, hi = [], [], []
    for v in soll:
        b = np.roll(ep[h:], int(round(v / dt)), axis=1)
        s = bootstrap_shift(ep[:h], b, t, window=(100, 600),
                            max_lag_ms=200, n_boot=800)
        mess.append(s["verschiebung_ms"]); lo.append(s["lo"]); hi.append(s["hi"])
    mess, lo, hi = np.array(mess), np.array(lo), np.array(hi)
    versatz = mess[0]

    fig, ax = plt.subplots(figsize=(9, 6))
    ax.plot(soll, soll + versatz, ls="--", lw=1.5, color="gray",
            label="Erwartung (Eigenversatz der Bedingung mitgerechnet)")
    ax.errorbar(soll, mess, yerr=[mess - lo, hi - mess], marker="o",
                lw=2, capsize=5, color=CONDITION_COLORS[0],
                label="gemessen, mit 95-%-Bereich")
    ax.axhline(versatz, lw=1, ls=":", color="gray")
    ax.set_xlabel("künstlich vorgegebene Verschiebung [ms]")
    ax.set_ylabel("zurückgemessene Verschiebung [ms]")
    ax.set_title("Nachweisgrenze des Latenzmaßes\n"
                 f"Der Betrag wird richtig getroffen, aber der Vertrauensbereich "
                 f"ist rund ±{np.mean((hi - lo) / 2):.0f} ms breit")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    sichern(fig, "B5_nachweisgrenze")


def B6_tfr(res=None):
    """Zeit-Frequenz über alle Bedingungen, gemeinsame Farbskala."""
    res = res or lade(SEP9, with_tfr=True)
    if res["akustisch"].tfr is None:
        res = lade(SEP9, with_tfr=True)
    fig, _ = plot_tfr_grid({ANZEIGE_SEP9.get(k, k): v for k, v in res.items()},
                           xlim=(-1.0, 2.0))
    fig.suptitle("Zeit-Frequenz, ROI Fz+Cz+Pz — z-Score gegen die eigene "
                 "Grundlinie, gemeinsame Skala", y=1.02)
    sichern(fig, "B6_tfr_gitter")

    fig, _ = tfr_difference(res["Wade L"], res["akustisch"], vmax=2.0,
                            xlim=(-1.0, 2.0),
                            title="Wade (Linse) \u2212 Kontrolle")
    sichern(fig, "B6b_tfr_differenz")


# ════════════════════════════════════════════════════════════════════
#  C — Messreihe 13.08.
# ════════════════════════════════════════════════════════════════════
def C1_fuss_oberarm(res=None):
    """Fuß gegen Oberarm — der größte Abstandsunterschied im Datensatz."""
    res = res or lade(AUG13, param=PARAM_AUG13)
    roi = {k: RoiView(v) for k, v in res.items()}
    t = res["Fuß"].time_axis
    E = lambda n: roi[n].epoch_traces()

    test = cluster_permutation_test(E("Fuß"), E("Oberarm"), t,
                                    window=(0, 800), n_perm=3000)
    P2 = lambda x, tt: peak_latency(x, tt, (150, 400), "max")["latenz_ms"]
    lat = bootstrap_difference(E("Oberarm"), E("Fuß"), t, P2,
                               n_boot=2000, n_perm=2000)
    xk = bootstrap_shift(E("Oberarm"), E("Fuß"), t, window=(100, 500),
                         max_lag_ms=150, n_boot=1500)

    fig, ax = plt.subplots(2, 1, figsize=(12, 8),
                           gridspec_kw={"height_ratios": [2, 1]})
    d, f = zeige(roi, ["Fuß", "Oberarm", "kein Reiz"], ANZEIGE_AUG13)
    plot_compare(d, "ROI", ax=ax[0], xlim=(-150, 800), clusters=test, colors=f,
                 title="Messreihe 13.08. — Fu\u00df gegen Oberarm\n"
                       "alle drei mit Noise-Cancelling, die Akustik ist also "
                       "in allen Bedingungen gleich ged\u00e4mpft")
    infokasten(ax[0],
               f"P2-Latenz Fuß − Oberarm:  {lat['differenz']:+.0f} ms "
               f"[{lat['lo']:+.0f}, {lat['hi']:+.0f}],  {_stern(lat['p'])}\n"
               f"Kreuzkorrelation:  {xk['verschiebung_ms']:+.0f} ms "
               f"[{xk['lo']:+.0f}, {xk['hi']:+.0f}]   —   "
               f"erwartet bei Aδ-Leitung: +70 bis +110 ms",)
    plot_cluster_test(test, ax=ax[1])
    ax[1].set_xlim(-150, 800)
    fig.tight_layout()
    fussnote(fig, "Messreihe 13.08. \u00b7 " + FUSSNOTE_NC)
    sichern(fig, "C1_fuss_vs_oberarm")


def C2_akustisch_kontrolle(res=None):
    """Der akustische Störanteil, sauber gegen eine echte Nullbedingung."""
    res = res or lade(AUG13, param=PARAM_AUG13)
    roi = {k: RoiView(v) for k, v in res.items()}
    t = res["Fuß"].time_axis
    E = lambda n: roi[n].epoch_traces()

    test = cluster_permutation_test(E("akustisch"), E("kein Reiz"), t,
                                    window=(0, 800), n_perm=3000)

    fig, ax = plt.subplots(2, 1, figsize=(12, 8),
                           gridspec_kw={"height_ratios": [2, 1]})
    d, f = zeige(roi, ["akustisch", "kein Reiz", "Fuß", "Oberarm"],
                 ANZEIGE_AUG13)
    f[ANZEIGE_AUG13["akustisch"]] = "#f97b8b"   # unged\u00e4mpft hervorheben
    plot_compare(d, "ROI", ax=ax[0], xlim=(-150, 800), clusters=test, colors=f,
                 title="Was das Noise-Cancelling entfernt\n"
                       "Die beiden Bedingungen \u201ekein Hautreiz\u201c "
                       "unterscheiden sich allein in der D\u00e4mpfung "
                       "(gr\u00fcn: p < 0.05)")
    plot_cluster_test(test, ax=ax[1])
    ax[1].set_xlim(-150, 800)
    ax[1].set_title("ohne D\u00e4mpfung gegen mit D\u00e4mpfung, punktweise")
    fig.tight_layout()
    fussnote(fig, "Messreihe 13.08. \u00b7 " + FUSSNOTE_NC)
    sichern(fig, "C2_akustisch_vs_kontrolle")


def C3_energie_zeitfenster(res=None):
    """Wo im Zeitverlauf welcher Anteil sitzt — die Trennung von
    akustischem und somatosensorischem Beitrag."""
    res = res or lade(AUG13, param=PARAM_AUG13)
    roi = {k: RoiView(v) for k, v in res.items()}
    t = res["Fuß"].time_axis
    fen = [(0, 100), (100, 150), (150, 400), (400, 800), (800, 2000)]
    namen = ["0–100", "100–150", "150–400", "400–800", "800–2000"]

    basis = np.array([np.sqrt((roi["kein Reiz"].trace()[(t >= a) & (t <= b)] ** 2).mean())
                      for a, b in fen])
    breite = 0.2
    x = np.arange(len(fen))

    fig, ax = plt.subplots(figsize=(11, 5))
    for k, n in enumerate(["Fuß", "Oberarm", "akustisch"]):
        y = np.array([np.sqrt((roi[n].trace()[(t >= a) & (t <= b)] ** 2).mean())
                      for a, b in fen]) / basis
        ax.bar(x + (k - 1) * breite, y, breite, color=FARBEN[n],
               label=ANZEIGE_AUG13[n])
    ax.axhline(1, ls="--", lw=1.4, color="k", alpha=0.7,
               label=ANZEIGE_AUG13["kein Reiz"] + "  (Ma\u00dfstab)")
    ax.set_xticks(x)
    ax.set_xticklabels(namen)
    ax.set_xlabel("Zeitfenster [ms]")
    ax.set_ylabel("Signalstärke, Vielfaches der Kontrolle")
    ax.set_title("Was die D\u00e4mpfung entfernt, liegt vor 150 ms \u2014 "
                 "die Antwort auf den Hautreiz danach\n"
                 "Deshalb greifen die Kopfh\u00f6rer genau dort, wo die "
                 "St\u00f6rung sitzt, ohne die Antwort anzutasten")
    ax.legend()
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    fussnote(fig, "Messreihe 13.08. \u00b7 " + FUSSNOTE_NC)
    sichern(fig, "C3_energie_nach_zeitfenster")


# ════════════════════════════════════════════════════════════════════
#  D — Fokussierender Applikator
# ════════════════════════════════════════════════════════════════════
W_REL = (100, 500)      # Auswertefenster, vorab festgelegt
N_REL = 21              # kleinste Bedingung — alle Maße darauf angeglichen


def _reliabilitaet(ep, t, n_zieh=200, n_sub=N_REL, seed=0):
    """Reliabilität mit Streuung: wiederholt auf n_sub herunterziehen.

    Die Angleichung ist nicht Kosmetik — Reliabilität und
    Einzeltrial-Konsistenz wachsen beide mit der Epochenzahl. Ohne
    gemeinsames n vergleicht man n statt der Bedingungen."""
    from offline.measures import split_half_reliability, single_trial_consistency
    rng = np.random.default_rng(seed)
    rs, cs = [], []
    for k in range(n_zieh):
        sub = ep[np.sort(rng.choice(len(ep), min(n_sub, len(ep)), replace=False))]
        rs.append(split_half_reliability(sub, t, W_REL, n_rep=300, seed=k))
        cs.append(single_trial_consistency(sub, t, W_REL)["r_mittel"])
    return np.array(rs), np.array(cs)


def D1_applikator(res=None):
    """Der fokussierende Applikator: nicht größer, aber verlässlicher.

    Die Amplitude unterscheidet sich nicht. Was sich unterscheidet, ist
    die Reproduzierbarkeit der Antwort — und das ist für einen Applikator
    das eigentlich interessante Maß."""
    res = res or lade(SEP9)
    roi = {k: RoiView(v) for k, v in res.items()}
    t = res["Wade L"].time_axis
    E = {k: roi[k].epoch_traces() for k in
         ["Wade L", "Wade K (1)", "Wade K (2)"]}
    E["Kopf (beide)"] = np.vstack([E["Wade K (1)"], E["Wade K (2)"]])

    test = cluster_permutation_test(E["Wade L"], E["Kopf (beide)"], t,
                                    window=(0, 800), n_perm=3000)

    fig = plt.figure(figsize=(13, 9))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.15, 1], hspace=0.38, wspace=0.26)

    ax = fig.add_subplot(gs[0, :])
    plot_compare({"Linse": roi["Wade L"],
                  "normaler Kopf (1)": roi["Wade K (1)"],
                  "normaler Kopf (2)": roi["Wade K (2)"]}, "ROI", ax=ax,
                 xlim=(-150, 700), clusters=test,
                 colors={"Linse": "#3ddc84", "normaler Kopf (1)": "#f97b8b",
                         "normaler Kopf (2)": "#8b7cf6"},
                 title="Wade, gleicher Ort — Linse gegen normalen Reizkopf")
    ax.legend(loc="upper right", fontsize=11)
    infokasten(ax, "Kurvenform: kein Cluster mit p < 0.05 "
                   f"(bestes p = {test['cluster']['p'].min():.2f})\n"
                   "mittlere Amplitude:  N1  p = 0.92   ·   P2  p = 0.93")

    namen = ["Linse", "normaler\nKopf (1)", "normaler\nKopf (2)"]
    schl = ["Wade L", "Wade K (1)", "Wade K (2)"]
    farben = ["#3ddc84", "#f97b8b", "#8b7cf6"]

    for sp, (titel, idx, ylab) in enumerate([
            ("Reproduzierbarkeit der Antwort", 0, "Split-half-Reliabilität r"),
            ("Einzelversuch gegen Mittelwert", 1, "mittleres r")]):
        a = fig.add_subplot(gs[1, sp])
        werte = []
        for k, (nm, key, col) in enumerate(zip(namen, schl, farben)):
            v = _reliabilitaet(E[key], t, seed=k)[idx]
            med = np.median(v)
            lo, hi = np.percentile(v, [2.5, 97.5])
            a.bar(k, med, 0.6, color=col,
                  yerr=[[med - lo], [hi - med]], capsize=6, ecolor="gray")
            werte.append((med, lo, hi))
        # erst den Platz festlegen, dann beschriften — sonst landen die
        # Zahlen über dem Titel
        y0 = min(w[1] for w in werte)
        y1 = max(w[2] for w in werte)
        rand = 0.18 * (y1 - y0)
        a.set_ylim(y0 - 0.4 * rand, y1 + 1.5 * rand)
        for k, (med, lo, hi) in enumerate(werte):
            a.text(k, hi + 0.35 * rand, f"{med:+.2f}", ha="center", fontsize=12)
        a.axhline(0, color="k", lw=1.2)
        a.set_xticks(range(3))
        a.set_xticklabels(namen)
        a.set_ylabel(ylab)
        a.set_title(f"{titel}\n(alle bei n = {N_REL}, "
                    f"{W_REL[0]}–{W_REL[1]} ms)",
                    fontsize=13)
        a.grid(alpha=0.3, axis="y")

    sichern(fig, "D1_applikator_linse_vs_kopf")


def D2_applikator_zeitkontrolle(_=None):
    """Ist es der Applikator oder einfach die Uhrzeit?

    Die Linse wurde vor dem normalen Kopf gemessen — Reihenfolge und
    Applikator sind verwechselbar. Diese Abbildung prüft die
    Zeiterklärung: fiele die Reliabilität einfach über die Sitzung ab,
    müsste die früheste Aufnahme die beste sein."""
    from offline.measures import split_half_reliability

    reihe = [("16:37", "akustisch",    "163744", "—"),
             ("16:45", "Oberschenkel", "164514", "Linse"),
             ("16:52", "Wade",         "165220", "Linse"),
             ("17:00", "Wade",         "170018", "Kopf"),
             ("17:11", "Wade",         "171102", "Kopf")]
    farbe = {"Linse": "#3ddc84", "Kopf": "#f97b8b", "—": "#7d8794"}

    med, lo, hi, etik, cols, halb = [], [], [], [], [], []
    for zeit, ort, f, kopf in reihe:
        s = load_session(ROOT / f"recordings/ERP_20260909_{f}.csv")
        eeg = OfflineFilter(fs=s.fs).highpass(1.0).notch(50.0)(s.raw)
        r = replay(eeg, s.trigger_idx, fs=s.fs, ch_labels=s.ch_labels,
                   with_tfr=False, **PARAM)
        t = r.time_axis
        ep = r.epochs[:, :, [r.ch(c) for c in ROI]].mean(2)
        v = _reliabilitaet(ep, t, n_zieh=150)[0]
        med.append(np.median(v))
        a, b = np.percentile(v, [2.5, 97.5])
        lo.append(a); hi.append(b)
        h = len(ep) // 2
        halb.append((split_half_reliability(ep[:h], t, W_REL, n_rep=300),
                     split_half_reliability(ep[h:], t, W_REL, n_rep=300)))
        etik.append(f"{zeit}\n{ort}\n{kopf}")
        cols.append(farbe[kopf])

    med = np.array(med)
    x = np.arange(len(reihe))
    fig, ax = plt.subplots(1, 2, figsize=(15, 6.2),
                           gridspec_kw={"width_ratios": [1.4, 1]})

    ax[0].bar(x, med, 0.62, color=cols,
              yerr=[med - np.array(lo), np.array(hi) - med],
              capsize=6, ecolor="gray")
    ax[0].axhline(0, color="k", lw=1.2)
    ax[0].set_xticks(x)
    ax[0].set_xticklabels(etik)
    ax[0].set_ylabel("Split-half-Reliabilität r")
    ax[0].set_title("In zeitlicher Reihenfolge der Messungen", fontsize=14)
    ax[0].set_ylim(-1.5, 1.05)
    ax[0].grid(alpha=0.3, axis="y")

    for k, (h1, h2) in enumerate(halb):
        ax[1].plot([0, 1], [h1, h2], marker="o", lw=2.2, color=cols[k],
                   label=etik[k].replace("\n", " "))
    ax[1].axhline(0, color="k", lw=1.2)
    ax[1].set_xticks([0, 1])
    ax[1].set_xticklabels(["erste Hälfte", "zweite Hälfte"])
    ax[1].set_ylabel("Split-half-Reliabilität r")
    ax[1].set_title("Innerhalb jeder Aufnahme", fontsize=14)
    ax[1].legend(fontsize=10, loc="center left", bbox_to_anchor=(1.02, 0.5))
    ax[1].grid(alpha=0.3, axis="y")

    fig.suptitle("Ist es der Applikator oder einfach die Uhrzeit?   "
                 "Die früheste Aufnahme ist nicht die beste, und die "
                 "Linse-Messungen bleiben über ihre eigene Dauer stabil.",
                 fontsize=14, y=1.01)
    fig.tight_layout()
    sichern(fig, "D2_applikator_zeitkontrolle")



# ════════════════════════════════════════════════════════════════════
#  E — Die drei tragfähigen Vergleiche
# ════════════════════════════════════════════════════════════════════
#
# Aufbau nach Rücksprache: die Messungen ohne Linse (09.09., normaler
# Reizkopf) bleiben außen vor, weil das Stoßwellengerät dort Probleme
# machte. Damit entfällt der Applikatorvergleich — er hätte das Gerät
# gemessen, nicht den Applikator.
#
# Übrig bleiben drei Vergleiche, jeder mit eigener Kontrolle:
#   1  akustische Dämpfung gegen ungedämpft (Referenz)
#   2  proximal gegen distal, Tag 1, normaler Kopf, rund 1,10 m Unterschied
#   3  proximal gegen distal, Tag 2, Linse,        rund 0,45 m Unterschied

E_DATEIEN = {
    "T1 ungedämpft":   "recordings/ERP_20260813_122235_nurAkustisch.csv",
    "T1 Kontrolle":    "recordings/ERP_20260813_122821_keinReiz.csv",
    "T1 Oberarm":      "recordings/ERP_20260813_125428_stimulationOberarm.csv",
    "T1 Fuß":          "recordings/ERP_20260813_131731_stimulationFuss.csv",
    "T2 Kontrolle":    "recordings/ERP_20260909_163744.csv",
    "T2 Oberschenkel": "recordings/ERP_20260909_164514.csv",
    "T2 Wade":         "recordings/ERP_20260909_165220.csv",
}
E_FARBEN = {
    "T1 ungedämpft": "#f97b8b", "T1 Kontrolle": "#7d8794",
    "T2 Kontrolle": "#b0b8c1",
    "T1 Oberarm": "#ffa726", "T1 Fuß": "#4a9eff",
    "T2 Oberschenkel": "#ffa726", "T2 Wade": "#3ddc84",
}
E_FENSTER = (100, 500)
RMS = lambda x, tt: float(np.sqrt((x[(tt >= E_FENSTER[0]) & (tt <= E_FENSTER[1])] ** 2).mean()))
P2L = lambda x, tt: peak_latency(x, tt, (150, 450), "max")["latenz_ms"]


def _e_laden():
    """Rohe Epochen je Bedingung, ROI-gemittelt. Angeglichen wird nicht
    hier, sondern paarweise im jeweiligen Vergleich — eine globale
    Angleichung würde von der kleinsten Bedingung diktiert und alle
    anderen Vergleiche unnötig schwächen."""
    out = {}
    for name, pfad in E_DATEIEN.items():
        s = load_session(ROOT / pfad)
        eeg = OfflineFilter(fs=s.fs).highpass(1.0).notch(50.0)(s.raw)
        r = replay(eeg, s.trigger_idx, fs=s.fs, ch_labels=s.ch_labels,
                   label=name, with_tfr=False, **PARAM)
        out[name] = r.epochs[:, :, [r.ch(c) for c in ROI]].mean(2)
        out["_t"] = r.time_axis
    return out


def _paar(E, a, b, seed=0):
    return matched_subsample([E[a], E[b]], seed=seed)


def _evoked_diff(A, B, t, fenster, n_boot=1500, seed=0):
    """Unterschied der **rauschbereinigten** evozierten Stärke, B − A.

    Der rohe RMS des Mittelwerts enthält noch σ²/n an Rauschen. Zwei
    Bedingungen mit gleichem n, aber unterschiedlich unruhigen Einzeltrials
    unterscheiden sich darin schon ohne jeden Signalunterschied — eine
    verrauschte Aufnahme sähe dann nach mehr Antwort aus. `evoked_rms`
    zieht den erwarteten Rauschanteil ab; bleibt nichts übrig, ist das
    Ergebnis 0."""
    f = lambda ep: evoked_rms(ep, t, fenster)["rms"]
    punkt = f(B) - f(A)
    rng = np.random.default_rng(seed)
    vals = np.empty(n_boot)
    for i in range(n_boot):
        vals[i] = (f(B[rng.integers(0, len(B), len(B))])
                   - f(A[rng.integers(0, len(A), len(A))]))
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return punkt, float(lo), float(hi)


def _kurven(ax, E, namen, t, test=None, titel="", xlim=(-150, 800)):
    for n in namen:
        ep = E[n]
        m = ep.mean(0)
        sem = ep.std(0, ddof=1) / np.sqrt(len(ep))
        ls = "--" if n == "T2 Kontrolle" else "-"
        ax.plot(t, m, lw=2.0, ls=ls, color=E_FARBEN[n], label=f"{n}  (n={len(ep)})")
        ax.fill_between(t, m - sem, m + sem, color=E_FARBEN[n], alpha=0.16, lw=0)
    if test is not None:
        cl = test["cluster"]
        for _, c in cl[cl["p"] < 0.05].iterrows():
            ax.axvspan(c["von_ms"], c["bis_ms"], color="#3ddc84", alpha=0.16,
                       lw=0, zorder=0)
    ax.axvline(0, color=TEXT_PRIMARY, lw=1, ls="--", alpha=0.7)
    ax.axhline(0, color=TEXT_PRIMARY, lw=0.8, alpha=0.3)
    ax.set_xlim(xlim)
    ax.set_xlabel("Zeit [ms]")
    ax.set_ylabel("Amplitude [µV]")
    ax.set_title(titel)
    ax.legend(fontsize=10)
    ax.grid(alpha=0.3)


def E1_akustische_daempfung(E=None):
    """Referenz: die Dämpfung wirkt, und die Kontrolle ist über Tage stabil.

    Drei Kurven, alle ohne Hautreiz. Die beiden gedämpften Kontrollen
    stammen von Messtagen drei Wochen auseinander — dass sie
    übereinanderliegen, ist selbst das Ergebnis: die Kette ist über Tage
    reproduzierbar. Die ungedämpfte Bedingung weicht von beiden im selben
    frühen Fenster ab."""
    E = E or _e_laden()
    t = E["_t"]
    tA = cluster_permutation_test(*_paar(E, "T1 ungedämpft", "T1 Kontrolle"),
                                  t, window=(0, 800), n_perm=4000)
    tB = cluster_permutation_test(*_paar(E, "T1 ungedämpft", "T2 Kontrolle"),
                                  t, window=(0, 800), n_perm=4000)
    tN = cluster_permutation_test(*_paar(E, "T1 Kontrolle", "T2 Kontrolle"),
                                  t, window=(0, 800), n_perm=4000)

    fig = plt.figure(figsize=(13, 8.5))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.5, 1], hspace=0.42, wspace=0.22)
    ax = fig.add_subplot(gs[0, :])
    _kurven(ax, E, ["T1 ungedämpft", "T1 Kontrolle", "T2 Kontrolle"], t,
            test=tA, titel="Akustische Dämpfung — alle drei ohne Hautreiz")

    def _p(test):
        cl = test["cluster"]
        sig = cl[cl["p"] < 0.05]
        return (f"{sig.iloc[0]['von_ms']:.0f}–{sig.iloc[0]['bis_ms']:.0f} ms, "
                f"p = {sig.iloc[0]['p']:.3f}") if len(sig) else \
               (f"kein Cluster (bestes p = {cl['p'].min():.2f})" if len(cl)
                else "kein Cluster")
    infokasten(ax,
               f"ungedämpft gegen Kontrolle Tag 1:  {_p(tA)}\n"
               f"ungedämpft gegen Kontrolle Tag 2:  {_p(tB)}\n"
               f"Kontrolle Tag 1 gegen Tag 2 (Nullprobe):  {_p(tN)}")

    for sp, (test, titel) in enumerate([
            (tA, "ungedämpft gegen Kontrolle — hier ist ein Unterschied"),
            (tN, "Kontrolle gegen Kontrolle — hier darf keiner sein")]):
        a = fig.add_subplot(gs[1, sp])
        plot_cluster_test(test, ax=a)
        a.set_xlim(-150, 800)
        a.set_ylim(-4.5, 4.5)
        a.set_title(titel, fontsize=13)
    fussnote(fig, "Beide Messtage, drei Wochen auseinander · " + FUSSNOTE_NC)
    sichern(fig, "E1_akustische_daempfung")


def E2_koerperstellen(E=None):
    """Proximal gegen distal, an beiden Messtagen nebeneinander.

    Tag 1 mit dem normalen Kopf über rund 1,10 m Wegunterschied, Tag 2 mit
    der Linse über rund 0,45 m. Gleiche y-Skala, damit die Amplituden
    vergleichbar bleiben."""
    E = E or _e_laden()
    t = E["_t"]
    paare = [("T1 Oberarm", "T1 Fuß", "Tag 1 · normaler Kopf · ~1,10 m", "T1 Kontrolle"),
             ("T2 Oberschenkel", "T2 Wade", "Tag 2 · Linse · ~0,45 m", "T2 Kontrolle")]

    fig, axes = plt.subplots(1, 2, figsize=(15, 5.8), sharey=True)
    for ax, (prox, dist, titel, ktrl) in zip(axes, paare):
        A, B = _paar(E, prox, dist)
        test = cluster_permutation_test(A, B, t, window=(0, 800), n_perm=4000)
        _kurven(ax, {**E, prox: A, dist: B}, [prox, dist, ktrl], t,
                test=test, titel=titel)
        ad, al, ah = _evoked_diff(A, B, t, (100, 500))
        xk = bootstrap_shift(A, B, t, window=(100, 500), max_lag_ms=150,
                             n_boot=1500)
        ax.legend(fontsize=10, loc="upper left")
        infokasten(ax,
                   f"Amplitude, rauschbereinigt (100–500 ms):  {ad:+.2f} µV "
                   f"[{al:+.2f}, {ah:+.2f}]\n"
                   f"Latenz distal − proximal:  {xk['verschiebung_ms']:+.0f} ms "
                   f"[{xk['lo']:+.0f}, {xk['hi']:+.0f}]")
    axes[1].set_ylabel("")
    fig.suptitle("Körperstelle: proximal gegen distal — grün: Cluster mit p < 0.05",
                 fontsize=15, y=1.01)
    fig.tight_layout()
    fussnote(fig, "Kontrolle des jeweiligen Tages grau · " + FUSSNOTE_NC)
    sichern(fig, "E2_koerperstellen_beide_tage")


def E3_uebersicht(E=None):
    """Alle Vergleiche auf einen Blick, gegen ihre eigene Nachweisgrenze.

    Links die Amplitude, rechts die Latenz. Die graue Fläche ist das, was
    dasselbe Maß liefert, wenn gar kein Unterschied vorliegt — links aus
    zwei Kontrollen verschiedener Messtage, rechts aus Hälften derselben
    Reizbedingung. Ein Balken, der die Fläche nicht verlässt, ist kein
    Befund."""
    E = E or _e_laden()
    t = E["_t"]

    amp_zeilen = [
        ("ungedämpft − Kontrolle T1", "T1 Kontrolle", "T1 ungedämpft", "#f97b8b"),
        ("ungedämpft − Kontrolle T2", "T2 Kontrolle", "T1 ungedämpft", "#f97b8b"),
        ("Oberarm − Kontrolle T1",    "T1 Kontrolle", "T1 Oberarm",    "#ffa726"),
        ("Fuß − Kontrolle T1",        "T1 Kontrolle", "T1 Fuß",        "#4a9eff"),
        ("Oberschenkel − Kontrolle T2", "T2 Kontrolle", "T2 Oberschenkel", "#ffa726"),
        ("Wade − Kontrolle T2",       "T2 Kontrolle", "T2 Wade",       "#3ddc84"),
        ("Fuß − Oberarm (T1)",        "T1 Oberarm",   "T1 Fuß",        "#8b7cf6"),
        ("Wade − Oberschenkel (T2)",  "T2 Oberschenkel", "T2 Wade",    "#8b7cf6"),
    ]
    # Zwei Fenster, und jede Zeile wird in BEIDEN bewertet. Je Vergleich
    # das passende Fenster auszusuchen waere Rosinenpickerei: der
    # akustische Anteil liegt frueh, die Antwort auf den Hautreiz spaet —
    # wer nur eines zeigt, laesst die halbe Aussage weg.
    FENSTER = [((0, 100), "früh: RMS 0–100 ms"),
               ((100, 500), "spät: RMS 100–500 ms")]

    fig, ax = plt.subplots(1, 3, figsize=(19, 6),
                           gridspec_kw={"width_ratios": [1.25, 1.0, 1.0]})
    y = np.arange(len(amp_zeilen))[::-1]
    etik = []

    for sp, (fen, titel) in enumerate(FENSTER):
        werte, lo, hi, cols = [], [], [], []
        for lab, a, b, col in amp_zeilen:
            A, B = _paar(E, a, b)
            d, l, h = _evoked_diff(A, B, t, fen)
            werte.append(d); lo.append(l); hi.append(h)
            cols.append(col)
            if sp == 0:
                etik.append(f"{lab}  (n={len(A)})")
        A, B = _paar(E, "T1 Kontrolle", "T2 Kontrolle")
        nd, nl, nh = _evoked_diff(A, B, t, fen)
        nul = {"lo": nl, "hi": nh}

        a_ = ax[sp]
        a_.axvspan(nul["lo"], nul["hi"], color="gray", alpha=0.22, lw=0, zorder=0,
                   label="Nullprobe: Kontrolle Tag 1 gegen Tag 2")
        a_.errorbar(werte, y, xerr=[np.array(werte) - lo, np.array(hi) - werte],
                    fmt="none", lw=2.2, capsize=5, ecolor="gray")
        for k, (w, c) in enumerate(zip(werte, cols)):
            a_.plot(w, y[k], "o", ms=11, color=c)
        a_.axvline(0, color=TEXT_PRIMARY, lw=1.4)
        a_.set_yticks(y)
        a_.set_yticklabels(etik if sp == 0 else [])
        a_.set_xlabel("Unterschied, rauschbereinigt [µV]")
        a_.set_title(titel)
        a_.set_ylim(-0.9, len(y) - 0.4)
        a_.grid(alpha=0.3, axis="x")
        if sp == 0:
            a_.legend(fontsize=9, loc="lower right", framealpha=0.9)

    # ── Latenz: nur dort, wo beide Bedingungen eine Antwort haben ──────
    # Weglaenge je Vergleich, daraus die Erwartung fuer zwei Fasertypen:
    #   A-delta (nozizeptiv, 10-15 m/s) und A-beta (Beruehrung, ~50 m/s).
    # Die beiden Vorhersagen liegen weit auseinander — daran laesst sich
    # ablesen, welche Art von Reizantwort die Daten ueberhaupt zulassen.
    lat_zeilen = [("Fuß − Oberarm (T1, ~1,10 m)", "T1 Oberarm", "T1 Fuß",
                   "#4a9eff", 1.10),
                  ("Wade − Oberschenkel (T2, ~0,45 m)", "T2 Oberschenkel",
                   "T2 Wade", "#3ddc84", 0.45)]
    lw_, llo, lhi, lcol, letik, dist = [], [], [], [], [], []
    for lab, a, b, col, d in lat_zeilen:
        A, B = _paar(E, a, b)
        x = bootstrap_shift(A, B, t, window=(100, 500), max_lag_ms=150, n_boot=1500)
        lw_.append(x["verschiebung_ms"]); llo.append(x["lo"]); lhi.append(x["hi"])
        lcol.append(col); letik.append(lab); dist.append(d)

    # Rauschgrenze: Hälften derselben Reizbedingung
    haelften = []
    for n in ["T1 Oberarm", "T1 Fuß", "T2 Oberschenkel", "T2 Wade"]:
        ep = E[n]; h = len(ep) // 2
        haelften.append(bootstrap_shift(ep[:h], ep[h:], t, window=(100, 500),
                                        max_lag_ms=150, n_boot=1000)["verschiebung_ms"])
    grenze = float(np.max(np.abs(haelften)))

    y2 = np.arange(len(lw_))[::-1]
    ax[2].axvspan(-grenze, grenze, color="gray", alpha=0.22, lw=0, zorder=0,
                  label=f"Nachweisgrenze ±{grenze:.0f} ms\n(Hälften derselben Bedingung)")
    ax[2].errorbar(lw_, y2, xerr=[np.array(lw_) - llo, np.array(lhi) - lw_],
                   fmt="none", lw=2.2, capsize=5, ecolor="gray")
    for k, (w, c) in enumerate(zip(lw_, lcol)):
        ax[2].plot(w, y2[k], "o", ms=11, color=c)
    # Erwartungsbereiche einzeichnen
    for k, d in enumerate(dist):
        yy = y2[k]
        ad_lo, ad_hi = d / 15 * 1000, d / 10 * 1000        # A-delta
        ab = d / 50 * 1000                                  # A-beta
        ax[2].plot([ad_lo, ad_hi], [yy + 0.20] * 2, lw=6, solid_capstyle="butt",
                   color="#f97b8b", alpha=0.85,
                   label="erwartet bei Aδ (Schmerz, 10–15 m/s)" if k == 0 else None)
        ax[2].plot([ab], [yy + 0.20], marker="v", ms=10, color="#42d4f4",
                   label="erwartet bei Aβ (Berührung, ~50 m/s)" if k == 0 else None)

    ax[2].axvline(0, color=TEXT_PRIMARY, lw=1.4)
    ax[2].set_yticks(y2); ax[2].set_yticklabels(letik)
    ax[2].set_xlim(-130, 130)
    ax[2].set_ylim(-0.9, len(lw_) - 0.15)
    ax[2].set_xlabel("distal später [ms]  →")
    ax[2].set_title("Latenz (nur wo beide eine Antwort haben)")
    ax[2].legend(fontsize=9, loc="lower left", framealpha=0.9)
    ax[2].grid(alpha=0.3, axis="x")

    fig.suptitle("Alle Vergleiche gegen ihre eigene Nachweisgrenze",
                 fontsize=15, y=1.03)
    fig.tight_layout()
    fussnote(fig, "Jeder Vergleich paarweise auf gleiche Epochenzahl "
                  "angeglichen · " + FUSSNOTE_NC)
    sichern(fig, "E3_uebersicht_amplitude_latenz")


# ════════════════════════════════════════════════════════════════════
ABBILDUNGEN = {
    "A1": A1_verarbeitungskette, "A2": A2_filter, "A3": A3_triggerauswahl,
    "A4": A4_mittelungsgewinn,   "A5": A5_kanaluebersicht,
    "B1": B1_serie_uebersicht,   "B2": B2_koerperstelle,
    "B3": B3_reproduzierbarkeit, "B4": B4_akustisch,
    "B5": B5_nachweisgrenze,     "B6": B6_tfr,
    "C1": C1_fuss_oberarm,       "C2": C2_akustisch_kontrolle,
    "C3": C3_energie_zeitfenster,
    # D1/D2 (Applikatorvergleich) sind stillgelegt: sie stuetzen sich auf
    # die Messungen mit normalem Reizkopf vom 09.09., bei denen das
    # Stosswellengeraet Probleme machte. Der Vergleich haette das Geraet
    # gemessen, nicht den Applikator. Der Code bleibt fuer den Fall, dass
    # die Messung sauber wiederholt wird.
    "E1": E1_akustische_daempfung,
    "E2": E2_koerperstellen,
    "E3": E3_uebersicht,
}
AKTUELLER_STIL = "hell"


def main(auswahl=None):
    global AKTUELLER_STIL
    namen = auswahl or list(ABBILDUNGEN)
    unbekannt = [n for n in namen if n not in ABBILDUNGEN]
    if unbekannt:
        raise SystemExit(f"Unbekannt: {unbekannt}. Verfügbar: {list(ABBILDUNGEN)}")

    # Die Durchläufe einmal rechnen und an alle Abbildungen weiterreichen —
    # sonst wird jede Datei bis zu dreimal eingelesen und gefiltert.
    braucht_sep9 = any(n.startswith("B") for n in namen)
    braucht_e = any(n.startswith("E") for n in namen)
    braucht_aug13 = any(n.startswith("C") for n in namen)
    sep9 = lade(SEP9, with_tfr="B6" in namen) if braucht_sep9 else None
    aug13 = lade(AUG13, param=PARAM_AUG13) if braucht_aug13 else None
    e_dat = _e_laden() if braucht_e else None

    for stil, dunkel in (("hell", False), ("dunkel", True)):
        AKTUELLER_STIL = stil
        print(f"\n── {stil} ──")
        use_app_style(dark=dunkel, presentation=True)
        for n in namen:
            fn = ABBILDUNGEN[n]
            daten = (sep9 if n.startswith(("B", "D")) else
                     aug13 if n.startswith("C") else
                     e_dat if n.startswith("E") else None)
            try:
                fn(daten) if daten is not None else fn()
            except Exception as e:
                print(f"    FEHLER {n}: {type(e).__name__}: {e}")

    print(f"\nFertig — {OUT}")


if __name__ == "__main__":
    main(sys.argv[1:] or None)
