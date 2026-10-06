/* Floating side banners (left + right).
   Left : Amazon affiliate products + HoskoteConstruction promo
   Right: Amazon affiliate products + SalaryBit tool cross-sell
   Mobile (<=768px): one bottom bar that alternates between Amazon and cross-sell.
   Edit the three lists below to change anything. */
(function () {
  var AMAZON = [
    { title: "Fertility Temples of Tamil Nadu: Legends, Rituals & a Pilgrim's Guide", url: "https://link.amazon/B0gXCEtHq", img: "/images/book-fertility-temples.jpg" },
    { title: "BLUE TYGA Sunscreen Jacket 2.0 (UPF 50+)", url: "https://link.amazon/B0hvg7fFP", img: "/images/product-blue-tyga-jacket.jpg" },
    { title: "Samsung 7 kg 5 Star Fully-Automatic Top Load Washing Machine", url: "https://link.amazon/B0aRwUZZz", img: "/images/product-samsung-washer.jpg" }
  ];
  var SALARYBIT = [
    { icon: "📜", title: "Simple Will Maker", desc: "Write your will free", url: "/simple-will.html" },
    { icon: "🧾", title: "ITR Filing Assistant", desc: "File your return with confidence", url: "/itr-assistant.html" },
    { icon: "🛡️", title: "Tax Notice Shield", desc: "Got an IT notice? Check your risk", url: "/notice-shield.html" },
    { icon: "🏥", title: "Insurance Mitra", desc: "Claim rejected? Get help", url: "/insurance-mitra.html" }
  ];
  var HOSKOTE = {
    icon: "🏗️", title: "HoskoteConstruction", desc: "Build your home in Hoskote from ₹1,800/sqft. Free site visit.",
    url: "https://www.hoskoteconstruction.in/?utm_source=salarybit&utm_medium=side_banner&utm_campaign=ekhata",
    img: "https://res.cloudinary.com/dvjocpz8j/image/upload/w_300,h_200,c_fill,g_auto,q_auto,f_auto/v1781875175/WhatsApp_Image_2026-06-19_at_12.54.59_pubyuv.jpg"
  };
  if (document.getElementById("sb-banner-right")) return;

  var css = document.createElement("style");
  css.textContent =
    ".sb-banner{position:fixed;top:50%;transform:translateY(-50%);z-index:9999;width:196px;max-height:calc(100vh - 24px);overflow-y:auto;" +
    "background:#fff;border:1px solid #e5e7eb;box-shadow:0 4px 18px rgba(0,0,0,.15);padding:8px;" +
    "font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;scrollbar-width:thin}" +
    "#sb-banner-right{right:0;border-right:0;border-radius:12px 0 0 12px}" +
    "#sb-banner-left{left:0;border-left:0;border-radius:0 12px 12px 0}" +
    ".sb-banner .sb-h{font-size:10.5px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:#6b7280;margin:0 0 6px}" +
    ".sb-banner .sb-h2{margin-top:8px;padding-top:8px;border-top:1px solid #e5e7eb}" +
    ".sb-banner a.sb-c{display:flex;align-items:center;gap:8px;margin:0 0 6px;padding:5px;border-radius:8px;background:#fff7e0;" +
    "border:1px solid #f5c542;color:#111827;text-decoration:none;text-align:left}" +
    ".sb-banner a.sb-c:hover{background:#ffeeb3}" +
    ".sb-banner .sb-i{flex:none;width:44px;height:52px;object-fit:contain;border-radius:4px;background:#fff}" +
    ".sb-banner .sb-tx{min-width:0}" +
    ".sb-banner .sb-t{display:-webkit-box;font-size:11px;font-weight:600;line-height:1.25;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}" +
    ".sb-banner .sb-s{display:block;font-size:10.5px;font-weight:700;color:#b45309;margin-top:2px}" +
    ".sb-banner a.sb-x{display:block;margin:0 0 6px;padding:7px 8px;border-radius:8px;background:#eef6ff;" +
    "border:1px solid #bcd9f7;color:#0f2b46;text-decoration:none}" +
    ".sb-banner a.sb-x:hover{background:#dcecfd}" +
    ".sb-banner a.sb-x b{display:block;font-size:12px;line-height:1.25}" +
    ".sb-banner a.sb-x span{display:block;font-size:10.5px;color:#4b5d6e;margin-top:2px;line-height:1.3}" +
    ".sb-banner a.sb-hk{display:block;margin:0 0 6px;border-radius:8px;background:#fff4ec;border:1px solid #f4b48a;" +
    "color:#3a1d0a;text-decoration:none;overflow:hidden}" +
    ".sb-banner a.sb-hk:hover{background:#ffe8d8}" +
    ".sb-banner a.sb-hk img{display:block;width:100%;height:56px;object-fit:cover}" +
    ".sb-banner a.sb-hk div{padding:6px 8px}" +
    ".sb-banner a.sb-hk b{display:block;font-size:12px}" +
    ".sb-banner a.sb-hk span{display:block;font-size:10.5px;line-height:1.3;margin-top:2px}" +
    ".sb-banner a.sb-hk em{display:block;font-style:normal;font-size:10.5px;font-weight:700;color:#c2410c;margin-top:3px}" +
    ".sb-banner .sb-n{font-size:9.5px;color:#9ca3af;margin:2px 0 0;text-align:center}" +
    ".sb-banner a.sb-mob{display:none}" +
    "#sb-banner-left{display:none}" +
    "@media(min-width:1200px){#sb-banner-left{display:block}}" +
    ".sb-close,.sb-dots{display:none}" +
    "@media(max-width:768px){" +
    "#sb-banner-left{display:none!important}" +
    "#sb-banner-right.sb-closed{display:none!important}" +
    "#sb-banner-right{position:fixed;top:auto;right:0;bottom:0;left:0;transform:none;width:100%;max-height:none;overflow:visible;" +
    "box-sizing:border-box;border:0;border-top:1px solid #e5e7eb;border-radius:14px 14px 0 0;" +
    "padding:8px 8px calc(6px + env(safe-area-inset-bottom,0px));box-shadow:0 -3px 14px rgba(0,0,0,.18);-webkit-transform:translateZ(0)}" +
    "#sb-banner-right .sb-h,#sb-banner-right .sb-n{display:none}" +
    "#sb-banner-right .sb-g{display:none;gap:6px;align-items:stretch}" +
    "#sb-banner-right .sb-g-a{display:flex}" +
    "#sb-banner-right.sb-alt .sb-g-a{display:none}" +
    "#sb-banner-right.sb-alt .sb-g-b{display:flex}" +
    "#sb-banner-right .sb-g>a{flex:1 1 0;margin:0;min-width:0}" +
    "#sb-banner-right a.sb-c{display:block;padding:4px;text-align:center}" +
    "#sb-banner-right .sb-i{display:block;width:100%;height:46px;margin:0 auto 3px}" +
    "#sb-banner-right .sb-t{font-size:10.5px;-webkit-line-clamp:2}" +
    "#sb-banner-right .sb-s{display:none}" +
    "#sb-banner-right a.sb-x,#sb-banner-right a.sb-hk{padding:6px;display:flex;flex-direction:column;justify-content:center;text-align:center;min-height:78px}" +
    "#sb-banner-right a.sb-x b,#sb-banner-right a.sb-hk b{font-size:11.5px}" +
    "#sb-banner-right a.sb-x span,#sb-banner-right a.sb-hk span{font-size:10px}" +
    "#sb-banner-right a.sb-hk img,#sb-banner-right a.sb-hk em{display:none}" +
    "#sb-banner-right a.sb-hk div{padding:0}" +
    ".sb-dots{display:flex;justify-content:center;gap:6px;margin-top:5px}" +
    ".sb-dots i{width:16px;height:4px;border-radius:2px;background:#d1d5db;cursor:pointer}" +
    ".sb-dots i.on{background:#f59e0b}" +
    ".sb-close{display:flex;position:absolute;top:-12px;right:10px;width:26px;height:26px;border-radius:50%;background:#fff;" +
    "border:1px solid #d1d5db;box-shadow:0 1px 4px rgba(0,0,0,.2);align-items:center;justify-content:center;font-size:16px;line-height:1;" +
    "color:#374151;cursor:pointer;padding:0}" +
    "}";
  document.head.appendChild(css);

  function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;"); }

  function amazonHtml() {
    var h = '<p class="sb-h">🛒 Recommended on Amazon</p><div class="sb-g sb-g-a">';
    AMAZON.forEach(function (p) {
      h += '<a class="sb-c" href="' + p.url + '" target="_blank" rel="sponsored nofollow noopener">' +
           '<img class="sb-i" src="' + p.img + '" alt="' + esc(p.title) + '" loading="lazy">' +
           '<span class="sb-tx"><span class="sb-t">' + esc(p.title) + '</span><span class="sb-s">View on Amazon →</span></span></a>';
    });
    return h + '</div>';
  }
  function toolHtml(t) {
    return '<a class="sb-x" href="' + t.url + '"><b>' + t.icon + ' ' + esc(t.title) + '</b><span>' + esc(t.desc) + '</span></a>';
  }
  function hoskoteHtml(extraClass) {
    return '<a class="sb-hk ' + (extraClass || "") + '" href="' + HOSKOTE.url + '" target="_blank" rel="noopener">' +
           '<img src="' + HOSKOTE.img + '" alt="House built by HoskoteConstruction" loading="lazy">' +
           '<div><b>' + HOSKOTE.icon + ' ' + esc(HOSKOTE.title) + '</b><span>' + esc(HOSKOTE.desc) + '</span><em>Free site visit →</em></div></a>';
  }
  function build(id, innerB, cls) {
    var box = document.createElement("aside");
    box.id = id; box.className = "sb-banner";
    box.setAttribute("aria-label", "Recommended products and services");
    box.innerHTML = amazonHtml() + innerB + '<p class="sb-n">Amazon links are affiliate links</p>';
    document.body.appendChild(box);
    return box;
  }

  // Right: Amazon + SalaryBit tools (+ Hoskote shown only in the mobile bar)
  var rightB = '<p class="sb-h sb-h2">⚡ Free tools by SalaryBit</p><div class="sb-g sb-g-b">' +
               toolHtml(SALARYBIT[0]) + toolHtml(SALARYBIT[1]) + hoskoteHtml("sb-mob") + '</div>';
  // Left: Amazon + HoskoteConstruction + one more SalaryBit tool
  var leftB = '<p class="sb-h sb-h2">🏠 Building in Hoskote?</p><div class="sb-g sb-g-b">' +
              hoskoteHtml() + toolHtml(SALARYBIT[2]) + '</div>';

  var right = build("sb-banner-right", rightB);
  var closeBtn = document.createElement("button");
  closeBtn.className = "sb-close"; closeBtn.type = "button"; closeBtn.setAttribute("aria-label", "Close"); closeBtn.innerHTML = "&times;";
  var dots = document.createElement("div");
  dots.className = "sb-dots"; dots.innerHTML = '<i class="on"></i><i></i>';
  right.appendChild(dots); right.appendChild(closeBtn);
  build("sb-banner-left", leftB);

  // ---- Mobile bottom bar behaviour ----
  var mq = window.matchMedia("(max-width:768px)");
  var closed = false;
  try { closed = sessionStorage.getItem("sbBannerClosed") === "1"; } catch (e) {}
  function isMobile() { return mq.matches; }
  function fit() {
    // keep page content from being hidden behind the fixed bar
    var pad = (isMobile() && !right.classList.contains("sb-closed")) ? right.offsetHeight + "px" : "";
    document.body.style.paddingBottom = pad;
  }
  function setAlt(on) {
    right.classList.toggle("sb-alt", on);
    var d = dots.children; d[0].className = on ? "" : "on"; d[1].className = on ? "on" : "";
    fit();
  }
  if (closed) right.classList.add("sb-closed");
  closeBtn.addEventListener("click", function () {
    right.classList.add("sb-closed");
    try { sessionStorage.setItem("sbBannerClosed", "1"); } catch (e) {}
    fit();
  });
  dots.children[0].addEventListener("click", function () { setAlt(false); });
  dots.children[1].addEventListener("click", function () { setAlt(true); });

  var timer = setInterval(function () {
    if (!isMobile() || right.classList.contains("sb-closed")) { right.classList.remove("sb-alt"); return; }
    setAlt(!right.classList.contains("sb-alt"));
  }, 6000);

  window.addEventListener("resize", fit);
  window.addEventListener("orientationchange", function () { setTimeout(fit, 300); });
  window.addEventListener("load", fit);
  fit(); setTimeout(fit, 500); setTimeout(fit, 1500);
})();
