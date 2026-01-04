# Create the final, consolidated README.md file

final_content = """# Customer Support Agent – Automated Document Processing

## Overview
This project describes an automated **Customer Support Agent** that receives customer documents, classifies them, extracts structured data, and responds to support tickets using a company knowledge base with a human-in-the-loop fallback.

The system is designed to reduce manual effort in support and operations while maintaining high accuracy, traceability, and escalation paths when automation is insufficient.

---

## Supported Inputs

### Document Categories
The system processes three types of documents:

1. **Invoices**  
   Billing-related documents containing transactional and payment information.

2. **Support Tickets**  
   Customer questions, issues, or complaints that require a response.

3. **Feature Requests**  
   Customer suggestions or requests for product improvements.

### File Formats
- Text files (`.txt`)
- PDF documents (`.pdf`)
- Image files (`.png`, `.jpg`, `.jpeg`)

---

## Processing Flow

### 1. Document Classification
For every incoming document, the system:
- Determines the **document category**:
  - Invoice
  - Support Ticket
  - Feature Request
- Identifies the **file format** (text, image, PDF)
- Assigns a **confidence score** to the classification

**Example output:**
```json
{
  "document_type": "invoice",
  "file_format": "pdf",
  "confidence_score": 0.94
}
