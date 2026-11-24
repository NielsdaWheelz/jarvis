# private apk

build on the owner's mac with the android sdk, platform 36.1, build-tools 36.1.0
and java 21. the wrapper pins gradle and its distribution digest.

- keep the pkcs12 signing key, its single-line passphrase file and its gradle
  properties file outside the checkout, mode 0600. the properties are
  `storeFile`, `passwordFile` and `keyAlias`. provision independent recovery
  custody for the signing key and record its certificate sha256 separately.
- set `JARVIS_ANDROID_SIGNING_CONFIG` to the properties path. set the public
  `JARVIS_OAUTH_CLIENT_ID` registered on the existing
  [access app](../deploy/home-edge/README.md).
- set the dedicated firebase android app's public
  `JARVIS_FIREBASE_APPLICATION_ID`, `JARVIS_FIREBASE_API_KEY`,
  `JARVIS_FIREBASE_PROJECT_ID` and `JARVIS_FIREBASE_SENDER_ID`. the server
  sending credential stays on the server.
- run `./gradlew :app:assembleRelease -Pjarvis.versionCode=N -Pjarvis.versionName=VERSION`.
  before any install, run `./check-release APK TRUSTED_SHA256 INSTALLED_VERSION_CODE`.
  read the installed version code from android package diagnostics. use 0 for
  the first install. the trusted hash is the same one published at the edge.
- sign upgrades with the same key and install without uninstalling. confirm
  the package's installed version, app-link verification and retained local
  draft before marking the upgrade accepted.
