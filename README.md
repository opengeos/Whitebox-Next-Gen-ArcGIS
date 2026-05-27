# ArcGIS Frontend for Whitebox Next Gen

ArcGIS Pro Python Toolbox frontend for [Whitebox Next Gen](https://github.com/jblindsay/whitebox_next_gen).

The main toolbox is `WhiteboxNextGen.pyt`.

## Using the Toolbox

1. Download and connect the toolbox.

   Download this repository from GitHub or download a release archive. Unzip the
   archive to a local folder. In ArcGIS Pro, add that folder as a folder
   connection, then open `WhiteboxNextGen.pyt` from the Catalog pane. When you open the toolbox for the first time, it will prompt you to confirm that you trust the source before proceeding. Click "Yes" to continue.

   ![](https://github.com/user-attachments/assets/a782297e-2964-4b82-ac1c-d3a1afbb9537)

   After a few seconds, the toolbox should load and show the tool categories and tools.

   ![](https://github.com/user-attachments/assets/6e4e77b8-14c9-4d95-a49b-182e4c3e9631)

2. Run `Install Required Packages`.

   Select the **Install Required Packages** tool and run it. This will install `whitebox-workflows` into the selected Python environment. The
   default Python executable points to ArcGIS Pro's default Python environment.
   If that environment is not writable, clone the ArcGIS Pro environment first
   or select another Python executable that ArcGIS Pro can run.

   ![](https://github.com/user-attachments/assets/81bdf019-7dda-4766-bca0-53946505ce0e)

3. Run `Runtime Diagnostics`.

   Run the **Runtime Diagnostics** tool to check that the toolbox can find and import `whitebox_workflows`. If the diagnostics fail, check the error message and adjust your configuration as needed. If the diagnostics succeed, you should see a success message.

   ![](https://github.com/user-attachments/assets/e4b1aa58-9676-4b20-84ab-8f0887d5a8c2)

   Click "View Details" to see the diagnostic report, which includes information about the Python environment and the number of tools that should be available based on the catalog snapshot.

   ![](https://github.com/user-attachments/assets/b19cb54f-7301-4525-ac08-3f9af042ee21)

4. Run tools.

   Choose any tool from the toolbox categories, set input datasets and output
   file paths, then run the tool. Outputs should be saved as files in the
   project folder, not inside a geodatabase.

   ![](https://github.com/user-attachments/assets/32cfd378-9f13-4d2b-8f85-bba01ff11945)

## Runtime Configuration

This toolbox calls the `whitebox_workflows` Python package. If the package is in
a separate Python environment, point the toolbox at it:

```bash
export WBW_EXTERNAL_PYTHON=/path/to/python
```

Useful environment variables:

- `WBW_EXTERNAL_PYTHON`: Python executable that can import `whitebox_workflows`.
- `WBW_ARCGIS_RUNTIME_MODE`: `auto`, `external`, or `arcgis`; default `auto`.
- `WBW_ARCGIS_INCLUDE_PRO`: whether to request Pro catalog visibility; default `true`.
- `WBW_ARCGIS_TIER`: requested tier; default `open`.

### Pro License Configuration

Pro tools require a Whitebox Workflows build with Pro support and a valid Pro
license. Set these variables in the environment used to launch ArcGIS Pro, then
restart ArcGIS Pro and run `Runtime Diagnostics`.

Common Pro settings:

- `WBW_ARCGIS_TIER`: set to `pro`.
- `WBW_ARCGIS_INCLUDE_PRO`: set to `true`.
- `WBW_ARCGIS_FALLBACK_TIER`: fallback tier if license activation fails; default `open`.

Floating license:

- `WBW_ARCGIS_LICENSE_MODE`: set to `floating`.
- `WBW_ARCGIS_FLOATING_LICENSE_ID`: floating license ID, for example `fl_12345`.
- `WBW_ARCGIS_LICENSE_PROVIDER_URL` (or `WBW_LICENSE_PROVIDER_URL`): license provider URL.
- `WBW_ARCGIS_MACHINE_ID`: optional machine identifier.
- `WBW_ARCGIS_CUSTOMER_ID`: optional customer identifier.

Signed entitlement from a file:

- `WBW_ARCGIS_LICENSE_MODE`: set to `signed_file`.
- `WBW_ARCGIS_SIGNED_ENTITLEMENT_FILE`: path to signed entitlement JSON.
- `WBW_ARCGIS_PUBLIC_KEY_KID`: public key ID.
- `WBW_ARCGIS_PUBLIC_KEY_B64URL`: provider public key.

Signed entitlement from an environment variable:

- `WBW_ARCGIS_LICENSE_MODE`: set to `signed_json`.
- `WBW_ARCGIS_SIGNED_ENTITLEMENT_JSON`: signed entitlement JSON string.
- `WBW_ARCGIS_PUBLIC_KEY_KID`: public key ID.
- `WBW_ARCGIS_PUBLIC_KEY_B64URL`: provider public key.

The licensing modes mirror the upstream Whitebox Workflows Python startup
patterns documented in the
[Whitebox Workflows README](https://github.com/jblindsay/whitebox_next_gen/blob/main/crates/wbw_python/README.md#licensing-and-pro-workflows).

## Development

Regenerate the catalog snapshot from the local Next Gen checkout:

```bash
python scripts/generate_catalog_snapshot.py
```

Run local smoke tests without ArcGIS:

```bash
python -m pytest tests
```
