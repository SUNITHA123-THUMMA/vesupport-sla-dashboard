
import pandas as pd
from sqlalchemy import text


TICKET_DETAILS_QUERY = """
SELECT
    t.id AS ticket_id,
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

FROM vesupport.tickets t

LEFT JOIN vesupport.ticket_field_values tfv
    ON tfv.ticket_id = t.id

LEFT JOIN vesupport.users u
    ON t.assignee_id = u.id

GROUP BY
    t.id,
    t.title,
    t.priority,
    t.state,
    u.name,
    t.requester_identity,
    t.source,
    t.created_at,
    t.updated_at

ORDER BY t.id DESC
"""


DAILY_SLA_QUERY = """
SELECT
    d.date,
    SUM(d.created_tickets) AS created_tickets,
    SUM(d.resolved_tickets) AS resolved_tickets
FROM (
    SELECT
        DATE(t.created_at + INTERVAL 330 MINUTE) AS date,
        COUNT(DISTINCT t.id) AS created_tickets,
        0 AS resolved_tickets
    FROM vesupport.tickets t
    GROUP BY DATE(t.created_at + INTERVAL 330 MINUTE)

    UNION ALL

    SELECT
        DATE(te.created_at + INTERVAL 330 MINUTE) AS date,
        0 AS created_tickets,
        COUNT(DISTINCT te.ticket_id) AS resolved_tickets
    FROM vesupport.timeline_events te
    WHERE te.kind = 'close'
    GROUP BY DATE(te.created_at + INTERVAL 330 MINUTE)
) d

GROUP BY d.date
ORDER BY d.date
"""


def fetch_ticket_details(engine):
    """Return ticket-level details from MySQL."""
    return pd.read_sql(
        text(TICKET_DETAILS_QUERY),
        con=engine
    )


def fetch_daily_sla(engine):
    """Return daily ticket creation and closure totals."""
    return pd.read_sql(
        text(DAILY_SLA_QUERY),
        con=engine
    )
