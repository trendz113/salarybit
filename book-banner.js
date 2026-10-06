/* Floating side banners (left + right) with Amazon affiliate products.
   Edit PRODUCTS to change titles/links/images. Mobile: single bottom bar. */
(function () {
  var PRODUCTS = [
    { title: "Fertility Temples of Tamil Nadu: Legends, Rituals & a Pilgrim's Guide", url: "https://link.amazon/B0gXCEtHq", img: "/images/book-fertility-temples.jpg" },
    { title: "BLUE TYGA Sunscreen Jacket 2.0 (UPF 50+)", url: "https://link.amazon/B0hvg7fFP", img: "/images/product-blue-tyga-jacket.jpg" },
    { title: "Samsung 7 kg 5 Star Fully-Automatic Top Load Washing Machine", url: "https://link.amazon/B0aRwUZZz", img: "/images/product-samsung-washer.jpg" }
  ];
  if (document.getElementById("sb-banner-right")) return;

  var css = document.createElement("style");
  css.textContent =
    ".sb-banner{position:fixed;top:50%;transform:translateY(-50%);z-index:9999;width:160px;max-height:92vh;overflow-y:auto;" +
    "background:#fff;border:1px solid #e5e7eb;box-shadow:0 4px 18px rgba(0,0,0,.15);padding:10px;" +
    "font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}" +
    "#sb-banner-right{right:0;border-right:0;border-radius:12px 0 0 12px}" +
    "#sb-banner-left{left:0;border-left:0;border-radius:0 12px 12px 0}" +
    ".sb-banner .sb-h{font-size:11px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:#6b7280;margin:0 0 8px}" +
    ".sb-banner a.sb-c{display:block;margin:0 0 8px;padding:8px;border-radius:8px;background:#fff7e0;" +
    "border:1px solid #f5c542;color:#111827;text-decoration:none;text-align:center}" +
    ".sb-banner a.sb-c:hover{background:#ffeeb3}" +
    ".sb-banner .sb-i{display:block;width:100%;height:90px;object-fit:contain;margin:0 0 6px;border-radius:4px;background:#fff}" +
    ".sb-banner .sb-t{display:block;font-size:11.5px;font-weight:600;line-height:1.3;" +
    "display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}" +
    ".sb-banner .sb-s{display:block;font-size:11px;font-weight:700;color:#b45309;margin-top:4px}" +
    ".sb-banner .sb-n{font-size:9.5px;color:#9ca3af;margin:0;text-align:center}" +
    "#sb-banner-left{display:none}" +
    "@media(min-width:1000px){#sb-banner-left{display:block}}" +
    "@media(max-width:768px){#sb-banner-left{display:none!important}" +
    "#sb-banner-right{top:auto;bottom:0;right:0;left:0;transform:none;width:auto;max-height:none;overflow:visible;" +
    "border:0;border-top:1px solid #e5e7eb;border-radius:12px 12px 0 0;padding:6px 8px;display:flex;gap:6px;align-items:stretch}" +
    "#sb-banner-right .sb-h,#sb-banner-right .sb-n{display:none}" +
    "#sb-banner-right a.sb-c{flex:1;margin:0;padding:4px;min-width:0}" +
    "#sb-banner-right .sb-i{height:44px;margin-bottom:2px}" +
    "#sb-banner-right .sb-t{font-size:10px;-webkit-line-clamp:2}" +
    "#sb-banner-right .sb-s{display:none}" +
    "body{padding-bottom:100px}}";
  document.head.appendChild(css);

  function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;"); }
  function build(id, label) {
    var box = document.createElement("aside");
    box.id = id;
    box.className = "sb-banner";
    box.setAttribute("aria-label", label);
    var html = '<p class="sb-h">🛒 Recommended on Amazon</p>';
    PRODUCTS.forEach(function (p) {
      html += '<a class="sb-c" href="' + p.url + '" target="_blank" rel="sponsored nofollow noopener">' +
              '<img class="sb-i" src="' + p.img + '" alt="' + esc(p.title) + '" loading="lazy">' +
              '<span class="sb-t">' + esc(p.title) + '</span>' +
              '<span class="sb-s">View on Amazon →</span></a>';
    });
    html += '<p class="sb-n">Affiliate links</p>';
    box.innerHTML = html;
    document.body.appendChild(box);
  }
  build("sb-banner-right", "Recommended products");
  build("sb-banner-left", "Recommended products");
})();
