# android access and signer publication

keep the existing self-hosted access app, allowed identity provider, exact owner
policy and connector audience. the connector continues to validate the signed
access assertion on every request it forwards to the jarvis unix socket.

1. in the existing access app, enable managed oauth. enable dynamic client
   registration and allow only
   `https://jarvis.nielseriknandal.com/auth/android`. leave loopback and localhost
   disabled. set the access token lifetime to 15 minutes and the refresh grant to 7 days. browser
   access retains its existing cookie and sign-in policy.
2. the root `/.well-known/cloudflare-access-protected-resource` on jarvis
   identifies the resource and the issuer. read the issuer's
   `/.well-known/oauth-authorization-server` at
   `https://hidden-thunder-6080.cloudflareaccess.com`. use the advertised
   registration endpoint once with
   `client_name=jarvis android`, `token_endpoint_auth_method=none`,
   `grant_types=["authorization_code","refresh_token"]`,
   `response_types=["code"]`, and the single callback above in `redirect_uris`.
   keep the resulting public client id for signed upgrades.
3. in the existing app's public hostname destination, add one public override
   with path pattern `/.well-known/assetlinks.json`. keep the pattern exact.
   publish the worker using this directory's wrangler config and
   `--var "JARVIS_ANDROID_SIGNER:$fingerprint"`, where the value is the trusted
   uppercase, colon-separated sha256 of the apk signing certificate. the
   worker route includes query strings. the worker answers only the exact
   pathname at the edge and never opens the tunnel.
4. confirm that anonymous get returns the signer json with 200 and zero redirects.
   confirm the adjacent path and data routes still require access. inspect the
   application's owner policy and connector audience for equality with the
   pre-change values. check desktop cookie login with the exact owner and
   verify signed android app links and an actual bearer api read before cutover.

[managed oauth](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/managed-oauth/)
· [exact destination overrides](https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/applications/methods/get/)
· [worker routes](https://developers.cloudflare.com/workers/configuration/routing/routes/)
