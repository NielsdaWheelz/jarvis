const origin = "https://jarvis.nielseriknandal.com";
const path = "/.well-known/assetlinks.json";
const fingerprint = /^(?:[0-9A-F]{2}:){31}[0-9A-F]{2}$/;

export default {
  fetch(request, env) {
    const url = new URL(request.url);
    if (url.origin !== origin || url.pathname !== path) return new Response(null, { status: 404 });
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response(null, { status: 405, headers: { Allow: "GET, HEAD" } });
    }
    if (!fingerprint.test(env.JARVIS_ANDROID_SIGNER)) {
      return new Response(null, { status: 503 });
    }
    const statements = [{
      relation: ["delegate_permission/common.handle_all_urls"],
      target: {
        namespace: "android_app",
        package_name: "dev.niels.jarvis",
        sha256_cert_fingerprints: [env.JARVIS_ANDROID_SIGNER],
      },
    }];
    return new Response(request.method === "HEAD" ? null : JSON.stringify(statements), {
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "public, max-age=300",
        "X-Content-Type-Options": "nosniff",
      },
    });
  },
};
