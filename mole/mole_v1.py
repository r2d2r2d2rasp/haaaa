# -*- coding: utf-8 -*-
"""
HackTurin - Mole Antonelliana v1: contenitore rettangolare a 2 piani
Fusion 360 (Python API) - quote in mm - Z = verticale - fronte (faccia forata) = -Y - USB-C a sinistra (-X)

Corpi generati (stampabili senza supporti, ognuno appoggiato sul proprio fondo):
  Mole_01_PianoTerra : base con vano per Arduino UNO Q + Seeed Base Shield, 4 perni sui fori UNO
  Mole_02_PrimoPiano : scatola con pavimento a griglia (feritoie cavi), guide OLED/luce, tasca pulsante
  Mole_03_Coperchio  : tetto piatto provvisorio (sara' sostituito dalla cupola)
Incastro a "matrioska": ogni piano entra nel sottostante (gioco 0.2 mm per lato + nervature di calettamento).
Rilanciare lo script rigenera tutto (cancella i corpi 'Mole_*' precedenti).
"""
import adsk.core
import adsk.fusion

GEN_NAME = 'MoleGen'

# ------------------------------------------------------------------ PARAMETRI (mm)
# scheda + shield
ENV_L, ENV_W, ENV_H = 69.0, 54.0, 30.0       # ingombro dichiarato dello stack UNO Q + Base Shield
BOARD_L, BOARD_W = 68.58, 53.34              # PCB UNO Q (datasheet ABX00162, cap. 12)
HOLES = [(13.97, 2.54), (15.24, 50.80), (66.04, 7.62), (66.04, 35.56)]  # fori (passo UNO), origine = angolo basso-sx
USBC_Y = 37.8                                # centro USB-C dal bordo basso della scheda (lato -X)
USBC_W, USBC_Z0, USBC_Z1 = 16.0, 3.3, 12.3   # apertura in parete: larghezza, quota min/max

# generali
T = 1.2             # spessore pareti
FLOOR_A = 1.6       # fondo della base
FLOOR_C = 1.6       # pavimento a griglia del primo piano
LID_T = 2.0         # spessore coperchio
CLR = 0.2           # gioco di accoppiamento per lato
CAV_CLR = 0.6       # gioco attorno all'ingombro della scheda
RIB_H = 0.35        # sporgenza nervature di calettamento (interferenza ~0.15 con gioco 0.2)

# perni scheda
STAND_H, STAND_D, PIN_D, PIN_H = 3.0, 5.4, 3.0, 2.2

# quote verticali
CABLE_SPACE = 8.4   # spazio sopra lo shield per i connettori Grove inseriti
NEST = 5.0          # profondita' d'incastro del primo piano nella base
C_INT_H = 30.0      # altezza interna del primo piano

# pavimento a griglia
COLS, ROWS = 4, 4
CELL_W, CELL_H, RIB = 12.0, 8.0, 2.5
GRID_Y0 = -16.5     # inizio feritoie (Y); davanti resta una fascia piena per le guide

# guide moduli sulla parete frontale
STEM, LIP, LIP_T, GUIDE_H = 1.0, 1.0, 1.0, 24.0
OLED_W, D_OLED = 26.6, 5.5                  # modulo OLED (26.6 x 20) e profondita' guida
LIGHT_W, LIGHT_H, D_LIGHT = 20.0, 20.0, 7.0  # light sensor (20 x 20)
MOD_LIFT, STOP_W = 5.0, 4.0                 # moduli sollevati di 5 mm (sotto passa il cavo)
WIN_W, WIN_Z0, WIN_Z1 = 24.0, 10.0, 23.0    # finestra OLED (larghezza, quota min/max sopra il pavimento)
LIGHT_HOLE_D = 8.0
N_VENT, VENT_W, VENT_PITCH = 4, 2.2, 3.9    # feritoie sulla faccia frontale

# pulsante tattile 12x12 (parete +X)
BTN_BODY, BTN_DEPTH, BTN_ZC, BTN_HOLE_D = 12.0, 4.5, 15.0, 13.0
BTN_SLOT = BTN_BODY + 0.4

# ------------------------------------------------------------------ quote derivate
IL, IW = ENV_L + 2 * CAV_CLR, ENV_W + 2 * CAV_CLR      # vano base 70.2 x 55.2
OL, OW = IL + 2 * T, IW + 2 * T                        # esterno base 72.6 x 57.6
BX0, BY0 = -BOARD_L / 2, -BOARD_W / 2                  # angolo basso-sx della scheda

Z_BOARD = FLOOR_A + STAND_H
Z_STACK_TOP = Z_BOARD + ENV_H
Z_L = round(Z_STACK_TOP + CABLE_SPACE, 1)              # fondo del primo piano
HA = Z_L + NEST                                        # bordo superiore della base

CL, CW = IL - 2 * CLR, IW - 2 * CLR                    # esterno primo piano 69.8 x 54.8
CIL, CIW = CL - 2 * T, CW - 2 * T                      # interno 67.4 x 52.4
Z_CF = Z_L + FLOOR_C                                   # piano di calpestio dei sensori
Z_CT = Z_CF + C_INT_H                                  # bordo superiore primo piano
LID_L, LID_W = CIL - 2 * CLR, CIW - 2 * CLR            # coperchio 67.0 x 52.0

# ------------------------------------------------------------------ primitive
CM = 0.1  # 1 mm = 0.1 cm (unita' interne Fusion)
_tbm = adsk.fusion.TemporaryBRepManager.get()
_BT = adsk.fusion.BooleanTypes


def _pt(x, y, z):
    return adsk.core.Point3D.create(x * CM, y * CM, z * CM)


def box(x0, y0, z0, x1, y1, z1):
    xa, xb = sorted((x0, x1))
    ya, yb = sorted((y0, y1))
    za, zb = sorted((z0, z1))
    obb = adsk.core.OrientedBoundingBox3D.create(
        _pt((xa + xb) / 2, (ya + yb) / 2, (za + zb) / 2),
        adsk.core.Vector3D.create(1, 0, 0), adsk.core.Vector3D.create(0, 1, 0),
        (xb - xa) * CM, (yb - ya) * CM, (zb - za) * CM)
    return _tbm.createBox(obb)


def zcyl(cx, cy, z0, z1, r):
    return _tbm.createCylinderOrCone(_pt(cx, cy, z0), r * CM, _pt(cx, cy, z1), r * CM)


def ycyl(cx, cz, y0, y1, r):
    return _tbm.createCylinderOrCone(_pt(cx, y0, cz), r * CM, _pt(cx, y1, cz), r * CM)


def xcyl(cy, cz, x0, x1, r):
    return _tbm.createCylinderOrCone(_pt(x0, cy, cz), r * CM, _pt(x1, cy, cz), r * CM)


def add(a, b):
    if not _tbm.booleanOperation(a, b, _BT.UnionBooleanType):
        raise RuntimeError('unione fallita')


def sub(a, b):
    if not _tbm.booleanOperation(a, b, _BT.DifferenceBooleanType):
        raise RuntimeError('sottrazione fallita')


def ledge_y(body, y_face, toward, x0, x1, z_top, w=2.0, h=2.0, steps=5):
    """Mensola a gradini (~45 gradi, stampabile senza supporti) che sporge da una parete
    interna posta in y=y_face verso +Y (toward>0) o -Y (toward<0); lato superiore piano a z_top."""
    for k in range(steps):
        wk = w * (k + 1) / steps
        zb = z_top - h + h * k / steps
        if toward > 0:
            add(body, box(x0, y_face - 0.05, zb, x1, y_face + wk, z_top))
        else:
            add(body, box(x0, y_face - wk, zb, x1, y_face + 0.05, z_top))


# ------------------------------------------------------------------ PARTE 1: piano terra
def build_A():
    A = box(-OL / 2, -OW / 2, 0, OL / 2, OW / 2, HA)
    sub(A, box(-IL / 2, -IW / 2, FLOOR_A, IL / 2, IW / 2, HA + 1))
    # perni sui fori della UNO Q (la scheda si infila e resta bloccata dal piano sopra)
    for hx, hy in HOLES:
        x, y = BX0 + hx, BY0 + hy
        add(A, zcyl(x, y, FLOOR_A - 0.1, FLOOR_A + STAND_H, STAND_D / 2))
        add(A, zcyl(x, y, FLOOR_A + STAND_H - 0.1, FLOOR_A + STAND_H + PIN_H, PIN_D / 2))
    # mensole che reggono il pavimento del primo piano (lati lunghi)
    ledge_y(A, -IW / 2, +1, -IL / 2 - 0.05, IL / 2 + 0.05, Z_L)
    ledge_y(A, +IW / 2, -1, -IL / 2 - 0.05, IL / 2 + 0.05, Z_L)
    # apertura USB-C sul lato -X
    yc = BY0 + USBC_Y
    sub(A, box(-OL / 2 - 0.5, yc - USBC_W / 2, USBC_Z0, -IL / 2 + 0.5, yc + USBC_W / 2, USBC_Z1))
    # feritoie di raffreddamento (parete posteriore +Y e laterale +X)
    for i in range(7):
        x = (i - 3) * 7.5
        sub(A, box(x - 1.2, IW / 2 - 0.5, 8.0, x + 1.2, OW / 2 + 0.5, 26.0))
    for y in (-12.0, -4.0, 4.0, 12.0):
        sub(A, box(IL / 2 - 0.5, y - 1.2, 8.0, OL / 2 + 0.5, y + 1.2, 26.0))
    return A


# ------------------------------------------------------------------ PARTE 2: primo piano
def build_C():
    C = box(-CL / 2, -CW / 2, Z_L, CL / 2, CW / 2, Z_CT)
    sub(C, box(-CIL / 2, -CIW / 2, Z_CF, CIL / 2, CIW / 2, Z_CT + 1))

    # pavimento a griglia: feritoie per i cavi Grove / Qwiic
    gx0 = -(COLS * CELL_W + (COLS - 1) * RIB) / 2
    for i in range(COLS):
        for j in range(ROWS):
            xa = gx0 + i * (CELL_W + RIB)
            ya = GRID_Y0 + j * (CELL_H + RIB)
            sub(C, box(xa, ya, Z_L - 0.5, xa + CELL_W, ya + CELL_H, Z_CF + 0.5))

    # --- parete frontale: guide OLED + sensore luce + feritoie
    yf = -CIW / 2
    xl = -CIL / 2
    zg = Z_CF + GUIDE_H
    s0 = (xl - 0.05, xl + STEM)
    oled = (s0[1], s0[1] + OLED_W + 0.4)
    s1 = (oled[1], oled[1] + STEM)
    light = (s1[1], s1[1] + LIGHT_W + 0.4)
    s2 = (light[1], light[1] + STEM)

    def stem(xa, xb, depth):
        add(C, box(xa, yf - 0.05, Z_CF - 0.05, xb, yf + depth + LIP_T, zg))

    def lip(xa, xb, depth):
        add(C, box(xa, yf + depth, Z_CF - 0.05, xb, yf + depth + LIP_T, zg))

    stem(s0[0], s0[1], D_OLED)
    stem(s1[0], s1[1], max(D_OLED, D_LIGHT))
    stem(s2[0], s2[1], D_LIGHT)
    lip(s0[0], s0[1] + LIP, D_OLED)
    lip(s1[0] - LIP, s1[1], D_OLED)
    lip(s1[0], s1[1] + LIP, D_LIGHT)
    lip(s2[0] - LIP, s2[1], D_LIGHT)
    for (xa, xb, d) in ((oled[0], oled[1], D_OLED), (light[0], light[1], D_LIGHT)):
        add(C, box(xa, yf - 0.05, Z_CF - 0.05, xa + STOP_W, yf + d, Z_CF + MOD_LIFT))
        add(C, box(xb - STOP_W, yf - 0.05, Z_CF - 0.05, xb, yf + d, Z_CF + MOD_LIFT))

    y_out = -CW / 2 - 0.5
    ox = (oled[0] + oled[1]) / 2
    sub(C, box(ox - WIN_W / 2, y_out, Z_CF + WIN_Z0, ox + WIN_W / 2, yf + 0.02, Z_CF + WIN_Z1))
    lx = (light[0] + light[1]) / 2
    sub(C, ycyl(lx, Z_CF + MOD_LIFT + LIGHT_H / 2, y_out, yf + 0.02, LIGHT_HOLE_D / 2))
    vx0 = s2[1] + 2.0
    for i in range(N_VENT):
        x = vx0 + VENT_W / 2 + i * VENT_PITCH
        sub(C, box(x - VENT_W / 2, y_out, Z_CF + 4.0, x + VENT_W / 2, yf + 0.02, Z_CF + 25.0))

    # --- parete +X: tasca per pulsante tattile 12x12 (si infila dall'alto)
    xr = CIL / 2
    zc = Z_CF + BTN_ZC
    zt = Z_CF + 22.0
    bx0 = xr - (BTN_DEPTH + 1.2)
    half = BTN_SLOT / 2
    add(C, box(bx0, half, Z_CF - 0.05, xr + 0.05, half + 1.0, zt))
    add(C, box(bx0, -half - 1.0, Z_CF - 0.05, xr + 0.05, -half, zt))
    for sy in (-1, 1):                       # 4 tasselli d'angolo dietro il corpo del pulsante
        for sz in (-1, 1):
            ya, yb = (4.0, half + 1.0) if sy > 0 else (-half - 1.0, -4.0)
            za, zb = (zc + 4.0, zc + 7.0) if sz > 0 else (zc - 7.0, zc - 4.0)
            add(C, box(bx0, ya, za, bx0 + 1.2, yb, zb))
    add(C, box(bx0 + 1.15, -half, Z_CF - 0.05, xr + 0.05, half, zc - 6.2))   # piedistallo
    sub(C, xcyl(0, zc, xr - 0.02, CL / 2 + 0.5, BTN_HOLE_D / 2))

    # --- mensole per il coperchio (lati lunghi)
    ledge_y(C, -CIW / 2, +1, -CIL / 2 - 0.05, CIL / 2 + 0.05, Z_CT - LID_T)
    ledge_y(C, +CIW / 2, -1, -CIL / 2 - 0.05, CIL / 2 + 0.05, Z_CT - LID_T)

    # --- nervature di calettamento nella zona che entra nella base
    z0, z1 = Z_L + 0.6, Z_L + NEST - 0.2
    for x in (-17.0, 17.0):
        add(C, box(x - 0.5, -CW / 2 - RIB_H, z0, x + 0.5, -CW / 2 + 0.05, z1))
        add(C, box(x - 0.5, CW / 2 - 0.05, z0, x + 0.5, CW / 2 + RIB_H, z1))
    add(C, box(-CL / 2 - RIB_H, -0.5, z0, -CL / 2 + 0.05, 0.5, z1))
    add(C, box(CL / 2 - 0.05, -0.5, z0, CL / 2 + RIB_H, 0.5, z1))
    return C


# ------------------------------------------------------------------ PARTE 3: coperchio
def build_D():
    z0 = Z_CT - LID_T
    D = box(-LID_L / 2, -LID_W / 2, z0, LID_L / 2, LID_W / 2, Z_CT)
    for x in (-15.0, 15.0):
        add(D, box(x - 0.5, -LID_W / 2 - RIB_H, z0, x + 0.5, -LID_W / 2 + 0.05, Z_CT))
        add(D, box(x - 0.5, LID_W / 2 - 0.05, z0, x + 0.5, LID_W / 2 + RIB_H, Z_CT))
    add(D, box(-LID_L / 2 - RIB_H, -0.5, z0, -LID_L / 2 + 0.05, 0.5, Z_CT))
    add(D, box(LID_L / 2 - 0.05, -0.5, z0, LID_L / 2 + RIB_H, 0.5, Z_CT))
    return D


# ------------------------------------------------------------------ main
def _clear_previous(root, parametric):
    if parametric:
        for bf in [f for f in root.features.baseFeatures if f.name.startswith(GEN_NAME)]:
            bf.deleteMe()
    for b in [b for b in root.bRepBodies if b.name.startswith('Mole_')]:
        b.deleteMe()


def build():
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    root = design.rootComponent
    parametric = design.designType == adsk.fusion.DesignTypes.ParametricDesignType
    print('design parametrico: %s | up vector vista: %s' % (
        parametric, app.activeViewport.camera.upVector.asArray()))
    _clear_previous(root, parametric)

    parts = [('Mole_01_PianoTerra', build_A()),
             ('Mole_02_PrimoPiano', build_C()),
             ('Mole_03_Coperchio', build_D())]
    bf = None
    if parametric:
        bf = root.features.baseFeatures.add()
        bf.name = GEN_NAME
        bf.startEdit()
    for name, tb in parts:
        body = root.bRepBodies.add(tb, bf) if parametric else root.bRepBodies.add(tb)
        body.name = name
        bb = body.boundingBox
        print('%s: %.0f mm3 | X %.1f..%.1f  Y %.1f..%.1f  Z %.1f..%.1f' % (
            name, body.volume * 1000,
            bb.minPoint.x * 10, bb.maxPoint.x * 10, bb.minPoint.y * 10, bb.maxPoint.y * 10,
            bb.minPoint.z * 10, bb.maxPoint.z * 10))
    if parametric:
        bf.finishEdit()
    app.activeViewport.fit()
    print('quote: vano base %.1f x %.1f | base esterna %.1f x %.1f x %.1f | primo piano z %.1f..%.1f | totale h %.1f' % (
        IL, IW, OL, OW, HA, Z_L, Z_CT, Z_CT))
