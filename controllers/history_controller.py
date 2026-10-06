"""CONTROLLER: Transaction History."""
from PyQt6.QtWidgets import QMessageBox
from utils.errors import report, safe_slot
from utils.validators import ValidationError, clean_date_range
from views.transaction_history_view import OrderDetailDialog, PurchaseDetailDialog


class HistoryController:
    def __init__(self, model, view, generated_by=None):
        self.model = model
        self.view = view
        self.generated_by = generated_by
        
        self.view.populate_filter_options(self.model.get_filter_options())

        self.view.filters_changed.connect(self.load)
        self.view.view_requested.connect(self.open_detail)
        self.view.page_changed.connect(self.change_page)
        self.view.export_pdf_requested.connect(self.export_pdf)

        self.current_rows = []
        self.current_tab = "All Transactions"
        self.current_page = 1
        
        self.load()

    def refresh_filters(self):
        """Re-read platforms / payment methods / staff so anything newly added
        (a new platform or bank) shows up in the filters straight away."""
        self.view.refresh_filter_options(self.model.get_filter_options())

    @safe_slot("Transaction History Error")
    def load(self):
        self.current_page = 1
        tab = self.view.get_active_tab()
        f = self.view.get_filters()
        # A start date after the end date would silently show nothing.
        try:
            clean_date_range(f.get("date_from"), f.get("date_to"))
        except ValidationError as exc:
            QMessageBox.warning(self.view, "Check the Dates", str(exc))
            return

        orders = self.model.get_customer_orders(
            search=f["search"], date_from=f["date_from"], date_to=f["date_to"],
            status=f["status"], platform=f["platform"],
            payment_method=f["payment_method"], staff=f["staff"])

        # Purchase Orders don't have a Platform or Payment Method of their own -
        # they're supplier restocks, not customer sales. So once either filter
        # is narrowed to something specific, no PO can ever legitimately match
        # it; leave the purchases list empty instead of showing every PO
        # regardless of what Platform/Payment Method is selected (this was the
        # bug: Facebook Live and TikTok Live both showed the same PO rows,
        # since nothing was actually filtering them).
        platform_is_narrowed = f["platform"] and f["platform"] != "All Platforms"
        payment_is_narrowed = f["payment_method"] and f["payment_method"] != "All Payment Methods"
        if platform_is_narrowed or payment_is_narrowed:
            purchases = []
        else:
            purchases = self.model.get_inventory_purchases(
                search=f["search"], date_from=f["date_from"], date_to=f["date_to"],
                status=f["status"], staff=f["staff"])

        if tab == "Customer Orders":
            rows = orders
        elif tab == "Inventory Purchases":
            rows = purchases
        else:
            rows = sorted(orders + purchases, key=lambda r: r["id"], reverse=True)

        self.current_rows = rows
        self.current_tab = tab

        start = (self.current_page - 1) * self.view.page_size
        end = start + self.view.page_size
        self.view.display_transactions(rows[start:end], tab)
        self.view.set_pagination(len(rows), self.current_page)
        self.view.update_summary(self.model.get_summary(f["date_from"], f["date_to"]))

    def export_pdf(self, path):
        """Exports EVERY row matching the current filters/tab (not just the
        page on screen), categorised by type and status."""
        if not self.current_rows:
            QMessageBox.information(
                self.view, "Nothing to Export",
                "There are no transactions matching the current filters.")
            return
        if not path or not str(path).strip():
            return
        if not str(path).lower().endswith(".pdf"):
            path = f"{path}.pdf"
        try:
            from controllers.history_pdf import build_history_pdf
            build_history_pdf(
                path, self.current_rows, self.view.get_filters(),
                tab=self.current_tab, generated_by=self.generated_by)
        except ImportError:
            QMessageBox.warning(
                self.view, "PDF Export Unavailable",
                "PDF export needs the 'reportlab' package.\n"
                "Install it with: pip install reportlab")
            return
        except PermissionError:
            QMessageBox.warning(
                self.view, "Export Failed",
                "Couldn't write the file. If it is open in another program, "
                "close it and try again.")
            return
        except Exception as exc:  # noqa: BLE001 - log it, show a friendly reason
            report(exc, self.view, "Export Failed", context="export_pdf")
            return
        QMessageBox.information(
            self.view, "Export Complete", f"Transaction history saved to:\n{path}")

    @safe_slot("Transaction History Error")
    def change_page(self, direction):
        if not self.current_rows:
            return

        total_pages = max(
            1,
            (len(self.current_rows) + self.view.page_size - 1) // self.view.page_size
        )
        new_page = self.current_page + int(direction)
        if new_page < 1 or new_page > total_pages:
            return

        self.current_page = new_page
        start = (self.current_page - 1) * self.view.page_size
        end = start + self.view.page_size
        self.view.display_transactions(
            self.current_rows[start:end],
            self.current_tab
        )
        self.view.set_pagination(len(self.current_rows), self.current_page)

    @safe_slot("Transaction History Error")
    def open_detail(self, kind, row_id):
        if kind == "order":
            detail = self.model.get_order_detail(row_id)
            if detail:
                # Pass self.process_refund as the callback for the button
                OrderDetailDialog(self.view, detail, on_refund=self.process_refund).exec()
        else:
            detail = self.model.get_purchase_detail(row_id)
            if detail:
                PurchaseDetailDialog(self.view, detail).exec()
                
    def process_refund(self, order_id):
        """Triggers the refund in the DB and refreshes the table."""
        try:
            self.model.process_refund(order_id)
        except Exception as exc:  # noqa: BLE001
            report(exc, self.view, "Refund Failed", context=f"refund {order_id}")
            self.load()      # show the real status
            return
        self.load()