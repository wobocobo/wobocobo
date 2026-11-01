"""Spidey cruzando la cabecera.

Porta el muñeco de wobocobo.com (función spidey() de js/main.js) a un SVG
sin JS: precalcula los fotogramas aquí y los mete como animaciones SMIL
entre <!--spidey--> y <!--/spidey--> en cabecera.svg y cabecera-dia.svg.
Solo librería estándar.

    python scripts/spidey.py
"""

import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FPS = 20
SCALE = 0.42  # ~44 px de la mano a los pies
K = 0.35  # cuánto acelera en la parte baja del arco (en la web, 0.45)
START = 2  # s hasta la primera pasada
PERIOD = 20  # s entre el comienzo de una pasada y el de la siguiente

RED = '#d0202c'
RED_FAR = '#a3141f'
RED_DARK = '#4a070e'
BLUE = '#2453b8'
BLUE_FAR = '#1a3d8c'
BLUE_DARK = '#0a1838'

# color de la telaraña: el --text de cada tema de la web
THEMES = {'cabecera.svg': '#f2f6fc', 'cabecera-dia.svg': '#0d1526'}

# Recorrido: entra de un salto por encima del título y se cuelga de las
# azoteas de los tres edificios altos. ax, ay: ancla; L: largo de la
# telaraña; a, b: ángulo al engancharse y al soltarse (0 = colgando recto).
ARCS = [
    {'ax': 566, 'ay': 118, 'L': 72, 'a': -70, 'b': 30},
    {'ax': 684, 'ay': 97, 'L': 86, 'a': -30, 'b': 30},
    {'ax': 780, 'ay': 96, 'L': 78, 'a': -20, 'b': 50},
]
ARC_DUR = 1.6
JUMP_DUR = (0.5, 0.7)  # entre arcos: lo que pida la velocidad, dentro de estos límites
ENTRY_DUR = 1.3
EXIT_DUR = 0.9
ENTRY_FROM = (-40, 44)  # centro del cuerpo al entrar, fuera del cuadro

# ---- muñeco: lo mismo que en la web ----

SEG = {'torso': 30, 'neck': 9, 'upper': 17, 'fore': 16, 'hand': 4, 'thigh': 21, 'shin': 20, 'foot': 9}

POSES = {
    'swingA': {'tor': 178, 'head': 168, 'a1u': 180, 'a1f': 180, 'a2u': -40, 'a2f': -10, 'l1t': -15, 'l1s': -45, 'l2t': -5, 'l2s': -30},
    'swingM': {'tor': 175, 'head': 162, 'a1u': 180, 'a1f': 180, 'a2u': -15, 'a2f': 35, 'l1t': 35, 'l1s': -10, 'l2t': 12, 'l2s': -28},
    'swingB': {'tor': 166, 'head': 152, 'a1u': 180, 'a1f': 180, 'a2u': 35, 'a2f': 80, 'l1t': 85, 'l1s': 30, 'l2t': 60, 'l2s': 8},
    'tuck': {'tor': 160, 'head': 140, 'a1u': 150, 'a1f': 135, 'a2u': 60, 'a2f': 115, 'l1t': 110, 'l1s': -5, 'l2t': 95, 'l2s': -25},
    'ball': {'tor': 150, 'head': 118, 'a1u': 85, 'a1f': 150, 'a2u': 70, 'a2f': 135, 'l1t': 140, 'l1s': 5, 'l2t': 128, 'l2s': -8},
}

# piezas en orden de pintado: [nombre, desde, hasta, radio1, radio2, color]
PARTS = [
    ['a1u', 'shoulder', 'e1', 3.6, 3, 'far'],  # brazo de la telaraña, por detrás
    ['a1f', 'e1', 'w1', 3, 2.5, 'far'],
    ['a1h', 'w1', 'h1', 2.8, 2.4, 'far'],
    ['l2t', 'hip', 'k2', 5, 4, 'blueFar'],  # pierna de atrás
    ['l2s', 'k2', 'an2', 4, 3.1, 'blueFar'],
    ['l2b', 'b2', 'an2', 3.5, 3.1, 'far'],
    ['l2f', 'an2', 'toe2', 3.1, 2.2, 'far'],
    ['tb', 'pelvis', 'chest', 6, 8.2, 'blue'],  # tronco: azul a los lados, panel rojo delante
    ['tr', 'panelLow', 'panelTop', 3.4, 6, 'red'],
    'emblem',
    ['l1t', 'hip', 'k1', 5.2, 4.2, 'blue'],  # pierna de delante
    ['l1s', 'k1', 'an1', 4.1, 3.2, 'blue'],
    ['l1b', 'b1', 'an1', 3.6, 3.2, 'red'],
    ['l1f', 'an1', 'toe1', 3.2, 2.3, 'red'],
    'head',
    ['a2u', 'shoulder', 'e2', 3.8, 3.1, 'red'],  # brazo libre, por delante
    ['a2f', 'e2', 'w2', 3.1, 2.6, 'red'],
    ['a2h', 'w2', 'h2', 2.9, 2.4, 'red'],
]
PAINT = {
    'red': f'fill="url(#sp-w)" stroke="{RED_DARK}"',
    'far': f'fill="url(#sp-wf)" stroke="{RED_DARK}"',
    'blue': f'fill="{BLUE}" stroke="{BLUE_DARK}"',
    'blueFar': f'fill="{BLUE_FAR}" stroke="{BLUE_DARK}"',
}


def web_pattern(id_, color):
    return (
        f'<pattern id="{id_}" width="3.2" height="3.2" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        f'<rect width="3.2" height="3.2" fill="{color}"/>'
        f'<path d="M0 0H3.2M0 0V3.2" stroke="{RED_DARK}" stroke-width=".35" stroke-opacity=".55"/></pattern>'
    )


# cabeza de perfil a tres cuartos, mirando a la derecha (arriba = -y)
HEAD = (
    f'<ellipse rx="7.4" ry="8.8" fill="url(#sp-w)" stroke="{RED_DARK}" stroke-width=".9"/>'
    '<path d="M1.2 1.6Q.9-2.8 6.3-3.6Q6.4 1.6 1.2 1.6Z" fill="#fff" stroke="#111" stroke-width="1.1" stroke-linejoin="round"/>'
    '<path d="M-.8 1.6Q-1-2.4-4.6-3Q-4.8 1.2-.8 1.6Z" fill="#fff" stroke="#111" stroke-width="1.1" stroke-linejoin="round"/>'
)

EMBLEM = (
    '<ellipse cy=".6" rx="1.2" ry="2.3"/><circle cy="-2.2" r="1"/>'
    '<path fill="none" stroke="#111" stroke-width=".5" stroke-linecap="round" '
    'd="M0-1.2L-3.4-3.6M0-1.2L3.4-3.6M0-.4L-3.8-1M0-.4L3.8-1M0 .6L-3.6 2M0 .6L3.6 2M0 1.4L-2.8 4.2M0 1.4L2.8 4.2"/>'
)


def direction(a):
    r = math.radians(a)
    return math.sin(r), math.cos(r)


def add(p, a, length):
    dx, dy = direction(a)
    return p[0] + dx * length, p[1] + dy * length


def lerp(a, b, u):
    return a + (b - a) * u


def lerp_pt(p, q, u):
    return lerp(p[0], q[0], u), lerp(p[1], q[1], u)


def ease_out(u):
    return 1 - (1 - u) * (1 - u)


def smooth(u):
    return u * u * (3 - 2 * u)


def mix(a, b, u):
    return {k: lerp(a[k], b[k], smooth(u)) for k in a}


def rig(p):
    """Articulaciones de una pose, con la mano de la telaraña en (0, 0)."""
    j = {'pelvis': (0, 0)}
    j['hip'] = add(j['pelvis'], p['tor'], 1.5)
    neck = add(j['pelvis'], p['tor'], SEG['torso'])
    j['chest'] = add(neck, p['tor'], -2)
    j['shoulder'] = add(neck, p['tor'], -3)
    j['head'] = add(neck, p['head'], SEG['neck'])
    j['panelLow'] = add(add(j['pelvis'], p['tor'], 3), p['tor'] - 90, 1.8)
    j['panelTop'] = add(j['chest'], p['tor'] - 90, 1.8)
    j['emblem'] = add(add(j['pelvis'], p['tor'], 21), p['tor'] - 90, 2)
    j['e1'] = add(j['shoulder'], p['a1u'], SEG['upper'])
    j['w1'] = add(j['e1'], p['a1f'], SEG['fore'])
    j['h1'] = add(j['w1'], p['a1f'], SEG['hand'])
    j['e2'] = add(j['shoulder'], p['a2u'], SEG['upper'])
    j['w2'] = add(j['e2'], p['a2f'], SEG['fore'])
    j['h2'] = add(j['w2'], p['a2f'], SEG['hand'])
    for n in (1, 2):
        t, s = p[f'l{n}t'], p[f'l{n}s']
        j[f'k{n}'] = add(j['hip'], t, SEG['thigh'])
        j[f'an{n}'] = add(j[f'k{n}'], s, SEG['shin'])
        j[f'b{n}'] = lerp_pt(j[f'k{n}'], j[f'an{n}'], 0.45)
        j[f'toe{n}'] = add(j[f'an{n}'], s + 75, SEG['foot'])
    x, y = j['h1']
    return {k: (v[0] - x, v[1] - y) for k, v in j.items()}


def capsule(length, r1, r2):
    """Pieza redondeada de (0, 0) a (0, length), más gruesa en un extremo."""
    f = lambda n: f'{n:.2f}'.rstrip('0').rstrip('.')
    return (
        f'M{f(-r1)} 0L{f(-r2)} {f(length)}A{r2} {r2} 0 0 0 {f(r2)} {f(length)}'
        f'L{f(r1)} 0A{r1} {r1} 0 0 0 {f(-r1)} 0Z'
    )


# ---- recorrido ----

def rotate(v, a):
    c, s = math.cos(a), math.sin(a)
    return v[0] * c - v[1] * s, v[0] * s + v[1] * c


def center(pose):
    """Centro del cuerpo respecto a la mano: los saltos giran sobre él."""
    j = rig(pose)
    return lerp_pt(j['pelvis'], j['shoulder'], 0.5)


def hand_from_center(c, rot, pose):
    off = rotate(center(pose), rot)
    return c[0] - off[0] * SCALE, c[1] - off[1] * SCALE


def center_from_hand(h, rot, pose):
    off = rotate(center(pose), rot)
    return h[0] + off[0] * SCALE, h[1] + off[1] * SCALE


def arc_point(arc, deg):
    phi = math.radians(deg)
    return arc['ax'] + arc['L'] * math.sin(phi), arc['ay'] + arc['L'] * math.cos(phi)


def anchor(arc):
    return arc['ax'], arc['ay']


def bezier2(p, c, q, u):
    return (
        (1 - u) ** 2 * p[0] + 2 * (1 - u) * u * c[0] + u * u * q[0],
        (1 - u) ** 2 * p[1] + 2 * (1 - u) * u * c[1] + u * u * q[1],
    )


def bezier3(p, c1, c2, q, u):
    v = 1 - u
    return (
        v**3 * p[0] + 3 * v * v * u * c1[0] + 3 * v * u * u * c2[0] + u**3 * q[0],
        v**3 * p[1] + 3 * v * v * u * c1[1] + 3 * v * u * u * c2[1] + u**3 * q[1],
    )


def curve_len(fn, n=60):
    pts = [fn(i / n) for i in range(n + 1)]
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(n))


def release_speed(arc):
    """px/s de la mano al soltarse (o al engancharse) del arco."""
    half = math.radians(arc['b'] - arc['a']) / 2
    return arc['L'] * half * 2 * (1 - K) / ARC_DUR


def arc_seg(arc):
    a, b = math.radians(arc['a']), math.radians(arc['b'])
    mid, half = (a + b) / 2, (b - a) / 2

    def state(u):
        phi = mid + half * ((1 - K) * (2 * u - 1) + K * math.sin(math.pi * (u - 0.5)))
        pos = arc['ax'] + arc['L'] * math.sin(phi), arc['ay'] + arc['L'] * math.cos(phi)
        pose = mix(POSES['swingA'], POSES['swingM'], u * 2) if u < 0.5 else mix(POSES['swingM'], POSES['swingB'], u * 2 - 1)
        return pos, -phi, pose, (pos, anchor(arc))

    return ARC_DUR, state


def jump_seg(arc, nxt):
    p1, p2 = arc_point(arc, arc['b']), arc_point(nxt, nxt['a'])
    rb = math.radians(arc['b'])
    cx = (p1[0] + p2[0]) / 2
    c = cx, p1[1] - (cx - p1[0]) * math.tan(rb)
    dur = curve_len(lambda u: bezier2(p1, c, p2, u)) / release_speed(arc)
    dur = min(max(dur, JUMP_DUR[0]), JUMP_DUR[1])

    def state(u):
        pos = bezier2(p1, c, p2, u)
        rot = lerp(-rb, -math.radians(nxt['a']), u)
        pose = mix(POSES['swingB'], POSES['tuck'], u * 2) if u < 0.5 else mix(POSES['tuck'], POSES['swingA'], u * 2 - 1)
        web = None
        if u > 0.5:  # dispara la siguiente
            web = pos, lerp_pt(pos, anchor(nxt), ease_out((u - 0.5) / 0.5))
        elif u < 0.4:  # la soltada se recoge hacia su ancla
            web = lerp_pt(p1, anchor(arc), ease_out(u / 0.4)), anchor(arc)
        return pos, rot, pose, web

    return dur, state


def entry_seg(arc):
    """Salto por encima del título con voltereta; dispara al bajar."""
    rot1 = -math.radians(arc['a'])
    h1 = arc_point(arc, arc['a'])
    c1 = center_from_hand(h1, rot1, POSES['swingA'])
    tan = math.cos(math.radians(arc['a'])), -math.sin(math.radians(arc['a']))  # hacia donde arranca el arco
    k1, k2 = (130, -70), 120
    p0 = ENTRY_FROM
    cp1 = p0[0] + k1[0], p0[1] + k1[1]
    cp2 = c1[0] - tan[0] * k2, c1[1] - tan[1] * k2

    def state(u):
        v = 0.85 * ease_out(u) + 0.15 * u  # llega frenando al arco
        cpos = bezier3(p0, cp1, cp2, c1, v)
        rot = rot1 - 2 * math.pi * (1 - smooth(min(1, u / 0.75)))
        pose = POSES['ball'] if u < 0.5 else mix(POSES['ball'], POSES['swingA'], (u - 0.5) / 0.5)
        pos = hand_from_center(cpos, rot, pose)
        web = None
        if u >= 0.6:
            web = pos, lerp_pt(pos, anchor(arc), ease_out((u - 0.6) / 0.4))
        return pos, rot, pose, web

    return ENTRY_DUR, state


def exit_seg(arc):
    """Se suelta del último arco y se va por la derecha con voltereta."""
    rb = math.radians(arc['b'])
    rot0 = -rb
    h0 = arc_point(arc, arc['b'])
    p0 = center_from_hand(h0, rot0, POSES['swingB'])
    d = 60
    c = p0[0] + d * math.cos(rb), p0[1] - d * math.sin(rb)
    p2 = c[0] + d, c[1]

    def state(u):
        v = 0.3 * u + 0.7 * u * u  # sale disparado
        cpos = bezier2(p0, c, p2, v)
        rot = rot0 + 2 * math.pi * ease_out(u)
        pose = mix(POSES['swingB'], POSES['ball'], min(1, u * 2.5))
        pos = hand_from_center(cpos, rot, pose)
        web = None
        if u < 0.4:
            web = lerp_pt(h0, anchor(arc), ease_out(u / 0.4)), anchor(arc)
        return pos, rot, pose, web

    return EXIT_DUR, state


def segments():
    segs = [entry_seg(ARCS[0])]
    for i, arc in enumerate(ARCS):
        segs.append(arc_seg(arc))
        if i + 1 < len(ARCS):
            segs.append(jump_seg(arc, ARCS[i + 1]))
    segs.append(exit_seg(ARCS[-1]))
    return segs


# ---- fotogramas y SVG ----

def num(v):
    s = f'{v:.1f}'.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def unwrap(degs):
    out = [degs[0]]
    for d in degs[1:]:
        while d - out[-1] > 180:
            d -= 360
        while d - out[-1] < -180:
            d += 360
        out.append(d)
    return out


def frames():
    segs = segments()
    total = sum(d for d, _ in segs)
    n = round(total * FPS)
    out = []
    for i in range(n + 1):
        t = total * i / n
        for dur, state in segs:
            if t <= dur:
                break
            t -= dur
        out.append(state(min(1, t / dur)))
    return total, out


def extent(state):
    """Caja (x0, y0, x1, y1) del muñeco en la escena, con margen por el grosor."""
    pos, rot, pose, _ = state
    pts = [rotate(p, rot) for p in rig(pose).values()]
    xs = [pos[0] + x * SCALE for x, _ in pts]
    ys = [pos[1] + y * SCALE for _, y in pts]
    m = 9 * SCALE
    return min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m


def animate_transform(kind, values, extra=''):
    return (
        f'<animateTransform attributeName="transform" type="{kind}" values="{values}"{extra} '
        f'begin="spclk.begin" dur="{{dur}}s" fill="freeze"/>'
    )


def block(web_color):
    total, fs = frames()
    dur = num(total)
    # entre pasadas se queda congelado en el último fotograma: tiene que estar fuera
    assert extent(fs[0])[2] < 0, 'el primer fotograma se ve'
    assert extent(fs[-1])[0] > 900, 'el último fotograma se ve'

    # por pieza: articulación de partida y ángulo, fotograma a fotograma
    tracks = {}
    for pos, rot, pose, web in fs:
        j = rig(pose)
        for part in PARTS:
            if isinstance(part, list):
                name, a, b = part[0], j[part[1]], j[part[2]]
                ang = math.degrees(math.atan2(-(b[0] - a[0]), b[1] - a[1]))
                tracks.setdefault(name, []).append((a, ang))
        tracks.setdefault('head', []).append((j['head'], 180 - pose['head']))
        tracks.setdefault('emblem', []).append((j['emblem'], 180 - pose['tor']))

    def moving(track):
        tr = ';'.join(f'{num(p[0])},{num(p[1])}' for p, _ in track)
        rt = ';'.join(num(a) for a in unwrap([a for _, a in track]))
        return animate_transform('translate', tr) + animate_transform('rotate', rt, ' additive="sum"')

    j0 = rig(POSES['swingA'])
    body = []
    for part in PARTS:
        if part == 'emblem':
            body.append(f'<g fill="#111">{EMBLEM}{moving(tracks["emblem"])}</g>')
        elif part == 'head':
            body.append(f'<g>{HEAD}{moving(tracks["head"])}</g>')
        else:
            name, a, b, r1, r2, paint = part
            length = math.dist(j0[a], j0[b])
            body.append(
                f'<path d="{capsule(length, r1, r2)}" {PAINT[paint]} stroke-width=".8" stroke-linejoin="round">'
                f'{moving(tracks[name])}</path>'
            )

    man_tr = ';'.join(f'{num(p[0])},{num(p[1])}' for p, _, _, _ in fs)
    man_rt = ';'.join(num(a) for a in unwrap([math.degrees(r) for _, r, _, _ in fs]))

    # la telaraña: se queda donde estaba mientras no se ve
    last = ((0, 0), (0, 0))
    webs = []
    for *_, web in fs:
        if web:
            last = web
        webs.append((web is not None, last))
    line_anims = ''.join(
        f'<animate attributeName="{attr}" values="{";".join(num(w[1][i][k]) for w in webs)}" '
        f'begin="spclk.begin" dur="{dur}s" fill="freeze"/>'
        for attr, i, k in (('x1', 0, 0), ('y1', 0, 1), ('x2', 1, 0), ('y2', 1, 1))
    )
    line_anims += (
        f'<animate attributeName="opacity" values="{";".join("1" if w[0] else "0" for w in webs)}" '
        f'calcMode="discrete" begin="spclk.begin" dur="{dur}s" fill="freeze"/>'
    )

    gap = num(PERIOD - total)
    out = (
        '<g class="sp">'
        '<style>@media (prefers-reduced-motion:reduce){.sp{display:none}}</style>'
        '<defs>'
        + web_pattern('sp-w', RED)
        + web_pattern('sp-wf', RED_FAR)
        + '<filter id="sp-sh" x="-50%" y="-50%" width="200%" height="200%">'
        '<feDropShadow dx="0" dy="2" stdDeviation="1.6" flood-color="#000" flood-opacity=".35"/></filter>'
        '</defs>'
        f'<animate id="spclk" attributeName="opacity" values="1;1" dur="{dur}s" begin="{START}s;spclk.end+{gap}s"/>'
        f'<line stroke="{web_color}" stroke-opacity=".85" stroke-width="1.4" stroke-linecap="round" opacity="0">'
        f'{line_anims}</line>'
        '<g filter="url(#sp-sh)"><g transform="translate(-300,-300)">'
        + animate_transform('translate', man_tr)
        + animate_transform('rotate', man_rt, ' additive="sum"')
        + f'<g transform="scale({SCALE})">'
        + ''.join(body)
        + '</g></g></g></g>'
    )
    return out.replace('{dur}', dur), total


def main():
    for name, web_color in THEMES.items():
        path = ROOT / name
        if not path.exists():
            continue
        svg = path.read_text(encoding='utf-8')
        sp, total = block(web_color)
        sp = f'<!--spidey-->{sp}<!--/spidey-->'
        if '<!--spidey-->' in svg:
            svg = re.sub(r'<!--spidey-->.*?<!--/spidey-->', lambda _: sp, svg, flags=re.S)
        else:
            # dentro del grupo recortado, por delante de todo
            svg = svg[: svg.rindex('</g></svg>')] + sp + '</g></svg>'
        path.write_text(svg, encoding='utf-8', newline='')
        print(f'{name}: pasada de {total:.1f} s, {len(svg.encode()) / 1024:.0f} KB')


if __name__ == '__main__':
    main()
