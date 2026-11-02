"""Adivina la peli: el juego del README.

Cada ronda es una peli muy votada de mis votos en wobocobo.com con tres
señuelos del mismo decenio, con algún género en común e igual de conocidos.
Se juega abriendo un issue «Adivina la peli: A» (… «D») desde los botones
del README. Cada fallo aclara el póster y suma una pista; al sexto se
revela y empieza otra ronda.

El estado vive en estado.json de la rama «juego», junto a las imágenes. La
respuesta no está en claro: solo su HMAC con el secreto del repo
(JUEGO_SECRETO). Lo que escribe el jugador (título del issue, usuario) son
datos: se leen de la API y se escapan al pintarlos. Solo librería estándar.

    python scripts/juego.py juega <carpeta>     repasa los issues abiertos del juego
    python scripts/juego.py nueva <carpeta>     empieza otra ronda (workflow_dispatch)
    python scripts/juego.py contesta <carpeta>  comenta y cierra lo ya jugado
"""

import hashlib
import hmac
import json
import os
import random
import re
import secrets
import sys
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

from cartelera import FONT, RATINGS, attr, clip, decimal, fetch_json, fetch_jpeg, text_width, wrap

PREFIX = 'Adivina la peli:'
TITLE_RE = re.compile(r'Adivina la peli: ([ABCD])')
LETTERS = 'ABCD'
MIN_VOTES = 50_000
MAX_FAILS = 6
PIXELS = [10, 14, 20, 28, 40, 60]  # ancho del póster según los fallos
KEEP_DONE = 200  # issues ya jugados que se recuerdan, por si hay que reintentar la respuesta

API = 'https://api.github.com'
UA = 'wobocobo-juego (+https://wobocobo.com)'
PROFILE = 'https://github.com/wobocobo'

# colores de la web (tema oscuro): la tarjeta es un objeto, igual en los dos temas
BG = '#0e1526'
SURFACE = '#111a30'
BORDER = '#1e2a47'
BORDER_MID = '#33456e'
TEXT = '#f2f6fc'
BODY = '#dce5f2'
MUTED = '#93a3c4'
ACCENT = '#45c7ff'
ON_ACCENT = '#04283c'

rng = random.SystemRandom()


# ---- rondas ----

def playable(m):
    return (
        (m.get('votes') or 0) >= MIN_VOTES
        and str(m.get('poster', '')).startswith('https://')
        and m.get('year')
        and m.get('genres')
        and 'Serie de TV' not in m['genres']
    )


def seal(secret, state, letter):
    msg = f"{state['ronda']}:{state['nonce']}:{letter}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def answer(secret, state, by_id):
    """La opción buena (letra y peli), o None si el secreto no cuadra."""
    for i, letter in enumerate(LETTERS):
        if hmac.compare_digest(seal(secret, state, letter), state['sello']):
            return letter, by_id.get(state['opciones'][i]['id'])
    return None


def new_round(state, movies, secret):
    pool = [m for m in movies if playable(m)]
    seen = set(state.get('vistas', []))
    fresh = [m for m in pool if m['id'] not in seen]
    if not fresh:  # se han jugado todas: vuelta a empezar
        state['vistas'] = []
        fresh = pool
    rng.shuffle(fresh)
    for movie in fresh:
        decoys = [
            o for o in pool
            if o['id'] != movie['id']
            and o['year'] // 10 == movie['year'] // 10
            and set(o['genres']) & set(movie['genres'])
            and o['title'] != movie['title']
        ]
        if len({o['title'] for o in decoys}) >= 3:
            break
    else:
        sys.exit('no hay ninguna peli con tres señuelos')
    picked = []
    for o in rng.sample(decoys, len(decoys)):
        if o['title'] not in {p['title'] for p in picked}:
            picked.append(o)
        if len(picked) == 3:
            break
    options = picked + [movie]
    rng.shuffle(options)
    state.update(
        ronda=state.get('ronda', 0) + 1,
        nonce=secrets.token_hex(8),
        opciones=[{'id': o['id'], 'title': o['title']} for o in options],
        fallos=0,
        jugadores=[],
    )
    state['sello'] = seal(secret, state, LETTERS[options.index(movie)])


def end_round(state, movie, winner):
    """Guarda la peli de la ronda que acaba (ya se puede ver) para el marcador."""
    poster = fetch_jpeg(movie['poster'], 80, 120)
    state['anterior'] = {
        'title': movie['title'],
        'year': movie.get('year'),
        'ganador': winner,
        'poster': poster,
    }
    state.setdefault('vistas', []).append(movie['id'])


def clues(movie):
    """Pistas en orden: las dos primeras desde el principio, luego una por fallo."""
    cast = movie.get('cast') or []
    out = [
        ('AÑO', str(movie.get('year') or '?')),
        ('GÉNEROS', ' · '.join(movie.get('genres') or [])),
        ('DIRECCIÓN', ', '.join(movie.get('directors') or []) or '?'),
        ('PROTAGONISTA', cast[0] if cast else '?'),
        ('PAÍS', movie.get('country') or '?'),
        ('REPARTO', ', '.join(cast[1:3]) or '?'),
    ]
    notes = f"FA {decimal(movie['avg'])}" if movie.get('avg') is not None else ''
    notes += f" · yo le puse un {movie['rating']}" if movie.get('rating') else ''
    out.append(('NOTAS', notes.strip(' ·') or '?'))
    return out


def play(state, issue, movies, by_id, secret):
    """Un intento. Devuelve la respuesta y el motivo de cierre del issue."""
    login = issue['user']['login']
    m = TITLE_RE.fullmatch(issue['title'])
    if not m:
        return (
            'No entiendo este intento: el título tiene que ser exactamente «Adivina la peli: A» '
            f'(o B, C, D). Usa los botones de {PROFILE} y envíalo tal cual.',
            'not_planned',
        )
    if login.lower() in state['jugadores']:
        return f"Ya has probado en la ronda {state['ronda']}: un intento por persona y ronda. ¡Suerte en la siguiente!", 'not_planned'

    found = answer(secret, state, by_id)
    if not found:
        sys.exit('el secreto no cuadra con la ronda: lanza una ronda nueva a mano')
    letter, movie = found
    if movie is None:  # ya no está en mis votos: se cierra la ronda sin más
        new_round(state, movies, secret)
        return f'Esa ronda se ha quedado sin peli. Ya hay otra en {PROFILE}: prueba de nuevo.', 'not_planned'

    guess = state['opciones'][LETTERS.index(m.group(1))]['title']
    name = f"**{movie['title']}** ({movie['year']})"
    if m.group(1) == letter:
        hits = state.setdefault('aciertos', {})
        hits[login] = hits.get(login, 0) + 1
        n = hits[login]
        end_round(state, movie, login)
        new_round(state, movies, secret)
        return (
            f"🎉 ¡Acierto! Era {name}. Llevas {n} {'acierto' if n == 1 else 'aciertos'}. "
            f'Ya hay ronda nueva en {PROFILE}.',
            'completed',
        )

    state['fallos'] += 1
    state['jugadores'].append(login.lower())
    if state['fallos'] >= MAX_FAILS:
        end_round(state, movie, None)
        new_round(state, movies, secret)
        return (
            f'No era «{guess}». Con este van {MAX_FAILS} fallos, así que se revela: era {name}. '
            f'Ya hay ronda nueva en {PROFILE}.',
            'completed',
        )
    label, value = clues(movie)[state['fallos'] + 1]
    return (
        f"No es «{guess}». Fallos: {state['fallos']} de {MAX_FAILS}. "
        f'Nueva pista: {label.capitalize()}, {value}. El póster ya se ve un poco mejor en {PROFILE}.',
        'completed',
    )


# ---- GitHub ----

def api(method, path, body=None):
    req = urllib.request.Request(
        API + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            'Authorization': f"Bearer {os.environ['GITHUB_TOKEN']}",
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
            'User-Agent': UA,
        },
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read() or 'null')


def open_issues():
    """Issues abiertos del juego, del más antiguo al más nuevo."""
    repo = os.environ['GITHUB_REPOSITORY']
    out = []
    for page in range(1, 6):
        batch = api('GET', f'/repos/{repo}/issues?state=open&sort=created&direction=asc&per_page=100&page={page}')
        out += [i for i in batch if 'pull_request' not in i and i['title'].startswith(PREFIX)]
        if len(batch) < 100:
            break
    return out


# ---- imágenes ----

def board_svg(state, movie):
    W, H, M = 888, 252, 6
    fails = state['fallos']
    px = PIXELS[min(fails, len(PIXELS) - 1)]
    pixel = fetch_jpeg(movie['poster'], px, round(px * 1.5)) if movie else None
    shown = clues(movie) if movie else []

    rows = []
    y = 100
    for i, (label, value) in enumerate(shown):
        open_ = i < fails + 2
        rows.append(
            f'<text x="196" y="{y}" font-size="9.5" font-weight="700" letter-spacing="1.2" fill="{MUTED}">{label}</text>'
        )
        if open_:
            rows.append(f'<text x="300" y="{y}" font-size="13" fill="{BODY}">{escape(clip(value, 13, 300))}</text>')
        else:
            n = i - 1
            rows.append(
                f'<text x="300" y="{y}" font-size="12" fill="{MUTED}" fill-opacity=".55">'
                f"con {n} {'fallo' if n == 1 else 'fallos'}</text>"
            )
        y += 18

    dots = ''.join(
        f'<circle cx="{202 + i * 16}" cy="232" r="5" fill="{"#a8302c" if i < fails else "none"}" stroke="{BORDER_MID}" stroke-width="1.5"/>'
        for i in range(MAX_FAILS)
    )

    hits = sorted(state.get('aciertos', {}).items(), key=lambda kv: (-kv[1], kv[0].lower()))[:5]
    board = []
    y = 64
    for i, (login, n) in enumerate(hits):
        board.append(
            f'<text x="640" y="{y}" font-size="12.5" fill="{BODY}"><tspan fill="{MUTED}">{i + 1}.</tspan> '
            f'@{escape(clip(login, 12.5, 150))}</text>'
            f'<text x="866" y="{y}" text-anchor="end" font-size="12.5" font-weight="700" fill="{ACCENT}">{n}</text>'
        )
        y += 19
    if not hits:
        board.append(f'<text x="640" y="64" font-size="12" fill="{MUTED}">Aún no ha acertado nadie.</text>')

    prev = state.get('anterior')
    last = ''
    if prev:
        who = f"la acertó @{prev['ganador']}" if prev.get('ganador') else 'nadie la acertó'
        img = (
            f'<image href="{prev["poster"]}" x="640" y="176" width="40" height="60" preserveAspectRatio="xMidYMid slice" clip-path="url(#pc)"/>'
            if prev.get('poster')
            else f'<rect x="640" y="176" width="40" height="60" rx="4" fill="{SURFACE}"/>'
        )
        title = wrap(prev['title'], 12.5, 180, 2, bold=True)
        last = (
            f'<text x="640" y="166" font-size="9.5" font-weight="700" letter-spacing="1.2" fill="{MUTED}">RONDA ANTERIOR</text>'
            + img
            + ''.join(
                f'<text x="690" y="{190 + i * 16}" font-size="12.5" font-weight="700" fill="{TEXT}">{escape(t)}</text>'
                for i, t in enumerate(title)
            )
            + f'<text x="690" y="{190 + len(title) * 16}" font-size="11.5" fill="{MUTED}">'
            f"{escape(str(prev.get('year') or ''))} · {escape(who)}</text>"
        )

    poster = (
        f'<image href="{pixel}" x="24" y="21" width="140" height="210" preserveAspectRatio="xMidYMid slice" '
        'style="image-rendering:pixelated" image-rendering="optimizeSpeed" clip-path="url(#pp)"/>'
        if pixel
        else f'<rect x="24" y="21" width="140" height="210" rx="8" fill="{SURFACE}"/>'
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W + 2 * M}" height="{H + 2 * M}" '
        f'viewBox="0 0 {W + 2 * M} {H + 2 * M}" role="img" aria-label="Adivina la peli: ronda {state["ronda"]}">'
        f'<title>Adivina la peli: ronda {state["ronda"]}</title>'
        '<defs>'
        '<clipPath id="pp"><rect x="24" y="21" width="140" height="210" rx="8"/></clipPath>'
        '<clipPath id="pc"><rect x="640" y="176" width="40" height="60" rx="4"/></clipPath>'
        '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#111a30"/><stop offset="1" stop-color="#0a0f1e"/></linearGradient>'
        '<filter id="sh" x="-5%" y="-5%" width="110%" height="115%">'
        '<feDropShadow dx="0" dy="2" stdDeviation="2.5" flood-color="#000" flood-opacity=".3"/></filter>'
        '</defs>'
        f'<g transform="translate({M} {M - 2})" font-family="{attr(FONT)}">'
        f'<g filter="url(#sh)"><rect width="{W}" height="{H}" rx="14" fill="url(#bg)"/></g>'
        f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="13.5" fill="none" stroke="{BORDER}"/>'
        + poster
        + f'<rect x="24" y="21" width="140" height="210" rx="8" fill="none" stroke="{BORDER_MID}"/>'
        f'<text x="196" y="44" font-size="10" font-weight="700" letter-spacing="1.6" fill="{ACCENT}">'
        f'ADIVINA LA PELI · RONDA {state["ronda"]}</text>'
        f'<text x="196" y="74" font-size="24" font-weight="700" fill="{TEXT}">¿Qué peli es?</text>'
        + ''.join(rows)
        + dots
        + f'<text x="{202 + MAX_FAILS * 16}" y="236" font-size="11.5" fill="{MUTED}">'
        f'{fails} de {MAX_FAILS} fallos · elige abajo, un intento por persona</text>'
        f'<line x1="616" y1="24" x2="616" y2="{H - 24}" stroke="{BORDER}" stroke-width="1.5"/>'
        f'<text x="640" y="44" font-size="9.5" font-weight="700" letter-spacing="1.2" fill="{MUTED}">MARCADOR</text>'
        + ''.join(board)
        + last
        + '</g></svg>'
    )


def option_svg(letter, title):
    W, H, M = 208, 52, 4
    lines = wrap(title, 13, W - 64, 2, bold=True)
    y0 = H / 2 + 4.5 - (len(lines) - 1) * 8
    text = ''.join(
        f'<text x="54" y="{y0 + i * 16:.1f}" font-size="13" font-weight="700" fill="{TEXT}">{escape(t)}</text>'
        for i, t in enumerate(lines)
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W + 2 * M}" height="{H + 2 * M}" '
        f'viewBox="0 0 {W + 2 * M} {H + 2 * M}" role="img" aria-label="{attr(f"Opción {letter}: {title}")}">'
        f'<title>{escape(f"Opción {letter}: {title}")}</title>'
        f'<g transform="translate({M} {M})" font-family="{attr(FONT)}">'
        f'<rect width="{W}" height="{H}" rx="12" fill="{SURFACE}" stroke="{BORDER_MID}" stroke-width="1.5"/>'
        f'<circle cx="27" cy="{H / 2}" r="15" fill="{ACCENT}"/>'
        f'<text x="27" y="{H / 2 + 5.5}" text-anchor="middle" font-size="16" font-weight="800" fill="{ON_ACCENT}">{letter}</text>'
        + text
        + '</g></svg>'
    )


def render(folder, state, movie):
    (folder / 'juego.svg').write_text(board_svg(state, movie), encoding='utf-8')
    for letter, opt in zip(LETTERS, state['opciones']):
        (folder / f'opcion-{letter.lower()}.svg').write_text(option_svg(letter, opt['title']), encoding='utf-8')


# ---- main ----

def load(folder):
    path = folder / 'estado.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def save(folder, state):
    state['hechos'] = state.get('hechos', [])[-KEEP_DONE:]
    (folder / 'estado.json').write_text(json.dumps(state, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ('juega', 'nueva', 'contesta'):
        sys.exit(__doc__)
    action, folder = sys.argv[1], Path(sys.argv[2])
    folder.mkdir(parents=True, exist_ok=True)
    state = load(folder)

    if action == 'contesta':
        done = {d['n']: d for d in state.get('hechos', [])}
        repo = os.environ['GITHUB_REPOSITORY']
        for issue in open_issues():
            d = done.get(issue['number'])
            if not d:
                continue  # llegó después: lo juega su propia ejecución
            api('POST', f"/repos/{repo}/issues/{issue['number']}/comments", {'body': d['texto']})
            api('PATCH', f"/repos/{repo}/issues/{issue['number']}", {'state': 'closed', 'state_reason': d['cierre']})
            print(f"#{issue['number']} contestado")
        return

    secret = os.environ.get('JUEGO_SECRETO', '')
    if not secret:
        sys.exit('falta el secreto JUEGO_SECRETO')
    movies = fetch_json(RATINGS)
    by_id = {m['id']: m for m in movies}

    if action == 'nueva' or 'ronda' not in state:
        prev = answer(secret, state, by_id) if 'ronda' in state else None
        if prev and prev[1]:  # la que había se revela sin ganador
            end_round(state, prev[1], None)
        new_round(state, movies, secret)
        print(f"ronda {state['ronda']}")

    if action == 'juega':
        done = {d['n'] for d in state.get('hechos', [])}
        for issue in open_issues():
            if issue['number'] in done:
                continue
            if issue['user'].get('type') == 'Bot':
                text, reason = 'Este juego es para personas.', 'not_planned'
            else:
                text, reason = play(state, issue, movies, by_id, secret)
            state.setdefault('hechos', []).append({'n': issue['number'], 'texto': text, 'cierre': reason})
            print(f"#{issue['number']}: {reason}")

    found = answer(secret, state, by_id)
    render(folder, state, found[1] if found else None)
    save(folder, state)


if __name__ == '__main__':
    main()
