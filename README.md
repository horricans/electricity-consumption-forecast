# Turkey Hourly Electricity Consumption Forecasting

Day-ahead forecasting of Turkey's national hourly electricity consumption, built on
EPİAŞ Transparency Platform data (2017–2026). The forecast is made at midnight for the
following 24 hours.

> **Status:** In progress. Feature engineering and LightGBM tuning are complete. The
> neural network model and the final test-set evaluation are still to come.

## Results so far

Metric: MAPE (%) on national consumption. Validation period: 2024-09-01 to 2025-09-01.
The test set (2025-09-01 onward) has not been used yet.

| Model | Train MAPE | Validation MAPE |
|---|---|---|
| Naive baseline (lag-168) | — | 5.41 |
| LightGBM, default parameters | 1.22 | 4.10 |
| LightGBM, tuned (unconstrained search) | 0.28 | 2.91 |
| **LightGBM, tuned (constrained search)** | **1.52** | **2.92** |

The two tuned models score almost the same on validation. The constrained model was
selected: it reaches the same accuracy with much less capacity, and its train–validation
gap is about half that of the unconstrained model.

Validation scores are somewhat optimistic. 50 Optuna trials were each scored on the same
validation set, so the reported numbers slightly overstate expected performance on unseen
data. The test set exists to correct for this.

## Data

- **Consumption:** EPİAŞ Transparency Platform, real-time consumption endpoint.
  Hourly, 2017-01-01 to 2026-08-30 (84,696 rows, no gaps or duplicates).
- **Weather:** Open-Meteo for Istanbul, Ankara and İzmir, combined into a single
  population-weighted `national_temp` signal.
- **Calendar:** Turkish public and religious holidays, Bayram day index, weekday and
  hour.

The raw data is not included in this repository (`data/` is git-ignored).

## Approach

1. **Target transformation.** The model predicts `target_ratio = consumption / yearly_baseline`,
   where `yearly_baseline` is a trailing one-year mean. Trend is removed before training and
   added back at prediction time. Tree models cannot extrapolate beyond the value range they
   were trained on, so this lets them handle long-term growth.
2. **Leakage-safe features.** Because the forecast is made 24 hours ahead, every lag is
   at least 24 hours.
3. **Time-based split.** Train before 2024-09-01, validation for one year, test for the
   final year. No shuffling and no cross-validation.
4. **Feature selection** by gain importance, correlation analysis and domain reasoning,
   in three versions. The final set has 19 features.
5. **Hyperparameter search** with Optuna, minimising validation MAPE in consumption space.

## Repository structure

| Path | Contents |
|---|---|
| `01_fetch.py` | Fetches consumption data from the EPİAŞ API |
| `notebooks/02_validation.ipynb` | Data validation checks |
| `notebooks/03_eda.ipynb` | Exploratory data analysis |
| `notebooks/04_weather_data.ipynb` | Weather data collection and national aggregation |
| `notebooks/05_baseline_model.ipynb` | Naive baseline (lag-168) |
| `notebooks/06_features.ipynb` | Feature engineering |
| `notebooks/07_LightGBM.ipynb` | LightGBM training, feature selection and tuning |
| `project_documentation.md` | Detailed write-up of the data pipeline and feature rationale |
| `eda_bulgular.md` | EDA findings (Turkish) |

## Setup

Requires Python 3.10+.

```bash
git clone https://github.com/horricans/electricity-consumption-forecast
cd electricity-consumption-forecast
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install pandas numpy lightgbm optuna scikit-learn matplotlib seaborn holidays astral requests python-dotenv pyarrow
```

To fetch data from EPİAŞ, create a `.env` file in the project root with your EPİAŞ
Transparency Platform credentials:

```
EPIAS_USERNAME=your_username
EPIAS_PASSWORD=your_password
```

Then run `python 01_fetch.py`.

## Next steps

- Neural network model, compared against LightGBM on the validation set
- Final evaluation of the selected model on the held-out test set
- Optimise the base temperature (currently 16 °C) and the `yearly_baseline` window length
