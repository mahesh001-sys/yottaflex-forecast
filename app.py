from pathlib import Path

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parent
PROCESSED = ROOT / "data" / "processed"

st.set_page_config(
    page_title="Sales Forecast Dashboard",
    page_icon="📊",
    layout="wide",
)

st.title("Sales Forecast Dashboard")
st.caption("Pipeline, scenario comparisons, and historical forecast accuracy")


@st.cache_data
def load_csv(filename):
    path = PROCESSED / filename
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


forecast = load_csv("forecast_summary.csv")
scenarios = load_csv("scenario_summary.csv")
accuracy = load_csv("forecast_accuracy.csv")
evaluation = load_csv("forecast_evaluation.csv")


def money(value):
    if pd.isna(value):
        return "—"
    return f"${value:,.0f}"


def show_missing(filename):
    st.warning(f"Could not find `data/processed/{filename}`.")


# Sidebar filters
st.sidebar.header("Filters")

if forecast.empty:
    show_missing("forecast_summary.csv")
    st.stop()

for column in ["quarter", "territory_id", "stage_name"]:
    if column not in forecast.columns:
        forecast[column] = "Unknown"
    forecast[column] = forecast[column].fillna("Unknown").astype(str)

quarters = sorted(forecast["quarter"].unique())
territories = sorted(forecast["territory_id"].unique())

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

filtered = forecast[
    forecast["quarter"].isin(selected_quarters)
    & forecast["territory_id"].isin(selected_territories)
].copy()

# Key metrics
st.subheader("Forecast overview")

if filtered.empty:
    st.info("No forecast rows match the selected filters.")
    st.stop()

opportunity_count = filtered["opportunity_count"].sum()
total_amount = filtered["total_amount"].sum()
weighted_pipeline = filtered["total_weighted_pipeline"].sum()
adjusted_revenue = filtered["adjusted_expected_revenue"].sum()

metric1, metric2, metric3, metric4 = st.columns(4)
metric1.metric("Opportunities", f"{opportunity_count:,.0f}")
metric2.metric("Total pipeline", money(total_amount))
metric3.metric("Weighted pipeline", money(weighted_pipeline))
metric4.metric("Adjusted expected revenue", money(adjusted_revenue))

if "snapshot_date" in filtered.columns:
    snapshot_dates = pd.to_datetime(
        filtered["snapshot_date"], errors="coerce"
    ).dropna()
    if not snapshot_dates.empty:
        st.caption(f"Snapshot date: {snapshot_dates.max().date()}")

# Forecast views
left, right = st.columns(2)

with left:
    st.subheader("Adjusted expected revenue by quarter")
    quarter_data = (
        filtered.groupby("quarter", as_index=False)["adjusted_expected_revenue"]
        .sum()
        .sort_values("quarter")
    )
    st.bar_chart(
        quarter_data.set_index("quarter")["adjusted_expected_revenue"]
    )

with right:
    st.subheader("Adjusted expected revenue by territory")
    territory_data = (
        filtered.groupby("territory_id", as_index=False)["adjusted_expected_revenue"]
        .sum()
        .sort_values("adjusted_expected_revenue", ascending=False)
    )
    st.bar_chart(
        territory_data.set_index("territory_id")["adjusted_expected_revenue"]
    )

st.subheader("Forecast detail")
st.dataframe(
    filtered.sort_values(
        ["quarter", "territory_id", "stage_name"],
        na_position="last",
    ),
    use_container_width=True,
    hide_index=True,
)

# Scenario comparison
st.subheader("Scenario comparison")

if scenarios.empty:
    st.info("Scenario summary is not available yet.")
else:
    scenario_view = scenarios.copy()
    for column in ["scenario", "quarter", "territory_id"]:
        if column not in scenario_view.columns:
            scenario_view[column] = "Unknown"
        scenario_view[column] = (
            scenario_view[column].fillna("Unknown").astype(str)
        )

    scenario_view = scenario_view[
        scenario_view["quarter"].isin(selected_quarters)
        & scenario_view["territory_id"].isin(selected_territories)
    ]

    if scenario_view.empty:
        st.info("No scenario rows match the selected filters.")
    else:
        scenario_totals = (
            scenario_view.groupby("scenario", as_index=False)
            .agg(
                opportunity_count=("opportunity_count", "sum"),
                total_amount=("total_amount", "sum"),
                total_weighted_pipeline=("total_weighted_pipeline", "sum"),
            )
            .sort_values("scenario")
        )

        st.bar_chart(
            scenario_totals.set_index("scenario")["total_weighted_pipeline"]
        )
        st.dataframe(
            scenario_totals,
            use_container_width=True,
            hide_index=True,
        )

# Historical accuracy
st.subheader("Historical forecast accuracy")

if accuracy.empty:
    st.info("Forecast accuracy results are not available yet.")
else:
    accuracy_view = accuracy.copy()

    if "model" in accuracy_view.columns:
        models = sorted(accuracy_view["model"].dropna().astype(str).unique())
        selected_models = st.multiselect(
            "Models",
            options=models,
            default=models,
            key="accuracy_models",
        )
        accuracy_view = accuracy_view[
            accuracy_view["model"].astype(str).isin(selected_models)
        ]

    if "horizon_bucket" in accuracy_view.columns:
        horizons = sorted(
            accuracy_view["horizon_bucket"].dropna().astype(str).unique()
        )
        selected_horizons = st.multiselect(
            "Snapshot-to-close horizon",
            options=horizons,
            default=horizons,
            key="accuracy_horizons",
        )
        accuracy_view = accuracy_view[
            accuracy_view["horizon_bucket"].astype(str).isin(selected_horizons)
        ]

    if not accuracy_view.empty:
        accuracy_cols = [
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

        # Keep the chart readable by plotting overall WAPE only.
        if {"wape_pct", "segment_type", "model", "horizon_bucket"}.issubset(
            accuracy_view.columns
        ):
            overall_wape = accuracy_view[
                accuracy_view["segment_type"].astype(str).str.lower() == "overall"
            ].copy()

            if not overall_wape.empty:
                overall_wape["chart_label"] = (
                    overall_wape["model"].astype(str)
                    + " | "
                    + overall_wape["horizon_bucket"].astype(str)
                )
                overall_wape = overall_wape.sort_values(
                    ["horizon_bucket", "model"]
                )

                st.caption("Overall WAPE by model and snapshot-to-close horizon")
                st.bar_chart(
                    overall_wape.set_index("chart_label")["wape_pct"]
                )
            else:
                st.info("Overall WAPE rows are not available for the selected filters.")

        st.dataframe(
            accuracy_view[accuracy_cols],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No accuracy rows match the selected filters.")

# Brier score
st.subheader("Probability calibration")

if evaluation.empty:
    st.info("Brier score results are not available yet.")
else:
    st.dataframe(
        evaluation,
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        "For Brier score, lower values indicate better probability predictions."
    )