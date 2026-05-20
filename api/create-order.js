const Razorpay = require('razorpay');

exports.handler = async (event) => {
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  };

  if (event.httpMethod === 'OPTIONS') return { statusCode: 200, headers, body: '' };
  if (event.httpMethod !== 'POST') return { statusCode: 405, headers, body: JSON.stringify({ error: 'Method not allowed' }) };

  const rzp = new Razorpay({
    key_id: process.env.RAZORPAY_KEY_ID,
    key_secret: process.env.RAZORPAY_KEY_SECRET,
  });

  try {
    const order = await rzp.orders.create({
      amount: 4900, // ₹49 in paise — hardcoded, never trust client
      currency: 'INR',
      receipt: 'qr_' + Date.now(),
    });

    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({
        order_id: order.id,
        amount: order.amount,
        currency: order.currency,
      }),
    };
  } catch (err) {
    console.error('create-order error:', err);
    return { statusCode: 500, headers, body: JSON.stringify({ error: err.message }) };
  }
};
