/* Floating side banner: recommended books (Amazon affiliate). Edit BOOKS to change titles/links. */
(function () {
  var BOOKS = [
    { title: "Fertility Temples of Tamil Nadu: Legends, Rituals & a Pilgrim's Guide", url: "https://link.amazon/B0gXCEtHq" },
    { title: "BLUE TYGA Sunscreen Jacket 2.0 (UPF 50+)", url: "https://link.amazon/B0hvg7fFP" },
    { title: "Samsung 7 kg 5 Star Fully-Automatic Top Load Washing Machine", url: "https://link.amazon/B0aRwUZZz" }
  ];
  if (document.getElementById("sb-book-banner")) return;

  var css = document.createElement("style");
  css.textContent =
    "#sb-book-banner{position:fixed;right:0;top:50%;transform:translateY(-50%);z-index:9999;width:170px;" +
    "background:#fff;border:1px solid #e5e7eb;border-right:0;border-radius:12px 0 0 12px;" +
    "box-shadow:0 4px 18px rgba(0,0,0,.15);padding:10px;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}" +
    "#sb-book-banner .sb-h{font-size:11px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:#6b7280;margin:0 0 8px}" +
    "#sb-book-banner a{display:block;margin:0 0 6px;padding:8px 10px;border-radius:8px;background:#fff7e0;" +
    "border:1px solid #f5c542;color:#111827;font-size:12.5px;font-weight:600;line-height:1.3;text-decoration:none}" +
    "#sb-book-banner a:hover{background:#ffeeb3}" +
    "#sb-book-banner .sb-s{display:block;font-size:11px;font-weight:700;color:#b45309;margin-top:2px}" +
    "#sb-book-banner .sb-n{font-size:9.5px;color:#9ca3af;margin:4px 0 0}" +
    "@media(max-width:768px){#sb-book-banner{top:auto;bottom:0;right:0;left:0;transform:none;width:auto;" +
    "border:0;border-top:1px solid #e5e7eb;border-radius:12px 12px 0 0;padding:6px 8px;display:flex;gap:6px;align-items:stretch}" +
    "#sb-book-banner .sb-h,#sb-book-banner .sb-n{display:none}" +
    "#sb-book-banner a{flex:1;margin:0;font-size:11px;padding:6px;text-align:center}" +
    "body{padding-bottom:64px}}";
  document.head.appendChild(css);

  var box = document.createElement("aside");
  box.id = "sb-book-banner";
  box.setAttribute("aria-label", "Recommended books");
  var html = '<p class="sb-h">🛒 Recommended on Amazon</p>';
  BOOKS.forEach(function (b) {
    html += '<a href="' + b.url + '" target="_blank" rel="sponsored nofollow noopener">' +
            b.title + '<span class="sb-s">View on Amazon →</span></a>';
  });
  html += '<p class="sb-n">Affiliate links</p>';
  box.innerHTML = html;
  document.body.appendChild(box);
})();
