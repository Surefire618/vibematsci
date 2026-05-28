#!/bin/bash -l
#SBATCH -o %j.out
#SBATCH -e %j.err
#SBATCH -D ./
#SBATCH --ntasks=1
#SBATCH --constraint=gpu
#SBATCH --gres=gpu:a100:1
#SBATCH --cpus-per-task=18
#SBATCH --mem=125000
#SBATCH --time=02:00:00

set -euo pipefail

module purge
module load cuda/12.1 cudnn/8.9.0

export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

eval "$(micromamba shell hook --shell bash)"
micromamba activate mace

cd "${SLURM_SUBMIT_DIR}"

python build_structure.py
python run_md.py
