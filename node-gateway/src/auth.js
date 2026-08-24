const crypto = require('node:crypto');

const TOKEN_TTL_SECONDS = 8 * 60 * 60;

function base64url(value) {
  return Buffer.from(value).toString('base64url');
}

function sign(payload, secret = process.env.JWT_SECRET) {
  if (!secret) throw new Error('JWT_SECRET is not set.');
  const header = base64url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const body = base64url(JSON.stringify(payload));
  const signature = crypto.createHmac('sha256', secret).update(`${header}.${body}`).digest('base64url');
  return `${header}.${body}.${signature}`;
}

function issueAdminToken(email) {
  const now = Math.floor(Date.now() / 1000);
  return sign({ sub: email, role: 'admin', iat: now, exp: now + TOKEN_TTL_SECONDS });
}

function verify(token, secret = process.env.JWT_SECRET) {
  if (!secret || typeof token !== 'string') return null;
  const [header, body, suppliedSignature, ...extra] = token.split('.');
  if (!header || !body || !suppliedSignature || extra.length) return null;
  const expectedSignature = crypto.createHmac('sha256', secret).update(`${header}.${body}`).digest();
  let actualSignature;
  try {
    actualSignature = Buffer.from(suppliedSignature, 'base64url');
  } catch {
    return null;
  }
  if (actualSignature.length !== expectedSignature.length || !crypto.timingSafeEqual(actualSignature, expectedSignature)) return null;
  try {
    const payload = JSON.parse(Buffer.from(body, 'base64url').toString('utf8'));
    if (!payload.exp || payload.exp < Math.floor(Date.now() / 1000)) return null;
    return payload;
  } catch {
    return null;
  }
}

function requireAdmin(req, res, next) {
  const value = req.get('authorization') || '';
  const token = value.startsWith('Bearer ') ? value.slice(7) : '';
  const payload = verify(token);
  if (!payload || payload.role !== 'admin') {
    return res.status(401).json({ error: 'unauthorized', message: 'A valid admin bearer token is required.' });
  }
  req.auth = payload;
  return next();
}

module.exports = { issueAdminToken, requireAdmin };
