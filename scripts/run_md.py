"""Run NVT or NPT MD with MACE-MPA-0, driven by config.json."""
import json
import time
from ase import units
from ase.constraints import FixAtoms
from ase.io import read
from ase.io.trajectory import Trajectory
from ase.md.langevin import Langevin
from ase.md.nptberendsen import NPTBerendsen
from ase.md.velocitydistribution import MaxwellBoltzmannDistribution, Stationary
from mace.calculators import mace_mp

CFG = json.load(open('config.json'))

TEMPERATURE_K = float(CFG['temperature_K'])
PRESSURE_GPa  = CFG.get('pressure_GPa', None)
TIMESTEP_FS   = float(CFG['timestep_fs'])
N_STEPS       = int(CFG['n_steps'])
LOG_EVERY     = int(CFG['log_every'])
TRAJ_EVERY    = int(CFG['traj_every'])
FRICTION      = 0.01 / units.fs

atoms = read('initial.xyz')
print(f"Loaded {len(atoms)} atoms, cell = {atoms.cell.lengths()}")

with open('n_fixed_atoms.txt') as f:
    n_fixed = int(f.read().strip())
if n_fixed > 0:
    atoms.set_constraint(FixAtoms(indices=list(range(n_fixed))))
    print(f"Fixed first {n_fixed} atoms (ice framework)")

calc = mace_mp(model="medium-mpa-0", device="cuda", default_dtype="float32")
atoms.calc = calc

MaxwellBoltzmannDistribution(atoms, temperature_K=TEMPERATURE_K)
Stationary(atoms)

if PRESSURE_GPa is None:
    print(f"Ensemble: NVT (Langevin) at {TEMPERATURE_K} K")
    dyn = Langevin(
        atoms,
        timestep=TIMESTEP_FS * units.fs,
        temperature_K=TEMPERATURE_K,
        friction=FRICTION,
    )
else:
    print(f"Ensemble: NPT (Berendsen) at {TEMPERATURE_K} K, {PRESSURE_GPa} GPa")
    dyn = NPTBerendsen(
        atoms,
        timestep=TIMESTEP_FS * units.fs,
        temperature_K=TEMPERATURE_K,
        pressure_au=float(PRESSURE_GPa) * units.GPa,
        compressibility_au=4.57e-5 / units.bar,
        taut=100 * units.fs,
        taup=1000 * units.fs,
    )

traj = Trajectory('md.traj', 'w', atoms)
dyn.attach(traj.write, interval=TRAJ_EVERY)

log_file = open('md.log', 'w', buffering=1)
log_file.write("# step  time_ps   T_K     Epot_eV     Ekin_eV    Etot_eV  step_s\n")
t0 = time.time()
last = [t0]

def log():
    now  = time.time()
    step = dyn.nsteps
    epot = atoms.get_potential_energy()
    ekin = atoms.get_kinetic_energy()
    n_mobile = len(atoms) - n_fixed
    T = ekin / (1.5 * units.kB * n_mobile) if n_mobile else 0.0
    dt_step = (now - last[0]) / max(LOG_EVERY, 1)
    last[0] = now
    log_file.write(
        f"{step:8d} {step*TIMESTEP_FS*1e-3:9.4f} "
        f"{T:8.2f} {epot:12.4f} {ekin:10.4f} {epot+ekin:12.4f} {dt_step:7.3f}\n"
    )

dyn.attach(log, interval=LOG_EVERY)

print(f"Starting MD: {N_STEPS} steps × {TIMESTEP_FS} fs = "
      f"{N_STEPS*TIMESTEP_FS/1000:.1f} ps")
dyn.run(N_STEPS)

log_file.close()
traj.close()
print(f"Done in {time.time()-t0:.1f} s")
