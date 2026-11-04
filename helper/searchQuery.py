# ==============================
# Standard Library
# ==============================
import re
import time
import threading

# ==============================
# Third-Party Libraries
# ==============================
import psycopg2
import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlalchemy.engine import URL
from langchain_community.utilities import SQLDatabase

# ==============================
# Internal Modules
# ==============================
from core.config import settings

# ==========================================================================
# The SQL written by the AI model is never trusted. Before it runs:
#   1. it must be ONE plain SELECT on the ONE table of that search
#   2. only simple search conditions are allowed (no sub-query, no other
#      table, no unknown function)
#   3. the selected columns are replaced with our own fixed list, so the
#      result always matches the fields returned to the frontend
#   4. the number of rows is capped
# It then runs in a read-only transaction with a time limit.
# ==========================================================================

# Columns returned to the frontend for each search table, in this order
SEARCH_COLUMNS = {
    "pm_risk_table": [
        "stakeholder", "customer_name", "project_name", "project_vertical", "project_type",
        "risk_id", "risk_category", "specific_risk", "risk_event", "risk_root_cause",
        "risk_impact", "likelihood_level", "likelihood_justification",
        "impact_level", "impact_justification", "risk_rating", "risk_mitigation_plan",
        "risk_mitigation_control_owner_group",
    ],
    "sc_risk_table": [
        "stakeholder", "risk_id", "customer", "project_name", "vertical",
        "project_description", "product_service_offering", "risk_category",
        "risk_desc", "risk_event", "root_cause", "risk_impact", "likelihood", "likelihood_justification",
        "impact", "impact_justification", "risk_rating", "key_mitigation",
        "residual_risk_rating", "control_owner",
    ],
    "lesson_learn": [
        "ll_id", "sfdc_opportunity_id", "customer_name", "project_name",
        "sfdc_segment", "lead_project_manager", "achiement_improvement",
        "category", "challenge", "resolution", "lesson_learned",
        "stakeholder_pic", "segment",
    ],
    "pm_issues": [
        "issue_id", "customer_segment", "project_type", "project_complexity",
        "issue_description", "issue_reason", "issue_owner", "issue_action_plan",
        "issue_help_needed", "issue_impacted_deliverables_milestone", "issue_resolution",
    ],
}

# Parts a SELECT is allowed to have (no INTO, JOIN, GROUP BY, WITH, FOR UPDATE, ...)
ALLOWED_SELECT_PARTS = {"expressions", "from", "from_", "where", "order", "limit", "offset", "distinct"}

# Things allowed inside WHERE / ORDER BY. Anything else is refused,
# including every function sqlglot does not know by name (pg_sleep, dblink, ...).
ALLOWED_NODES = (
    exp.Where, exp.Order, exp.Ordered, exp.Offset,
    exp.Column, exp.Identifier, exp.Literal, exp.Boolean, exp.Null,
    exp.And, exp.Or, exp.Not, exp.Paren,
    exp.ILike, exp.Like, exp.RegexpILike, exp.RegexpLike, exp.SimilarTo, exp.Escape,
    exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE,
    exp.Is, exp.In, exp.Between, exp.Any, exp.All, exp.Array, exp.Tuple,
    exp.Case, exp.If, exp.Cast, exp.DataType, exp.DataTypeParam,
    exp.Add, exp.Sub, exp.Mul, exp.Neg,
    exp.Lower, exp.Upper, exp.Trim, exp.Length, exp.Coalesce, exp.Nullif,
    exp.DPipe, exp.Concat, exp.StrPosition, exp.Greatest, exp.Least, exp.Abs,
)


class UnsafeQueryError(Exception):
    """The generated SQL is not a query we are willing to run."""


# Table description given to the AI model, built once per table and reused.
# Only the column names and types are included, never rows of real data.
# (A change to a table's columns is picked up after a backend restart.)
_search_dbs = {}
_search_dbs_lock = threading.Lock()

def get_search_db(table: str) -> SQLDatabase:
    with _search_dbs_lock:
        db = _search_dbs.get(table)

        if db is None:
            uri = URL.create(
                "postgresql+psycopg2",
                username=settings.DB_USER,
                password=settings.DB_PASSWORD,
                host=settings.DB_HOST,
                port=int(settings.DB_PORT_R),
                database=settings.DB_NAME
            )
            db = SQLDatabase.from_uri(uri, include_tables=[table], sample_rows_in_table_info=0, engine_args={'pool_pre_ping': True, 'pool_recycle': 300})

            # the table structure is now in memory, no connection needs to stay open
            db._engine.dispose()
            _search_dbs[table] = db

        return db


# Cut the first SQL statement out of the model's answer
def extract_select(response_text: str) -> str:
    match = re.search(r"\bselect\b", response_text or "", re.IGNORECASE)
    if not match:
        raise UnsafeQueryError("no SELECT statement found")

    text = response_text[match.start():]

    # stop at the first ';' that is not inside quotes
    quote = None
    for index, char in enumerate(text):
        if quote:
            if char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif char == ";":
            return text[:index]

    # no ';' → drop a closing markdown code fence if the model added one
    return text.split("```")[0]


# Check the generated SQL and rebuild it into the query that will really run
def build_safe_query(response_text: str, table: str) -> str:
    columns = SEARCH_COLUMNS[table]
    max_rows = settings.DB_SEARCH_MAX_ROWS

    try:
        query = sqlglot.parse_one(extract_select(response_text), read="postgres")
    except SqlglotError as e:
        raise UnsafeQueryError(f"cannot read the SQL: {str(e).splitlines()[0]}")

    # 1. one plain SELECT
    if not isinstance(query, exp.Select):
        raise UnsafeQueryError(f"not a plain SELECT ({type(query).__name__})")

    for part, value in query.args.items():
        if value and part not in ALLOWED_SELECT_PARTS:
            raise UnsafeQueryError(f"'{part}' is not allowed")

    distinct = query.args.get("distinct")
    if distinct and distinct.args.get("on"):
        raise UnsafeQueryError("DISTINCT ON is not allowed")

    # 2. from the expected table only
    from_clause = query.args.get("from_") or query.args.get("from")
    source = from_clause.this if from_clause else None
    if not isinstance(source, exp.Table) or not isinstance(source.this, exp.Identifier):
        raise UnsafeQueryError("query must read from a table")

    for part, value in source.args.items():
        if value and part not in ("this", "db", "alias"):
            raise UnsafeQueryError(f"'{part}' on the table is not allowed")

    if source.name.lower() != table or source.db.lower() not in ("", "public"):
        raise UnsafeQueryError(f"table '{source.sql(dialect='postgres')}' is not allowed, expected '{table}'")

    # 3. only simple conditions in WHERE / ORDER BY / OFFSET
    for part in ("where", "order", "offset"):
        clause = query.args.get(part)
        if not clause:
            continue
        for node in clause.walk():
            if not isinstance(node, ALLOWED_NODES):
                raise UnsafeQueryError(f"'{type(node).__name__}' is not allowed in {part.upper()}")

    # 4. always select our own columns, in our own order
    query.set("expressions", [exp.column(name, quoted=True) for name in columns])

    # 5. cap the number of rows ("all" in the question gives no LIMIT)
    limit = query.args.get("limit")
    rows = max_rows
    if isinstance(limit, exp.Limit) and isinstance(limit.expression, exp.Literal) and limit.expression.is_int:
        rows = min(int(limit.expression.this), max_rows)
    query.set("limit", exp.Limit(expression=exp.Literal.number(rows)))

    offset = query.args.get("offset")
    if offset and not (isinstance(offset.expression, exp.Literal) and offset.expression.is_int):
        query.set("offset", None)

    return query.sql(dialect="postgres", comments=False)


# ##################################################################################### #
# Parameter: response_text (SQL from the AI model), table    result: rows, message      #
# Function: check the generated SQL, run it read-only, return rows as list of dict     #
#           message is None when the search ran, otherwise the reason it did not       #
# ##################################################################################### #
def run_search_query(response_text: str, table: str):
    try:
        query = build_safe_query(response_text, table)
    except UnsafeQueryError as e:
        print(f"[search] {table} query refused: {e} | generated: {' '.join((response_text or '').split())[:500]}")
        return [], "The search could not be understood. Please rephrase your question."

    started = time.perf_counter()
    connection = None
    try:
        # Restricted read-only user when configured, otherwise the normal user
        connection = psycopg2.connect(
            host=settings.DB_HOST,
            user=settings.DB_SEARCH_USER or settings.DB_USER,
            password=settings.DB_SEARCH_PASSWORD if settings.DB_SEARCH_USER else settings.DB_PASSWORD,
            database=settings.DB_NAME,
            port=settings.DB_PORT_R
        )
        connection.set_session(readonly=True)

        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = %s", (settings.DB_SEARCH_TIMEOUT_SECONDS * 1000,))
            cursor.execute(query)
            rows = cursor.fetchall()

        # time is logged so the time limit can be tuned from real numbers
        print(f"[search] {table} rows={len(rows)} time={time.perf_counter() - started:.2f}s")
        return [dict(zip(SEARCH_COLUMNS[table], row)) for row in rows], None

    except psycopg2.errors.QueryCanceled:
        print(f"[search] {table} stopped after {settings.DB_SEARCH_TIMEOUT_SECONDS}s time limit | query: {query}")
        return [], "The search took too long. Please make your question more specific."

    except psycopg2.Error as err:
        print(f"[search] {table} failed after {time.perf_counter() - started:.2f}s: {err} | query: {query}")
        return [], "The search could not be completed."

    finally:
        if connection is not None:
            connection.close()
