# Numbered Runner Scripts

Run from repository root (`C:\Excalibur\news`) inside the `news` Conda environment.

## Full Pipeline

```powershell
python scripts\00_run_all.py
```

`00_run_all.py` executes the numbered scripts in order:
`01_ingest.py` -> `02_synthesize.py` -> `03_apply_profile.py` -> `04_render.py`

## Step Scripts

```powershell
python scripts\01_ingest.py
python scripts\02_synthesize.py
python scripts\03_apply_profile.py
python scripts\04_render.py
```

## Common Flags

- `--llm` / `--no-llm`
- `--source-config config\sources.yaml`
- `--synthesis-config config\synthesis.yaml`
- `--profile-config config\reader_profiles.yaml`
- `--db-path data\news.db`
- `--output-dir output`
