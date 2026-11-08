# RAGVanta web readiness

**QA follow-up fixes are implemented.** The changes and regression tests are summarized below.

Verified on 7 November 2026 in Chrome at 320, 375, 768, and 1440 CSS pixels. Browser checks exercised navigation and checked document width, page titles, metadata, missing-page rendering, favicon availability, and visible links. Form error/success checks used mocked API responses; the Python suites separately exercise real offline application behavior. No paid provider calls were made.

Support links use the owner-provided email `vedantdubey020@gmail.com` and phone `+91 83685 30934`. Phone links use `tel:+918368530934`; email links use `mailto:`. Copyright years update at runtime. No raster images are shipped by these clients; the new SVG favicons are under 0.5 KB, so raster recompression is not applicable. Long evidence tables and preformatted output retain bounded internal scrolling; page-level horizontal scrolling was checked separately.

Dependency audits found no known vulnerabilities in the installed environments at the time of this check. These results are point-in-time checks, not guarantees about future advisories or live infrastructure.

## Changes

- Added responsive workspace navigation with an accessible expanded state, a home link on the brand, favicon, route/view titles and descriptions, and footer contact links.
- Constrained flexible/grid children and long content to prevent page overflow. Mobile inputs use 16px text, and buttons provide at least 44px touch height.
- Added a custom HTML 404 with a real 404 response while preserving JSON API error responses.
- Added specific collection/upload/answer feedback and fixed creation so the new collection becomes active. Owner-scoped collection deletion reclaims quota and removes dependent documents, chunks and vectors.
- Account expiry, logout, cross-tab account changes and delayed responses clear/invalidate account-specific content. Switching collections clears old answers and citations.
- Explicitly package the web assets, including SVG and 404 files, in the Python wheel.

## Evidence

53 Python tests and all three browser regression tests passed. They cover account expiry/cross-tab logout, collection quota recovery, and mobile overflow at 320, 375, 768 and 1440 CSS pixels. Ruff, JavaScript syntax, release invariants, locked dependency resolution, wheel build and installed dependency audit passed. CI installs Chromium before running the browser suite. The wheel includes index, stylesheet, JavaScript, favicon and 404 assets.

## Deployment boundary

The existing hosted profile requires a configured HTTPS origin, administrator-created accounts, persistent disk, provider budgets, and backup configuration. This pass did not provision or deploy a live service, run paid models, or verify a public domain/TLS endpoint. Follow deploy-render.md before release. The local profile deliberately remains loopback-only.
