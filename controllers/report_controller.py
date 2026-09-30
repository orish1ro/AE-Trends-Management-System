import csv
from datetime import datetime, timedelta

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QMessageBox

from models.inventory_model import compute_status
from utils.errors import report, safe_slot
from utils.validators import ValidationError, clean_date_range
from models.transaction_model import TransactionModel, nice_date

# Orders don't have a literal "Cancelled" status in the schema -- map the
# real OrderStatus values down to the 3-state view the Reports page shows.
STATUS_MAP = {
    "Pending": "Pending",
    "Paid": "Completed",
    "Prepared": "Completed",
    "Shipped": "Completed",
    "Completed": "Completed",
    "Refunded": "Cancelled",
}


def _daterange(start_str, end_str):
    start = datetime.strptime(start_str, "%Y-%m-%d").date()
    end = datetime.strptime(end_str, "%Y-%m-%d").date()
    days, day = [], start
    while day <= end:
        days.append(day)
        day += timedelta(days=1)
    return days


def _hour_label(hour):
    period = "AM" if hour < 12 else "PM"
    display_hour = hour % 12 or 12
    return f"{display_hour} {period}"


class ReportController:
    def __init__(self, db, report_view, dashboard_view):
        self.db = db
        self.report_view = report_view
        self.dashboard_view = dashboard_view
        self.txn_model = TransactionModel(db)
        self.current_rows = []
        self._pl_daily = []
        self._pl_granularity = "Daily"
        self._last_from = None
        self._last_to = None

        self.report_view.filters_changed.connect(self.load_reports)
        self.report_view.export_requested.connect(self.export_report)
        self.report_view.pl_granularity_changed.connect(self.change_pl_granularity)

    # ------------------------------------------------------------------ #
    @safe_slot("Reports Error", parent_attr="report_view")
    def load_reports(self, from_date=None, to_date=None):
        if from_date is None:
            from_date = self.report_view.from_date.date().toString("yyyy-MM-dd")
        if to_date is None:
            to_date = self.report_view.to_date.date().toString("yyyy-MM-dd")

        # A "from" date after the "to" date would quietly show an empty report.
        try:
            clean_date_range(from_date, to_date)
        except ValidationError as exc:
            QMessageBox.warning(self.report_view, "Check the Dates", str(exc))
            return

        with self.db.get_connection() as conn:
            order_rows = conn.execute(
                """
                SELECT o.OrderID, o.OrderDate, o.TotalAmount, o.OrderStatus,
                       c.FullName AS CustomerName, pl.PlatformName,
                       COALESCE(SUM(od.Quantity), 0) AS UnitsSold
                FROM Orders o
                JOIN Customer c ON c.CustomerID = o.CustomerID
                JOIN Platform pl ON pl.PlatformID = o.PlatformID
                LEFT JOIN OrderDetails od ON od.OrderID = o.OrderID
                WHERE date(o.OrderDate) BETWEEN date(?) AND date(?)
                GROUP BY o.OrderID
                ORDER BY o.OrderID DESC
                """,
                (from_date, to_date),
            ).fetchall()

            detail_rows = conn.execute(
                """
                SELECT od.OrderID, od.ProductID, od.Quantity, od.Subtotal,
                       date(o.OrderDate) AS OrderDay
                FROM OrderDetails od
                JOIN Orders o ON o.OrderID = od.OrderID
                WHERE date(o.OrderDate) BETWEEN date(?) AND date(?)
                """,
                (from_date, to_date),
            ).fetchall()

            payment_rows = conn.execute("SELECT OrderID, PaymentMethod FROM Payment").fetchall()

            cost_rows = conn.execute(
                """
                SELECT ProductID, SUM(Quantity * UnitCost) * 1.0 / SUM(Quantity) AS AvgCost
                FROM PurchaseOrderDetails
                GROUP BY ProductID
                """
            ).fetchall()

            po_spend_rows = conn.execute(
                """
                SELECT date(OrderDate) AS d, COALESCE(SUM(TotalCost), 0) AS Total
                FROM PurchaseOrder
                WHERE Status = 'Received' AND date(OrderDate) BETWEEN date(?) AND date(?)
                GROUP BY date(OrderDate)
                """,
                (from_date, to_date),
            ).fetchall()

            # Use 'localtime' here -- OrderDate is now stored in local time
            # (see transaction_model.create_order), and date('now') without
            # the 'localtime' modifier evaluates in UTC, which would put
            # this back out of sync with the chart's "Today" range again.
            today_sales = conn.execute(
                "SELECT COALESCE(SUM(TotalAmount), 0) FROM Orders WHERE date(OrderDate) = date('now', 'localtime')"
            ).fetchone()[0]
            yesterday_sales = conn.execute(
                "SELECT COALESCE(SUM(TotalAmount), 0) FROM Orders WHERE date(OrderDate) = date('now', 'localtime', '-1 day')"
            ).fetchone()[0]
            products = [
                dict(row) for row in conn.execute("SELECT * FROM Product WHERE COALESCE(IsArchived, 0) = 0 AND COALESCE(IsPendingReceipt, 0) = 0")
            ]
            span_days = (datetime.strptime(to_date, "%Y-%m-%d") - datetime.strptime(from_date, "%Y-%m-%d")).days + 1
            prev_end = (datetime.strptime(from_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
            prev_start = (datetime.strptime(from_date, "%Y-%m-%d") - timedelta(days=span_days)).strftime("%Y-%m-%d")
            prev_revenue = conn.execute(
                "SELECT COALESCE(SUM(TotalAmount), 0) FROM Orders WHERE date(OrderDate) BETWEEN date(?) AND date(?)",
                (prev_start, prev_end),
            ).fetchone()[0]

        cost_by_product = {row["ProductID"]: row["AvgCost"] or 0.0 for row in cost_rows}
        payment_by_order = {row["OrderID"]: row["PaymentMethod"] or "—" for row in payment_rows}
        po_spend_by_day = {row["d"]: row["Total"] or 0.0 for row in po_spend_rows}
        product_names = {p["ProductID"]: p["ProductName"] for p in products}

        # --- per-order cost + per-product / per-day aggregates ---
        cost_by_order, qty_by_product, revenue_by_product = {}, {}, {}
        revenue_by_day, cost_by_day = {}, {}
        for d in detail_rows:
            unit_cost = cost_by_product.get(d["ProductID"], 0.0)
            line_cost = unit_cost * d["Quantity"]
            cost_by_order[d["OrderID"]] = cost_by_order.get(d["OrderID"], 0.0) + line_cost
            qty_by_product[d["ProductID"]] = qty_by_product.get(d["ProductID"], 0) + d["Quantity"]
            revenue_by_product[d["ProductID"]] = revenue_by_product.get(d["ProductID"], 0.0) + (d["Subtotal"] or 0.0)
            revenue_by_day[d["OrderDay"]] = revenue_by_day.get(d["OrderDay"], 0.0) + (d["Subtotal"] or 0.0)
            cost_by_day[d["OrderDay"]] = cost_by_day.get(d["OrderDay"], 0.0) + line_cost

        # --- transaction rows (feeds both the new table and the dashboard tab) ---
        rows = []
        order_status_counts = {"Completed": 0, "Pending": 0, "Cancelled": 0}
        for order in order_rows:
            mapped_status = STATUS_MAP.get(order["OrderStatus"], "Pending")
            order_status_counts[mapped_status] = order_status_counts.get(mapped_status, 0) + 1
            revenue = order["TotalAmount"] or 0.0
            cost = cost_by_order.get(order["OrderID"], 0.0)
            order_day = order["OrderDate"][:10]
            rows.append({
                "order": f"ORD-{order['OrderID']:04d}",
                "id": f"ORD-{order['OrderID']:04d}",
                "date": nice_date(order["OrderDate"]),
                "date_sort": order["OrderDate"],
                "chart_label": order_day,
                "customer": order["CustomerName"],
                "type": "Walk-in" if order["PlatformName"] == "Walk-in" else "Online",
                "items": order["UnitsSold"],                 # kept as int -- dashboard reads this
                "items_count": order["UnitsSold"] or 0,
                "payment": payment_by_order.get(order["OrderID"], "—"),
                "total": revenue,
                "profit": revenue - cost,
                "status": order["OrderStatus"],               # raw status, unchanged for the dashboard tab
                "display_status": mapped_status,               # Completed / Pending / Cancelled for Reports
            })

        total_sales = sum(row["total"] for row in rows)

        # --- inventory health ---
        low_stock_items, inventory_health = [], []
        expiring_count, nearest_expiring_days, inventory_value = 0, None, 0.0
        for product in products:
            reorder_level = product.get("ReorderLevel") or 10
            status = compute_status(product["StockQuantity"], product["ExpirationDate"], reorder_level)
            days_left = None
            if product["ExpirationDate"]:
                try:
                    days_left = (datetime.strptime(product["ExpirationDate"][:10], "%Y-%m-%d") - datetime.now()).days
                except ValueError:
                    days_left = None
            stock_qty = product["StockQuantity"] or 0
            stock_value = (product["Price"] or 0) * stock_qty
            inventory_value += stock_value

            if status == "Expired" or stock_qty == 0 or stock_qty <= max(1, reorder_level // 2):
                alert = "Critical"
            elif status in ("Low Stock", "Expiring Soon"):
                alert = "Low Stock"
            else:
                alert = "Healthy"

            inventory_health.append({
                "name": product["ProductName"],
                "category": product["Category"] or "",
                "stock": stock_qty,
                "stock_value": stock_value,
                "units_sold": qty_by_product.get(product["ProductID"], 0),
                "reorder_level": reorder_level,
                "status": alert,
            })

            if status in ("Low Stock", "Expired", "Expiring Soon"):
                low_stock_items.append({
                    "name": product["ProductName"],
                    "category": product["Category"] or "",
                    "stock_qty": stock_qty,
                    "reorder_level": reorder_level,
                    "status": status,
                    "days_left": days_left,
                })
            if status in ("Expiring Soon", "Expired"):
                expiring_count += 1
                if days_left is not None and days_left >= 0:
                    nearest_expiring_days = (
                        days_left if nearest_expiring_days is None else min(nearest_expiring_days, days_left)
                    )

        priority = {"Expired": 0, "Expiring Soon": 1, "Low Stock": 2}
        low_stock_items.sort(key=lambda i: (priority.get(i["status"], 3), i.get("days_left") if i.get("days_left") is not None else 999))
        alert_order = {"Critical": 0, "Low Stock": 1, "Healthy": 2}
        inventory_health.sort(key=lambda i: (alert_order.get(i["status"], 3), i["name"]))

        # --- top products (profitability) ---
        top_products = []
        for product_id, revenue in sorted(revenue_by_product.items(), key=lambda kv: kv[1], reverse=True)[:8]:
            qty = qty_by_product.get(product_id, 0)
            cost = cost_by_product.get(product_id, 0.0) * qty
            profit = revenue - cost
            margin = (profit / revenue * 100) if revenue else 0.0
            top_products.append({
                "name": product_names.get(product_id, f"Product #{product_id}"),
                "qty": qty,
                "revenue": revenue,
                "cost": cost,
                "profit": profit,
                "margin": margin,
            })

        # --- COGS / gross profit ---
        cogs = sum(cost_by_order.values())
        inventory_spend = sum(po_spend_by_day.values())
        gross_profit = total_sales - cogs
        gross_margin = (gross_profit / total_sales * 100) if total_sales else 0.0

        kpis = {
            "revenue": total_sales,
            "revenue_growth": ((total_sales - prev_revenue) / prev_revenue * 100) if prev_revenue else None,
            "cogs": cogs,
            "inventory_spend": inventory_spend,
            "gross_profit": gross_profit,
            "gross_margin": gross_margin,
            # Cash-based check, separate from Gross Profit (which is matched
            # to units actually sold): did the cash spent restocking during
            # this period actually come back through sales in the same
            # period? Negative means money is still tied up in stock that
            # hasn't sold yet -- not necessarily "losing", but not "returned"
            # either.
            "net_profit": total_sales - inventory_spend,
        }

        # --- daily P&L / sales trend series across the whole selected range ---
        order_count_by_day = {}
        for row in rows:
            order_count_by_day[row["chart_label"]] = order_count_by_day.get(row["chart_label"], 0) + 1

        daily_series = []
        for day in _daterange(from_date, to_date):
            key = day.strftime("%Y-%m-%d")
            revenue = revenue_by_day.get(key, 0.0)
            cost = cost_by_day.get(key, 0.0)
            daily_series.append({
                "date": key,
                "label": day.strftime("%b %d"),
                "revenue": revenue,
                "cogs": cost,
                "gross_profit": revenue - cost,
                "orders": order_count_by_day.get(key, 0),
            })

        self._pl_daily = daily_series
        self._last_from, self._last_to = from_date, to_date
        # A single-day filter (Today/Yesterday/a custom one-day range) means
        # daily_series above has exactly one point, which reads as an empty
        # chart. Show an hourly breakdown for that one day instead -- much
        # more useful, and the data actually has real timestamps to support it.
        chart_series = self._compute_hourly_series(from_date) if from_date == to_date else daily_series
        self._pl_daily = chart_series
        # "Daily" always mirrors the current KPI filter above; Weekly/Monthly
        # pull their own wider lookback window (see change_pl_granularity)
        # so switching to them still shows a real trend even when the
        # filter above is something narrow like "Today".
        if self._pl_granularity == "Daily":
            pl_series = chart_series
        else:
            pl_series = self._bucket_series(
                self._compute_daily_series(*self._pl_lookback_range(self._pl_granularity, to_date)),
                self._pl_granularity,
            )
        avg_order_value = (total_sales / len(rows)) if rows else 0.0

        self.current_rows = rows
        display_rows = [{**row, "status": row["display_status"]} for row in rows]

        self.report_view.display_report({
            "kpis": kpis,
            "pl_series": pl_series,
            "pl_granularity": self._pl_granularity,
            "sales_series": chart_series,
            "sales_stats": {"orders": len(rows), "avg_order_value": avg_order_value},
            "order_status": order_status_counts,
            "top_products": top_products,
            "inventory": inventory_health,
            "transactions": display_rows,
            "period_label": f"{nice_date(from_date)} – {nice_date(to_date)}",
            "last_updated": datetime.now().strftime("%I:%M %p").lstrip("0"),
        })

        # --- dashboard tab feed, unchanged from the original behaviour ---
        self.dashboard_view.display_recent_transactions(self.txn_model.get_recent_orders(8))
        self.dashboard_view.update_metrics(
            today_sales, len(low_stock_items),
            sum(1 for row in rows if row["status"] == "Pending"),
            expiring_count,
            ((today_sales - yesterday_sales) / yesterday_sales * 100) if yesterday_sales else None,
            total_orders=len(rows),
            inventory_value=inventory_value,
            expiring_days=nearest_expiring_days,
        )
        # --- rolling 7-day trend for the Sales Performance chart ---
        # Deliberately independent of the "Today/This Week/This Month" filter
        # above: a trend line needs several points to draw a line at all, so
        # picking "Today" (a single day) must not collapse it to one dot.
        chart_to_dt = datetime.now().date()
        chart_from_dt = chart_to_dt - timedelta(days=6)
        chart_from_str, chart_to_str = chart_from_dt.isoformat(), chart_to_dt.isoformat()

        with self.db.get_connection() as conn:
            chart_rows = conn.execute(
                """
                SELECT date(OrderDate) AS d, COALESCE(SUM(TotalAmount), 0) AS Total
                FROM Orders
                WHERE date(OrderDate) BETWEEN date(?) AND date(?)
                GROUP BY date(OrderDate)
                """,
                (chart_from_str, chart_to_str),
            ).fetchall()
        chart_revenue_by_day = {r["d"]: r["Total"] for r in chart_rows}

        chart_daily_series = []
        for day in _daterange(chart_from_str, chart_to_str):
            key = day.strftime("%Y-%m-%d")
            chart_daily_series.append({
                "date": key,
                "label": day.strftime("%b %d"),
                "revenue": chart_revenue_by_day.get(key, 0.0),
            })

        self.dashboard_view.update_charts(rows, chart_daily_series)
        self.dashboard_view.update_top_products(
            [{"name": tp["name"], "qty": tp["qty"], "revenue": tp["revenue"]} for tp in top_products[:5]]
        )
        self.dashboard_view.update_alerts(low_stock_items)

    # ------------------------------------------------------------------ #
    # PROFIT & LOSS: Daily / Weekly / Monthly bucketing
    # ------------------------------------------------------------------ #
    def _bucket_series(self, daily_series, granularity):
        if granularity == "Daily" or not daily_series:
            return daily_series
        buckets, order = {}, []
        for point in daily_series:
            d = datetime.strptime(point["date"], "%Y-%m-%d").date()
            if granularity == "Weekly":
                key_date = d - timedelta(days=d.weekday())
                label = key_date.strftime("%b %d")
            else:  # Monthly
                key_date = d.replace(day=1)
                label = key_date.strftime("%b %Y")
            key = key_date.isoformat()
            if key not in buckets:
                buckets[key] = {"date": key, "label": label, "revenue": 0.0, "cogs": 0.0,
                                 "gross_profit": 0.0, "orders": 0}
                order.append(key)
            b = buckets[key]
            b["revenue"] += point["revenue"]
            b["cogs"] += point["cogs"]
            b["orders"] += point["orders"]
        result = []
        for key in order:
            b = buckets[key]
            b["gross_profit"] = b["revenue"] - b["cogs"]
            result.append(b)
        return result

    # Weekly/Monthly need enough history to actually show a trend, so they
    # look back a fixed window ending at the filter's "To" date rather than
    # reusing whatever (possibly single-day) range the KPI filter has set.
    _PL_LOOKBACK_DAYS = {"Weekly": 7 * 12, "Monthly": 30 * 12}

    def _pl_lookback_range(self, granularity, to_date=None):
        to_date = to_date or self._last_to or datetime.now().strftime("%Y-%m-%d")
        lookback = self._PL_LOOKBACK_DAYS[granularity]
        from_date = (datetime.strptime(to_date, "%Y-%m-%d") - timedelta(days=lookback - 1)).strftime("%Y-%m-%d")
        return from_date, to_date

    def _compute_daily_series(self, from_date, to_date):
        """Revenue/COGS/order-count per day for an arbitrary range, computed
        independently of the currently-applied KPI date filter. Used to give
        the Weekly/Monthly P&L views their own lookback window."""
        with self.db.get_connection() as conn:
            detail_rows = conn.execute(
                """
                SELECT od.ProductID, od.Quantity, od.Subtotal, date(o.OrderDate) AS OrderDay
                FROM OrderDetails od
                JOIN Orders o ON o.OrderID = od.OrderID
                WHERE date(o.OrderDate) BETWEEN date(?) AND date(?)
                """,
                (from_date, to_date),
            ).fetchall()
            cost_rows = conn.execute(
                """
                SELECT ProductID, SUM(Quantity * UnitCost) * 1.0 / SUM(Quantity) AS AvgCost
                FROM PurchaseOrderDetails
                GROUP BY ProductID
                """
            ).fetchall()
            order_rows = conn.execute(
                """
                SELECT OrderID, date(OrderDate) AS OrderDay
                FROM Orders
                WHERE date(OrderDate) BETWEEN date(?) AND date(?)
                """,
                (from_date, to_date),
            ).fetchall()

        cost_by_product = {row["ProductID"]: row["AvgCost"] or 0.0 for row in cost_rows}
        revenue_by_day, cost_by_day, order_count_by_day = {}, {}, {}
        for d in detail_rows:
            unit_cost = cost_by_product.get(d["ProductID"], 0.0)
            revenue_by_day[d["OrderDay"]] = revenue_by_day.get(d["OrderDay"], 0.0) + (d["Subtotal"] or 0.0)
            cost_by_day[d["OrderDay"]] = cost_by_day.get(d["OrderDay"], 0.0) + unit_cost * d["Quantity"]
        for row in order_rows:
            order_count_by_day[row["OrderDay"]] = order_count_by_day.get(row["OrderDay"], 0) + 1

        daily_series = []
        for day in _daterange(from_date, to_date):
            key = day.strftime("%Y-%m-%d")
            revenue = revenue_by_day.get(key, 0.0)
            cost = cost_by_day.get(key, 0.0)
            daily_series.append({
                "date": key,
                "label": day.strftime("%b %d"),
                "revenue": revenue,
                "cogs": cost,
                "gross_profit": revenue - cost,
                "orders": order_count_by_day.get(key, 0),
            })
        return daily_series

    def _compute_hourly_series(self, day_str):
        """Same idea as _compute_daily_series, but bucketed by hour-of-day
        for one specific date. Used when the selected range is a single
        day, since a 1-point-per-day chart has nothing to show for a
        single-day filter (see paint bug fix in report_charts.py) -- an
        hourly breakdown is the useful thing to show instead."""
        with self.db.get_connection() as conn:
            detail_rows = conn.execute(
                """
                SELECT od.ProductID, od.Quantity, od.Subtotal,
                       CAST(strftime('%H', o.OrderDate) AS INTEGER) AS Hour
                FROM OrderDetails od
                JOIN Orders o ON o.OrderID = od.OrderID
                WHERE date(o.OrderDate) = date(?)
                """,
                (day_str,),
            ).fetchall()
            cost_rows = conn.execute(
                """
                SELECT ProductID, SUM(Quantity * UnitCost) * 1.0 / SUM(Quantity) AS AvgCost
                FROM PurchaseOrderDetails
                GROUP BY ProductID
                """
            ).fetchall()
            order_rows = conn.execute(
                """
                SELECT OrderID, CAST(strftime('%H', OrderDate) AS INTEGER) AS Hour
                FROM Orders
                WHERE date(OrderDate) = date(?)
                """,
                (day_str,),
            ).fetchall()

        cost_by_product = {row["ProductID"]: row["AvgCost"] or 0.0 for row in cost_rows}
        revenue_by_hour, cost_by_hour, orders_by_hour = {}, {}, {}
        for d in detail_rows:
            unit_cost = cost_by_product.get(d["ProductID"], 0.0)
            revenue_by_hour[d["Hour"]] = revenue_by_hour.get(d["Hour"], 0.0) + (d["Subtotal"] or 0.0)
            cost_by_hour[d["Hour"]] = cost_by_hour.get(d["Hour"], 0.0) + unit_cost * d["Quantity"]
        for row in order_rows:
            orders_by_hour[row["Hour"]] = orders_by_hour.get(row["Hour"], 0) + 1

        series = []
        for hour in range(24):
            revenue = revenue_by_hour.get(hour, 0.0)
            cost = cost_by_hour.get(hour, 0.0)
            series.append({
                "date": f"{day_str}T{hour:02d}",
                "label": _hour_label(hour),
                "revenue": revenue,
                "cogs": cost,
                "gross_profit": revenue - cost,
                "orders": orders_by_hour.get(hour, 0),
            })
        return series

    @safe_slot("Reports Error", parent_attr="report_view")
    def change_pl_granularity(self, granularity):
        self._pl_granularity = granularity
        if granularity == "Daily":
            if self._pl_daily:
                self.report_view.update_pl_chart(self._pl_daily, granularity)
            return
        from_date, to_date = self._pl_lookback_range(granularity)
        series = self._compute_daily_series(from_date, to_date)
        self.report_view.update_pl_chart(self._bucket_series(series, granularity), granularity)

    # ------------------------------------------------------------------ #
    @safe_slot("Dashboard Error", parent_attr="dashboard_view")
    def load_dashboard_range(self, preset):
        today = QDate.currentDate()
        if preset == "Today":
            start = today
        elif preset == "This Week":
            start = today.addDays(1 - today.dayOfWeek())
        else:
            start = QDate(today.year(), today.month(), 1)
        from_date = start.toString("yyyy-MM-dd")
        to_date = today.toString("yyyy-MM-dd")
        self.report_view.from_date.setDate(start)
        self.report_view.to_date.setDate(today)
        self.load_reports(from_date, to_date)

    # ------------------------------------------------------------------ #
    # EXPORT
    # ------------------------------------------------------------------ #
    _EXPORT_HEADERS = ["Order", "Date", "Customer", "Type", "Items", "Payment", "Total", "Profit", "Status"]

    @staticmethod
    def _safe_cell(value):
        """Stops a customer name like '=HYPERLINK(...)' from running as a
        formula when the export is opened in Excel/Sheets."""
        text = "" if value is None else str(value)
        return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text

    def _export_dicts(self):
        return [
            {
                "Order": row["order"],
                "Date": row["date"],
                "Customer": self._safe_cell(row["customer"]),
                "Type": self._safe_cell(row["type"]),
                "Items": row["items_count"],
                "Payment": self._safe_cell(row["payment"]),
                "Total": f"{row['total']:.2f}",
                "Profit": f"{row['profit']:.2f}",
                "Status": row["status"],
            }
            for row in self.current_rows
        ]

    def export_report(self, fmt, path):
        if not self.current_rows:
            QMessageBox.information(self.report_view, "Nothing to Export",
                                    "There are no rows in the current report.")
            return
        if fmt not in ("csv", "excel", "pdf"):
            QMessageBox.warning(self.report_view, "Export Failed",
                                f"'{fmt}' is not a supported export format.")
            return
        if not path or not str(path).strip():
            return   # the save dialog was cancelled
        ext = {"csv": ".csv", "excel": ".xlsx", "pdf": ".pdf"}[fmt]
        if not str(path).lower().endswith(ext):
            path = f"{path}{ext}"
        try:
            if fmt == "csv":
                self._export_csv(path)
            elif fmt == "excel":
                self._export_excel(path)
            else:
                self._export_pdf(path)
        except Exception as exc:  # noqa: BLE001 -- logged, shown in plain words
            report(exc, self.report_view, "Export Failed", context=f"export_report {fmt}")

    def _export_csv(self, path):
        with open(path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=self._EXPORT_HEADERS)
            writer.writeheader()
            writer.writerows(self._export_dicts())

    def _export_excel(self, path):
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font
        except ImportError:
            QMessageBox.warning(
                self.report_view, "Excel Export Unavailable",
                "Excel export needs the 'openpyxl' package.\nInstall it with: pip install openpyxl",
            )
            return
        wb = Workbook()
        ws = wb.active
        ws.title = "Sales Report"
        ws.append(self._EXPORT_HEADERS)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for row in self._export_dicts():
            ws.append([row[h] for h in self._EXPORT_HEADERS])
        for column_cells in ws.columns:
            width = max(len(str(c.value)) for c in column_cells if c.value is not None) + 2
            ws.column_dimensions[column_cells[0].column_letter].width = min(max(width, 10), 32)
        wb.save(path)

    def _export_pdf(self, path):
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import landscape, letter
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet
        except ImportError:
            QMessageBox.warning(
                self.report_view, "PDF Export Unavailable",
                "PDF export needs the 'reportlab' package.\nInstall it with: pip install reportlab",
            )
            return
        doc = SimpleDocTemplate(path, pagesize=landscape(letter))
        styles = getSampleStyleSheet()
        data = [self._EXPORT_HEADERS] + [[row[h] for h in self._EXPORT_HEADERS] for row in self._export_dicts()]
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#C7A53B")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E7E0D2")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAF7F0")]),
        ]))
        doc.build([Paragraph("AE Trends — Sales Report", styles["Title"]), Spacer(1, 12), table])