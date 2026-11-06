
from pathlib import Path

import pandas as pd
import streamlit as st


# ==================================================
# 1. CONFIGURATION
# ==================================================

ROOT = Path(__file__).resolve().parent
PROCESSED = ROOT / "data" / "processed"

st.set_page_config(
    page_title="YottaFlex Forecast Dashboard",
    page_icon="📊",
    layout="wide",
)

st.title("📊 YottaFlex Forecast Dashboard")

st.caption(
    "Sales pipeline forecasting | Scenario analysis | "
    "Historical accuracy | Probability evaluation"
)

st.info(
    "Proof of concept using synthetic sales data. "
    "Forecast results are experimental and should not "
    "be interpreted as production-ready predictions."
)


# ==================================================
# 2. DATA LOADING
# ==================================================

@st.cache_data(show_spinner=False)
def load_csv(filename):
    path = PROCESSED / filename

    if not path.exists():
        return pd.DataFrame(), f"File not found: {filename}"

    try:
        data = pd.read_csv(path)

        if data.empty:
            return data, f"{filename} contains no rows."

        return data, None

    except (
        pd.errors.ParserError,
        UnicodeDecodeError,
        OSError,
        ValueError,
    ) as error:
        return pd.DataFrame(), f"Could not read {filename}: {error}"


def show_data_status(filename, error):
    if error:
        st.warning(
            f"Problem loading `data/processed/{filename}`: {error}"
        )


def show_missing(filename):
    st.warning(
        f"`data/processed/{filename}` is unavailable "
        "or contains no usable rows."
    )


forecast, forecast_error = load_csv("forecast_summary.csv")
scenarios, scenarios_error = load_csv("scenario_summary.csv")
accuracy, accuracy_error = load_csv("forecast_accuracy.csv")
evaluation, evaluation_error = load_csv("forecast_evaluation.csv")


# ==================================================
# 3. HELPER FUNCTIONS
# ==================================================

def money(value):
    if pd.isna(value):
        return "—"

    return f"${value:,.2f}"


def safe_numeric(data, columns):
    data = data.copy()

    for column in columns:
        if column in data.columns:
            data[column] = pd.to_numeric(
                data[column],
                errors="coerce",
            )

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


def apply_filters(data, quarters, territories, stages=None):
    result = data.copy()

    if "quarter" in result.columns:
        result = result[
            result["quarter"].isin(quarters)
        ]

    if "territory_id" in result.columns:
        result = result[
            result["territory_id"].isin(territories)
        ]

    if stages is not None and "stage_name" in result.columns:
        result = result[
            result["stage_name"].isin(stages)
        ]

    return result.copy()


def format_percentage(value):
    if pd.isna(value):
        return "—"

    return f"{value:.2f}%"


def show_empty_message(message):
    st.info(message)


# ==================================================
# 4. SIDEBAR AND FORECAST VALIDATION
# ==================================================

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
        "Forecast summary is missing required columns: "
        + ", ".join(missing_columns)
    )
    st.stop()


forecast = prepare_categories(
    forecast,
    [
        "quarter",
        "territory_id",
        "stage_name",
    ],
)

forecast = safe_numeric(
    forecast,
    required_forecast_columns,
)


# Remove rows that cannot contribute to the main metrics.
forecast = forecast.dropna(
    subset=required_forecast_columns
)


if forecast.empty:
    st.error(
        "No usable forecast rows remain after data validation."
    )
    st.stop()


# ==================================================
# 5. SIDEBAR FILTERS
# ==================================================

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
    "Sales Stage",
    options=stages,
    default=stages,
)


filtered = apply_filters(
    forecast,
    selected_quarters,
    selected_territories,
    selected_stages,
)


# ==================================================
# 6. FORECAST OVERVIEW
# ==================================================

st.divider()
st.subheader("1. Forecast Overview")


if filtered.empty:
    show_empty_message(
        "No forecast records match the selected filters. "
        "Select at least one quarter, territory, and stage."
    )
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
    "Baseline Weighted Pipeline",
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


# ==================================================
# 7. FORECAST ANALYSIS
# ==================================================

st.divider()
st.subheader("2. Forecast Analysis")

left, right = st.columns(2)


with left:

    st.markdown("**Adjusted Expected Revenue by Quarter**")

    quarter_data = (
        filtered.groupby(
            "quarter",
            as_index=False,
        )["adjusted_expected_revenue"]
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
        show_empty_message(
            "Quarterly forecast data is unavailable."
        )


with right:

    st.markdown("**Adjusted Expected Revenue by Territory**")

    territory_data = (
        filtered.groupby(
            "territory_id",
            as_index=False,
        )["adjusted_expected_revenue"]
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
        show_empty_message(
            "Territory forecast data is unavailable."
        )


# ==================================================
# 8. FORECAST DETAILS
# ==================================================

st.divider()
st.subheader("3. Forecast Details")


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


sort_columns = [
    column
    for column in [
        "quarter",
        "territory_id",
        "stage_name",
    ]
    if column in filtered.columns
]


forecast_details = filtered[detail_columns].copy()

if sort_columns:
    forecast_details = forecast_details.sort_values(
        sort_columns,
        na_position="last",
    )


st.dataframe(
    forecast_details,
    use_container_width=True,
    hide_index=True,
)


# ==================================================
# 9. SCENARIO COMPARISON
# ==================================================

st.divider()
st.subheader("4. Scenario Comparison")

show_data_status(
    "scenario_summary.csv",
    scenarios_error,
)


if scenarios.empty:

    show_empty_message(
        "Scenario summary is not available yet."
    )

else:

    scenario_view = prepare_categories(
        scenarios,
        [
            "scenario",
            "quarter",
            "territory_id",
        ],
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

        scenario_view = safe_numeric(
            scenario_view,
            scenario_required,
        )

        scenario_view = apply_filters(
            scenario_view,
            selected_quarters,
            selected_territories,
            selected_stages,
        )

        if scenario_view.empty:

            show_empty_message(
                "No scenario rows match the selected filters."
            )

        else:

            scenario_totals = (
                scenario_view.groupby(
                    "scenario",
                    as_index=False,
                )
                .agg(
                    opportunity_count=(
                        "opportunity_count",
                        "sum",
                    ),
                    total_amount=(
                        "total_amount",
                        "sum",
                    ),
                    total_weighted_pipeline=(
                        "total_weighted_pipeline",
                        "sum",
                    ),
                )
                .sort_values("scenario")
            )

            st.markdown(
                "**Weighted Pipeline by Scenario**"
            )

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


# ==================================================
# 10. HISTORICAL FORECAST ACCURACY
# ==================================================

st.divider()
st.subheader("5. Historical Forecast Accuracy")

show_data_status(
    "forecast_accuracy.csv",
    accuracy_error,
)


if accuracy.empty:

    show_empty_message(
        "Historical forecast accuracy results are not available yet."
    )

else:

    accuracy_view = accuracy.copy()

    # Model filter
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
            accuracy_view["model"]
            .astype(str)
            .isin(selected_models)
        ]


    # Horizon filter
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


    # Convert accuracy metrics.
    accuracy_view = safe_numeric(
        accuracy_view,
        [
            "evaluated_snapshot_rows",
            "expected_revenue",
            "actual_booked_revenue",
            "error",
            "wape_pct",
            "bias_pct",
        ],
    )


    if accuracy_view.empty:

        show_empty_message(
            "No accuracy rows match the selected filters."
        )

    else:

        # Overall WAPE chart
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
                [
                    "horizon_bucket",
                    "model",
                ]
            )

            st.markdown(
                "**Overall WAPE by Model and Horizon**"
            )

            st.bar_chart(
                overall_wape.set_index("chart_label")[
                    "wape_pct"
                ]
            )

            st.caption(
                "WAPE measures forecast error as a percentage "
                "of actual booked revenue. Lower is better."
            )

        else:

            show_empty_message(
                "Overall WAPE rows are not available for the "
                "selected filters."
            )


        # Bias chart
        if (
            "bias_pct" in accuracy_view.columns
            and "model" in accuracy_view.columns
            and "horizon_bucket" in accuracy_view.columns
        ):

            bias_data = accuracy_view.copy()

            if "segment_type" in bias_data.columns:

                bias_data = bias_data[
                    bias_data["segment_type"]
                    .astype(str)
                    .str.lower()
                    .eq("overall")
                ]

            if not bias_data.empty:

                bias_data["chart_label"] = (
                    bias_data["model"].astype(str)
                    + " | "
                    + bias_data["horizon_bucket"].astype(str)
                )

                bias_data = bias_data.sort_values(
                    [
                        "horizon_bucket",
                        "model",
                    ]
                )

                st.markdown(
                    "**Forecast Bias by Model and Horizon**"
                )

                st.bar_chart(
                    bias_data.set_index("chart_label")[
                        "bias_pct"
                    ]
                )

                st.caption(
                    "Positive bias indicates overforecasting. "
                    "Negative bias indicates underforecasting."
                )


        # Accuracy table
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


# ==================================================
# 11. PROBABILITY EVALUATION
# ==================================================

st.divider()
st.subheader("6. Probability Evaluation")

show_data_status(
    "forecast_evaluation.csv",
    evaluation_error,
)


if evaluation.empty:

    show_empty_message(
        "Probability evaluation results are not available yet."
    )

else:

    evaluation_view = evaluation.copy()

    st.markdown(
        "**Baseline vs Adjusted Probability Performance**"
    )

    if "model" in evaluation_view.columns:

        evaluation_models = sorted(
            evaluation_view["model"]
            .dropna()
            .astype(str)
            .unique()
        )

        selected_evaluation_models = st.multiselect(
            "Evaluation Model",
            options=evaluation_models,
            default=evaluation_models,
            key="evaluation_models",
        )

        evaluation_view = evaluation_view[
            evaluation_view["model"]
            .astype(str)
            .isin(selected_evaluation_models)
        ]


    if evaluation_view.empty:

        show_empty_message(
            "No probability evaluation rows match the selected models."
        )

    else:

        if "brier_score" in evaluation_view.columns:

            evaluation_view = safe_numeric(
                evaluation_view,
                ["brier_score"],
            )

            brier_columns = [
                column
                for column in [
                    "model",
                    "evaluated_opportunities",
                    "brier_score",
                ]
                if column in evaluation_view.columns
            ]

            st.dataframe(
                evaluation_view[brier_columns],
                use_container_width=True,
                hide_index=True,
            )

            if "model" in evaluation_view.columns:

                brier_chart = (
                    evaluation_view.groupby("model")[
                        "brier_score"
                    ]
                    .mean()
                    .sort_values()
                )

                st.markdown("**Brier Score Comparison**")

                st.bar_chart(brier_chart)

            st.caption(
                "Brier score measures the accuracy of probability "
                "predictions. Lower values indicate better "
                "probabilistic performance."
            )

        else:

            st.warning(
                "The evaluation file does not contain a "
                "`brier_score` column."
            )

            st.dataframe(
                evaluation_view,
                use_container_width=True,
                hide_index=True,
            )


# ==================================================
# 12. PROJECT METHODOLOGY AND LIMITATIONS
# ==================================================

st.divider()
st.subheader("7. Project Notes")

note_left, note_right = st.columns(2)

with note_left:

    st.markdown(
        """
        **Methodology**

        - Reproducible synthetic sales pipeline data.
        - Baseline stage-probability weighted forecast.
        - Historical stage conversion and opportunity adjustments.
        - Pessimistic, baseline and optimistic scenarios.
        - Historical forecast evaluation against recorded bookings.
        - Data-quality and anomaly validation.
        """
    )


with note_right:

    st.markdown(
        """
        **Limitations**

        - All records are synthetic.
        - Baseline stage probabilities are example assumptions.
        - Adjusted forecasts are rule-based, not machine learning.
        - WAPE remains high, particularly at longer horizons.
        - Results are not production-ready predictions.
        - No live CRM or production data integration.
        """
    )


st.caption(
    "YottaFlex Forecast | Sales Forecasting Proof of Concept"
)
