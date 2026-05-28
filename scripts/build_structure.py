"""Build a cubic water box with optional bottom-layer ice framework, driven by config.json."""
import json
import numpy as np
from ase import Atoms
from ase.io import write
from ase.neighborlist import neighbor_list

CFG = json.load(open('config.json'))
rng = np.random.default_rng(42)

A_IC      = 6.358                                      # cubic ice Ic lattice constant (Å)
OH_BOND   = 0.96
HOH_ANGLE = 104.5
MIN_OO    = 2.5                                        # rejection radius for liquid insertion

SUPERCELL       = max(1, round(float(CFG['box_size_A']) / A_IC))
L               = A_IC * SUPERCELL
N_FIXED_LAYERS  = min(SUPERCELL, max(0, int(CFG['n_fixed_layers'])))  # in units of unit cells
ICE_TOP_Z       = N_FIXED_LAYERS * A_IC

print(f"Box: {L:.3f} Å (supercell {SUPERCELL}³)")
print(f"Fixed ice layers: {N_FIXED_LAYERS} (z < {ICE_TOP_Z:.3f} Å)")

# -- oxygens on diamond lattice (cubic ice Ic) --------------------------------
frac_O = np.array([
    [0.00, 0.00, 0.00], [0.00, 0.50, 0.50],
    [0.50, 0.00, 0.50], [0.50, 0.50, 0.00],
    [0.25, 0.25, 0.25], [0.25, 0.75, 0.75],
    [0.75, 0.25, 0.75], [0.75, 0.75, 0.25],
])
oxy = (Atoms('O8', scaled_positions=frac_O,
             cell=np.eye(3) * A_IC, pbc=True)
       * (SUPERCELL, SUPERCELL, SUPERCELL))
print(f"Oxygens generated: {len(oxy)}")

# -- build ice (O+H) for the bottom N_FIXED_LAYERS unit cells -----------------
ice_atoms = Atoms(cell=np.eye(3) * L, pbc=True)
placed_O  = []
if N_FIXED_LAYERS > 0:
    i_idx, j_idx, D_vec = neighbor_list('ijD', oxy, cutoff=3.0)
    nbrs = {k: [] for k in range(len(oxy))}
    for a, b, d in zip(i_idx, j_idx, D_vec):
        nbrs[a].append(d)

    keep_O = [k for k, p in enumerate(oxy.positions) if p[2] < ICE_TOP_Z]
    H_pos = []
    for o_idx in keep_O:
        vecs = sorted(nbrs[o_idx], key=np.linalg.norm)[:4]
        pick = rng.choice(4, size=2, replace=False)
        for p in pick:
            v = vecs[p] / np.linalg.norm(vecs[p])
            H_pos.append(oxy.positions[o_idx] + OH_BOND * v)

    ice_atoms += Atoms('O' * len(keep_O),
                       positions=oxy.positions[keep_O],
                       cell=oxy.cell, pbc=True)
    ice_atoms += Atoms('H' * len(H_pos),
                       positions=H_pos, cell=oxy.cell, pbc=True)
    placed_O = list(oxy.positions[keep_O])
print(f"Ice atoms (fixed): {len(ice_atoms)} ({len(placed_O)} O)")

# -- random water template ----------------------------------------------------
half = np.deg2rad(HOH_ANGLE) / 2
H_template = OH_BOND * np.array([
    [np.sin(half), 0.0, np.cos(half)],
    [-np.sin(half), 0.0, np.cos(half)],
])

def random_water(center):
    Q, _ = np.linalg.qr(rng.standard_normal((3, 3)))
    if np.linalg.det(Q) < 0:
        Q[:, 0] *= -1
    h = H_template @ Q.T
    return center, center + h[0], center + h[1]

# -- fill remaining volume with liquid waters at ice-Ic O number density -------
N_total   = SUPERCELL**3 * 8
N_liquid  = N_total - len(placed_O)
new_O     = []
attempts  = 0
max_attempts = 500_000
z_lo      = ICE_TOP_Z + 0.5 if N_FIXED_LAYERS > 0 else 0.5

while len(new_O) < N_liquid and attempts < max_attempts:
    attempts += 1
    candidate = np.array([
        rng.uniform(0, L),
        rng.uniform(0, L),
        rng.uniform(z_lo, L - 0.5),
    ])
    ok = True
    for p in placed_O:
        d = candidate - p
        d -= L * np.round(d / L)
        if np.dot(d, d) < MIN_OO**2:
            ok = False
            break
    if ok:
        new_O.append(candidate)
        placed_O.append(candidate)

print(f"Inserted {len(new_O)} liquid waters in {attempts} attempts")

liquid_atoms = Atoms(cell=np.eye(3) * L, pbc=True)
for o in new_O:
    o_pos, h1, h2 = random_water(o)
    liquid_atoms += Atoms('OHH', positions=[o_pos, h1, h2])

system = ice_atoms + liquid_atoms
system.set_cell(np.eye(3) * L)
system.set_pbc(True)
system.wrap()

n_water  = sum(1 for s in system.symbols if s == 'O')
density  = n_water * 18.015 / 6.022e23 / (L * 1e-8)**3
n_fixed  = len(ice_atoms)
print(f"Final: {len(system)} atoms, {n_water} H₂O, ρ={density:.3f} g/cm³, n_fixed={n_fixed}")

write('initial.xyz',  system)
write('initial.traj', system)
with open('n_fixed_atoms.txt', 'w') as f:
    f.write(f"{n_fixed}\n")
print("Wrote initial.xyz, initial.traj, n_fixed_atoms.txt")
