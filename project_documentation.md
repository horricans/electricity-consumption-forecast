# Turkey Hourly Electricity Consumption Forecasting — Project Documentation

**Author:** Sultan Selin Başar
**Status:** Feature engineering complete → next step: LightGBM model
**Last updated:** covers work through the feature engineering stage

---

## 1. Project Overview

Forecasting Turkey's national hourly electricity consumption using data from EPİAŞ
(Energy Exchange Istanbul), as a portfolio data science project. The forecast is
made at midnight for the following 24 hours (day-ahead, hourly resolution).

**Model roadmap:** naive baseline (lag-168) → LightGBM → neural network.

---

## 2. Data Pipeline

### 2.1 Consumption Data

- **Source:** EPİAŞ Şeffaflık Platformu (Transparency Platform), real-time
  consumption endpoint, pulled via authenticated API (`01_fetch.py`).
- **Coverage:** 2017-01-01 00:00 → 2026-08-30 23:00, `Europe/Istanbul` timezone.
- **Row count:** 84,696 hourly rows — matches the expected hour count exactly.
- **Why 2017 as the start date:** Turkey has used a fixed UTC+03:00 offset since
  September 2016, so starting in 2017 avoids the duplicate/missing-hour problems
  that daylight saving transitions would otherwise cause.

### 2.2 Data Validation

| Check | Result |
|---|---|
| Missing hours | None |
| Duplicate timestamps | None |
| Nulls | None |
| Zero / negative values | None |
| Ordering | Monotonically increasing |

**Descriptive statistics (MWh):** mean 36,295 · std 6,408 · min 15,333
(2020-05-25 07:00) · median 35,940 · max 59,504 (2025-07-28 14:00).

### 2.3 Weather Data

- **Source:** Open-Meteo, for Istanbul, Ankara, and İzmir.
- **Combination method:** population-weighted average into a single
  `national_temp` signal — weighting reflects that a degree of temperature
  change affects consumption in proportion to how many people experience it,
  not just the raw temperature reading.
- **Base temperature (T_base):** set to 16°C initially; to be optimized later
  against validation performance.

### 2.4 Train / Validation / Test Split

Time-based, no shuffling:

```python
train = merged_df[merged_df["date"] < "2024-09-01"]
val   = merged_df[(merged_df["date"] >= "2024-09-01") & (merged_df["date"] < "2025-09-01")]
test  = merged_df[merged_df["date"] >= "2025-09-01"]
```

| Split | Range |
|---|---|
| Train | 2017-01-01 → 2024-08-31 |
| Validation | 2024-09-01 → 2025-08-31 |
| Test | 2025-09-01 → 2026-08-30 |

Test is held out until final model evaluation — it is not touched during
feature selection or hyperparameter tuning, to avoid gradually overfitting to it.

### 2.5 Forecast Setup and the Leakage Constraint

The forecast is made at **midnight for the next 24 hours**. This means at
prediction time, the most recent actual consumption value available is from
**24 hours ago** — not 1 hour ago. Any lag feature must therefore use
`shift(24)` or larger; `shift()` values smaller than 24 would use information
that would not actually be available at prediction time in production.

---

## 3. Exploratory Data Analysis — Key Findings

(Full detail in `eda_bulgular.md`. Summary of findings that directly shaped
feature engineering below.)

- **Three overlapping cycles:** daily (24h), weekly (168h), yearly (~8,766h).
- **Trend:** consumption rises 2017→2026, with summer peaks growing faster
  than winter peaks (likely growing share of cooling load).
- **Yearly seasonality:** two maxima (Jan–Feb heating, Jul–Aug cooling), two
  minima (Apr–May, Oct) — consumption responds to temperature, not calendar
  month, and the relationship is U-shaped around a neutral point.
- **Daily profile:** minimum ~04:00–05:00; sharp jump at 08:00 every month
  (start of business activity); summer peak ~12:00–15:00 (cooling); winter
  peak shifts earlier to ~07:00–09:00 (heating + lighting, since sunrise in
  Ankara in January is ~08:30 and Turkey's fixed UTC+3 offset means winter
  mornings are dark).
- **Weekly profile:** Monday nights are the lowest of the week (industry not
  yet back from Sunday); Tue–Fri highest and similar; Saturday has a
  *softened* morning ramp (no synchronized commute); Sunday lowest overall.
- **Holiday effect (critical):** religious holidays shift by ~11 days/year
  (lunar calendar) — a fixed calendar feature (`month`, `dayofyear`) can never
  learn this; an explicit holiday flag is required.
- **Known anomalies:** COVID-19 (Apr 2020 – mid-2021, confirmed both
  statistically and against the official restriction timeline); 2020-05-25 is
  the series' absolute minimum (Bayram + COVID overlap).

---

## 4. Baseline Model — Naive Lag-168

**Logic:** predict each hour using the actual consumption from exactly one
week (168 hours) earlier. Chosen over `lag_24` because the weekly lag
preserves day-type (weekday vs. Monday vs. Saturday vs. Sunday all behave
differently, per the EDA findings above).

```python
y_pred = val["lag_168"]
MAPE = ((val["consumption"] - val["lag_168"]).abs() / val["consumption"]).mean() * 100
```

**Result: Validation MAPE ≈ 5.41%**

This is the threshold every later model must beat. MAPE (not MAE/RMSE) was
chosen because the series has a large seasonal range in absolute level
(summer vs. winter), so a percentage error is more interpretable than an
absolute one.

### Error breakdown (diagnostic, not just a scorecard)

**By hour of day:** lowest at night (~4.6%, hour 0–6), highest in the
afternoon (~6.2–6.4%, hours 13–16). Interpretation: nighttime load is mostly
baseline demand that doesn't shift much week-to-week; afternoon load is more
temperature-sensitive (cooling), so a week-old lag misses recent weather
changes more there.

**By day of week:** Monday is worst (6.49%), Thursday is best (4.64%).
Wed/Thu are the most "routine" days (surrounded by other workdays, rarely
hit by holidays), so `lag_168` performs best there. Monday is a transition
day from the weekend, which the naive model can't anticipate.

**Conclusion from baseline diagnostics:** the error pattern itself pointed
toward two feature priorities — temperature sensitivity by hour (motivating
temperature × time-of-day interactions, left to LightGBM to learn) and
day-type transitions (motivating explicit day-of-week and holiday features).

---

## 5. Feature Engineering

All features are built in `06_features.ipynb`, reading from
`data/processed/merged_data.parquet` (raw merged consumption + weather,
84,696 rows, 8 columns) and producing a feature-complete dataframe.

### 5.1 Consumption Lag & Rolling Features

```python
data["consumption_lag_24"]  = data["consumption"].shift(24)
data["consumption_lag_48"]  = data["consumption"].shift(48)
data["consumption_lag_168"] = data["consumption"].shift(168)

data["consumption_rolling_mean_24"]  = data["consumption"].shift(24).rolling(24).mean()
data["consumption_rolling_mean_168"] = data["consumption"].shift(24).rolling(168).mean()
```

- `shift(24)` is always applied **before** `.rolling()` — the forecast
  horizon is 24h, so no hour within that rolling window would actually be
  available at prediction time. Applying `.rolling()` without the shift first
  would leak future information into the feature.
- `lag_24` / `lag_48` capture recent level; `lag_168` captures the weekly
  pattern; the rolling means smooth out hour-specific noise that a single lag
  point can carry.

### 5.2 Calendar Features

```python
data["is_weekend"] = data["weekday"].isin(["Saturday", "Sunday"]).astype(int)
data["DoW"] = data["date"].dt.dayofweek   # 0=Monday..6=Sunday
data["DoY"] = data["date"].dt.dayofyear
```

The original `weekday` string column is kept for readability/debugging but
excluded from the model's feature list.

### 5.3 Holiday Features

Built using the `holidays` Python package (`holidays.TR(years=range(2017, 2027))`).

- **`is_religious_holiday`** — Kurban Bayramı or Ramazan Bayramı days
  (matched by name from the `holidays` package), separated from national
  holidays because the two have very different consumption impact
  (religious holidays cause a much sharper, multi-day drop).
- **`is_arife`** — the day immediately before a religious holiday begins,
  provided that day itself is not already a holiday. Edge case handled: in
  2022, arife coincided with May 1st (Labour Day) — checking "is tomorrow's
  holiday name religious AND today's holiday name is not religious" (rather
  than "today is in the holiday set at all") correctly keeps that day flagged
  as arife.
- **`is_national_holiday`** — fixed-date national holidays (New Year's,
  April 23, May 1, May 19, July 15, August 30, October 29), matched
  explicitly by name to avoid misclassifying a religious holiday that falls
  on the same calendar date (e.g. April 23, 2023 coincided with Kurban
  Bayramı).
- **`is_kopru`** ("bridge day") — a working day sandwiched between a holiday
  (or weekend) on both sides, when people commonly take the day off.
- **`bayram_day_index`** — 0 (not a holiday) through 4 (day 4 of Kurban
  Bayramı, which is 4 days; Ramazan Bayramı is 3 days, so index only reaches
  3 for that one). Captures that the first day of a religious holiday behaves
  very differently from the last.

Validated counts (val period + full series):
`is_national_holiday` ≈ 69 days/period, `is_religious_holiday` = 70 days
(1,680 hours / 24), `is_arife` = 20 days (480 hours / 24) — matching 2
arife days × 10 years.

### 5.4 Temperature Features

```python
T_base = 16

data["HDD"] = (T_base - data["national_temp"]).clip(lower=0)  # heating degree days
data["CDD"] = (data["national_temp"] - T_base).clip(lower=0)  # cooling degree days

data["temp_lag_24"] = data["national_temp"].shift(24)
data["temp_lag_48"] = data["national_temp"].shift(48)
data["temp_rolling_mean_24"] = data["national_temp"].shift(24).rolling(24).mean()
```

- HDD/CDD split the U-shaped temperature–consumption relationship into two
  one-directional signals, since a raw temperature value can't tell a linear
  or tree model which side of the neutral point it's on.
- Temperature lags capture thermal inertia — buildings don't respond to
  temperature changes instantly, so yesterday's temperature still affects
  today's heating/cooling load.

### 5.5 Trend Handling

Rather than feeding the model a raw trend feature (`time_idx`, `year`), the
target is normalized instead:

```python
data["yearly_baseline"] = data["consumption"].shift(24).rolling(8766).mean()  # ~1 year of hours
data["target_ratio"] = data["consumption"] / data["yearly_baseline"]
```

**Rationale:** tree-based models (LightGBM) cannot extrapolate beyond the
value ranges seen during training. A raw trend feature fails on validation/
test periods because those sit entirely outside the training range — the
model would flatten the trend rather than continue it. By having the model
predict `target_ratio` ("how far is this hour from its own trailing
baseline") instead of absolute consumption, the trend is absorbed into the
baseline itself rather than needing to be extrapolated by the model.

At inference time: `predicted_consumption = predicted_ratio * yearly_baseline`.

**Open item:** the 1-year rolling window means the first year of the series
has no `yearly_baseline` (NaN). A shorter window (e.g. 90 days) is a
candidate to revisit during T_base / windowing optimization.

### 5.6 Lighting Features

Computed from sunrise/sunset times for Ankara (chosen as a geographically
central reference point — unlike temperature, day-length varies only by a
few minutes across Istanbul/İzmir/Ankara's latitude range, so a single
location is a reasonable approximation without population-weighting):

```python
from astral import LocationInfo
from astral.sun import sun

ankara = LocationInfo(latitude=39.93, longitude=32.86, timezone="Europe/Istanbul")
```

Sunrise/sunset hours are precomputed once per day-of-year (using a leap year,
2020, as the reference so day 366 exists) and mapped onto the full series via
`DoY`, rather than computed per-row, since the pattern repeats yearly and
Turkey has no daylight saving shifts to complicate the mapping.

- **`day_length`** = `sunset_hour - sunrise_hour`.
- **`is_dark`** = 1 if the current hour is before sunrise or after sunset.
- **`hour_to_sunrise`** = hours remaining until sunrise; `NaN` during daytime
  (not 0, since 0 would be indistinguishable from "sunrise is happening right
  now"). For evening darkness (after sunset), this correctly points to
  **tomorrow's** sunrise rather than today's (which has already passed) —
  handled via a `next_day_sunrise` helper column and `np.select` with two
  conditions (before-sunrise vs. after-sunset).

Motivation: EDA found that the winter morning peak shifts earlier than the
summer one, attributed to darkness + cold + synchronized wake-up time driving
a lighting-load component that's absent in summer. `is_dark` and
`hour_to_sunrise` give the model this signal directly instead of relying on
`hour` + `month` alone.

### 5.7 COVID-19 Flag

```python
data["is_covid"] = (
    (data["date"] >= "2020-03-16") & (data["date"] <= "2020-06-01")
).astype(int)
```

**Derivation:** two independent lines of evidence converged on this window.

1. **Statistical:** outlier detection during data validation flagged 36
   below-lower-bound values, concentrated in 2020-04-12 to 2020-05-26.
2. **Official timeline (cross-referenced via news sources):** March 16, 2020
   — schools, cafes, and venues closed (first concrete restrictions); June 1,
   2020 — "controlled social life" (*kontrollü sosyal hayat*) began, public
   sector remote-work mandate ended, cafes/restaurants reopened. This is the
   officially recognized start/end of the first restriction period.

The wider official window (Mar 16 – Jun 1) was used rather than just the
statistical outlier window (Apr 12 – May 26), since the latter only captures
the sharpest point of the effect, not its full ramp-up/down. The two windows
overlap, giving confidence in the choice.

Note: an EPİAŞ Transparency Platform query (consumption by sector, e.g.
Sanayi/Ticarethane) was attempted to independently verify industrial-sector
recovery timing, but the platform's monthly aggregate table produced
internally inconsistent results (e.g. May 2020 appearing ~15× higher than
January 2020, which contradicts both known seasonality and the project's own
validated total-consumption data) and was not used as a source.

### 5.8 Data Type Cleanup

```python
bool_cols = ["is_religious_holiday", "is_arife", "is_national_holiday", "is_kopru"]
data[bool_cols] = data[bool_cols].astype(int)
```

Converted for consistency with the other binary features (`is_weekend`,
`is_dark`, `is_covid`), which were already `int`.

---

## 6. Current Feature Set (Summary)

| Group | Features |
|---|---|
| Consumption lag/rolling | `consumption_lag_24`, `consumption_lag_48`, `consumption_lag_168`, `consumption_rolling_mean_24`, `consumption_rolling_mean_168` |
| Calendar | `hour`, `DoW`, `DoY`, `month`, `year`, `is_weekend` |
| Holiday | `is_religious_holiday`, `is_arife`, `is_national_holiday`, `is_kopru`, `bayram_day_index` |
| Temperature | `national_temp`, `HDD`, `CDD`, `temp_lag_24`, `temp_lag_48`, `temp_rolling_mean_24` |
| Trend (via target) | `yearly_baseline`, `target_ratio` |
| Lighting | `day_length`, `is_dark`, `hour_to_sunrise` |
| Anomaly | `is_covid` |

**Deliberately not yet added:** explicit interaction terms (`hour × month`,
`hour × dayofweek`) — left for LightGBM to learn on its own, since tree
models can capture interactions natively; a doubling/quadrupling-check via
feature importance is planned once the model is trained.

**Intermediate/helper columns present but not intended as model features:**
`sunrise_hour`, `sunset_hour`, `next_day_sunrise` (used only to compute
`hour_to_sunrise` and `day_length`); `weekday` (string, kept for readability).

---

## 7. Next Steps

1. Save the completed feature set to `data/processed/featured_data.parquet`.
2. Train LightGBM on the train split; evaluate on validation using the same
   MAPE metric (overall + hourly/day-of-week breakdown) as the baseline.
3. Use feature importance to prune redundant features (e.g. `consumption_lag_48`
   vs. `consumption_lag_24`, `day_length`/`is_dark` vs. temperature) and decide
   whether explicit interaction terms are needed.
4. Optimize `T_base` (currently fixed at 16°C) and the `yearly_baseline`
   rolling window length against validation performance.
5. Hyperparameter tuning (validation set).
6. Train a neural network and compare against LightGBM.
7. Final evaluation on the held-out test set (once, at the end).
