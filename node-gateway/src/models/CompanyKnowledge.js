const mongoose = require('mongoose');

// Metadata/source-of-truth for docs embedded into the FAISS index (Task 3.3,
// Python side). This Mongo collection does NOT store vectors — it's what the
// Python service re-embeds from if the FAISS index needs to be rebuilt.
const companyKnowledgeSchema = new mongoose.Schema(
  {
    doc_id: { type: String, required: true, unique: true, index: true },
    title: { type: String, required: true },
    classification: {
      type: String,
      required: true,
      enum: ['CONFIDENTIAL', 'INTERNAL', 'PUBLIC'],
    },
    content: { type: String, required: true },
    embedded_at: { type: Date, default: null },
  },
  { collection: 'company_knowledge', versionKey: false },
);

module.exports = mongoose.model('CompanyKnowledge', companyKnowledgeSchema);
