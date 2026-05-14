#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${NF2OOD_ENV_FILE:-${SCRIPT_DIR}/nf2ood.env}"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
fi

pipeline_name=""
revision=""
install_root=""
configs_dir=""
container_engine="${NF2OOD_CONTAINER_MODULE:-singularity}"
engine_module="${NFCORE_ENGINE_MODULE:-}"
nfcore_module="${NFCORE_MODULE_NAME:-nf-core}"

usage() {
  cat <<EOF
Usage: $(basename "$0") --name PIPELINE --revision VERSION [options]

Options:
  -n, --name PIPELINE         nf-core pipeline name without the nf-core- prefix
  -r, --revision VERSION      nf-core pipeline revision
      --install-root PATH     Base install root
      --configs-dir PATH      Central configs directory to symlink
                               Maintain configs once here for all pipelines
      --container-engine NAME Container engine for nf-core download
      --engine-module NAME    Module name for the container engine
      --nfcore-module NAME    Module name for nf-core
  -h, --help                  Show this help
EOF
}

while (($# > 0)); do
  case "$1" in
    -n|--name)
      pipeline_name="$2"
      shift 2
      ;;
    -r|--revision)
      revision="$2"
      shift 2
      ;;
    --install-root)
      install_root="$2"
      configs_dir="${install_root}/configs"
      shift 2
      ;;
    --configs-dir)
      configs_dir="$2"
      shift 2
      ;;
    --container-engine)
      container_engine="$2"
      shift 2
      ;;
    --engine-module)
      engine_module="$2"
      shift 2
      ;;
    --nfcore-module)
      nfcore_module="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "${pipeline_name}" || -z "${revision}" ]]; then
  echo "Both --name and --revision are required." >&2
  usage
  exit 1
fi

# install_root defaults to the parent of NF2OOD_PIPELINE_ROOT when not set
# via --install-root. NF2OOD_PIPELINE_ROOT is required (no Tufts-flavored
# fallback) so misconfigured sites fail fast with a clear message.
if [[ -z "${install_root}" ]]; then
  if [[ -z "${NF2OOD_PIPELINE_ROOT:-}" ]]; then
    echo "Error: NF2OOD_PIPELINE_ROOT is not set and --install-root was not given." >&2
    echo "       Run 'source ./nf2ood.env' (after 'cp nf2ood.env.example nf2ood.env')." >&2
    exit 1
  fi
  install_root="$(dirname "${NF2OOD_PIPELINE_ROOT}")"
fi

# Configs are maintained centrally under <install_root>/configs.
# Each downloaded pipeline replaces its local configs directory with a symlink
# to that shared copy so site updates only need to happen in one place.
if [[ -z "${configs_dir}" ]]; then
  configs_dir="${install_root}/configs"
fi

if command -v module >/dev/null 2>&1; then
  if [[ -n "${engine_module}" ]]; then
    module load "${engine_module}"
  elif ! command -v "${container_engine}" >/dev/null 2>&1; then
    echo "Warning: ${container_engine} not found on PATH and no --engine-module was provided." >&2
  fi

  if [[ -n "${nfcore_module}" ]] && ! command -v nf-core >/dev/null 2>&1; then
    module load "${nfcore_module}"
  fi
fi

if ! command -v nf-core >/dev/null 2>&1; then
  echo "nf-core command not found." >&2
  exit 1
fi

pipeline_dir="${install_root}/pipelines/nf-core-${pipeline_name}"
version_dir="${pipeline_dir}/${revision}"
cache_dir="${install_root}/singularity-images"

export NXF_SINGULARITY_CACHEDIR="${cache_dir}"

mkdir -p "${pipeline_dir}"
cd "${pipeline_dir}"

echo "Downloading nf-core/${pipeline_name} ${revision} to ${version_dir}"

nf-core pipelines download "${pipeline_name}" \
  -r "${revision}" \
  --outdir "${revision}" \
  -d 8 \
  -s "${container_engine}" \
  --force \
  -u amend \
  -x none

cd "${version_dir}"

if [[ -d "${configs_dir}" ]]; then
  echo "Using central configs from ${configs_dir}"
  rm -rf configs
  ln -s "${configs_dir}" configs
fi

chmod -R 775 "${version_dir}"
if [[ -d "${cache_dir}" ]]; then
  chmod -R 775 "${cache_dir}"
fi

echo "Done"
