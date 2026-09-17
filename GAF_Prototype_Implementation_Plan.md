# GAF AI Prototype — Implementation Plan

## 1. Objective

Build a demo/MVP of the two AI assistants described in the GAF Prototype Build Brief:

1. **Smart Order Helper**
2. **Product & Warranty Advisor**

The prototype should use the supplied synthetic datasets and demonstrate the complete customer-service journey without requiring production SAP, Salesforce, or delivery-system integrations.

The brief requires human confirmation before an order is submitted and requires the Product & Warranty Advisor to answer only from approved documents, cite its source, withhold unsupported answers, and escalate expert-only questions.

---

# 2. Recommended Technology Stack

## Cloud

**Microsoft Azure**

### Core services

| Requirement | Azure service |
|---|---|
| Agent/orchestration | Microsoft Foundry Agent Service |
| LLM | Azure OpenAI / Foundry model access |
| RAG / document retrieval | Azure AI Search |
| Approved documents | Azure Blob Storage |
| Structured business data | Azure SQL Database |
| Backend/API | Azure Functions or Azure Container Apps |
| Authentication | Microsoft Entra ID |
| Secrets | Azure Key Vault |
| API integration | Azure API Management |
| Async events | Azure Service Bus |
| Monitoring | Application Insights + Azure Monitor |
| Frontend | React + TypeScript |

For the prototype, start with only the services required to make the demo work. Add API Management, Service Bus, Front Door/WAF, private networking, and production integrations later.

---

# 3. Prototype Architecture

```text
                         React UI
                            |
                            v
                    Backend / API
                 Azure Functions/
                 Container Apps
                            |
             +--------------+--------------+
             |                             |
             v                             v
      Order Assistant             Warranty Assistant
             |                             |
             v                             v
      Business Tools                 Azure AI Search
             |                             |
             v                             v
        Azure SQL                  Blob Storage
             |                    Approved GAF Docs
             v
      Synthetic GAF Data
```

## Production direction

```text
                         GAF User
                            |
                    Front Door + WAF
                            |
                    API Management
                            |
                  Foundry Agent Service
                     /                                /                        Order Assistant      Warranty Advisor
                 |                    |
          Business Tools          AI Search
                 |                    |
              Azure SQL          Blob Storage
                 |
          SAP / PeopleSoft
          Salesforce
                 |
            Service Bus
                 |
          Delivery Watcher
```

---

# 4. Important Architecture Principle

Do **not** implement every logical worker as an independent LLM.

The brief describes workers such as:

- Order Reader
- Customer Checker
- Product Matcher
- Stock & Credit Checker
- Duplicate Guard
- Order Builder
- Delivery Watcher

Treat these as logical responsibilities.

Use an orchestrator plus deterministic tools wherever possible.

```text
                    Order Orchestrator
                           |
       +-------------------+-------------------+
       |                   |                   |
       v                   v                   v
 Order extraction     Customer lookup     Product lookup
       |                   |                   |
       +-------------------+-------------------+
                           |
                     Inventory tool
                           |
                      Credit tool
                           |
                    Duplicate tool
                           |
                     Order builder
                           |
                    HUMAN CONFIRM
                           |
                           v
                          ERP
```

The LLM should understand natural language and decide which capability to invoke.

Business-critical calculations and checks should be deterministic.

---

# 5. Phase 1 — Foundation

## Tasks

- Create Git repository.
- Create frontend project.
- Create backend project.
- Configure environment variables.
- Configure existing LLM API credentials.
- Configure existing Azure AI Search credentials.
- Create Azure resource group.
- Create Blob Storage.
- Create Azure SQL.
- Create Key Vault.
- Establish local development configuration.
- Establish basic CI/CD if required.

## Suggested repository

```text
gaf-ai-prototype/
├── frontend/
│   ├── src/
│   ├── components/
│   ├── pages/
│   └── services/
│
├── backend/
│   ├── api/
│   ├── agents/
│   ├── tools/
│   ├── rag/
│   ├── models/
│   ├── services/
│   └── config/
│
├── data/
│   ├── products.json
│   ├── addon_rules.json
│   ├── inventory.json
│   ├── customers.json
│   ├── recent_orders.json
│   ├── product_approvals.json
│   ├── warranty_rules.json
│   └── escalation_rules.json
│
├── documents/
│   └── approved/
│
├── tests/
│
└── infra/
```

---

# 6. Phase 2 — Synthetic Data Layer

Use the data supplied in the GAF brief.

## Assistant 1 datasets

### Data Set A — Product Catalogue

Contains:

- SKU
- Product name
- Colour
- Unit of measure
- Bundles per square
- Product type

Example:

```text
TL-HDZ-CHAR
Timberline HDZ Shingles
Charcoal
Square
3 bundles per square
```

### Data Set B — Add-on Rules

Defines which additional products should be suggested.

For Timberline HDZ:

- Pro-Start
- Seal-A-Ridge
- Tiger Paw
- Cobra

### Data Set C — Inventory

Contains:

- SKU
- Warehouse/DC
- Quantity available
- Restock date

### Data Set D — Customer Accounts

Contains:

- Account ID
- Customer name
- Default ship-to city
- Credit status
- Credit limit used

### Data Set E — Recent Orders

Contains:

- Order ID
- Account
- SKU
- Quantity
- Order date
- Delivery date

---

## Assistant 2 datasets

### Data Set F — Approved Knowledge Documents

Contains:

- Document ID
- Title
- Topic
- Version
- Valid-until date

### Data Set G — Product Approval Registry

Contains:

- Product
- Florida approval number
- Miami-Dade NOA
- Standard wind tier
- WindProven tier

### Data Set H — Warranty Requirement Rules

Contains:

- Warranty tier
- Installation method
- Required accessories
- Wind coverage

### Data Set I — Escalation Rules

Defines questions that:

- Can be answered
- Must be escalated
- Require urgent escalation
- Must be withheld because no approved source exists

---

# 7. Phase 3 — Business Tools

Build deterministic backend tools before building the complete agents.

## Assistant 1 tools

```text
lookup_product()
convert_uom()
get_addons()
lookup_customer()
check_inventory()
check_credit()
detect_duplicate()
build_order()
```

## Example

```text
check_inventory()

INPUT
{
  "sku": "TL-HDZ-CHAR",
  "warehouse": "Tampa DC",
  "quantity_squares": 60
}

OUTPUT
{
  "available": true,
  "quantity_available": 220,
  "restock_date": null
}
```

## Other tools

```text
convert_uom()

60 squares
        |
        v
60 x 3
        |
        v
180 bundles
```

```text
detect_duplicate()

Customer + SKU + quantity + recent date
                |
                v
        Matching order?
          /                  YES           NO
         |             |
      WARNING         PASS
```

The tools should return structured JSON and should not depend on LLM-generated business facts.

---

# 8. Phase 4 — Smart Order Helper

Implement the workflow described in the brief.

```text
Customer order
      |
      v
Order Reader
      |
      v
Customer Checker
      |
      v
Product Matcher
      |
      v
Stock & Credit Checker
      |
      v
Duplicate Guard
      |
      v
Order Builder
      |
      v
Human Confirmation
```

## 8.1 Order Reader

Use the LLM to extract:

- Product
- Colour
- Quantity
- Unit
- Delivery location
- Delivery date

Example:

```text
"I need 60 squares of Timberline HDZ in Charcoal
for Sunshine Roofing, deliver next Tuesday."
```

Structured result:

```json
{
  "product": "Timberline HDZ",
  "colour": "Charcoal",
  "quantity": 60,
  "uom": "square",
  "customer": "Sunshine Roofing",
  "delivery_city": "Tampa",
  "delivery_date": "..."
}
```

If required information is missing, ask the user rather than guessing.

---

## 8.2 Customer Checker

Call:

```text
lookup_customer()
```

Verify:

- Customer identity
- Default city
- Credit status
- Unusual delivery address

---

## 8.3 Product Matcher

Call:

```text
lookup_product()
convert_uom()
get_addons()
```

For the sample:

```text
60 squares
      =
180 bundles
```

Resolve the exact SKU:

```text
TL-HDZ-CHAR
```

Suggest:

```text
Pro-Start
Seal-A-Ridge
Tiger Paw
Cobra
```

---

## 8.4 Stock & Credit Checker

Check:

```text
check_inventory()
check_credit()
```

Return clear status:

```text
Stock: PASS
Credit: PASS
Back-order risk: LOW
```

If blocked:

```text
Credit: BLOCKED
```

The order must not proceed to confirmation until blocking issues are resolved.

---

## 8.5 Duplicate Guard

Call:

```text
detect_duplicate()
```

For the supplied example, the prototype should detect the matching recent order and show:

```text
Possible duplicate
Order: ORD-77012
```

---

## 8.6 Order Builder

Generate an `OrderDraft`.

Example:

```json
{
  "customer_id": "ACC-1001",
  "items": [
    {
      "sku": "TL-HDZ-CHAR",
      "quantity": 180,
      "uom": "bundle"
    }
  ],
  "delivery_city": "Tampa",
  "confidence": 92,
  "warnings": [
    "Possible duplicate"
  ],
  "status": "PENDING_HUMAN_CONFIRMATION"
}
```

### Critical rule

```text
AI prepares the order.
AI does NOT submit the order.
Human presses Confirm.
```

---

# 9. Phase 5 — Product & Warranty Advisor

Workflow:

```text
Question
   |
   v
Question Reader
   |
   v
Sorter / Classifier
   |
   +------ Expert-only ------> Escalation Builder
   |
   v
Document Finder
   |
   v
Answer Writer
   |
   v
Answer + Source
```

---

# 10. RAG Implementation

## Document pipeline

```text
Approved GAF PDFs
       |
       v
Azure Blob Storage
       |
       v
Document extraction
       |
       v
Chunking
       |
       v
Embeddings
       |
       v
Azure AI Search
```

## AI Search metadata

Each chunk should contain:

```json
{
  "chunk_id": "...",
  "document_id": "DOC-102",
  "title": "WindProven Warranty Terms",
  "version": "3.0",
  "valid_until": "2027-06-30",
  "product": "Timberline HDZ",
  "region": "Florida",
  "content": "...",
  "embedding": "..."
}
```

Use metadata filtering to avoid expired or non-approved documents.

---

# 11. Grounding Rules

System-level behavior:

```text
Answer ONLY from retrieved approved GAF content.

Do not use general model knowledge for warranty,
installation, product approval, or building-code claims.

Every answer must include its source.

If the retrieved approved content does not support
the answer:

"No approved source available — answer withheld."

Do not guess.
```

This is one of the most important safety requirements of the prototype.

---

# 12. Question Classification

Before generating an answer, classify the question.

## Answer directly

Examples:

```text
General product facts
Warranty tiers
Required accessories
```

## Escalate

Examples:

```text
Exact nailing pattern for a specific building
Design wind speed
HVHZ-specific technical questions
```

## Urgent escalation

Examples:

```text
Leak
Safety issue
Possible product defect
```

## Withhold

```text
No approved source
```

---

# 13. Phase 6 — UI

## Smart Order Helper

Three-column layout:

```text
+----------------+----------------------+----------------+
| Conversation   | Order Canvas         | Safety Checks  |
|                |                      |                |
| Customer msg   | Timberline HDZ       | ✓ Customer     |
|                | Charcoal             | ✓ Stock        |
| Assistant      | 60 squares           | ✓ Credit       |
| response       | = 180 bundles       | ⚠ Duplicate    |
|                |                      |                |
|                | + Add Pro-Start      | Back-order     |
|                | + Add Ridge Cap      | risk: Low      |
+----------------+----------------------+----------------+
| Confidence: 92%              [Confirm & Send Order] |
+------------------------------------------------------+
```

Show the reasoning for deterministic calculations:

```text
60 squares = 180 bundles
```

Use visual status:

```text
GREEN  = OK
AMBER  = Check
RED    = Blocked
```

The Confirm button must be gated.

---

# 14. Product & Warranty UI

```text
+--------------------------------------+-------------------+
| Product & Warranty Advisor           | Sources           |
|                                      |                   |
| Location: [Tampa]                   | DOC-102           |
|                                      | WindProven Terms  |
| Customer question                   | v3.0              |
|                                      |                   |
| Assistant answer                    | DOC-103           |
|                                      | Florida Guide     |
| Warranty comparison                  | v2.1              |
|                                      |                   |
| Standard       WindProven            |                   |
| Up to 130 mph  No maximum            |                   |
|                                      |                   |
| [Route to Technical Services]        |                   |
+--------------------------------------+-------------------+
```

Include:

- Location selector
- Chat
- Source panel
- Document version
- Warranty comparison
- Route-to-expert banner
- No-source state

---

# 15. Phase 7 — Connect Both Assistants

After both assistants work independently, create shared session context.

```json
{
  "session_id": "...",
  "customer_id": "ACC-1001",
  "product": "TL-HDZ-CHAR",
  "location": "Tampa",
  "order_id": "...",
  "conversation_context": {}
}
```

Demo flow:

```text
Customer:
"I need 60 squares..."

        |
        v

Smart Order Helper

        |
        v

Order prepared

        |
        v

Customer:
"Will this qualify for the best wind warranty?"

        |
        v

Product & Warranty Advisor

        |
        v

Grounded answer + source
```

The two assistants should feel like one continuous customer experience.

---

# 16. Phase 8 — Mock Enterprise Integrations

Do NOT start by connecting to real SAP/Salesforce.

Create interfaces:

```text
CustomerProvider
ProductProvider
InventoryProvider
CreditProvider
OrderProvider
DeliveryProvider
```

Prototype implementation:

```text
CustomerProvider -> synthetic data
ProductProvider  -> synthetic data
InventoryProvider -> synthetic data
OrderProvider -> prototype database
```

Future implementation:

```text
CustomerProvider -> Salesforce
ProductProvider  -> SAP/ERP
InventoryProvider -> SAP/ERP
CreditProvider -> ERP
OrderProvider -> SAP/ERP
DeliveryProvider -> real delivery system
```

This allows the agent layer to remain unchanged.

---

# 17. Phase 9 — Testing

Create 20–30 golden scenarios.

## Assistant 1

| Test | Expected |
|---|---|
| 60 squares HDZ Charcoal | Correct SKU |
| 60 squares | 180 bundles |
| Unknown customer | Ask/flag |
| Credit hold | Block |
| Insufficient inventory | Warning |
| Existing order | Duplicate warning |
| Missing accessory | Suggest accessory |
| Quantity >30 squares | Delivery-method check |
| Human confirmation | Required |
| No automatic submission | Must pass |

## Assistant 2

| Test | Expected |
|---|---|
| General product question | Answer with source |
| Warranty question | Answer with source |
| Expired document | Do not use |
| No relevant document | Withhold |
| Exact nailing question | Escalate |
| HVHZ technical question | Escalate |
| Leak/defect | Urgent escalation |
| Product approval question | Retrieve approved registry |
| Warranty accessory question | Grounded answer |

---

# 18. Demo Acceptance Criteria

The prototype is ready when this complete scenario works:

```text
1. Customer orders 60 squares of Timberline HDZ Charcoal.

2. Assistant identifies the product and customer.

3. Assistant resolves SKU:
   TL-HDZ-CHAR

4. Assistant converts:
   60 squares = 180 bundles

5. Assistant suggests:
   Pro-Start
   Seal-A-Ridge
   Tiger Paw
   Cobra

6. Assistant checks inventory.

7. Assistant checks credit.

8. Assistant identifies possible duplicate:
   ORD-77012

9. Assistant prepares order.

10. Human reviews and clicks Confirm.

11. Customer asks warranty question.

12. Advisor retrieves approved documents.

13. Advisor answers using retrieved content only.

14. Advisor shows document and version.

15. Expert-only question is routed to Technical Services.

16. Unsupported question is withheld.
```

---

# 19. Recommended Development Timeline

## Day 1

- Repository
- React
- FastAPI
- Azure resources
- Existing LLM connection
- Existing AI Search connection
- Synthetic data

## Day 2

- Business tools
- Product lookup
- UoM conversion
- Customer lookup
- Inventory
- Credit
- Duplicate detection

## Day 3–4

- Smart Order Helper
- Orchestration
- Order draft
- Human confirmation

## Day 5

- Approved document ingestion
- AI Search index
- Metadata
- Retrieval

## Day 6

- Product & Warranty Advisor
- Classification
- RAG
- Citations
- Escalation

## Day 7

- UI implementation
- Order canvas
- Safety checks
- Sources panel

## Day 8

- Connect both assistants
- Shared session context
- End-to-end flow

## Day 9

- Testing
- Guardrails
- Error handling

## Day 10

- Azure deployment
- Demo data
- UI polish
- Demo rehearsal

---

# 20. What NOT to Build in This Phase

Avoid these until the prototype is proven:

- Real SAP integration
- Real Salesforce integration
- Real delivery tracking
- Production-grade networking
- Kubernetes
- Complex microservices
- Large multi-agent swarm
- Automated order submission
- Production customer data
- Production warranty decisions

The brief itself states that the sample data is illustrative and that the recommended targets/rules need validation against live GAF information before actual use.

---

# 21. Immediate Azure Checklist

Since LLM and AI Search access already exist, create/configure these next:

### Required now

- [ ] Azure subscription
- [ ] Resource group
- [ ] Foundry project/agent environment
- [ ] Model deployment/access
- [ ] Azure Blob Storage
- [ ] Azure SQL or prototype SQLite
- [ ] Azure Functions or Container Apps
- [ ] Key Vault

### Later

- [ ] Entra ID production configuration
- [ ] API Management
- [ ] Service Bus
- [ ] Application Insights
- [ ] Azure Monitor
- [ ] Front Door/WAF
- [ ] VNet/private endpoints
- [ ] SAP integration
- [ ] Salesforce integration

---

# 22. Final Recommended MVP

```text
                  ┌──────────────────────┐
                  │    React Frontend    │
                  └──────────┬───────────┘
                             |
                             v
                  ┌──────────────────────┐
                  │   FastAPI Backend    │
                  └──────────┬───────────┘
                             |
                 ┌───────────┴───────────┐
                 |                       |
                 v                       v
       ┌─────────────────┐     ┌─────────────────┐
       │ Smart Order     │     │ Product/Warranty│
       │ Helper          │     │ Advisor         │
       └────────┬────────┘     └────────┬────────┘
                |                       |
                v                       v
       ┌─────────────────┐     ┌─────────────────┐
       │ Business Tools  │     │ Azure AI Search │
       └────────┬────────┘     └────────┬────────┘
                |                       |
                v                       v
          ┌───────────┐          ┌──────────────┐
          │ Azure SQL │          │ Blob Storage │
          └───────────┘          └──────────────┘
```

**Build this first.** Once this works end-to-end, add enterprise integrations and production security rather than over-engineering the initial demo.
