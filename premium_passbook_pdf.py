"""
premium_passbook_pdf.py
────────────────────────
Generates the PAID, properly-paginated A4 PDF for The Family Passbook.

Input:  a JSON-serialisable dict produced by the `serializePassbook()`
        JS function added to family-passbook.html — see that file for
        the exact shape. Roughly:

        {
          "sections": [
            {
              "id": "p0", "kicker": "...", "title": "...",
              "items": [
                {"type": "intro", "text": "..."},
                {"type": "fields", "title": "...", "fields": [{"label":..,"value":..}, ...]},
                {"type": "fieldrow", "label": "...", "value": "..."},
                {"type": "group", "title": "...", "rows": [[{"label":..,"value":..}, ...], ...]},
                {"type": "checklist", "tag": "DAY 1-2", "items": [{"label":..,"checked":bool}, ...]},
                {"type": "note", "text": "..."}
              ]
            }, ...
          ]
        }

Output: raw PDF bytes (call generate_premium_passbook_pdf(data, meta)).

Why WeasyPrint: it respects real CSS Paged Media (@page, running headers/
footers, page-break-before), which is exactly what gets this right where
browser window.print() falls apart — every section renders as its own
A4 page with a fixed header/footer instead of overflowing unpredictably.
"""

import html
from datetime import datetime

from jinja2 import Template
from weasyprint import HTML

BRAND = {
    "ink": "#1B2A3D",
    "paper": "#F3ECD9",
    "paper_line": "#DED2AE",
    "brass": "#A9812F",
    "brass_dark": "#7A5C1F",
    "stamp": "#8B3A2B",
    "sage": "#5C6B62",
    "white_ish": "#FBF8F0",
}

FONT_IMPORT = (
    "https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,500;"
    "0,9..144,700;0,9..144,900;1,9..144,600&family=Source+Serif+4:opsz,wght@8..60,400;"
    "8..60,500;8..60,600&family=Courier+Prime:wght@400;700&display=swap"
)

CSS_TEMPLATE = """
@import url('{{ font_import }}');

@page {
  size: A4;
  margin: 22mm 16mm 20mm;
  @top-center {
    content: element(running-header);
  }
  @bottom-center {
    content: element(running-footer);
  }
}
@page cover {
  margin: 0;
  @top-center { content: none; }
  @bottom-center { content: none; }
}

* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: 'Source Serif 4', serif;
  color: {{ ink }};
  font-size: 12.5px;
  line-height: 1.5;
}
.display { font-family: 'Fraunces', serif; }
.mono { font-family: 'Courier Prime', monospace; }

#running-header {
  position: running(running-header);
  font-family: 'Courier Prime', monospace;
  font-size: 8.5px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: {{ brass_dark }};
  width: 100%;
  text-align: center;
  border-bottom: 1px solid {{ paper_line }};
  padding-bottom: 4mm;
}
#running-footer {
  position: running(running-footer);
  font-family: 'Courier Prime', monospace;
  font-size: 8.5px;
  color: {{ sage }};
  width: 100%;
  text-align: center;
}
#running-footer .pageno::after { content: counter(page) " / " counter(pages); }

/* ───────── COVER PAGE ───────── */
.cover-page {
  page: cover;
  page-break-after: always;
  height: 297mm;
  width: 210mm;
  background: {{ ink }};
  background-image:
    radial-gradient(circle at 20% 15%, rgba(233,201,122,0.08), transparent 40%),
    radial-gradient(circle at 80% 85%, rgba(233,201,122,0.06), transparent 45%);
  color: {{ paper }};
  position: relative;
  padding: 26mm 20mm;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.cover-eyebrow {
  font-family: 'Courier Prime', monospace;
  font-size: 11px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: #B9A46B;
}
.cover-title {
  font-family: 'Fraunces', serif;
  font-weight: 900;
  font-size: 54px;
  line-height: 1.05;
  margin: 10mm 0 4mm;
}
.cover-subtitle {
  font-family: 'Fraunces', serif;
  font-style: italic;
  font-weight: 500;
  font-size: 17px;
  color: #E8C97A;
  max-width: 130mm;
}
.premium-seal {
  position: absolute;
  top: 26mm;
  right: 20mm;
  width: 30mm;
  height: 30mm;
  border-radius: 50%;
  border: 1.6px solid #E8C97A;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  transform: rotate(8deg);
}
.premium-seal .seal-inner {
  border: 1px solid #E8C97A;
  border-radius: 50%;
  width: 25mm;
  height: 25mm;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: 'Courier Prime', monospace;
  font-size: 8px;
  letter-spacing: 0.08em;
  color: #E8C97A;
  line-height: 1.5;
  padding: 2mm;
}
.cover-owner-block {
  font-family: 'Courier Prime', monospace;
  font-size: 12px;
  color: {{ paper }};
  border-top: 1px solid rgba(243,236,217,0.25);
  border-bottom: 1px solid rgba(243,236,217,0.25);
  padding: 6mm 0;
}
.cover-owner-block .row { display: flex; justify-content: space-between; padding: 1.4mm 0; }
.cover-owner-block .k { color: #B9A46B; letter-spacing: 0.06em; }
.cover-owner-block .v { font-weight: 700; }
.cover-footer {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  font-family: 'Courier Prime', monospace;
  font-size: 10px;
  color: #8C9AA6;
}
.cover-footer .brand { color: #E8C97A; font-size: 12px; letter-spacing: 0.1em; }

/* ───────── CONTENT PAGES ───────── */
.sec {
  page-break-before: always;
}
.sec-kicker {
  font-family: 'Courier Prime', monospace;
  font-size: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: {{ stamp }};
  margin-bottom: 2mm;
}
.sec-title {
  font-family: 'Fraunces', serif;
  font-weight: 900;
  font-size: 24px;
  margin: 0 0 3mm;
  border-bottom: 2px solid {{ brass }};
  padding-bottom: 3mm;
}
.sec-intro {
  color: {{ sage }};
  font-size: 11.5px;
  line-height: 1.55;
  margin-bottom: 5mm;
}
.sec-note {
  font-size: 10px;
  color: {{ sage }};
  font-style: italic;
  border-left: 2px solid {{ brass }};
  padding-left: 3mm;
  margin: 4mm 0;
}

.fblock {
  border: 1px solid {{ paper_line }};
  background: rgba(233,222,190,0.28);
  border-radius: 2px;
  padding: 4mm 5mm;
  margin-bottom: 5mm;
  page-break-inside: avoid;
}
.fblock-title {
  font-family: 'Fraunces', serif;
  font-weight: 700;
  font-size: 12.5px;
  color: {{ brass_dark }};
  margin-bottom: 2mm;
}
.frow {
  display: flex;
  align-items: baseline;
  padding: 1.6mm 0;
  border-bottom: 1px dotted {{ paper_line }};
  font-size: 11px;
}
.frow:last-child { border-bottom: none; }
.frow .lbl {
  font-family: 'Courier Prime', monospace;
  font-size: 9.5px;
  color: {{ ink }};
  opacity: 0.75;
  width: 52mm;
  flex: none;
  padding-right: 3mm;
}
.frow .val {
  flex: 1;
  font-weight: 600;
  word-break: break-word;
}
.frow .val.blank { color: #B9AF95; font-weight: 400; font-style: italic; }

.standalone-row { margin-bottom: 3mm; }

.grow-card {
  border: 1px solid {{ paper_line }};
  border-left: 2.5px solid {{ brass }};
  background: {{ white_ish }};
  border-radius: 2px;
  padding: 3mm 4mm;
  margin-bottom: 3mm;
  page-break-inside: avoid;
}
.grow-card .grow-index {
  font-family: 'Courier Prime', monospace;
  font-size: 8.5px;
  color: {{ brass_dark }};
  letter-spacing: 0.08em;
  margin-bottom: 1mm;
}

.tag {
  display: inline-block;
  font-family: 'Courier Prime', monospace;
  font-size: 9px;
  letter-spacing: 0.08em;
  color: #fff;
  background: {{ stamp }};
  padding: 1mm 2.5mm;
  border-radius: 2px;
  margin: 3mm 0 2mm;
}
.chk-list { list-style: none; padding: 0; margin: 0 0 4mm; }
.chk-list li {
  display: flex; gap: 2.5mm; align-items: flex-start;
  padding: 1.4mm 0; border-bottom: 1px dotted {{ paper_line }};
  font-size: 10.5px; line-height: 1.5;
}
.chk-box {
  flex: none; width: 3.4mm; height: 3.4mm; margin-top: 0.6mm;
  border: 1px solid {{ brass_dark }};
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 8px; color: {{ stamp }}; font-weight: 700;
}

.empty-section {
  color: #B9AF95;
  font-style: italic;
  font-size: 11px;
}
"""

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body>

<div id="running-header">The Family Passbook &nbsp;·&nbsp; SalaryBit.in &nbsp;·&nbsp; Premium Edition</div>
<div id="running-footer"><span class="mono">Passbook No. {{ passbook_no }} &nbsp;—&nbsp; Page <span class="pageno"></span></span></div>

<section class="cover-page">
  <div>
    <div class="cover-eyebrow">SalaryBit.in &nbsp;·&nbsp; Premium Edition</div>
    <div class="cover-title display">The Family<br>Passbook</div>
    <div class="cover-subtitle">One document your family can open on the worst day of<br>their life, and know exactly what to do.</div>
  </div>
  <div class="premium-seal">
    <div class="seal-inner mono">VERIFIED<br>COPY<br>№ {{ passbook_no }}</div>
  </div>
  <div class="cover-owner-block">
    <div class="row"><span class="k">Belongs to</span><span class="v">{{ owner_name or '—' }}</span></div>
    <div class="row"><span class="k">Prepared on</span><span class="v">{{ prepared_on }}</span></div>
    <div class="row"><span class="k">Emergency contact</span><span class="v">{{ spouse_name or '—' }}</span></div>
  </div>
  <div class="cover-footer">
    <div>Printed for personal, private use.<br>Not for redistribution or resale.</div>
    <div class="brand display">SalaryBit</div>
  </div>
</section>

{% for sec in sections %}
<section class="sec">
  {% if sec.kicker %}<div class="sec-kicker">{{ sec.kicker }}</div>{% endif %}
  <h1 class="sec-title">{{ sec.title }}</h1>

  {% set has_content = sec['items']|length > 0 %}
  {% if not has_content %}
    <p class="empty-section">Not filled in.</p>
  {% endif %}

  {% for item in sec['items'] %}
    {% if item.type == 'intro' %}
      <p class="sec-intro">{{ item.text }}</p>

    {% elif item.type == 'note' %}
      <p class="sec-note">{{ item.text }}</p>

    {% elif item.type == 'checklist' %}
      <span class="tag mono">{{ item.tag }}</span>
      <ul class="chk-list">
        {% for li in item['items'] %}
        <li><span class="chk-box">{{ '✓' if li.checked else '' }}</span><span>{{ li.label }}</span></li>
        {% endfor %}
      </ul>

    {% elif item.type == 'fields' %}
      <div class="fblock">
        {% if item.title %}<div class="fblock-title">{{ item.title }}</div>{% endif %}
        {% for f in item.fields %}
        <div class="frow">
          <span class="lbl">{{ f.label }}</span>
          <span class="val {{ 'blank' if not f.value }}">{{ f.value if f.value else '—' }}</span>
        </div>
        {% endfor %}
      </div>

    {% elif item.type == 'fieldrow' %}
      <div class="fblock standalone-row">
        <div class="frow">
          <span class="lbl">{{ item.label }}</span>
          <span class="val {{ 'blank' if not item.value }}">{{ item.value if item.value else '—' }}</span>
        </div>
      </div>

    {% elif item.type == 'group' %}
      {% if item.title %}<div class="fblock-title">{{ item.title }}</div>{% endif %}
      {% if item.rows|length == 0 %}
        <p class="empty-section">None added.</p>
      {% endif %}
      {% for row in item.rows %}
        <div class="grow-card">
          <div class="grow-index">ENTRY {{ loop.index }}</div>
          {% for f in row %}
          <div class="frow">
            <span class="lbl">{{ f.label }}</span>
            <span class="val {{ 'blank' if not f.value }}">{{ f.value if f.value else '—' }}</span>
          </div>
          {% endfor %}
        </div>
      {% endfor %}
    {% endif %}
  {% endfor %}
</section>
{% endfor %}

</body>
</html>
"""


def _esc(v):
    if v is None:
        return ""
    return html.escape(str(v)).strip()


def _clean_sections(raw_sections):
    """Escape all user-supplied text so nothing breaks the HTML/CSS."""
    cleaned = []
    for sec in raw_sections or []:
        c_items = []
        for item in sec.get("items", []):
            t = item.get("type")
            if t in ("intro", "note"):
                c_items.append({"type": t, "text": _esc(item.get("text"))})
            elif t == "checklist":
                c_items.append({
                    "type": t,
                    "tag": _esc(item.get("tag")),
                    "items": [{"label": _esc(li.get("label")), "checked": bool(li.get("checked"))}
                              for li in item.get("items", [])]
                })
            elif t == "fields":
                c_items.append({
                    "type": t,
                    "title": _esc(item.get("title")),
                    "fields": [{"label": _esc(f.get("label")), "value": _esc(f.get("value"))}
                               for f in item.get("fields", [])]
                })
            elif t == "fieldrow":
                c_items.append({"type": t, "label": _esc(item.get("label")), "value": _esc(item.get("value"))})
            elif t == "group":
                c_items.append({
                    "type": t,
                    "title": _esc(item.get("title")),
                    "rows": [[{"label": _esc(f.get("label")), "value": _esc(f.get("value"))} for f in row]
                              for row in item.get("rows", [])]
                })
        cleaned.append({
            "id": _esc(sec.get("id")),
            "kicker": _esc(sec.get("kicker")),
            "title": _esc(sec.get("title")),
            "items": c_items,
        })
    return cleaned


def _find_cover_fields(sections):
    """Pull owner name / spouse name out of the cover section (p0) for
    the premium cover page, without hardcoding a data schema."""
    owner_name, spouse_name = "", ""
    for sec in sections:
        if sec.get("id") != "p0":
            continue
        for item in sec.get("items", []):
            if item.get("type") != "fields":
                continue
            for f in item.get("fields", []):
                label = (f.get("label") or "").lower()
                if "full name" in label and not owner_name:
                    owner_name = f.get("value") or ""
                if "spouse" in label and not spouse_name:
                    spouse_name = f.get("value") or ""
    return owner_name, spouse_name


def generate_premium_passbook_pdf(passbook_data: dict, payment_id: str = "") -> bytes:
    """
    passbook_data: dict with a "sections" list (see module docstring).
    payment_id: Razorpay payment id, used to derive a Passbook No. so
                every paid copy looks individually numbered/verified.
    Returns: PDF file bytes.
    """
    sections = _clean_sections(passbook_data.get("sections", []))
    owner_name, spouse_name = _find_cover_fields(sections)

    passbook_no = (payment_id[-8:] if payment_id else datetime.now().strftime("%y%m%d%H%M")).upper()
    prepared_on = datetime.now().strftime("%d %b %Y")

    css = Template(CSS_TEMPLATE).render(font_import=FONT_IMPORT, **BRAND)
    html_out = Template(HTML_TEMPLATE).render(
        sections=sections,
        owner_name=_esc(owner_name),
        spouse_name=_esc(spouse_name),
        passbook_no=passbook_no,
        prepared_on=prepared_on,
    )
    full_html = f"<style>{css}</style>{html_out}"
    pdf_bytes = HTML(string=full_html, base_url="https://salarybit.in/").write_pdf()
    return pdf_bytes


if __name__ == "__main__":
    # Local smoke test with representative sample data.
    sample = {
        "sections": [
            {
                "id": "p0", "kicker": "Passbook No. — fill after printing", "title": "The Family Passbook",
                "items": [
                    {"type": "intro", "text": "One document your spouse or family can open on the worst day of their life."},
                    {"type": "fields", "title": "This passbook belongs to", "fields": [
                        {"label": "Full name", "value": "Deepak R."},
                        {"label": "Date of birth", "value": "1988-04-12"},
                        {"label": "Phone number", "value": "+91 98xxxxxx21"},
                        {"label": "Home address", "value": "Hoskote, Bangalore"},
                    ]},
                    {"type": "fields", "title": "If you are reading this in an emergency — start here", "fields": [
                        {"label": "Spouse / next of kin name", "value": "Anita R."},
                        {"label": "Their phone number", "value": "+91 98xxxxxx45"},
                        {"label": "Family doctor / hospital", "value": ""},
                    ]},
                    {"type": "note", "text": "Tip: print two copies of this cover page alone and keep one with your spouse."},
                ]
            },
            {
                "id": "p1", "kicker": "Section 01", "title": "The First 7 Days",
                "items": [
                    {"type": "intro", "text": "Nobody thinks clearly under grief."},
                    {"type": "checklist", "tag": "DAY 1-2", "items": [
                        {"label": "Get the medical certificate of cause of death.", "checked": True},
                        {"label": "Register the death and get 8-10 original certificates.", "checked": False},
                    ]},
                ]
            },
            {
                "id": "p3", "kicker": "Section 03", "title": "Bank & Money",
                "items": [
                    {"type": "group", "title": "Bank accounts", "rows": [
                        [{"label": "Bank + branch", "value": "HDFC, Hoskote"},
                         {"label": "Account type", "value": "Savings"},
                         {"label": "Nominee registered?", "value": "Y"}],
                    ]},
                ]
            },
        ]
    }
    pdf = generate_premium_passbook_pdf(sample, payment_id="pay_TESTABCD1234")
    with open("/home/claude/passbook/sample_premium_passbook.pdf", "wb") as f:
        f.write(pdf)
    print("wrote sample PDF, bytes:", len(pdf))
