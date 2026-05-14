# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

_Nothing yet._

## [1.1.0] - 2026-05-14

This release focuses on portability for non-Tufts HPC centers, robustness of
the generation step, and code-quality cleanups in the bash driver and Python
helpers.

### Added

- `-V` flag prints the tool version (`nf2ood 1.1.0`) and exits.
- `-n` / `--dry-run` previews what would be generated without touching the
  output directory.
- `-p` / `--pipeline NAME` and `-v` / `--version VER` filters (both
  repeatable) for regenerating a single app in place. When either filter is
  active, unrelated apps in the output directory are preserved and `--force`
  becomes a no-op with a warning.
- `-s` / `--subcategory-map` flag plus a new top-level
  `pipeline2subcategory.tsv` data file that holds the pipeline-to-OOD
  subcategory mapping previously embedded as a 50-line `case` statement
  inside `nf2ood`.
- `-m` short alias for `--image-map`.
- `-i` / `--input` is now optional; defaults to `$NF2OOD_PIPELINE_ROOT` so
  the common workflow (`download_nfcore_pipeline.sh` -> `nf2ood`) does not
  need to repeat the path.
- End-of-run summary listing `Generated` / `Failed-skipped` /
  `Non-version dirs ignored` counts and per-entry lists. `nf2ood` exits
  non-zero if any pipeline failed.

### Changed

- `nf2ood.env` is now gitignored; the checked-in example is
  `nf2ood.env.example`. New workflow:
  `cp nf2ood.env.example nf2ood.env && source ./nf2ood.env`.
- Site environment variables are validated up front:
  - **REQUIRED** (die at startup, pointing at `nf2ood.env.example`):
    `NF2OOD_PIPELINE_ROOT`, `NF2OOD_SINGULARITY_CACHEDIR`,
    `NF2OOD_PARTITION_YML`.
  - **SOFT (warn)**: `NF2OOD_SLURM_PROFILE` falls back to `default` with a
    one-shot warning when unset.
  - **SOFT**: `NF2OOD_CLUSTER`, `NF2OOD_DEFAULT_DIRECTORY`,
    `NF2OOD_MODULE_NAME`, `NF2OOD_CONTAINER_MODULE`, `NF2OOD_ENV_FILE`
    keep cross-site safe defaults.
- `NF2OOD_MODULE_NAME=""` and `NF2OOD_CONTAINER_MODULE=""` are now honored
  as "skip this `module load`", letting sites with system-installed
  Nextflow / Singularity / Apptainer opt out of the corresponding module
  load. The runtime wrapper continues to auto-skip the whole block on
  compute nodes with no `module` command at all.
- Version-directory filter tightened from "starts with a digit" to a
  SemVer-ish regex (`^[0-9]+\.[0-9]`), so `dev`, `latest`, `main`, etc.
  are skipped automatically (reported as informational, not warnings).
- README restructured for site-agnostic onboarding: new "Quick start"
  recipe, "Configuration reference" grouped by REQUIRED / SOFT (warn) /
  SOFT, dedicated "Subcategory mapping" section, "Institutional profile
  (Tufts example)" heading making the Tufts framing explicit.
- App-customization rewritten as a single Python pass. New
  `customize_app.py` walks the known set of template files and applies
  every `--set TOKEN=VALUE` substitution at once, replacing ~24 per-app
  `perl -0pi -e` shellouts with one Python invocation per app.
- The Ruby ERB header for `nf-params.json.erb` (the `to_bool` / `to_number`
  helpers and the surrounding params hash) lives in
  `nfcore_ood_template/nf-params.template.erb` with an
  `__NF_PARAMS_ENTRIES__` placeholder, instead of being a Python
  triple-quoted string in `json2ood.py`.
- `.gitignore` expanded with common macOS / Windows OS files, IDE
  droppings, Python build/cache, logs, and merge debris.

### Removed

- Nextflow Tower / Seqera Platform `tower_access_token` widget and the
  related `-with-tower` runtime handling. Sites that still need this can
  fork the template; the helpers were never used at Tufts.
- Duplicate `resetBatchConnectFormOnce` definition and standalone
  `DOMContentLoaded` listener in `nfcore_ood_template/form.js`.
- `perl` runtime dependency. Token substitution is now Python.
- Tufts-flavored hardcoded fallback paths in `nf2ood` and
  `download_nfcore_pipeline.sh`. Affected variables now either fail-fast
  (REQUIRED) or use neutral cross-site defaults.

### Fixed

- A missing `nextflow_schema.json` for one pipeline no longer aborts the
  whole run. The pipeline is warned, skipped, and reported in the summary;
  `nf2ood` exits non-zero overall but all sibling pipelines still get a
  chance to generate.
- `json2ood.py` now loads on Python 3.8 / 3.9, which are still common on
  HPC login and compute nodes. (A `str | int | float | bool | None`
  runtime expression had crashed module load there.)
- `generate_app` failures (for example a `json2ood.py` crash on a
  malformed schema) are now reliably caught and reported as
  Failed/skipped. Previously bash's `set -e` suppression inside `if` test
  contexts caused such failures to be silently absorbed: the app was
  counted as generated even though its `form.yml.erb` and
  `template/nf-params.json.erb` were missing. The partial app directory
  is also cleaned up on failure so future runs do not see half-rendered
  state.

### Upgrading from previous versions

1. `git pull` and `cp nf2ood.env.example nf2ood.env`, then edit your
   local `nf2ood.env` so the three REQUIRED variables point at your site
   paths.
2. If your site does not have Nextflow or Singularity as environment
   modules, add `export NF2OOD_MODULE_NAME=""` and/or
   `export NF2OOD_CONTAINER_MODULE=""` to your `nf2ood.env`.
3. Generated apps will no longer contain a Tower access token field.
   Existing OOD apps continue to work; regenerate them with `nf2ood -p
   <name>` to pick up this and other template changes.
4. The `--input` argument is no longer required as long as
   `NF2OOD_PIPELINE_ROOT` is set; existing scripts that pass `--input`
   explicitly continue to work unchanged.

## [1.0.0] - initial public release

First public release of `nf2ood`. Generates Open OnDemand batch-connect
apps from locally downloaded nf-core pipelines, including the download
step (`download_nfcore_pipeline.sh`) and the schema-to-form converter
(`json2ood.py`). No explicit version tag; see git history for details.

[Unreleased]: https://github.com/TuftsRT/nfcore2ood/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/TuftsRT/nfcore2ood/compare/5d20ce7...v1.1.0
[1.0.0]: https://github.com/TuftsRT/nfcore2ood/tree/5d20ce7
