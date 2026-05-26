# Whitebox Next Gen ArcGIS

ArcGIS Pro Python Toolbox frontend for Whitebox Next Gen.

The main toolbox is `WhiteboxNextGen.pyt`. Add this repository as a folder
connection in ArcGIS Pro, then open the toolbox from the Catalog pane.

## Runtime

This toolbox calls the `whitebox_workflows` Python package. Install the package
in either ArcGIS Pro's Python environment or a separate Python environment and
point the toolbox at it:

```bash
export WBW_EXTERNAL_PYTHON=/path/to/python
```

Useful environment variables:

- `WBW_EXTERNAL_PYTHON`: Python executable that can import `whitebox_workflows`.
- `WBW_ARCGIS_RUNTIME_MODE`: `auto`, `external`, or `arcgis`; default `auto`.
- `WBW_ARCGIS_INCLUDE_PRO`: whether to request Pro catalog visibility; default `true`.
- `WBW_ARCGIS_TIER`: requested tier; default `open`.

Use the `Runtime Diagnostics` tool first to confirm the active runtime.

## Development

Regenerate the catalog snapshot from the local Next Gen checkout:

```bash
python scripts/generate_catalog_snapshot.py
```

Run local smoke tests without ArcGIS:

```bash
python -m pytest tests
```
