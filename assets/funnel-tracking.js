/* SalaryBit funnel tracking (GA4). Loads BEFORE Razorpay checkout.js and wraps it.
   Events: checkout_started, payment_completed_client, payment_failed, checkout_abandoned.
   NOTE: payment_completed_client fires when Razorpay's browser callback returns; it is NOT
   server-verified revenue. Treat verified revenue from the Razorpay dashboard / server logs. */
(function(){
  function ev(n,p){try{if(typeof gtag==='function')gtag('event',n,p||{});}catch(e){}}
  var page=location.pathname.replace(/\/$/,'').split('/').pop()||'home';
  var real;
  function wrap(R){
    if(!R||R.__sbWrapped)return R;
    function W(opts){
      opts=opts||{};
      var amt=opts.amount?opts.amount/100:undefined, h=opts.handler, d=opts.modal&&opts.modal.ondismiss;
      var base={tool:page,value:amt,currency:'INR'};
      opts.handler=function(r){ev('payment_completed_client',base);return h&&h.apply(this,arguments);};
      opts.modal=opts.modal||{};
      opts.modal.ondismiss=function(){ev('checkout_abandoned',base);return d&&d.apply(this,arguments);};
      var inst=new R(opts);
      var open=inst.open&&inst.open.bind(inst);
      if(open)inst.open=function(){ev('checkout_started',base);return open();};
      if(inst.on)inst.on('payment.failed',function(){ev('payment_failed',base);});
      return inst;
    }
    W.prototype=R.prototype;W.__sbWrapped=true;return W;
  }
  try{Object.defineProperty(window,'Razorpay',{configurable:true,get:function(){return real;},set:function(v){real=wrap(v);}});}catch(e){}
})();
