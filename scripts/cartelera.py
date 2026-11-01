"""Cartelera viva: la última peli que he votado y una playlist al azar.

Lee los datos de wobocobo.com y genera dos SVG para el README: la entrada
de cine de cine.html (cine.svg) y el tocadiscos de spoti.html (vinilo.svg).
Las imágenes van en base64 dentro del SVG, porque GitHub no deja que un
SVG metido como imagen cargue nada de fuera. Solo librería estándar.

    python scripts/cartelera.py [carpeta]   (por defecto, salida/)
"""

import base64
import json
import math
import random
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

RATINGS = 'https://wobocobo.com/data/ratings.json'
PLAYLISTS = 'https://wobocobo.com/data/spoti.json'
WESERV = 'https://images.weserv.nl/?'  # FilmAffinity da 403 al hotlink
OEMBED = 'https://open.spotify.com/oembed?url=https://open.spotify.com/playlist/'
UA = 'wobocobo-cartelera (+https://wobocobo.com)'

FONT = "'Segoe UI',system-ui,-apple-system,Roboto,'Helvetica Neue',Arial,sans-serif"
MONTHS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sept', 'oct', 'nov', 'dic']

# papel y tinta de la entrada: iguales en los dos temas, como en la web
PAPER = '#f3e6cf'
INK = '#2a1d12'
TICKET_RED = '#a8302c'
# tramos de la nota (dorado, verde, ámbar, rojo): fondo del círculo y color del número
TIERS = {
    'top': ('#b8891f', '#8a6512'),
    'good': ('#2c8148', '#1f6a39'),
    'mid': ('#bd6b25', '#96501a'),
    'low': ('#a8302c', '#9a2824'),
}
AMBER = '#e8b45c'


# ---- red ----

def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read()


def fetch_json(url):
    return json.loads(fetch(url).decode('utf-8'))


def fetch_jpeg(src, w, h):
    """Imagen recortada a w×h por weserv, como data URI (None si falla)."""
    query = urllib.parse.urlencode({'url': src, 'w': w, 'h': h, 'fit': 'cover', 'output': 'jpg', 'q': 78})
    try:
        data = fetch(WESERV + query)
    except OSError as e:
        print(f'aviso: sin imagen ({e}): {src}', file=sys.stderr)
        return None
    if not data.startswith(b'\xff\xd8'):
        print(f'aviso: weserv no devolvió un JPEG: {src}', file=sys.stderr)
        return None
    return 'data:image/jpeg;base64,' + base64.b64encode(data).decode('ascii')


# ---- texto ----

def attr(s):
    return escape(str(s), {'"': '&quot;'})


def text_width(s, size, bold=False):
    """Ancho aproximado con una fuente de sistema: basta para recortar."""
    w = 0
    for ch in s:
        if ch in 'il.,:;!|\'’ ':
            w += 0.3
        elif ch in 'fjrtI()-':
            w += 0.4
        elif ch in 'mwMW':
            w += 0.85
        elif ch.isupper() or ch.isdigit():
            w += 0.66
        elif ord(ch) > 0x2000:  # emojis y símbolos
            w += 1.1
        else:
            w += 0.54
    return w * size * (1.06 if bold else 1)


def clip(s, size, width, bold=False):
    if text_width(s, size, bold) <= width:
        return s
    while s and text_width(s + '…', size, bold) > width:
        s = s[:-1]
    return s.rstrip() + '…'


def wrap(s, size, width, lines, bold=False):
    """Parte en líneas por palabras; la última se recorta con «…»."""
    out, cur = [], ''
    words = s.split()
    for i, word in enumerate(words):
        test = f'{cur} {word}'.strip()
        if text_width(test, size, bold) <= width or not cur:
            cur = test
            continue
        out.append(cur)
        cur = word
        if len(out) == lines - 1:
            cur = ' '.join(words[i:])
            break
    out.append(clip(cur, size, width, bold))
    return out


def tier(rating):
    if rating >= 9:
        return 'top'
    if rating >= 7:
        return 'good'
    if rating >= 5:
        return 'mid'
    return 'low'


def decimal(n):
    return f'{n:.1f}'.replace('.', ',')


def spanish_date(iso):
    m = re.fullmatch(r'(\d{4})-(\d{2})-(\d{2})', iso or '')
    if not m:
        return ''
    y, mo, d = (int(g) for g in m.groups())
    return f'{d} {MONTHS[mo - 1]} {y}'


# ---- entrada de cine ----

def ticket_svg(movie, poster):
    W, H, PW = 560, 240, 160  # entrada, alto y ancho del póster (2:3)
    M = 6  # margen para la sombra
    x0 = PW + 20  # texto del papel
    tw = W - x0 - 22
    r_bg, r_fg = TIERS[tier(movie['rating'])]
    title = wrap(movie['title'], 20, tw, 2, bold=True)
    meta = ' · '.join(str(v) for v in (movie.get('year'), movie.get('country')) if v)
    directors = ', '.join(movie.get('directors') or [])
    when = spanish_date(movie.get('ratedAt'))
    label = f"{movie['title']} ({movie['year']})" if movie.get('year') else movie['title']

    t = []
    y = 66
    for line in title:
        t.append(f'<text x="{x0}" y="{y}" font-size="20" font-weight="700" fill="{INK}">{escape(line)}</text>')
        y += 24
    if meta:
        t.append(f'<text x="{x0}" y="{y}" font-size="12.5" font-weight="600" fill="{INK}" fill-opacity=".75">{escape(meta)}</text>')
        y += 21
    if directors:
        lab = 'DIRECCIÓN'
        lw = text_width(lab, 9.5, True) + len(lab) * 0.8 + 6
        t.append(
            f'<text x="{x0}" y="{y}" font-size="12.5" fill="{INK}">'
            f'<tspan font-size="9.5" font-weight="700" letter-spacing=".8" fill="{TICKET_RED}">{lab}</tspan>'
            f'<tspan dx="6">{escape(clip(directors, 12.5, tw - lw))}</tspan></text>'
        )

    # cajas de las notas, abajo como en la web
    scores = []
    boxes = [('MI NOTA', str(movie['rating']), r_fg)]
    if movie.get('avg') is not None:
        boxes.append(('FILMAFFINITY', decimal(movie['avg']), INK))
    for i, (lab, val, color) in enumerate(boxes):
        bx = x0 + i * 128
        scores.append(
            f'<rect x="{bx}" y="146" width="118" height="48" rx="6" fill="none" stroke="{INK}" stroke-opacity=".3" stroke-width="1.5"/>'
            f'<text x="{bx + 59}" y="161" text-anchor="middle" font-size="8.5" font-weight="700" letter-spacing=".7" fill="{INK}" fill-opacity=".65">{lab}</text>'
            f'<text x="{bx + 59}" y="185" text-anchor="middle" font-size="22" font-weight="700" fill="{color}">{escape(val)}</text>'
        )

    stub = [s for s in (when, f"Nº {movie['id']}") if s]
    if poster:
        front = f'<image href="{poster}" width="{PW}" height="{H}" preserveAspectRatio="xMidYMid slice"/>'
    else:
        front = f'<rect width="{PW}" height="{H}" fill="#111a30"/>'

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W + 2 * M}" height="{H + 2 * M}" '
        f'viewBox="0 0 {W + 2 * M} {H + 2 * M}" role="img" aria-label="{attr("La última peli que he votado: " + label)}">'
        f'<title>{escape("La última peli que he votado: " + label)}</title>'
        '<defs>'
        # muescas entre el póster y el papel, arriba y abajo
        f'<mask id="m"><rect width="{W}" height="{H}" rx="10" fill="#fff"/>'
        f'<circle cx="{PW}" cy="0" r="9"/><circle cx="{PW}" cy="{H}" r="9"/></mask>'
        '<pattern id="lines" width="4" height="4" patternUnits="userSpaceOnUse">'
        '<rect width="4" height="1" fill="#000" fill-opacity=".025"/></pattern>'
        '<filter id="sh" x="-5%" y="-5%" width="110%" height="115%">'
        '<feDropShadow dx="0" dy="2" stdDeviation="2.5" flood-color="#000" flood-opacity=".3"/></filter>'
        '<filter id="bs" x="-50%" y="-50%" width="200%" height="200%">'
        '<feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#000" flood-opacity=".45"/></filter>'
        '</defs>'
        f'<g transform="translate({M} {M - 2})" font-family="{attr(FONT)}" filter="url(#sh)"><g mask="url(#m)">'
        f'{front}'
        f'<rect x="{PW}" width="{W - PW}" height="{H}" fill="{PAPER}"/>'
        f'<rect x="{PW}" width="{W - PW}" height="{H}" fill="url(#lines)"/>'
        f'<line x1="{PW}" y1="12" x2="{PW}" y2="{H - 12}" stroke="{INK}" stroke-opacity=".35" stroke-width="1.5" stroke-dasharray="4 4"/>'
        '</g>'
        # nota en el póster
        f'<g filter="url(#bs)"><circle cx="{PW - 25}" cy="25" r="17" fill="{r_bg}" stroke="#fff" stroke-opacity=".85" stroke-width="2"/></g>'
        f'<text x="{PW - 25}" y="30.5" text-anchor="middle" font-size="15" font-weight="700" fill="#fff">{movie["rating"]}</text>'
        # papel
        f'<text x="{x0}" y="30" font-size="10" font-weight="700" letter-spacing="1.6" fill="{TICKET_RED}">ENTRADA · CINE</text>'
        f'<line x1="{x0}" y1="40" x2="{W - 20}" y2="40" stroke="{INK}" stroke-opacity=".35" stroke-width="1.5" stroke-dasharray="5 3"/>'
        + ''.join(t)
        + ''.join(scores)
        + f'<line x1="{x0}" y1="208" x2="{W - 20}" y2="208" stroke="{INK}" stroke-opacity=".35" stroke-width="1.5" stroke-dasharray="5 3"/>'
        f'<text x="{x0}" y="226" font-size="10.5" fill="{INK}" fill-opacity=".7">{escape("   ·   ".join(stub))}</text>'
        '</g></svg>'
    )


# ---- tocadiscos ----

def deck_svg(name, note, cover):
    W, H = 340, 240
    M = 6
    cx, cy, R = 106, 102, 88  # plato
    rr = R * 0.94  # vinilo
    lr = rr * 0.32  # etiqueta

    grooves = ''.join(
        f'<circle r="{r:.1f}" fill="none" stroke="#1f1f25" stroke-width="1.6"/>'
        for r in [rr * 0.37 + i * 2.8 for i in range(int((rr * 0.97 - rr * 0.37) / 2.8))]
    )

    def wedge(a0, a1, opacity):
        p0 = (rr * math.cos(math.radians(a0)), rr * math.sin(math.radians(a0)))
        p1 = (rr * math.cos(math.radians(a1)), rr * math.sin(math.radians(a1)))
        return (
            f'<path d="M0 0L{p0[0]:.1f} {p0[1]:.1f}A{rr:.1f} {rr:.1f} 0 0 1 {p1[0]:.1f} {p1[1]:.1f}Z" '
            f'fill="#fff" fill-opacity="{opacity}"/>'
        )

    if cover:
        label = (
            f'<image href="{cover}" x="{-lr:.1f}" y="{-lr:.1f}" width="{2 * lr:.1f}" height="{2 * lr:.1f}" '
            'clip-path="url(#lab)" preserveAspectRatio="xMidYMid slice"/>'
        )
    else:
        label = f'<circle r="{lr:.1f}" fill="#1db954"/>'

    # brazo: cuelga del pivote y apoya la cápsula en los surcos
    px, py, arm = 290, 36, 150
    sub = f'<tspan font-size="11" fill="#f3e6cf" fill-opacity=".6"> · {escape(clip(note, 11, 120))}</tspan>' if note else ''
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W + 2 * M}" height="{H + 2 * M}" '
        f'viewBox="0 0 {W + 2 * M} {H + 2 * M}" role="img" aria-label="{attr("Una de mis playlists: " + name)}">'
        f'<title>{escape("Una de mis playlists: " + name)}</title>'
        '<style>.rec{animation:spin 1.8s linear infinite;transform-box:fill-box;transform-origin:center}'
        '@keyframes spin{to{transform:rotate(360deg)}}'
        '@media (prefers-reduced-motion:reduce){.rec{animation:none}}</style>'
        '<defs>'
        '<linearGradient id="wood" x1="0" y1="0" x2="1" y2=".55"><stop offset="0" stop-color="#241912"/><stop offset="1" stop-color="#15100c"/></linearGradient>'
        '<radialGradient id="hi" cx=".3" cy=".2" r=".8"><stop offset="0" stop-color="#fff" stop-opacity=".06"/><stop offset=".6" stop-color="#fff" stop-opacity="0"/></radialGradient>'
        '<radialGradient id="plat"><stop offset="0" stop-color="#3a3a3a"/><stop offset=".7" stop-color="#1a1a1a"/></radialGradient>'
        '<radialGradient id="knob" cx=".35" cy=".35" r=".7"><stop offset="0" stop-color="#f0f0f0"/><stop offset="1" stop-color="#8a8a8a"/></radialGradient>'
        '<linearGradient id="metal"><stop offset="0" stop-color="#8f8f8f"/><stop offset=".45" stop-color="#e6e6e6"/><stop offset="1" stop-color="#9a9a9a"/></linearGradient>'
        '<linearGradient id="cart" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3a3a3a"/><stop offset="1" stop-color="#161616"/></linearGradient>'
        f'<clipPath id="lab"><circle r="{lr:.1f}"/></clipPath>'
        '<filter id="sh" x="-10%" y="-10%" width="120%" height="125%">'
        '<feDropShadow dx="0" dy="2" stdDeviation="2.5" flood-color="#000" flood-opacity=".35"/></filter>'
        '<filter id="ps" x="-30%" y="-30%" width="160%" height="170%">'
        '<feDropShadow dx="0" dy="6" stdDeviation="6" flood-color="#000" flood-opacity=".6"/></filter>'
        '<filter id="glow" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="2.5"/></filter>'
        '</defs>'
        f'<g transform="translate({M} {M - 2})" font-family="{attr(FONT)}">'
        f'<g filter="url(#sh)"><rect width="{W}" height="{H}" rx="12" fill="url(#wood)"/></g>'
        f'<rect width="{W}" height="{H}" rx="12" fill="url(#hi)"/>'
        f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="11.5" fill="none" stroke="#fff" stroke-opacity=".06"/>'
        # plato con aros de metal
        f'<g transform="translate({cx} {cy})">'
        f'<g filter="url(#ps)"><circle r="{R + 6}" fill="#6b6b6b"/></g>'
        f'<circle r="{R + 4}" fill="#b8b8b8"/><circle r="{R}" fill="url(#plat)"/>'
        # vinilo: surcos, brillo y la carátula de etiqueta; gira entero
        f'<g class="rec"><circle r="{rr:.1f}" fill="#141418"/>{grooves}'
        f'<circle r="{rr * 0.335:.1f}" fill="none" stroke="#0a0a0c" stroke-width="{rr * 0.015 + 1:.1f}"/>'
        + wedge(-155, -125, 0.1)
        + wedge(25, 55, 0.08)
        + label
        + f'<circle r="{lr * 0.16:.1f}" fill="#b8b8b8"/></g></g>'
        # brazo
        f'<g transform="translate({px} {py}) rotate(45)">'
        f'<g filter="url(#ps)"><rect x="-3" y="0" width="6" height="{arm}" rx="3" fill="url(#metal)"/></g>'
        f'<rect x="-6" y="{arm - 4}" width="12" height="19" rx="3" fill="url(#cart)" transform="rotate(14 0 {arm})"/>'
        '<circle r="11" fill="url(#knob)"/></g>'
        # led encendido
        f'<circle cx="{W - 18}" cy="{H - 18}" r="4" fill="{AMBER}" filter="url(#glow)"/>'
        f'<circle cx="{W - 18}" cy="{H - 18}" r="4" fill="{AMBER}"/>'
        # nombre de la playlist en la madera
        f'<text x="20" y="{H - 30}" font-size="9" font-weight="700" letter-spacing="1.6" fill="{AMBER}">PLAYLIST DEL DÍA</text>'
        f'<text x="20" y="{H - 12}" font-size="15" font-weight="700" fill="#f3e6cf">{escape(clip(name, 15, W - 70, True))}{sub}</text>'
        '</g></svg>'
    )


# ---- main ----

def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else 'salida')
    out.mkdir(parents=True, exist_ok=True)

    movies = fetch_json(RATINGS)
    movie = movies[0]  # la más reciente va primero
    poster = movie.get('poster', '')
    poster = fetch_jpeg(poster, 240, 360) if poster.startswith('https://') else None
    (out / 'cine.svg').write_text(ticket_svg(movie, poster), encoding='utf-8')
    print(f"cine.svg: {movie['title']} ({movie.get('year')})")

    playlists = [p for p in fetch_json(PLAYLISTS) if re.fullmatch(r'[A-Za-z0-9]{22}', p.get('id', ''))]
    random.shuffle(playlists)
    for pl in playlists[:5]:  # si una falla, prueba con otra
        try:
            info = fetch_json(OEMBED + pl['id'])
        except (OSError, ValueError) as e:
            print(f"aviso: oEmbed falló para {pl['id']}: {e}", file=sys.stderr)
            continue
        thumb = info.get('thumbnail_url', '')
        cover = fetch_jpeg(thumb, 128, 128) if thumb.startswith('https://') else None
        name = info.get('title') or pl.get('name') or 'Playlist'
        (out / 'vinilo.svg').write_text(deck_svg(name, pl.get('note'), cover), encoding='utf-8')
        print(f'vinilo.svg: {name}')
        break
    else:
        sys.exit('ninguna playlist respondió al oEmbed')


if __name__ == '__main__':
    main()
