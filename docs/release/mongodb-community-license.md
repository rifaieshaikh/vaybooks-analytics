# MongoDB Community license review

The desktop build downloads MongoDB Community Server and runs it on localhost. That server is licensed under the Server Side Public License (SSPL), not the application’s own license.

Before a commercial desktop distribution:

- Keep the SSPL license notice with the bundled `mongod` binary.
- Do not offer the database as a hosted service under a different license. A hosted deployment should use a separately licensed MongoDB offering or another database.
- The application code that talks to MongoDB is not itself an SSPL derivative merely because it is a client.
- Record the MongoDB version pinned by `desktop` download scripts in the installer third-party notices.

This review does not replace legal advice. It is the checklist the release uses before signing an installer.
