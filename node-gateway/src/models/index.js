const mongoose = require('mongoose');

// Shared connect helper — used by the seed script now, and by index.js
// whenever write logic is wired in (Task 5.3 / 6.2). Not called anywhere
// in the request flow yet, per this task's boundary.
async function connect(uri = process.env.MONGODB_URI) {
  if (!uri) {
    throw new Error('MONGODB_URI is not set.');
  }
  if (mongoose.connection.readyState === 1) return mongoose.connection;
  await mongoose.connect(uri);
  return mongoose.connection;
}

module.exports = {
  connect,
  Request: require('./Request'),
  Employee: require('./Employee'),
  PolicyConfig: require('./PolicyConfig'),
  CompanyKnowledge: require('./CompanyKnowledge'),
};
