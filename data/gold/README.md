# Ground truth (held out — evaluation only)

Built by `scripts/build_gold.py`. The agent and the baselines never read these files.

| File | Built from | Licence |
|---|---|---|
| `wellbore_headers.csv` | NPD wellbore headers (development + exploration), via [awgeo/Volve_field_data](https://github.com/awgeo/Volve_field_data) @ `7cdecf1` | Norwegian Licence for Open Government Data (NLOD), © Norwegian Offshore Directorate (Sodir) |
| `markers.csv` | `Well_picks_Volve_v1.dat` from the Volve data village, via [andymcdgeo/spwla_volve](https://github.com/andymcdgeo/spwla_volve) @ `c293edf` | Equinor Open Data Licence. Data courtesy of Equinor and the Volve licence partners |

Columns in `wellbore_headers.csv`: one row per (wellbore, fact).
`disputed = True` marks a known disagreement between our input files and the official record
(see `note`). Disputed values are reported separately in the evaluation and are never changed.

No header gold exists for 15/9-19 BT2 and 15/9-F-11 T2: technical sidetracks are not registered
separately at NPD.
