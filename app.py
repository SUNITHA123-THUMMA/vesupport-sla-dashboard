import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus

# --------------------------------------------------
# 1. PAGE CONFIGURATION
# --------------------------------------------------
st.set_page_config(
    page_title="VeSupport SLA Dashboard",
    page_icon="📊",
    layout="wide"
)

st.title("📊 VeSupport SLA Management Dashboard")
st.caption("Live ticket data from MySQL")

# --------------------------------------------------
# 2. DATABASE CONNECTION
# --------------------------------------------------
@st.cache_resource
def get_engine():
    db = st.secrets["mysql"]

    user = quote_plus(db["user"])
    password = quote_plus(db["password"])
    host = db["host"]
    port = db.get("port", 3306)
    database = db["database"]

    connection_url = (
        f"mysql+pymysql://{user}:{password}"
        f"@{host}:{port}/{database}"
    )

    return create_engine(
        connection_url,
        pool_pre_ping=True,
        pool_recycle=1800
    )


# --------------------------------------------------
# 3. LOAD DATA FROM YOUR SQL QUERIES
# --------------------------------------------------
@st.cache_data(ttl=60)
def load_data():
    engine = get_engine()

    ticket_query = text("""
        SELECT
            tfv.ticket_id,
            t.title,
            t.priority,
            MAX(CASE WHEN tfv.field_id = 1
                THEN tfv.value END) AS ticket_type,
            MAX(CASE WHEN tfv.field_id = 2
                THEN tfv.value END) AS `group`,
            MAX(CASE WHEN tfv.field_id = 3
                THEN tfv.value END) AS sub_section,
            MAX(CASE WHEN tfv.field_id = 4
                THEN tfv.value END) AS business_unit,
            t.state,
            u.name AS assignee_name,
            t.requester_identity,
            t.source,
            DATE(ADDTIME(t.created_at, '05:30:00'))
                AS created_date,
            DATE(ADDTIME(t.updated_at, '05:30:00'))
                AS updated_date
        FROM ticket_field_values tfv
        RIGHT JOIN tickets t
            ON tfv.ticket_id = t.id
        LEFT JOIN users u
            ON t.assignee_id = u.id
        GROUP BY
            tfv.ticket_id,
            t.title,
            t.priority,
            t.state,
            u.name,
            t.requester_identity,
            t.source,
            t.created_at,
            t.updated_at
        ORDER BY tfv.ticket_id DESC
    """)

    daily_query = text("""
        SELECT
            d.date,
            SUM(d.created_tickets) AS created_tickets,
            SUM(d.resolved_tickets) AS resolved_tickets
        FROM (
            SELECT
                DATE(t.created_at + INTERVAL 330 MINUTE) AS date,
                COUNT(DISTINCT t.id) AS created_tickets,
                0 AS resolved_tickets
            FROM tickets t
            GROUP BY DATE(t.created_at + INTERVAL 330 MINUTE)

            UNION ALL

            SELECT
                DATE(te.created_at + INTERVAL 330 MINUTE) AS date,
                0 AS created_tickets,
                COUNT(DISTINCT te.ticket_id) AS resolved_tickets
            FROM timeline_events te
            WHERE te.kind = 'close'
            GROUP BY DATE(te.created_at + INTERVAL 330 MINUTE)
        ) d
        GROUP BY d.date
        ORDER BY d.date
    """)

    with engine.connect() as conn:
        tickets = pd.read_sql(ticket_query, conn)
        daily = pd.read_sql(daily_query, conn)

    daily["date"] = pd.to_datetime(daily["date"])

    return tickets, daily


# --------------------------------------------------
# 4. DATABASE STATUS AND REFRESH
# --------------------------------------------------
col1, col2 = st.columns([3, 1])

with col1:
    st.info("Data refreshes automatically every 60 seconds.")

with col2:
    if st.button("🔄 Refresh data"):
        load_data.clear()
        st.rerun()

try:
    engine = get_engine()

    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    st.success("MySQL database connection successful!")

    tickets, daily = load_data()

except Exception as e:
    st.error("Unable to connect to MySQL or execute the queries.")
    st.code(str(e))
    st.stop()


# --------------------------------------------------
# 5. FILTERS
# --------------------------------------------------
if tickets.empty:
    st.warning("The database query returned no ticket records.")
    st.stop()

tickets["created_date"] = pd.to_datetime(
    tickets["created_date"], errors="coerce"
)

states = sorted(
    tickets["state"].dropna().astype(str).unique().tolist()
)

priorities = sorted(
    tickets["priority"].dropna().astype(str).unique().tolist()
)

f1, f2 = st.columns(2)

with f1:
    selected_states = st.multiselect(
        "Filter by ticket state",
        states,
        default=states
    )

with f2:
    selected_priorities = st.multiselect(
        "Filter by priority",
        priorities,
        default=priorities
    )

filtered = tickets[
    tickets["state"].astype(str).isin(selected_states)
    & tickets["priority"].astype(str).isin(selected_priorities)
]


# --------------------------------------------------
# 6. KPI CARDS
# --------------------------------------------------

states = filtered["state"].astype(str).str.strip().str.lower()

total_tickets = len(filtered)

closed_tickets = states.isin(["closed", "resolved"]).sum()

open_tickets = (~states.isin(
    ["closed", "resolved", "rejected"]
)).sum()

k1, k2, k3 = st.columns(3)

k1.metric("Total Tickets", f"{total_tickets:,}")
k2.metric("Closed / Resolved Tickets", f"{closed_tickets:,}")
k3.metric("Open Tickets", f"{open_tickets:,}")


# --------------------------------------------------
# 7. DAILY SLA TREND
# --------------------------------------------------
st.subheader("Daily Ticket Trends")

if not daily.empty:
    fig = px.line(
        daily,
        x="date",
        y=["created_tickets", "resolved_tickets"],
        markers=True,
        title="Created vs. Closed Tickets by Date",
        labels={
            "date": "Date",
            "value": "Number of Tickets",
            "variable": "Metric"
        }
    )

    st.plotly_chart(fig, width="stretch")
else:
    st.warning("No daily SLA records were returned.")


# --------------------------------------------------
# 8. TICKET BREAKDOWNS
# --------------------------------------------------
left, right = st.columns(2)

with left:
    st.subheader("Tickets by Priority")

    priority_data = (
        filtered["priority"]
        .fillna("Unknown")
        .value_counts()
        .rename_axis("Priority")
        .reset_index(name="Tickets")
    )

    fig_priority = px.bar(
        priority_data,
        x="Priority",
        y="Tickets",
        title="Ticket Count by Priority"
    )

    st.plotly_chart(fig_priority, width="stretch")

with right:
    st.subheader("Tickets by State")

    state_data = (
        filtered["state"]
        .fillna("Unknown")
        .value_counts()
        .rename_axis("State")
        .reset_index(name="Tickets")
    )

    fig_state = px.pie(
        state_data,
        names="State",
        values="Tickets",
        title="Ticket State Distribution",
        hole=0.4
    )

    st.plotly_chart(fig_state, width="stretch")


# ------------------------------------------
# ASSIGNEE WORKLOAD
# ------------------------------------------

# Workload by assignee - descending ticket count

st.subheader("Workload by Assignee")

workload = (
    filtered.assign(
        assignee_name=filtered["assignee_name"].fillna("Unassigned")
    )
    .groupby("assignee_name")
    .size()
    .reset_index(name="ticket_count")
    .sort_values("ticket_count", ascending=False)
)

if not workload.empty:
    fig = px.bar(
        workload,
        x="ticket_count",
        y="assignee_name",
        orientation="h",
        text="ticket_count",
        labels={
            "ticket_count": "Ticket Count",
            "assignee_name": "Assignee Name"
        },
        title="Workload by Assignee"
    )

    # Show every assignee name and sort by ticket count descending
    fig.update_layout(
        height=max(600, len(workload) * 35),
        yaxis=dict(
            tickmode="array",
            tickvals=workload["assignee_name"].tolist(),
            ticktext=workload["assignee_name"].tolist(),
            categoryorder="array",
            categoryarray=workload["assignee_name"].tolist(),
            autorange="reversed",
            automargin=True
        ),
        xaxis_title="Number of Tickets",
        yaxis_title="Assignee Name",
        showlegend=False
    )

    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, width="stretch")
else:
    st.info("No workload data available.")



# --------------------------------------------------
# 9. TICKET DETAILS TABLE
# --------------------------------------------------
st.subheader("Ticket Details")

display_columns = [
    "ticket_id",
    "title",
    "priority",
    "ticket_type",
    "group",
    "sub_section",
    "business_unit",
    "state",
    "assignee_name",
    "created_date",
    "updated_date"
]

display_columns = [
    c for c in display_columns if c in filtered.columns
]

st.dataframe(
    filtered[display_columns],
    width="stretch",
    hide_index=True
)

# --------------------------------------------------
# 10. DOWNLOAD RESULTS
# --------------------------------------------------
csv = filtered.to_csv(index=False).encode("utf-8")

st.download_button(
    "⬇️ Download Ticket Data (CSV)",
    data=csv,
    file_name="vesupport_ticket_details.csv",
    mime="text/csv"
)

st.caption(
    "Dashboard data is queried from MySQL. "
    "Daily created and closed counts are grouped by event date."
)
