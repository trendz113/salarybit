// api/create-order.js
const Razorpay = require('razorpay');

const rzp = new Razorpay({
  key_id: process.env.RAZORPAY_KEY_ID,
  key_secret: process.env.RAZORPAY_KEY_SECRET,
});

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  try {
    const order = await rzp.orders.create({
      amount: 4900, // ₹49 in paise — hardcoded, never trust client
      currency: 'INR',
      receipt: 'qr_' + Date.now(),
    });

    return res.status(200).json({
      order_id: order.id,
      amount: order.amount,
      currency: order.currency,
    });

  } catch (err) {
    console.error('create-order error:', err);
    return res.status(500).json({ error: err.message });
  }
};
