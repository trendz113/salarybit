const Razorpay = require('razorpay');

exports.handler = async function(event, context) {
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Content-Type': 'application/json'
  };

  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 200, headers, body: '' };
  }

  try {
    const rzp = new Razorpay({
      key_id:     process.env.RAZORPAY_KEY_ID,
      key_secret: process.env.RAZORPAY_KEY_SECRET
    });

    const order = await rzp.orders.create({
      amount:   9900,
      currency: 'INR',
      receipt:  'resume_' + Math.random().toString(36).slice(2)
    });

    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({
        order_id:     order.id,
        amount:       order.amount,
        currency:     order.currency,
        razorpay_key: process.env.RAZORPAY_KEY_ID
      })
    };

  } catch(err) {
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({ error: err.message })
    };
  }
};
