import asyncio
import os
from datetime import datetime
from functools import partial

import gspread
from google.oauth2.service_account import Credentials

from src.logger import get_logger

log = get_logger("database.sheets")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

HEADERS = [
    "Order ID", "Timestamp", "Customer Name", "Phone",
    "Location", "Dough", "Sauce", "Toppings", "Cook Style", "Notes", "Status"
]

_SERVICE_ACCOUNT_PATH = os.path.join(
    os.path.dirname(__file__), "service_account.json"
)


def _get_sheet() -> gspread.Worksheet:
    creds = Credentials.from_service_account_file(_SERVICE_ACCOUNT_PATH, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "")
    if not sheet_id:
        raise RuntimeError("GOOGLE_SHEET_ID not set in .env")
    return gc.open_by_key(sheet_id).sheet1


def _ensure_headers(sheet: gspread.Worksheet) -> None:
    first_row = sheet.row_values(1)
    if first_row != HEADERS:
        sheet.insert_row(HEADERS, 1)
        log.info("Inserted header row into sheet")


def _append_order_sync(order: dict) -> int:
    sheet = _get_sheet()
    _ensure_headers(sheet)
    all_rows = sheet.get_all_values()
    order_id = len(all_rows)  # header = row 1, first order = row 2 → id 1
    row = [
        str(order_id),
        order["timestamp"],
        order["customer_name"],
        order["phone"],
        order["location"],
        order["dough"],
        order["sauce"],
        order["toppings"],
        order["cook_style"],
        order.get("notes", ""),
        "New",
    ]
    sheet.append_row(row, value_input_option="USER_ENTERED")
    log.info("Order #%d appended to sheet", order_id)
    return order_id


async def append_order(order: dict) -> int:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(_append_order_sync, order))
