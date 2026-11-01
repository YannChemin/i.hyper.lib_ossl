# i.hyper.lib_ossl

GRASS GIS addon (Python script) that harvests the
[Open Soil Spectral Library (OSSL)](https://soilspectroscopy.org/) into the
same shared, source-tagged spectral library used by `i.hyper.lib_ecosis`,
`i.hyper.lib_usgs`, `i.hyper.lib_relab` and `i.hyper.lib_gsti`, at
`$HOME/grassdata/hyperspeclib`.

The OSSL is the largest open compilation of soil spectra, pairing MIR,
VisNIR and NIR laboratory scans with the measured soil properties of the
same layer (organic carbon, texture, pH, CEC, carbonates and dozens more).
It is the soil counterpart to the sources this family already covers: where
`i.hyper.lib_gsti` supplies leaf spectra with plant traits and
`i.hyper.lib_usgs` supplies mineral endmembers, this one supplies soil
spectra with soil chemistry — so the paired laboratory values are kept, not
just the spectra, which is what makes the source usable for soil-property
regression rather than spectral matching alone.

Records are written using the exact same row schema as the other four
harvesters, so all five sources can be queried together in one
`pyarrow.dataset` scan.

See [i.hyper.lib_ossl.md](i.hyper.lib_ossl.md) for full usage, the row schema
mapping, the two harvest routes, incremental/streaming behavior, and
examples.

## Two harvest routes

The OSSL is published twice over, and the two copies do not carry the same
content, so `source=` selects between them.

| | `source=gcs` (default) | `source=api` |
|---|---|---|
| Origin | v1.3 per-dataset bulk files on Google Cloud Storage | experimental REST API |
| Datasets | 20 | 10 (different codes) |
| Scan domains | MIR, VisNIR, **NIR** | MIR, VisNIR only |
| Filtering | `bbox=`, `depth_*=`, `var*=` (applied locally) | those, plus `nation=`, `state=`, `soil_texture=` (server-side) |
| Volume | ~2.2 GB gzipped for everything | one request per station chunk |

The NIR (Neospectra) scans exist **only** in the bulk files, so the default
route is `gcs`. Only the API understands `nation=`, `state=` and
`soil_texture=`.

## Quick start

```sh
# See what is on offer before downloading anything.
i.hyper.lib_ossl -l

# Harvest everything, keeping the downloads for re-use.
i.hyper.lib_ossl cache_dir=$HOME/DBDATA/OSSL

# Or one dataset and one domain.
i.hyper.lib_ossl datasets=Neospectra scans=nir
```

## Notes

- **MIR is stored in nanometres by default** (`mir_axis=nm`), converted from
  the native wavenumbers, so MIR rows are directly comparable with the
  nm-based rows of the other four sources and with `i.hyper.speclookup`'s
  wavelength filters. `mir_axis=wavenumber` keeps the native cm⁻¹ axis.
- Every OSSL dataset ships its own column layout, so the spectral columns
  are discovered from each file's header. KSSL's VisNIR table in particular
  stores its odd wavelengths under bare integer column names interleaved
  with the regular spelling; all 2151 bands at 1 nm are recovered.
- The API answers an empty result set with HTTP 500 and has no
  `limit`/`offset`, so datasets are paged by station ID. This is handled as
  a warning, not a failure.
- Progress is reported via `G_percent()` and so shows up in
  [MetaMonitor](https://github.com/YannChemin/MetaMonitor) with no extra
  setup.
- The OSSL is a compilation of datasets under differing terms (per-dataset
  `dataset.license.*` for the lab/site tables, generally CC-BY 4.0 for the
  scans). Check `extra_metadata.site` before redistributing, and cite
  [doi:10.1371/journal.pone.0296545](https://doi.org/10.1371/journal.pone.0296545).

## Build / install

Dual-mode Makefile: builds as a GRASS addon
(`make MODULE_TOPDIR=$HOME/dev/grass`) or as a standalone script
(`make DEBIAN_BUILD=1 install`).

## See also

`i.hyper.lib_ecosis`, `i.hyper.lib_gsti`, `i.hyper.lib_relab`,
`i.hyper.lib_usgs`, `i.hyper.speclookup`, `i.hyper.spectroscopy`,
`i.hyper.endmembers`

## License

See [LICENSE](LICENSE).
