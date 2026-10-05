"""offline/plots.py — Matplotlib-Fassung der Plots aus der Anwendung.

`gui/erp_plot.py` (pyqtgraph) und `gui/tfr_plot.py` (matplotlib in einem
Qt-Canvas) hängen beide an einem laufenden Qt-Fenster und lassen sich im
Notebook nicht verwenden. Hier stehen dieselben Darstellungen als reine
Matplotlib-Funktionen: gleiche Kanalfarben, gleiche Farbskala und
Normierung (RdYlGn_r, z-Score −4…+4), gleiche Aufteilung in TFR-Low und
TFR-High. Wer die Bilder nebeneinanderlegt, soll dasselbe sehen.
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm

try:                                    # Farben aus der App übernehmen
    from gui.theme import (CHANNEL_COLORS, BG_PLOT, TEXT_PRIMARY, BORDER)
except Exception:                       # ohne PyQt6 installiert
    CHANNEL_COLORS = ["#4a9eff", "#3ddc84", "#e5a8f0", "#ffa726",
                      "#8b7cf6", "#42d4f4", "#f97b8b", "#bfef45"]
    BG_PLOT, TEXT_PRIMARY, BORDER = "#12151a", "#e6e9ed", "#333a43"

DEFAULT_LABELS = ["Fz", "C3", "Cz", "C4", "Pz", "PO7", "Oz", "PO8"]


def use_app_style(dark: bool = True, presentation: bool = False):
    """Plots auf das Aussehen der Anwendung stellen.

    Einmal pro Notebook aufrufen. `dark=False` gibt den hellen
    Matplotlib-Standard — besser für Beamer und Ausdruck.
    `presentation=True` vergrößert alle Schriften und Linien: eine
    Abbildung, die am Bildschirm gut aussieht, ist an die Wand geworfen
    meist unlesbar."""
    plt.rcdefaults()
    if presentation:
        plt.rcParams.update({
            "font.size": 13, "axes.titlesize": 15, "axes.labelsize": 13,
            "xtick.labelsize": 12, "ytick.labelsize": 12,
            "legend.fontsize": 12, "figure.titlesize": 17,
            "lines.linewidth": 2.0, "axes.linewidth": 1.2,
            "figure.dpi": 110, "savefig.dpi": 200,
            "savefig.bbox": "tight",
        })
    if not dark:
        # Hell: nur ein dezentes Raster, sonst Matplotlib-Standard
        plt.rcParams.update({"grid.alpha": 0.3, "axes.grid": False})
        return
    plt.rcParams.update({
        "figure.facecolor":  BG_PLOT,
        "axes.facecolor":    BG_PLOT,
        "savefig.facecolor": BG_PLOT,
        "axes.edgecolor":    BORDER,
        "axes.labelcolor":   TEXT_PRIMARY,
        "text.color":        TEXT_PRIMARY,
        "xtick.color":       TEXT_PRIMARY,
        "ytick.color":       TEXT_PRIMARY,
        "grid.color":        BORDER,
        "grid.alpha":        0.3,
        "legend.facecolor":  BG_PLOT,
        "legend.edgecolor":  BORDER,
        "figure.dpi":        110,
    })


def _unpack_erp(result):
    """`ReplayResult` oder rohe Arrays annehmen."""
    if hasattr(result, "erp_mean"):
        labels = result.ch_labels or DEFAULT_LABELS[:result.erp_mean.shape[1]]
        return result.time_axis, result.erp_mean, result.n_accepted, labels, result
    raise TypeError("plot_erp erwartet ein ReplayResult")


# ── ERP ──────────────────────────────────────────────────────────────
def plot_erp(result, channels=None, sem: bool = False,
             xlim=None, ylim=None, ax=None, title=None):
    """Alle Kanäle übereinander — die Notebook-Fassung von
    `ERPPlotWidget.update_erp()`.

    channels: Auswahl als Namen oder Indizes, Vorgabe alle
    sem:      Standardfehler als Band mitzeichnen
    """
    t, mean, n, labels, res = _unpack_erp(result)
    idx = _channel_idx(channels, labels)

    if ax is None:
        _, ax = plt.subplots(figsize=(9, 4.5))
    band = res.erp_sem() if sem else None

    for i in idx:
        color = CHANNEL_COLORS[i % len(CHANNEL_COLORS)]
        ax.plot(t, mean[:, i], color=color, lw=1.8, label=labels[i])
        if band is not None:
            ax.fill_between(t, mean[:, i] - band[:, i], mean[:, i] + band[:, i],
                            color=color, alpha=0.18, lw=0)

    ax.axvline(0, color=TEXT_PRIMARY, lw=1, ls="--", alpha=0.7)
    ax.axhline(0, color=TEXT_PRIMARY, lw=0.8, alpha=0.3)
    ax.set_xlabel("Zeit [ms]")
    ax.set_ylabel("Amplitude [µV]")
    ax.grid(True, alpha=0.3)
    ax.set_xlim(xlim or (t[0], t[-1]))
    if ylim:
        ax.set_ylim(ylim)
    ax.legend(ncol=4, fontsize=8, loc="upper right")
    ax.set_title(title or f"Evoziertes Potential — n = {n} Epochen "
                          f"{('· ' + res.label) if res.label else ''}")
    return ax


def plot_erp_grid(result, channels=None, sem: bool = True,
                  ncols: int = 2, ylim=None, sharey: bool = True):
    """Ein Feld pro Kanal. Im Live-Betrieb unpraktisch, offline aber die
    ehrlichere Ansicht: übereinandergelegte Kurven verdecken sich, sobald
    ein Kanal deutlich größere Amplituden hat."""
    t, mean, n, labels, res = _unpack_erp(result)
    idx = _channel_idx(channels, labels)
    band = res.erp_sem() if sem else None

    nrows = int(np.ceil(len(idx) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(5.2 * ncols, 2.4 * nrows),
                             sharex=True, sharey=sharey, squeeze=False)
    flat = axes.ravel()

    for k, i in enumerate(idx):
        ax = flat[k]
        color = CHANNEL_COLORS[i % len(CHANNEL_COLORS)]
        ax.plot(t, mean[:, i], color=color, lw=1.6)
        if band is not None:
            ax.fill_between(t, mean[:, i] - band[:, i], mean[:, i] + band[:, i],
                            color=color, alpha=0.2, lw=0)
        ax.axvline(0, color=TEXT_PRIMARY, lw=0.9, ls="--", alpha=0.6)
        ax.axhline(0, color=TEXT_PRIMARY, lw=0.7, alpha=0.25)
        ax.grid(True, alpha=0.25)
        ax.set_title(labels[i], fontsize=10, color=color)
        if ylim:
            ax.set_ylim(ylim)
    for ax in flat[len(idx):]:
        ax.set_visible(False)
    for ax in axes[-1]:
        ax.set_xlabel("Zeit [ms]")
    for row in axes:
        row[0].set_ylabel("µV")

    fig.suptitle(f"ERP je Kanal — n = {n} Epochen"
                 f"{(' · ' + res.label) if res.label else ''}")
    fig.tight_layout()
    return fig, axes


# ── TFR ──────────────────────────────────────────────────────────────
def _tfr_of(result):
    tfr = getattr(result, "tfr", result)
    if tfr is None or getattr(tfr, "P_total", None) is None:
        label = getattr(result, "label", "?")
        raise ValueError(
            f"Keine TFR-Ergebnisse für '{label}' — mit with_tfr=True neu "
            "durchlaufen lassen, oder es kam keine Epoche zustande.")
    return tfr


def plot_tfr(result, vmax: float = 4.0, cmap: str = "RdYlGn_r",
             figsize=(9, 6), axes=None, colorbar: bool = True,
             xlim=None, title=None):
    """Zeit-Frequenz-Darstellung, Aufbau wie `TFRPlotWidget`: oben
    10–50 Hz, unten 1–10 Hz, beide als z-Score gegen die Grundlinie
    (−1,0 s bis −0,2 s), auf ±4 begrenzt.

    axes: (ax_hoch, ax_tief) — zum Zeichnen in ein vorhandenes Gitter.
          Ohne Angabe wird eine eigene Abbildung erzeugt."""
    tfr = _tfr_of(result)
    norm = TwoSlopeNorm(vmin=-vmax, vcenter=0, vmax=vmax)
    t = tfr.t_all

    if axes is None:
        fig, (ax_hi, ax_lo) = plt.subplots(2, 1, figsize=figsize,
                                           gridspec_kw={"hspace": 0.35})
    else:
        ax_hi, ax_lo = axes
        fig = ax_hi.figure

    for ax, P, f, name in ((ax_hi, tfr.P_high, tfr.f_high, "High (10–50 Hz)"),
                           (ax_lo, tfr.P_low,  tfr.f_low,  "Low (1–10 Hz)")):
        im = ax.imshow(np.clip(P, -vmax, vmax), origin="lower", aspect="auto",
                       cmap=cmap, norm=norm, interpolation="bilinear",
                       extent=[float(t[0]), float(t[-1]),
                               float(f[0]), float(f[-1])])
        ax.axvline(0, color=TEXT_PRIMARY, lw=1, ls="--", alpha=0.7)
        ax.set_ylabel("Frequenz [Hz]")
        if xlim:
            ax.set_xlim(xlim)
        if axes is None:
            ax.set_title(f"TFR {name} — n={tfr.n_epochs}")
        if colorbar:
            fig.colorbar(im, ax=ax, label="z-Score")

    ax_lo.set_xlabel("Zeit [s]")
    label = title if title is not None else getattr(result, "label", "")
    if label and axes is None:
        fig.suptitle(label)
    return fig, (ax_hi, ax_lo)


def plot_tfr_grid(results: dict, vmax: float = 4.0, cmap: str = "RdYlGn_r",
                  xlim=None, height: float = 2.6, width: float = 3.6):
    """Mehrere Bedingungen nebeneinander, **eine gemeinsame Farbskala**.

    Getrennte Skalen je Bedingung wären der übliche Fehler: dann sieht
    jede Karte gleich kräftig aus, egal wie stark die Antwort war, und der
    Vergleich zeigt nur noch die jeweilige Normierung. Deshalb ein
    gemeinsamer Bereich ±vmax und ein einziger Farbbalken.

    Oben 10–50 Hz, unten 1–10 Hz, je Spalte eine Bedingung.
    """
    namen = list(results)
    n = len(namen)
    fig, axes = plt.subplots(2, n, figsize=(width * n + 1.4, 2 * height),
                             squeeze=False, sharex=True)
    im = None
    for k, name in enumerate(namen):
        tfr = _tfr_of(results[name])
        plot_tfr(results[name], vmax=vmax, cmap=cmap, xlim=xlim,
                 axes=(axes[0, k], axes[1, k]), colorbar=False)
        axes[0, k].set_title(f"{name}\nn={tfr.n_epochs}", fontsize=10)
        im = axes[0, k].images[0]
        if k:                       # Achsenbeschriftung nur ganz links
            for ax in axes[:, k]:
                ax.set_ylabel("")
    fig.colorbar(im, ax=axes, label="z-Score", fraction=0.025, pad=0.015)
    return fig, axes


def tfr_difference(result_a, result_b, vmax: float = 2.0,
                   cmap: str = "RdBu_r", xlim=None, figsize=(9, 6),
                   title=None):
    """Differenz zweier z-Karten, `a` − `b` (üblich: Bedingung − Kontrolle).

    Beide Karten sind bereits gegen ihre **eigene** Grundlinie normiert.
    Die Differenz zeigt daher, wo sich die Bedingungen in ihrer relativen
    Änderung gegenüber der jeweiligen Ruhe unterscheiden — nicht, wo mehr
    absolute Leistung liegt. Die Achsen müssen übereinstimmen, was sie tun,
    solange beide Durchläufe dieselben TFR-Parameter benutzt haben.
    """
    A, B = _tfr_of(result_a), _tfr_of(result_b)
    if A.P_total.shape != B.P_total.shape:
        raise ValueError(
            f"Karten passen nicht zusammen: {A.P_total.shape} vs "
            f"{B.P_total.shape} — beide Durchläufe brauchen dieselben "
            "tfr_pre_ms / tfr_post_ms / tfr_roi.")

    norm = TwoSlopeNorm(vmin=-vmax, vcenter=0, vmax=vmax)
    t = A.t_all
    n_lo = len(A.f_low)
    D = A.P_total - B.P_total
    fig, (ax_hi, ax_lo) = plt.subplots(2, 1, figsize=figsize,
                                       gridspec_kw={"hspace": 0.35})

    for ax, P, f, name in ((ax_hi, D[n_lo:], A.f_high, "High (10–50 Hz)"),
                           (ax_lo, D[:n_lo], A.f_low,  "Low (1–10 Hz)")):
        im = ax.imshow(np.clip(P, -vmax, vmax), origin="lower", aspect="auto",
                       cmap=cmap, norm=norm, interpolation="bilinear",
                       extent=[float(t[0]), float(t[-1]),
                               float(f[0]), float(f[-1])])
        ax.axvline(0, color=TEXT_PRIMARY, lw=1, ls="--", alpha=0.7)
        ax.set_ylabel("Frequenz [Hz]")
        ax.set_title(f"Differenz {name}")
        if xlim:
            ax.set_xlim(xlim)
        fig.colorbar(im, ax=ax, label="Δ z-Score")

    ax_lo.set_xlabel("Zeit [s]")
    a_lab = getattr(result_a, "label", "a")
    b_lab = getattr(result_b, "label", "b")
    fig.suptitle(title or f"{a_lab} − {b_lab}   "
                          f"(n={A.n_epochs} vs {B.n_epochs})")
    return fig, (ax_hi, ax_lo)


# ── Rohsignal ────────────────────────────────────────────────────────
def plot_raw(t, data, ch_labels=None, trigger_t=None, offset=None,
             xlim=None, figsize=(12, 6), title="Signal"):
    """Kanäle gestapelt, wie im Rohdatenfenster der App — zum Sichten der
    Aufnahme vor der Auswertung.

    offset: Abstand zwischen den Kanälen in µV; ohne Angabe aus der
            Streuung geschätzt."""
    data = np.asarray(data, dtype=float)
    labels = list(ch_labels or DEFAULT_LABELS[:data.shape[1]])
    if offset is None:
        offset = 6 * float(np.median(np.std(data, axis=0))) or 1.0

    fig, ax = plt.subplots(figsize=figsize)
    for i in range(data.shape[1]):
        ax.plot(t, data[:, i] - i * offset, lw=0.6,
                color=CHANNEL_COLORS[i % len(CHANNEL_COLORS)])
    if trigger_t is not None:
        for tt in np.atleast_1d(trigger_t):
            ax.axvline(float(tt), color=TEXT_PRIMARY, lw=0.7, ls="--", alpha=0.35)

    ax.set_yticks([-i * offset for i in range(data.shape[1])])
    ax.set_yticklabels(labels)
    ax.set_xlabel("Zeit [s]")
    ax.set_xlim(xlim or (t[0], t[-1]))
    ax.set_title(f"{title}  (Kanalabstand {offset:.0f} µV)")
    ax.grid(True, axis="x", alpha=0.25)
    return fig, ax


# ── Vergleich mehrerer Bedingungen ───────────────────────────────────
CONDITION_COLORS = ["#4a9eff", "#ffa726", "#3ddc84", "#f97b8b",
                    "#8b7cf6", "#42d4f4"]


def plot_compare(results: dict, channel, sem: bool = True, xlim=None,
                 ylim=None, ax=None, title=None, clusters=None,
                 mark_ms=None, colors=None, cluster_color="#3ddc84"):
    """Mehrere Bedingungen in einem Kanal übereinander.

    results:  {name: ReplayResult}
    clusters: Ergebnis von `cluster_permutation_test` — bedeutsame
              Abschnitte (p < 0.05) werden hinterlegt
    mark_ms:  Latenzen als senkrechte Striche, {name: ms}
    colors:   Farben der Kurven. Entweder eine Liste in der Reihenfolge
              von `results` oder ein Wörterbuch {name: farbe}; beim
              Wörterbuch behalten nicht genannte Bedingungen ihre
              Vorgabefarbe. Ohne Angabe gilt CONDITION_COLORS.
    cluster_color: Farbe der hinterlegten Cluster.
    """
    if ax is None:
        _, ax = plt.subplots(figsize=(10, 4.5))

    for k, (name, res) in enumerate(results.items()):
        color = CONDITION_COLORS[k % len(CONDITION_COLORS)]
        if isinstance(colors, dict):
            color = colors.get(name, color)
        elif colors is not None and k < len(colors):
            color = colors[k]
        t, x = res.time_axis, res.trace(channel)
        ax.plot(t, x, lw=1.8, color=color, label=f"{name}  (n={res.n_accepted})")
        if sem:
            ep = res.epoch_traces(channel)
            if len(ep) > 1:
                s = ep.std(axis=0, ddof=1) / np.sqrt(len(ep))
                ax.fill_between(t, x - s, x + s, color=color, alpha=0.18, lw=0)
        if mark_ms and name in mark_ms:
            ax.axvline(mark_ms[name], color=color, lw=1.2, ls=":", alpha=0.9)

    if clusters is not None:
        df = clusters["cluster"]
        for _, c in df[df["p"] < 0.05].iterrows():
            ax.axvspan(c["von_ms"], c["bis_ms"], color=cluster_color,
                       alpha=0.16, lw=0, zorder=0)

    ax.axvline(0, color=TEXT_PRIMARY, lw=1, ls="--", alpha=0.7)
    ax.axhline(0, color=TEXT_PRIMARY, lw=0.8, alpha=0.3)
    ax.set_xlabel("Zeit [ms]")
    ax.set_ylabel("Amplitude [µV]")
    ax.grid(True, alpha=0.3)
    if xlim:
        ax.set_xlim(xlim)
    if ylim:
        ax.set_ylim(ylim)
    elif xlim:
        # Matplotlib skaliert y über ALLE Daten, auch die außerhalb von xlim.
        # Bei einem Fenster bis 2000 ms, von dem nur 800 ms gezeigt werden,
        # staucht das die Kurven auf einen Bruchteil der Höhe.
        lo, hi = np.inf, -np.inf
        for name, res in results.items():
            t = res.time_axis
            m = (t >= xlim[0]) & (t <= xlim[1])
            if not m.any():
                continue
            y = res.trace(channel)[m]
            d = np.zeros_like(y)
            if sem:
                ep = res.epoch_traces(channel)
                if len(ep) > 1:
                    d = (ep.std(axis=0, ddof=1) / np.sqrt(len(ep)))[m]
            lo, hi = min(lo, float((y - d).min())), max(hi, float((y + d).max()))
        if np.isfinite(lo) and hi > lo:
            rand = 0.10 * (hi - lo)
            ax.set_ylim(lo - rand, hi + rand)
    ax.legend(fontsize=9)
    label = channel if isinstance(channel, str) else f"Kanal {channel}"
    ax.set_title(title or f"{label} — Bedingungen im Vergleich")
    return ax


def plot_cluster_test(test: dict, ax=None):
    """t-Kurve des Permutationstests mit hinterlegten Clustern."""
    if ax is None:
        _, ax = plt.subplots(figsize=(10, 2.6))
    ax.plot(test["t_zeit"], test["t"], lw=1.4, color=CONDITION_COLORS[0])
    for s in (+1, -1):
        ax.axhline(s * test["t_thresh"], ls="--", lw=0.9, alpha=0.6,
                   color=TEXT_PRIMARY)
    df = test["cluster"]
    for _, c in df.iterrows():
        ax.axvspan(c["von_ms"], c["bis_ms"], lw=0, zorder=0,
                   color="#3ddc84" if c["p"] < 0.05 else TEXT_PRIMARY,
                   alpha=0.22 if c["p"] < 0.05 else 0.08)
    ax.axvline(0, color=TEXT_PRIMARY, lw=1, ls="--", alpha=0.7)
    ax.set_xlabel("Zeit [ms]")
    ax.set_ylabel("t")
    ax.set_title(f"Unterschied punktweise (n={test['n_a']} vs {test['n_b']}) "
                 f"— grün: Cluster mit p < 0.05")
    ax.grid(alpha=0.3)
    return ax


def plot_selection(res, threshold=None, ax=None):
    """Welcher Trigger wurde warum verwendet — über die Sitzungszeit."""
    if ax is None:
        _, ax = plt.subplots(figsize=(10, 3.2))
    df = res.triggers
    farben = {"akzeptiert": "#3ddc84", "abgelehnt": "#f97b8b",
              "ignoriert": "#7d8794", "nicht gewählt": "#5b636d",
              "unvollständig": "#8b7cf6"}
    for status, grp in df.groupby("status"):
        c = next((v for k, v in farben.items() if status.startswith(k)), "#ffa726")
        ax.scatter(grp["t_s"], grp["max_abs"], s=30, color=c,
                   marker="o" if status == "akzeptiert" else "x",
                   label=f"{status} ({len(grp)})")
    if threshold:
        ax.axhline(threshold, ls="--", lw=1, alpha=0.7, color=TEXT_PRIMARY)
    ax.set_yscale("log")
    ax.set_xlabel("Zeit in der Sitzung [s]")
    ax.set_ylabel("max |µV| der Epoche")
    ax.set_title(f"Trigger-Auswahl — {res.label}")
    ax.legend(fontsize=8, ncol=2)
    ax.grid(alpha=0.3)
    return ax


def _channel_idx(channels, labels):
    if channels is None:
        return list(range(len(labels)))
    out = []
    for c in np.atleast_1d(channels):
        if isinstance(c, (int, np.integer)):
            out.append(int(c))
        else:
            out.append(labels.index(str(c)))
    return out
