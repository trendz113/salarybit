# SalaryBit revenue audit (homepage + payment code review)

Scope: homepage and server code only. No live checkout or Search Console data was available.

## Done on branch fix/trust-and-homepage-focus
- Privacy/About/footer claims corrected (AI and paid tools do send data to server + AI provider).
- Problem-led hero, hero search, empty visitor stat removed.
- Real prices on Fix Your Finance (Rs199), Notice Shield (Rs149), Insurance Mitra (Rs99) cards.
- AI tools grid collapsed to top 6 with "Show all" toggle.
- 9 off-topic blog posts set to noindex, removed from sitemap and homepage (URLs kept).
- GA4 events on homepage: search, tool_card_click.
- Payment signature checks now use hmac.compare_digest (constant-time).

## Payment review findings (server_railway.py, api/*.js)
- Razorpay signatures are verified server-side on every paid endpoint reviewed. Good.
- NOT done: replay protection. A valid order_id|payment_id|signature can be reused to regenerate a paid report (extra AI cost). Fix needs a persistent store (e.g. Redis/DB) of consumed payment IDs; in-memory is unsafe with gunicorn max-requests restarts.
- NOT audited: refunds, Razorpay webhooks, failed-payment handling, price-vs-display match on every tool.
- Paid endpoints live on a separate Railway host (API_BASE) hardcoded in each page.

## Remaining (needs owner input)
1. Funnel events (checkout_started, payment_success, report_delivered) inside each tool page.
2. Rewrite thin templated blog posts with real content.
3. Search Console data to validate SEO topics.
4. Sitemap uses an ns0: prefix from scripts/site_doctor.py (valid XML, cosmetic).
5. Manual test: one real payment in Razorpay test mode, mobile layout.
