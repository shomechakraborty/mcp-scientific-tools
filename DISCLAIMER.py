"""
LEGAL DISCLAIMER — Scientific Tools MCP Server
================================================
This disclaimer governs all use of the Scientific Tools MCP Server
and its associated tools, APIs, and data outputs.

Include this text in:
  - Your README.md
  - Your terms of service page (yourdomain.com/terms)
  - The /terms endpoint of your server
  - Code comments in server.py

Last updated: 2025
"""

DISCLAIMER_SHORT = """
DISCLAIMER: This service is provided "as is" without warranty of any kind.
Data is retrieved from third-party public APIs and may be incomplete,
inaccurate, or outdated. Not intended for use in clinical, legal, financial,
or safety-critical decisions. Use at your own risk.
"""

DISCLAIMER_FULL = """
================================================================================
SCIENTIFIC TOOLS MCP SERVER — LEGAL DISCLAIMER AND TERMS OF SERVICE
================================================================================

PLEASE READ THIS DISCLAIMER CAREFULLY BEFORE USING THIS SERVICE.
BY ACCESSING OR USING THIS SERVICE, YOU AGREE TO BE BOUND BY THESE TERMS.
IF YOU DO NOT AGREE, DO NOT USE THIS SERVICE.

--------------------------------------------------------------------------------
1. SERVICE DESCRIPTION
--------------------------------------------------------------------------------

The Scientific Tools MCP Server ("Service") provides programmatic access to
publicly available scientific data from third-party sources including but not
limited to PubMed, arXiv, Semantic Scholar, PubChem, ChEMBL, USPTO, EPO,
USGS, NASA, and OpenAQ ("Third-Party Sources").

The Service acts solely as a data retrieval and formatting intermediary.
It does not generate, verify, validate, or independently assess the accuracy
of any data returned from Third-Party Sources.

--------------------------------------------------------------------------------
2. NO WARRANTIES
--------------------------------------------------------------------------------

THE SERVICE IS PROVIDED "AS IS" AND "AS AVAILABLE" WITHOUT WARRANTY OF ANY
KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO:

  (a) WARRANTIES OF MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE;
  (b) WARRANTIES THAT THE SERVICE WILL BE UNINTERRUPTED, ERROR-FREE,
      OR FREE FROM HARMFUL COMPONENTS;
  (c) WARRANTIES AS TO THE ACCURACY, COMPLETENESS, TIMELINESS, RELIABILITY,
      OR CORRECTNESS OF ANY DATA, RESULTS, OR OUTPUTS;
  (d) WARRANTIES THAT THIRD-PARTY SOURCES ARE AVAILABLE, ACCURATE,
      OR UP TO DATE AT ANY TIME;
  (e) IMPLIED WARRANTIES ARISING FROM COURSE OF DEALING OR USAGE OF TRADE.

Data returned by this Service is retrieved from Third-Party Sources over which
the Service has no control. Third-Party Sources may contain errors, omissions,
outdated information, or may be unavailable at any time without notice.

--------------------------------------------------------------------------------
3. LIMITATION OF LIABILITY
--------------------------------------------------------------------------------

TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, THE OPERATOR OF THIS
SERVICE SHALL NOT BE LIABLE FOR ANY:

  (a) DIRECT, INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE
      DAMAGES ARISING FROM YOUR USE OF OR INABILITY TO USE THE SERVICE;
  (b) LOSS OF PROFITS, REVENUE, DATA, BUSINESS, OR GOODWILL;
  (c) DECISIONS MADE IN RELIANCE ON DATA RETURNED BY THIS SERVICE;
  (d) ERRORS, INACCURACIES, OR OMISSIONS IN DATA FROM THIRD-PARTY SOURCES;
  (e) SERVICE INTERRUPTIONS, DOWNTIME, OR DATA LOSS;
  (f) UNAUTHORIZED ACCESS TO OR ALTERATION OF YOUR DATA OR TRANSMISSIONS;
  (g) STATEMENTS OR CONDUCT OF ANY THIRD PARTY IN CONNECTION WITH THE SERVICE.

IN ALL CASES, THE AGGREGATE LIABILITY OF THE SERVICE OPERATOR TO YOU FOR ANY
CLAIMS ARISING FROM OR RELATED TO THIS SERVICE SHALL NOT EXCEED THE TOTAL
AMOUNT PAID BY YOU FOR THE SERVICE IN THE THIRTY (30) DAYS PRECEDING THE
CLAIM.

SOME JURISDICTIONS DO NOT ALLOW THE EXCLUSION OR LIMITATION OF CERTAIN
WARRANTIES OR LIABILITY. IN SUCH JURISDICTIONS, THE ABOVE LIMITATIONS APPLY
TO THE FULLEST EXTENT PERMITTED BY LAW.

--------------------------------------------------------------------------------
4. NOT PROFESSIONAL ADVICE
--------------------------------------------------------------------------------

DATA AND OUTPUTS PROVIDED BY THIS SERVICE DO NOT CONSTITUTE AND MUST NOT
BE RELIED UPON AS:

  (a) MEDICAL, CLINICAL, OR HEALTHCARE ADVICE;
  (b) LEGAL ADVICE OR LEGAL OPINION, INCLUDING PATENT OR IP COUNSEL;
  (c) FINANCIAL, INVESTMENT, OR TRADING ADVICE;
  (d) PHARMACEUTICAL, TOXICOLOGICAL, OR SAFETY ASSESSMENTS;
  (e) SCIENTIFIC CONCLUSIONS OR VALIDATED RESEARCH FINDINGS.

Users requiring professional advice in any of the above domains must consult
qualified licensed professionals. The Service Operator expressly disclaims
any responsibility for decisions made based on outputs from this Service.

Specifically:
  - Literature search results are not a substitute for systematic review
    conducted by qualified researchers.
  - Compound property data is not a substitute for laboratory analysis
    or toxicological assessment by qualified chemists.
  - Patent search results are not a substitute for freedom-to-operate
    analysis conducted by a licensed patent attorney.
  - Earthquake and environmental data are not a substitute for
    official emergency management guidance.

--------------------------------------------------------------------------------
5. DATA ACCURACY AND THIRD-PARTY SOURCES
--------------------------------------------------------------------------------

This Service retrieves data from the following Third-Party Sources, each
subject to their own terms, accuracy limitations, and availability:

  - PubMed / NCBI (National Center for Biotechnology Information)
  - arXiv (Cornell University)
  - Semantic Scholar (Allen Institute for AI)
  - PubChem (National Center for Biotechnology Information)
  - ChEMBL (European Bioinformatics Institute)
  - USPTO (United States Patent and Trademark Office)
  - EPO / Espacenet (European Patent Office)
  - USGS (United States Geological Survey)
  - NASA (National Aeronautics and Space Administration)
  - OpenAQ (Open Air Quality)

The Service Operator makes no representation regarding the accuracy,
completeness, or timeliness of data from any of these sources. Data
may be delayed, incomplete, unavailable, or incorrect at any time.
Users are responsible for independently verifying any data before
relying on it for any purpose.

--------------------------------------------------------------------------------
6. ACCEPTABLE USE
--------------------------------------------------------------------------------

You agree not to use this Service to:

  (a) Make clinical, medical, or safety-critical decisions without
      independent professional verification;
  (b) Circumvent rate limits, access controls, or billing mechanisms;
  (c) Resell, redistribute, or sublicense raw data outputs in violation
      of the terms of the underlying Third-Party Sources;
  (d) Engage in any activity that violates applicable laws or regulations;
  (e) Reverse engineer, decompile, or attempt to extract the Service's
      underlying algorithms or source code beyond what is publicly provided;
  (f) Submit queries designed to extract personally identifiable information
      from Third-Party Sources.

--------------------------------------------------------------------------------
7. SERVICE AVAILABILITY
--------------------------------------------------------------------------------

The Service Operator does not guarantee any specific level of uptime,
availability, or response time. The Service may be interrupted, modified,
suspended, or discontinued at any time with or without notice. The Service
Operator shall not be liable for any losses resulting from service
interruptions or discontinuation.

--------------------------------------------------------------------------------
8. INTELLECTUAL PROPERTY
--------------------------------------------------------------------------------

Data returned by this Service originates from Third-Party Sources and is
subject to the intellectual property rights of those sources and their
respective contributors. The Service Operator claims no ownership over
data retrieved from Third-Party Sources.

The Service infrastructure, code, and formatting are the property of the
Service Operator. Unauthorized reproduction or distribution of the Service
infrastructure is prohibited.

--------------------------------------------------------------------------------
9. PRIVACY AND DATA HANDLING
--------------------------------------------------------------------------------

Query parameters submitted to this Service are processed in memory solely
for the purpose of fulfilling the request and are not stored beyond the
duration of each individual request. Usage metadata (tool name, timestamp,
call volume) is retained for billing and analytics purposes.

No personally identifiable information is knowingly collected, stored, or
transmitted to third parties beyond what is required for payment processing
(Stripe) and API authentication.

For EU users: processing of usage metadata for billing purposes is conducted
under the legitimate interest legal basis pursuant to GDPR Article 6(1)(f).

--------------------------------------------------------------------------------
10. MODIFICATIONS
--------------------------------------------------------------------------------

The Service Operator reserves the right to modify these terms at any time.
Continued use of the Service following any modification constitutes acceptance
of the modified terms. Users are encouraged to review these terms periodically.

--------------------------------------------------------------------------------
11. GOVERNING LAW
--------------------------------------------------------------------------------

These terms shall be governed by and construed in accordance with the laws
of the United States and the state in which the Service Operator is domiciled,
without regard to conflict of law provisions.

To the extent permitted by applicable local, state, national, and international
law, the limitations and exclusions in these terms apply in full. Users and
operators are solely responsible for ensuring their use of this service
complies with their own applicable local, state, national, and international
laws and regulations. The Service Operator makes no representation that the
service is appropriate or available for use in any particular jurisdiction.

Nothing in these terms limits any rights you may have under applicable
mandatory consumer protection laws in your jurisdiction that cannot be
excluded by contract.

--------------------------------------------------------------------------------
12. CONTACT
--------------------------------------------------------------------------------

For questions regarding these terms, contact: your@email.com

================================================================================
END OF DISCLAIMER AND TERMS OF SERVICE
================================================================================
"""

# Short version for code file headers
CODE_HEADER_DISCLAIMER = """
# DISCLAIMER: Data retrieved from third-party public APIs (PubMed, PubChem,
# USPTO, USGS, NASA, OpenAQ, etc.). Provided "as is" without warranty.
# Not intended for clinical, legal, financial, or safety-critical use.
# See /terms endpoint or DISCLAIMER.py for full terms of service.
# Operator liability limited to fees paid in preceding 30 days.
"""


if __name__ == "__main__":
    print(DISCLAIMER_FULL)
