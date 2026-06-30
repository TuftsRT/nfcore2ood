# nf2ood

**Version: 1.4.0** &middot; [CHANGELOG](./CHANGELOG.md)

`nf2ood` generates Open OnDemand batch-connect apps from locally downloaded
nf-core pipelines. The repository includes both the download step and the
pipeline-to-Open-OnDemand app generation step.

Print the installed version at any time with:

```bash
./nf2ood -V
```

<img src="docs/icon.png" alt="nf2ood icon" width="30%">

## Demo

This recording shows how to download an nf-core pipeline with
[`download_nfcore_pipeline.sh`](./download_nfcore_pipeline.sh)
and then run [`nf2ood`](./nf2ood)
to generate Open OnDemand apps.

https://github.com/user-attachments/assets/bc7234ff-5b9c-42a0-b616-44f5f6d57eaa

## Prerequisites

- `python3`
- Open OnDemand 3.1 or newer for generated checkbox hide/show behavior
- a local copy of nf-core pipeline downloads that include `nextflow_schema.json`
- the site-specific modules and paths needed by [`download_nfcore_pipeline.sh`](./download_nfcore_pipeline.sh)

## What `nf2ood` does

- discovers nf-core pipelines and versions under an input directory
- locates `nextflow_schema.json` for each pipeline version
- converts schema fields into `form.yml` and `template/nf-params.json.erb`
- creates one Open OnDemand app directory per pipeline version
- writes a per-app `README.md` for deployment review

## Quick start

The recipe below is site-agnostic; values shown in
[`nf2ood.env.example`](./nf2ood.env.example) are Tufts examples that you
should edit for your own HPC center.

```bash
# 1. Create your local site config (gitignored) from the example.
cp nf2ood.env.example nf2ood.env
# edit nf2ood.env so the REQUIRED variables point at your site paths

# 2. Load the site config.
source ./nf2ood.env

# 3. Download an nf-core pipeline into your local pipeline tree.
./download_nfcore_pipeline.sh --name taxprofiler --revision 1.2.6

# 4. Generate Open OnDemand apps from that tree.
#    --input defaults to $NF2OOD_PIPELINE_ROOT so you can omit it when
#    you want to process the same tree the downloader installed into.
./nf2ood --output /path/to/generated-apps
```

`nf2ood` validates the required variables up front and dies with a clear
message if any are missing. See [Configuration reference](#configuration-reference)
for the full list, and [Institutional profile (Tufts example)](#institutional-profile-tufts-example)
for the worked Tufts deployment that ships with the repo.

## Recommended deployment flow

For other centers deploying nf-core workflows on Open OnDemand, the intended
workflow is:

1. Use [`download_nfcore_pipeline.sh`](./download_nfcore_pipeline.sh)
   to download nf-core pipelines onto local storage.
2. Run [`nf2ood`](./nf2ood) against
   that local pipeline tree to generate Open OnDemand apps.

This keeps pipeline installation separate from app generation and makes it
easier to adapt the deployment for another site.

## Step 1: Download pipelines locally

[`download_nfcore_pipeline.sh`](./download_nfcore_pipeline.sh)
downloads a selected nf-core pipeline and revision into a local pipeline
directory structure that `nf2ood` can consume later.

Make sure your site environment file is in place (see
[Quick start](#quick-start)) and then source it before running the
downloader so the downloader and generator share the same site config:

```bash
source ./nf2ood.env
./download_nfcore_pipeline.sh --name taxprofiler --revision 1.2.6
```

The script currently:

- loads modules only when needed for your site
- downloads the requested pipeline with `nf-core pipelines download`
- stores the pipeline under a local `nf-core-<name>/<version>` directory
- replaces the per-pipeline `configs` directory with a symlink to the shared central copy
- allows site overrides through CLI flags while using defaults from `nf2ood.env`

Configs are maintained centrally under the shared nf-core install root, usually
`<install-root>/configs`. The downloader removes the downloaded local `configs`
directory and points each pipeline to that shared copy instead. This means you
update configs once in the central location and all downloaded pipelines use
the same maintained set.

The downloader does not require a container engine module. If `apptainer` or
`singularity` is already installed on `PATH`, the script can use it directly.
Use `--engine-module <name>` only at sites where the engine must be loaded as
a module first.

Important:

The downloader requires `NF2OOD_PIPELINE_ROOT` (or `--install-root`) to be
set; it does not assume a Tufts-style default. The Tufts-specific paths
shipped in [`nf2ood.env.example`](./nf2ood.env.example) are illustrative
and must be edited in your local `nf2ood.env` before downloading pipelines
at another site.

## Configuration reference

All site configuration lives in your local `nf2ood.env`, copied from
[`nf2ood.env.example`](./nf2ood.env.example) (which is the version checked
in). `nf2ood.env` itself is gitignored so site values stay local.

```bash
cp nf2ood.env.example nf2ood.env  # one time
# edit nf2ood.env for your site
source ./nf2ood.env
./nf2ood --output /path/to/generated-apps
# equivalent to: ./nf2ood --input "$NF2OOD_PIPELINE_ROOT" --output /path/to/generated-apps
```

Variables are grouped by how `nf2ood` treats them when they are unset.

**REQUIRED** — `nf2ood` dies at startup if any of these are unset:

- `NF2OOD_PIPELINE_ROOT`: root directory containing installed nf-core pipelines
- `NF2OOD_SINGULARITY_CACHEDIR`: Singularity or Apptainer cache path
- `NF2OOD_PARTITION_YML`: path to the partition YAML snippet baked into generated `form.yml`.
  If this is unset, `nf2ood` falls back to `./cpu_partition.yml` in the current
  working directory.

**SOFT (warn)** — `nf2ood` falls back to a placeholder and logs a one-shot
warning:

- `NF2OOD_SLURM_PROFILE`: Nextflow profile used for scheduler-backed runs;
  fallback is `default`, which is not site-specific.

**SOFT** — `nf2ood` silently uses a safe cross-site default when unset:

- `NF2OOD_CLUSTER` (default `cluster`): Open OnDemand cluster id written into `form.yml`
- `NF2OOD_DEFAULT_DIRECTORY` (default `$HOME`): default working directory shown in the app form
- `NF2OOD_MODULE_NAME` (default `nextflow`, `""` to skip): name of the Nextflow environment module the generated job wrapper should `module load`. Set explicitly to `""` if your site installs Nextflow system-wide and there is no module to load.
- `NF2OOD_CONTAINER_MODULE` (default `singularity`, `""` to skip): name of the container-engine environment module to `module load` at job runtime. Set explicitly to `""` for sites where Singularity / Apptainer is installed as an OS package rather than as an environment module. The runtime wrapper also auto-skips module loading entirely on compute nodes that have no `module` function at all.
- `NF2OOD_ENV_FILE` (default empty): path that generated runtime scripts will try to source

Downloader defaults are derived from those settings:

- install root defaults to the parent directory of `NF2OOD_PIPELINE_ROOT`
  (the downloader also accepts `--install-root` to override)
- configs dir defaults to `<install-root>/configs`
- container engine defaults to `NF2OOD_CONTAINER_MODULE`

## Institutional profile (Tufts example)

[`nf2ood.env.example`](./nf2ood.env.example) is shipped with Tufts values
to illustrate a working configuration. The Tufts institutional nf-core
profile, `-profile tufts`, is published in
[`nf-core/configs`](https://nf-co.re/configs/tufts/) and is the
site-specific execution profile used for Tufts HPC deployments. It is
referenced by `NF2OOD_SLURM_PROFILE="tufts"` in
[`nf2ood.env.example`](./nf2ood.env.example).

Other centers should not reuse the Tufts profile as-is. The recommended
approach is:

1. Create and maintain your own institutional profile in
   [`nf-core/configs`](https://nf-co.re/configs/).
2. Set `NF2OOD_SLURM_PROFILE` to that profile name in your local
   `nf2ood.env`.

That keeps scheduler settings, partitions, modules, storage paths, and
local site policies aligned with your own HPC environment. If you leave
`NF2OOD_SLURM_PROFILE` unset, `nf2ood` warns at startup and the generated
apps will use a placeholder profile name, which will not match any real
profile.

Important runtime note:

The generated job wrapper will try to source `NF2OOD_ENV_FILE` again at job
runtime. By default, `nf2ood.env` sets this to the `nf2ood.env` file next to
[`nf2ood`](./nf2ood). That only works
if the same path is visible from the Open OnDemand host and compute nodes.

## Step 2: Generate Open OnDemand apps

Source your local environment file first:

```bash
source ./nf2ood.env
./nf2ood --output /path/to/generated-apps
```

`--input` defaults to `$NF2OOD_PIPELINE_ROOT` when omitted, so the
command above scans the same pipeline tree the downloader installs
into. Pass `-i/--input PATH` explicitly to scan a different tree.

Optional flags:

- `-i, --input PATH`: directory containing nf-core pipeline directories.
  Defaults to `$NF2OOD_PIPELINE_ROOT` when unset.
- `-s, --subcategory-map /path/to/pipeline2subcategory.tsv`: override the default
  pipeline-to-subcategory map
- `-p, --pipeline NAME`: only process pipelines matching `NAME` (accepts
  `nf-core-rnaseq` or just `rnaseq`). Repeatable.
- `-v, --version VER`: only process versions matching `VER` (e.g. `3.18.0`).
  Repeatable.
- `-f, --force`: delete the existing output directory before regeneration.
  Ignored when `--pipeline` or `--version` is given so unrelated apps in the
  output directory are preserved.
- `-n, --dry-run`: print what would be generated without writing any files.

When `--pipeline` or `--version` is set, the output directory is reused; only
the matching app directories are regenerated and other apps are left alone.
This is the recommended way to refresh a single app after a pipeline update
without rebuilding the whole tree.

A final summary lists how many apps were generated, how many failed (e.g.
missing `nextflow_schema.json`), and how many non-version directories like
`dev` or `latest` were ignored. `nf2ood` exits non-zero if any pipeline
failed.

Help:

```bash
./nf2ood --help
```

## Input layout

`nf2ood` expects one directory per pipeline and one directory per version. It
looks for `nextflow_schema.json` in the common nf-core download layouts.

```text
pipelines/
├── nf-core-rnaseq/
│   └── 3.18.0/
│       └── 3_18_0/
│           └── nextflow_schema.json
└── nf-core-bamtofastq/
    └── 2.1.1/
        └── 2_1_1/
            └── nextflow_schema.json
```

Schema discovery currently checks these locations in order:

```text
<input>/<pipeline>/<version>/<version_underscored>/nextflow_schema.json
<input>/<pipeline>/<version>/nextflow_schema.json
<input>/<pipeline>/<version_underscored>/nextflow_schema.json
<input>/<pipeline>/nextflow_schema.json
```

## Generated app contents

Each generated app directory includes:

- `manifest.yml`
- `form.yml`
- `form.js`
- `submit.yml.erb`
- `view.html.erb`
- `template/before.sh.erb`
- `template/script.sh.erb`
- `template/nf-params.json.erb`
- `README.md`
- app assets from the shared template such as `icon.png`, `LICENSE.txt`, and `CHANGELOG.md`

## Current generated behavior

- the partition field is baked into `form.yml` from `NF2OOD_PARTITION_YML`, or
  from `./cpu_partition.yml` when that file exists in the current working directory
- the default working directory is baked into `form.yml` from `NF2OOD_DEFAULT_DIRECTORY`
- the runtime script can load both a workflow module and a container module
- local executor mode generates a small `custom.config`
- Slurm mode runs `nextflow` with the configured `NF2OOD_SLURM_PROFILE`
- generated schema field names are normalized so Open OnDemand hide rules do
  not break when digits appear inside field names
- generated checkbox `data-hide-...-when-un-checked` behavior requires Open
  OnDemand 3.1 or newer

## Subcategory mapping

By default, `nf2ood` uses
[`pipeline2subcategory.tsv`](./pipeline2subcategory.tsv) when it exists. That
file maps pipeline names to Open OnDemand subcategories (`rnaseq`, `genomics`,
`singlecell`, etc.) used in each generated `manifest.yml`.

Format is a two-column TSV:

```text
<pipeline_name>\t<subcategory>
```

If a pipeline is not listed, the subcategory falls back to:

- the pipeline slug (everything after the `nf-core-` prefix), for
  `nf-core-*` pipelines
- `bioinformatics`, for anything else

Override the default path with `-s, --subcategory-map`.

## Portability notes

This repository is more configurable than the earlier script, but the generated
apps still assume:

- Open OnDemand batch connect conventions
- a partition partial file compatible with your site
- a module environment if you want module loading
- an nf-core pipeline installation layout under `NF2OOD_PIPELINE_ROOT`
- a scheduler profile name understood by your local nf-core pipeline installs

Those are the main areas to review before sharing the generated apps with other
centers or preparing an Appverse submission.

## Contributor

<img src="https://github.com/zhan4429.png" alt="Yucheng Zhang" width="120">

Yucheng Zhang  
Research Technology, Tufts Technology Services  
Tufts University  
yucheng.zhang@tufts.edu

## License

This repository is released under the MIT License. See [LICENSE](LICENSE).
