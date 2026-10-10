# Five-minute Nigraan demonstration

Use the resettable fictional Bismillah Distributors company. All evaluation is synthetic; pilot savings, customer traction and revenue have not been established.

Prepare the week **before** the timer starts: sign in as Rashid (Owner), reset data, sign out, and sign in as Sana (Accountant) to load the week. Keep two sessions ready for the accountant and independent approver. Read the current API counts and cash result; the reserve can breach under conservative collection assumptions. Do not retrain or regenerate the production models during the pitch.

| Time | Show | Explain |
| --- | --- | --- |
| 0:00–0:30 | Payment run summary | “An SME accountant prepares vendor payments; its owner needs to stop suspicious payments and know whether collections cover the reserve.” State that this company and data are fictional. |
| 0:30–1:10 | Live rules comparison and flagged invoices | Show what the basic and expert rules flag on these actual lines. Explain that the firewall combines learned duplicate/risk/anomaly models with deterministic policy and relationship checks. Additional flags are review candidates, not proven fraud or accuracy. |
| 1:10–2:15 | One blocked case | Follow the reason → invoice/bank/relationship evidence → verification checklist. Show the registered contact with its provenance limitation, masked bank history and requester. Toggle the English/Roman Urdu call script. Distinguish model evidence from the optional generated explanation. |
| 2:15–2:55 | Outcome and independent approval | Record a verification method, reference, checks and note using an explicitly described **synthetic test outcome**. Explain that clearing a false alarm does not authorize payment: a different person must approve, and combined vendor commitments above the limit require the owner. |
| 2:55–3:35 | Upload sample | Show the document reader's field confidence and the existing confirmation/scoring workflow. Identify PDF/OCR fallback when Gemini is unavailable. Show the resent invoice detected as a duplicate. |
| 3:35–4:15 | Cash outlook and What-if | Select a week, then explicitly date an unconfirmed overdue collection. Distinguish facts, estimates and assumptions; the scenario does not edit the books. The forecast spans 13 weeks; receipts have only a 4-week synthetic backtest. |
| 4:15–5:00 | Dashboard evaluation and impact | Show the held-out 638 payments, expert baseline and invoice-age sensitivity result. State synthetic limitations and the target buyer hypothesis. Explain the next pilot measurements and the relevant SDG links. |

## Match the AICON’26 rubric

| Criterion | Demonstrable evidence | Honest limit |
| --- | --- | --- |
| AI integration depth | Learned duplicate detection, XGBoost behavioural risk with reasons, Isolation Forest, late-payment model; held-out evaluation and age-feature sensitivity | Graph and policy rules are deterministic. Generated summaries do not make payment decisions. |
| Problem-solving quality | One invoice-to-payment flow, evidence, recorded human verification, independent approvals, vendor limits, reserve scenarios | CSV export is a demo instruction, not bank settlement. |
| Demo and presentation | Prepared week, one complete case, upload, cash scenario, reproducible results | Avoid depending on a live LLM response or model retraining during five minutes. |
| Creativity and SDG impact | Accessible SME controls and Roman Urdu verification support; links to SDG 8.3 (SME formalisation) and 16.4 (illicit financial flows) | Social impact is a proposed contribution, not a measured outcome. |
| Industrial impact | Target workflow and buyer, documented pilot plan with minutes saved, false alarms and collection forecast error | No interviews or sales have been verified. Pricing remains a hypothesis. |

The financial-operations domain judge carries 85% of the evaluation, with 15% from other domain judges. Explain control separation and cash assumptions precisely; use one plain-language example to show where learned models add value.

## Before presenting

- Verify deployed frontend/API links and add the actual recording URL to README. Repository checks do not verify a public deployment.
- Run the full flow on the presentation device: owner reset, accountant load, evidence, recorded case outcome, independent approval, upload, cash scenario and dashboard.
- Test Gemini beforehand if configured. Otherwise identify the labelled template/PDF/OCR fallback. Do not describe the regex evaluation as unseen-layout Gemini accuracy.
- Keep a recording of the verified flow for connectivity failures.
- Verify sidebar collapse/expand, mobile navigation, keyboard focus and reduced motion.
- State what the team personally developed during the event using commit history and team records. Confirm dates before claiming all application code was written during AICON’26.

## Buyer and pilot hypotheses

The first target buyer is the owner or finance lead of a Pakistani distributor with recurring weekly vendor payments and credit sales. This is a target segment, **not a named customer**. An initial pricing hypothesis is PKR 5,000–15,000 per company per month, to test against the buyer's existing review cost and willingness to pay; it is not an advertised or validated price.

Before expanding the product, hold 3–5 consented interviews with distributors/accountants. Record current payment volumes, review time, approval roles, bank-change verification, collection delays, deployment requirements and willingness to pay. Obtain permission for any real ledger pilot and anonymise examples. Compare manual review with Nigraan over a defined period: review minutes, missed suspicious cases, false alarms, reserve breaches and receipt forecast error. Do not infer prevented fraud from unreviewed flags.

Defer ERP imports, reconciliation, payment scheduling, WhatsApp notifications and lender channels until a pilot establishes which integration matters. Tamper-evident audit storage is a future requirement; the current audit log is inspectable but not tamper-proof.
