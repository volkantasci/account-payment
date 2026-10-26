# Copyright 2026 volkantasci
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from werkzeug import urls

from odoo import Command, fields
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.payment import utils as payment_utils


@tagged("post_install", "-at_install")
class TestPaymentLinkCurrency(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_currency = cls.company_data["currency"]
        cls.foreign_currency = cls.setup_other_currency(
            "EUR", rounding=0.01, rates=[("2026-01-01", 0.5)]
        )
        cls.invoice = cls.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": cls.partner_a.id,
                "currency_id": cls.foreign_currency.id,
                "invoice_date": "2026-01-15",
                "date": "2026-01-15",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Consulting Service",
                            "quantity": 1.0,
                            "price_unit": 1000.0,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )
        cls.invoice.action_post()

    def test_default_currency_keeps_standard_portal_link(self):
        wizard = (
            self.env["payment.link.wizard"]
            .with_context(
                active_id=self.invoice.id,
                active_model="account.move",
            )
            .create({})
        )
        self.assertEqual(wizard.currency_id, self.foreign_currency)
        self.assertAlmostEqual(wizard.amount, 1000.0)
        self.assertIn(f"move_id={self.invoice.id}", wizard.link)
        self.assertIn("#portal_pay", wizard.link)

    def test_onchange_currency_converts_amount_and_uses_payment_pay_route(self):
        wizard = (
            self.env["payment.link.wizard"]
            .with_context(
                active_id=self.invoice.id,
                active_model="account.move",
            )
            .create({"amount": 500.0})
        )
        wizard.currency_id = self.company_currency
        wizard._onchange_currency_id()

        # 1000 EUR at rate 0.5 = 2000 company currency; 500 EUR = 1000 company currency
        self.assertAlmostEqual(wizard.amount_max, 2000.0)
        self.assertAlmostEqual(wizard.amount, 1000.0)
        self.assertIn("/payment/pay?", wizard.link)

        parsed = urls.url_parse(wizard.link)
        params = urls.url_decode(parsed.query)
        self.assertEqual(int(params["currency_id"]), self.company_currency.id)
        self.assertAlmostEqual(float(params["amount"]), 1000.0)
        self.assertTrue(
            payment_utils.check_access_token(
                params["access_token"],
                self.partner_a.id,
                1000.0,
                self.company_currency.id,
            )
        )

    def test_transaction_auto_links_invoice_by_reference(self):
        provider = self.env["payment.provider"].search([], limit=1)
        payment_method = self.env["payment.method"].search([], limit=1)
        tx = self.env["payment.transaction"].create(
            {
                "provider_id": provider.id,
                "payment_method_id": payment_method.id,
                "reference": f"{self.invoice.name}-1",
                "amount": 1000.0,
                "currency_id": self.company_currency.id,
                "partner_id": self.partner_a.id,
                "date": fields.Datetime.now(),
            }
        )
        self.assertEqual(tx.invoice_ids, self.invoice)
