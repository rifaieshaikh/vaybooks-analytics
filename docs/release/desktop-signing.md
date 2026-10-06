# Desktop signing and upgrade

## Windows

The NSIS installer is signed when the build machine has a certificate:

- `CSC_LINK` — path or URL of the code-signing certificate
- `CSC_KEY_PASSWORD` — certificate password

`electron-builder` reads those variables during `npm run dist`. A build without them is unsigned and is not a commercial release.

`npm run dist` sets `CSC_IDENTITY_AUTO_DISCOVERY=false` so the Windows build skips signtool when no certificate is configured.

## macOS

DMG and PKG builds (`npm run dist:mac` and `npm run dist:client:mac`) sign when the build Mac has a Developer ID. The Mac scripts leave identity discovery on.

- **Developer ID Application** signs the app and the DMG
- **Developer ID Installer** signs the PKG

Notarize the signed build so Gatekeeper opens it without an extra approval step. A build without those identities is unsigned. An unsigned app opens after the user allows it in Privacy and Security.

Upgrades keep the existing organization. Documents written before `org_id` existed are treated as the default organization, and the Mongo store writes `org_id: default` on startup.

Support diagnostics are the audit list under Settings → Audit plus a backup from `GET /api/backup`.
