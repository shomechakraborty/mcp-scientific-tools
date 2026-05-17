"""
Privacy Policy
===============
Served at GET /privacy
GDPR-compliant privacy policy for the Scientific Tools MCP Server.
"""

PRIVACY_POLICY = """
================================================================================
SCIENTIFIC TOOLS MCP SERVER — PRIVACY POLICY
================================================================================

Last updated: 2025

This Privacy Policy describes how the Scientific Tools MCP Server
("Service", "we", "us") collects, uses, and protects information
when you use our service at https://mcp-site.com.

--------------------------------------------------------------------------------
1. INFORMATION WE COLLECT
--------------------------------------------------------------------------------

When you request an API key we collect:
  - Email address
  - Name (optional)
  - Intended use case (optional)
  - IP address at time of request
  - User agent string

When you use the API we collect:
  - Tool name called
  - Timestamp of each call
  - Success or failure status
  - Response latency
  - API key identifier (not the key itself)

We do NOT collect:
  - The content of your queries beyond what is needed to fulfil them
  - Personal data about end users of your agent pipelines
  - Payment card details (handled entirely by Stripe)
  - Any data beyond what is listed above

--------------------------------------------------------------------------------
2. HOW WE USE YOUR INFORMATION
--------------------------------------------------------------------------------

We use collected information to:
  - Issue and validate API keys
  - Report usage to Stripe for billing purposes
  - Monitor service health and performance
  - Maintain legal agreement audit records
  - Detect and prevent abuse

We do NOT:
  - Sell your data to third parties
  - Use your data for advertising
  - Share your data with anyone except as described below

--------------------------------------------------------------------------------
3. DATA SHARING
--------------------------------------------------------------------------------

We share data with the following third parties only:

  Stripe (stripe.com): Email address and usage data for billing purposes.
  Stripe's privacy policy: https://stripe.com/privacy

  Hetzner (hetzner.com): Our hosting provider. Server logs may be
  retained per their standard infrastructure policies.
  Hetzner's privacy policy: https://www.hetzner.com/legal/privacy-policy

We do not share your data with any other third parties.

--------------------------------------------------------------------------------
4. DATA RETENTION
--------------------------------------------------------------------------------

  API keys and agreements: Retained permanently as legal records.
  Call logs: Retained for 90 days for billing reconciliation.
  Query content: Not retained — processed in memory only.
  IP addresses: Retained in agreement records permanently.

--------------------------------------------------------------------------------
5. YOUR RIGHTS (GDPR)
--------------------------------------------------------------------------------

If you are located in the European Union, you have the right to:
  - Access the personal data we hold about you
  - Request correction of inaccurate data
  - Request deletion of your data (subject to legal retention requirements)
  - Object to processing of your data
  - Request a copy of your data in a portable format

To exercise any of these rights, contact: shomechakraborty@gmail.com

We will respond to requests within 30 days.

--------------------------------------------------------------------------------
6. CCPA (CALIFORNIA RESIDENTS)
--------------------------------------------------------------------------------

California residents have the right to know what personal information
we collect, request deletion of their personal information, and opt out
of the sale of personal information. We do not sell personal information.

To exercise your rights, contact: shomechakraborty@gmail.com

--------------------------------------------------------------------------------
7. COOKIES
--------------------------------------------------------------------------------

Our API service does not use cookies. Our website may use minimal
session cookies for the checkout flow only. No tracking or advertising
cookies are used.

--------------------------------------------------------------------------------
8. SECURITY
--------------------------------------------------------------------------------

We protect your data using:
  - SSL/TLS encryption for all data in transit
  - File system permissions restricting access to credentials
  - API key authentication for all service access
  - Rate limiting to prevent abuse

--------------------------------------------------------------------------------
9. CHILDREN
--------------------------------------------------------------------------------

This service is not directed at children under 13. We do not knowingly
collect personal information from children under 13.

--------------------------------------------------------------------------------
10. CHANGES TO THIS POLICY
--------------------------------------------------------------------------------

We may update this policy periodically. Continued use of the service
after changes constitutes acceptance of the updated policy.

--------------------------------------------------------------------------------
11. CONTACT
--------------------------------------------------------------------------------

For privacy questions or to exercise your rights:
  Email: shomechakraborty@gmail.com
  Website: https://mcp-site.com

================================================================================
END OF PRIVACY POLICY
================================================================================
"""
