# Contributing to Sentinel.AI

Thank you for helping make Sentinel.AI more useful, explainable, and adaptable. This project is a foundation: policies, detectors, company knowledge, and providers should be customized by each deployment.

## Before You Start

- Read the repository [README](README.md) and the documentation in `docs/`.
- Open an issue for significant behavior changes so the threat model and intended policy are clear.
- Do not include real secrets, personal data, customer data, or confidential company information in issues, tests, fixtures, or pull requests. Use synthetic examples.

## Good First Contribution Areas

- Add a focused detector for a new sensitive data pattern.
- Improve false-positive handling with a regression test.
- Add or improve a provider adapter behind the categorizer boundary.
- Improve the documentation or customization examples.
- Add synthetic company-knowledge fixtures for vector retrieval tests.

## Development Workflow

1. Fork the repository and create a focused branch.
2. Make the smallest change that solves the issue.
3. Add or update a test for behavior changes.
4. Run the relevant checks:

```powershell
node-gateway\scripts\testPolicyCache.js
Push-Location dashboard
node scripts/testIdentity.js
node scripts/testChatResponse.js
npm ci
npm run build
Pop-Location
Push-Location python-detection
python -m unittest test_risk_engine.py test_sanitizer.py -v
Pop-Location
```

5. Run `git diff --check`.
6. Open a pull request describing the change, policy impact, privacy considerations, and verification results.

## Extension Rules

A detector should return evidence, not an action decision. Keep the final `ALLOW`, `SANITIZE`, or `BLOCK` decision inside the deterministic risk engine. New findings should include a normalized category, confidence, and an optional text span when the value can be safely masked.

Never log or place raw sensitive values in response flags. Use category-level messages and synthetic test fixtures. A new provider must degrade safely when unavailable and must not become the final security authority.

## Pull Requests

Please include:

- The problem and expected behavior.
- The files or extension point changed.
- Tests added or run.
- Any new environment variables or deployment requirements.
- Any known false positives, false negatives, or compatibility concerns.

By contributing, you agree that your contribution can be used and redistributed under the project's eventual license. The repository currently has no license file; add one before accepting external contributions at scale.
