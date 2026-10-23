"""membership-value-more: savings versus the fee for Prime, Uber One, Instacart+, Walmart+ and Grubhub+ (and DashPass),
from order emails and rules/memberships.json. Order emails are made up; no service publishes a sample receipt."""

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from clawback.models import Email, Subscription
from clawback.pipeline.flags import flag_one
from clawback.pipeline.value import (MembershipsFile, RULES_FILE, included_elsewhere, membership_value, memberships,
                                     read_order)

TODAY = date(2026, 10, 22)


def member(name, fee, sid=None):
    return Subscription(id=sid or name.lower().replace(" ", "-"), merchant=name, category="delivery_membership",
                        amount=fee, monthly_cost=fee)


def mail(n, sender, subject, body, eid=None):
    on = TODAY - timedelta(days=n)
    return Email(id=eid or f"{sender}-{n}-{subject[:5]}", received_at=datetime(on.year, on.month, on.day, tzinfo=timezone.utc),
                 sender=sender, subject=subject, body_text=body)


def amazon_order(n, subtotal, order):
    return mail(n, "auto-confirm@amazon.com", f"Your Amazon.com order #{order}",
                f"Order #{order}\nItems Subtotal: ${subtotal:.2f}\nShipping & Handling: $0.00\n"
                f"Order Total: ${subtotal * 1.08:.2f}\nArriving tomorrow")


def test_rules_file_is_dated_sourced_and_https():
    data = MembershipsFile.model_validate(json.loads(Path(RULES_FILE).read_text(encoding="utf-8")))
    assert {m.key for m in data.memberships} == {"dashpass", "uber_one", "instacart_plus", "walmart_plus",
                                                  "grubhub_plus", "amazon_prime"}
    for m in data.memberships:
        assert m.source_urls and all(u.startswith("https://") for u in m.source_urls)
        assert m.checked_on == date(2026, 10, 23) and m.monthly_fee > 0 and m.notes


def test_dashpass_stated_savings_unchanged():
    emails = [mail(5, "no-reply@doordash.com", "Order confirmed: Chipotle",
                   "Thanks for your order! Subtotal $22.40. Delivery fee $0.00. DashPass saved you $2.99 on this order.")]
    v = membership_value(member("DoorDash DashPass", 9.99), [], TODAY, emails)
    assert (v.uses, v.savings, v.net, v.verdict, v.basis) == (1, 2.99, -7.0, "losing_money", "stated")


def test_no_order_emails_means_not_enough_receipts_and_no_flag():
    s = member("DoorDash DashPass", 9.99)
    s.value = membership_value(s, [], TODAY, [])
    assert s.value.verdict == "not_enough_receipts" and "not enough receipts to tell" in s.value.note
    flags = {f.kind for f in flag_one(s, None, TODAY)}
    assert "membership_losing_money" not in flags and "unknown_usage" in flags  # ask instead


def test_prime_orders_over_35_save_nothing_on_shipping():
    emails = [amazon_order(3, 48.20, "112-1234567-1234567"), amazon_order(12, 61.00, "112-7654321-7654321")]
    s = member("Amazon Prime", 14.99)
    s.value = v = membership_value(s, [], TODAY, emails)
    assert (v.uses, v.savings, v.verdict, v.basis) == (2, 0.0, "losing_money", "estimated")
    [flag] = [f for f in flag_one(s, None, TODAY) if f.kind == "membership_losing_money"]
    assert flag.severity == "medium"  # an estimate, and Prime Video etc. aren't counted
    assert "Only shipping is counted" in flag.message and "at most" in flag.message


def test_prime_one_order_is_not_enough_to_tell():
    v = membership_value(member("Amazon Prime", 14.99), [], TODAY, [amazon_order(3, 48.20, "112-1234567-1234567")])
    assert v.verdict == "not_enough_receipts"


def test_prime_order_under_35_has_no_published_fee():
    emails = [amazon_order(3, 12.99, "112-1111111-1111111"), amazon_order(9, 19.99, "112-2222222-2222222")]
    v = membership_value(member("Amazon Prime", 14.99), [], TODAY, emails)
    assert v.verdict == "not_enough_receipts"  # Amazon doesn't publish the non-member charge under $35


def test_one_amazon_order_with_several_emails_counts_once():
    a = amazon_order(3, 48.20, "112-1234567-1234567")
    shipped = mail(2, "shipment-tracking@amazon.com", "Your Amazon.com order #112-1234567-1234567 has shipped",
                   "Order #112-1234567-1234567 has shipped.")
    b = amazon_order(9, 51.00, "112-2222222-2222222")
    v = membership_value(member("Amazon Prime", 14.99), [], TODAY, [a, shipped, b])
    assert v.uses == 2


def test_walmart_store_deliveries_pay_off():
    emails = [mail(n, "help@walmart.com", "Your Walmart order is confirmed",
                   f"Order #2000111222{n}. Delivery from store. Subtotal ${s:.2f}. Delivery fee $0.00.")
              for n, s in ((2, 52.10), (9, 41.75))]
    v = membership_value(member("Walmart+", 12.95), [], TODAY, emails)
    assert v.verdict == "paying_off" and v.savings_low == 15.90 and v.savings == 15.90  # 2 x $7.95, the low end


def test_walmart_shipped_orders_under_35_save_the_fee():
    emails = [mail(n, "help@walmart.com", "Your Walmart order has shipped",
                   f"Order #2000333444{n}. Your order has shipped. Subtotal ${s:.2f}.") for n, s in ((4, 18.0), (6, 22.5))]
    v = membership_value(member("Walmart+", 12.95), [], TODAY, emails)
    assert v.verdict == "paying_off" and v.savings == 13.98  # 2 x $6.99, published


def test_instacart_low_end_covers_the_fee():
    emails = [mail(n, "orders@instacart.com", "Your order receipt",
                   f"Order #IC{n}123456. Subtotal ${s:.2f}. Delivery fee $0.00. Service fee $3.10.")
              for n, s in ((1, 64.0), (8, 40.0), (15, 72.3))]
    v = membership_value(member("Instacart+", 9.99), [], TODAY, emails)
    assert v.verdict == "paying_off" and v.savings == 11.97  # 3 x $3.99, the published floor


def test_instacart_cannot_be_called_losing_without_a_published_top_fee():
    emails = [mail(1, "orders@instacart.com", "Your order receipt", "Order #IC9988776. Subtotal $50.00.")]
    v = membership_value(member("Instacart+", 9.99), [], TODAY, emails)
    assert v.verdict != "losing_money"


def test_uber_one_ride_credits():
    rides = [mail(n, "noreply@uber.com", "Your Tuesday evening trip with Uber",
                  f"Thanks for riding, Jane. Total ${fare:.2f}. Trip id 8f3a{n}c.") for n, fare in ((2, 24.0), (10, 31.0))]
    v = membership_value(member("Uber One", 9.99), [], TODAY, rides)
    assert v.basis == "estimated" and v.savings == 2.75 and v.verdict == "losing_money"  # 5% of $55


def test_uber_eats_order_that_states_its_savings():
    order = mail(2, "noreply@uber.com", "Your Uber Eats order",
                 "Order #UE77812. Subtotal $28.00. Delivery Fee $0.00. You saved $6.49 with Uber One.")
    v = membership_value(member("Uber One", 9.99), [], TODAY, [order])
    assert (v.savings, v.basis, v.verdict) == (6.49, "stated", "losing_money")


def test_grubhub_without_stated_savings_is_not_enough_to_tell():
    orders = [mail(n, "orders@eat.grubhub.com", "Your Grubhub order", f"Order #GH55{n}321. Subtotal $31.00.")
              for n in (3, 11)]
    v = membership_value(member("Grubhub+", 9.99), [], TODAY, orders)
    assert v.verdict == "not_enough_receipts"


def test_grubhub_plus_is_included_with_prime():
    grub, prime = member("Grubhub+", 9.99), member("Amazon Prime", 14.99)
    included_elsewhere([grub, prime])
    [flag] = grub.flags
    assert flag.kind == "included_elsewhere" and flag.monthly_savings == 9.99
    assert "Amazon Prime includes Grubhub+" in flag.message
    assert not prime.flags


def test_membership_mail_is_not_an_order():
    assert read_order(mail(1, "no-reply@doordash.com", "Your DashPass membership renewed", "Order #A12345 $9.99")) is None


@pytest.mark.parametrize("name", ["Amazon Prime", "Uber One", "Instacart+", "Walmart+", "Grubhub+", "DoorDash DashPass"])
def test_every_membership_is_reachable_from_the_merchant_list(name):
    from clawback.pipeline.value import membership_for
    assert membership_for(member(name, 9.99)) is not None
    assert len(memberships()) == 6
