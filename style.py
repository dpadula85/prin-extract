"""style.py - Daniele's matplotlib style, mirroring ~/bin/plot_potentials.py's rcParams block.

Copied from `conformational_analyses/style.py` (`RC_PARAMS`, `new_axes`,
`rc_override`) and `exciphon/postprocess/style.py` (`save_centered`); keep in step
with them. One panel per figure; save with `save_centered`, never `bbox="tight"`.
"""

from contextlib import contextmanager

import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator

RC_PARAMS = {
    "font.family": "serif",
    "font.size": 42,
    "xtick.labelsize": 38,
    "ytick.labelsize": 38,
    "xtick.direction": "in",
    "ytick.direction": "in",
    "xtick.top": True,
    "ytick.right": True,
    "figure.figsize": (12, 9),
    "savefig.dpi": 600,
    # A size keyword, so a legend stays proportionate to the active "font.size".
    "legend.fontsize": "small",
    "legend.frameon": False,
}

# Major ticks longer/thicker than minor, so the two are visually distinct at a glance.
_MAJOR_TICK = {"length": 12, "width": 1.8}
_MINOR_TICK = {"length": 6, "width": 1.2}


def new_axes(use_latex: bool = True):
    """A figure/axes pair with Daniele's personal plotting style applied (inward
    major+minor ticks on all four sides, majors longer/thicker than minors, large
    fonts, (12, 9) figure, 600 dpi save).

    `use_latex=True` (default) renders text with the real LaTeX/pgf engine, like
    `plot_potentials.py` -- needs a working LaTeX installation; pass `False` to fall
    back to matplotlib's built-in mathtext where one isn't available.

    Updates `plt.rcParams` directly (matching `plot_potentials.py`'s own
    `mpl.rcParams.update(...)`), not via a `plt.rc_context` -- text (axis labels,
    legends, colorbars, ticks) is drawn lazily, at `show()`/`savefig()` time, well
    after this function returns, so a context manager that only wraps
    `plt.subplots()` reverts `text.usetex` before anything is actually rendered.
    That silent revert is exactly why `\\AA` and other text-mode-only LaTeX macros
    used to render as literal backslash-text instead of the real symbol: matplotlib's
    own mathtext fallback happens to handle some LaTeX macros close enough to pass a
    casual glance, but not that one. As a result, style/rcParams changes here persist
    for the rest of the process once called -- call this (or `plt.rcParams.update`
    directly) before any raw `plt.subplots()` figure that should share the style too.
    """
    plt.rcParams.update(RC_PARAMS)
    plt.rcParams["text.usetex"] = use_latex
    fig, ax = plt.subplots()
    ax.xaxis.set_minor_locator(AutoMinorLocator())
    ax.yaxis.set_minor_locator(AutoMinorLocator())
    ax.tick_params(which="major", top=True, right=True, direction="in", **_MAJOR_TICK)
    ax.tick_params(which="minor", top=True, right=True, direction="in", **_MINOR_TICK)
    return fig, ax


@contextmanager
def rc_override(**overrides):
    """Temporarily overrides `plt.rcParams` on top of whatever's already active, for
    every figure created *and saved* inside the `with` block -- then restores exactly
    the previous values (not `RC_PARAMS` unconditionally, so nesting/repeated use
    stays correct). A no-op with no `overrides` given.

    Exists because text (axis labels, ticks, legends) draws lazily at `show()`/
    `savefig()` time (`new_axes`'s own docstring), so a caller that wants a one-off
    style tweak -- e.g. a larger font for one particular analysis' figures -- must
    keep the override active through the actual `savefig()` call, not just figure
    creation; this is the same "override before creation, restore after" pattern the
    module docstring already recommends for a raw multi-panel `plt.subplots(...)`
    figure, formalized so every caller doesn't hand-roll its own save/restore
    bookkeeping (and risk restoring too early, before the real render).
    """
    previous = {k: plt.rcParams[k] for k in overrides}
    plt.rcParams.update(overrides)
    try:
        yield
    finally:
        plt.rcParams.update(previous)


def save_centered(fig, ax, out_path, pad_inches=0.15):
    """Save `fig` with `ax`'s own box (the actual plot area -- spines,
    ticks, data -- "the graph") exactly horizontally AND vertically
    centered on the saved canvas, instead of matplotlib's
    `bbox_inches="tight"` (asymmetric whenever labels are, e.g. a
    y-axis label only on the left with nothing to match it on the
    right).

    Measures how far the figure's actual rendered content (`ax`'s own
    labels/ticks, any secondary axis, everything `fig.get_tightbbox`
    reports) extends beyond `ax`'s own box on each side, then sets
    `fig.subplots_adjust` margins from the LARGER requirement of each
    opposing pair (left vs. right, bottom vs. top) plus `pad_inches` --
    so the side that needs less content space gets extra background
    whitespace instead, keeping the graph itself centered.
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    tight_bbox = fig.get_tightbbox(renderer)
    width_in, height_in = fig.get_size_inches()
    pos = ax.get_position()
    axes_left_in, axes_right_in = pos.x0 * width_in, pos.x1 * width_in
    axes_bottom_in, axes_top_in = pos.y0 * height_in, pos.y1 * height_in

    needed_left = axes_left_in - tight_bbox.x0
    needed_right = tight_bbox.x1 - axes_right_in
    needed_bottom = axes_bottom_in - tight_bbox.y0
    needed_top = tight_bbox.y1 - axes_top_in

    margin_x = max(needed_left, needed_right, 0.0) + pad_inches
    margin_y = max(needed_bottom, needed_top, 0.0) + pad_inches
    fig.subplots_adjust(left=margin_x / width_in, right=1 - margin_x / width_in,
                         bottom=margin_y / height_in, top=1 - margin_y / height_in)
    fig.savefig(out_path)
