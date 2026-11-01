## DESCRIPTION

*i.hyper.lib_ossl* harvests the **Open Soil Spectral Library** (OSSL,
[soilspectroscopy.org](https://soilspectroscopy.org/)) into the same shared,
source-tagged, partitioned local spectral database used by
*i.hyper.lib_ecosis*, *i.hyper.lib_usgs*, *i.hyper.lib_relab* and
*i.hyper.lib_gsti*, by default at `$HOME/grassdata/hyperspeclib`.

The OSSL is the largest open compilation of soil spectra, pairing
mid-infrared, visible/near-infrared and near-infrared laboratory scans with
the measured soil properties of the very same layer (organic carbon,
texture, pH, CEC, carbonates and dozens more). It is the soil counterpart to
the vegetation and mineral sources already harvested by this family: where
*i.hyper.lib_gsti* supplies leaf spectra with plant traits and
*i.hyper.lib_usgs* supplies mineral endmembers, this module supplies soil
spectra with soil chemistry.

Each harvested record becomes one row in the common
[row schema](#row-schema), so all five sources can be queried together in a
single `pyarrow.dataset` scan and are found by
*i.hyper.speclookup*.

### Two harvest routes

The OSSL is published in two different ways, and they do not carry the same
content, so the module implements both and `source=` selects between them.

| | `source=gcs` (default) | `source=api` |
|---|---|---|
| Origin | v1.3 per-dataset bulk files on Google Cloud Storage | experimental REST API at `api.soilspectroscopy.org` |
| Datasets | 20 | 10 (different codes) |
| Scan domains | MIR, VisNIR, **NIR** | MIR, VisNIR only |
| Filtering | `bbox=`, `depth_*=`, `var*=` applied locally | all of those, plus `nation=`, `state=`, `soil_texture=`, applied server-side |
| Volume | about 2.2 GB gzipped for everything | one request per station chunk |
| Stability | static files, reliable | experimental, rate-limited, sometimes down |

**The NIR (Neospectra-class) scans exist only in the bulk files.** Asking for
`scans=nir` with `source=api` raises a warning and drops that domain. If you
want everything, use the default `source=gcs`.

Conversely, only the API understands `nation=`, `state=` and
`soil_texture=`, because those are server-side joins against the OSSL's own
site table. With `source=gcs` those three options are ignored with a
warning; `bbox=`, `depth_min=`/`depth_max=` and `var=`/`var_min=`/`var_max=`
work on both routes, because the module re-applies them locally.

### Spectral axes and units

The OSSL encodes its three domains differently, and the module preserves the
distinction in the `measurement_type` and `wavelength_unit` columns:

| Domain | Measurement | Native axis |
|---|---|---|
| `mir` | absorbance, log10(1/R) | 600-4000 cm<sup>-1</sup>, 2 cm<sup>-1</sup> steps |
| `visnir` | reflectance, 0-1 | 350-2500 nm |
| `nir` | reflectance, 0-1 | 1100-2550 nm, varying by dataset |

Because the other four `i.hyper.lib_*` sources are all in nanometres, and
*i.hyper.speclookup*'s `min_wavelength=`/`max_wavelength=` filters assume
nanometres, **MIR is converted to nm by default** (`mir_axis=nm`), using
nm = 10<sup>7</sup> / cm<sup>-1</sup>. The conversion inverts the ordering,
so the stored axis is re-sorted ascending and each value stays with its own
band: 600-4000 cm<sup>-1</sup> becomes 2500-16666.7 nm. Pass
`mir_axis=wavenumber` to keep the native cm<sup>-1</sup> axis instead, which
is what you want for spectroscopic work on the MIR fingerprint region.

### Per-dataset schema variation

Every OSSL dataset ships its own column layout, and the module discovers the
layout from each file's header rather than assuming a fixed one. In the v1.3
bulk files in particular:

- the identifier columns differ: most scan tables lead with
  `id.layer_local_c` alone, KSSL's lead with `id.scan_local_c` and
  `id.sample_local_c`;
- the spectral range differs: LUCAS MIR starts at 628 cm<sup>-1</sup> rather
  than 600, MTQ NIR at 1100 nm, GPKOR NIR at 1400 nm and Neospectra NIR at
  1350 nm;
- the soil-lab tables range from 1 property (GPKOR) to over 80 (KSSL);
- **KSSL's VisNIR table stores its odd wavelengths under bare integer column
  names** (`351`, `353`, ...) interleaved with the regular
  `scan_visnir.352_ref` spelling, so that table is really 1 nm resolution
  across 350-2500 nm. The module reads both spellings and recovers all 2151
  bands. Bare integers are only accepted as wavelengths where a properly
  named spectral column proves the table really is a scan table, so a site
  column such as `site.landuse2009_src_code` is never mistaken for a band.

The v1.3 scan tables carry **only** `id.layer_local_c`, so that is the key
the module joins spectra to the site and soil-lab tables on. The API's
tables also carry `id.layer_uuid_txt`, the documented OSSL join key, and the
module prefers it there.

### Row schema

One row per (layer, scan domain), identical to the other `i.hyper.lib_*`
harvesters:

| Column | Content |
|---|---|
| `source_database` | always `ossl` (the Hive partition key) |
| `dataset_id` | sanitized dataset code plus scan domain, e.g. `KSSL_mir` |
| `dataset_title` | e.g. `OSSL KSSL (v1.3 MIR scans)` |
| `record_id` | `id.layer_local_c`, with `::<id.scan_local_c>` appended where a layer was scanned more than once |
| `organization` | dataset owner or surveyor, where the source states one |
| `source_url` | `https://soilspectroscopy.org/` |
| `source_api_url` | the dataset DOI, else the OSSL paper DOI |
| `longitude`, `latitude` | WGS84 point coordinates, falling back to the county centroid |
| `measurement_type` | `absorbance` (MIR) or `reflectance` (VisNIR, NIR) |
| `wavelength_unit` | `nm`, or `1/cm` with `mir_axis=wavenumber` |
| `n_bands` | number of bands actually carrying a value |
| `wavelengths` | ascending axis values, bands with no value dropped |
| `values` | the measurements, index-aligned with `wavelengths` |
| `extra_metadata` | JSON, see below |
| `ingest_date` | ISO timestamp of this ingestion |

`extra_metadata` holds the OSSL's own richness, which has no place in the
common columns:

```json
{
  "ossl_version": "v1.3",
  "scan_domain": "mir",
  "layer_local_id": "32383",
  "layer_uuid": "ae260ed01bbadec9ffbac7a7036dc4a3",
  "soil_properties": {"oc_usda.c729_w.pct": "1.82", "ph.h2o_usda.a268_index": "6.4"},
  "site": {"layer.upper.depth_usda_cm": "0", "pedon.taxa_usda_txt": "Hapludalfs"},
  "scan_metadata": {"scan.mir.model.name_utf8_txt": "Bruker Vertex 70"}
}
```

`soil_properties` is the paired laboratory chemistry, keyed by the OSSL's
`<property>_<method>_<unit>` column names, with the join-key columns removed.
It is what makes this source usable for soil-property regression rather than
spectral matching alone.

### Storage

With `format=parquet` (the default) each (dataset, scan domain) pair is
written to one ZSTD-compressed file under a Hive-style partition:

```text
$HOME/grassdata/hyperspeclib/
├── _manifest.json
└── source_database=ossl/
    ├── dataset_KSSL_mir.parquet
    ├── dataset_KSSL_visnir.parquet
    ├── dataset_Neospectra_nir.parquet
    └── ...
```

Where `shapely` is installed the file is valid **GeoParquet 1.1**, carrying a
WKB `geometry` point column alongside the plain `longitude`/`latitude`
columns, so the library opens directly in QGIS or GeoPandas.
`format=sqlite` writes the same rows into a single `hyperspeclib.sqlite`
table instead, for installations without `pyarrow`.

Ingestion is incremental. `_manifest.json` records what was written per
dataset and scan domain, and an unfiltered re-run skips the pairs already
present; the **-f** flag forces re-ingestion. A *filtered* run is never
recorded as complete, so it can never mask a later full harvest. Writing is
streamed in batches of `stream_batch_size` records, so peak memory does not
grow with dataset size, and nothing is written for a pair that yields no
record.

## NOTES

**Volume.** The complete v1.3 set is about 2.2 GB gzipped; KSSL alone is
306 MB of MIR and 532 MB of VisNIR. Without `cache_dir=` the files are
decoded straight off the socket and never touch disk, which costs no space
but re-downloads for each scan domain. With `cache_dir=` they are kept and
reused, which is much faster for repeated or interrupted runs.

**The API answers an empty result set with HTTP 500.** That is upstream
behaviour, not a fault in this module, so an empty station chunk is reported
as a warning and the harvest continues rather than aborting. The API also
has no `limit`/`offset` parameter, so a dataset has to be paged by station
ID; `station_chunk=` sets how many stations go into each `/data` request.
Resolving the station list first also gives the ingest a true progress
percentage. The OSSL documentation describes the API as provided for testing
purposes only.

**Progress** is reported through `G_percent()` and so appears in
[MetaMonitor](https://github.com/YannChemin/MetaMonitor) without any extra
setup: per station chunk on the API route, and off the download byte count
on the bulk route.

**Licence.** The OSSL is a compilation of datasets under different terms:
the soil-lab and site tables carry a per-dataset licence in their
`dataset.license.*` fields (ODbL for some), while the scan tables are
generally CC-BY 4.0. Check `extra_metadata.site` for the dataset at hand
before redistributing. Cite Safanelli et al. (2025),
[doi:10.1371/journal.pone.0296545](https://doi.org/10.1371/journal.pone.0296545).

## EXAMPLES

### Harvest the whole library

```sh
i.hyper.lib_ossl cache_dir=$HOME/DBDATA/OSSL
```

### See what is on offer before committing to a download

```sh
i.hyper.lib_ossl -l                 # dataset codes and their scan domains
i.hyper.lib_ossl -l source=api      # the API's codes, with station counts
i.hyper.lib_ossl -n                 # nation and texture filter vocabularies
```

### Just the Neospectra NIR scans

```sh
i.hyper.lib_ossl datasets=Neospectra scans=nir
```

### MIR on its native wavenumber axis, for fingerprint-region work

```sh
i.hyper.lib_ossl datasets=KSSL scans=mir mir_axis=wavenumber \
    cache_dir=$HOME/DBDATA/OSSL
```

### Topsoil spectra of carbon-rich layers over western Europe

```sh
i.hyper.lib_ossl datasets=LUCAS scans=visnir \
    bbox="POLYGON((-5 42,9 42,9 51,-5 51,-5 42))" \
    depth_min=0 depth_max=30 \
    var=oc_usda.c729_w.pct var_min=2 var_max=20
```

### The same subset through the API, filtered by nation server-side

```sh
i.hyper.lib_ossl source=api datasets=LUCAS.SSL scans=visnir \
    nation=France depth_min=0 depth_max=30
```

### Query the harvested library alongside the other sources

```python
import json

import pyarrow.compute as pc
import pyarrow.dataset as ds

lib = ds.dataset("~/grassdata/hyperspeclib", format="parquet", partitioning="hive")

# Every soil spectrum within a bounding box, from any OSSL dataset.
soil = lib.to_table(
    filter=(pc.field("source_database") == "ossl")
    & (pc.field("longitude") > -5)
    & (pc.field("longitude") < 9)
)

# Pair each spectrum with its measured organic carbon.
for row in soil.to_pylist():
    oc = json.loads(row["extra_metadata"])["soil_properties"].get("oc_usda.c729_w.pct")
    if oc is not None:
        print(row["record_id"], row["n_bands"], oc)
```

### Find the harvested spectra from GRASS

```sh
i.hyper.speclookup library=$HOME/grassdata/hyperspeclib \
    min_wavelength=400 max_wavelength=2400
```

## SEE ALSO

*[i.hyper.endmembers](i.hyper.endmembers.md),
[i.hyper.lib_ecosis](i.hyper.lib_ecosis.md),
[i.hyper.lib_gsti](i.hyper.lib_gsti.md),
[i.hyper.lib_relab](i.hyper.lib_relab.md),
[i.hyper.lib_usgs](i.hyper.lib_usgs.md),
[i.hyper.speclookup](i.hyper.speclookup.md),
[i.hyper.spectroscopy](i.hyper.spectroscopy.md),
[r3.what](r3.what.md)*

OSSL documentation: [docs.soilspectroscopy.org](https://docs.soilspectroscopy.org/)

## REFERENCES

Safanelli, J.L., Hengl, T., Parente, L.L., Minarik, R., Bloom, D.E.,
Todd-Brown, K., Gholizadeh, A., Mendes, W.d.S., Sanderman, J. (2025).
*Open Soil Spectral Library (OSSL): Building reproducible soil calibration
models through open development and community engagement.* PLOS ONE 20(1),
e0296545. [doi:10.1371/journal.pone.0296545](https://doi.org/10.1371/journal.pone.0296545)

## AUTHORS

Spectral Feature Extraction and Interpretation Engine
