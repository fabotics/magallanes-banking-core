# Changelog

One entry per release to `main`. Dates are the day the release was merged, in UTC.

## Unreleased

- Docs: `/docs` has an Authorize button for the API key, a description per group and an example per request body.
- Errors: an unexpected error answers in the API's own JSON shape, with no detail.
- Repository: `SECURITY.md`, this changelog, a `Makefile`, coverage and a dependency audit in CI, CodeQL and Dependabot.

## 0.21.0 (2026-11-17)

- A successful verification carries the profile and the recent card movements.
- The customer's answer about their charges is recorded: recognised or not recognised.
- A case opened too early can be withdrawn.

## 0.20.1 (2026-11-17)

- The assistant in the app has a name, Maggie.

## 0.20.0 (2026-11-17)

- An ID number said aloud is read through its noise.
- The bank caps how often a confirmation is checked and says what to do next.

## 0.19.1 (2026-11-17)

- CRM: the sales board's view holds only what the board can load.

## 0.19.0 (2026-11-17)

- CRM: a five-stage insurance funnel, with cards that say who and how much.

## 0.18.0 (2026-11-16)

- The insurance sale is mirrored to the CRM from the API.

## 0.17.0 (2026-11-16)

- Fixes from two real conversations.

## 0.16.1 (2026-11-16)

- A reload of the sign-in address returns to the sign-in screen.

## 0.16.0 (2026-11-16)

- A third demo customer, an English speaker.

## 0.15.0 (2026-11-16)

- The bank's brand on every customer page.
- The widget can take the customer reference as its own attribute.

## 0.14.0 (2026-11-16)

- The sign-in screen offers the bank's phone line.

## 0.13.0 (2026-11-16)

- The assistant lives inside its own view and follows the app's language.
- The card cover is priced at market level, with higher limits.

## 0.12.0 (2026-11-16)

- Sign in with ID number and PIN. The browser remembers the customer.

## 0.11.0 (2026-11-16)

- An English-speaking customer, and messages in the language of the call.

## 0.10.0 (2026-11-16)

- The app has the bank's own look, a phone frame and a screen to talk to the bank.

## 0.9.0 (2026-11-16)

- Routes to a person, meetings and sales leads.

## 0.8.0 (2026-11-16)

- Channel identity, a waiting status and personal quotes.

## 0.7.0 (2026-11-16)

- Customer pages in English, with a language switch.

## 0.6.0 (2026-11-16)

- The customer app: PIN, identity confirmation and contract signing.

## 0.5.0 (2026-11-16)

- Live signature with a policy number and confirmation messages.

## 0.4.0 (2026-11-16)

- Identity is confirmed in the app first. The spoken check is the fallback.

## 0.3.1 (2026-11-16)

- More tests for the seed script and helpers. README brought in line with the code.

## 0.3.0 (2026-11-16)

- Operations dashboard: resolution, escalation and offer metrics.

## 0.2.0 (2026-11-16)

- Call summary to the customer's messaging channel.

## 0.1.3 (2026-11-16)

- Merchant registry lookup by tax ID, over REST and MCP.

## 0.1.2 (2026-11-16)

- The insurance catalog is available in the pilot country only.

## 0.1.1 (2026-11-16)

- Deployment fix: `requirements.txt` is the only dependency source.

## 0.1.0 (2026-11-16)

- First release: identity verification, accounts, card transactions, temporary card block, cases, insurance eligibility, offers, proposals and the signing page.
