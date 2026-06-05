import json
import requests
import config
from common import get_auth_token, handle_typedb_response


def query(query: str | list[str], database: str, transaction_type: str = "read") -> str:
    """Executes given TypeQL query (or list of queries) against the given database.

    A single string is sent via the one-shot `/v1/query` endpoint (one transaction,
    one pipeline). A list opens a transaction, submits each entry as an independent
    query, and commits (write/schema) or closes (read).

    Args:
        query: TypeQL query string, or list of query strings to run in one transaction
        database: The name of the database against which the query will be executed
        transaction_type: Transaction type - "read", "write", or "schema" (default: "read")

    Returns:
        Query result as JSON string. For list input, a JSON array of per-query results.
    """
    if isinstance(query, list):
        return _query_batch(query, database, transaction_type)
    return _query_single(query, database, transaction_type)


def _query_single(query: str, database: str, transaction_type: str) -> str:
    token = get_auth_token()
    response = requests.post(
        f"{config.TYPEDB_URL}/v1/query",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "databaseName": database,
            "transactionType": transaction_type,
            "query": query,
            "commit": transaction_type in ("write", "schema"),
        },
    )
    handle_typedb_response(response)
    return response.text


def _query_batch(queries: list[str], database: str, transaction_type: str) -> str:
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}

    open_resp = requests.post(
        f"{config.TYPEDB_URL}/v1/transactions/open",
        headers=headers,
        json={"databaseName": database, "transactionType": transaction_type},
    )
    handle_typedb_response(open_resp)
    txn_id = open_resp.json()["transactionId"]

    try:
        results = []
        for q in queries:
            r = requests.post(
                f"{config.TYPEDB_URL}/v1/transactions/{txn_id}/query",
                headers=headers,
                json={"query": q},
            )
            handle_typedb_response(r)
            results.append(r.json())

        if transaction_type in ("write", "schema"):
            commit_resp = requests.post(
                f"{config.TYPEDB_URL}/v1/transactions/{txn_id}/commit",
                headers=headers,
            )
            handle_typedb_response(commit_resp)
        else:
            requests.post(
                f"{config.TYPEDB_URL}/v1/transactions/{txn_id}/close",
                headers=headers,
            )
        return json.dumps(results)
    except Exception:
        requests.post(
            f"{config.TYPEDB_URL}/v1/transactions/{txn_id}/close",
            headers=headers,
        )
        raise
