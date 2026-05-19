#!/usr/bin/env python3
"""
spectro_studio.py — Audio → spectrogram → STL pipeline. PySide6, v16.

Self-contained single-file tool with code-IDE inspired UI:
    - Monospace throughout (JetBrains Mono if available, falls back gracefully)
    - Drag-and-drop audio onto the file slot or anywhere on the window
    - Auto-compute on parameter change (debounced)
    - 2D/3D preview toggle

Pipeline:
    audio file → STFT → log/linear-frequency heightmap → contrast curve
              → downsampled mesh grid → watertight closed solid → binary STL

Install:
    pip install numpy soundfile pillow PySide6 pyqtgraph PyOpenGL

(pyqtgraph + PyOpenGL provide the 3D preview. 2D works without them.
pyqtgraph auto-detects PySide6 as the Qt binding when no PyQt is installed.)
"""

import json
import os
import struct
import sys
import traceback
from pathlib import Path

import numpy as np
import soundfile as sf

from PIL import Image
Image.MAX_IMAGE_PIXELS = None

from PySide6.QtCore import Qt, QTimer, QThread, Signal, QMimeData
from PySide6.QtGui import (
    QImage, QPixmap, QIntValidator, QDoubleValidator, QFont, QFontDatabase,
    QDragEnterEvent, QDropEvent, QPainter, QColor, QPen,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QComboBox,
    QLineEdit, QSlider, QCheckBox, QHBoxLayout, QVBoxLayout, QGridLayout,
    QFileDialog, QMessageBox, QSizePolicy, QToolTip,
    QStackedWidget, QButtonGroup, QDialog, QScrollArea, QTextBrowser,
    QInputDialog,
)

try:
    import pyqtgraph.opengl as gl
    HAVE_PYQTGRAPH = True
except Exception:
    HAVE_PYQTGRAPH = False


# ============================================================================
# AUDIO EXTENSIONS (used in multiple places)
# ============================================================================

AUDIO_EXTS = {'.wav', '.flac', '.ogg', '.oga', '.aiff', '.aif'}


# ============================================================================
# COLORMAPS
# ============================================================================

COLORMAPS = {
    'grayscale': [[0,0,0],[32,32,32],[64,64,64],[96,96,96],[128,128,128],[160,160,160],[192,192,192],[224,224,224],[255,255,255]],
    'magma':     [[0,0,4],[28,16,68],[79,18,123],[129,37,129],[181,54,122],[229,80,100],[251,135,97],[254,194,135],[252,253,191]],
    'inferno':   [[0,0,4],[31,12,72],[85,15,109],[136,34,106],[186,54,85],[227,89,51],[249,140,10],[249,201,50],[252,255,164]],
    'viridis':   [[68,1,84],[71,44,122],[59,81,139],[44,113,142],[33,144,141],[39,173,129],[92,200,99],[170,220,50],[253,231,37]],
    'plasma':    [[13,8,135],[75,3,161],[125,3,168],[168,34,150],[203,70,121],[229,107,93],[248,148,65],[253,195,40],[240,249,33]],
    'cividis':   [[0,32,77],[0,49,108],[42,68,118],[80,86,121],[114,105,123],[148,125,121],[184,148,113],[222,173,98],[253,231,55]],
    'phosphor':  [[0,0,0],[24,8,0],[60,20,0],[100,38,4],[148,64,8],[196,98,16],[228,140,32],[248,188,72],[255,232,160]],
}

# Display name → internal key. Internal keys stay lowercase (they're file-
# name-safe and match matplotlib's convention); display names are presented
# in the UI dropdown only.
COLORMAP_DISPLAY = {
    'Grayscale': 'grayscale',
    'Magma':     'magma',
    'Inferno':   'inferno',
    'Viridis':   'viridis',
    'Plasma':    'plasma',
    'Cividis':   'cividis',
    'Phosphor':  'phosphor',
}
COLORMAP_DISPLAY_INV = {v: k for k, v in COLORMAP_DISPLAY.items()}

# Window name display → internal key. make_window() expects the internal
# lowercase form; the UI shows capitalized names.
WINDOW_DISPLAY = {
    'Hann':            'hann',
    'Hamming':         'hamming',
    'Blackman':        'blackman',
    'Blackman-Harris': 'blackmanharris',
    'Rect':            'rect',
}

# Frequency scale: same pattern.
SCALE_DISPLAY = {'Log': 'log', 'Linear': 'linear'}


def build_lut(name, size=256):
    stops = np.array(COLORMAPS.get(name, COLORMAPS['grayscale']), dtype=np.float32)
    n_segs = len(stops) - 1
    t = np.linspace(0, n_segs, size)
    idx = np.clip(np.floor(t).astype(int), 0, n_segs - 1)
    frac = (t - idx)[:, None]
    return (stops[idx] + (stops[idx + 1] - stops[idx]) * frac).astype(np.uint8)


# ============================================================================
# PRESETS
# ============================================================================
# User-saved parameter snapshots. Stored as JSON in the user's home dir so
# the file is invisible-by-default but recoverable if needed. The file is
# created on first save; the app degrades gracefully if it doesn't exist,
# is corrupt, or isn't writable (presets just don't persist between runs).
#
# Schema:
#   {"version": 1, "presets": [{"name": "Voice", "params": {...}}, ...]}
#
# `params` mirrors the output of SpectroStudio._collect_params(). It's
# treated as an opaque blob from the storage layer's perspective — the
# preset loader is responsible for understanding and applying it.

PRESETS_PATH = Path.home() / '.spectro_studio_presets.json'
PRESETS_SCHEMA_VERSION = 1
PRESETS_MAX_COUNT = 20  # user requested >=10; cap at 20 to keep dropdown sane


def load_presets():
    """Read presets from disk. Returns a list of dicts. On any error
    (missing file, bad JSON, wrong schema) returns the built-in defaults
    rather than failing — presets are convenience, not data the user can't
    afford to lose."""
    if not PRESETS_PATH.exists():
        return _factory_presets()
    try:
        with open(PRESETS_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _factory_presets()
        if data.get('version') != PRESETS_SCHEMA_VERSION:
            # Future: handle migrations here. For v1, just fall back to
            # factory rather than risk applying mismatched data.
            return _factory_presets()
        presets = data.get('presets', [])
        if not isinstance(presets, list):
            return _factory_presets()
        # Filter out malformed entries — accept anything with a name and
        # a params dict, ignore extras.
        clean = []
        for p in presets:
            if (isinstance(p, dict)
                    and isinstance(p.get('name'), str)
                    and isinstance(p.get('params'), dict)):
                clean.append({'name': p['name'], 'params': p['params']})
        return clean
    except (OSError, json.JSONDecodeError, ValueError):
        return _factory_presets()


def save_presets(presets):
    """Write the preset list to disk. Returns True on success, False on
    failure. Caller can ignore the return value — failure is non-fatal."""
    try:
        with open(PRESETS_PATH, 'w', encoding='utf-8') as f:
            json.dump({
                'version': PRESETS_SCHEMA_VERSION,
                'presets': presets,
            }, f, indent=2)
        return True
    except OSError:
        return False


def _factory_presets():
    """A handful of starting presets demonstrating different aesthetics.
    These ship with the app so a first-time user has something to click.
    Parameter values are picked to give visibly different results on the
    same audio — voice content, sustained tones, transients, ambient."""
    return [
        {
            'name': 'Voice',
            'params': {
                'fft_size': 4096, 'hop_div': 8, 'window_display': 'Hann',
                'scale_display': 'Log', 'f_min': 80, 'f_max': 8000, 'db_range': 80,
                'colormap_display': 'Phosphor',
                'gamma': 1.5, 'floor': 0.3, 'ceiling': 1.0, 'invert': False,
                'form': 'flat',
                'width_mm': 200.0, 'depth_mm': 80.0, 'auto_depth': True,
                'outer_r_mm': 50.0, 'ring_w_mm': 30.0,
                'max_height_mm': 25.4, 'base_mm': 2.0, 'mesh_res': 2000,
            },
        },
        {
            'name': 'Music',
            'params': {
                'fft_size': 16384, 'hop_div': 16, 'window_display': 'Hann',
                'scale_display': 'Log', 'f_min': 20, 'f_max': 22050, 'db_range': 80,
                'colormap_display': 'Magma',
                'gamma': 1.5, 'floor': 0.3, 'ceiling': 1.0, 'invert': False,
                'form': 'flat',
                'width_mm': 200.0, 'depth_mm': 120.0, 'auto_depth': True,
                'outer_r_mm': 50.0, 'ring_w_mm': 30.0,
                'max_height_mm': 25.4, 'base_mm': 2.0, 'mesh_res': 2000,
            },
        },
        {
            'name': 'Nature',
            'params': {
                'fft_size': 8192, 'hop_div': 8, 'window_display': 'Blackman',
                'scale_display': 'Log', 'f_min': 20, 'f_max': 16000, 'db_range': 100,
                'colormap_display': 'Viridis',
                'gamma': 1.2, 'floor': 0.2, 'ceiling': 0.95, 'invert': False,
                'form': 'flat',
                'width_mm': 200.0, 'depth_mm': 100.0, 'auto_depth': True,
                'outer_r_mm': 50.0, 'ring_w_mm': 30.0,
                'max_height_mm': 20.0, 'base_mm': 2.0, 'mesh_res': 2000,
            },
        },
        {
            'name': 'Drone',
            'params': {
                'fft_size': 16384, 'hop_div': 16,
                'window_display': 'Blackman-Harris',
                'scale_display': 'Log', 'f_min': 20, 'f_max': 8000, 'db_range': 90,
                'colormap_display': 'Plasma',
                'gamma': 1.8, 'floor': 0.35, 'ceiling': 1.0, 'invert': False,
                'form': 'ring',
                'width_mm': 200.0, 'depth_mm': 50.0, 'auto_depth': True,
                'outer_r_mm': 60.0, 'ring_w_mm': 25.0,
                'max_height_mm': 25.4, 'base_mm': 2.0, 'mesh_res': 2000,
            },
        },
        {
            'name': 'Percussion',
            'params': {
                'fft_size': 1024, 'hop_div': 4, 'window_display': 'Rect',
                'scale_display': 'Linear', 'f_min': 20, 'f_max': 22050, 'db_range': 60,
                'colormap_display': 'Inferno',
                'gamma': 2.0, 'floor': 0.4, 'ceiling': 1.0, 'invert': False,
                'form': 'flat',
                'width_mm': 200.0, 'depth_mm': 100.0, 'auto_depth': True,
                'outer_r_mm': 50.0, 'ring_w_mm': 30.0,
                'max_height_mm': 25.4, 'base_mm': 2.0, 'mesh_res': 2000,
            },
        },
    ]


# ============================================================================
# STFT / HEIGHTMAP / CONTRAST / DOWNSAMPLE
# (unchanged from v3 — these are the load-bearing numerical functions)
# ============================================================================

def make_window(kind, n):
    i = np.arange(n)
    if kind == 'rect':
        return np.ones(n, dtype=np.float32)
    if kind == 'hamming':
        return (0.54 - 0.46 * np.cos(2 * np.pi * i / (n - 1))).astype(np.float32)
    if kind == 'blackman':
        a = 2 * np.pi * i / (n - 1)
        return (0.42 - 0.5 * np.cos(a) + 0.08 * np.cos(2 * a)).astype(np.float32)
    if kind == 'blackmanharris':
        a = 2 * np.pi * i / (n - 1)
        return (0.35875 - 0.48829 * np.cos(a) + 0.14128 * np.cos(2 * a)
                - 0.01168 * np.cos(3 * a)).astype(np.float32)
    return (0.5 * (1 - np.cos(2 * np.pi * i / (n - 1)))).astype(np.float32)


def stft(samples, n_fft, hop, window):
    if len(samples) < n_fft:
        samples = np.concatenate(
            [samples, np.zeros(n_fft - len(samples), dtype=samples.dtype)])
    num_frames = max(1, (len(samples) - n_fft) // hop + 1)
    from numpy.lib.stride_tricks import as_strided
    s = samples.strides[0]
    framed = as_strided(samples, shape=(num_frames, n_fft), strides=(s * hop, s))
    spec = np.fft.rfft(framed * window, axis=1)
    return np.abs(spec).astype(np.float32)


def stft_to_heightmap(spec, sr, height, fmin=20.0, fmax=None, scale='log',
                      db_range=80.0):
    num_frames, num_bins = spec.shape
    bin_hz = sr / (2 * (num_bins - 1))
    if fmax is None:
        fmax = sr / 2
    fmin = max(1.0, fmin)
    fmax = min(sr / 2, max(fmin + 1, fmax))

    edges = 1.0 - np.arange(height + 1) / height
    if scale == 'log':
        freqs = np.exp(np.log(fmin) + (np.log(fmax) - np.log(fmin)) * edges)
    else:
        freqs = fmin + (fmax - fmin) * edges
    bin_edges = freqs / bin_hz
    bin_lo = np.clip(np.floor(np.minimum(bin_edges[:-1], bin_edges[1:])).astype(int),
                     0, num_bins - 1)
    bin_hi = np.clip(np.ceil(np.maximum(bin_edges[:-1], bin_edges[1:])).astype(int),
                     0, num_bins - 1)

    out = np.empty((height, num_frames), dtype=np.float32)
    for y in range(height):
        b0, b1 = bin_lo[y], bin_hi[y]
        if b1 < b0:
            b1 = b0
        out[y] = spec[:, b0:b1 + 1].max(axis=1)

    ref = float(out.max()) if out.size else 1e-12
    if ref <= 0:
        ref = 1e-12
    db = 20.0 * (np.log10(np.maximum(out, 1e-12)) - np.log10(ref))
    db = np.clip(db, -db_range, 0)
    return ((db + db_range) / db_range).astype(np.float32)


def apply_curve(heights, gamma=1.0, floor=0.0, ceiling=1.0, invert=False):
    h = heights.astype(np.float32, copy=True)
    if floor < 0 or ceiling > 1 or floor >= ceiling:
        raise ValueError(f"need 0 ≤ floor ({floor}) < ceiling ({ceiling}) ≤ 1")
    if floor > 0 or ceiling < 1:
        h = np.clip(h, floor, ceiling)
        h = (h - floor) / (ceiling - floor)
    h = np.clip(h, 0, 1)
    if gamma != 1.0:
        h = h ** gamma
    if invert:
        h = 1.0 - h
    return h


def downsample(heights, target_w):
    H, W = heights.shape
    if target_w >= W:
        return heights
    factor = max(1, W // target_w)
    new_W = (W // factor) * factor
    new_H = (H // factor) * factor
    h = heights[:new_H, :new_W]
    h = h.reshape(new_H // factor, factor, new_W // factor, factor)
    return h.max(axis=(1, 3))


# ============================================================================
# MESH CONSTRUCTION
# ============================================================================

def build_mesh(heights, x_mm, y_mm, z_mm, base_mm):
    H, W = heights.shape
    xs = np.linspace(0, x_mm, W, dtype=np.float32)
    ys = np.linspace(0, y_mm, H, dtype=np.float32)
    X, Y = np.meshgrid(xs, ys)
    Z = (heights * z_mm + base_mm).astype(np.float32)

    v00 = np.stack([X[:-1, :-1], Y[:-1, :-1], Z[:-1, :-1]], axis=-1)
    v01 = np.stack([X[:-1, 1:],  Y[:-1, 1:],  Z[:-1, 1:]],  axis=-1)
    v10 = np.stack([X[1:, :-1],  Y[1:, :-1],  Z[1:, :-1]],  axis=-1)
    v11 = np.stack([X[1:, 1:],   Y[1:, 1:],   Z[1:, 1:]],   axis=-1)
    top_t1 = np.stack([v00, v01, v11], axis=-2).reshape(-1, 3, 3)
    top_t2 = np.stack([v00, v11, v10], axis=-2).reshape(-1, 3, 3)

    def strip(top_pts, flip):
        bot = top_pts.copy()
        bot[:, 2] = 0
        if not flip:
            t1 = np.stack([top_pts[:-1], bot[:-1],     bot[1:]],     axis=1)
            t2 = np.stack([top_pts[:-1], bot[1:],      top_pts[1:]], axis=1)
        else:
            t1 = np.stack([top_pts[:-1], bot[1:],      bot[:-1]],    axis=1)
            t2 = np.stack([top_pts[:-1], top_pts[1:],  bot[1:]],     axis=1)
        return np.concatenate([t1, t2], axis=0)

    front = np.stack([X[0,  :], Y[0,  :], Z[0,  :]], axis=-1)
    back  = np.stack([X[-1, :], Y[-1, :], Z[-1, :]], axis=-1)
    left  = np.stack([X[:,  0], Y[:,  0], Z[:,  0]], axis=-1)
    right = np.stack([X[:, -1], Y[:, -1], Z[:, -1]], axis=-1)
    front_tris = strip(front, flip=False)
    back_tris  = strip(back,  flip=True)
    left_tris  = strip(left,  flip=True)
    right_tris = strip(right, flip=False)

    perim = []
    perim.extend((X[0, j], Y[0, j], 0.0) for j in range(W))
    perim.extend((X[i, W-1], Y[i, W-1], 0.0) for i in range(1, H))
    perim.extend((X[H-1, j], Y[H-1, j], 0.0) for j in range(W-2, -1, -1))
    perim.extend((X[i, 0], Y[i, 0], 0.0) for i in range(H-2, 0, -1))
    perim = np.array(perim, dtype=np.float32)
    n_p = len(perim)
    center = np.array([x_mm * 0.5, y_mm * 0.5, 0.0], dtype=np.float32)
    next_perim = np.roll(perim, -1, axis=0)
    bottom_tris = np.stack([
        np.broadcast_to(center, (n_p, 3)),
        next_perim, perim,
    ], axis=1).astype(np.float32)
    e1 = bottom_tris[0, 1] - bottom_tris[0, 0]
    e2 = bottom_tris[0, 2] - bottom_tris[0, 0]
    if np.cross(e1, e2)[2] > 0:
        bottom_tris = bottom_tris[:, ::-1, :].copy()

    return np.concatenate(
        [top_t1, top_t2, front_tris, back_tris, left_tris, right_tris, bottom_tris],
        axis=0)


def build_ring_mesh(heights, outer_radius_mm, ring_width_mm, z_mm, base_mm):
    H, W = heights.shape
    inner_radius = outer_radius_mm - ring_width_mm
    if inner_radius <= 0:
        raise ValueError(
            f'ring width ({ring_width_mm} mm) must be smaller than '
            f'outer radius ({outer_radius_mm} mm)')

    thetas = np.linspace(0, 2 * np.pi, W, endpoint=False, dtype=np.float32)
    radii = np.linspace(outer_radius_mm, inner_radius, H, dtype=np.float32)
    cos_t = np.cos(thetas)
    sin_t = np.sin(thetas)
    R = radii[:, None]
    X = (R * cos_t[None, :]).astype(np.float32)
    Y = (R * sin_t[None, :]).astype(np.float32)
    Z = (heights * z_mm + base_mm).astype(np.float32)
    V = np.stack([X, Y, Z], axis=-1)
    V_next = np.roll(V, -1, axis=1)

    v00 = V[:-1, :, :]
    v01 = V_next[:-1, :, :]
    v10 = V[1:, :, :]
    v11 = V_next[1:, :, :]
    top_t1 = np.stack([v00, v01, v11], axis=-2).reshape(-1, 3, 3)
    top_t2 = np.stack([v00, v11, v10], axis=-2).reshape(-1, 3, 3)

    outer_top = V[0, :, :]
    outer_bot = outer_top.copy(); outer_bot[:, 2] = 0
    outer_top_n = np.roll(outer_top, -1, axis=0)
    outer_bot_n = np.roll(outer_bot, -1, axis=0)
    outer_t1 = np.stack([outer_top, outer_bot,   outer_bot_n], axis=1)
    outer_t2 = np.stack([outer_top, outer_bot_n, outer_top_n], axis=1)

    inner_top = V[-1, :, :]
    inner_bot = inner_top.copy(); inner_bot[:, 2] = 0
    inner_top_n = np.roll(inner_top, -1, axis=0)
    inner_bot_n = np.roll(inner_bot, -1, axis=0)
    inner_t1 = np.stack([inner_top, inner_bot_n, inner_bot],   axis=1)
    inner_t2 = np.stack([inner_top, inner_top_n, inner_bot_n], axis=1)

    bot_t1 = np.stack([outer_bot, inner_bot,   outer_bot_n], axis=1)
    bot_t2 = np.stack([inner_bot, inner_bot_n, outer_bot_n], axis=1)

    return np.concatenate([
        top_t1, top_t2,
        outer_t1.reshape(-1, 3, 3), outer_t2.reshape(-1, 3, 3),
        inner_t1.reshape(-1, 3, 3), inner_t2.reshape(-1, 3, 3),
        bot_t1.reshape(-1, 3, 3),   bot_t2.reshape(-1, 3, 3),
    ], axis=0).astype(np.float32)


def write_binary_stl(triangles, path):
    n = len(triangles)
    e1 = triangles[:, 1] - triangles[:, 0]
    e2 = triangles[:, 2] - triangles[:, 0]
    normals = np.cross(e1, e2)
    norms = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = (normals / np.maximum(norms, 1e-12)).astype(np.float32)

    dtype = np.dtype([
        ('normal', '<f4', 3), ('v0', '<f4', 3),
        ('v1', '<f4', 3),     ('v2', '<f4', 3),
        ('attr', '<u2'),
    ])
    rec = np.zeros(n, dtype=dtype)
    rec['normal'] = normals
    rec['v0'] = triangles[:, 0]
    rec['v1'] = triangles[:, 1]
    rec['v2'] = triangles[:, 2]

    with open(path, 'wb') as f:
        f.write((b'spectro_studio ' + b' ' * 80)[:80])
        f.write(struct.pack('<I', n))
        f.write(rec.tobytes())


# ============================================================================
# DESIGN TOKENS
# ============================================================================

# Refined dark palette: low contrast surfaces, single accent.
# Slightly cooler bg than v3, slightly warmer accent — feels less plasticky.
T = {
    'bg':         '#0e0f12',   # window background (near-black, faint blue)
    'surface':    '#16181c',   # entry / combo fields
    'surface_hi': '#1d2026',   # hover
    'border':     '#2a2d34',   # hairline rules and edit boundaries
    'border_lo':  '#1a1c20',   # subtler rules
    'text':       '#d6d9df',   # primary
    'text_dim':   '#7a7f88',   # labels, section headers
    'text_dis':   '#3f434b',   # disabled
    'accent':     '#f7a35c',   # warm amber — replaced by COLORMAP_ACCENTS below
    'accent_dim': '#7a4f29',   # accent rolled off for resting states
    'canvas':     '#070809',   # preview backgrounds (deeper than bg)
    'good':       '#7fb069',
    'warn':       '#e0c068',
}

# Per-colormap UI accent colors. The accent flows through section headers,
# the export button, slider hover, checkbox fills, and the busy spinner.
# Each entry is (accent, accent_dim) — accent_dim is the deeper/desaturated
# variant used for resting states.
#
# Picked from each colormap's mid-bright region (roughly the 70-80% point
# of the gradient) — this is where the most-saturated, most-characteristic
# color usually lives. The bright tip is often too pale to read as a UI
# accent against dark surfaces; the cold end is too muted.
#
# Grayscale uses a bright off-white as its accent — no chroma to draw from
# the map, so we pick the brightest tone that still reads as a UI element
# rather than just text.
COLORMAP_ACCENTS = {
    # (accent, accent_dim). accent_dim is a desaturated/darker variant used
    # for the slider's filled track (a secondary accent role). Hand-picked
    # from each map's most chromatic mid stop, balanced for legibility on
    # the dark surface.
    #
    # Grayscale: bright off-white against the dark surface. Pure white feels
    # harsh; this softer near-white reads as a deliberate accent without
    # being chromatically loud. The dim variant is a mid-gray for slider
    # tracks.
    'grayscale': ('#d8d8d8', '#5a5a5a'),
    'magma':     ('#e55064', '#73282f'),   # stop-5 pink-coral
    'inferno':   ('#e35933', '#732a19'),   # stop-5 deep orange
    'viridis':   ('#27ad81', '#155440'),   # stop-5 teal-green
    'plasma':    ('#e56b5d', '#732e26'),   # stop-5 coral
    'cividis':   ('#dead62', '#6d5530'),   # stop-7 warm gold
    'phosphor':  ('#e48c20', '#73450f'),   # stop-6 CRT orange
}


def apply_theme_accent(cmap_internal_name):
    """Update the module-level theme dict's accent colors based on the
    currently selected colormap. Caller is responsible for re-applying the
    QSS stylesheet to widgets after this returns (since QSS isn't
    automatically re-evaluated when T changes)."""
    accent, accent_dim = COLORMAP_ACCENTS.get(
        cmap_internal_name, COLORMAP_ACCENTS['grayscale'])
    T['accent'] = accent
    T['accent_dim'] = accent_dim


def _lighten(hex_color, amount=0.25):
    """Return a hex color that is `amount` of the way toward white from the
    input. Used for hover-state derivations from the accent. Tiny pure-
    Python helper — saves importing a color library for one operation."""
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    lr = int(round(r + (255 - r) * amount))
    lg = int(round(g + (255 - g) * amount))
    lb = int(round(b + (255 - b) * amount))
    return f'#{lr:02x}{lg:02x}{lb:02x}'


def pick_mono_font():
    """Resolve the best monospace font available.

    Order of preference (in priority): JetBrains Mono, IBM Plex Mono, Fira Code,
    SF Mono, Menlo, Consolas, Monaco. The first installed one wins; Menlo is
    guaranteed on macOS, Consolas on Windows, so the chain always resolves.
    """
    # In Qt6 (PySide6), QFontDatabase methods are static.
    available = set(QFontDatabase.families())
    preferred = [
        'JetBrains Mono',
        'IBM Plex Mono',
        'Fira Code',
        'SF Mono',
        'Menlo',          # macOS default mono — always present on Mac
        'Consolas',       # Windows
        'DejaVu Sans Mono',  # Linux
        'Monaco',
    ]
    for name in preferred:
        if name in available:
            return name
    return 'monospace'


def make_qss(mono_family):
    """Build the global stylesheet. Mono family resolved once at startup."""
    return f"""
* {{
    font-family: '{mono_family}', monospace;
    font-size: 11px;
    letter-spacing: 0.2px;
}}

QMainWindow, QWidget {{
    background-color: {T['bg']};
    color: {T['text']};
}}

QLabel {{ background-color: transparent; color: {T['text']}; }}
QLabel:disabled {{ color: {T['text_dis']}; }}

/* No groupbox chrome — section headers handled by SectionLabel */
QGroupBox {{ border: none; margin: 0; padding: 0; }}

QPushButton {{
    background-color: transparent;
    color: {T['text']};
    border: 1px solid {T['border']};
    border-radius: 1px;
    padding: 5px 12px;
}}
QPushButton:hover {{
    background-color: {T['surface_hi']};
    border-color: {T['text_dim']};
}}
QPushButton:pressed {{
    background-color: {T['bg']};
}}
QPushButton:disabled {{
    color: {T['text_dis']};
    border-color: {T['border_lo']};
}}
QPushButton:checked {{
    background-color: transparent;
    color: {T['accent']};
    border-color: {T['accent']};
}}
QPushButton#primary {{
    background-color: {T['accent']};
    color: {T['bg']};
    border-color: {T['accent']};
}}
QPushButton#primary:hover {{
    /* Slight lift over the accent — derived from accent so it tracks
       the colormap. Adds ~25% white to brighten on hover. */
    background-color: {_lighten(T['accent'], 0.25)};
    border-color: {_lighten(T['accent'], 0.25)};
}}
QPushButton#primary:disabled {{
    background-color: transparent;
    color: {T['text_dis']};
    border-color: {T['border_lo']};
}}

QLineEdit {{
    background-color: {T['surface']};
    color: {T['text']};
    border: 1px solid {T['border']};
    border-radius: 1px;
    padding: 3px 6px;
    /* Min-height matches ROW_MIN_HEIGHT — see comment there for why. */
    min-height: 22px;
    selection-background-color: {T['accent']};
    selection-color: {T['bg']};
}}
QLineEdit:focus {{ border-color: {T['accent']}; }}
QLineEdit:read-only {{ color: {T['text_dim']}; background-color: {T['border_lo']}; }}
QLineEdit:disabled {{ color: {T['text_dis']}; }}

QComboBox {{
    background-color: {T['surface']};
    color: {T['text']};
    border: 1px solid {T['border']};
    border-radius: 1px;
    padding: 3px 6px;
    min-height: 22px;
}}
QComboBox:focus {{ border-color: {T['accent']}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox::down-arrow {{
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {T['text_dim']};
}}
QComboBox QAbstractItemView {{
    background-color: {T['surface']};
    color: {T['text']};
    border: 1px solid {T['border']};
    selection-background-color: {T['accent']};
    selection-color: {T['bg']};
    outline: none;
    padding: 2px;
}}

QCheckBox {{ background-color: transparent; color: {T['text']}; spacing: 8px; }}
QCheckBox:disabled {{ color: {T['text_dis']}; }}
QCheckBox::indicator {{
    width: 12px; height: 12px;
    background-color: {T['surface']};
    border: 1px solid {T['border']};
    border-radius: 1px;
}}
QCheckBox::indicator:checked {{
    background-color: {T['accent']};
    border-color: {T['accent']};
}}

QSlider::groove:horizontal {{
    border: none;
    height: 1px;
    background: {T['border']};
}}
QSlider::handle:horizontal {{
    background: {T['text']};
    border: none;
    width: 2px; height: 12px;
    margin: -6px 0;
    border-radius: 0;
}}
QSlider::handle:horizontal:hover {{ background: {T['accent']}; }}
QSlider::handle:horizontal:disabled {{ background: {T['text_dis']}; }}
QSlider::sub-page:horizontal {{ background: {T['text_dim']}; }}
QSlider::sub-page:horizontal:disabled {{ background: {T['border']}; }}

/* Scrollbars — dark, minimal, matching the rest of the UI. Applied
   globally so the sidebar scroll area and the manual dialog scroll bar
   look consistent. */
QScrollBar:vertical {{
    background: {T['bg']};
    width: 10px;
    margin: 0;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {T['border']};
    min-height: 30px;
    border-radius: 0;
}}
QScrollBar::handle:vertical:hover {{
    background: {T['text_dim']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
    background: none;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: {T['bg']};
}}

QToolTip {{
    background-color: {T['surface_hi']};
    color: {T['text']};
    border: 1px solid {T['border']};
    padding: 6px 10px;
}}
"""


# ============================================================================
# LAYOUT CONSTANTS
# ============================================================================

PAD = 10
PARAMS_WIDTH = 420   # bumped from 380 to leave room for the scrollbar (~14px)
                     # without losing space for the controls themselves
PREVIEW_W = 720
PREVIEW_H = 500
HEIGHTMAP_RES_H = 1024
SLIDER_STEPS = 10000
ROW_MIN_HEIGHT = 28  # minimum height of one parameter row's widgets, in px.
                     # Sized so that 13px mono font + 3px vertical padding +
                     # 1px borders all fit without text clipping. 24px was
                     # too tight — text rendered fine in some Qt builds but
                     # got vertically clipped in others.

SPEC_DEBOUNCE_MS = 350
CONTRAST_DEBOUNCE_MS = 40
PREVIEW_3D_DEBOUNCE_MS = 250
PREVIEW_3D_MAX_RES = 400


# ============================================================================
# WORKER THREADS — unchanged from v3
# ============================================================================

class ComputeWorker(QThread):
    status = Signal(str)
    finished_ok = Signal(object, object, int, float)
    failed = Signal(str)

    def __init__(self, audio_path, n_fft, hop_div, window, scale,
                 fmin, fmax, db_range):
        super().__init__()
        self.audio_path = audio_path
        self.n_fft = n_fft; self.hop_div = hop_div
        self.window = window; self.scale = scale
        self.fmin = fmin; self.fmax = fmax; self.db_range = db_range
        self._abort = False

    def abort(self):
        self._abort = True

    def run(self):
        try:
            self.status.emit('loading audio…')
            data, sr = sf.read(self.audio_path, dtype='float32', always_2d=False)
            if self._abort: return
            if data.ndim > 1:
                data = data.mean(axis=1).astype(np.float32)
            duration = len(data) / sr

            hop = max(1, self.n_fft // self.hop_div)
            win = make_window(self.window, self.n_fft)

            self.status.emit(f'stft · n_fft={self.n_fft} · hop={hop}')
            spec = stft(data, self.n_fft, hop, win)
            if self._abort: return

            self.status.emit('building heightmap…')
            heightmap = stft_to_heightmap(
                spec, sr, height=HEIGHTMAP_RES_H,
                fmin=self.fmin, fmax=self.fmax,
                scale=self.scale, db_range=self.db_range)
            if self._abort: return
            self.finished_ok.emit(spec, heightmap, sr, duration)
        except Exception as e:
            traceback.print_exc()
            self.failed.emit(str(e))


class StlWorker(QThread):
    status = Signal(str)
    finished_ok = Signal(str, int, str)
    failed = Signal(str)

    def __init__(self, heightmap, params, out_path):
        super().__init__()
        self.heightmap = heightmap; self.params = params
        self.out_path = out_path

    def run(self):
        try:
            p = self.params
            curved = apply_curve(self.heightmap, gamma=p['gamma'],
                                 floor=p['floor'], ceiling=p['ceiling'],
                                 invert=p['invert'])
            ds = downsample(curved, p['resolution'])
            H, W = ds.shape
            if p['form'] == 'flat':
                ds = ds[::-1, :]
                self.status.emit(f'building flat mesh · {W}×{H}')
                tris = build_mesh(ds, x_mm=p['width_mm'], y_mm=p['depth_mm'],
                                  z_mm=p['max_height_mm'], base_mm=p['base_mm'])
                footprint = f"{p['width_mm']:.0f}×{p['depth_mm']:.1f}mm"
            else:
                self.status.emit(f'building ring mesh · {W}×{H}')
                tris = build_ring_mesh(ds, outer_radius_mm=p['outer_radius'],
                                       ring_width_mm=p['ring_width'],
                                       z_mm=p['max_height_mm'],
                                       base_mm=p['base_mm'])
                inner_r = p['outer_radius'] - p['ring_width']
                footprint = f"⌀{2*p['outer_radius']:.0f}/{2*inner_r:.0f}mm"
            self.status.emit(f'writing stl · {len(tris):,} tris')
            write_binary_stl(tris, self.out_path)
            self.finished_ok.emit(self.out_path, len(tris), footprint)
        except Exception as e:
            traceback.print_exc()
            self.failed.emit(str(e))


class PngWorker(QThread):
    status = Signal(str)
    finished_ok = Signal(str, int, int)
    failed = Signal(str)

    def __init__(self, heightmap, params, lut, canvas_w, canvas_h, out_path):
        super().__init__()
        self.heightmap = heightmap; self.params = params; self.lut = lut
        self.canvas_w = canvas_w; self.canvas_h = canvas_h
        self.out_path = out_path

    def run(self):
        try:
            cw, ch = self.canvas_w, self.canvas_h
            if cw < 50 or ch < 50:
                cw, ch = PREVIEW_W, PREVIEW_H
            target_aspect = cw / ch
            p = self.params
            curved = apply_curve(self.heightmap, gamma=p['gamma'],
                                 floor=p['floor'], ceiling=p['ceiling'],
                                 invert=p['invert'])
            H_hm, W_hm = curved.shape
            aspect_w = int(round(H_hm * target_aspect))
            target_w = max(W_hm, aspect_w)
            target_h = int(round(target_w / target_aspect))
            self.status.emit(f'rendering png · {target_w}×{target_h}')
            img_l = Image.fromarray((curved * 255).astype(np.uint8), mode='L')
            img_l = img_l.resize((target_w, target_h), Image.LANCZOS)
            arr = np.array(img_l)
            rgb = self.lut[arr]
            Image.fromarray(rgb, mode='RGB').save(self.out_path, optimize=False)
            self.finished_ok.emit(self.out_path, target_w, target_h)
        except Exception as e:
            traceback.print_exc()
            self.failed.emit(str(e))


class Preview3DWorker(QThread):
    finished_ok = Signal(object, object, object)
    failed = Signal(str)

    def __init__(self, heightmap, params, lut, preview_res):
        super().__init__()
        self.heightmap = heightmap; self.params = params
        self.lut = lut; self.preview_res = preview_res

    def run(self):
        try:
            p = self.params
            curved = apply_curve(self.heightmap, gamma=p['gamma'],
                                 floor=p['floor'], ceiling=p['ceiling'],
                                 invert=p['invert'])
            res = min(self.preview_res, int(p['resolution']))
            ds = downsample(curved, res)
            if p['form'] == 'flat':
                ds_oriented = ds[::-1, :]
                tris = build_mesh(ds_oriented, x_mm=p['width_mm'],
                                  y_mm=p['depth_mm'],
                                  z_mm=p['max_height_mm'],
                                  base_mm=p['base_mm'])
            else:
                tris = build_ring_mesh(ds, outer_radius_mm=p['outer_radius'],
                                       ring_width_mm=p['ring_width'],
                                       z_mm=p['max_height_mm'],
                                       base_mm=p['base_mm'])
            verts = tris.reshape(-1, 3).astype(np.float32)
            n_tris = len(tris)
            faces = np.arange(n_tris * 3, dtype=np.uint32).reshape(n_tris, 3)

            # ----------------------------------------------------------
            # Per-vertex colors.
            # We color by source heightmap value at the vertex's (x,y) —
            # the same value that drove the height. This means a column
            # of mesh (a tall spike) reads as one color from base to top,
            # matching what the 2D preview shows. The alternative (color
            # by Z) makes every spike fade from cold-base to hot-tip,
            # which doesn't match the 2D and looks topographic rather
            # than spectral.
            #
            # The ds heightmap is the source of truth — note that for the
            # flat form we used ds_oriented (vertical flip) in the mesh,
            # so we sample from ds_oriented to match. For the ring form,
            # ds was used directly with no flip.
            # ----------------------------------------------------------
            ds_for_color = ds_oriented if p['form'] == 'flat' else ds
            H_ds, W_ds = ds_for_color.shape
            vx = verts[:, 0]
            vy = verts[:, 1]
            if p['form'] == 'flat':
                # (x, y) → (col, row) in [0, W-1] × [0, H-1]
                col = np.clip((vx / max(1e-6, p['width_mm'])) * (W_ds - 1),
                              0, W_ds - 1).astype(np.int32)
                row = np.clip((vy / max(1e-6, p['depth_mm'])) * (H_ds - 1),
                              0, H_ds - 1).astype(np.int32)
            else:
                # (x, y) → polar → (col=θ, row=r)
                outer_r = p['outer_radius']
                inner_r = outer_r - p['ring_width']
                r = np.sqrt(vx * vx + vy * vy)
                theta = np.arctan2(vy, vx)
                # theta is in [-π, π); normalize to [0, 1)
                theta_n = (theta / (2 * np.pi)) % 1.0
                col = np.clip(theta_n * W_ds, 0, W_ds - 1).astype(np.int32)
                # r maps row 0 (outer) to outer_r and row H-1 (inner) to inner_r
                # Clamp r to [inner_r, outer_r] for vertices on walls/base
                r_clamped = np.clip(r, inner_r, outer_r)
                if outer_r > inner_r:
                    row_f = (outer_r - r_clamped) / (outer_r - inner_r) * (H_ds - 1)
                else:
                    row_f = np.zeros_like(r_clamped)
                row = np.clip(row_f, 0, H_ds - 1).astype(np.int32)

            sample = ds_for_color[row, col]  # [N_vertices], in [0, 1]
            idx = np.clip(sample * 255, 0, 255).astype(np.uint8)
            rgb = self.lut[idx].astype(np.float32) / 255.0  # (N_verts, 3)

            # ----------------------------------------------------------
            # Bake lighting into vertex colors.
            #
            # pyqtgraph's built-in 'shaded' shader is famously dark — it uses
            # a single light with no ambient term, so any face that isn't
            # roughly facing the camera ends up near-black. Rather than
            # write a custom GLSL shader (fragile across pyqtgraph versions),
            # we compute lighting in numpy here and pass the final colors
            # to a non-shading mode (shader=None).
            #
            # Lighting model: Lambert with strong ambient.
            #   lit = ambient + diffuse * max(0, dot(normal, light_dir))
            #
            # The ambient floor (0.55) is deliberately high — this is a
            # data-visualization preview, not a rendering of a physical
            # object. Readability beats realism. The diffuse term (0.45)
            # still gives shape cues so the 3D form reads, but no surface
            # is darker than ~55% of its base color.
            #
            # Light direction: roughly (-0.5, 0.5, 0.8), pointing down at
            # the mesh from above-and-back-left in world space. The
            # default camera is elevation +30, azimuth -60, so this
            # direction roughly aligns with "over the camera's shoulder".
            # ----------------------------------------------------------
            AMBIENT = 0.55
            DIFFUSE = 0.45
            light_dir = np.array([-0.5, 0.5, 0.8], dtype=np.float32)
            light_dir = light_dir / np.linalg.norm(light_dir)

            # Triangle face normals (flat shading — each vertex of a tri
            # gets the same normal). tris is shape (n_tris, 3, 3).
            e1 = tris[:, 1] - tris[:, 0]
            e2 = tris[:, 2] - tris[:, 0]
            face_normals = np.cross(e1, e2)
            face_norms = np.linalg.norm(face_normals, axis=1, keepdims=True)
            face_normals = face_normals / np.maximum(face_norms, 1e-12)

            # Lambert coefficient per face, then repeat 3× to per-vertex.
            # Use the absolute value of dot product (light from "both sides")
            # so that interior surfaces aren't pitch-black — this is a
            # preview, viewer might orbit underneath. Slight cheat but
            # consistent with the readability-over-realism principle above.
            lambert = np.abs(face_normals @ light_dir)            # (n_tris,)
            lit_coef = AMBIENT + DIFFUSE * lambert                # (n_tris,)
            lit_coef_per_vert = np.repeat(lit_coef, 3)            # (n_verts,)

            rgb = rgb * lit_coef_per_vert[:, None]                # (n_verts, 3)
            rgb = np.clip(rgb, 0, 1)

            # Also lift very-dark colormap stops off black so the bottom
            # end of magma/inferno doesn't disappear into the background.
            # Without this, the deep-purple end of magma sits at ~(0,0,0.02)
            # which renders as black regardless of lighting.
            COLOR_FLOOR = 0.08
            rgb = COLOR_FLOOR + (1.0 - COLOR_FLOOR) * rgb

            colors = np.column_stack([rgb, np.ones(len(rgb), dtype=np.float32)])
            self.finished_ok.emit(verts, faces, colors)
        except Exception as e:
            traceback.print_exc()
            self.failed.emit(str(e))


# ============================================================================
# CUSTOM WIDGETS — design language
# ============================================================================

class SectionLabel(QLabel):
    """Section header — uppercase, bold, amber. Acts as a strong visual
    divider between parameter groups in the sidebar."""

    def __init__(self, text, padding_top=18):
        super().__init__(text.upper())
        # Letter-spacing widens the uppercase text so it doesn't look cramped
        # in mono. Slightly larger size gives it presence over the rows below.
        # padding_top can be overridden (e.g. to 0 for headers that sit at
        # the very top of their column).
        self._padding_top = padding_top
        self.refresh_color()

    def refresh_color(self):
        """Re-read T['accent'] and reapply styling. Called when the colormap
        changes — section labels track the accent color."""
        self.setStyleSheet(
            f"color: {T['accent']}; "
            f"padding: {self._padding_top}px 0 6px 0; "
            f"font-weight: bold; "
            f"font-size: 12px; "
            f"letter-spacing: 1.2px;")


class HRule(QWidget):
    """1px horizontal hairline rule."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(1)
        self.setStyleSheet(f"background-color: {T['border']};")


class BusyOverlay(QWidget):
    """Semi-transparent overlay shown while heavy work is running.

    Sits on top of the preview area as a child widget, sized to match. Paints
    a spinning arc and a status message. While visible, intercepts mouse
    events so the user can't interact with the (stale) preview underneath.

    The animation is driven by a 60ms QTimer that increments a rotation phase;
    paintEvent draws the arc at the current phase. No expensive ops in the
    paint path.

    Usage:
        overlay = BusyOverlay(parent=preview_area)
        overlay.start('Loading audio…')
        # ... later
        overlay.stop()
    """

    # Animation constants — tweaked for "patient but alive" feel
    SPINNER_RADIUS = 18      # pixels
    SPINNER_THICKNESS = 2    # pixels
    SPINNER_ARC_DEGREES = 100  # arc length (full = 360)
    SPINNER_PERIOD_MS = 1200   # full rotation period

    def __init__(self, parent):
        super().__init__(parent)
        self._phase = 0.0
        self._message = ''
        self._timer = QTimer(self)
        self._timer.setInterval(60)  # ~16 fps — enough for smooth rotation,
                                     # cheap on CPU
        self._timer.timeout.connect(self._tick)
        # Initially hidden; manually shown by start()
        self.hide()
        # Cover the entire parent automatically
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)

    def start(self, message=''):
        self._message = message
        # If the parent has been resized since last show, sync size now
        if self.parent():
            self.resize(self.parent().size())
        self.show()
        self.raise_()
        if not self._timer.isActive():
            self._timer.start()

    def stop(self):
        self._timer.stop()
        self.hide()

    def set_message(self, message):
        """Update the in-progress label without restarting the spinner."""
        self._message = message
        self.update()

    def _tick(self):
        self._phase = (self._phase + 60 / self.SPINNER_PERIOD_MS) % 1.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. Semi-transparent dark wash — makes the underlying preview look
        # "stale" while still partially visible.
        wash = QColor(7, 8, 9, 180)  # T['canvas'] + ~70% alpha
        painter.fillRect(self.rect(), wash)

        # 2. Spinner — an arc that rotates. Centered horizontally; offset
        # vertically up a bit so the status text sits below the visual center.
        cx = self.width() // 2
        cy = self.height() // 2 - 16
        r = self.SPINNER_RADIUS

        # Background ring (full circle, very dim — gives the arc a "track")
        pen = QPen(QColor(T['border']))
        pen.setWidth(self.SPINNER_THICKNESS)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(cx - r, cy - r, 2 * r, 2 * r, 0, 360 * 16)

        # Foreground arc in accent — rotates
        pen = QPen(QColor(T['accent']))
        pen.setWidth(self.SPINNER_THICKNESS)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        start_angle = int(-self._phase * 360 * 16)  # negative = clockwise
        span_angle = int(self.SPINNER_ARC_DEGREES * 16)
        painter.drawArc(cx - r, cy - r, 2 * r, 2 * r,
                        start_angle, span_angle)

        # 3. Status message centered below the spinner
        if self._message:
            painter.setPen(QColor(T['text']))
            font = painter.font()
            # Slightly larger than the rest of the UI; this should be readable
            font.setPointSize(11)
            painter.setFont(font)
            text_rect = self.rect().adjusted(0, 16, 0, 0)  # offset down a bit
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter,
                             self._message)

        painter.end()

    def resizeEvent(self, event):
        # When parent resizes, the overlay needs to follow. This is wired up
        # via the parent's resize event in PreviewArea.
        super().resizeEvent(event)

    def mousePressEvent(self, event):
        # Swallow clicks so the underlying preview doesn't try to handle them
        event.accept()


class DropZone(QLabel):
    """Drag-target for audio files. Shows hint text when empty,
    file info when loaded. Always accepts drops; toggles visual state
    while a drag hovers over it."""

    file_dropped = Signal(str)
    browse_requested = Signal()

    HINT = '  Drop audio here  ·  or click to browse'

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setText(self.HINT)
        self.setMinimumHeight(64)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hovered = False
        self._loaded = False
        self._update_style()
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _update_style(self):
        if self._hovered:
            border_color = T['accent']
            text_color = T['accent']
            bg = T['surface']
        elif self._loaded:
            border_color = T['border']
            text_color = T['text']
            bg = T['surface']
        else:
            border_color = T['border']
            text_color = T['text_dim']
            bg = 'transparent'
        # Border with subtle dashes when empty to read as "input slot"
        style = ('dashed' if not self._loaded else 'solid')
        self.setStyleSheet(
            f"DropZone {{"
            f"  background-color: {bg};"
            f"  color: {text_color};"
            f"  border: 1px {style} {border_color};"
            f"  border-radius: 1px;"
            f"  padding: 8px 12px;"
            f"}}")

    def set_loaded(self, info_text):
        self._loaded = True
        self.setText(info_text)
        self._update_style()

    def clear_loaded(self):
        self._loaded = False
        self.setText(self.HINT)
        self._update_style()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if self._mime_has_audio(event.mimeData()):
            event.acceptProposedAction()
            self._hovered = True
            self._update_style()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._hovered = False
        self._update_style()

    def dropEvent(self, event: QDropEvent):
        self._hovered = False
        self._update_style()
        path = self._mime_first_audio(event.mimeData())
        if path:
            event.acceptProposedAction()
            self.file_dropped.emit(path)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.browse_requested.emit()

    @staticmethod
    def _mime_has_audio(mime: QMimeData) -> bool:
        if not mime.hasUrls():
            return False
        for url in mime.urls():
            if url.isLocalFile():
                ext = Path(url.toLocalFile()).suffix.lower()
                if ext in AUDIO_EXTS:
                    return True
        return False

    @staticmethod
    def _mime_first_audio(mime: QMimeData):
        """Return the first audio file path in the drop, or None."""
        if not mime.hasUrls():
            return None
        for url in mime.urls():
            if url.isLocalFile():
                p = url.toLocalFile()
                if Path(p).suffix.lower() in AUDIO_EXTS:
                    return p
        return None


# ============================================================================
# NUMERIC ROW — slider + value, but visually quieter
# ============================================================================

class NumericRow:
    """A label + slider + numeric entry. Layout is tight; entry reads as the
    primary value. Either source updates the shared value; typed values are
    clamped to [lo, hi] on commit."""

    def __init__(self, parent_grid, row, label, lo, hi, value,
                 is_int=False, fmt=None, live=False, tip=None, suffix='',
                 preview_callback=None):
        self.lo = lo
        self.hi = hi
        self.is_int = is_int
        self.fmt = fmt if fmt is not None else ('{:d}' if is_int else '{:.2f}')
        self.live = live
        self.preview_callback = preview_callback
        self.suffix = suffix
        self._value = value
        self._syncing = False
        self._listeners = []

        self.label = QLabel(label)
        self.label.setStyleSheet(f"color: {T['text_dim']};")
        # Set a minimum height on the label too so it doesn't get
        # squeezed when the row is tight on vertical space.
        self.label.setMinimumHeight(ROW_MIN_HEIGHT)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(SLIDER_STEPS)
        self.slider.setValue(self._to_slider(value))
        self.slider.setMinimumWidth(110)
        self.slider.setMinimumHeight(ROW_MIN_HEIGHT)

        self.entry = QLineEdit(self._format(value))
        self.entry.setFixedWidth(74)
        self.entry.setAlignment(Qt.AlignmentFlag.AlignRight)
        # QLineEdit honors fixed-height more robustly than minimum-height —
        # without this, text can clip vertically when the parent layout is
        # tight (the symptom: digits showing only their bottom half).
        self.entry.setFixedHeight(ROW_MIN_HEIGHT)
        if is_int:
            self.entry.setValidator(QIntValidator(int(lo), int(hi)))
        else:
            v = QDoubleValidator(float(lo), float(hi), 4)
            v.setNotation(QDoubleValidator.Notation.StandardNotation)
            self.entry.setValidator(v)

        parent_grid.addWidget(self.label, row, 0)
        parent_grid.addWidget(self.slider, row, 1)
        parent_grid.addWidget(self.entry, row, 2)

        self.slider.valueChanged.connect(self._slider_changed)
        self.entry.editingFinished.connect(self._entry_committed)
        self.entry.returnPressed.connect(self._entry_committed)

        if tip:
            self.label.setToolTip(tip)
            self.slider.setToolTip(tip)
            self.entry.setToolTip(tip)

    def value_changed(self, listener):
        self._listeners.append(listener)

    def _to_slider(self, value):
        if self.hi == self.lo:
            return 0
        frac = (float(value) - self.lo) / (self.hi - self.lo)
        return int(round(max(0.0, min(1.0, frac)) * SLIDER_STEPS))

    def _from_slider(self, s):
        frac = s / SLIDER_STEPS
        val = self.lo + frac * (self.hi - self.lo)
        if self.is_int:
            return int(round(val))
        return val

    def _format(self, v):
        return self.fmt.format(int(round(v)) if self.is_int else float(v))

    def _slider_changed(self, s):
        if self._syncing:
            return
        val = self._from_slider(s)
        self._syncing = True
        self.entry.setText(self._format(val))
        self._syncing = False
        self._value = val
        self._notify()

    def _entry_committed(self):
        if self._syncing:
            return
        text = self.entry.text().strip()
        if not text:
            self.entry.setText(self._format(self._value))
            return
        try:
            val = float(text)
        except ValueError:
            self.entry.setText(self._format(self._value))
            return
        if self.is_int:
            val = int(round(val))
        val = max(self.lo, min(self.hi, val))
        if val == self._value:
            self.entry.setText(self._format(val))
            return
        self._syncing = True
        self.entry.setText(self._format(val))
        self.slider.setValue(self._to_slider(val))
        self._syncing = False
        self._value = val
        self._notify()

    def _notify(self):
        if self.live and self.preview_callback:
            self.preview_callback()
        for fn in self._listeners:
            try:
                fn(self._value)
            except Exception:
                traceback.print_exc()

    def value(self):
        return self._value

    def set_value(self, v, *, notify=False):
        if self.is_int:
            v = int(round(v))
        v = max(self.lo, min(self.hi, v))
        old = self._value
        self._value = v
        self._syncing = True
        self.entry.setText(self._format(v))
        self.slider.setValue(self._to_slider(v))
        self._syncing = False
        if notify and v != old:
            self._notify()

    def set_range(self, lo, hi, *, notify=True):
        """Update the allowed range. Re-clamps the current value if it falls
        outside the new range. Updates the validator and re-derives the
        slider position.

        With notify=True (default), if the current value gets clamped, fires
        listeners and preview_callback so dependent UI updates. Pass
        notify=False to silently clamp without cascading."""
        if hi < lo:
            hi = lo
        self.lo = lo
        self.hi = hi
        # Update validator to reflect new range
        if self.is_int:
            self.entry.setValidator(QIntValidator(int(lo), int(hi)))
        else:
            v = QDoubleValidator(float(lo), float(hi), 4)
            v.setNotation(QDoubleValidator.Notation.StandardNotation)
            self.entry.setValidator(v)
        # Re-clamp current value and update widgets
        old = self._value
        new = max(self.lo, min(self.hi, old))
        self._value = new
        self._syncing = True
        self.entry.setText(self._format(new))
        self.slider.setValue(self._to_slider(new))
        self._syncing = False
        if new != old and notify:
            self._notify()

    def set_enabled(self, enabled):
        self.slider.setEnabled(enabled)
        self.entry.setReadOnly(not enabled)
        self.label.setEnabled(enabled)


# ============================================================================
# 2D PREVIEW CANVAS
# ============================================================================

class PreviewCanvas2D(QLabel):
    # Empty-state hint shown when no audio is loaded. Not a header — this is
    # a soft instruction inside the canvas. Lowercase, no prefix, dim color.
    EMPTY_HINT = 'load audio to begin'

    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.setMinimumSize(PREVIEW_W // 2, PREVIEW_H // 2)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"background-color: {T['canvas']}; color: {T['text_dis']};")
        self.setText(self.EMPTY_HINT)
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(60)
        self._resize_timer.timeout.connect(self._notify_resize)

    def set_pixmap(self, pix):
        if pix is None:
            self.clear()
            self.setText(self.EMPTY_HINT)
        else:
            self.setPixmap(pix)
            self.setText('')

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start()

    def _notify_resize(self):
        self.owner.on_2d_preview_resized()


# ============================================================================
# 3D PREVIEW VIEWER
# ============================================================================

class Preview3DViewer(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._mesh_item = None
        self._grid_item = None
        if HAVE_PYQTGRAPH:
            self.view = gl.GLViewWidget()
            # Slightly lighter than the 2D preview canvas — the 3D view
            # benefits from a touch of contrast headroom on the dark side
            # of the mesh. Still firmly in dark-theme territory.
            self.view.setBackgroundColor('#1c1f24')
            self.view.setCameraPosition(distance=300, elevation=30, azimuth=-60)
            layout.addWidget(self.view)
            self._grid_item = gl.GLGridItem()
            self._grid_item.setSize(x=400, y=400)
            self._grid_item.setSpacing(x=20, y=20)
            self._grid_item.setColor((90, 95, 105, 160))
            self.view.addItem(self._grid_item)
        else:
            self.view = None
            hint = QLabel(
                '// 3d preview unavailable\n\n'
                '   pip install pyqtgraph PyOpenGL\n')
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setStyleSheet(
                f"background-color: {T['canvas']}; "
                f"color: {T['text_dim']}; padding: 40px;")
            layout.addWidget(hint)

    def set_mesh(self, verts, faces, colors):
        if not HAVE_PYQTGRAPH or self.view is None:
            return
        if len(verts) > 0:
            cx, cy = verts[:, 0].mean(), verts[:, 1].mean()
            verts = verts.copy()
            verts[:, 0] -= cx
            verts[:, 1] -= cy
        if self._mesh_item is not None:
            self.view.removeItem(self._mesh_item)
            self._mesh_item = None
        meshdata = gl.MeshData(vertexes=verts, faces=faces, vertexColors=colors)
        self._mesh_item = gl.GLMeshItem(
            meshdata=meshdata, smooth=False, drawEdges=False,
            # Lighting is pre-baked into vertex colors in Preview3DWorker —
            # see notes there. shader=None means pyqtgraph passes our
            # already-lit colors through with no further darkening.
            shader=None, glOptions='opaque')
        self.view.addItem(self._mesh_item)
        if len(verts) > 0:
            r = float(np.linalg.norm(verts, axis=1).max())
            self.view.setCameraPosition(distance=max(80, r * 2.2))

    def clear_mesh(self):
        if self._mesh_item is not None and self.view is not None:
            self.view.removeItem(self._mesh_item)
            self._mesh_item = None


# ============================================================================
# MANUAL — content and dialog
# ============================================================================

# Written for a reader who doesn't know DSP. Technical terms appear so they
# can be looked up, but every parameter is explained in plain language with
# a prescriptive recommendation ("for X type of audio, use Y").
MANUAL_HTML = """
<h1>spectro_studio · manual</h1>

<p class="lede">This tool turns audio into a 3D-printable surface. The loudness
at each frequency over time becomes a height value; the result is exported as
an STL file you can slice and print. Below: what every parameter does and
how to pick values that suit your audio.</p>

<h2>// the pipeline, in one paragraph</h2>

<p>Your audio is sliced into short overlapping chunks. Each chunk is run
through an FFT to estimate how much energy is at each frequency. Stacking
those frequency snapshots side-by-side gives a 2D image (a <i>spectrogram</i>):
the horizontal axis is time, the vertical axis is frequency, and brightness
encodes loudness. That image becomes a heightmap, the heightmap becomes a
mesh, and the mesh is written as an STL. Each section below covers one stage.</p>

<hr/>

<h2>// spectrogram parameters</h2>

<p>These control the analysis itself. Changing any of them re-runs the FFT,
which is the slow part — the tool waits ~350ms after your last change before
recomputing so you can drag sliders without queuing up work.</p>

<h3>fft_size</h3>
<p>How many audio samples go into each FFT chunk. There is a fundamental
trade-off here: <b>large fft_size</b> gives sharp frequency detail (you can
tell two close notes apart) but smudges time (a transient that lasts 20ms
will smear across the chunk). <b>Small fft_size</b> gives sharp time detail
but blurry frequencies. Roughly:</p>
<ul>
<li><code>1024</code>–<code>2048</code>: drums, percussion, transients. Time
crisp, frequency mushy.</li>
<li><code>4096</code>–<code>8192</code>: speech, mixed music. Balanced.</li>
<li><code>16384</code>: sustained tones, ambient, drone, instrumentals with
held notes. Frequency crisp, time mushy.</li>
</ul>

<h3>hop_ratio</h3>
<p>How far each chunk shifts from the previous one, expressed as a fraction
of fft_size. <code>1/16</code> means each chunk overlaps the previous by
15/16 (94%); <code>1/2</code> means they share half their samples (50%).
Higher overlap (smaller fraction → e.g. <code>1/16</code> is higher than
<code>1/2</code>) gives a smoother time axis but proportionally more
computation. <code>1/4</code> or <code>1/8</code> is the standard
compromise; <code>1/16</code> is for smooth, polished results.</p>

<h3>window</h3>
<p>Before each chunk goes into the FFT, it's multiplied by a tapered curve
that smoothly fades the edges to zero. Why? Because the FFT pretends each
chunk repeats forever — and abrupt edges between repeats create fake
high-frequency content called <i>spectral leakage</i>. The window kills the
edges so leakage drops. Each window shape is a different trade-off between
<b>peak sharpness</b> (how cleanly two close frequencies separate) and
<b>noise floor</b> (how loud the leaked junk is around real peaks).
See <a href="#windows">the window cookbook</a> below for the details and
when to choose each.</p>

<h3>freq_scale</h3>
<p><code>log</code> means each octave (doubling of frequency) gets equal
vertical space on the heightmap. This matches how human hearing works — 100
to 200 Hz feels like the same step as 1000 to 2000 Hz. Use it for music.
<code>linear</code> gives each Hz equal space, which means low frequencies
(where most musical content lives) get cramped into the bottom strip. Use it
when you want to highlight high-frequency content evenly, or when comparing
to a scientific reference.</p>

<h3>f_min · f_max</h3>
<p>The frequency range shown on the heightmap. Anything outside this range is
mapped to base height. <code>20 Hz</code> is the lower limit of human hearing;
<code>20,000 Hz</code> is the upper limit (less for adults). The maximum
possible <code>f_max</code> is the Nyquist limit — the audio's sample rate
divided by 2. <code>f_max</code> is auto-clamped to Nyquist when you load a
file. Common moves:</p>
<ul>
<li>For speech: <code>f_min=80</code>, <code>f_max=8000</code>. Cuts hum and
ultrasonic noise, focuses on vocal range.</li>
<li>For full-range music: <code>20</code> to <code>22050</code>.</li>
<li>To emphasize a specific band: narrow the range. The vertical resolution
of the heightmap is fixed (1024 pixels tall), so narrowing the range gives
that band more vertical detail.</li>
</ul>

<h3>db_range</h3>
<p>Dynamic range in decibels — how far below the loudest peak still counts
as "visible" on the heightmap. Audio levels span enormous ranges (a whisper
to a gunshot is ~100 dB), and decibels are how we squash that to something
useful. <b>Smaller db_range (e.g. 40)</b> shows only loud peaks against a
flat base — sharp, dramatic relief. <b>Larger db_range (e.g. 100)</b> reveals
quiet content like reverb tails, ambient noise, and detail — gentler
gradients across more of the surface. Default <code>80</code> is a good
starting point.</p>

<hr/>

<h2>// display</h2>

<h3>colormap</h3>
<p>Only affects the on-screen preview and the saved PNG, <b>not</b> the STL
geometry. <code>grayscale</code> is special: in grayscale the brightness you
see in the preview is exactly the height in the STL. With colored maps the
mapping is no longer monotonic-by-eye (purple isn't taller than yellow in
viridis, for instance), but you may still find color easier to read for
quick navigation. <code>magma</code>, <code>inferno</code>, <code>viridis</code>,
and <code>plasma</code> are perceptually uniform — equal brightness steps
look equal — which makes them well-suited for technical visualization.
<code>phosphor</code> is a CRT-style amber gradient if you want the
retro-terminal look.</p>

<hr/>

<h2>// contrast</h2>

<p>These reshape the heightmap <i>after</i> the spectrogram is built. They're
cheap (preview updates immediately) and they're where you do most of your
artistic tuning.</p>

<h3>gamma</h3>
<p>A non-linear curve applied to the heightmap. <code>gamma &lt; 1</code>
lifts quiet content into visible terrain — useful when most of your audio is
quiet with rare loud peaks, and you want to see the texture in between.
<code>gamma &gt; 1</code> flattens valleys and emphasizes peaks — useful when
you want a sparse, dramatic relief where the loudest moments tower over a
near-flat base. <code>gamma = 1.0</code> is linear (no curve). Default
<code>1.5</code> gently emphasizes peaks.</p>

<h3>floor</h3>
<p>Brightness values below this threshold clip to base height. This is a
noise gate. If your audio has hiss, room tone, or hum, raising floor to
<code>0.3</code>–<code>0.4</code> makes the base of your print clean rather
than textured with noise. Default <code>0.3</code>.</p>

<h3>ceiling</h3>
<p>Brightness values above this threshold clip to maximum height. Useful for
audio with one or two extreme spikes (gunshot, clap, sample-level peak) that
would otherwise force the rest of your content to sit very low. Lowering
ceiling to <code>0.85</code> or <code>0.9</code> compresses those spikes flat
so the rest of the surface gets the full height range. Default <code>1.0</code>
(no compression).</p>

<h3>invert (engrave)</h3>
<p>Flips the heightmap so loud content becomes <i>recessed</i> rather than
raised. The result is a surface where audio carves into the base. Useful if
you want to mill or engrave the spectrogram rather than print it as relief.</p>

<hr/>

<h2>// output — geometry</h2>

<h3>form</h3>
<p><b>flat</b> is a rectangular plate with the spectrogram as relief on top.
Standard for wall art, plaques, and tactile displays.
<b>ring</b> wraps the spectrogram into an annulus (a flat doughnut): time
wraps fully around the circumference (0° to 360°), and frequency maps to
radius (high frequency on the outside, low frequency inside). Watch out:
audio that doesn't loop will show a visible seam where the end meets the
beginning. Crop to a clean loop point or fade your audio if seam matters.</p>

<h3>width_mm / depth_mm / auto_depth (flat only)</h3>
<p><code>width_mm</code> is the physical X size, along the time axis.
<code>depth_mm</code> is the Y size, along the frequency axis. With
<code>auto_depth</code> on, depth is computed so the printed footprint
matches the preview's aspect ratio — i.e. the STL looks like what you see
on screen. Uncheck to set depth manually if you want a specific aspect
(square plates, etc.).</p>

<h3>outer_r_mm / ring_w_mm (ring only)</h3>
<p><code>outer_r_mm</code> is half the outer diameter. <code>ring_w_mm</code>
is the radial width of the band; the inner radius is computed
(<code>outer_r − ring_w</code>) and has to stay positive. Thin rings read as
bracelets or rings; wide rings approach a disc with a small central hole.
Note that the inner edge is angularly compressed and the outer edge is
stretched — that's unavoidable when you wrap a rectangle onto a ring, more
noticeable at large ring widths.</p>

<h3>max_height_mm</h3>
<p>Maximum height of the relief above the base — the tallest point of the
loudest moment. <code>25.4 mm = 1"</code>. The cap is <code>254 mm = 10"</code>,
which is sculptural territory. Higher relief reads more dramatically but
takes longer to print and uses more filament.</p>

<h3>base_mm</h3>
<p>Solid thickness beneath the relief. <code>1</code>–<code>3 mm</code> is
typical for FDM printing. <code>0</code> gives a base-less mesh (it will still
be watertight; the underside of the relief becomes the underside of the
print). For Ring forms, a base of <code>2</code>–<code>3 mm</code> makes a
nice flat bottom to sit on.</p>

<h3>mesh_res</h3>
<p>Width of the mesh grid in vertices. Higher values give finer detail in
the surface but produce bigger STL files and longer slicing times.
Suggestions:</p>
<ul>
<li><code>500</code>–<code>1000</code>: quick prototypes, draft prints.</li>
<li><code>2000</code>: balanced default — produces a few-million-triangle
mesh that slices in a few seconds.</li>
<li><code>4000</code>+: production / fine detail, larger files, slower.</li>
</ul>
<p>The STL size estimate beneath this slider shows you what you're committing
to before you export.</p>

<hr/>

<h2 id="windows">// window cookbook</h2>

<p>All five windows do the same job — taper the edges of each FFT chunk to
suppress spectral leakage — but they trade off two things differently:</p>
<ul>
<li><b>Main-lobe width</b>: how cleanly two close frequencies separate.
Narrower is sharper.</li>
<li><b>Side-lobe level</b>: how loud the leaked junk is around real peaks.
Lower is cleaner.</li>
</ul>
<p>You can have one or the other but not both. Here's when to reach for each:</p>

<h3>hann (default)</h3>
<p>A smooth cosine taper. Side-lobes around <code>-32 dB</code>, moderate
main lobe width. The standard general-purpose window. If you don't have a
reason to use something else, use this.</p>

<h3>hamming</h3>
<p>Similar to Hann but with a small DC offset that lowers the first side-lobe
to about <code>-43 dB</code> at the cost of slightly higher distant side-lobes.
Use when the loudest content drowns out neighbors and you want a touch
cleaner peaks; perceptually very similar to Hann in most music.</p>

<h3>blackman</h3>
<p>A three-cosine sum. Side-lobes around <code>-58 dB</code> — much cleaner
peak separation — but the main lobe is wider, so close frequencies blur
together. Use when your audio has loud sustained tones whose neighbors you
want suppressed (organ, drone, sustained chords).</p>

<h3>blackmanharris</h3>
<p>The extreme version: side-lobes around <code>-92 dB</code>, ultra-clean
peaks against a very low noise floor. The main lobe is wider still. Use for
very pure tones with quiet background you want to reveal (test tones, single
instruments, audio analysis where leakage matters more than time resolution).
For most music it's overkill and the time smearing is annoying.</p>

<h3>rect (no window)</h3>
<p>Literally no taper. Sharpest possible main lobe, very loud side-lobes
(around <code>-13 dB</code>). Use only for transients (drums, claps, gunshots)
where you don't care about leakage and want the crispest possible time
resolution. In effect, you're letting the FFT see the abrupt edges of the
chunk — fine for impulse-like content, terrible for sustained tones.</p>

<h3>which one for what?</h3>
<ul>
<li><b>Music, mixed sources, unknown content:</b> hann.</li>
<li><b>Drums, percussion, transients, speech consonants:</b> hann (still fine)
or rect if you want maximum bite.</li>
<li><b>Sustained tones, drones, ambient, organ:</b> blackman or
blackmanharris.</li>
<li><b>Speech vowels, sustained vocal notes:</b> blackman.</li>
<li><b>Field recordings with loud peaks and quiet detail:</b> hamming or
blackman.</li>
</ul>

<hr/>

<h2>// workflow tips</h2>

<ul>
<li><b>Start grayscale.</b> Switch colormaps later for the saved PNG. While
tuning, grayscale is the only mode where what you see is what you'll print.</li>
<li><b>Tune contrast last.</b> Set fft_size, hop, and window first (because
they trigger expensive recomputes). Then sweep gamma / floor / ceiling — the
preview updates instantly.</li>
<li><b>Watch the triangle estimate</b> below mesh_res. If you're seeing tens
of millions of triangles, your slicer is going to struggle and the STL will
be hundreds of megabytes. Dial mesh_res down until you're under 5M for most
prints.</li>
<li><b>The 3D preview is capped at 400 grid columns</b> for interactivity.
The exported STL uses the full mesh_res — don't worry that the preview looks
chunkier than the final.</li>
<li><b>For Ring form, crop your audio to a clean loop point first.</b> The
seam where end meets beginning will show on the print.</li>
</ul>

<hr/>

<p class="footer">spectro_studio · v16 · drag audio onto the slot or anywhere
on the window to load</p>
"""


class ManualDialog(QDialog):
    """Modal manual. Mono font, dark theme, scrollable, with the same
    aesthetic as the main app — but rendered text rather than form widgets."""

    def __init__(self, parent, mono_family):
        super().__init__(parent)
        self.setWindowTitle('spectro_studio · manual')
        self.resize(820, 720)
        self.setModal(False)  # let user keep tweaking while reading

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        # Stylesheet for the manual content. Note QTextBrowser uses a subset
        # of CSS — keep it simple.
        css = f"""
        <style>
            body {{
                background-color: {T['bg']};
                color: {T['text']};
                font-family: '{mono_family}', monospace;
                font-size: 12px;
                line-height: 1.6;
                padding: 28px 36px;
            }}
            h1 {{
                color: {T['text']};
                font-size: 18px;
                font-weight: normal;
                margin: 0 0 6px 0;
                padding: 0;
            }}
            h2 {{
                color: {T['text_dim']};
                font-size: 13px;
                font-weight: normal;
                margin: 28px 0 8px 0;
                letter-spacing: 0.3px;
            }}
            h3 {{
                color: {T['accent']};
                font-size: 12px;
                font-weight: normal;
                margin: 18px 0 4px 0;
            }}
            p {{
                color: {T['text']};
                margin: 0 0 10px 0;
            }}
            p.lede {{
                color: {T['text_dim']};
                margin: 0 0 16px 0;
            }}
            p.footer {{
                color: {T['text_dis']};
                margin-top: 24px;
                font-size: 11px;
            }}
            code {{
                color: {T['accent']};
                background-color: {T['surface']};
                padding: 1px 4px;
            }}
            b {{
                color: {T['text']};
                font-weight: bold;
            }}
            i {{
                color: {T['text_dim']};
                font-style: normal;
            }}
            ul {{
                margin: 4px 0 12px 0;
                padding-left: 20px;
            }}
            li {{
                color: {T['text']};
                margin: 3px 0;
            }}
            hr {{
                border: none;
                border-top: 1px solid {T['border']};
                margin: 24px 0;
            }}
            a {{
                color: {T['accent']};
                text-decoration: none;
            }}
        </style>
        """
        browser.setHtml(css + MANUAL_HTML)
        # Style the scrollbar via the dialog stylesheet to match the main app
        browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {T['bg']};
                border: none;
            }}
            QScrollBar:vertical {{
                background: {T['bg']};
                width: 10px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {T['border']};
                min-height: 30px;
                border-radius: 0;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {T['text_dim']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: {T['bg']};
            }}
        """)
        layout.addWidget(browser)

        # Footer bar with a close button — keyboard Esc also closes (QDialog default)
        footer = QWidget()
        footer.setStyleSheet(f"background-color: {T['bg']};")
        f_layout = QHBoxLayout(footer)
        f_layout.setContentsMargins(PAD * 2, PAD, PAD * 2, PAD)
        hint = QLabel('// esc or click outside to close')
        hint.setStyleSheet(f"color: {T['text_dis']};")
        f_layout.addWidget(hint)
        f_layout.addStretch(1)
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.accept)
        f_layout.addWidget(close_btn)
        layout.addWidget(footer)


# ============================================================================
# TOOLTIPS for individual controls (re-added in v5)
# ============================================================================

TIP = {
    'fft_size':   'Samples per FFT chunk. Larger = finer frequency, coarser '
                  'time. See manual for guidance.',
    'hop_ratio':  'Chunk overlap as a fraction of fft_size. 1/16 = 94% overlap.',
    'window':     'Taper shape applied before each FFT. Hann is the default; '
                  'see manual for the cookbook.',
    'freq_scale': 'log = octaves equally spaced (musical). linear = Hz '
                  'equally spaced.',
    'fmin':       'Lowest frequency on the heightmap. Type a value and press '
                  'Enter to commit.',
    'fmax':       'Highest frequency. Capped at Nyquist (sample rate ÷ 2).',
    'db_range':   'Dynamic range in dB. Smaller = sharper peaks; larger = '
                  'more quiet detail.',
    'cmap':       'Affects preview/PNG only, not STL geometry. Grayscale: '
                  'brightness = STL height.',
    'gamma':      '<1 lifts quiet content; >1 emphasizes peaks; 1 = linear.',
    'floor':      'Brightness below this clips to base. Acts as a noise gate.',
    'ceiling':    'Brightness above this clips to max height. Tames extreme '
                  'spikes.',
    'invert':     'Loud content becomes recessed — engraving instead of '
                  'relief.',
    'form':       'flat = rectangular plate. ring = wrap into annulus (time '
                  'wraps 360°, frequency = radius).',
    'outer_r':    'Outer radius of the ring (mm). Diameter = 2×.',
    'ring_w':     'Radial width of the ring. Inner radius = outer − this.',
    'width_mm':   'Physical X size (along the time axis).',
    'depth_mm':   'Physical Y size. With auto_depth on, derived from preview '
                  'aspect.',
    'auto_depth': 'Match STL footprint to preview/PNG aspect ratio.',
    'max_h':      'Max relief height above base. 254 mm = 10".',
    'base_mm':    'Solid thickness beneath relief. 1–3 mm typical for FDM.',
    'mesh_res':   'Grid width in vertices. Higher = finer detail, bigger STL.',
    'save_png':   'Export current preview as PNG.',
    'export_stl': 'Build the full watertight mesh and save as binary STL.',
}


# ============================================================================
# MAIN WINDOW
# ============================================================================

class SpectroStudio(QMainWindow):
    def __init__(self, mono_family='monospace'):
        super().__init__()
        self.setWindowTitle('spectro_studio')
        self.resize(1240, 880)
        self.setMinimumSize(1060, 740)

        self._mono_family = mono_family
        self._manual_dialog = None  # cached so it remembers scroll position

        # Accept drops at the window level too, so dropping anywhere works
        self.setAcceptDrops(True)

        self.audio_path = None
        self.sr = 0
        self.duration = 0.0
        self.spec = None
        self.heightmap = None
        self.lut_view = build_lut('phosphor')
        self._current_pixmap = None

        self._spec_timer = QTimer(self)
        self._spec_timer.setSingleShot(True)
        self._spec_timer.setInterval(SPEC_DEBOUNCE_MS)
        self._spec_timer.timeout.connect(self._do_compute)

        self._contrast_timer = QTimer(self)
        self._contrast_timer.setSingleShot(True)
        self._contrast_timer.setInterval(CONTRAST_DEBOUNCE_MS)
        self._contrast_timer.timeout.connect(self._render_2d_preview)

        self._preview3d_timer = QTimer(self)
        self._preview3d_timer.setSingleShot(True)
        self._preview3d_timer.setInterval(PREVIEW_3D_DEBOUNCE_MS)
        self._preview3d_timer.timeout.connect(self._do_rebuild_3d)

        self._compute_worker = None
        self._stl_worker = None
        self._png_worker = None
        self._preview3d_worker = None

        self._ui_ready = False
        self._build_ui()
        self._ui_ready = True
        self._sync_buttons()
        self._update_tri_estimate()

    # ------------------------------------------------------------------
    # Window-level drag-drop (lets user drop anywhere, not just on the slot)
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event: QDragEnterEvent):
        if DropZone._mime_has_audio(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        path = DropZone._mime_first_audio(event.mimeData())
        if path:
            event.acceptProposedAction()
            self._load_audio_path(path)

    def eventFilter(self, obj, event):
        # Keep the busy overlay matched to the preview container's size.
        # Without this, after window resizes the overlay shows in the wrong
        # place — the parent grows but the child widget doesn't follow.
        if (hasattr(self, '_preview_container')
                and obj is self._preview_container
                and event.type() in (event.Type.Resize, event.Type.Show)):
            if hasattr(self, 'busy_overlay'):
                self.busy_overlay.resize(self._preview_container.size())
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(PAD * 2, PAD * 2, PAD * 2, PAD)
        outer.setSpacing(0)

        # === Title strip ===
        title_row = QHBoxLayout()
        title_row.setSpacing(PAD)
        title = QLabel('spectro_studio')
        title.setStyleSheet(
            f"color: {T['text']}; "
            f"font-size: 14px; "
            f"letter-spacing: 0.5px;")
        subtitle = QLabel('// audio → heightmap → printable mesh')
        subtitle.setStyleSheet(f"color: {T['text_dim']};")
        title_row.addWidget(title)
        title_row.addWidget(subtitle)
        title_row.addStretch(1)
        # Manual button — minimal, just a `?` in the corner
        self.btn_manual = QPushButton('?  Manual')
        self.btn_manual.setToolTip('Open the manual')
        self.btn_manual.clicked.connect(self._open_manual)
        title_row.addWidget(self.btn_manual)
        outer.addLayout(title_row)

        outer.addSpacing(4)
        outer.addWidget(HRule())
        outer.addSpacing(PAD)

        # === Drop zone (full width, top) ===
        self.drop_zone = DropZone()
        self.drop_zone.file_dropped.connect(self._load_audio_path)
        self.drop_zone.browse_requested.connect(self._browse_audio)
        outer.addWidget(self.drop_zone)

        # === Main split: params | preview ===
        outer.addSpacing(PAD)
        main = QWidget()
        main_layout = QHBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(PAD * 2)
        outer.addWidget(main, stretch=1)

        # Left: params sidebar.
        # The sidebar is wrapped in a QScrollArea because with 7+ sections
        # (Presets, Spectrogram, Display, Contrast, Output)
        # the total height of the controls can exceed the window height on
        # shorter displays. Without the scroll area, Qt squashes rows to
        # fit — which makes them unreadable. With it, content overflows
        # cleanly and a scrollbar appears only when needed; on tall
        # windows the scroll area is invisible.
        params_widget = QWidget()
        # params_widget no longer has a fixed width — the scroll area sets
        # the fixed width on itself, and the inner widget fills it.
        params_layout = QVBoxLayout(params_widget)
        params_layout.setContentsMargins(0, 0, 0, 0)
        params_layout.setSpacing(0)
        # Critical: tell the layout that the widget MUST be at least as tall
        # as its content demands. Without this, the scroll area's
        # widgetResizable=True flag interprets "fit inside viewport" as
        # license to compress rows below their min-height. SetMinimumSize
        # makes the widget grow to its content's minimum (triggering scroll)
        # rather than squashing.
        params_layout.setSizeConstraint(
            QVBoxLayout.SizeConstraint.SetMinimumSize)
        self._build_param_panels(params_layout)
        params_layout.addStretch(1)

        params_scroll = QScrollArea()
        params_scroll.setWidget(params_widget)
        params_scroll.setWidgetResizable(True)  # let inner widget take scroll area's width
        params_scroll.setFixedWidth(PARAMS_WIDTH)
        # Hide horizontal scrollbar — sidebar is fixed-width, no horizontal
        # scroll should ever be needed
        params_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        params_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # Match the dark surface so the scroll area itself isn't visible
        # against the rest of the UI
        params_scroll.setStyleSheet(
            f"QScrollArea {{ background: {T['bg']}; border: none; }}")
        main_layout.addWidget(params_scroll)

        # Vertical hairline divider between params and preview
        vsep = QWidget()
        vsep.setFixedWidth(1)
        vsep.setStyleSheet(f"background-color: {T['border']};")
        main_layout.addWidget(vsep)

        # Right: preview
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(PAD)
        self._build_preview_panel(preview_layout)
        main_layout.addWidget(preview_widget, stretch=1)

        # === Bottom status bar ===
        outer.addWidget(HRule())
        outer.addSpacing(6)
        bot = QHBoxLayout()
        bot.setContentsMargins(0, 0, 0, 0)
        self.status_label = QLabel('// idle · awaiting audio')
        self.status_label.setStyleSheet(f"color: {T['text_dim']};")
        bot.addWidget(self.status_label, stretch=1)
        # Mono fingerprint on the right
        fp = QLabel(f"{Path(__file__).name if '__file__' in globals() else 'spectro_studio'} · v16")
        fp.setStyleSheet(f"color: {T['text_dis']};")
        bot.addWidget(fp)
        outer.addLayout(bot)

    def _build_param_panels(self, parent_layout):
        # ---- presets ----
        # Compact preset chooser at the top — presets are an entry point, so
        # they sit above the parameters they affect. Single row of widgets to
        # keep vertical footprint small (the sidebar is already dense).
        parent_layout.addWidget(SectionLabel('presets', padding_top=0))
        self._build_presets_row(parent_layout)

        # ---- spectrogram ----
        parent_layout.addWidget(SectionLabel('spectrogram'))
        sg_grid = QGridLayout()
        sg_grid.setHorizontalSpacing(PAD)
        sg_grid.setVerticalSpacing(3)
        sg_grid.setColumnStretch(1, 1)
        self.cb_nfft = self._add_combo_row(
            sg_grid, 0, 'FFT Size',
            ['256','512','1024','2048','4096','8192','16384'], '16384',
            on_change=self._schedule_compute, tip=TIP['fft_size'])
        self.cb_hop = self._add_combo_row(
            sg_grid, 1, 'Hop Ratio', ['2','4','8','16'], '16',
            on_change=self._schedule_compute, tip=TIP['hop_ratio'])
        self.cb_window = self._add_combo_row(
            sg_grid, 2, 'Window',
            ['Hann','Hamming','Blackman','Blackman-Harris','Rect'], 'Hann',
            on_change=self._schedule_compute, tip=TIP['window'])
        self.cb_scale = self._add_combo_row(
            sg_grid, 3, 'Frequency Scale', ['Log','Linear'], 'Log',
            on_change=self._schedule_compute, tip=TIP['freq_scale'])
        self.r_fmin = NumericRow(sg_grid, 4, 'Min Frequency', 0, 24000, 20,
                                 is_int=True, tip=TIP['fmin'])
        self.r_fmax = NumericRow(sg_grid, 5, 'Max Frequency', 0, 24000, 22050,
                                 is_int=True, tip=TIP['fmax'])
        self.r_db = NumericRow(sg_grid, 6, 'dB Range', 20, 120, 80,
                               is_int=True, tip=TIP['db_range'])
        for r in (self.r_fmin, self.r_fmax, self.r_db):
            r.value_changed(lambda _v: self._schedule_compute())
        parent_layout.addLayout(sg_grid)

        # ---- display ----
        parent_layout.addWidget(SectionLabel('display'))
        dg_grid = QGridLayout()
        dg_grid.setHorizontalSpacing(PAD)
        dg_grid.setVerticalSpacing(3)
        dg_grid.setColumnStretch(1, 1)
        self.cb_cmap = self._add_combo_row(
            dg_grid, 0, 'Colormap', list(COLORMAP_DISPLAY.keys()), 'Phosphor',
            on_change=self._on_cmap_change, tip=TIP['cmap'])
        parent_layout.addLayout(dg_grid)

        # ---- contrast (live) ----
        parent_layout.addWidget(SectionLabel('contrast'))
        cg_grid = QGridLayout()
        cg_grid.setHorizontalSpacing(PAD)
        cg_grid.setVerticalSpacing(3)
        cg_grid.setColumnStretch(1, 1)
        self.r_gamma = NumericRow(cg_grid, 0, 'Gamma', 0.2, 4.0, 1.5,
                                  fmt='{:.2f}', live=True, tip=TIP['gamma'],
                                  preview_callback=self._schedule_contrast)
        self.r_floor = NumericRow(cg_grid, 1, 'Floor', 0.0, 0.95, 0.3,
                                  fmt='{:.2f}', live=True, tip=TIP['floor'],
                                  preview_callback=self._schedule_contrast)
        self.r_ceiling = NumericRow(cg_grid, 2, 'Ceiling', 0.05, 1.0, 1.0,
                                    fmt='{:.2f}', live=True, tip=TIP['ceiling'],
                                    preview_callback=self._schedule_contrast)
        self.cb_invert = QCheckBox('Invert (engrave)')
        self.cb_invert.setToolTip(TIP['invert'])
        self.cb_invert.stateChanged.connect(self._schedule_contrast)
        cg_grid.addWidget(self.cb_invert, 3, 0, 1, 3)
        parent_layout.addLayout(cg_grid)

        # ---- output ----
        parent_layout.addWidget(SectionLabel('output'))
        og_grid = QGridLayout()
        og_grid.setHorizontalSpacing(PAD)
        og_grid.setVerticalSpacing(3)
        og_grid.setColumnStretch(1, 1)

        # form selector as toggle buttons rather than dropdown — fewer clicks
        form_lbl = QLabel('Form')
        form_lbl.setStyleSheet(f"color: {T['text_dim']};")
        og_grid.addWidget(form_lbl, 0, 0)
        form_row = QHBoxLayout()
        form_row.setContentsMargins(0, 0, 0, 0)
        form_row.setSpacing(0)
        self.btn_flat = QPushButton('Flat')
        self.btn_flat.setCheckable(True)
        self.btn_flat.setChecked(True)
        self.btn_ring = QPushButton('Ring')
        self.btn_ring.setCheckable(True)
        form_group = QButtonGroup(self)
        form_group.setExclusive(True)
        form_group.addButton(self.btn_flat)
        form_group.addButton(self.btn_ring)
        self.btn_flat.setToolTip(TIP['form'])
        self.btn_ring.setToolTip(TIP['form'])
        self.btn_flat.clicked.connect(lambda: self._on_form_change('flat'))
        self.btn_ring.clicked.connect(lambda: self._on_form_change('ring'))
        form_row.addWidget(self.btn_flat)
        form_row.addWidget(self.btn_ring)
        form_row.addStretch(1)
        form_container = QWidget()
        form_container.setLayout(form_row)
        og_grid.addWidget(form_container, 0, 1, 1, 2)

        parent_layout.addLayout(og_grid)

        # Flat-specific
        self.flat_widget = QWidget()
        fr = QGridLayout(self.flat_widget)
        fr.setHorizontalSpacing(PAD); fr.setVerticalSpacing(3)
        fr.setColumnStretch(1, 1)
        fr.setContentsMargins(0, 4, 0, 0)
        self.r_width = NumericRow(fr, 0, 'Width (mm)', 10, 1000, 200.0,
                                  fmt='{:.1f}', tip=TIP['width_mm'])
        self.r_width.value_changed(
            lambda _v: (self._refresh_auto_depth(),
                        self._schedule_3d_preview()))
        self.r_depth = NumericRow(fr, 1, 'Depth (mm)', 10, 1000, 50.0,
                                  fmt='{:.1f}', tip=TIP['depth_mm'])
        self.r_depth.value_changed(lambda _v: self._schedule_3d_preview())
        self.cb_depth_auto = QCheckBox('Auto depth from preview aspect')
        self.cb_depth_auto.setToolTip(TIP['auto_depth'])
        self.cb_depth_auto.setChecked(True)
        self.cb_depth_auto.stateChanged.connect(self._on_depth_auto_toggle)
        fr.addWidget(self.cb_depth_auto, 2, 0, 1, 3)
        parent_layout.addWidget(self.flat_widget)

        # Ring-specific
        self.ring_widget = QWidget()
        rr = QGridLayout(self.ring_widget)
        rr.setHorizontalSpacing(PAD); rr.setVerticalSpacing(3)
        rr.setColumnStretch(1, 1)
        rr.setContentsMargins(0, 4, 0, 0)
        self.r_outer = NumericRow(rr, 0, 'Outer Radius (mm)', 10, 200, 50.0,
                                  fmt='{:.1f}', tip=TIP['outer_r'])
        self.r_outer.value_changed(
            lambda _v: (self._update_tri_estimate(),
                        self._schedule_3d_preview()))
        self.r_ring_w = NumericRow(rr, 1, 'Ring Width (mm)', 5, 100, 30.0,
                                   fmt='{:.1f}', tip=TIP['ring_w'])
        self.r_ring_w.value_changed(
            lambda _v: (self._update_tri_estimate(),
                        self._schedule_3d_preview()))
        parent_layout.addWidget(self.ring_widget)
        self.ring_widget.hide()

        # Common
        common_grid = QGridLayout()
        common_grid.setHorizontalSpacing(PAD)
        common_grid.setVerticalSpacing(3)
        common_grid.setColumnStretch(1, 1)
        common_grid.setContentsMargins(0, 4, 0, 0)
        self.r_max_h = NumericRow(common_grid, 0, 'Max Height (mm)', 0.5, 254,
                                  25.4, fmt='{:.1f}', tip=TIP['max_h'])
        self.r_max_h.value_changed(lambda _v: self._schedule_3d_preview())
        self.r_base = NumericRow(common_grid, 1, 'Base (mm)', 0.0, 20, 2.0,
                                 fmt='{:.1f}', tip=TIP['base_mm'])
        self.r_base.value_changed(lambda _v: self._schedule_3d_preview())
        self.r_res = NumericRow(common_grid, 2, 'Mesh Resolution', 100, 8000, 2000,
                                is_int=True, tip=TIP['mesh_res'])
        self.r_res.value_changed(lambda _v: self._update_tri_estimate())

        self.tri_estimate = QLabel(' ')
        self.tri_estimate.setStyleSheet(f"color: {T['text_dim']};")
        common_grid.addWidget(self.tri_estimate, 3, 0, 1, 3)
        parent_layout.addLayout(common_grid)

        # Action buttons — primary export gets the accent treatment
        parent_layout.addSpacing(PAD)
        act_row = QHBoxLayout()
        act_row.setSpacing(PAD)
        self.btn_save_png = QPushButton('Save PNG')
        self.btn_save_png.setToolTip(TIP['save_png'])
        self.btn_save_png.clicked.connect(self.save_preview_png)
        self.btn_stl = QPushButton('Export STL')
        self.btn_stl.setObjectName('primary')
        self.btn_stl.setToolTip(TIP['export_stl'])
        self.btn_stl.clicked.connect(self.generate_stl)
        act_row.addWidget(self.btn_save_png)
        act_row.addWidget(self.btn_stl, stretch=1)
        parent_layout.addLayout(act_row)

        self._on_depth_auto_toggle()
        self._wire_cross_constraints()

    # ------------------------------------------------------------------
    # Cross-parameter constraints
    # ------------------------------------------------------------------
    # Three pairs of parameters have to obey strict ordering. Rather than
    # discover violations at compute/export time and throw an error, we keep
    # them coupled at the slider level: changing one bumps the other's range
    # so the invalid region simply can't be selected.
    #
    #   f_min < f_max         (else stft_to_heightmap silently clamps)
    #   floor < ceiling       (else apply_curve raises ValueError)
    #   ring_w < outer_r      (else build_ring_mesh raises ValueError)
    #
    # The epsilon below is the strict-less-than buffer — small enough not to
    # feel like the slider is "stuck", large enough to keep the math safe.
    def _wire_cross_constraints(self):
        # --- f_min < f_max ---
        # When f_min changes, f_max can't dip below f_min + 1Hz.
        # When f_max changes, f_min can't rise above f_max - 1Hz.
        def on_fmin(v):
            self.r_fmax.set_range(max(1, int(v) + 1), 24000, notify=False)
        def on_fmax(v):
            self.r_fmin.set_range(0, max(0, int(v) - 1), notify=False)
        self.r_fmin.value_changed(on_fmin)
        self.r_fmax.value_changed(on_fmax)
        # Apply once at startup so initial bounds reflect defaults
        on_fmin(self.r_fmin.value())
        on_fmax(self.r_fmax.value())

        # --- floor < ceiling ---
        # apply_curve refuses floor == ceiling, so use a 0.01 buffer.
        FC_EPS = 0.01
        def on_floor(v):
            self.r_ceiling.set_range(round(v + FC_EPS, 2), 1.0, notify=False)
        def on_ceiling(v):
            self.r_floor.set_range(0.0, round(v - FC_EPS, 2), notify=False)
        self.r_floor.value_changed(on_floor)
        self.r_ceiling.value_changed(on_ceiling)
        on_floor(self.r_floor.value())
        on_ceiling(self.r_ceiling.value())

        # --- ring_w < outer_r ---
        # Use 0.1 mm buffer so the inner radius is always >= 0.1 mm (the
        # mesh would degenerate if inner radius hit zero).
        RW_EPS = 0.1
        def on_outer(v):
            self.r_ring_w.set_range(5.0, round(v - RW_EPS, 1), notify=False)
        def on_ring_w(v):
            # If user explicitly maxes ring_w, push outer_r up to match
            # rather than blocking — keeps the slider feeling responsive.
            min_outer = round(v + RW_EPS, 1)
            if self.r_outer.value() < min_outer:
                self.r_outer.set_range(min_outer, 200, notify=False)
                self.r_outer.set_value(min_outer)
        self.r_outer.value_changed(on_outer)
        self.r_ring_w.value_changed(on_ring_w)
        on_outer(self.r_outer.value())

    def _add_combo_row(self, grid, row, label, values, default,
                       on_change=None, tip=None):
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {T['text_dim']};")
        lbl.setMinimumHeight(ROW_MIN_HEIGHT)
        cb = QComboBox()
        cb.addItems(values)
        cb.setCurrentText(default)
        # Fixed (not just minimum) — same reason as QLineEdit in NumericRow:
        # QComboBox text can clip vertically when over-constrained.
        cb.setFixedHeight(ROW_MIN_HEIGHT)
        if tip:
            lbl.setToolTip(tip)
            cb.setToolTip(tip)
        grid.addWidget(lbl, row, 0)
        grid.addWidget(cb, row, 1, 1, 2)
        if on_change:
            cb.currentTextChanged.connect(lambda _t: on_change())
        return cb

    # ------------------------------------------------------------------
    # Presets — UI + persistence
    # ------------------------------------------------------------------
    # The preset row appears at the top of the sidebar. Layout:
    #
    #   [Preset dropdown ▾]
    #   [Save]  [Save As…]  [Rename]  [Delete]
    #
    # Selecting a preset from the dropdown applies it immediately. The four
    # action buttons cover the full lifecycle.
    def _build_presets_row(self, parent_layout):
        # Load from disk once at startup. Mutations call save_presets()
        # immediately so the file is always in sync.
        self._presets = load_presets()
        self._suppress_preset_apply = False  # used to avoid recursive applies

        self.cb_preset = QComboBox()
        self.cb_preset.setToolTip(
            "Saved parameter snapshots. Selecting one applies it to all "
            "controls below.")
        self.cb_preset.setFixedHeight(ROW_MIN_HEIGHT)
        self._refresh_preset_combo()
        self.cb_preset.currentIndexChanged.connect(self._on_preset_selected)
        parent_layout.addWidget(self.cb_preset)

        # Action row below the dropdown. Compact — these are infrequent
        # operations, so they don't need to be large.
        actions = QHBoxLayout()
        actions.setSpacing(PAD // 2)
        actions.setContentsMargins(0, 4, 0, 0)

        self.btn_preset_save = QPushButton('Save')
        self.btn_preset_save.setFixedHeight(ROW_MIN_HEIGHT)
        self.btn_preset_save.setToolTip(
            "Overwrite the currently-selected preset with the current "
            "parameter values. Disabled when no preset is selected.")
        self.btn_preset_save.clicked.connect(self._on_preset_save)

        self.btn_preset_save_as = QPushButton('Save As…')
        self.btn_preset_save_as.setFixedHeight(ROW_MIN_HEIGHT)
        self.btn_preset_save_as.setToolTip(
            "Save the current parameter values as a new named preset.")
        self.btn_preset_save_as.clicked.connect(self._on_preset_save_as)

        self.btn_preset_rename = QPushButton('Rename')
        self.btn_preset_rename.setFixedHeight(ROW_MIN_HEIGHT)
        self.btn_preset_rename.setToolTip("Rename the selected preset.")
        self.btn_preset_rename.clicked.connect(self._on_preset_rename)

        self.btn_preset_delete = QPushButton('Delete')
        self.btn_preset_delete.setFixedHeight(ROW_MIN_HEIGHT)
        self.btn_preset_delete.setToolTip("Delete the selected preset.")
        self.btn_preset_delete.clicked.connect(self._on_preset_delete)

        actions.addWidget(self.btn_preset_save)
        actions.addWidget(self.btn_preset_save_as)
        actions.addWidget(self.btn_preset_rename)
        actions.addWidget(self.btn_preset_delete)
        parent_layout.addLayout(actions)

        self._sync_preset_buttons()

    def _refresh_preset_combo(self):
        """Rebuild the dropdown items from self._presets. Preserves the
        currently-selected name across rebuild when possible."""
        prev_name = self.cb_preset.currentText() if hasattr(self, 'cb_preset') else ''
        self._suppress_preset_apply = True
        self.cb_preset.clear()
        # First item is a non-selectable "(none)" placeholder so the
        # dropdown can be in a no-preset-selected state. We use index 0 as
        # the "nothing selected" sentinel.
        self.cb_preset.addItem('(no preset selected)')
        for p in self._presets:
            self.cb_preset.addItem(p['name'])
        # Restore prior selection if it still exists
        if prev_name:
            idx = self.cb_preset.findText(prev_name)
            if idx >= 0:
                self.cb_preset.setCurrentIndex(idx)
        self._suppress_preset_apply = False

    def _sync_preset_buttons(self):
        """Enable/disable buttons based on selection state. Save/Rename/
        Delete need an existing preset; Save As is always available."""
        has_selection = self.cb_preset.currentIndex() > 0
        self.btn_preset_save.setEnabled(has_selection)
        self.btn_preset_rename.setEnabled(has_selection)
        self.btn_preset_delete.setEnabled(has_selection)
        # Save As stays enabled — caps enforced inside the handler.
        self.btn_preset_save_as.setEnabled(
            len(self._presets) < PRESETS_MAX_COUNT)

    def _selected_preset_index(self):
        """Return the index into self._presets for the currently selected
        item, or None if nothing is selected. The combobox has a sentinel
        at index 0, so we subtract one."""
        i = self.cb_preset.currentIndex()
        return (i - 1) if i > 0 else None

    def _on_preset_selected(self):
        # Called both by user clicks and by programmatic combobox changes.
        # _suppress_preset_apply is set during _refresh_preset_combo so we
        # don't re-apply on every rebuild.
        self._sync_preset_buttons()
        if self._suppress_preset_apply:
            return
        idx = self._selected_preset_index()
        if idx is None:
            return
        self._apply_preset(self._presets[idx]['params'])

    def _on_preset_save(self):
        idx = self._selected_preset_index()
        if idx is None:
            return
        name = self._presets[idx]['name']
        reply = QMessageBox.question(
            self, 'Overwrite preset',
            f"Overwrite preset '{name}' with current parameters?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._presets[idx]['params'] = self._snapshot_params()
        save_presets(self._presets)
        self._set_status(f"// preset · saved '{name}'")

    def _on_preset_save_as(self):
        if len(self._presets) >= PRESETS_MAX_COUNT:
            QMessageBox.information(
                self, 'Preset limit reached',
                f"You already have {PRESETS_MAX_COUNT} presets. Delete one "
                "before creating another.")
            return
        name, ok = QInputDialog.getText(
            self, 'New preset', 'Preset name:')
        if not ok or not name.strip():
            return
        name = name.strip()
        # Names should be unique — if the name already exists, treat as
        # an overwrite-confirm flow
        existing = [i for i, p in enumerate(self._presets) if p['name'] == name]
        if existing:
            reply = QMessageBox.question(
                self, 'Name in use',
                f"A preset called '{name}' already exists. Overwrite it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return
            self._presets[existing[0]]['params'] = self._snapshot_params()
        else:
            self._presets.append({'name': name, 'params': self._snapshot_params()})
        save_presets(self._presets)
        self._refresh_preset_combo()
        # Select the just-saved preset
        idx = self.cb_preset.findText(name)
        if idx > 0:
            self.cb_preset.setCurrentIndex(idx)
        self._sync_preset_buttons()
        self._set_status(f"// preset · saved '{name}'")

    def _on_preset_rename(self):
        idx = self._selected_preset_index()
        if idx is None:
            return
        old_name = self._presets[idx]['name']
        new_name, ok = QInputDialog.getText(
            self, 'Rename preset', 'New name:', text=old_name)
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        new_name = new_name.strip()
        # Reject collisions
        if any(p['name'] == new_name for i, p in enumerate(self._presets) if i != idx):
            QMessageBox.warning(self, 'Name in use',
                                f"A preset called '{new_name}' already exists.")
            return
        self._presets[idx]['name'] = new_name
        save_presets(self._presets)
        self._refresh_preset_combo()
        # Re-select the renamed entry
        new_idx = self.cb_preset.findText(new_name)
        if new_idx > 0:
            self.cb_preset.setCurrentIndex(new_idx)

    def _on_preset_delete(self):
        idx = self._selected_preset_index()
        if idx is None:
            return
        name = self._presets[idx]['name']
        reply = QMessageBox.question(
            self, 'Delete preset',
            f"Delete preset '{name}'? This can't be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        del self._presets[idx]
        save_presets(self._presets)
        self._refresh_preset_combo()
        # Reset to "(no preset selected)" since the selected one just vanished
        self.cb_preset.setCurrentIndex(0)
        self._sync_preset_buttons()
        self._set_status(f"// preset · deleted '{name}'")

    def _snapshot_params(self):
        """Capture the current state of every parameter widget as a flat
        dict. Stores display names (e.g. 'Hann' not 'hann') so presets are
        readable if someone opens the JSON file.

        Note that this is distinct from _collect_params, which produces
        the dict used for compute/render. We need a slightly different
        shape here:
          - includes auto_depth flag (compute doesn't care about it)
          - uses display names for combobox values (round-trippable to UI)
          - doesn't include audio path or sample rate
        """
        return {
            'fft_size':         int(self.cb_nfft.currentText()),
            'hop_div':          int(self.cb_hop.currentText()),
            'window_display':   self.cb_window.currentText(),
            'scale_display':    self.cb_scale.currentText(),
            'f_min':            int(self.r_fmin.value()),
            'f_max':            int(self.r_fmax.value()),
            'db_range':         int(self.r_db.value()),
            'colormap_display': self.cb_cmap.currentText(),
            'gamma':            float(self.r_gamma.value()),
            'floor':            float(self.r_floor.value()),
            'ceiling':          float(self.r_ceiling.value()),
            'invert':           bool(self.cb_invert.isChecked()),
            'form':             self._current_form(),
            'width_mm':         float(self.r_width.value()),
            'depth_mm':         float(self.r_depth.value()),
            'auto_depth':       bool(self.cb_depth_auto.isChecked()),
            'outer_r_mm':       float(self.r_outer.value()),
            'ring_w_mm':        float(self.r_ring_w.value()),
            'max_height_mm':    float(self.r_max_h.value()),
            'base_mm':          float(self.r_base.value()),
            'mesh_res':         int(self.r_res.value()),
        }

    def _apply_preset(self, params):
        """Apply a preset dict to the UI. Order-sensitive: cross-constraint
        rules (f_min<f_max, floor<ceiling, ring_w<outer_r) mean we have to
        set the relaxing direction before the tightening one, or the second
        set_value will fight against bounds left over from the first.

        Also defers expensive cascades (compute, 3D rebuild) until the end
        so we don't fire several recomputes during a single apply.

        Missing keys silently fall back to current values — presets from
        older versions of the app stay usable.
        """
        p = params or {}

        def g(key, default):
            return p.get(key, default)

        # Suppress side-effect compute/render until we've set everything
        was_suppressed = self._suppress_preset_apply
        self._suppress_preset_apply = True

        # === Spectrogram combos (these trigger _schedule_compute on
        # change, which is fine — we'll trigger one ourselves at the end) ===
        if 'fft_size' in p:
            self.cb_nfft.setCurrentText(str(int(g('fft_size', 16384))))
        if 'hop_div' in p:
            self.cb_hop.setCurrentText(str(int(g('hop_div', 16))))
        if 'window_display' in p:
            self.cb_window.setCurrentText(g('window_display', 'Hann'))
        if 'scale_display' in p:
            self.cb_scale.setCurrentText(g('scale_display', 'Log'))

        # === Frequency range: set f_max FIRST (to maximum allowed), then
        # f_min, then f_max to target. This avoids the cross-constraint
        # rejecting the f_max setting. ===
        target_fmin = int(g('f_min', 20))
        target_fmax = int(g('f_max', 22050))
        # Step 1: open the range up to max so neither value is blocked
        self.r_fmax.set_value(24000, notify=True)
        # Step 2: now we can set f_min safely
        self.r_fmin.set_value(target_fmin, notify=True)
        # Step 3: set f_max to its target — constraint allows it
        self.r_fmax.set_value(target_fmax, notify=True)

        if 'db_range' in p:
            self.r_db.set_value(int(g('db_range', 80)))

        # === Display ===
        if 'colormap_display' in p:
            self.cb_cmap.setCurrentText(g('colormap_display', 'Phosphor'))

        # === Contrast: floor<ceiling — set ceiling first to 1.0 to open
        # room, then floor, then ceiling to target ===
        target_floor = float(g('floor', 0.3))
        target_ceiling = float(g('ceiling', 1.0))
        self.r_ceiling.set_value(1.0, notify=True)
        self.r_floor.set_value(target_floor, notify=True)
        self.r_ceiling.set_value(target_ceiling, notify=True)

        if 'gamma' in p:
            self.r_gamma.set_value(float(g('gamma', 1.5)))
        if 'invert' in p:
            self.cb_invert.setChecked(bool(g('invert', False)))

        # === Output: form first, then form-specific values ===
        form = g('form', 'flat')
        if form == 'ring':
            self.btn_ring.setChecked(True)
            self._on_form_change('ring')
        else:
            self.btn_flat.setChecked(True)
            self._on_form_change('flat')

        # Flat-specific
        if 'width_mm' in p:
            self.r_width.set_value(float(g('width_mm', 200.0)))
        if 'depth_mm' in p:
            self.r_depth.set_value(float(g('depth_mm', 100.0)))
        if 'auto_depth' in p:
            self.cb_depth_auto.setChecked(bool(g('auto_depth', True)))

        # Ring-specific: outer_r first (it bounds ring_w)
        target_outer = float(g('outer_r_mm', 50.0))
        target_ring_w = float(g('ring_w_mm', 30.0))
        # Open outer_r to its max, set ring_w, then constrain outer
        self.r_outer.set_value(200.0, notify=True)
        self.r_ring_w.set_value(target_ring_w, notify=True)
        self.r_outer.set_value(target_outer, notify=True)

        if 'max_height_mm' in p:
            self.r_max_h.set_value(float(g('max_height_mm', 25.4)))
        if 'base_mm' in p:
            self.r_base.set_value(float(g('base_mm', 2.0)))
        if 'mesh_res' in p:
            self.r_res.set_value(int(g('mesh_res', 2000)))

        self._suppress_preset_apply = was_suppressed

        # Now trigger ONE compute + render with all the new params at once
        self._update_tri_estimate()
        if self.audio_path:
            self._do_compute()
        elif self.heightmap is not None:
            self._render_2d_preview()
            self._schedule_3d_preview()

    def _build_preview_panel(self, parent_layout):
        # Header with view toggle. Uses SectionLabel for visual consistency
        # with the sidebar section headers — same uppercase amber treatment.
        # padding_top=0 because this header sits at the top of its column;
        # the sidebar sections need top-padding for inter-section breathing
        # room, but the preview header has no section above it.
        head = QHBoxLayout()
        head.setSpacing(0)
        self.preview_header = SectionLabel('preview', padding_top=0)
        head.addWidget(self.preview_header)
        head.addStretch(1)
        self.btn_2d = QPushButton('2D')
        self.btn_2d.setCheckable(True)
        self.btn_2d.setChecked(True)
        self.btn_2d.setFixedWidth(48)
        self.btn_3d = QPushButton('3D')
        self.btn_3d.setCheckable(True)
        self.btn_3d.setFixedWidth(48)
        view_group = QButtonGroup(self)
        view_group.setExclusive(True)
        view_group.addButton(self.btn_2d)
        view_group.addButton(self.btn_3d)
        self.btn_2d.clicked.connect(lambda: self._switch_view(0))
        self.btn_3d.clicked.connect(lambda: self._switch_view(1))
        head.addWidget(self.btn_2d)
        head.addWidget(self.btn_3d)
        parent_layout.addLayout(head)

        # Preview area: stacked widget for 2D/3D, with a busy overlay on top.
        # The overlay is a sibling-child of preview_stack, not stacked in it
        # — it shows on demand via raise_() and start(), independent of which
        # view (2D or 3D) is current.
        preview_container = QWidget()
        # Wrap in a layout so the stack fills the container naturally
        pc_layout = QVBoxLayout(preview_container)
        pc_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_stack = QStackedWidget()
        self.preview_canvas = PreviewCanvas2D(self)
        self.preview_3d = Preview3DViewer()
        self.preview_stack.addWidget(self.preview_canvas)
        self.preview_stack.addWidget(self.preview_3d)
        pc_layout.addWidget(self.preview_stack)

        # Overlay is parented to preview_container, NOT to the layout, so it
        # floats on top rather than being managed by the layout. Synced size
        # to the container via a resize-event filter below.
        self.busy_overlay = BusyOverlay(preview_container)
        self._preview_container = preview_container
        # Install an event filter so we get notified on parent resize
        preview_container.installEventFilter(self)

        parent_layout.addWidget(preview_container, stretch=1)

    # ------------------------------------------------------------------
    # View switching
    # ------------------------------------------------------------------
    def _switch_view(self, index):
        self.preview_stack.setCurrentIndex(index)
        if index == 1 and self.heightmap is not None:
            self._schedule_3d_preview()

    # ------------------------------------------------------------------
    # Auto-compute scheduling
    # ------------------------------------------------------------------
    def _schedule_compute(self):
        if not self._ui_ready or self.audio_path is None:
            return
        self._spec_timer.start()
        self._set_status('// pending recompute…')

    def _schedule_contrast(self):
        if not self._ui_ready:
            return
        self._contrast_timer.start()
        self._schedule_3d_preview()

    def _schedule_3d_preview(self):
        if not self._ui_ready:
            return
        if self.preview_stack.currentIndex() == 1 and self.heightmap is not None:
            self._preview3d_timer.start()

    def _do_compute(self):
        if not self.audio_path:
            return
        if self._compute_worker is not None and self._compute_worker.isRunning():
            try:
                self._compute_worker.abort()
                self._compute_worker.finished_ok.disconnect()
                self._compute_worker.failed.disconnect()
                self._compute_worker.status.disconnect()
            except Exception:
                pass

        self._begin_busy('Computing spectrogram…')
        self._compute_worker = ComputeWorker(
            self.audio_path,
            n_fft=int(self.cb_nfft.currentText()),
            hop_div=int(self.cb_hop.currentText()),
            window=WINDOW_DISPLAY.get(self.cb_window.currentText(), 'hann'),
            scale=SCALE_DISPLAY.get(self.cb_scale.currentText(), 'log'),
            fmin=float(self.r_fmin.value()),
            fmax=float(self.r_fmax.value()),
            db_range=float(self.r_db.value()))
        # Worker status updates flow into both the bottom status bar AND
        # the overlay's centered message so the user sees what's happening
        # without hunting for the small text.
        self._compute_worker.status.connect(self._set_status)
        self._compute_worker.status.connect(self.busy_overlay.set_message)
        self._compute_worker.finished_ok.connect(self._on_compute_done)
        self._compute_worker.failed.connect(self._on_worker_failed)
        self._compute_worker.start()

    def _on_compute_done(self, spec, heightmap, sr, duration):
        self.spec = spec
        self.heightmap = heightmap
        self.sr = sr
        self.duration = duration
        self._render_2d_preview()
        self._update_tri_estimate()
        self._refresh_auto_depth()
        self._end_busy('compute')
        # If the 3D view is active, the next step kicks off a 3D rebuild which
        # has its own busy state. _schedule_3d_preview handles that.
        self._schedule_3d_preview()
        self._set_status(
            f'// ready · {spec.shape[0]}f × {spec.shape[1]}b · '
            f'hm {heightmap.shape[1]}×{heightmap.shape[0]}')
        self._sync_buttons()

    def _on_worker_failed(self, msg):
        self._end_busy('compute')
        self._end_busy('3d')  # safety — any worker can fail
        QMessageBox.critical(self, 'Error', msg)
        self._set_status('// error')
        self._sync_buttons()

    # ------------------------------------------------------------------
    # Busy-state management
    # ------------------------------------------------------------------
    # Multiple operations can run concurrently (e.g. compute finishes and
    # immediately triggers a 3D rebuild). We track active operations by tag
    # and show the overlay while any are running. This avoids race conditions
    # where the overlay flickers between two back-to-back ops.
    def _begin_busy(self, message):
        if not hasattr(self, '_busy_tags'):
            self._busy_tags = set()
        # Use the message itself as a coarse tag if not specified otherwise —
        # but for our use case the explicit tag system below is cleaner.
        # Internally we just show whenever any work is in flight.
        self.busy_overlay.start(message)

    def _end_busy(self, _tag=None):
        # Only hide if nothing else is in flight. Right now we have two
        # concurrent workers: compute and 3d-preview. We hide whenever both
        # are idle.
        compute_running = (self._compute_worker is not None
                           and self._compute_worker.isRunning())
        preview_running = (self._preview3d_worker is not None
                           and self._preview3d_worker.isRunning())
        if not compute_running and not preview_running:
            self.busy_overlay.stop()

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------
    def _sync_buttons(self):
        ready = self.heightmap is not None
        self.btn_stl.setEnabled(ready)
        self.btn_save_png.setEnabled(ready)

    def _set_status(self, msg):
        self.status_label.setText(msg)

    def _on_form_change(self, form):
        if form == 'flat':
            self.btn_flat.setChecked(True)
            self.ring_widget.hide()
            self.flat_widget.show()
        else:
            self.btn_ring.setChecked(True)
            self.flat_widget.hide()
            self.ring_widget.show()
        self._update_tri_estimate()
        self._schedule_3d_preview()

    def _current_form(self):
        return 'flat' if self.btn_flat.isChecked() else 'ring'

    def _on_depth_auto_toggle(self):
        auto = self.cb_depth_auto.isChecked()
        self.r_depth.set_enabled(not auto)
        if auto:
            self._refresh_auto_depth()
        self._schedule_3d_preview()

    def _refresh_auto_depth(self):
        if not self.cb_depth_auto.isChecked():
            return
        if self.heightmap is None:
            return
        cw = self.preview_canvas.width()
        ch = self.preview_canvas.height()
        if cw < 50 or ch < 50:
            cw, ch = PREVIEW_W, PREVIEW_H
        try:
            w = float(self.r_width.value())
        except (TypeError, ValueError):
            return
        self.r_depth.set_value(round(w * ch / cw, 1))

    def _on_cmap_change(self):
        # Combo shows display names ("Magma"); look up internal key ("magma").
        display_name = self.cb_cmap.currentText()
        internal = COLORMAP_DISPLAY.get(display_name, 'phosphor')
        self.lut_view = build_lut(internal)
        # Cascade the colormap's accent color through the UI: update T[],
        # regenerate the QSS, re-apply to the app, then walk and restyle
        # any widgets that snapshotted the accent at construction time.
        apply_theme_accent(internal)
        self._reapply_theme()
        if self.heightmap is not None:
            self._render_2d_preview()
            self._schedule_3d_preview()

    def _reapply_theme(self):
        """Re-apply the QSS stylesheet to the whole app and refresh any
        widgets that hold accent-colored styling outside the QSS.

        QSS templates pull from T[] each time they're evaluated, so a fresh
        make_qss() picks up the new accent. Widgets that set their style
        inline at construction (e.g. SectionLabel) need explicit refresh."""
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(make_qss(self._mono_family))
        # Refresh all SectionLabel instances anywhere in the window tree
        for lbl in self.findChildren(SectionLabel):
            lbl.refresh_color()
        # Invalidate the cached manual dialog — its CSS baked in the old
        # accent. Next _open_manual() will rebuild with current theme.
        if getattr(self, '_manual_dialog', None) is not None:
            self._manual_dialog.close()
            self._manual_dialog = None

    def _update_tri_estimate(self):
        if self.heightmap is None:
            self.tri_estimate.setText(' ')
            return
        H, W = self.heightmap.shape
        target_w = max(1, int(self.r_res.value()))
        factor = max(1, W // target_w)
        ds_w = W // factor
        ds_h = H // factor

        if self._current_form() == 'flat':
            n_top    = 2 * (ds_h - 1) * (ds_w - 1)
            n_walls  = 4 * (ds_h + ds_w)
            n_bottom = 2 * (ds_w + ds_h) - 4
            extra = ''
        else:
            n_top    = 2 * (ds_h - 1) * ds_w
            n_walls  = 2 * 2 * ds_w
            n_bottom = 2 * ds_w
            outer_r = float(self.r_outer.value())
            ring_w = float(self.r_ring_w.value())
            inner_r = outer_r - ring_w
            extra = f' · ⌀{2*outer_r:.0f}/{2*inner_r:.0f}mm'

        total = max(0, n_top + n_walls + n_bottom)
        mb = total * 50 / 1e6
        self.tri_estimate.setText(
            f'-> {ds_w}×{ds_h} · {total/1e6:.2f}M tris · ~{mb:.0f} MB{extra}')

    # ------------------------------------------------------------------
    # 2D preview rendering
    # ------------------------------------------------------------------
    def _render_2d_preview(self):
        if self.heightmap is None:
            return
        try:
            curved = apply_curve(
                self.heightmap,
                gamma=float(self.r_gamma.value()),
                floor=float(self.r_floor.value()),
                ceiling=float(self.r_ceiling.value()),
                invert=self.cb_invert.isChecked())
        except (ValueError, ZeroDivisionError):
            return

        cw = max(10, self.preview_canvas.width())
        ch = max(10, self.preview_canvas.height())
        img = Image.fromarray((curved * 255).astype(np.uint8), mode='L')
        img = img.resize((cw, ch), Image.BOX)
        arr = np.array(img)
        rgb = np.ascontiguousarray(self.lut_view[arr])
        qimg = QImage(rgb.data, cw, ch, cw * 3, QImage.Format.Format_RGB888)
        self._current_pixmap = QPixmap.fromImage(qimg.copy())
        self.preview_canvas.set_pixmap(self._current_pixmap)

    def on_2d_preview_resized(self):
        if self.heightmap is not None:
            self._render_2d_preview()
        self._refresh_auto_depth()

    # ------------------------------------------------------------------
    # 3D preview
    # ------------------------------------------------------------------
    def _do_rebuild_3d(self):
        if self.heightmap is None or not HAVE_PYQTGRAPH:
            return
        if self._preview3d_worker is not None and self._preview3d_worker.isRunning():
            try:
                self._preview3d_worker.finished_ok.disconnect()
                self._preview3d_worker.failed.disconnect()
            except Exception:
                pass
        params = self._collect_params()
        if self.cb_depth_auto.isChecked() and params['form'] == 'flat':
            cw = self.preview_canvas.width()
            ch = self.preview_canvas.height()
            if cw >= 50 and ch >= 50:
                params['depth_mm'] = params['width_mm'] * ch / cw
        # Only show the overlay if the 3D view is the one currently visible.
        # If the user is on the 2D tab, rebuilding the 3D mesh in the
        # background shouldn't pop up an overlay on top of their 2D view.
        if self.preview_stack.currentIndex() == 1:
            self._begin_busy('Building 3D mesh…')
        self._preview3d_worker = Preview3DWorker(
            self.heightmap, params, self.lut_view, PREVIEW_3D_MAX_RES)
        self._preview3d_worker.finished_ok.connect(self._on_3d_done)
        self._preview3d_worker.failed.connect(self._on_worker_failed)
        self._preview3d_worker.start()

    def _on_3d_done(self, verts, faces, colors):
        self.preview_3d.set_mesh(verts, faces, colors)
        self._end_busy('3d')

    # ------------------------------------------------------------------
    # Manual
    # ------------------------------------------------------------------
    def _open_manual(self):
        # Cache the dialog so reopening preserves scroll position
        if self._manual_dialog is None:
            self._manual_dialog = ManualDialog(self, self._mono_family)
        self._manual_dialog.show()
        self._manual_dialog.raise_()
        self._manual_dialog.activateWindow()

    # ------------------------------------------------------------------
    # Audio loading
    # ------------------------------------------------------------------
    def _browse_audio(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Choose audio', '',
            'Audio (*.wav *.flac *.ogg *.oga *.aiff *.aif);;All (*.*)')
        if path:
            self._load_audio_path(path)

    def _load_audio_path(self, path):
        try:
            info = sf.info(path)
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Failed to read audio:\n{e}')
            return
        self.audio_path = path
        info_str = (f'{Path(path).name}  ·  {info.samplerate} Hz  ·  '
                    f'{info.frames/info.samplerate:.2f}s  ·  '
                    f'{info.channels}ch  ·  {info.subtype}')
        self.drop_zone.set_loaded(info_str)
        nyq = info.samplerate // 2
        if self.r_fmax.value() > nyq:
            self.r_fmax.set_value(nyq, notify=True)
        self.spec = None
        self.heightmap = None
        self._current_pixmap = None
        self.preview_canvas.set_pixmap(None)
        self.preview_3d.clear_mesh()
        self._update_tri_estimate()
        self._sync_buttons()
        self._set_status('// loaded · computing…')
        self._do_compute()

    # ------------------------------------------------------------------
    # Parameter collection
    # ------------------------------------------------------------------
    def _collect_params(self):
        return {
            'gamma':         float(self.r_gamma.value()),
            'floor':         float(self.r_floor.value()),
            'ceiling':       float(self.r_ceiling.value()),
            'invert':        self.cb_invert.isChecked(),
            'form':          self._current_form(),
            'width_mm':      float(self.r_width.value()),
            'depth_mm':      float(self.r_depth.value()),
            'outer_radius':  float(self.r_outer.value()),
            'ring_width':    float(self.r_ring_w.value()),
            'max_height_mm': float(self.r_max_h.value()),
            'base_mm':       float(self.r_base.value()),
            'resolution':    int(self.r_res.value()),
        }

    # ------------------------------------------------------------------
    # Save PNG
    # ------------------------------------------------------------------
    def save_preview_png(self):
        if self.heightmap is None:
            return
        win_key = WINDOW_DISPLAY.get(self.cb_window.currentText(), 'hann')
        default_name = (f'{Path(self.audio_path).stem}_'
                        f'{win_key}_preview.png'
                        if self.audio_path else 'preview.png')
        path, _ = QFileDialog.getSaveFileName(
            self, 'Save PNG', default_name,
            'PNG (*.png);;All (*.*)')
        if not path:
            return
        self._png_worker = PngWorker(
            self.heightmap, self._collect_params(), self.lut_view,
            self.preview_canvas.width(), self.preview_canvas.height(), path)
        self._png_worker.status.connect(self._set_status)
        self._png_worker.finished_ok.connect(self._on_png_done)
        self._png_worker.failed.connect(self._on_worker_failed)
        self._png_worker.start()

    def _on_png_done(self, path, w, h):
        self._set_status(f'// saved {Path(path).name} · {w}×{h}')

    # ------------------------------------------------------------------
    # Export STL
    # ------------------------------------------------------------------
    def generate_stl(self):
        if self.heightmap is None:
            return
        params = self._collect_params()
        if self.cb_depth_auto.isChecked() and params['form'] == 'flat':
            cw = self.preview_canvas.width()
            ch = self.preview_canvas.height()
            if cw < 50 or ch < 50:
                cw, ch = PREVIEW_W, PREVIEW_H
            params['depth_mm'] = params['width_mm'] * ch / cw
        win_key = WINDOW_DISPLAY.get(self.cb_window.currentText(), 'hann')
        default_name = (
            f"{Path(self.audio_path).stem}_{win_key}_"
            f"{params['form']}.stl" if self.audio_path else 'spectro.stl')
        path, _ = QFileDialog.getSaveFileName(
            self, 'Export STL', default_name,
            'STL (*.stl);;All (*.*)')
        if not path:
            return
        self.btn_stl.setEnabled(False)
        self.btn_save_png.setEnabled(False)
        self._stl_worker = StlWorker(self.heightmap, params, path)
        self._stl_worker.status.connect(self._set_status)
        self._stl_worker.finished_ok.connect(self._on_stl_done)
        self._stl_worker.failed.connect(self._on_worker_failed)
        self._stl_worker.start()

    def _on_stl_done(self, path, n_tris, footprint):
        self._set_status(
            f'// exported {Path(path).name} · {n_tris:,} tris · {footprint}')
        self._sync_buttons()


# ============================================================================
# Main
# ============================================================================

def main():
    app = QApplication(sys.argv)
    mono_family = pick_mono_font()
    # Force the chosen mono as the default app font as well, so anything not
    # covered by the stylesheet (file dialogs, message boxes) still uses it.
    app.setFont(QFont(mono_family, 10))
    # Apply the default colormap's accent before any styling. The window
    # widgets snapshot T['accent'] at construction, so this needs to land
    # before SpectroStudio() runs.
    apply_theme_accent('phosphor')
    app.setStyleSheet(make_qss(mono_family))
    QToolTip.setFont(QFont(mono_family, 10))
    win = SpectroStudio(mono_family=mono_family)
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
