
from pathlib import Path

import pandas as pd
import streamlit as st


# --------------------------------------------------
# Configuration
# --------------------------------------------------

ROOT = Path(__file__).resolve().parent
PROCESSED = ROOT / "data" / "processed"

st.set_page_config(
    page_title="YottaFlex Forecast Dashboard",
    page_icon="📊",
    layout="wide",
)

st.title("YottaFlex Forecast Dashboard")
st.caption(
    "Sales pipeline forecasting, scenario comparisons, "
    "historical accuracy and probability calibration"
)

st.info(
    "Proof of concept using synthetic sales data. "
    "Historical forecast accuracy is still limited; "
    "results should not be interpreted as production-ready predictions."
)


# --------------------------------------------------
# Data loading
# --------------------------------------------------

@st.cache_data(show_spinner=False)
def load_csv(filename):
    path = PROCESSED / filename

    if not path.exists():
        return pd.DataFrame(), f"File not found: {filename}"

    try:
        return pd.read_csv(path), None
    except (pd.errors.ParserError, UnicodeDecodeError, OSError) as error:
        return pd.DataFrame(), f"Could not read {filename}: {error}"


def show_data_status(filename, error):
    if error:
        st.warning(
            f"Could not load `data/processed/{filename}`. {error}"
        )


forecast, forecast_error = load_csv("forecast_summary.csv")
scenarios, scenarios_error = load_csv("scenario_summary.csv")
accuracy, accuracy_error = load_csv("forecast_accuracy.csv")
evaluation, evaluation_error = load_csv("forecast_evaluation.csv")


# --------------------------------------------------
# Helper functions
# --------------------------------------------------

def money(value):
    if pd.isna(value):
        return "—"

    return f"${value:,.2f}"


def numeric_column(data, column):
    if column in data.columns:
        data[column] = pd.to_numeric(
            data[column],
            errors="coerce",
        ).fillna(0)

    return data


def prepare_categories(data, columns):
    data = data.copy()

    for column in columns:
        if column not in data.columns:
            data[column] = "Unknown"

        data[column] = (
            data[column]
            .fillna("Unknown")
            .astype(str)
        )

    return data


def apply_filters(data, quarters, territories):
    result = data.copy()

    if "quarter" in result.columns:
        result = result[
            result["quarter"].isin(quarters)
        ]

    if "territory_id" in result.columns:
        result = result[
            result["territory_id"].isin(territories)
        ]

    return result.copy()


def show_missing(filename):
    st.warning(
        f"Could not find `data/processed/{filename}` "
        "or the file contains no usable rows."
    )


# --------------------------------------------------
# Forecast data validation
# --------------------------------------------------

st.sidebar.header("Forecast Filters")

if forecast.empty:
    show_data_status("forecast_summary.csv", forecast_error)
    show_missing("forecast_summary.csv")
    st.stop()

required_forecast_columns = [
    "opportunity_count",
    "total_amount",
    "total_weighted_pipeline",
    "adjusted_expected_revenue",
]

missing_columns = [
    column
    for column in required_forecast_columns
    if column not in forecast.columns
]

if missing_columns:
    st.error(
        "The forecast summary is missing required columns: "
        + ", ".join(missing_columns)
    )
    st.stop()

forecast = prepare_categories(
    forecast,
    ["quarter", "territory_id", "stage_name"],
)

for column in required_forecast_columns:
    forecast = numeric_column(forecast, column)


# --------------------------------------------------
# Sidebar filters
# --------------------------------------------------

quarters = sorted(forecast["quarter"].unique())
territories = sorted(forecast["territory_id"].unique())
stages = sorted(forecast["stage_name"].unique())

selected_quarters = st.sidebar.multiselect(
    "Quarter",
    options=quarters,
    default=quarters,
)

selected_territories = st.sidebar.multiselect(
    "Territory",
    options=territories,
    default=territories,
)

selected_stages = st.sidebar.multiselect(
    "Stage",
    options=stages,
    default=stages,
)

filtered = apply_filters(
    forecast,
    selected_quarters,
    selected_territories,
)

filtered = filtered[
    filtered["stage_name"].isin(selected_stages)
].copy()


# --------------------------------------------------
# Forecast overview
# --------------------------------------------------

st.subheader("Forecast Overview")

if filtered.empty:
    st.info("No forecast rows match the selected filters.")
    st.stop()

opportunity_count = filtered["opportunity_count"].sum()
total_amount = filtered["total_amount"].sum()
weighted_pipeline = filtered["total_weighted_pipeline"].sum()
adjusted_revenue = filtered["adjusted_expected_revenue"].sum()

metric1, metric2, metric3, metric4 = st.columns(4)

metric1.metric(
    "Opportunities",
    f"{opportunity_count:,.0f}",
)

metric2.metric(
    "Total Pipeline",
    money(total_amount),
)

metric3.metric(
    "Weighted Pipeline",
    money(weighted_pipeline),
)

metric4.metric(
    "Adjusted Expected Revenue",
    money(adjusted_revenue),
)

if "snapshot_date" in filtered.columns:
    snapshot_dates = pd.to_datetime(
        filtered["snapshot_date"],
        errors="coerce",
    ).dropna()

    if not snapshot_dates.empty:
        st.caption(
            f"Latest snapshot date: {snapshot_dates.max().date()}"
        )


# --------------------------------------------------
# Forecast charts
# --------------------------------------------------

st.divider()
st.subheader("Forecast Analysis")

left, right = st.columns(2)

with left:
    st.markdown("**Adjusted Expected Revenue by Quarter**")

    quarter_data = (
        filtered.groupby("quarter", as_index=False)
        ["adjusted_expected_revenue"]
        .sum()
        .sort_values("quarter")
    )

    if not quarter_data.empty:
        st.bar_chart(
            quarter_data.set_index("quarter")[
                "adjusted_expected_revenue"
            ]
        )
    else:
        st.info("Quarterly forecast data is unavailable.")

with right:
    st.markdown("**Adjusted Expected Revenue by Territory**")

    territory_data = (
        filtered.groupby("territory_id", as_index=False)
        ["adjusted_expected_revenue"]
        .sum()
        .sort_values(
            "adjusted_expected_revenue",
            ascending=False,
        )
    )

    if not territory_data.empty:
        st.bar_chart(
            territory_data.set_index("territory_id")[
                "adjusted_expected_revenue"
            ]
        )
    else:
        st.info("Territory forecast data is unavailable.")


# --------------------------------------------------
# Forecast detail
# --------------------------------------------------

st.divider()
st.subheader("Forecast Details")

detail_columns = [
    column
    for column in [
        "quarter",
        "territory_id",
        "stage_name",
        "opportunity_count",
        "total_amount",
        "total_weighted_pipeline",
        "adjusted_expected_revenue",
        "snapshot_date",
    ]
    if column in filtered.columns
]

st.dataframe(
    filtered[detail_columns].sort_values(
        ["quarter", "territory_id", "stage_name"],
        na_position="last",
    ),
    use_container_width=True,
    hide_index=True,
)


# --------------------------------------------------
# Scenario comparison
# --------------------------------------------------

st.divider()
st.subheader("Scenario Comparison")

show_data_status("scenario_summary.csv", scenarios_error)

if scenarios.empty:
    st.info("Scenario summary is not available yet.")

else:
    scenario_view = prepare_categories(
        scenarios,
        ["scenario", "quarter", "territory_id"],
    )

    scenario_required = [
        "opportunity_count",
        "total_amount",
        "total_weighted_pipeline",
    ]

    missing_scenario_columns = [
        column
        for column in scenario_required
        if column not in scenario_view.columns
    ]

    if missing_scenario_columns:
        st.warning(
            "Scenario summary is missing required columns: "
            + ", ".join(missing_scenario_columns)
        )
    else:
        scenario_view = apply_filters(
            scenario_view,
            selected_quarters,
            selected_territories,
        )

        for column in scenario_required:
            scenario_view = numeric_column(
                scenario_view,
                column,
            )

        if scenario_view.empty:
            st.info("No scenario rows match the selected filters.")

        else:
            scenario_totals = (
                scenario_view.groupby(
                    "scenario",
                    as_index=False,
                )
                .agg(
                    opportunity_count=("opportunity_count", "sum"),
                    total_amount=("total_amount", "sum"),
                    total_weighted_pipeline=(
                        "total_weighted_pipeline",
                        "sum",
                    ),
                )
                .sort_values("scenario")
            )

            st.markdown("**Weighted Pipeline by Scenario**")

            st.bar_chart(
                scenario_totals.set_index("scenario")[
                    "total_weighted_pipeline"
                ]
            )

            st.markdown("**Scenario Summary**")

            st.dataframe(
                scenario_totals,
                use_container_width=True,
                hide_index=True,
            )


# --------------------------------------------------
# Historical forecast accuracy
# --------------------------------------------------

st.divider()
st.subheader("Historical Forecast Accuracy")

show_data_status("forecast_accuracy.csv", accuracy_error)

if accuracy.empty:
    st.info(
        "Historical forecast accuracy results are not available yet."
    )

else:
    accuracy_view = accuracy.copy()

    if "model" in accuracy_view.columns:
        models = sorted(
            accuracy_view["model"]
            .dropna()
            .astype(str)
            .unique()
        )

        selected_models = st.multiselect(
            "Forecast Model",
            options=models,
            default=models,
            key="accuracy_models",
        )

        accuracy_view = accuracy_view[
            accuracy_view["model"].astype(str).isin(selected_models)
        ]

    if "horizon_bucket" in accuracy_view.columns:
        horizons = sorted(
            accuracy_view["horizon_bucket"]
            .dropna()
            .astype(str)
            .unique()
        )

        selected_horizons = st.multiselect(
            "Snapshot-to-Close Horizon",
            options=horizons,
            default=horizons,
            key="accuracy_horizons",
        )

        accuracy_view = accuracy_view[
            accuracy_view["horizon_bucket"]
            .astype(str)
            .isin(selected_horizons)
        ]

    if accuracy_view.empty:
        st.info("No accuracy rows match the selected filters.")

    else:
        if "wape_pct" in accuracy_view.columns:
            accuracy_view = numeric_column(
                accuracy_view,
                "wape_pct",
            )

        if "segment_type" in accuracy_view.columns:
            overall_wape = accuracy_view[
                accuracy_view["segment_type"]
                .astype(str)
                .str.lower()
                .eq("overall")
            ].copy()
        else:
            overall_wape = pd.DataFrame()

        if (
            not overall_wape.empty
            and {
                "wape_pct",
                "model",
                "horizon_bucket",
            }.issubset(overall_wape.columns)
        ):
            overall_wape["chart_label"] = (
                overall_wape["model"].astype(str)
                + " | "
                + overall_wape["horizon_bucket"].astype(str)
            )

            overall_wape = overall_wape.sort_values(
                ["horizon_bucket", "model"]
            )

            st.markdown("**Overall WAPE by Model and Horizon**")

            st.bar_chart(
                overall_wape.set_index("chart_label")["wape_pct"]
            )

            st.caption(
                "WAPE measures forecast error as a percentage of "
                "actual booked revenue. Lower is better."
            )

        else:
            st.info(
                "Overall WAPE rows are not available for the selected filters."
            )

        accuracy_columns = [
            column
            for column in [
                "model",
                "horizon_bucket",
                "segment_type",
                "segment_value",
                "evaluated_snapshot_rows",
                "expected_revenue",
                "actual_booked_revenue",
                "error",
                "wape_pct",
                "bias_pct",
                "bias_direction",
            ]
            if column in accuracy_view.columns
        ]

        st.markdown("**Accuracy Detail**")

        st.dataframe(
            accuracy_view[accuracy_columns],
            use_container_width=True,
            hide_index=True,
        )


# --------------------------------------------------
# Probability calibration
# --------------------------------------------------

st.divider()
st.subheader("Probability Calibration")

show_data_status("forecast_evaluation.csv", evaluation_error)

if evaluation.empty:
    st.info("Probability evaluation results are not available yet.")

else:
    st.dataframe(
        evaluation,
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        "Brier score evaluates the quality of probability predictions. "
        "Lower values indicate better calibration and predictive performance."
    )


# --------------------------------------------------
# Project methodology and limitations
# --------------------------------------------------

st.divider()
st.subheader("Project Notes")

st.markdown(
    """
    - The project uses reproducible synthetic sales pipeline data.
    - Forecast scenarios compare pessimistic, baseline and optimistic assumptions.
    - Historical accuracy is evaluated against recorded bookings.
    - Injected anomalies are maintained separately from clean data.
    - Results are intended for experimentation and evaluation, not production decisions.
    """
)

st.caption(
    "YottaFlex Forecast | Sales Forecasting Proof of Concept"
)
