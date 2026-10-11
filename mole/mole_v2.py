# -*- coding: utf-8 -*-
"""
HackTurin - Mole Antonelliana v2
Riusa v1 (piano terra e primo piano identici) e aggiunge l'estetica Mole che si appoggia sopra:
  Mole_03_Coperchio : come v1 + anello di centraggio per la cupola + 6 feritoie (aria verso la cupola)
  Mole_04_Cupola    : tamburo con arcate + cornicione + cupola a profilo concavo + tempietto a colonne + tetto a gradini
  Mole_05_Guglia    : guglia a gradini con stella, si innesta sul perno del tempietto
Cupola e guglia si stampano in piedi, senza supporti. Quote in mm, Z verticale, fronte = -Y.
Rilanciare lo script rigenera tutti i corpi 'Mole_*'. Richiede mole_v1.py nella stessa cartella.
"""
import math
import os
import adsk.core
import adsk.fusion

_V1 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mole_v1.py')
exec(compile(open(_V1, encoding='utf-8').read(), _V1, 'exec'), globals())

# ------------------------------------------------------------------ PARAMETRI estetica (mm)
Z0 = Z_CT                                  # quota d'appoggio: faccia superiore del coperchio
T_D = 1.2                                  # spessore del guscio cupola
DR_L, DR_W = LID_L, LID_W                  # base cupola 67.0 x 52.0 (rientro di 1.4 mm per lato, come i piani sotto)
DRUM_H, DOME_H = 12.0, 28.0                # tamburo con arcate + cupola
TOP_HX, TOP_HY = 12.0, 9.2                 # semi-lati in cima alla cupola (24.0 x 18.4)
SL0, SL1 = -1.4, -0.25                     # pendenze inizio/fine del profilo (cubica di Hermite) -> concavo
N_SECT = 6                                 # sezioni della loft

ARCH_W, ARCH_Z0, ARCH_Z1, ARCH_PIER = 6.0, 3.5, 6.0, 4.5   # arcata: larghezza, base, imposta, pilastro d'angolo
ARCH_N_LONG, ARCH_N_SHORT = 6, 5
CORN_OUT, CORN_H, CORN_STEPS = 1.6, 2.0, 5                 # cornicione a gradini (~45 gradi)

COL_D, COL_H = 3.0, 8.0                    # colonne del tempietto
COL_X, COL_Y = TOP_HX - 2.2, TOP_HY - 2.2
ENT_T = 1.5                                # trabeazione
ROOF = [(9.6, 7.0), (8.0, 5.8), (6.4, 4.6), (5.0, 3.6), (3.8, 2.8)]   # semi-lati dei gradini del tetto
ROOF_STEP_H = 0.8
PEG = (5.0, 3.0, 4.0)                      # perno per la guglia (X, Y, altezza)

G_STEPS = [(5.2, 4.0, 2.0), (4.0, 3.2, 3.0), (2.8, 2.2, 3.0)]  # base a gradini della guglia (semi-X, semi-Y, h)
G_CONE_H, G_CONE_R0, G_CONE_R1 = 8.0, 2.0, 1.0
G_NEEDLE_H, G_NEEDLE_R = 6.0, 1.0
STAR_R, STAR_RI, STAR_T = 4.5, 1.8, 1.2    # stella a 5 punte

RING_L, RING_W = DR_L - 2 * T_D - 0.4, DR_W - 2 * T_D - 0.4   # anello sul coperchio 64.2 x 49.2
RING_T, RING_H = 1.0, 3.0
LIDV_L, LIDV_W = 14.0, 3.0                 # feritoie nel coperchio

# ------------------------------------------------------------------ quote derivate
Z_DRUM_TOP = Z0 + DRUM_H
Z_CAP = Z_DRUM_TOP + DOME_H
Z_ENT = Z_CAP + COL_H
Z_ROOF = Z_ENT + ENT_T + ROOF_STEP_H * len(ROOF)
G_BODY_H = sum(g[2] for g in G_STEPS)
Z_STAR = Z_ROOF + G_BODY_H + G_CONE_H + G_NEEDLE_H - 0.5
Z_TOP = Z_STAR + STAR_R


def _prof(s):
    """Profilo concavo: 1 alla base della cupola, 0 in cima (cubica di Hermite con pendenze SL0/SL1)."""
    a, b = SL0, SL1
    a3, a2 = 2 + a + b, -3 - 2 * a - b
    return ((a3 * s + a2) * s + a) * s + 1


def _centers(length, n):
    avail = length - 2 * ARCH_PIER
    gap = (avail - n * ARCH_W) / (n - 1)
    first = -length / 2 + ARCH_PIER + ARCH_W / 2
    return [first + i * (ARCH_W + gap) for i in range(n)]


# ------------------------------------------------------------------ pipeline a feature (loft/shell) -> copia temporanea
def _plane_sketch(root, z, hx, hy, junk, tag):
    pin = root.constructionPlanes.createInput()
    pin.setByOffset(root.xYConstructionPlane, adsk.core.ValueInput.createByReal(z * CM))
    pl = root.constructionPlanes.add(pin)
    pl.name = 'MoleTmp_pl_' + tag
    junk.append(pl)
    sk = root.sketches.add(pl)
    sk.name = 'MoleTmp_sk_' + tag
    junk.append(sk)
    sk.sketchCurves.sketchLines.addTwoPointRectangle(
        adsk.core.Point3D.create(-hx * CM, -hy * CM, 0), adsk.core.Point3D.create(hx * CM, hy * CM, 0))
    return sk


def _cleanup(junk):
    for o in reversed(junk):
        o.deleteMe()


def make_dome(root):
    """Tamburo (estrusione) + cupola (loft) -> guscio cavo aperto in basso. Ritorna una copia temporanea."""
    junk = []
    FO = adsk.fusion.FeatureOperations
    sk0 = _plane_sketch(root, Z0, DR_L / 2, DR_W / 2, junk, 'drum')
    ei = root.features.extrudeFeatures.createInput(sk0.profiles.item(0), FO.NewBodyFeatureOperation)
    ei.setDistanceExtent(False, adsk.core.ValueInput.createByReal(DRUM_H * CM))
    ext = root.features.extrudeFeatures.add(ei)
    ext.name = 'MoleTmp_drum'
    junk.append(ext)
    drum = ext.bodies.item(0)

    li = root.features.loftFeatures.createInput(FO.NewBodyFeatureOperation)
    for k in range(N_SECT):
        s = k / (N_SECT - 1)
        hx = TOP_HX + (DR_L / 2 - TOP_HX) * _prof(s)
        hy = TOP_HY + (DR_W / 2 - TOP_HY) * _prof(s)
        sk = _plane_sketch(root, Z_DRUM_TOP + DOME_H * s, hx, hy, junk, 'dome%d' % k)
        li.loftSections.add(sk.profiles.item(0))
    li.isSolid = True
    loft = root.features.loftFeatures.add(li)
    loft.name = 'MoleTmp_loft'
    junk.append(loft)

    tools = adsk.core.ObjectCollection.create()
    tools.add(loft.bodies.item(0))
    ci = root.features.combineFeatures.createInput(drum, tools)
    ci.operation = FO.JoinFeatureOperation
    comb = root.features.combineFeatures.add(ci)
    comb.name = 'MoleTmp_join'
    junk.append(comb)

    bot = None
    for f in drum.faces:
        if f.geometry.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
            ok, n = f.evaluator.getNormalAtPoint(f.pointOnFace)
            if n.z < -0.99 and abs(f.boundingBox.minPoint.z - Z0 * CM) < 1e-6:
                bot = f
    faces = adsk.core.ObjectCollection.create()
    faces.add(bot)
    si = root.features.shellFeatures.createInput(faces, False)
    si.insideThickness = adsk.core.ValueInput.createByReal(T_D * CM)
    shell = root.features.shellFeatures.add(si)
    shell.name = 'MoleTmp_shell'
    junk.append(shell)

    tmp = _tbm.copy(shell.bodies.item(0))
    _cleanup(junk)
    return tmp


def make_star(root, zc):
    """Stella a 5 punte (piatta, nel piano XZ, spessore STAR_T) centrata in (0, 0, zc)."""
    junk = []
    sk = root.sketches.add(root.xZConstructionPlane)
    sk.name = 'MoleTmp_star'
    junk.append(sk)
    pts = []
    for i in range(10):
        ang = math.pi / 2 + i * math.pi / 5
        rad = STAR_R if i % 2 == 0 else STAR_RI
        p = adsk.core.Point3D.create(rad * math.cos(ang) * CM, 0, (zc + rad * math.sin(ang)) * CM)
        pts.append(sk.modelToSketchSpace(p))
    lines = sk.sketchCurves.sketchLines
    first = lines.addByTwoPoints(pts[0], pts[1])
    prev = first
    for i in range(2, 10):
        prev = lines.addByTwoPoints(prev.endSketchPoint, pts[i])
    lines.addByTwoPoints(prev.endSketchPoint, first.startSketchPoint)
    ei = root.features.extrudeFeatures.createInput(sk.profiles.item(0), adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    ei.setSymmetricExtent(adsk.core.ValueInput.createByReal(STAR_T * CM), True)
    ext = root.features.extrudeFeatures.add(ei)
    ext.name = 'MoleTmp_star_ext'
    junk.append(ext)
    tmp = _tbm.copy(ext.bodies.item(0))
    _cleanup(junk)
    return tmp


# ------------------------------------------------------------------ PARTE 3 (v2): coperchio con anello e feritoie
def build_D2():
    D = build_D()
    ro_x, ro_y = RING_L / 2, RING_W / 2
    ring = box(-ro_x, -ro_y, Z_CT - 0.05, ro_x, ro_y, Z_CT + RING_H)
    sub(ring, box(-ro_x + RING_T, -ro_y + RING_T, Z_CT - 0.5, ro_x - RING_T, ro_y - RING_T, Z_CT + RING_H + 0.5))
    add(D, ring)
    zr0, zr1 = Z_CT + 0.6, Z_CT + RING_H - 0.4
    for x in (-15.0, 15.0):                  # nervature di calettamento sull'anello
        add(D, box(x - 0.5, -ro_y - RIB_H, zr0, x + 0.5, -ro_y + 0.05, zr1))
        add(D, box(x - 0.5, ro_y - 0.05, zr0, x + 0.5, ro_y + RIB_H, zr1))
    add(D, box(-ro_x - RIB_H, -0.5, zr0, -ro_x + 0.05, 0.5, zr1))
    add(D, box(ro_x - 0.05, -0.5, zr0, ro_x + RIB_H, 0.5, zr1))
    for x in (-20.0, 0.0, 20.0):             # feritoie: l'aria sale dal primo piano alla cupola
        for y in (-8.0, 8.0):
            sub(D, box(x - LIDV_L / 2, y - LIDV_W / 2, Z_CT - LID_T - 0.5, x + LIDV_L / 2, y + LIDV_W / 2, Z_CT + 0.5))
    return D


# ------------------------------------------------------------------ PARTE 4: cupola + tempietto
def build_cupola(root):
    d = make_dome(root)
    xh, yh = DR_L / 2, DR_W / 2

    # arcate passanti sul tamburo (prima del cornicione, che sta piu' in alto)
    zs = Z0 + ARCH_Z1
    for xc in _centers(DR_L, ARCH_N_LONG):
        tool = box(xc - ARCH_W / 2, -yh - 3, Z0 + ARCH_Z0, xc + ARCH_W / 2, yh + 3, zs)
        add(tool, ycyl(xc, zs, -yh - 3, yh + 3, ARCH_W / 2))
        sub(d, tool)
    for yc in _centers(DR_W, ARCH_N_SHORT):
        tool = box(-xh - 3, yc - ARCH_W / 2, Z0 + ARCH_Z0, xh + 3, yc + ARCH_W / 2, zs)
        add(tool, xcyl(yc, zs, -xh - 3, xh + 3, ARCH_W / 2))
        sub(d, tool)

    # cornicione a gradini alla base della cupola
    for k in range(CORN_STEPS):
        out = CORN_OUT * (k + 1) / CORN_STEPS
        zb = Z_DRUM_TOP - CORN_H + CORN_H * k / CORN_STEPS
        ring = box(-xh - out, -yh - out, zb, xh + out, yh + out, Z_DRUM_TOP)
        sub(ring, box(-xh + 0.2, -yh + 0.2, zb - 1, xh - 0.2, yh - 0.2, Z_DRUM_TOP + 1))
        add(d, ring)

    # tempietto: 8 colonne + trabeazione + tetto a gradini + perno per la guglia
    cols = [(sx * COL_X, sy * COL_Y) for sx in (-1, 1) for sy in (-1, 1)]
    cols += [(0, COL_Y), (0, -COL_Y), (COL_X, 0), (-COL_X, 0)]
    for (x, y) in cols:
        add(d, zcyl(x, y, Z_CAP - 0.3, Z_ENT + 0.3, COL_D / 2))
    add(d, box(-(TOP_HX - 0.4), -(TOP_HY - 0.4), Z_ENT, TOP_HX - 0.4, TOP_HY - 0.4, Z_ENT + ENT_T))
    z = Z_ENT + ENT_T
    for (hx, hy) in ROOF:
        add(d, box(-hx, -hy, z - 0.05, hx, hy, z + ROOF_STEP_H))
        z += ROOF_STEP_H
    add(d, box(-PEG[0] / 2, -PEG[1] / 2, Z_ROOF - 0.05, PEG[0] / 2, PEG[1] / 2, Z_ROOF + PEG[2]))
    return d


# ------------------------------------------------------------------ PARTE 5: guglia con stella
def build_guglia(root):
    g = box(-G_STEPS[0][0], -G_STEPS[0][1], Z_ROOF, G_STEPS[0][0], G_STEPS[0][1], Z_ROOF + G_STEPS[0][2])
    z = Z_ROOF + G_STEPS[0][2]
    for (hx, hy, h) in G_STEPS[1:]:
        add(g, box(-hx, -hy, z - 0.05, hx, hy, z + h))
        z += h
    add(g, _tbm.createCylinderOrCone(_pt(0, 0, z - 0.05), G_CONE_R0 * CM, _pt(0, 0, z + G_CONE_H), G_CONE_R1 * CM))
    z += G_CONE_H
    add(g, zcyl(0, 0, z - 0.05, z + G_NEEDLE_H, G_NEEDLE_R))
    add(g, make_star(root, Z_STAR))
    # sede del perno del tempietto (0.1 mm di gioco per lato), aperta sotto
    sub(g, box(-PEG[0] / 2 - 0.1, -PEG[1] / 2 - 0.1, Z_ROOF - 0.1, PEG[0] / 2 + 0.1, PEG[1] / 2 + 0.1, Z_ROOF + PEG[2] + 0.4))
    return g


# ------------------------------------------------------------------ main
def _clear_tmp(design):
    tl = design.timeline
    for i in range(tl.count - 1, -1, -1):
        if i >= tl.count:
            continue
        ent = tl.item(i).entity
        if ent is not None and getattr(ent, 'name', '').startswith('MoleTmp_'):
            ent.deleteMe()


def build():
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    root = design.rootComponent
    parametric = design.designType == adsk.fusion.DesignTypes.ParametricDesignType
    _clear_previous(root, parametric)
    if parametric:
        _clear_tmp(design)

    parts = [('Mole_01_PianoTerra', build_A()),
             ('Mole_02_PrimoPiano', build_C()),
             ('Mole_03_Coperchio', build_D2()),
             ('Mole_04_Cupola', build_cupola(root)),
             ('Mole_05_Guglia', build_guglia(root))]
    bf = None
    if parametric:
        bf = root.features.baseFeatures.add()
        bf.name = GEN_NAME
        bf.startEdit()
    tot = 0.0
    for name, tb in parts:
        body = root.bRepBodies.add(tb, bf) if parametric else root.bRepBodies.add(tb)
        body.name = name
        bb = body.boundingBox
        tot += body.volume * 1000
        print('%s: %.0f mm3 | X %.1f..%.1f  Y %.1f..%.1f  Z %.1f..%.1f' % (
            name, body.volume * 1000,
            bb.minPoint.x * 10, bb.maxPoint.x * 10, bb.minPoint.y * 10, bb.maxPoint.y * 10,
            bb.minPoint.z * 10, bb.maxPoint.z * 10))
    if parametric:
        bf.finishEdit()
    app.activeViewport.fit()
    print('totale %.1f cm3 (~%.0f g PLA) | altezza complessiva %.1f mm' % (tot / 1000, tot / 1000 * 1.24, Z_TOP))
