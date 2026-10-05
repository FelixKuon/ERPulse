"""Offline-Auswertung aufgezeichneter Sitzungen.

Ergänzt die Live-Anwendung um einen Weg, dieselbe Auswertung nachträglich
auf einer CSV-Aufnahme zu fahren — mit nullphasiger Filterung (filtfilt)
statt des fortlaufenden IIR-Filters, der im Betrieb nötig ist.

Bewusst werden hier KEINE Kopien der Epochierung angelegt: `replay()`
treibt die echten `ERPProcessor`/`TFRProcessor` aus `core/` an, genau so
wie das Live-Fenster `gui/connection_dev_window.py` es im Betrieb tut. Was
die Anwendung anzeigt und
was das Notebook zeigt, kann dadurch nicht auseinanderlaufen.

Typische Verwendung:

    from offline import load_session, OfflineFilter, replay, plot_erp, plot_tfr

    ses = load_session("recordings/ERP_20260813_131731_stimulationFuss.csv")
    flt = OfflineFilter(fs=ses.fs).highpass(1.0).notch(50.0)
    eeg = flt(ses.raw)
    res = replay(eeg, ses.trigger_idx, fs=ses.fs)
    plot_erp(res)
    plot_tfr(res)
"""

from offline.loader import Session, load_session, list_sessions, channel_report
from offline.filters import OfflineFilter
from offline.selection import epoch_stats, select_triggers
from offline.replay import ReplayResult, replay, make_tfr_processor
from offline.measures import (peak_latency, fractional_area_latency,
                              crosscorr_shift, bootstrap_measure,
                              bootstrap_shift, bootstrap_difference,
                              cluster_permutation_test,
                              component_table, snr_table,
                              mean_amplitude, evoked_rms,
                              split_half_reliability,
                              single_trial_consistency, matched_subsample)
from offline.plots import (plot_erp, plot_erp_grid, plot_tfr, plot_raw,
                           plot_compare, plot_cluster_test, plot_selection,
                           plot_tfr_grid, tfr_difference, use_app_style)

__all__ = [
    "Session", "load_session", "list_sessions", "channel_report",
    "OfflineFilter",
    "epoch_stats", "select_triggers",
    "ReplayResult", "replay", "make_tfr_processor",
    "peak_latency", "fractional_area_latency", "crosscorr_shift",
    "bootstrap_measure", "bootstrap_shift", "bootstrap_difference",
    "cluster_permutation_test",
    "component_table", "snr_table",
    "mean_amplitude", "evoked_rms", "split_half_reliability",
    "single_trial_consistency", "matched_subsample",
    "plot_erp", "plot_erp_grid", "plot_tfr", "plot_raw", "plot_compare",
    "plot_cluster_test", "plot_selection", "plot_tfr_grid",
    "tfr_difference", "use_app_style",
]
