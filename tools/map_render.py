"""
Tavola cartografica degli alberi (PNG o PDF) — vedi next_steps.md, C1.

Nessuna dipendenza GIS e nessun browser sul server: le tessere della basemap
(OpenStreetMap o ortofoto Esri) vengono scaricate con urllib, cucite con
Pillow e ritagliate sull'inquadratura degli alberi; marker, etichette,
perimetro dell'area, legenda, barra di scala e freccia del nord sono disegnati
sopra. Il PDF è la stessa immagine impaginata su A4 (Pillow scrive PDF
nativamente, con JPEG interno), così un'unica pipeline serve entrambi i formati.

Il modulo non conosce il dominio: riceve punti già colorati e le voci della
legenda già contate (vedi report_map() in app.py).
"""
import io
import math
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

BASEMAPS = {
    'osm': {
        'label': 'OpenStreetMap',
        'url': 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
        'max_zoom': 19,
        'attribution': '© OpenStreetMap contributors',
    },
    'satellite': {
        'label': 'Ortofoto (Esri World Imagery)',
        'url': 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        'max_zoom': 19,
        'attribution': '© Esri, Maxar, Earthstar Geographics',
    },
}
FORMATS = {'png': 'image/png', 'pdf': 'application/pdf'}

# OSM richiede uno User-Agent identificativo per l'uso da server.
USER_AGENT = 'SilvaePro-MapExport/1.0'
TILE = 256
TILE_TIMEOUT_S = 12
TILE_WORKERS = 8

DPI = 250                       # A4 a 250 dpi: ~2900×2070 px, buona per la stampa
A4_MM = (210.0, 297.0)
MARGIN_MM = 10.0
PAD_FRACTION = 0.12             # margine attorno agli alberi nell'inquadratura
MIN_EXTENT_M = 80.0             # inquadratura minima (un solo albero, area piccolissima)
OVERZOOM = 2                    # livelli oltre lo zoom nativo, ingrandendo le tessere (come la webapp)
MAX_LABELS = 200                # oltre questo numero di alberi le etichette ID vengono omesse

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts')
POLYGON_COLOR = (26, 82, 118)   # #1a5276, lo stesso della selezione per area sulla mappa web


# ─── Geometria Web Mercator ───────────────────────────────

def _mm(v):
    """Millimetri → pixel alla risoluzione della tavola."""
    return int(round(v / 25.4 * DPI))

def _pt(v):
    """Punti tipografici → pixel."""
    return int(round(v / 72.0 * DPI))

def _lonlat_to_px(lon, lat, z):
    """Coordinate → pixel globali (tessere da 256 px) allo zoom z."""
    n = TILE * (2 ** z)
    x = (lon + 180.0) / 360.0 * n
    lat_r = math.radians(max(-85.05, min(85.05, lat)))
    y = (1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n
    return x, y

def _meters_per_px(lat, z):
    return 156543.03392 * math.cos(math.radians(lat)) / (2 ** z)

def _bbox(points, polygon):
    lats = [p['lat'] for p in points] + [v[0] for v in (polygon or [])]
    lons = [p['lon'] for p in points] + [v[1] for v in (polygon or [])]
    lat0, lat1, lon0, lon1 = min(lats), max(lats), min(lons), max(lons)
    # Inquadratura minima, così un albero isolato non finisce su una mappa "vuota"
    lat_c = (lat0 + lat1) / 2
    min_dlat = MIN_EXTENT_M / 111320.0
    min_dlon = MIN_EXTENT_M / (111320.0 * max(0.05, math.cos(math.radians(lat_c))))
    if lat1 - lat0 < min_dlat:
        lat0, lat1 = lat_c - min_dlat / 2, lat_c + min_dlat / 2
    if lon1 - lon0 < min_dlon:
        lon_c = (lon0 + lon1) / 2
        lon0, lon1 = lon_c - min_dlon / 2, lon_c + min_dlon / 2
    return lat0, lat1, lon0, lon1

def _fit_zoom(bbox, map_w, map_h, max_zoom):
    """Zoom (frazionario) a cui il bbox con il suo margine riempie l'area
    mappa; al massimo OVERZOOM livelli oltre lo zoom nativo delle tessere."""
    lat0, lat1, lon0, lon1 = bbox
    x0, y1 = _lonlat_to_px(lon0, lat0, 0)
    x1, y0 = _lonlat_to_px(lon1, lat1, 0)
    w = max(1e-9, (x1 - x0) * (1 + 2 * PAD_FRACTION))
    h = max(1e-9, (y1 - y0) * (1 + 2 * PAD_FRACTION))
    z = min(math.log2(map_w / w), math.log2(map_h / h))
    return max(1.0, min(float(max_zoom + OVERZOOM), z))


# ─── Tessere ──────────────────────────────────────────────

@lru_cache(maxsize=512)
def _fetch_tile(basemap, z, x, y):
    """Bytes della tessera, o None se non disponibile. Cache in memoria per
    processo: le tavole ripetute sulla stessa zona non rifanno le richieste."""
    if y < 0 or y >= 2 ** z:
        return None
    x = x % (2 ** z)
    url = BASEMAPS[basemap]['url'].format(z=z, x=x, y=y)
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TILE_TIMEOUT_S) as resp:
            return resp.read()
    except Exception:
        return None

def _tile_image(basemap, z, x, y, depth=0):
    """Tessera come immagine RGB 256×256. Se manca (l'ortofoto non copre tutto
    ai livelli alti, o la richiesta fallisce) si ingrandisce il quadrante
    corrispondente della tessera padre, fino a tre livelli più su."""
    blob = _fetch_tile(basemap, z, x, y)
    if blob:
        try:
            return Image.open(io.BytesIO(blob)).convert('RGB')
        except Exception:
            pass
    if z <= 0 or depth >= 3:
        return None
    parent = _tile_image(basemap, z - 1, x // 2, y // 2, depth + 1)
    if parent is None:
        return None
    half = TILE // 2
    qx, qy = (x % 2) * half, (y % 2) * half
    return parent.crop((qx, qy, qx + half, qy + half)).resize((TILE, TILE), Image.BICUBIC)

def _basemap_image(basemap, z, px0, py0, w, h):
    """Immagine RGB w×h della basemap con angolo in alto a sinistra nel pixel
    globale (px0, py0) allo zoom z (anche frazionario): le tessere del livello
    nativo più vicino per difetto vengono cucite e riscalate."""
    zn = min(int(math.floor(z)), BASEMAPS[basemap]['max_zoom'])
    scale = 2 ** (z - zn)          # > 1: le tessere native vengono ingrandite
    # Finestra nel sistema di pixel del livello nativo
    nx0, ny0 = px0 / scale, py0 / scale
    nx1, ny1 = (px0 + w) / scale, (py0 + h) / scale
    tx0, ty0 = int(math.floor(nx0 / TILE)), int(math.floor(ny0 / TILE))
    tx1, ty1 = int(math.floor((nx1 - 1e-6) / TILE)), int(math.floor((ny1 - 1e-6) / TILE))

    coords = [(tx, ty) for ty in range(ty0, ty1 + 1) for tx in range(tx0, tx1 + 1)]
    with ThreadPoolExecutor(max_workers=TILE_WORKERS) as ex:
        tiles = list(ex.map(lambda c: _tile_image(basemap, zn, c[0], c[1]), coords))

    mosaic = Image.new('RGB', ((tx1 - tx0 + 1) * TILE, (ty1 - ty0 + 1) * TILE), (232, 232, 232))
    for (tx, ty), tile in zip(coords, tiles):
        if tile is not None:
            mosaic.paste(tile, ((tx - tx0) * TILE, (ty - ty0) * TILE))

    # Ritaglio sulla finestra (in pixel nativi) e ingrandimento a w×h
    cx0, cy0 = nx0 - tx0 * TILE, ny0 - ty0 * TILE
    crop = mosaic.crop((int(round(cx0)), int(round(cy0)),
                        int(round(cx0 + w / scale)), int(round(cy0 + h / scale))))
    if crop.size != (w, h):
        crop = crop.resize((w, h), Image.BICUBIC)
    return crop


# ─── Disegno ──────────────────────────────────────────────

def _font(size_pt, bold=False):
    path = os.path.join(FONT_DIR, 'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')
    px = _pt(size_pt)
    try:
        return ImageFont.truetype(path, px)
    except Exception:
        return ImageFont.load_default(size=px)

def _hex_rgb(color):
    c = color.lstrip('#')
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))

def _text_w(draw, text, font):
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    return r - l

def _nice_scale_m(m_per_px, max_px):
    """Lunghezza "tonda" in metri della barra di scala, la più lunga che sta in max_px."""
    for m in (5000, 2000, 1000, 500, 200, 100, 50, 20, 10, 5, 2, 1):
        if m / m_per_px <= max_px:
            return m
    return 1

def _draw_scale_bar(draw, map_box, m_per_px):
    x0, y0, x1, y1 = map_box
    meters = _nice_scale_m(m_per_px, (x1 - x0) / 5)
    bar_px = int(round(meters / m_per_px))
    font = _font(7)
    label = f'{meters} m' if meters < 1000 else f'{meters / 1000:g} km'
    h = _mm(1.6)
    pad = _mm(1.5)
    bx = x0 + _mm(4)
    by = y1 - _mm(4) - h
    box_w = max(bar_px, _text_w(draw, label, font)) + 2 * pad
    box_h = h + _pt(7) + 3 * pad
    _translucent_box(draw, (bx - pad, by - _pt(7) - 2 * pad, bx - pad + box_w, by + h + pad))
    # Barra bicolore in due segmenti
    half = bar_px // 2
    draw.rectangle((bx, by, bx + half, by + h), fill=(0, 0, 0), outline=(0, 0, 0))
    draw.rectangle((bx + half, by, bx + bar_px, by + h), fill=(255, 255, 255), outline=(0, 0, 0), width=2)
    draw.text((bx, by - _pt(7) - pad // 2), label, fill=(0, 0, 0), font=font)

def _draw_north(draw, map_box):
    x0, y0, x1, y1 = map_box
    r = _mm(5)
    cx, cy = x1 - _mm(5) - r, y0 + _mm(5) + r
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 220), outline=(60, 60, 60), width=2)
    a = r * 0.62
    draw.polygon([(cx, cy - a), (cx - a * 0.4, cy + a * 0.45), (cx, cy + a * 0.15)], fill=(40, 40, 40))
    draw.polygon([(cx, cy - a), (cx + a * 0.4, cy + a * 0.45), (cx, cy + a * 0.15)], fill=(150, 150, 150))
    font = _font(6, bold=True)
    draw.text((cx - _text_w(draw, 'N', font) / 2, cy + a * 0.35), 'N', fill=(40, 40, 40), font=font)

def _translucent_box(draw, box):
    draw.rectangle(box, fill=(255, 255, 255, 215), outline=(200, 200, 200))

def _draw_legend(draw, x, y, width, legend):
    """Legenda a gruppi, con le voci in riga (a capo se non ci stanno).
    Restituisce la y sotto l'ultima riga."""
    title_f, item_f = _font(8, bold=True), _font(8)
    dot_r = _mm(1.3)
    row_h = _pt(8) + _mm(2.2)
    gap = _mm(6)
    groups = []
    for e in legend:
        if not groups or groups[-1][0] != e['group']:
            groups.append((e['group'], []))
        groups[-1][1].append(e)
    for gname, entries in groups:
        cx = x
        if gname:
            draw.text((cx, y), gname, fill=(60, 60, 60), font=title_f)
            cx += _text_w(draw, gname, title_f) + gap
        for e in entries:
            label = f"{e['label']}  {e['count']}"
            item_w = 2 * dot_r + _mm(1.5) + _text_w(draw, label, item_f)
            if cx + item_w > x + width and cx > x:
                cx = x + _mm(4)
                y += row_h
            cy = y + _pt(8) // 2 + _mm(0.3)
            draw.ellipse((cx, cy - dot_r, cx + 2 * dot_r, cy + dot_r),
                         fill=_hex_rgb(e['color']), outline=(255, 255, 255), width=2)
            draw.text((cx + 2 * dot_r + _mm(1.5), y), label, fill=(30, 30, 30), font=item_f)
            cx += item_w + gap
        y += row_h
    return y

def _legend_height(legend):
    """Altezza stimata della legenda: una riga per gruppo (più eventuali a capo,
    che vengono assorbiti dal margine)."""
    groups = len({e['group'] for e in legend})
    return groups * (_pt(8) + _mm(2.2)) + _mm(2)


# ─── Tavola ───────────────────────────────────────────────

def render(points, polygon=None, basemap='osm', fmt='pdf',
           title='', subtitle='', legend=None, footer=''):
    """Compone la tavola e restituisce (bytes, mimetype).

    points:   [{'lat','lon','label','color'}], color esadecimale '#rrggbb'
    polygon:  [(lat, lon), ...] perimetro dell'area selezionata, opzionale
    legend:   [{'group','label','color','count'}] nell'ordine di stampa
    """
    if basemap not in BASEMAPS:
        raise ValueError(f'basemap sconosciuta: {basemap}')
    if fmt not in FORMATS:
        raise ValueError(f'formato sconosciuto: {fmt}')
    if not points:
        raise ValueError('nessun punto da disegnare')
    legend = legend or []

    # Orientamento: quello che segue la forma dell'inquadratura
    bbox = _bbox(points, polygon)
    ax0, ay1 = _lonlat_to_px(bbox[2], bbox[0], 18)
    ax1, ay0 = _lonlat_to_px(bbox[3], bbox[1], 18)
    landscape = (ax1 - ax0) > (ay1 - ay0)
    page_w, page_h = (_mm(A4_MM[1]), _mm(A4_MM[0])) if landscape else (_mm(A4_MM[0]), _mm(A4_MM[1]))

    margin = _mm(MARGIN_MM)
    header_h = _pt(14) + _pt(9) + _mm(5)
    legend_h = _legend_height(legend) if legend else 0
    footer_h = _pt(7) + _mm(2)
    map_x0, map_y0 = margin, margin + header_h
    map_w = page_w - 2 * margin
    map_h = page_h - map_y0 - legend_h - footer_h - margin - _mm(3)
    map_box = (map_x0, map_y0, map_x0 + map_w, map_y0 + map_h)

    max_zoom = BASEMAPS[basemap]['max_zoom']
    z = _fit_zoom(bbox, map_w, map_h, max_zoom)
    lat_c = (bbox[0] + bbox[1]) / 2
    lon_c = (bbox[2] + bbox[3]) / 2
    cx, cy = _lonlat_to_px(lon_c, lat_c, z)
    px0, py0 = cx - map_w / 2, cy - map_h / 2

    def to_xy(lat, lon):
        x, y = _lonlat_to_px(lon, lat, z)
        return map_x0 + (x - px0), map_y0 + (y - py0)

    page = Image.new('RGB', (page_w, page_h), (255, 255, 255))
    page.paste(_basemap_image(basemap, z, px0, py0, map_w, map_h), (map_x0, map_y0))

    # Livello RGBA per tutto ciò che è semitrasparente (area, riquadri)
    overlay = Image.new('RGBA', page.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    if polygon and len(polygon) >= 3:
        pts = [to_xy(lat, lon) for lat, lon in polygon]
        od.polygon(pts, fill=POLYGON_COLOR + (30,))
        od.line(pts + [pts[0]], fill=POLYGON_COLOR + (255,), width=max(2, _mm(0.5)), joint='curve')

    n = len(points)
    r = _mm(1.5) if n <= MAX_LABELS else (_mm(1.0) if n <= 1000 else _mm(0.7))
    outline_w = max(1, _mm(0.25))
    for p in points:
        x, y = to_xy(p['lat'], p['lon'])
        od.ellipse((x - r, y - r, x + r, y + r), fill=_hex_rgb(p['color']) + (235,),
                   outline=(255, 255, 255, 255), width=outline_w)
    if n <= MAX_LABELS:
        lf = _font(6.5)
        lh = _pt(6.5)
        for p in points:
            if not p.get('label'):
                continue
            x, y = to_xy(p['lat'], p['lon'])
            od.text((x + r + _mm(0.7), y - lh / 2 - _mm(0.3)), str(p['label']), font=lf,
                    fill=(20, 20, 20, 255), stroke_width=max(2, _mm(0.2)), stroke_fill=(255, 255, 255, 255))

    _draw_scale_bar(od, map_box, _meters_per_px(lat_c, z))
    _draw_north(od, map_box)

    attr = BASEMAPS[basemap]['attribution']
    af = _font(5.5)
    aw = _text_w(od, attr, af)
    ah = _pt(5.5)
    _translucent_box(od, (map_box[2] - aw - _mm(2.5), map_box[3] - ah - _mm(1.6), map_box[2], map_box[3]))
    od.text((map_box[2] - aw - _mm(1.3), map_box[3] - ah - _mm(1.0)), attr, fill=(70, 70, 70), font=af)

    page = Image.alpha_composite(page.convert('RGBA'), overlay).convert('RGB')
    d = ImageDraw.Draw(page)
    d.rectangle(map_box, outline=(120, 120, 120), width=2)

    # Intestazione
    d.text((margin, margin), title, fill=(20, 20, 20), font=_font(14, bold=True))
    d.text((margin, margin + _pt(14) + _mm(1.5)), subtitle, fill=(90, 90, 90), font=_font(9))

    # Legenda e piè di pagina
    y = map_box[3] + _mm(3)
    if legend:
        y = _draw_legend(d, margin, y, map_w, legend)
    d.text((margin, page_h - margin - _pt(7)), footer, fill=(130, 130, 130), font=_font(7))

    buf = io.BytesIO()
    if fmt == 'png':
        page.save(buf, 'PNG', dpi=(DPI, DPI), optimize=True)
    else:
        page.save(buf, 'PDF', resolution=DPI, quality=88)
    return buf.getvalue(), FORMATS[fmt]
